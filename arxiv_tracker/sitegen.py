# -*- coding: utf-8 -*-
"""Static GitHub Pages digest: one dense, filterable table of the day's papers."""
import datetime
import html
import os
from typing import Any, Dict, List, Optional

from .insights import TRAINING_LABELS, arxiv_base_id, training_counts

STRUCTURED_FIELDS = (("problem", "核心问题"), ("challenge", "关键困难"), ("solution", "解决方案"),
                     ("results", "主要结果"), ("future", "未来方向"))


def _esc(x: Optional[str]) -> str:
    return html.escape(x or "", quote=True)


def _css(accent: str) -> str:
    return f"""
:root {{
  --bg:#f6f7f9; --card:#ffffff; --text:#0f172a; --muted:#64748b; --border:#e2e8f0; --row:#f8fafc; --acc:{accent};
}}
:root[data-theme="dark"] {{
  --bg:#0b0f17; --card:#111827; --text:#e5e7eb; --muted:#94a3b8; --border:#1f2937; --row:#0f1623; --acc:{accent};
}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);font:13.5px/1.45 ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,"PingFang SC","Microsoft YaHei",sans-serif}}
a{{color:var(--acc);text-decoration:none}} a:hover{{text-decoration:underline}}
.container{{width:96vw;max-width:1680px;margin:0 auto;padding:14px 0 24px}}
.header{{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:10px}}
h1{{font-size:20px;margin:0}}
.btn{{border:1px solid var(--border);background:var(--card);color:var(--text);padding:5px 10px;border-radius:8px;cursor:pointer;font:inherit}}
.btn:hover{{border-color:var(--acc)}}
.stats{{display:flex;gap:6px 14px;flex-wrap:wrap;align-items:center;background:var(--card);border:1px solid var(--border);border-radius:10px;padding:8px 12px}}
.stat strong{{font-size:15px;margin-right:3px}}
.stat-group{{display:flex;gap:6px;flex-wrap:wrap;align-items:center}}
.stat-label{{color:var(--muted);font-size:12px}}
.chip{{display:inline-block;border:1px solid var(--border);border-radius:999px;padding:0 8px;font-size:12px;line-height:20px;white-space:nowrap;background:var(--card);color:var(--text)}}
button.chip{{cursor:pointer;font-family:inherit}} button.chip:hover,button.chip.on{{border-color:var(--acc);color:var(--acc)}}
.chip b{{margin-left:3px}}
.t-预训练{{background:rgba(59,130,246,.12)}} .t-继续预训练{{background:rgba(14,165,233,.12)}} .t-SFT{{background:rgba(16,185,129,.14)}}
.t-RL{{background:rgba(245,158,11,.16)}} .t-RLVR{{background:rgba(249,115,22,.16)}} .t-偏好优化{{background:rgba(236,72,153,.13)}}
.t-蒸馏{{background:rgba(139,92,246,.14)}} .t-免训练{{background:rgba(100,116,139,.14)}} .t-评测基准{{background:rgba(234,179,8,.16)}}
.filters{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0}}
.filters input[type=search]{{flex:1;min-width:240px;border:1px solid var(--border);border-radius:8px;padding:7px 10px;background:var(--card);color:var(--text);font:inherit}}
.filters select{{border:1px solid var(--border);border-radius:8px;padding:6px 8px;background:var(--card);color:var(--text);font:inherit}}
.filters label{{display:flex;gap:5px;align-items:center;white-space:nowrap}}
.visible-count{{color:var(--muted);margin-left:auto}}
.table-wrap{{background:var(--card);border:1px solid var(--border);border-radius:10px;overflow:auto}}
table.papers{{width:100%;border-collapse:collapse;table-layout:fixed}}
.papers th{{position:sticky;top:0;z-index:1;background:var(--card);text-align:left;font-size:12px;color:var(--muted);font-weight:600;padding:8px;border-bottom:1px solid var(--border)}}
.papers td{{padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:top;overflow-wrap:anywhere}}
.papers tr[hidden]{{display:none!important}}
.paper-row{{cursor:pointer}} .paper-row:hover td{{background:var(--row)}}
.paper-row.open td{{background:var(--row);border-bottom-color:transparent}}
.pid a{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}}
.pid .date{{display:block;color:var(--muted);font-size:11px}}
.ptitle{{font-weight:600}} .ptitle a{{color:var(--text)}} .ptitle a:hover{{color:var(--acc)}}
.caret{{display:inline-block;width:12px;color:var(--muted);transition:transform .15s}} .open .caret{{transform:rotate(90deg)}}
.authors{{color:var(--muted);font-size:12px;font-weight:400}}
.muted{{color:var(--muted)}}
.code a{{display:inline-block;background:var(--acc);color:#fff;border-radius:6px;padding:0 7px;font-size:12px;font-weight:600;margin:0 4px 3px 0}}
.detail-row td{{background:var(--row);padding:4px 12px 14px 32px}}
.title-zh{{font-size:14px;font-weight:600;margin:2px 0 8px}}
.facts{{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px}}
.fact{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:7px 9px}}
.fact span{{display:block;font-size:11px;font-weight:700;color:var(--muted);margin-bottom:2px}}
.meta{{color:var(--muted);font-size:12px;margin-top:8px}}
.meta a{{margin-right:10px}}
details.abs{{margin-top:6px}} details.abs summary{{cursor:pointer;color:var(--acc);font-size:12px}}
details.abs div{{margin-top:4px;white-space:pre-wrap;font-size:12.5px}}
.empty td{{text-align:center;color:var(--muted);padding:24px}}
.history{{margin-top:14px}} .history summary{{cursor:pointer;color:var(--acc)}}
.history-list{{columns:6 140px;margin-top:6px}} .history-list a{{display:block;font-size:12px}}
.footer{{color:var(--muted);font-size:12px;margin-top:12px}}
@media (max-width:1100px){{.facts{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}
@media (max-width:760px){{
  .container{{width:auto;padding:10px}}
  table.papers,.papers tbody,.papers tr,.papers td{{display:block;width:100%}}
  .papers thead,.papers colgroup{{display:none}}
  .paper-row{{border-bottom:1px solid var(--border);padding:8px 0}}
  .papers td{{border:0;padding:2px 10px}}
  .papers td[data-label]::before{{content:attr(data-label) "：";color:var(--muted);font-size:12px}}
  .detail-row td{{padding:4px 10px 12px}}
  .facts{{grid-template-columns:1fr}}
}}
"""


_JS = """
<script>
(function() {
  const root = document.documentElement;
  function apply(t) {
    const dark = t === 'dark' || (t === 'auto' && window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches);
    if (dark) root.setAttribute('data-theme', 'dark'); else root.removeAttribute('data-theme');
  }
  let theme = localStorage.getItem('theme') || '__THEME__';
  if (!['light', 'dark', 'auto'].includes(theme)) theme = 'light';
  apply(theme);
  window.__toggleTheme = function() {
    theme = theme === 'light' ? 'dark' : theme === 'dark' ? 'auto' : 'light';
    localStorage.setItem('theme', theme);
    apply(theme);
    const el = document.getElementById('theme-label');
    if (el) el.textContent = theme.toUpperCase();
  };
  function setOpen(row, open) {
    const detail = row.nextElementSibling;
    row.classList.toggle('open', open);
    if (detail && detail.classList.contains('detail-row')) detail.hidden = !open;
  }
  window.__toggleRow = function(event, row) {
    if (event.target.closest('a')) return;
    setOpen(row, !row.classList.contains('open'));
  };
  window.__expandAll = function(open) {
    document.querySelectorAll('.paper-row').forEach(row => { if (!row.hidden) setOpen(row, open); });
  };
  window.__pick = function(kind, value) {
    const select = document.getElementById(kind + '-filter');
    select.value = select.value === value ? '' : value;
    window.__filter();
  };
  window.__filter = function() {
    const query = (document.getElementById('paper-search').value || '').trim().toLocaleLowerCase();
    const group = document.getElementById('group-filter').value;
    const training = document.getElementById('training-filter').value;
    const onlyCode = document.getElementById('code-only').checked;
    let visible = 0;
    document.querySelectorAll('.paper-row').forEach(row => {
      const match = (!query || row.dataset.search.includes(query)) &&
        (!group || row.dataset.groups.split('|').includes(group)) &&
        (!training || row.dataset.training.split('|').includes(training)) &&
        (!onlyCode || row.dataset.hasCode === 'true');
      row.hidden = !match;
      const detail = row.nextElementSibling;
      if (detail && detail.classList.contains('detail-row')) detail.hidden = !match || !row.classList.contains('open');
      if (match) visible += 1;
    });
    document.getElementById('visible-count').textContent = visible;
    document.querySelectorAll('button.chip[data-kind]').forEach(chip => {
      const value = document.getElementById(chip.dataset.kind + '-filter').value;
      chip.classList.toggle('on', chip.dataset.value === value);
    });
  };
  document.addEventListener('DOMContentLoaded', () => {
    const label = document.getElementById('theme-label');
    if (label) label.textContent = theme.toUpperCase();
    window.__filter();
  });
})();
</script>
"""


def _short_authors(authors: List[str]) -> str:
    if len(authors) <= 3:
        return ", ".join(authors)
    return ", ".join(authors[:3]) + " et al."


def _training_chips(labels: List[str]) -> str:
    return " ".join(f'<span class="chip t-{_esc(label)}">{_esc(label)}</span>' for label in labels)


def _code_links(urls: List[str]) -> str:
    urls = list(dict.fromkeys(urls or []))
    if not urls:
        return '<span class="muted">—</span>'
    return "".join(f'<a href="{_esc(u)}" target="_blank" rel="noreferrer">Code{"" if len(urls) == 1 else i}</a>'
                   for i, u in enumerate(urls[:3], 1))


def _cell(value: str) -> str:
    return _esc(value) if value else '<span class="muted">—</span>'


def _paper_rows(it: Dict[str, Any], ins: Dict[str, Any], columns: int) -> str:
    sid = it.get("id") or ""
    aid = arxiv_base_id(sid)
    url = it.get("html_url") or sid
    tags = ins.get("tags") or {}
    training = tags.get("training") or []
    groups = it.get("groups") or []
    authors = it.get("authors") or []
    updated = (it.get("updated") or it.get("published") or "")[:10]
    search = " ".join([aid, it.get("title") or "", ins.get("title_zh") or "", " ".join(authors),
                       it.get("summary") or "", " ".join(groups), " ".join(training),
                       *(tags.get(k) or "" for k in ("architecture", "application", "innovation")),
                       *(ins.get(k) or "" for k, _ in STRUCTURED_FIELDS)]).lower()

    row = (
        f'<tr class="paper-row" onclick="__toggleRow(event, this)" data-search="{_esc(search)}" '
        f'data-groups="{_esc("|".join(groups))}" data-training="{_esc("|".join(training))}" '
        f'data-has-code="{"true" if it.get("code_urls") else "false"}">'
        f'<td class="pid" data-label="论文编号"><a href="{_esc(url)}" target="_blank" rel="noreferrer">{_esc(aid)}</a>'
        f'<span class="date">{_esc(updated)}</span></td>'
        f'<td class="ptitle"><span class="caret">▸</span><a href="{_esc(url)}" target="_blank" rel="noreferrer">'
        f'{_esc(it.get("title") or "")}</a><div class="authors">{_esc(_short_authors(authors))}</div></td>'
        f'<td data-label="方向">{" ".join(f"<span class=chip>{_esc(g)}</span>" for g in groups) or _cell("")}</td>'
        f'<td data-label="模型架构">{_cell(tags.get("architecture"))}</td>'
        f'<td data-label="训练方法">{_training_chips(training) or _cell("")}</td>'
        f'<td data-label="应用场景">{_cell(tags.get("application"))}</td>'
        f'<td data-label="核心创新">{_cell(tags.get("innovation"))}</td>'
        f'<td class="code" data-label="Code">{_code_links(it.get("code_urls"))}</td>'
        '</tr>'
    )

    facts = "".join(f'<div class="fact"><span>{label}</span>{_esc(ins[key])}</div>'
                    for key, label in STRUCTURED_FIELDS if ins.get(key))
    links = [f'<a href="{_esc(url)}" target="_blank" rel="noreferrer">Abs</a>']
    if it.get("pdf_url"):
        links.append(f'<a href="{_esc(it["pdf_url"])}" target="_blank" rel="noreferrer">PDF</a>')
    links += [f'<a href="{_esc(u)}" target="_blank" rel="noreferrer">Project{i}</a>'
              for i, u in enumerate((it.get("project_urls") or [])[:2], 1)]
    meta_bits = [_esc(", ".join(authors))]
    venue = it.get("venue_inferred") or it.get("journal_ref") or ""
    if venue:
        meta_bits.append(_esc(venue))
    if it.get("comments"):
        meta_bits.append(_esc(it["comments"]))
    meta_bits.append(f'First {_esc((it.get("published") or "")[:10])} · Latest {_esc(updated)}')

    detail = [f'<tr class="detail-row" hidden><td colspan="{columns}">']
    if ins.get("title_zh"):
        detail.append(f'<div class="title-zh">{_esc(ins["title_zh"])}</div>')
    if facts:
        detail.append(f'<div class="facts">{facts}</div>')
    detail.append(f'<div class="meta">{"".join(links)}{" · ".join(meta_bits)}</div>')
    if it.get("summary"):
        detail.append(f'<details class="abs"><summary>Abstract</summary><div>{_esc(it["summary"])}</div></details>')
    detail.append('</td></tr>')
    return row + "".join(detail)


_COLUMNS = (("论文编号", "92px"), ("Title", "24%"), ("方向", "108px"), ("模型架构", "150px"),
            ("训练方法", "118px"), ("应用场景", "140px"), ("核心创新", ""), ("Code", "76px"))


def _table_html(items: List[Dict[str, Any]], insights: Dict[str, Dict[str, Any]]) -> str:
    cols = "".join(f'<col style="width:{w}">' if w else "<col>" for _, w in _COLUMNS)
    head = "".join(f"<th>{_esc(name)}</th>" for name, _ in _COLUMNS)
    rows = "".join(_paper_rows(it, insights.get(it.get("id") or "") or {}, len(_COLUMNS)) for it in items)
    if not items:
        rows = f'<tr class="empty"><td colspan="{len(_COLUMNS)}">今日暂无新增论文，检索会按计划继续。</td></tr>'
    return (f'<div class="table-wrap"><table class="papers"><colgroup>{cols}</colgroup>'
            f'<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>')


def _stats_html(items: List[Dict[str, Any]], insights: Dict[str, Dict[str, Any]],
                group_names: List[str], report_date: str) -> str:
    with_code = sum(1 for it in items if it.get("code_urls"))
    group_chips = "".join(
        f'<button class="chip" data-kind="group" data-value="{_esc(name)}" onclick="__pick(\'group\', this.dataset.value)">'
        f'{_esc(name)}<b>{sum(name in (it.get("groups") or []) for it in items)}</b></button>'
        for name in group_names)
    training_chips = "".join(
        f'<button class="chip t-{_esc(label)}" data-kind="training" data-value="{_esc(label)}" '
        f'onclick="__pick(\'training\', this.dataset.value)">{_esc(label)}<b>{count}</b></button>'
        for label, count in training_counts(items, insights))
    parts = [
        f'<span class="stat"><strong>{_esc(report_date)}</strong></span>',
        f'<span class="stat"><strong>{len(items)}</strong>篇</span>',
        f'<span class="stat"><strong>{with_code}</strong>篇有代码</span>',
    ]
    if group_chips:
        parts.append(f'<span class="stat-group"><span class="stat-label">方向</span>{group_chips}</span>')
    if training_chips:
        parts.append(f'<span class="stat-group"><span class="stat-label">训练方法</span>{training_chips}</span>')
    return f'<div class="stats">{"".join(parts)}</div>'


def _filters_html(items: List[Dict[str, Any]], insights: Dict[str, Dict[str, Any]], group_names: List[str]) -> str:
    group_opts = "".join(f'<option value="{_esc(n)}">{_esc(n)}</option>' for n in group_names)
    present = {label for label, _ in training_counts(items, insights)}
    training_opts = "".join(f'<option value="{_esc(l)}">{_esc(l)}</option>' for l in TRAINING_LABELS if l in present)
    return (
        '<div class="filters">'
        '<input id="paper-search" type="search" placeholder="搜索编号、标题、作者、架构、场景、摘要…" '
        'aria-label="搜索论文" oninput="__filter()">'
        f'<select id="group-filter" aria-label="方向" onchange="__filter()"><option value="">全部方向</option>{group_opts}</select>'
        f'<select id="training-filter" aria-label="训练方法" onchange="__filter()"><option value="">全部训练方法</option>{training_opts}</select>'
        '<label><input id="code-only" type="checkbox" onchange="__filter()"> 只看有代码</label>'
        '<button class="btn" onclick="__expandAll(true)">全部展开</button>'
        '<button class="btn" onclick="__expandAll(false)">全部收起</button>'
        f'<span class="visible-count">显示 <b id="visible-count">{len(items)}</b> / {len(items)}</span>'
        '</div>'
    )


def _build_page(title: str, body: str, history_html: str, theme_mode: str, accent: str) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title><style>{_css(accent)}</style>{_JS.replace("__THEME__", theme_mode)}</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{_esc(title)}</h1>
      <div><button class="btn" onclick="__toggleTheme()">Theme: <span id="theme-label">AUTO</span></button>
      <span class="muted" style="margin-left:8px">更新于 {_esc(now)}</span></div>
    </div>
    {body}
    <details class="history"><summary>History</summary><div class="history-list">{history_html}</div></details>
    <div class="footer">Generated by arxiv-tracker</div>
  </div>
</body></html>
"""


def _write(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _history_list(archive_dir: str, keep: int, prefix: str) -> str:
    if not os.path.isdir(archive_dir):
        return ""
    files = sorted((f for f in os.listdir(archive_dir) if f.endswith(".html")), reverse=True)[:keep]
    return "\n".join(f'<a href="{prefix}{_esc(f)}">{_esc(f[:-5])}</a>' for f in files)


def generate_site(items: List[Dict[str, Any]],
                  insights: Optional[Dict[str, Dict[str, Any]]],
                  site_dir: str, site_title: str = "arXiv Results",
                  keep_runs: int = 60,
                  theme: str = "light",
                  accent: Optional[str] = None,
                  group_names: Optional[List[str]] = None,
                  report_date: Optional[str] = None) -> Dict[str, str]:
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    archive_dir = os.path.join(site_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    open(os.path.join(site_dir, ".nojekyll"), "w").close()

    insights = insights or {}
    group_names = group_names or []
    report_date = report_date or datetime.datetime.now().strftime("%Y-%m-%d")
    acc = (accent or "#2563eb").strip()
    body = (_stats_html(items, insights, group_names, report_date)
            + _filters_html(items, insights, group_names)
            + _table_html(items, insights))

    arch_path = os.path.join(archive_dir, f"{stamp}.html")
    _write(arch_path, _build_page(site_title, body, _history_list(archive_dir, keep_runs, ""), theme, acc))
    index_path = os.path.join(site_dir, "index.html")
    _write(index_path, _build_page(site_title, body, _history_list(archive_dir, keep_runs, "archive/"), theme, acc))
    return {"index_path": index_path, "archive_path": arch_path, "stamp": stamp}
