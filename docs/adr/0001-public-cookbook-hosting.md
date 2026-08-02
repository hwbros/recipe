---
status: accepted
---

# Public hosting for the cookbook site

`cookbook/` needs to be reachable from other computers over the internet, not just this machine. This server (`home-server`) already runs two other public services behind nginx on ports 80/443 (bookfolio via Cloudflare on `ellybookfolio.com`, norwegian-singles-strava via DuckDNS + Let's Encrypt on `nsmrun.duckdns.org`), so we reuse that pattern instead of introducing a new mechanism.

**Decision**: Add a third nginx `server` block that serves `cookbook/` as static files directly from its path in this repo (`/home/hwbros/work/recipe/cookbook`, no copy to `/var/www`), under a new DuckDNS hostname `recipe.duckdns.org`, with a Let's Encrypt certificate (auto-renewed by the existing system-wide `certbot.timer`) and HTTP→HTTPS redirect. The DuckDNS subdomain is registered under the same DuckDNS account/token already used for `nsmrun.duckdns.org` — DuckDNS subdomains are independent of each other, so this doesn't affect the strava app's DNS record, and the token never leaves the server. The site has no authentication; it's public with no login, matching the other two services and the low sensitivity of the content.

**Considered and rejected**:
- LAN-only access — rejected; the user explicitly wants access from anywhere on the internet, not just the home network.
- A standalone process on a new port, bypassing nginx entirely — rejected; would require a new router port-forward, which is a physical/manual step outside what this session can do, whereas 80/443 are already forwarded.
- A brand-new DuckDNS account isolated from nssapp's — rejected; subdomains under one DuckDNS account don't share fate, so the isolation benefit is negligible against the extra manual OAuth signup step.
- HTTP Basic Auth — rejected; content isn't sensitive and the other two public services on this box don't gate access either.
