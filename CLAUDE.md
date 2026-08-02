# recipe

A personal Korean-language recipe collection with two parts:

- `recipe/*.md` — source notes (an Obsidian vault; `recipe/.obsidian/` is Obsidian's own app config, not project data). Hand-written, inconsistently formatted: headings range from `### Heading` to bracket-wrapped lines (`[제목]`) to whole-line-bold (`**제목**`) to bare short lines with no markup at all. Ingredient lists are sometimes bullets, sometimes bare "label: value" lines separated by blank lines. Steps are sometimes numbered, sometimes bulleted, sometimes prose. Some notes embed YouTube source links and `[mm:ss]` timestamps.
- `cookbook/` — the static site rendered from those notes: `cookbook/index.html` (cover + table of contents, recipes grouped by category) and `cookbook/recipes/<slug>.html` (one page per recipe, styled by `cookbook/style.css`).

## Regenerating the site

```bash
python3 scripts/generate_cookbook.py
```

This rewrites every file under `cookbook/recipes/` and `cookbook/index.html` from the current contents of `recipe/*.md`. No dependencies beyond the Python 3 standard library — run it after editing any recipe note to keep the site in sync.

### `scripts/recipes.json`

The generator does not infer slugs, English filenames, categories, or display order from the Markdown — those are curatorial decisions a script can't make reliably from unstructured Korean notes. They live in `scripts/recipes.json`:

- `categories`: ordered list of `{name, recipes: [slug, ...]}` — this defines both the table-of-contents grouping *and* the global recipe numbering / prev-next pager order (flattened top to bottom).
- `recipes`: `slug -> {title, md}` mapping each slug to its display title and source filename under `recipe/`.

**To add a new recipe:** drop the `.md` file in `recipe/`, add an entry to `recipes`, and list its slug under the right category — then rerun the generator.

## How the converter works (`scripts/generate_cookbook.py`)

There's no markdown library dependency; it's a small hand-rolled parser tailored to the shapes actually seen in these notes, not general CommonMark. Pipeline:

1. **`parse_blocks`** — line-based parser producing a flat list of blocks: `heading`, `pseudo_heading` (bracket-line / bold-line / bare short label / emoji-prefixed label — see below), `ulist`/`olist` (with one level of nesting), `para`, `blockquote`, `table`, `hr`. A trailing paragraph or blockquote that directly follows a list gets attached to that list's *last item* as `continuation` (this is what lets a numbered step be immediately followed by an explanatory paragraph and/or a warning callout in the source, e.g. `감자그라탕.md`, `금태 구이.md`).

2. **`block_role`** — classifies each block independently as `ingredients`, `steps`, `table`, `source` (a bare YouTube link), or `note`. There is deliberately no single per-section classification: a heading can introduce a run of mixed content (e.g. an intro sentence, then an ingredient list, then a steps list, all with no heading between them — see `삼치 데리야끼.md`), so classification happens block-by-block and consecutive same-role blocks under the same heading are grouped into one render unit (`build_units`).
   - List role: an `olist` is always `steps` (the source explicitly numbered it). A `ulist`'s role is decided by majority vote of `item_looks_like_ingredient` across its items.
   - `item_looks_like_ingredient`: a line is treated as an ingredient if, after stripping markdown and `[mm:ss]` timestamps, its "label: value" tail is short and doesn't end in a Korean sentence-final verb ending (다/요/함/줌/... — see `SENTENCE_END_CHARS`). This is a heuristic, not NLP — see Known limitations below.
   - `smooth_units` then reabsorbs a single stray `note`-role paragraph that's sandwiched between two `ingredients`-role blocks under the same heading, so one misclassified line doesn't fracture an otherwise-uniform ingredient list into three pieces.

3. **Rendering** — `render_ingredient_group` / `render_steps_group` turn units into the site's existing HTML shapes (`ingredient-list`, `sub-ingredient`, `steps` / `step-title`, `tips`, `ratio-table`, `tstamp` links, etc. — all defined in `cookbook/style.css`). A heading is only shown once per run of units that share it, so an intro sentence followed by its list doesn't repeat the label.

4. **Inline markdown** (`inline_md`) handles bold, italic, inline code, links, dropped emoji-image markdown, and two timestamp shapes: `[[mm:ss](url)]` → a clickable `tstamp` link, bare `[mm:ss]` → a `tstamp` span.

## Known limitations (accepted trade-off, not bugs)

This is a **generic** converter, not a per-recipe curator. For a cleanly-bulleted note (e.g. `함박스테이크.md`) the output matches a hand-tuned page almost exactly. For messier notes it will not reproduce hand-editorial polish:

- No automatic prose rewriting — a terse bullet stays a terse bullet.
- No automatic extraction of "tips" vs "steps" beyond what the block-role heuristic infers from shape (short label+value vs. long verb-ending sentence).
- A `.md` file that mixes several unrelated ingredient labels into one run-on paragraph (no bullets, no blank lines between labels — e.g. the `주재료/양념 재료/비법 재료` block in `만능된장.md`) renders as one prose note rather than a split ingredient list, because splitting a single paragraph into multiple labeled items isn't attempted.
- A `.md` file describing two distinct recipes in one file (also `만능된장.md`, which has both "만능된장" and "된장찌개") produces one page with both folded in; it doesn't try to detect "this is actually two recipes."
- If a heading is followed by both a short lead-in sentence *and* the list it introduces (no heading in between), the heading is attached to the sentence, not the list, and the two can end up visually separated once bucketed into the page's fixed 재료 / 조리 순서 / notes zones (e.g. `샤브샤브.md`'s "추천: 시트러스 폰즈 소스").

If a recipe renders oddly, the fastest fix is almost always to make the source `.md` more uniform (consistent bullets, blank line between distinct ideas) rather than special-casing the generator.

## Testing

There's no test suite. After changing the generator, sanity-check with:

```bash
python3 scripts/generate_cookbook.py
python3 -c "
import re, glob
for f in glob.glob('cookbook/recipes/*.html') + ['cookbook/index.html']:
    t = open(f, encoding='utf-8').read()
    for tag in ['div','ul','ol','li','p','blockquote','table','a']:
        o, c = len(re.findall(rf'<{tag}[ >]', t)), len(re.findall(rf'</{tag}>', t))
        if o != c: print(f, tag, o, c)
"
```

and spot-read a few of the messier notes (`스키야키.md`, `짜글이.md`, `감자그라탕.md`, `치즈불닭.md` are good stress tests — they exercise nested timestamps, headed stages, and numbered-item-plus-explanation patterns).

## Agent skills

### Issue tracker

Issues live in hwbros/recipe's GitHub Issues (uses the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context layout — `CONTEXT.md` + `docs/adr/` at the repo root (created lazily as needed). See `docs/agents/domain.md`.
