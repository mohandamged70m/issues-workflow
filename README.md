# Fresh Issues Workflow — Top 10 by Stars, Every 6h

Zero-cost automation: searches **all GitHub** for fresh Full-stack issues and pings Discord.

- Stack: JavaScript / TypeScript / Python / Next.js / FastAPI / MongoDB / Supabase / PostgreSQL
- Fresh only: created in last **48h**, max age 7 days, sorted newest → then **top 10 by ⭐ stars**
- Quality gate: repo `stars > 500`, `forks > 50`, pushed in last 6 months (active, popular)
- Labels: `good first issue`, `help wanted`, `up-for-grabs`, `hacktoberfest`
- Schedule: every 6h (`0 */6 * * *`) + manual Run
- Cost: $0 (GitHub Actions free tier + Discord webhook free)

## Setup (already done once)

1. Discord Server > Integrations > Webhooks > Copy URL (keep private, regenerate if leaked)
2. GitHub repo > Settings > Secrets and variables > Actions > `DISCORD_WEBHOOK_URL` = Discord URL
3. Push this code. Actions > Fresh Issues Tracker > Run workflow to test.

## Files

- `config.json` — tune `min_stars`, `lookback_hours`, `languages`, `keywords`
- `scripts/find_issues.py` — stdlib only, no deps
- `.github/workflows/issues-tracker.yml` — cron every 6h
- `state.json` — seen issue IDs (auto-committed, prevents resends)

## Test locally

```bash
python scripts/find_issues.py
# with Discord:
set DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
python scripts/find_issues.py
```
