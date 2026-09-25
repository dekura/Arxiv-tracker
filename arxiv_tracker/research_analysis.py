# -*- coding: utf-8 -*-
"""Create one evidence-linked, per-direction analysis for the site and Lark."""

import json
import os
import re
from typing import Any, Dict, Iterable, List, Optional

from .llm import _chat_completions_request, _json_loose


def merge_group_items(group_results):
    """Merge per-group query results by arXiv ID while preserving group matches."""
    by_id = {}
    merged = []
    for group_name, results in group_results:
        for item in results or []:
            aid = item.get("id")
            if aid and aid in by_id:
                names = by_id[aid].setdefault("groups", [])
                if group_name not in names:
                    names.append(group_name)
                continue
            copy = dict(item)
            copy["groups"] = list(dict.fromkeys((copy.get("groups") or []) + [group_name]))
            merged.append(copy)
            if aid:
                by_id[aid] = copy
    return merged


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _valid_text(value: Any) -> bool:
    text = _clean_text(value)
    if len(text) < 20 or all(char in ".…-—_" for char in text):
        return False
    return not any(token in text for token in ("待补充", "此处填写", "观察一", "观察二", "..."))


def _fallback_group(name: str, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
    ids = [paper.get("id") for paper in papers if paper.get("id")]
    if len(papers) == 1:
        paper = papers[0]
        title = paper.get("title_zh") or paper.get("title") or "本期论文"
        return {
            "direction": {
                "text": f"本期仅命中一篇《{title}》，样本不足以判断 {name} 方向的趋势；可把这项工作作为后续比较的起点。",
                "paper_ids": ids,
            },
            "connections": {
                "text": "本期没有第二篇同方向论文可作横向对照，因此暂不能判断它与同期工作的共同方法或差异。",
                "paper_ids": ids,
            },
            "bottleneck": {
                "text": "当前材料缺少同期对照结果，尚无法确认方法收益是否稳定，也不能据此归纳共同瓶颈。",
                "paper_ids": ids,
            },
            "next_steps": [{
                "question": "在该论文采用的任务和基准上复现核心结果，并补充强基线、成本及失败案例对照。",
                "paper_ids": ids,
            }],
            "source": "fallback",
        }

    title_examples = [paper.get("title_zh") or paper.get("title") or "无标题" for paper in papers[:3]]
    title_text = "、".join(f"《{title}》" for title in title_examples)
    return {
        "direction": {
            "text": f"本期收录 {len(papers)} 篇 {name} 论文；趋势综合暂不可用，先列出 {title_text} 供核对，不据此推断领域变化。",
            "paper_ids": ids[:3],
        },
        "connections": {
            "text": "目前没有通过内容校验的跨论文综合结论；可先对照各论文的任务设定、训练信号和评测基准。",
            "paper_ids": ids[: min(3, len(ids))],
        },
        "bottleneck": {
            "text": "仅凭分组命中关系无法可靠判断共同瓶颈；需要回看论文中的失败分析、数据覆盖和成本报告。",
            "paper_ids": ids[: min(3, len(ids))],
        },
        "next_steps": [{
            "question": "把本期论文放到可比任务和基准上复现，比较其方法、数据、评测结果与推理成本。",
            "paper_ids": ids[: min(3, len(ids))],
        }],
        "source": "fallback",
    }


def _validated_group(raw: Any, name: str, papers: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(raw, dict):
        return None
    allowed = {paper.get("id") for paper in papers if paper.get("id")}

    def claim(field: str, min_refs: int = 1):
        value = raw.get(field)
        if not isinstance(value, dict) or not _valid_text(value.get("text")):
            return None
        refs = list(dict.fromkeys(ref for ref in (value.get("paper_ids") or []) if ref in allowed))
        if len(refs) < min_refs:
            return None
        return {"text": _clean_text(value["text"]), "paper_ids": refs}

    min_cross_refs = 2 if len(allowed) > 1 else 1
    direction = claim("direction")
    connections = claim("connections", min_cross_refs)
    bottleneck = claim("bottleneck", min_cross_refs)
    next_steps = []
    for value in raw.get("next_steps") or []:
        if not isinstance(value, dict) or not _valid_text(value.get("question")):
            continue
        refs = list(dict.fromkeys(ref for ref in (value.get("paper_ids") or []) if ref in allowed))
        if refs:
            next_steps.append({"question": _clean_text(value["question"]), "paper_ids": refs})
        if len(next_steps) == 2:
            break
    if not direction or not connections or not bottleneck or not next_steps:
        return None
    return {
        "direction": direction,
        "connections": connections,
        "bottleneck": bottleneck,
        "next_steps": next_steps,
        "source": "llm",
    }


def generate_group_analysis(
    group_names: Iterable[str],
    items: List[Dict[str, Any]],
    summaries_zh: Optional[Dict[str, Dict[str, str]]] = None,
    summaries_en: Optional[Dict[str, Dict[str, str]]] = None,
    translations: Optional[Dict[str, Dict[str, str]]] = None,
    llm_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Generate grounded trend analysis and validate every citation against its group."""
    summaries_zh = summaries_zh or {}
    summaries_en = summaries_en or {}
    translations = translations or {}
    grouped = {name: [] for name in group_names}
    for item in items:
        for name in item.get("groups") or []:
            copy = dict(item)
            copy["title_zh"] = (translations.get(item.get("id") or "") or {}).get("title_zh", "")
            grouped.setdefault(name, []).append(copy)

    result = {
        name: {"count": len(papers), "empty": not papers}
        for name, papers in grouped.items()
    }
    populated = {name: papers for name, papers in grouped.items() if papers}
    if not populated:
        return result

    cfg = llm_cfg or {}
    api_key = cfg.get("api_key") or os.getenv(cfg.get("api_key_env") or "OPENAI_API_KEY", "")
    raw_groups = {}
    if api_key:
        evidence = {}
        for name, papers in populated.items():
            evidence[name] = []
            for item in papers:
                sid = item.get("id") or ""
                summary = summaries_zh.get(sid) or summaries_en.get(sid) or {}
                translation = translations.get(sid) or {}
                evidence[name].append({
                    "id": sid,
                    "title": translation.get("title_zh") or item.get("title") or "",
                    "title_original": item.get("title") or "",
                    "digest": (summary.get("digest_zh") or translation.get("summary_zh")
                               or summary.get("digest_en") or item.get("summary") or "")[:1100],
                })
        prompt = (
            "根据给定 arXiv 日报，逐方向写有证据的研究分析。每个方向分别概括："
            "研究/方法变化；论文之间的联系；共同瓶颈或尚未解决的问题；1-2 个可验证的后续研究问题。"
            "多篇论文时，联系和共同瓶颈必须确实对照至少两篇；只有一篇时，明确说样本不足，禁止伪造趋势或论文间联系。"
            "每条判断都附支持它的 paper_ids，只能使用该方向给出的 ID；跨论文联系和瓶颈至少引用两篇。"
            "只依据标题和摘要，不虚构实验结果。中文具体简洁，每条约 40-120 字，避免空话。"
            "返回严格 JSON，格式为 {\"groups\": {方向名: {\"direction\": {\"text\": \"...\", \"paper_ids\": [\"...\"]}, "
            "\"connections\": {\"text\": \"...\", \"paper_ids\": [\"...\"]}, "
            "\"bottleneck\": {\"text\": \"...\", \"paper_ids\": [\"...\"]}, "
            "\"next_steps\": [{\"question\": \"...\", \"paper_ids\": [\"...\"]}]}}}."
            "不要输出 Markdown 或示例占位符。\n\n论文材料：\n"
            + json.dumps(evidence, ensure_ascii=False)
        )
        try:
            response = _chat_completions_request(
                base_url=cfg.get("base_url", "https://api.deepseek.com"),
                api_key=api_key,
                model=cfg.get("model", "deepseek-flash"),
                messages=[
                    {"role": "system", "content": "你是严谨的机器学习与软件工程研究分析员，区分论文证据与推断。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=5000,
                timeout=90,
            )
            parsed = _json_loose(response)
            raw_groups = parsed.get("groups") if isinstance(parsed, dict) else {}
            if not isinstance(raw_groups, dict):
                raw_groups = {}
        except Exception as error:
            print(f"[Analysis] LLM synthesis unavailable; using explicit fallback: {error}")

    for name, papers in populated.items():
        validated = _validated_group(raw_groups.get(name), name, papers)
        if validated is None:
            if raw_groups:
                print(f"[Analysis] Invalid or incomplete synthesis for {name}; using explicit fallback.")
            validated = _fallback_group(name, papers)
        validated["count"] = len(papers)
        validated["empty"] = False
        result[name] = validated
    return result
