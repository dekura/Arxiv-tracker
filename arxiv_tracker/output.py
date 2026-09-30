# -*- coding: utf-8 -*-
import os, json, datetime
from typing import List, Dict, Any, Optional

from .insights import arxiv_base_id

STRUCTURED_FIELDS = (("problem", "核心问题"), ("challenge", "关键困难"), ("solution", "解决方案"),
                     ("results", "主要结果"), ("future", "未来方向"))


def _ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def save_json(items: List[Dict[str, Any]], out_dir: str) -> str:
    _ensure_dir(out_dir)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"arxiv_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    return path

def _cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ")

def save_markdown(items: List[Dict[str, Any]], out_dir: str,
                  insights: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    _ensure_dir(out_dir)
    insights = insights or {}
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"arxiv_{ts}.md")
    lines = ["# arXiv 论文速递", "",
             "| 论文编号 | Title | 方向 | 模型架构 | 训练方法 | 应用场景 | 核心创新 |",
             "|---|---|---|---|---|---|---|"]
    for it in items:
        tags = (insights.get(it.get("id") or "") or {}).get("tags") or {}
        aid = arxiv_base_id(it.get("id") or "")
        lines.append("| [{}]({}) | {} | {} | {} | {} | {} | {} |".format(
            aid, it.get("html_url") or "", _cell(it.get("title", "")),
            _cell(" / ".join(it.get("groups") or [])), _cell(tags.get("architecture", "")),
            _cell(" + ".join(tags.get("training") or [])), _cell(tags.get("application", "")),
            _cell(tags.get("innovation", ""))))
    lines.append("")

    for it in items:
        sid = it.get("id") or ""
        ins = insights.get(sid) or {}
        lines.append(f"## {arxiv_base_id(sid)} · {it.get('title', '')}")
        if ins.get("title_zh"):
            lines.append(f"*{ins['title_zh']}*")
            lines.append("")
        meta = [", ".join(it.get("authors", []))]
        if it.get("venue_inferred") or it.get("journal_ref"):
            meta.append(it.get("venue_inferred") or it.get("journal_ref"))
        links = [f"[Abs]({it['html_url']})"] if it.get("html_url") else []
        if it.get("pdf_url"):
            links.append(f"[PDF]({it['pdf_url']})")
        links += [f"[Code{i}]({u})" for i, u in enumerate(it.get("code_urls") or [], 1)]
        lines.append("- " + " · ".join(m for m in meta if m))
        if links:
            lines.append("- " + " · ".join(links))
        for key, label in STRUCTURED_FIELDS:
            if ins.get(key):
                lines.append(f"- **{label}**：{ins[key]}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path
