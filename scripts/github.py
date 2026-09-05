"""GitHub API layer — search issues + fetch repo details. Stdlib only."""
import json
import os
import time
import urllib.request
import urllib.parse

GITHUB_API = "https://api.github.com"
TOKEN = os.environ.get("GITHUB_TOKEN", "")


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
    """OR logic: one query per label + fallback with no label filter."""
    base = f"type:issue state:open created:>{since_date}"
    labels = cfg.get("labels", [])
    queries = [f'{base} label:"{l}"' for l in labels]
    queries.append(base)  # fallback ensures volume when labels have 0 hits
    return queries


def search_issues(query):
    params = {"q": query, "sort": "created", "order": "desc", "per_page": "100"}
    url = f"{GITHUB_API}/search/issues?{urllib.parse.urlencode(params)}"
    print(f"Searching: {query}")
    data, _ = gh_request(url)
    if not data:
        return []
    print(f"Found {data.get('total_count', 0)} total, returning {len(data.get('items', []))}")
    return data.get("items", [])


def search_all(cfg, since_date):
    queries = build_queries(cfg, since_date)
    print(f"Running {len(queries)} sub-queries (OR labels + fallback)")
    merged = {}
    for q in queries:
        for it in search_issues(q):
            merged[it.get("id")] = it
        time.sleep(2)  # respect search rate limit
    issues = list(merged.values())
    print(f"Merged unique issues: {len(issues)}")
    return issues


def get_repo(full_name, cache):
    if full_name in cache:
        return cache[full_name]
    url = f"{GITHUB_API}/repos/{full_name}"
    data, _ = gh_request(url)
    time.sleep(0.5)
    if data:
        cache[full_name] = data
    return data
