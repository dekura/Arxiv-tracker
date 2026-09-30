# -*- coding: utf-8 -*-
"""Compact, table-based HTML email (inline styles only; mail clients ignore most CSS)."""
import html
from typing import Any, Dict, List, Optional

from .insights import arxiv_base_id, training_counts

_FONT = "font-family:-apple-system,Segoe UI,Roboto,'PingFang SC','Microsoft YaHei',Arial,sans-serif"
_TH = "text-align:left;padding:6px 8px;background:#f1f5f9;color:#475569;font-size:12px;border-bottom:1px solid #e2e8f0"
_TD = "padding:6px 8px;border-top:1px solid #e2e8f0;vertical-align:top;font-size:13px;color:#0f172a"
_SUB = "padding:0 8px 8px 8px;vertical-align:top;font-size:12px;color:#475569;line-height:1.5"
_MUTED = "color:#94a3b8"
_LINK = "color:#2563eb;text-decoration:none"
_HEADERS = ("编号", "Title", "架构", "训练", "场景", "核心创新", "Code")
_DETAIL_FIELDS = (("problem", "问题"), ("challenge", "困难"), ("solution", "方案"), ("results", "结果"))


def _esc(x: Optional[str]) -> str:
    return html.escape(x or "", quote=True)


def _or_dash(value: str) -> str:
    return _esc(value) if value else f'<span style="{_MUTED}">—</span>'


def _code(urls: List[str]) -> str:
    urls = list(dict.fromkeys(urls or []))[:2]
    if not urls:
        return f'<span style="{_MUTED}">—</span>'
    return " ".join(f'<a style="{_LINK};font-weight:600" href="{_esc(u)}">Code{"" if len(urls) == 1 else i}</a>'
                    for i, u in enumerate(urls, 1))


def _rows(it: Dict[str, Any], ins: Dict[str, Any], detail: str, first_group: Optional[str]) -> str:
    sid = it.get("id") or ""
    url = it.get("html_url") or sid
    tags = ins.get("tags") or {}
    id_cell = f'<td style="{_TD};white-space:nowrap;font-family:Menlo,Consolas,monospace;font-size:12px">' \
              f'<a style="{_LINK}" href="{_esc(url)}">{_esc(arxiv_base_id(sid))}</a></td>'
    title_cell = f'<td style="{_TD};font-weight:600"><a style="color:#0f172a;text-decoration:none" href="{_esc(url)}">' \
                 f'{_esc(it.get("title") or "")}</a></td>'
    if first_group:
        return (f'<tr>{id_cell}{title_cell}<td colspan="5" style="{_TD};{_MUTED}">同时属于「{_esc(first_group)}」，'
                f'详情见该方向</td></tr>')
    row = (
        f'<tr>{id_cell}{title_cell}'
        f'<td style="{_TD}">{_or_dash(tags.get("architecture"))}</td>'
        f'<td style="{_TD};white-space:nowrap">{_or_dash(" + ".join(tags.get("training") or []))}</td>'
        f'<td style="{_TD}">{_or_dash(tags.get("application"))}</td>'
        f'<td style="{_TD}">{_or_dash(tags.get("innovation"))}</td>'
        f'<td style="{_TD};white-space:nowrap">{_code(it.get("code_urls"))}</td></tr>'
    )
    facts = [f'<b style="color:#334155">{label}</b> {_esc(ins[key])}' for key, label in _DETAIL_FIELDS if ins.get(key)]
    if detail == "full" and facts:
        row += f'<tr><td></td><td colspan="6" style="{_SUB}">{" ｜ ".join(facts)}</td></tr>'
    return row


def _table(rows: List[str]) -> str:
    head = "".join(f'<th style="{_TH}">{h}</th>' for h in _HEADERS)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
            f'style="border-collapse:collapse;border:1px solid #e2e8f0;margin:6px 0 16px">'
            f'<tr>{head}</tr>{"".join(rows)}</table>')


def render_email_html(
    items: List[Dict[str, Any]],
    insights: Optional[Dict[str, Dict[str, Any]]] = None,
    detail: str = "full",
    max_items: int = 50,
    title: str = "arXiv Daily Digest",
    groups: Optional[List[str]] = None,
    page_url: Optional[str] = None,
    report_date: Optional[str] = None,
) -> str:
    insights = insights or {}
    summary_bits = [b for b in (report_date, f"{len(items)} 篇",
                                f"{sum(1 for it in items if it.get('code_urls'))} 篇有代码") if b]
    dist = " · ".join(f"{label} {n}" for label, n in training_counts(items, insights))
    if dist:
        summary_bits.append(dist)
    if page_url:
        summary_bits.append(f'<a style="{_LINK}" href="{_esc(page_url)}">网页版（可筛选）</a>')
    out = [f'<div style="{_FONT};color:#0f172a;max-width:1400px">',
           f'<h2 style="margin:6px 0 4px;font-size:18px">{_esc(title)}</h2>',
           f'<div style="font-size:12px;color:#64748b;margin-bottom:10px">{" · ".join(summary_bits)}</div>']

    if not items:
        out.append("<p>今日暂无新增命中。</p></div>")
        return "\n".join(out)

    shown_in: Dict[str, str] = {}
    sections = [(name, [it for it in items if name in (it.get("groups") or [])]) for name in groups] \
        if groups else [(None, items)]
    for name, seq in sections:
        if name is not None:
            out.append(f'<h3 style="margin:14px 0 2px;font-size:15px;color:#2563eb">{_esc(name)} · {len(seq)} 篇</h3>')
        if not seq:
            out.append(f'<p style="font-size:13px;{_MUTED}">今日暂无新增。</p>')
            continue
        rows = []
        for it in seq[:max_items]:
            sid = it.get("id") or ""
            rows.append(_rows(it, insights.get(sid) or {}, detail, shown_in.get(sid)))
            if name is not None:
                shown_in.setdefault(sid, name)
        out.append(_table(rows))
    out.append("</div>")
    return "\n".join(out)
