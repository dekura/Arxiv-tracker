#!/usr/bin/env python3
"""Send this run's structured arXiv digest to a Lark custom bot."""

import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

# When invoked as ``python scripts/send_feishu_digest.py``, Python puts the
# scripts directory (not the repository root) on sys.path. Add the project root
# so this standalone Actions entry point can import the shared package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SITE_URL = "https://gjchen.me/Arxiv-tracker/"
MAX_CHARS = 12000
SUMMARY_CHARS = 300


def _escape_label(value):
    """Escape Markdown characters used inside link labels and plain text."""
    value = str(value or "")
    for char in ("\\", "`", "*", "_", "[", "]"):
        value = value.replace(char, "\\" + char)
    return value


def _shorten(text, limit):
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    clipped = text[:limit]
    # Prefer a word boundary for English, but Chinese text usually has no
    # spaces. Never let rsplit() turn a long Chinese string into just "…".
    if " " in clipped:
        word_boundary = clipped.rsplit(" ", 1)[0]
        if len(word_boundary) >= limit * 0.65:
            clipped = word_boundary
    else:
        for punctuation in ("。", "！", "？", "；", "，", ".", "!", "?", ";", ","):
            boundary = clipped.rfind(punctuation)
            if boundary >= limit * 0.65:
                clipped = clipped[:boundary]
                break
    return clipped.rstrip("，,。.;；:：！？!?") + "…"


def _group_items(payload):
    groups = defaultdict(list)
    for item in payload.get("items", []):
        names = item.get("groups") or ["今日论文"]
        for name in names:
            groups[name].append(item)
    return groups


def _analysis_claim(label, claim, item_by_id, text_key="text"):
    if not claim:
        return ""
    text = _escape_label(_shorten(claim.get(text_key) or "", 110))
    citations = []
    for paper_id in claim.get("paper_ids") or []:
        paper = item_by_id.get(paper_id)
        if not paper:
            continue
        title = _escape_label(paper.get("title_zh") or paper.get("title") or "论文")
        url = paper.get("html_url") or paper_id
        citations.append(f"[{title}]({url})")
    evidence = f"（依据：{'、'.join(citations)}）" if citations else ""
    return f"• **{label}**：{text}{evidence}"


def build_markdown(payload):
    groups = _group_items(payload)
    lines = ["🌱 **今天的 arXiv 新发现，看看研究问题正在往哪里走。**"]
    if payload.get("report_date"):
        lines.append(f"📅 {payload['report_date']}")
    unique_count = len({item.get("id") or item.get("title") for item in payload.get("items", [])})
    lines.append(f"📊 本期新增 {unique_count} 篇（按论文去重）")
    if not groups:
        lines.extend(["", "今天没有新的命中，检索会继续运行，明天再来看看。"])
    else:
        for group, papers in groups.items():
            # Lark card Markdown does not reliably render headings/blockquote.
            lines.extend(["", f"📚 **{_escape_label(group)} · {len(papers)} 篇**"])
            for paper in papers:
                title = (paper.get("title_zh") or paper.get("title") or "无标题").strip()
                url = (paper.get("html_url") or "").strip()
                title_md = _escape_label(title)
                if url:
                    title_md = f"[{title_md}]({url})"
                summary = _shorten(paper.get("summary"), SUMMARY_CHARS)
                lines.append(f"• **{title_md}**")
                if summary:
                    lines.append(f"  {summary}")
                code_urls = list(dict.fromkeys(paper.get("code_urls") or []))
                if code_urls:
                    code_links = " · ".join(f"[Code {index}]({url})" for index, url in enumerate(code_urls[:3], 1))
                    lines.append(f"  代码：{code_links}")

    group_analysis = payload.get("group_analysis") or {}
    populated_analysis = [
        (group, analysis) for group, analysis in group_analysis.items()
        if not analysis.get("empty") and analysis.get("count")
    ]
    if populated_analysis:
        item_by_id = {item.get("id"): item for item in payload.get("items", []) if item.get("id")}
        lines.extend(["", "🔎 **今日观察｜趋势、关注点与可做的问题**"])
        for group, analysis in populated_analysis:
            lines.extend(["", f"**{_escape_label(group)}**"])
            for label, key in (("方向变化", "direction"), ("论文联系", "connections"), ("共同瓶颈", "bottleneck")):
                rendered = _analysis_claim(label, analysis.get(key), item_by_id)
                if rendered:
                    lines.append(rendered)
            for question in analysis.get("next_steps") or []:
                rendered = _analysis_claim("可验证的问题", question, item_by_id, text_key="question")
                if rendered:
                    lines.append(rendered)

    lines.extend(["", f"🌐 [打开完整日报]({SITE_URL})"])
    markdown = "\n".join(lines)
    if len(markdown) > MAX_CHARS:
        # Preserve the trend analysis and site link; shorten the paper section first.
        marker = "\n🔎 **今日观察｜趋势、关注点与可做的问题**"
        if marker in markdown:
            prefix, tail = markdown.split(marker, 1)
            suffix = marker + tail
            notice = "\n\n…其余论文及详情请查看完整日报"
            budget = max(0, MAX_CHARS - len(suffix) - len(notice))
            prefix = prefix[:budget].rsplit("\n", 1)[0]
            markdown = prefix + notice + suffix
        else:
            suffix = f"\n\n…详情请查看[完整日报]({SITE_URL})"
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
        raise RuntimeError(f"Lark webhook request failed: {error}") from error
    if result.get("code", result.get("StatusCode", 0)) != 0:
        raise RuntimeError(f"Lark rejected the message: {result}")


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
        print(f"Lark digest failed: {error}", file=sys.stderr)
        raise SystemExit(1)
