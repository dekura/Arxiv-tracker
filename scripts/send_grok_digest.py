#!/usr/bin/env python3
"""Send this run's arXiv digest summary to a Grok Bot webhook."""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.send_feishu_digest import build_markdown  # noqa: E402

TITLE = "📚 arXiv 每日论文速递"


def build_message(payload, repo="", workflow="", ref="", run_url=""):
    """Same Markdown summary as the Feishu card, plus where this run lives."""
    summary = build_markdown(payload)
    message = {"title": TITLE, "text": summary, "summary": summary}
    for key, value in (
        ("repo", repo),
        ("workflow", workflow),
        ("ref", ref),
        ("run_url", run_url),
    ):
        if value:
            message[key] = value
    return message


def send(webhook, key, message):
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=body,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Grok webhook rejected the digest: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"Grok webhook request failed: {error.reason}") from error
    if status >= 300:
        raise RuntimeError(f"Grok webhook rejected the digest: HTTP {status}")
    return status


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "outputs/feishu_digest.json"
    webhook = os.environ.get("GROK_WEBHOOK_URL", "").strip()
    key = os.environ.get("GROK_WEBHOOK_KEY", "").strip()
    if not webhook or not key:
        raise RuntimeError(
            "GROK_WEBHOOK_URL or GROK_WEBHOOK_KEY is missing; add both as GitHub Actions secrets"
        )
    with open(path, encoding="utf-8") as source:
        payload = json.load(source)
    message = build_message(
        payload,
        repo=os.environ.get("GROK_REPO", "").strip(),
        workflow=os.environ.get("GROK_WORKFLOW", "").strip(),
        ref=os.environ.get("GROK_REF", "").strip(),
        run_url=os.environ.get("GROK_RUN_URL", "").strip(),
    )
    status = send(webhook, key, message)
    print(f"Grok digest sent ({len(message['summary'])} characters, HTTP {status})")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Grok digest failed: {error}", file=sys.stderr)
        raise SystemExit(1)
