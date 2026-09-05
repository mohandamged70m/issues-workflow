#!/usr/bin/env python3
"""Orchestrator: search -> filter -> top10 by stars -> notify -> save state."""
import sys
import os
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import load_config, load_state, save_state
from github import search_all, get_repo
from filters import is_candidate, repo_full_name
from notify import notify_or_print


def main():
    cfg = load_config()
    state = load_state()
    seen = set(state.get("seen_ids", []))

    lookback_hours = cfg.get("lookback_hours", 48)
    max_results = cfg.get("max_results", 10)
    max_age_days = cfg.get("max_age_days", 7)
    push_max_months = cfg.get("repo_push_max_age_months", 6)

    now = datetime.now(timezone.utc)
    since_dt = now - timedelta(hours=lookback_hours)
    since_date = since_dt.strftime("%Y-%m-%d")
    print(f"Window: created > {since_date} (last {lookback_hours}h), top {max_results} by stars")

    issues = search_all(cfg, since_date)

    repo_cache = {}
    candidates = []
    push_cutoff = now - timedelta(days=push_max_months * 30)
    age_cutoff = now - timedelta(days=max_age_days)

    for issue in issues:
        gid = issue.get("id")
        if gid in seen:
            continue
        full_name = repo_full_name(issue)
        if not full_name:
            continue
        repo = get_repo(full_name, repo_cache)
        if not repo:
            continue

        ok, reason, matched, repo_lang = is_candidate(issue, repo, cfg, since_dt, age_cutoff, push_cutoff)
        if not ok:
            continue

        candidates.append({
            "id": gid,
            "number": issue.get("number"),
            "title": (issue.get("title", "") or "")[:200],
            "url": issue.get("html_url", ""),
            "created_at": issue.get("created_at", ""),
            "repo": full_name,
            "stars": repo.get("stargazers_count", 0),
            "forks": repo.get("forks_count", 0),
            "repo_lang": repo_lang,
            "matched": matched[:5],
            "labels": [l.get("name", "") for l in issue.get("labels", [])][:5],
        })

    candidates.sort(key=lambda x: x["stars"], reverse=True)
    top = candidates[:max_results]
    print(f"Candidates after filter: {len(candidates)}, sending top: {len(top)}")

    sent = notify_or_print(top, cfg)

    # save state even on empty runs (updates last_run), mark seen only if sent
    if sent:
        for c in top:
            seen.add(c["id"])
    state["seen_ids"] = sorted(seen)[-2000:]
    state["last_run"] = now.isoformat()
    state["last_sent"] = len(top) if sent else 0
    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
