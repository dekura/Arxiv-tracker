#!/usr/bin/env python3
"""Send the structured digest from this run to a Feishu custom bot."""

import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict


SITE_URL = "https://gjchen.me/Arxiv-tracker/"
MAX_CHARS = 6000
SUMMARY_CHARS = 180


def _markdown_escape(value):
    return str(value or "").replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def build_markdown(payload):
    groups = defaultdict(list)
    for item in payload.get("items", []):
        names = item.get("groups") or ["今日论文"]
        for name in names:
            groups[name].append(item)

    lines = ["> 今天的 arXiv 新发现，挑重点快速读起来。"]
    if not groups:
        lines.append("\n🌱 **今天没有新命中**\n\n检索还在继续，明天再来看看。")
    else:
        for group, papers in groups.items():
            lines.append(f"\n### {group} · {len(papers)} 篇")
            for paper in papers:
                title = (paper.get("title_zh") or paper.get("title") or "无标题").strip()
                url = (paper.get("html_url") or "").strip()
                title_md = _markdown_escape(title)
                title_md = f"[{title_md}]({url})" if url else title_md
                summary = " ".join((paper.get("summary") or "").split())
                if summary:
                    if len(summary) > SUMMARY_CHARS:
                        summary = summary[:SUMMARY_CHARS].rsplit(" ", 1)[0].rstrip("，,。.;；") + "…"
                    lines.append(f"- **{title_md}**\n  {summary}")
                else:
                    lines.append(f"- **{title_md}**")

    if groups:
        ranked = sorted(groups.items(), key=lambda entry: (-len(entry[1]), entry[0]))
        focus, focus_papers = ranked[0]
        focus_count = len(focus_papers)
        counts = "、".join(f"{name} {len(papers)}篇" for name, papers in ranked)
        unique_ids = {
            paper.get("id") or paper.get("title")
            for papers in groups.values()
            for paper in papers
        }
        lines.append(f"\n### 📈 今日观察\n共命中 **{len(unique_ids)} 篇**，{focus}方向最多（{focus_count}篇）。各方向：{counts}。")

    lines.append(f"\n[🌐 打开完整日报]({SITE_URL})")
    markdown = "\n".join(lines)
    if len(markdown) > MAX_CHARS:
        suffix = f"\n\n…其余论文请查看[完整日报]({SITE_URL})"
        markdown = markdown[: MAX_CHARS - len(suffix) - 1].rsplit("\n", 1)[0] + suffix
    return markdown


def build_card(payload):
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "📚 arXiv 每日论文速递"},
        },
        "elements": [{"tag": "markdown", "content": build_markdown(payload)}],
    }


def send(webhook, card):
    body = json.dumps({"msg_type": "interactive", "card": card}, ensure_ascii=False).encode("utf-8")
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
    card = build_card(payload)
    send(webhook, card)
    print(f"Lark digest card sent ({len(card['elements'][0]['content'])} characters)")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Feishu digest failed: {error}", file=sys.stderr)
        raise SystemExit(1)
