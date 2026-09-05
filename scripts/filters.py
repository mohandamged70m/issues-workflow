"""Filtering: freshness, stars/forks, language fit, keywords. Edit rules here."""
from datetime import datetime, timedelta


def parse_dt(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def matches_keywords(issue, keywords):
    text = " ".join([issue.get("title", ""), issue.get("body") or ""]).lower()
    label_names = " ".join(l.get("name", "") for l in issue.get("labels", [])).lower()
    hay = text + " " + label_names
    return [k for k in keywords if k.lower() in hay]


def repo_full_name(issue):
    repo_url = issue.get("repository_url", "")
    if repo_url:
        return repo_url.replace("https://api.github.com/repos/", "")
    try:
        parts = issue.get("html_url", "").split("/")
        return f"{parts[3]}/{parts[4]}"
    except Exception:
        return ""


def is_candidate(issue, repo, cfg, since_dt, age_cutoff, push_cutoff):
    """Return (ok, reason, matched, repo_lang). Single place for all gates."""
    if "pull_request" in issue:
        return False, "is-pr", [], ""
    if issue.get("assignees") or issue.get("assignee"):
        return False, "assigned", [], ""

    created = parse_dt(issue.get("created_at", ""))
    if not created:
        return False, "no-date", [], ""
    if created < age_cutoff:
        return False, "too-old", [], ""
    if created < since_dt - timedelta(hours=6):
        return False, "outside-window", [], ""

    stars = repo.get("stargazers_count", 0)
    forks = repo.get("forks_count", 0)
    if stars < cfg.get("min_stars", 500):
        return False, f"stars-{stars}", [], ""
    if forks < cfg.get("min_forks", 50):
        return False, f"forks-{forks}", [], ""

    pushed = parse_dt(repo.get("pushed_at", "1970-01-01T00:00:00Z"))
    if pushed and pushed < push_cutoff:
        return False, "dead-repo", [], ""

    matched = matches_keywords(issue, cfg.get("keywords", []))
    if cfg.get("keywords") and not matched:
        return False, "no-keyword", [], ""

    repo_lang = repo.get("language") or ""
    allowed = {l.lower() for l in cfg.get("languages", [])}
    if repo_lang and allowed and repo_lang.lower() not in allowed:
        return False, f"lang-{repo_lang}", [], ""

    return True, "ok", matched, repo_lang
