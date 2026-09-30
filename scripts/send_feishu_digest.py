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

from arxiv_tracker.insights import TRAINING_LABELS  # noqa: E402

SITE_URL = "https://gjchen.me/Arxiv-tracker/"
MAX_CHARS = 12000
FIELD_CHARS = 70
# Tiers are tried in order until the card fits MAX_CHARS; later tiers drop the least essential lines.
DETAIL_TIERS = (
    (("problem", "核心问题"), ("challenge", "关键困难"), ("solution", "解决方案"), ("future", "未来方向")),
    (("problem", "核心问题"), ("solution", "解决方案")),
    (),
)


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
    for name in payload.get("groups") or []:
        groups[name]
    for item in payload.get("items", []):
        for name in item.get("groups") or ["今日论文"]:
            groups[name].append(item)
    return {name: papers for name, papers in groups.items() if papers}


def _title_link(paper):
    title = _escape_label((paper.get("title") or "Untitled").strip())
    url = (paper.get("html_url") or "").strip()
    return f"[{title}]({url})" if url else title


def _tag_line(paper):
    tags = paper.get("tags") or {}
    bits = [" + ".join(tags.get("training") or []), tags.get("architecture"), tags.get("application")]
    return " · ".join(_escape_label(bit) for bit in bits if bit)


def _paper_lines(paper, fields):
    lines = [f"• **{_title_link(paper)}**"]
    tag_line = _tag_line(paper)
    if tag_line:
        lines.append(f"  {tag_line}")
    innovation = ((paper.get("tags") or {}).get("innovation") or "").strip()
    if innovation:
        lines.append(f"  💡 {_escape_label(_shorten(innovation, FIELD_CHARS))}")
    facts = [f"**{label}**：{_escape_label(_shorten(paper[key], FIELD_CHARS))}"
             for key, label in fields if (paper.get(key) or "").strip()]
    for index in range(0, len(facts), 2):
        lines.append("  " + " ｜ ".join(facts[index:index + 2]))
    code_urls = list(dict.fromkeys(paper.get("code_urls") or []))
    if code_urls:
        lines.append("  代码：" + " · ".join(f"[Code {i}]({u})" for i, u in enumerate(code_urls[:3], 1)))
    return lines


def _training_summary(items):
    counts = defaultdict(int)
    for item in items:
        for label in (item.get("tags") or {}).get("training") or []:
            counts[label] += 1
    ordered = sorted(counts, key=lambda label: TRAINING_LABELS.index(label) if label in TRAINING_LABELS else 99)
    return " · ".join(f"{label} {counts[label]}" for label in ordered)


def _render(payload, fields):
    items = payload.get("items", [])
    unique_count = len({item.get("id") or item.get("title") for item in items})
    with_code = sum(1 for item in items if item.get("code_urls"))
    header = " · ".join(bit for bit in (payload.get("report_date"), f"{unique_count} 篇",
                                         f"{with_code} 篇有代码") if bit)
    lines = [f"📅 {header}"]
    distribution = _training_summary(items)
    if distribution:
        lines.append(f"🏷 训练方法：{distribution}")
    groups = _group_items(payload)
    if not groups:
        lines.extend(["", "今天没有新的命中，检索会继续运行，明天再来看看。"])
    shown_in = {}
    for group, papers in groups.items():
        # Lark card Markdown does not reliably render headings/blockquote.
        lines.extend(["", f"📚 **{_escape_label(group)} · {len(papers)} 篇**"])
        for paper in papers:
            key = paper.get("id") or paper.get("title")
            if key in shown_in:
                lines.append(f"• {_title_link(paper)}（见「{_escape_label(shown_in[key])}」）")
                continue
            shown_in[key] = group
            lines.extend(_paper_lines(paper, fields))
    lines.extend(["", f"🌐 [打开完整日报（可按方向/训练方法筛选）]({SITE_URL})"])
    return "\n".join(lines)


def build_markdown(payload):
    for fields in DETAIL_TIERS:
        markdown = _render(payload, fields)
        if len(markdown) <= MAX_CHARS:
            return markdown
    suffix = f"\n\n…其余论文请查看[完整日报]({SITE_URL})"
    return markdown[: MAX_CHARS - len(suffix) - 1].rsplit("\n", 1)[0] + suffix


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
