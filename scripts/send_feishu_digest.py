#!/usr/bin/env python3
"""Send the structured digest from this run to a Feishu custom bot."""

import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict


SITE_URL = "https://gjchen.me/Arxiv-tracker/"
MAX_CHARS = 2000


def build_message(payload):
    groups = defaultdict(list)
    for item in payload.get("items", []):
        names = item.get("groups") or ["今日论文"]
        for name in names:
            groups[name].append(item)

    lines = ["📚 arXiv 每日论文速递"]
    if not groups:
        lines.append("今日暂无新增命中。")
    else:
        for group, papers in groups.items():
            lines.append(f"\n🔹 {group}（{len(papers)}）")
            for paper in papers:
                title = (paper.get("title_zh") or paper.get("title") or "无标题").strip()
                url = (paper.get("html_url") or "").strip()
                lines.append(f"• {title}{f' — {url}' if url else ''}")
                summary = " ".join((paper.get("summary") or "").split())
                if summary:
                    lines.append(f"  {summary}")
    lines.append(f"\n网页：{SITE_URL}")

    message = "\n".join(lines)
    if len(message) > MAX_CHARS:
        suffix = f"\n\n内容较多，完整结果见：{SITE_URL}"
        excerpt = message[: MAX_CHARS - len(suffix) - 2].rsplit("\n", 1)[0]
        message = excerpt + "\n…" + suffix
    return message


def send(webhook, message):
    body = json.dumps({"msg_type": "text", "content": {"text": message}}).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Feishu webhook request failed: {error}") from error
    if result.get("code", result.get("StatusCode", 0)) != 0:
        raise RuntimeError(f"Feishu rejected the message: {result}")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "outputs/feishu_digest.json"
    webhook = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()
    if not webhook:
        raise RuntimeError("FEISHU_WEBHOOK_URL is missing; add it as a GitHub Actions secret")
    with open(path, encoding="utf-8") as source:
        payload = json.load(source)
    message = build_message(payload)
    send(webhook, message)
    print(f"Feishu digest sent ({len(message)} characters)")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Feishu digest failed: {error}", file=sys.stderr)
        raise SystemExit(1)
