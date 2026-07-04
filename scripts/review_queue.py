#!/usr/bin/env python3
"""Live view of the human-review queue.

GitHub Issues (label: needs-human-review) are the SINGLE SOURCE OF TRUTH for the
review queue. This script reads their current state live from the API - the same
"don't cache state that lives elsewhere" pattern used for the Harbor registry.

If you close/relabel/edit an issue in the GitHub UI, this reflects it immediately;
there is no YAML to hand-sync. When extraction discovers a NEW flag, the pipeline
OPENS a new issue and stamps its number onto the citation's `review_issue` field.

Usage:
  GITHUB_TOKEN=<token> python scripts/review_queue.py
"""
from __future__ import annotations
import json, os, sys, urllib.request

OWNER, REPO = "christicode", "benchmark-citations"
LABEL = "needs-human-review"


def main() -> None:
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not tok:
        sys.exit("set GITHUB_TOKEN (repo is private)")
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/issues?state=open&labels={LABEL}&per_page=100"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}",
                                               "Accept": "application/vnd.github+json"})
    issues = json.load(urllib.request.urlopen(req))
    issues = [i for i in issues if "pull_request" not in i]
    print(f"OPEN review-queue issues ({len(issues)}):\n")
    for i in sorted(issues, key=lambda x: x["number"]):
        labels = ",".join(l["name"] for l in i["labels"] if l["name"] != LABEL)
        print(f"  #{i['number']:<3} [{labels}]  {i['title']}")
    print("\nSource of truth: GitHub Issues. This is a live read; nothing is cached in-repo.")


if __name__ == "__main__":
    main()
