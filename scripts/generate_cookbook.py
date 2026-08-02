#!/usr/bin/env python3
"""Generate cookbook/index.html and cookbook/recipes/*.html from recipe/*.md.

The markdown notes are informal, hand-written Obsidian notes with no
consistent structure (different heading styles, bracket-wrapped titles,
inline timestamps, mixed bullet/numbered lists, etc). This generator applies
a best-effort generic markdown->HTML conversion plus heuristics to split
content into "ingredients" and "steps" sections. It will not reproduce the
hand-polished prose/tips found in some existing cookbook pages -- see
CLAUDE.md for what it can and can't do.

Usage: python3 scripts/generate_cookbook.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECIPE_DIR = ROOT / "recipe"
COOKBOOK_DIR = ROOT / "cookbook"
CONFIG_PATH = Path(__file__).resolve().parent / "recipes.json"

# ---------------------------------------------------------------------------
# Inline markdown -> HTML
# ---------------------------------------------------------------------------

def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline_md(text: str) -> str:
    s = esc(text.strip())
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)  # drop inline emoji images
    s = re.sub(
        r"\[\[(\d{1,2}:\d{2}(?::\d{2})?)\]\((https?://[^\s)]+)\)\]",
        r'<a class="tstamp" href="\2">\1</a>',
        s,
    )
    s = re.sub(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]", r'<span class="tstamp">\1</span>', s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r" {2,}", " ", s)
    return s.strip()


def strip_md(text: str) -> str:
    """Plain-text version of a line, used for heuristics (not rendering)."""
    s = text.strip()
    # Timestamps contain a literal colon (e.g. [00:06:23]) which would
    # otherwise be mistaken for a "label: value" ingredient delimiter.
    s = re.sub(r"\[\[(\d{1,2}:\d{2}(?::\d{2})?)\]\((https?://[^\s)]+)\)\]", "", s)
    s = re.sub(r"\[(\d{1,2}:\d{2}(?::\d{2})?)\]", "", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[*_`#]", "", s)
    return s.strip()


def extract_url(text: str) -> str:
    """Pull the actual href out of a "just a link" line, in case the link's
    display text differs from its target (e.g. "[Https://...](https://...)"
    where the display text has a typo'd capital scheme)."""
    m = re.match(r"^\[[^\]]+\]\((https?://[^\s)]+)\)$", text.strip(), re.IGNORECASE)
    if m:
        return m.group(1)
    return strip_md(text)


# ---------------------------------------------------------------------------
# Block-level markdown parser (subset tailored to these notes)
# ---------------------------------------------------------------------------

def parse_list(lines, i, ordered):
    m0 = re.match(r"^(\s*)", lines[i])
    base_indent = len(m0.group(1))
    items = []
    while i < len(lines):
        line = lines[i]
        if line.strip() == "":
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            if j < len(lines):
                m_next = re.match(r"^(\s*)([-*]\s+|\d+\.(?!\d)\s*)", lines[j])
                if m_next:
                    indent2 = len(m_next.group(1))
                    if indent2 > base_indent:
                        # Nested child of the last item -- marker type doesn't
                        # have to match (e.g. a numbered stage with bulleted
                        # sub-actions under it).
                        i = j
                        continue
                    next_ordered = bool(re.match(r"^\s*\d+\.(?!\d)", lines[j]))
                    if indent2 >= base_indent and next_ordered == ordered:
                        i = j
                        continue
            break
        m = re.match(r"^(\s*)(?:([-*])\s+|(\d+)\.(?!\d)\s*)(.*)$", line)
        if not m:
            break
        item_ordered = m.group(3) is not None
        indent = len(m.group(1))
        text = m.group(4)
        if indent <= base_indent:
            if item_ordered != ordered:
                break
            items.append({"text": text, "sub": [], "continuation": []})
            i += 1
        elif items:
            items[-1]["sub"].append(text)
            i += 1
        else:
            if item_ordered != ordered:
                break
            items.append({"text": text, "sub": [], "continuation": []})
            i += 1
    return items, i


def parse_blocks(raw: str):
    text = raw.replace("​", "")
    lines = text.split("\n")
    blocks = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if stripped == "":
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            blocks.append({"type": "heading", "text": m.group(2)})
            i += 1
            continue

        if re.match(r"^-{3,}$", stripped) or re.match(r"^\*{3,}$", stripped):
            blocks.append({"type": "hr"})
            i += 1
            continue

        if "|" in stripped and i + 1 < n and re.match(
            r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$", lines[i + 1].strip()
        ):
            header = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            blocks.append({"type": "table", "header": header, "rows": rows})
            continue

        if stripped.startswith(">"):
            bq = []
            while i < n and lines[i].strip().startswith(">"):
                bq.append(re.sub(r"^>\s?", "", lines[i].strip()))
                i += 1
            blocks.append({"type": "blockquote", "lines": bq})
            continue

        if re.match(r"^\s*([-*]\s+|\d+\.(?!\d)\s*)", line):
            ordered = bool(re.match(r"^\s*\d+\.(?!\d)", line))
            items, i = parse_list(lines, i, ordered)
            blocks.append({"type": "olist" if ordered else "ulist", "items": items})
            continue

        m_b = re.match(r"^\*\*(.+)\*\*$", stripped)
        if m_b:
            blocks.append({"type": "pseudo_heading", "text": m_b.group(1)})
            i += 1
            continue

        m_br = re.match(r"^\[([^\]]+)\]$", stripped)
        if m_br:
            blocks.append({"type": "pseudo_heading", "text": m_br.group(1)})
            i += 1
            continue

        # A line that's just a decorative emoji image followed by a short
        # label (e.g. "![💡](url) 조리할 때 핵심 팁") is being used as a
        # section header even though it has no # or bracket/bold wrapping.
        m_img = re.match(r"^!\[[^\]]*\]\([^)]*\)\s*(.+)$", stripped)
        if m_img:
            rest = strip_md(m_img.group(1))
            if rest and len(rest) <= 40 and not re.search(r"[.!?]$", rest):
                blocks.append({"type": "pseudo_heading", "text": rest})
                i += 1
                continue

        plain_stripped = strip_md(stripped)
        if (
            plain_stripped
            and len(plain_stripped) <= 24
            and ":" not in plain_stripped
            and "：" not in plain_stripped
            and not re.search(r"[.!?]$", plain_stripped)
        ):
            j = i + 1
            while j < n and lines[j].strip() == "":
                j += 1
            if j < n and re.match(r"^\s*([-*]\s+|\d+\.(?!\d)\s*)", lines[j]):
                blocks.append({"type": "pseudo_heading", "text": stripped})
                i += 1
                continue

        para_lines = [stripped]
        i += 1
        while i < n and lines[i].strip() != "" and not re.match(
            r"^(#{1,6}\s|\s*[-*]\s|\s*\d+\.(?!\d)\s*|>|\|)", lines[i]
        ):
            para_lines.append(lines[i].strip())
            i += 1
        blocks.append({"type": "para", "text": " ".join(para_lines)})

    # Attach trailing paragraphs/blockquotes to the preceding list's last item
    # (covers notes where a numbered step is followed by an explanatory
    # paragraph and/or a callout before the next step).
    merged = []
    for b in blocks:
        if b["type"] in ("para", "blockquote") and merged and merged[-1]["type"] in ("olist", "ulist"):
            merged[-1]["items"][-1]["continuation"].append(b)
            continue
        merged.append(b)
    return merged


# ---------------------------------------------------------------------------
# Section grouping + classification
# ---------------------------------------------------------------------------

SENTENCE_END_CHARS = set("다요함음림짐김침슴늠줌")


def ends_like_instruction(s: str) -> bool:
    s = s.rstrip(" .!)]~-")
    return bool(s) and s[-1] in SENTENCE_END_CHARS


def item_looks_like_ingredient(text: str) -> bool:
    plain = strip_md(text)
    if ":" in plain or "：" in plain:
        val = re.split(r"[:：]", plain, 1)[1].strip()
        if ends_like_instruction(val):
            return False
        return len(val) <= 60
    if ends_like_instruction(plain):
        return False
    return len(plain) <= 22 and bool(re.search(r"\d", plain))


def list_role(block) -> str:
    if block["type"] == "olist":
        return "steps"
    votes = [item_looks_like_ingredient(it["text"]) for it in block["items"]]
    if not votes:
        return "steps"
    return "ingredients" if sum(votes) >= len(votes) / 2 else "steps"


def block_role(block) -> str:
    """Classify a single content block on its own. A heading only tells you
    where one thing ends and another begins -- it doesn't tell you what kind
    of thing follows (some notes put an ingredients list and a steps list
    back to back with no heading between them at all), so role is decided
    per block, not per section.
    """
    if block["type"] == "table":
        return "table"
    if block["type"] in ("ulist", "olist"):
        return list_role(block)
    if block["type"] == "para":
        plain = strip_md(block["text"])
        if re.match(r"^https?://", plain, re.IGNORECASE) and "youtu" in plain.lower():
            return "source"
        # Some notes write ingredients as bare "label: value" lines
        # separated by blank lines instead of as a bulleted list.
        return "ingredients" if item_looks_like_ingredient(block["text"]) else "note"
    return "note"  # blockquote and anything else


def build_units(blocks):
    """Group consecutive blocks that share both a heading and a role into
    one renderable unit, in document order.

    A single heading can cover a run of mixed-role content (e.g. a lead-in
    sentence classified as a "note" followed by the ingredient list it
    introduces) which now splits into multiple units. Only the first unit
    in that run keeps the heading text, so it isn't rendered twice.
    """
    units = []
    current_heading = None
    heading_shown = False
    for b in blocks:
        if b["type"] in ("heading", "pseudo_heading"):
            current_heading = strip_md(b["text"])
            heading_shown = False
            continue
        if b["type"] == "hr":
            continue
        role = block_role(b)
        if units and units[-1]["raw_heading"] == current_heading and units[-1]["role"] == role:
            units[-1]["blocks"].append(b)
            continue
        display_heading = None if (current_heading is not None and heading_shown) else current_heading
        if current_heading is not None:
            heading_shown = True
        units.append({"heading": display_heading, "raw_heading": current_heading, "role": role, "blocks": [b]})
    return smooth_units(units)


def smooth_units(units):
    """Reabsorb a single stray "note" unit sandwiched between two
    "ingredients" units under the same heading. Per-paragraph classification
    occasionally misjudges one line in an otherwise uniform list (e.g. a
    quantity note ending in a word that happens to look like a verb
    ending); in context it's clearly still part of the same list, so treat
    it as one rather than fragmenting the list around it."""
    i = 1
    while i < len(units) - 1:
        prev_u, cur_u, next_u = units[i - 1], units[i], units[i + 1]
        if (
            cur_u["role"] == "note"
            and prev_u["role"] == "ingredients"
            and next_u["role"] == "ingredients"
            and prev_u["raw_heading"] == cur_u["raw_heading"] == next_u["raw_heading"]
        ):
            prev_u["blocks"].extend(cur_u["blocks"])
            prev_u["blocks"].extend(next_u["blocks"])
            del units[i : i + 2]
            continue
        i += 1
    return units


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_sub_list(sub_lines, ordered=False):
    tag = "ol" if ordered else "ul"
    out = [f"<{tag}>"]
    for s in sub_lines:
        out.append(f"<li>{inline_md(s)}</li>")
    out.append(f"</{tag}>")
    return "".join(out)


def render_blockquote(bq_block):
    lines = bq_block["lines"]
    items = [ln[2:].strip() for ln in lines if re.match(r"^[-*]\s+", ln)]
    prose = [ln for ln in lines if not re.match(r"^[-*]\s+", ln) and ln.strip()]
    cls = "warning" if any("주의" in ln for ln in prose) else "tip"
    out = [f'<blockquote class="{cls}">']
    for p in prose:
        out.append(f"<p>{inline_md(p)}</p>")
    if items:
        out.append(render_sub_list(items))
    out.append("</blockquote>")
    return "".join(out)


def render_continuation(item):
    out = []
    for b in item["continuation"]:
        if b["type"] == "para":
            out.append(f"<p>{inline_md(b['text'])}</p>")
        elif b["type"] == "blockquote":
            out.append(render_blockquote(b))
    return "".join(out)


def render_ingredient_group(heading, blocks):
    lis = []
    for b in blocks:
        if b["type"] in ("ulist", "olist"):
            for it in b["items"]:
                line = inline_md(it["text"])
                if it["sub"]:
                    line += render_sub_list(it["sub"])
                line += render_continuation(it)
                lis.append(f"<li>{line}</li>")
        elif b["type"] == "para":
            lis.append(f"<li>{inline_md(b['text'])}</li>")
    body = f'<ul class="ingredient-list">{"".join(lis)}</ul>'
    if heading and heading != "재료":
        return f'<div class="sub-ingredient"><span class="sub-title">{inline_md(heading)}</span>{body}</div>'
    return body


GENERIC_STEP_RE = re.compile(r"조리\s*순서|조리\s*방법|요리\s*순서|만드는\s*법")


def render_items_as_list(items):
    out = ["<ul>"]
    for it in items:
        line = inline_md(it["text"])
        sub_html = render_sub_list(it["sub"]) if it["sub"] else ""
        cont_html = render_continuation(it)
        out.append(f"<li>{line}{sub_html}{cont_html}</li>")
    out.append("</ul>")
    return "".join(out)


def render_steps_group(heading, blocks):
    """Return a list of <li> HTML strings for one steps-classified section.

    Headings that just restate the overall "조리 순서" section title are
    dropped (they'd be redundant with the h3 above the list). A heading that
    names one particular stage (e.g. "2. 재료 손질하기") over a flat bullet
    list becomes a single step with the bullets nested inside it. A heading
    over an already-numbered list is treated as a label on the first of
    those numbered steps, since the source already delimits the steps
    itself.
    """
    is_generic = bool(heading and GENERIC_STEP_RE.search(heading))
    effective_heading = None if is_generic else heading

    list_blocks = [b for b in blocks if b["type"] in ("ulist", "olist")]
    other_blocks = [b for b in blocks if b["type"] not in ("ulist", "olist")]

    if effective_heading and not list_blocks and other_blocks:
        body = "".join(render_generic_block(b) for b in other_blocks)
        return [f'<li><p class="step-title">{inline_md(effective_heading)}</p>{body}</li>']

    if effective_heading and len(list_blocks) == 1 and list_blocks[0]["type"] == "ulist":
        nested = render_items_as_list(list_blocks[0]["items"])
        return [f'<li><p class="step-title">{inline_md(effective_heading)}</p>{nested}</li>']

    lis = []
    first = True
    for block in list_blocks:
        for it in block["items"]:
            line = inline_md(it["text"])
            sub_html = render_sub_list(it["sub"]) if it["sub"] else ""
            cont_html = render_continuation(it)
            # A short label with an explanatory paragraph following it (e.g.
            # "감자 손질하기:두께 3~4mm.") reads better as a step title than
            # as an unstyled run-on line before the paragraph.
            is_short_label = bool(it["continuation"]) and len(strip_md(it["text"])) <= 30
            if first and effective_heading:
                lis.append(
                    f'<li><p class="step-title">{inline_md(effective_heading)}</p>'
                    f"<p>{line}</p>{sub_html}{cont_html}</li>"
                )
            elif is_short_label:
                lis.append(f'<li><p class="step-title">{line}</p>{sub_html}{cont_html}</li>')
            else:
                lis.append(f"<li>{line}{sub_html}{cont_html}</li>")
            first = False
    return lis


def render_generic_block(b):
    if b["type"] == "para":
        return f"<p>{inline_md(b['text'])}</p>"
    if b["type"] == "blockquote":
        return render_blockquote(b)
    if b["type"] == "ulist":
        return render_sub_list([it["text"] for it in b["items"]])
    if b["type"] == "olist":
        return render_sub_list([it["text"] for it in b["items"]], ordered=True)
    if b["type"] == "table":
        return render_table(b)
    return ""


def render_table(b):
    out = ['<table class="ratio-table"><thead><tr>']
    for h in b["header"]:
        out.append(f"<th>{inline_md(h)}</th>")
    out.append("</tr></thead><tbody>")
    for row in b["rows"]:
        out.append("<tr>" + "".join(f"<td>{inline_md(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def render_recipe_body(md_text: str) -> str:
    blocks = parse_blocks(md_text)
    units = build_units(blocks)

    ingredient_html_parts = []
    step_lis = []
    extra_html_parts = []
    source_html = None

    for unit in units:
        role, heading = unit["role"], unit["heading"]
        if role == "ingredients":
            ingredient_html_parts.append(render_ingredient_group(heading, unit["blocks"]))
        elif role == "steps":
            step_lis.extend(render_steps_group(heading, unit["blocks"]))
        elif role == "table":
            table_block = next(b for b in unit["blocks"] if b["type"] == "table")
            title = f'<h3 class="section-title">{inline_md(heading)}</h3>' if heading else ""
            extra_html_parts.append(f'<div class="tips">{title}{render_table(table_block)}</div>')
        elif role == "source" and source_html is None:
            para = unit["blocks"][0]
            url = extract_url(para["text"])
            source_html = f'<p class="recipe-source">출처: <a href="{esc(url)}">{esc(url)}</a></p>'
        else:  # note (also catches any extra "source" units beyond the first)
            title = f'<h3 class="section-title">{inline_md(heading)}</h3>' if heading else ""
            body = "".join(render_generic_block(b) for b in unit["blocks"])
            if body:
                extra_html_parts.append(f'<div class="tips">{title}{body}</div>')

    out = []
    if source_html:
        out.append(source_html)
    if ingredient_html_parts:
        out.append('<h3 class="section-title">재료</h3>')
        out.extend(ingredient_html_parts)
    if step_lis:
        out.append('<h3 class="section-title">조리 순서</h3>')
        out.append(f'<div class="steps"><ol>{"".join(step_lis)}</ol></div>')
    out.extend(extra_html_parts)
    return "\n    ".join(out)


# ---------------------------------------------------------------------------
# Page templates
# ---------------------------------------------------------------------------

RECIPE_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} · 나의 요리책</title>
<link rel="stylesheet" href="../style.css">
</head>
<body class="recipe-page">

<nav class="recipe-nav"><a class="back-link" href="../index.html">&larr; 차례로</a></nav>

<main>
  <section class="recipe" id="{slug}">
    <div class="recipe-header">
      <span class="recipe-num">{num:02d}</span>
      <h2>{title}</h2>
    </div>

    {body}
  </section>
</main>

<nav class="recipe-pager">
  {prev_link}
  {next_link}
</nav>

</body>
</html>
"""

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>나의 요리책</title>
<link rel="stylesheet" href="style.css">
</head>
<body>

<div class="cover">
  <div class="eyebrow">Home Cooking Notes</div>
  <h1>나의 요리책</h1>
  <p>메모해 둔 {count}가지 레시피를 한 권으로 모았습니다. 재료와 조리 순서는 원본 그대로, 보기 편하도록 구성만 정리했습니다.</p>
  <div class="count">총 {count}개 레시피</div>
</div>

<div class="toc-book">
  <h2>차례</h2>
  <div class="toc-columns">
{toc}
  </div>
</div>

<footer class="book-footer">
  개인 레시피 노트 모음 &middot; {count} recipes
</footer>

</body>
</html>
"""


def build_flat_order(config):
    order = []
    for cat in config["categories"]:
        for slug in cat["recipes"]:
            order.append(slug)
    return order


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    order = build_flat_order(config)
    recipes_dir = COOKBOOK_DIR / "recipes"
    recipes_dir.mkdir(parents=True, exist_ok=True)

    for idx, slug in enumerate(order, start=1):
        meta = config["recipes"][slug]
        md_path = RECIPE_DIR / meta["md"]
        md_text = md_path.read_text(encoding="utf-8")
        body = render_recipe_body(md_text)

        prev_slug = order[idx - 2] if idx > 1 else None
        next_slug = order[idx] if idx < len(order) else None
        prev_link = (
            f'<a href="{prev_slug}.html">&larr; 이전: {esc(config["recipes"][prev_slug]["title"])}</a>'
            if prev_slug
            else "<span></span>"
        )
        next_link = (
            f'<a class="pager-next" href="{next_slug}.html">다음: {esc(config["recipes"][next_slug]["title"])} &rarr;</a>'
            if next_slug
            else "<span></span>"
        )

        html = RECIPE_TEMPLATE.format(
            title=esc(meta["title"]),
            slug=slug,
            num=idx,
            body=body,
            prev_link=prev_link,
            next_link=next_link,
        )
        out_path = recipes_dir / f"{slug}.html"
        out_path.write_text(html, encoding="utf-8")
        print(f"wrote {out_path.relative_to(ROOT)}")

    toc_lines = []
    for cat in config["categories"]:
        toc_lines.append('    <div class="toc-group">')
        toc_lines.append(f'      <h3 class="toc-group-label">{esc(cat["name"])}</h3>')
        toc_lines.append('      <ol class="toc-list">')
        for slug in cat["recipes"]:
            title = esc(config["recipes"][slug]["title"])
            toc_lines.append(f'        <li><a href="recipes/{slug}.html">{title}</a></li>')
        toc_lines.append('      </ol>')
        toc_lines.append('    </div>')
    index_html = INDEX_TEMPLATE.format(count=len(order), toc="\n".join(toc_lines))
    (COOKBOOK_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print(f"wrote {(COOKBOOK_DIR / 'index.html').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
