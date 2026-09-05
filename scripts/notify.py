"""Discord notification only. Add more channels here later (no Telegram yet)."""
import json
import os
import sys
import urllib.request

DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")


def send_discord(items, cfg):
    lookback = cfg.get("lookback_hours", 48)
    embeds = []
    for c in items:
        desc = (
            f"⭐ **{c['stars']}** stars | 🍴 {c['forks']} | `{c['repo_lang']}`\n"
            f"📦 `{c['repo']}`\n"
            f"🏷️ {', '.join(c['labels']) if c['labels'] else 'no-label'}\n"
            f"🎯 matched: {', '.join(c['matched'])}\n"
            f"🕒 {c['created_at'][:10]}"
        )
        embeds.append({
            "title": c["title"][:200],
            "url": c["url"],
            "description": desc,
            "color": 5814783,
        })

    payload = {
        "content": f"🔥 **Top {len(items)} fresh issues ({lookback}h, ⭐-sorted)** — Full-stack JS/TS/Python",
        "embeds": embeds[:10],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        DISCORD_WEBHOOK,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "issues-tracker"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"Discord notified: HTTP {r.status}")
    except Exception as e:
        print(f"Discord send failed: {e}")
        sys.exit(1)


def notify_or_print(top, cfg):
    if not top:
        print("No new matching issues. Nothing to send.")
        return False
    if DISCORD_WEBHOOK:
        send_discord(top, cfg)
    else:
        print("DISCORD_WEBHOOK_URL not set — printing instead:")
        for c in top:
            print(f"⭐ {c['stars']} {c['repo']} #{c['number']} {c['title']} {c['url']}")
    return True
