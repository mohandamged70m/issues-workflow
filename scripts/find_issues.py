#!/usr/bin/env python3
"""Zero-cost GitHub issue tracker: fresh 48h issues, top 10 by stars -> Discord.

Uses only stdlib (urllib) so no pip install needed in Actions.
- Searches ALL GitHub issues via Search API
- Filters: open, unassigned, not PR, created in lookback window
- Repo gate: min stars, min forks, pushed recently
- Relevance: must match >=1 keyword in title/body/labels
- Sorts by repo stars DESC, takes top N
- Dedupes via state.json, notifies Discord webhook
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
STATE_PATH = os.path.join(ROOT, "state.json")

GITHUB_API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")
DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK_URL", "")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"seen_ids": []}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
            if "seen_ids" not in data:
                return {"seen_ids": []}
            return data
    except Exception:
        return {"seen_ids": []}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def gh_request(url):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "issues-workflow-tracker",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), dict(r.headers)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:500]
        print(f"GitHub API error {e.code} for {url}: {body}")
        if e.code == 403 and "rate limit" in body.lower():
            print("Rate limited. Wait 60s and retry once...")
            time.sleep(60)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8")), dict(r.headers)
        return None, {}
    except Exception as e:
        print(f"Request failed {url}: {e}")
        return None, {}


def build_queries(cfg, since_date):
    # Broad OR logic: one query per label + one fallback with NO label filter.
    # Fallback ensures we still get top-10 fresh issues even when
    # beginner labels have 0 hits in 48h window.
    # Language + keywords are filtered in Python after fetching repo.
    base = f"type:issue state:open created:>{since_date}"
    labels = cfg.get("labels", [])
    queries = [f'{base} label:"{l}"' for l in labels]
    # fallback: any fresh issue (sorted created desc, filtered by stars/keywords in code)
    queries.append(base)
    return queries


def build_query(cfg, since_date):
    # kept for backwards compat / logging
    return " ".join(build_queries(cfg, since_date)[:1])


def search_issues(query):
    params = {
        "q": query,
        "sort": "created",
        "order": "desc",
        "per_page": "100",
    }
    url = f"{GITHUB_API}/search/issues?{urllib.parse.urlencode(params)}"
    print(f"Searching: {query}")
    data, headers = gh_request(url)
    if not data:
        return []
    print(f"Found {data.get('total_count', 0)} total, returning {len(data.get('items', []))}")
    return data.get("items", [])


def get_repo(full_name, cache):
    if full_name in cache:
        return cache[full_name]
    url = f"{GITHUB_API}/repos/{full_name}"
    data, _ = gh_request(url)
    # be nice to API: small delay between repo fetches
    time.sleep(0.5)
    if data:
        cache[full_name] = data
    return data


def matches_keywords(issue, keywords):
    text = " ".join([
        issue.get("title", ""),
        issue.get("body") or "",
    ]).lower()
    label_names = " ".join(l.get("name", "") for l in issue.get("labels", [])).lower()
    hay = text + " " + label_names
    matched = [k for k in keywords if k.lower() in hay]
    return matched


def parse_dt(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def main():
    cfg = load_config()
    state = load_state()
    seen = set(state.get("seen_ids", []))

    lookback_hours = cfg.get("lookback_hours", 48)
    max_results = cfg.get("max_results", 10)
    min_stars = cfg.get("min_stars", 500)
    min_forks = cfg.get("min_forks", 50)
    max_age_days = cfg.get("max_age_days", 7)
    push_max_months = cfg.get("repo_push_max_age_months", 6)
    keywords = cfg.get("keywords", [])

    now = datetime.now(timezone.utc)
    since_dt = now - timedelta(hours=lookback_hours)
    since_date = since_dt.strftime("%Y-%m-%d")
    print(f"Window: created > {since_date} (last {lookback_hours}h), top {max_results} by stars")

    query_list = build_queries(cfg, since_date)
    print(f"Running {len(query_list)} sub-queries (one per label, no language constraint)")
    merged = {}
    for q in query_list:
        for it in search_issues(q):
            merged[it.get("id")] = it
        time.sleep(2)  # respect search rate limit (30 req/min)
    issues = list(merged.values())
    print(f"Merged unique issues from all labels: {len(issues)}")

    repo_cache = {}
    candidates = []
    push_cutoff = now - timedelta(days=push_max_months * 30)
    age_cutoff = now - timedelta(days=max_age_days)

    for issue in issues:
        # skip PRs (search type:issue should exclude, but double-check)
        if "pull_request" in issue:
            continue
        gid = issue.get("id")
        if gid in seen:
            continue
        # prefer unassigned (was no:assignee in old query, now enforced here)
        if issue.get("assignees") or issue.get("assignee"):
            continue

        created = parse_dt(issue.get("created_at", ""))
        if not created:
            continue
        # hard freshness gates: must be newer than max_age_days AND in lookback
        if created < age_cutoff:
            continue
        if created < since_dt - timedelta(hours=6):  # small tolerance
            continue

        repo_url = issue.get("repository_url", "")
        full_name = repo_url.replace("https://api.github.com/repos/", "") if repo_url else ""
        if not full_name:
            # fallback: parse html_url owner/repo
            try:
                parts = issue.get("html_url", "").split("/")
                full_name = f"{parts[3]}/{parts[4]}"
            except Exception:
                continue

        repo = get_repo(full_name, repo_cache)
        if not repo:
            continue

        stars = repo.get("stargazers_count", 0)
        forks = repo.get("forks_count", 0)
        if stars < min_stars or forks < min_forks:
            continue

        pushed = parse_dt(repo.get("pushed_at", "1970-01-01T00:00:00Z"))
        if pushed and pushed < push_cutoff:
            continue  # dead repo

        matched = matches_keywords(issue, keywords)
        if keywords and not matched:
            continue

        repo_lang = (repo.get("language") or "")
        allowed = {l.lower() for l in cfg.get("languages", [])}
        # enforce stack fit: repo main language must be JS/TS/Python (case-insensitive)
        # if repo language is unknown, allow via keyword match instead
        if repo_lang and allowed and repo_lang.lower() not in allowed:
            continue

        candidates.append({
            "id": gid,
            "number": issue.get("number"),
            "title": issue.get("title", "")[:200],
            "url": issue.get("html_url", ""),
            "created_at": issue.get("created_at", ""),
            "repo": full_name,
            "stars": stars,
            "forks": forks,
            "repo_lang": repo_lang,
            "matched": matched[:5],
            "labels": [l.get("name", "") for l in issue.get("labels", [])][:5],
        })

    # top 10 based on stars
    candidates.sort(key=lambda x: x["stars"], reverse=True)
    top = candidates[:max_results]

    print(f"Candidates after filter: {len(candidates)}, sending top: {len(top)}")

    if not top:
        print("No new matching issues. Nothing to send.")
        return 0

    if DISCORD_WEBHOOK:
        send_discord(top, cfg)
    else:
        print("DISCORD_WEBHOOK_URL not set — printing instead:")
        for c in top:
            print(f"⭐ {c['stars']} {c['repo']} #{c['number']} {c['title']} {c['url']}")

    # mark as seen only after (attempted) send
    for c in top:
        seen.add(c["id"])
    state["seen_ids"] = sorted(seen)[-2000:]  # cap growth
    state["last_run"] = now.isoformat()
    state["last_sent"] = len(top)
    save_state(state)
    return 0


def send_discord(items, cfg):
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
            "title": f"{c['title'][:200]}",
            "url": c["url"],
            "description": desc,
            "color": 5814783,
        })

    # Discord allows max 10 embeds per message — we send max 10
    payload = {
        "content": f"🔥 **Top {len(items)} fresh issues (48h, ⭐-sorted)** — Full-stack JS/TS/Python",
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
        # don't crash — state still saves? No: raise so Actions shows failure
        # but save state anyway to avoid resend loop? We save only on success path above.
        # Here we exit 1 without saving, so next run retries.
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
