# Deploying Ai-Lens

Ai-Lens runs two ways:

- **Static:** `python/build_static.py` writes the pages plus the news data as JSON files. Any
  static host can serve it, and a scheduled job rebuilds it to keep the feed fresh.
- **Server:** `python/server.py` serves the site and refreshes the feed itself, which also enables
  the "Refresh now" button.

## Recommended: GitHub Pages + GitHub Actions, free

The workflow in `.github/workflows/pages.yml` runs every 12 hours (00:00 and 12:00 UTC), on every push to `main`, and
on demand. Each run:

1. Downloads the previous news history from the live site (`api/store.json`), so stories older
   than the feeds' own windows are kept for `RETENTION_DAYS`.
2. Fetches all feeds, optionally translates new stories with Claude, and builds `_site/`.
3. Deploys `_site/` to GitHub Pages.

**One-time setup**
1. Repository **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. Optional: **Settings → Secrets and variables → Actions → New repository secret**
   `ANTHROPIC_API_KEY` to enable Arabic/English translation of headlines.
3. Run the workflow once from the **Actions** tab, or push to `main`.

The site is then at `https://<your-user>.github.io/<repo>/` until a custom domain is set.

**On-time refreshes with a Cloudflare Worker** (optional, free)

GitHub starts scheduled runs late on the free tier, often by several hours. The Worker in
`tools/cron-worker/` uses Cloudflare Cron Triggers, which fire on time, to start the workflow at
00:00 and 12:00 UTC. GitHub's own schedule stays as a backup.

1. On GitHub: **Settings → Developer settings → Personal access tokens → Fine-grained tokens →
   Generate new token**. Repository access: **Only select repositories** → this repository.
   Permissions: **Actions: Read and write** (nothing else). Copy the token.
2. In `tools/cron-worker/`:

   ```sh
   npx wrangler login
   npx wrangler deploy
   npx wrangler secret put GITHUB_TOKEN    # paste the token
   ```

3. Check it in the Cloudflare dashboard: **Workers → ai-lens-cron → Settings → Trigger events**,
   and its logs after the next run. The Worker has no public URL. When the token expires, create
   a new one and run `wrangler secret put GITHUB_TOKEN` again.

**Custom domain** (an apex domain such as `example.com`)
1. At your DNS provider, point the domain to GitHub Pages. Add one record per address; most DNS
   panels reject several addresses in one field.

   | Type | Name | Value |
   |---|---|---|
   | A | `@` | `185.199.108.153` |
   | A | `@` | `185.199.109.153` |
   | A | `@` | `185.199.110.153` |
   | A | `@` | `185.199.111.153` |
   | AAAA | `@` | `2606:50c0:8000::153` (optional, if your DNS panel supports AAAA) |
   | AAAA | `@` | `2606:50c0:8001::153` |
   | AAAA | `@` | `2606:50c0:8002::153` |
   | AAAA | `@` | `2606:50c0:8003::153` |
   | CNAME | `www` | `<your-user>.github.io` |

   These are GitHub's published Pages addresses. Replace any existing A record pointing to your
   registrar's parking page.
2. In **Settings → Pages → Custom domain**, enter the domain, wait for the DNS check to pass, then
   enable **Enforce HTTPS**. GitHub issues the certificate automatically, which can take up to an hour.
3. Recommended: verify the domain under your GitHub account (**Settings → Pages → Verified domains**)
   so no other repository can claim it.

Old DNS answers can stay cached for the previous record's TTL, often a few hours. If the old page
still appears, check with a public resolver (`dig +short example.com @1.1.1.1`).

**Limits to know**
- Actions minutes are free for public repositories.
- Scheduled runs can start several minutes late when GitHub is busy.
- To refresh more often, change the `cron` line in the workflow (e.g. `0 */6 * * *` for every 6 hours)
  and `REFRESH_MINUTES` to match. Or run the workflow on demand from the Actions tab.
- GitHub disables scheduled workflows in public repositories after 60 days without repository
  activity. Any commit re-enables them, or re-enable the workflow from the Actions tab.
- Pages is meant for sites like this one: a 1 GB size limit and a soft bandwidth limit of
  100 GB a month. The built site is about 1.5 MB.

## Alternative: Cloudflare Pages, free

Use this if you want Cloudflare's CDN or already manage your domain's DNS there.
Keep the same GitHub Action, but replace the deploy job with a `wrangler pages deploy _site`
step using a Cloudflare API token secret. The feed refresh still runs in GitHub Actions.

## Alternative: a small VPS (a few dollars or euros a month)

Use this for a true live server: refresh on your own schedule, the "Refresh now" button, and no
scheduling delays.

```sh
git clone https://github.com/<your-user>/<repo>.git && cd <repo>
cp .env.server.example .env      # HOST=0.0.0.0, DATA_PATH, LOG_PATH, BASE_PATH
./tools/start.sh
```

Put it behind a reverse proxy with HTTPS (Caddy or nginx), and use a systemd unit or cron
`@reboot` to run `tools/start.sh` at boot.

## Cost of the optional Claude translation

Only stories not translated before are sent, in batches of 20, capped by
`ENRICH_MAX_PER_REFRESH` per run. Results are kept in the news store, so each story is translated
once. Without the `ANTHROPIC_API_KEY` secret the step is skipped and hosting stays free.
