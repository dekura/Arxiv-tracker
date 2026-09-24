#!/usr/bin/env python3
"""Send this run's structured arXiv digest to a Lark custom bot."""

import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict

import yaml

from arxiv_tracker.llm import _chat_completions_request, _json_loose


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
    return text[:limit].rsplit(" ", 1)[0].rstrip("，,。.;；:：") + "…"


def _group_items(payload):
    groups = defaultdict(list)
    for item in payload.get("items", []):
        names = item.get("groups") or ["今日论文"]
        for name in names:
            groups[name].append(item)
    return groups


def _fallback_observations(groups):
    """Produce evidence-based notes if the configured LLM is unavailable."""
    notes = []
    ranked = sorted(groups.items(), key=lambda entry: (-len(entry[1]), entry[0]))
    for name, papers in ranked[:3]:
        examples = []
        for paper in papers[:2]:
            title = paper.get("title_zh") or paper.get("title") or "无标题"
            summary = _shorten(paper.get("summary"), 100).rstrip("。；;，,")
            examples.append(f"《{title}》{('：' + summary) if summary else ''}")
        if examples:
            notes.append(
                f"**{_escape_label(name)}方向**：本期代表工作包括" + "；".join(examples)
                + "。后续可重点比较这些方法在真实仓库、长程任务及成本约束下的稳定性。"
            )
    if not notes:
        notes.append("本期没有新增论文，暂时无法从本期样本判断研究趋势；可继续观察后续几天的主题变化。")
    return notes


def generate_observations(payload, config_path="config.yaml"):
    """Synthesize research signals across papers; never block delivery on LLM errors."""
    groups = _group_items(payload)
    if not groups:
        return _fallback_observations(groups)

    llm_cfg = {}
    try:
        with open(config_path, encoding="utf-8") as source:
            llm_cfg = (yaml.safe_load(source) or {}).get("llm") or {}
    except (OSError, yaml.YAMLError):
        pass
    api_key = os.getenv(llm_cfg.get("api_key_env") or "DS_API_KEY", "")
    if not api_key:
        return _fallback_observations(groups)

    # Keep the synthesis grounded in this run's actual item summaries.
    papers = []
    seen = set()
    for item in payload.get("items", []):
        key = item.get("id") or item.get("title")
        if key in seen:
            continue
        seen.add(key)
        papers.append({
            "groups": item.get("groups") or [],
            "title": item.get("title_zh") or item.get("title") or "",
            "abstract_or_digest": _shorten(item.get("summary"), 700),
        })
    if not papers:
        return _fallback_observations(groups)

    prompt = (
        "根据本次 arXiv 日报中的论文标题、分组和摘要，写 3 到 5 条有信息量的研究观察。\n"
        "每条都要结合至少两篇论文或明确指出它是单篇新方向；分析研究趋势、方法关注点、共同瓶颈，"
        "并提出具体可做的后续研究问题/实验。不要只复述篇数或逐篇摘要。"
        "观察内容用纯文本，不要输出标题标记、引用块或其他 Markdown 符号。\n"
        "只依据给定材料；区分材料证据与推测，不虚构实验结果。不同分组可以交叉综合。"
        "用简洁但具体的中文，每条约 100-180 字。返回严格 JSON："
        '{"observations":["...", "..."]}。\n\n'
        "本次论文数据：\n" + json.dumps(papers, ensure_ascii=False)
    )
    try:
        response = _chat_completions_request(
            base_url=llm_cfg.get("base_url", "https://api.deepseek.com"),
            api_key=api_key,
            model=llm_cfg.get("model", "deepseek-flash"),
            messages=[
                {"role": "system", "content": "你是严谨的软件工程与机器学习研究分析员。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.25,
            max_tokens=1800,
            timeout=60,
        )
        result = _json_loose(response)
        observations = result.get("observations") or []
        if isinstance(observations, str):
            observations = [observations]
        observations = [str(note).strip() for note in observations if str(note).strip()]
        if observations:
            return [_shorten(note, 400) for note in observations[:5]]
    except Exception as error:
        print(f"Trend synthesis unavailable; using evidence-based fallback: {error}", file=sys.stderr)
    return _fallback_observations(groups)


def build_markdown(payload):
    groups = _group_items(payload)
    lines = ["🌱 **今天的 arXiv 新发现，看看研究问题正在往哪里走。**"]
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

    observations = payload.get("observations") or []
    if observations:
        lines.extend(["", "🔎 **今日观察｜趋势、关注点与可做的问题**"])
        for observation in observations[:5]:
            lines.append(f"• {observation}")

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
    payload["observations"] = generate_observations(payload)
    card = build_card(payload)
    send(webhook, card)
    print(f"Lark digest card sent ({len(card['elements'][0]['content'])} characters)")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Lark digest failed: {error}", file=sys.stderr)
        raise SystemExit(1)
