# -*- coding: utf-8 -*-
import os, datetime, html
from typing import Dict, List, Any, Optional

import re
try:
    from markdown import markdown as _md
except Exception:
    _md = None

def _esc(x):  # 保留你的实现
    import html
    return html.escape(x or "", quote=True)

def _md2html(md: str) -> str:
    if not md: return ""
    if _md:
        return _md(md, extensions=["extra", "sane_lists", "tables"])
    return "<pre class='mono'>" + _esc(md) + "</pre>"

# --- 语言/内容判断 & 文本处理 ---
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
def _has_cjk(s: str) -> bool:
    return bool(_CJK_RE.search(s or ""))

def _first_sentence(text: str) -> str:
    if not text: return ""
    t = re.sub(r"\s+", " ", text.strip())
    parts = re.split(r"(?<=[。！？.!?])\s+", t)
    return parts[0] if parts else t

def _strip_format(md: str) -> str:
    """
    去掉冗余行：**Method Card...**, **Discussion...**, **Links**...
    """
    if not md: return ""
    out = []
    for line in md.splitlines():
        L = line.strip().lower()
        if L.startswith("**method card") or L.startswith("**discussion"):
            continue
        if L.startswith("- **links**"):
            continue
        out.append(line)
    return "\n".join(out)

def _localize_md_to_zh(md: str) -> str:
    """
    仅把标签本地化，内容不硬翻译（避免引入错误）。英文值保留。
    """
    repl = {
        "**Task / Problem**:": "**任务 / 问题**：",
        "**Core Idea**:": "**核心思路**：",
        "**Data / Benchmarks**:": "**数据 / 基准**：",
        "**Venue**:": "**会议 / 期刊**：",
    }
    s = md
    for k, v in repl.items():
        s = s.replace(k, v)
    return s
    
try:
    # 用于把 full_md 渲染成真正的 HTML 列表/加粗等
    from markdown import markdown as _md
except Exception:
    _md = None

def _esc(x: Optional[str]) -> str:
    return html.escape(x or "", quote=True)

def _md2html(md: str) -> str:
    if not md: return ""
    if _md:
        return _md(md, extensions=["extra", "sane_lists", "tables"])
    # 兜底（没有 markdown 包时，退化为等宽块）
    return "<pre class='mono'>" + _esc(md) + "</pre>"

def _strip_redundant_links(md: str) -> str:
    out = []
    for line in (md or "").splitlines():
        if line.strip().lower().startswith("- **links**"):
            continue
        out.append(line)
    return "\n".join(out)

def _css(accent: str = "#2563eb") -> str:
    return f"""
:root {{
  --bg:#f8fafc; --card:#ffffff; --text:#0f172a; --muted:#667085; --border:#e5e7eb; --acc:{accent};
}}
:root[data-theme="dark"] {{
  --bg:#0b0f17; --card:#111827; --text:#e5e7eb; --muted:#9ca3af; --border:#1f2937; --acc:{accent};
}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);
  font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial;line-height:1.6;}}
.container{{max-width:900px;margin:0 auto;padding:18px;}}
.header{{display:flex;gap:10px;justify-content:space-between;align-items:center;margin:8px 0 16px;flex-wrap:wrap}}
h1{{font-size:22px;margin:0}}
.badge{{font-size:12px;color:#111827;background:var(--acc);padding:2px 8px;border-radius:999px}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:16px 18px;margin:14px 0;box-shadow:0 1px 2px rgba(0,0,0,.04)}}
.title{{font-weight:700;margin:0 0 6px 0;font-size:18px}}
.meta-line{{color:var(--muted);font-size:13px;margin:2px 0}}
.links a{{color:var(--acc);text-decoration:none;margin-right:12px}}
.detail{{margin-top:10px;background:rgba(2,6,23,.03);border:1px solid var(--border);border-radius:10px;padding:8px 10px}}
summary{{cursor:pointer;color:var(--acc)}}
.mono{{white-space:pre-wrap;background:rgba(2,6,23,.03);border:1px solid var(--border);padding:10px;border-radius:10px}}
.row{{display:grid;grid-template-columns:1fr;gap:12px}}
@media (min-width: 860px) {{
  .row-2{{grid-template-columns:1fr 1fr}}
}}
.footer{{color:var(--muted);font-size:13px;margin:20px 0 10px}}
.hr{{height:1px;background:var(--border);margin:14px 0}}
.history-list a{{display:block;color:var(--acc);text-decoration:none;margin:4px 0}}
.controls{{display:flex;gap:8px;align-items:center}}
.btn{{border:1px solid var(--border);background:var(--card);padding:6px 10px;border-radius:10px;cursor:pointer;color:var(--text)}}
.btn:hover{{border-color:var(--acc)}}
.tabs{{display:flex;gap:6px;flex-wrap:wrap;margin:16px 0;border-bottom:2px solid var(--border)}}
.tab{{padding:8px 14px;cursor:pointer;border:none;background:transparent;color:var(--muted);border-bottom:2px solid transparent;margin-bottom:-2px}}
.tab.active{{color:var(--acc);border-bottom-color:var(--acc);font-weight:600}}
.group-section{{display:none}}
.group-section.active{{display:block}}
.group-header{{font-size:18px;font-weight:600;margin:8px 0 12px 0;color:var(--acc)}}
.overview{{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:18px;margin:16px 0 22px}}
.overview h2{{font-size:19px;margin:0 0 10px}}
.metrics,.group-counts,.paper-groups{{display:flex;gap:8px;flex-wrap:wrap}}
.metric,.group-count,.paper-group{{border:1px solid var(--border);border-radius:999px;padding:4px 10px;font-size:13px;color:var(--muted)}}
.metric strong{{color:var(--text);font-size:15px;margin-right:4px}}
.group-count{{color:var(--text)}}
.analysis-grid{{display:grid;grid-template-columns:1fr;gap:12px;margin-top:16px}}
.analysis-card{{border:1px solid var(--border);border-radius:12px;padding:14px;background:rgba(2,6,23,.02)}}
.analysis-card h3{{font-size:16px;margin:0 0 8px;color:var(--acc)}}
.insight{{margin:9px 0}}
.insight-label{{font-size:12px;font-weight:700;color:var(--muted);display:block}}
.insight p{{margin:2px 0}}
.evidence{{font-size:12px;margin-top:4px}}
.evidence a{{color:var(--acc);margin-right:8px}}
.search-controls{{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:18px 0 4px}}
.search-controls input{{flex:1;min-width:220px;border:1px solid var(--border);border-radius:10px;padding:10px 12px;background:var(--card);color:var(--text);font:inherit}}
.code-filter{{display:flex;gap:7px;align-items:center;color:var(--text);font-size:14px;white-space:nowrap}}
.tabs{{overflow-x:auto;flex-wrap:nowrap;scrollbar-width:thin;}}
.tab{{white-space:nowrap;flex:0 0 auto}}
.tab-count{{font-size:12px;opacity:.8;margin-left:4px}}
.paper-title{{color:var(--text);text-decoration:none}}
.paper-title:hover{{color:var(--acc);text-decoration:underline}}
.contribution{{margin:12px 0 4px;font-size:15px}}
.code-link{{display:inline-block!important;background:var(--acc);color:#fff!important;padding:4px 10px;border-radius:8px;font-weight:700;margin-right:8px!important}}
.paper-groups{{margin-top:9px}}
.paper-group{{font-size:11px;padding:1px 8px}}
.group-empty{{color:var(--muted);padding:12px 2px}}
.paper-card[hidden]{{display:none}}
@media (min-width: 720px){{.analysis-grid{{grid-template-columns:1fr 1fr}}}}
@media (max-width: 600px){{.container{{padding:12px}}.header{{align-items:flex-start}}.controls{{width:100%;flex-wrap:wrap}}.controls .btn{{font-size:12px;padding:6px 8px}}.card{{padding:14px}}.overview{{padding:14px}}.search-controls input{{min-width:100%}}}}
"""

def _join_links(it: Dict[str, Any]) -> str:
    parts = []
    if it.get("pdf_url"):  parts.append(f'<a href="{_esc(it["pdf_url"])}">PDF</a>')
    if it.get("code_urls"):
        for i,u in enumerate(it["code_urls"][:3]): parts.append(f'<a class="code-link" href="{_esc(u)}">Code{i+1}</a>')
    if it.get("project_urls"):
        for i,u in enumerate(it["project_urls"][:2]): parts.append(f'<a href="{_esc(u)}">Project{i+1}</a>')
    return " · ".join(parts)

def _card(it: Dict[str, Any],
          trans_zh: Optional[Dict[str,str]],
          sum_zh: Optional[Dict[str,str]],
          sum_en: Optional[Dict[str,str]],
          group_names: Optional[List[str]] = None) -> str:
    t = it.get("title") or ""
    au = ", ".join(it.get("authors") or [])
    venue = it.get("venue_inferred") or (it.get("journal_ref") or "")
    pub = it.get("published") or "—"
    upd = it.get("updated") or "—"
    comm = it.get("comments") or ""
    absu = it.get("summary") or ""

    zh_title = (trans_zh or {}).get("title_zh")
    zh_abs   = (trans_zh or {}).get("summary_zh")

    # 新的双语总结（来自 summarizer）
    digest_en = (sum_en or {}).get("digest_en") or (sum_zh or {}).get("digest_en") or ""
    digest_zh = (sum_zh or {}).get("digest_zh") or (sum_en or {}).get("digest_zh") or ""

    display_title = zh_title or t
    title_html = _esc(display_title)
    if it.get("html_url"):
        title_html = f'<a class="paper-title" href="{_esc(it["html_url"])}" target="_blank" rel="noreferrer">{title_html}</a>'

    contribution = digest_zh or zh_abs or digest_en or _first_sentence(absu)
    contribution = re.sub(r"\s+", " ", contribution).strip()
    if len(contribution) > 320:
        contribution = contribution[:319].rstrip(" ，。；;,") + "…"
    searchable = " ".join([t, zh_title or "", au, absu, zh_abs or "", digest_zh, digest_en, comm])
    groups = it.get("groups") or group_names or []
    group_chips = "".join(f'<span class="paper-group">{_esc(name)}</span>' for name in groups)
    parts = [
        f'<article class="card paper-card" data-search="{_esc(searchable)}" data-has-code="{"true" if it.get("code_urls") else "false"}">',
        f'<div class="title">{title_html}</div>',
    ]

    if contribution:
        parts.append(f'<p class="contribution">{_esc(contribution)}</p>')

    # 元信息分行
    parts.append(f'<div class="meta-line">Authors: {_esc(au)}</div>')
    if venue:
        parts.append(f'<div class="meta-line">Venue: {_esc(venue)}</div>')
    parts.append(f'<div class="meta-line">First: {_esc(pub)} · Latest: {_esc(upd)}</div>')
    if comm:
        parts.append(f'<div class="meta-line">Comments: {_esc(comm)}</div>')

    # 链接
    links = _join_links(it)
    if links: parts.append(f'<div class="links" style="margin-top:8px">{links}</div>')
    if group_chips: parts.append(f'<div class="paper-groups">{group_chips}</div>')

    # 摘要（英文原文，可折叠）
    if absu:
        parts.append('<details class="detail"><summary>Abstract</summary>')
        parts.append(f'<div class="mono">{_esc(absu)}</div></details>')

    # Longer bilingual summaries remain available without dominating the first screen.
    if digest_en or digest_zh or zh_abs:
        parts.append('<details class="detail"><summary>详细解读 / 中英总结</summary>')
        if digest_en:
            parts.append(f'<div class="mono">{_esc(digest_en)}</div>')
        if digest_zh:
            parts.append(f'<div class="mono" style="margin-top:8px">{_esc(digest_zh)}</div>')
        if zh_abs:
            parts.append(f'<div class="mono" style="margin-top:8px"><b>中文摘要：</b>{_esc(zh_abs)}</div>')
        parts.append('</details>')

    parts.append('</article>')
    return "\n".join(parts)


def _write(path: str, text: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f: f.write(text)

def _build_page(title: str, sub: str, overview_html: str, cards_html: str, history_html: str,
                theme_mode: str, accent: str) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    js = f"""
<script>
(function() {{
  const root = document.documentElement;
  function apply(t) {{
    if (t==='dark') root.setAttribute('data-theme','dark');
    else if (t==='light') root.removeAttribute('data-theme');
    else {{
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)
        root.setAttribute('data-theme','dark');
      else root.removeAttribute('data-theme');
    }}
  }}
  let t = localStorage.getItem('theme') || '{theme_mode}';
  if (!['light','dark','auto'].includes(t)) t='light';
  apply(t);
  window.__toggleTheme = function() {{
    let cur = localStorage.getItem('theme') || '{theme_mode}';
    if (cur==='light') cur='dark';
    else if (cur==='dark') cur='auto';
    else cur='light';
    localStorage.setItem('theme', cur);
    apply(cur);
    const el=document.getElementById('theme-label');
    if(el) el.textContent = cur.toUpperCase();
  }}
  window.__expandAll = function(open) {{
    document.querySelectorAll('details').forEach(d => d.open = !!open);
  }}
  window.__switchGroup = function(i) {{
    document.querySelectorAll('.tab').forEach((el, idx) => el.classList.toggle('active', idx === i));
    document.querySelectorAll('.group-section').forEach((el, idx) => el.classList.toggle('active', idx === i));
    window.__activeGroup = i;
  }}
  window.__filterDigest = function() {{
    const query = (document.getElementById('paper-search')?.value || '').trim().toLocaleLowerCase();
    const onlyCode = !!document.getElementById('code-only')?.checked;
    let counts = [];
    document.querySelectorAll('.group-section').forEach((section, idx) => {{
      let visible = 0;
      section.querySelectorAll('.paper-card').forEach(card => {{
        const match = (!query || (card.dataset.search || '').toLocaleLowerCase().includes(query)) &&
          (!onlyCode || card.dataset.hasCode === 'true');
        card.hidden = !match;
        if (match) visible += 1;
      }});
      counts.push(visible);
      const empty = section.querySelector('.group-empty');
      if (empty) {{
        empty.hidden = visible > 0;
        empty.textContent = (query || onlyCode) ? '当前筛选下没有匹配论文。' : '今日暂无新增论文。';
      }}
      const count = document.querySelector('.tab[data-index="' + idx + '"] .tab-count');
      if (count) count.textContent = visible;
    }});
    const active = window.__activeGroup || 0;
    if ((query || onlyCode) && !counts[active] && counts.some(count => count > 0)) {{
      window.__switchGroup(counts.findIndex(count => count > 0));
    }}
  }}
  const activeTab = document.querySelector('.tab.active');
  window.__activeGroup = activeTab ? Number(activeTab.dataset.index) : 0;
  document.addEventListener('DOMContentLoaded', window.__filterDigest);
}})();
</script>
"""
    controls = """
<div class="controls">
  <button class="btn" onclick="__toggleTheme()">Theme: <span id="theme-label" style="margin-left:6px">AUTO</span></button>
  <button class="btn" onclick="__expandAll(true)">Expand All</button>
  <button class="btn" onclick="__expandAll(false)">Collapse All</button>
</div>
"""
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)}</title><style>{_css(accent)}</style>{js}</head>
<body>
  <div class="container">
    <div class="header">
      <h1>{_esc(title)}</h1>
      <div style="display:flex;gap:10px;align-items:center">
        {controls}
        <span class="badge">{_esc(now)}</span>
      </div>
    </div>
    <div class="hr"></div>
    <div>{_esc(sub)}</div>
    {overview_html}
    {cards_html}
    <details style="margin-top:16px" class="detail"><summary>History</summary>
      <div class="history-list">{history_html}</div>
    </details>
    <div class="footer">Generated by arxiv-tracker</div>
  </div>
</body></html>
"""

def _history_list(archive_dir: str, keep: int) -> List[str]:
    if not os.path.isdir(archive_dir):
        return []
    files = [f for f in os.listdir(archive_dir) if f.endswith(".html")]
    files.sort(reverse=True)
    files = files[:keep]
    links = []
    for f in files:
        date = f.replace(".html","")
        links.append(f'<a href="archive/{_esc(f)}">{_esc(date)}</a>')
    return links

def _cards_html(items: List[Dict[str,Any]],
                summaries_zh: Dict[str,Dict[str,str]],
                summaries_en: Dict[str,Dict[str,str]],
                translations: Dict[str,Dict[str,str]],
                group_names: Optional[List[str]] = None) -> str:
    cards = []
    for it in items:
        sid = it.get("id") or ""
        cards.append(_card(it, translations.get(sid), summaries_zh.get(sid), summaries_en.get(sid), group_names))
    return "\n".join(cards)


def _body_html(items: List[Dict[str,Any]],
               summaries_zh: Dict[str,Dict[str,str]],
               summaries_en: Dict[str,Dict[str,str]],
               translations: Dict[str,Dict[str,str]],
               group_names: Optional[List[str]] = None) -> str:
    search_controls = '''<div class="search-controls">
  <input id="paper-search" type="search" placeholder="搜索论文标题和摘要" aria-label="搜索论文标题和摘要" oninput="__filterDigest()">
  <label class="code-filter"><input id="code-only" type="checkbox" onchange="__filterDigest()"> 只看有代码</label>
</div>'''
    if not group_names:
        cards = _cards_html(items, summaries_zh, summaries_en, translations)
        empty = '<div class="group-empty">今日暂无新增论文。</div>' if not items else '<div class="group-empty" hidden></div>'
        return search_controls + f'<div class="group-section active"><div class="row">{cards}</div>{empty}</div>'

    tabs = []
    sections = []
    for i, name in enumerate(group_names):
        group_items = [it for it in items if name in (it.get("groups") or [])]
        active_index = next((index for index, group in enumerate(group_names)
                             if any(group in (item.get("groups") or []) for item in items)), 0)
        active = " active" if i == active_index else ""
        tabs.append(
            f'<button class="tab{active}" data-index="{i}" onclick="__switchGroup({i})">{_esc(name)}'
            f'<span class="tab-count">{len(group_items)}</span></button>'
        )
        cards = _cards_html(group_items, summaries_zh, summaries_en, translations, group_names)
        empty = '<div class="group-empty">今日暂无新增论文。</div>' if not group_items else '<div class="group-empty" hidden></div>'
        sections.append(
            f'<div class="group-section{active}" data-group="{_esc(name)}">'
            f'<div class="group-header">{_esc(name)} · {len(group_items)} 篇</div>'
            f'{empty}<div class="row">{cards}</div></div>'
        )
    return search_controls + f'<div class="tabs" aria-label="研究方向">{"".join(tabs)}</div>' + "".join(sections)


def _evidence_html(claim: Dict[str, Any], item_by_id: Dict[str, Dict[str, Any]],
                   translations: Dict[str, Dict[str, str]]) -> str:
    links = []
    for paper_id in claim.get("paper_ids") or []:
        item = item_by_id.get(paper_id)
        if not item:
            continue
        title = (translations.get(paper_id) or {}).get("title_zh") or item.get("title") or paper_id
        url = item.get("html_url") or paper_id
        links.append(f'<a href="{_esc(url)}" target="_blank" rel="noreferrer">{_esc(title)}</a>')
    if not links:
        return ""
    return '<div class="evidence">依据：' + " · ".join(links) + "</div>"


def _claim_html(label: str, claim: Dict[str, Any], item_by_id, translations,
                text_key: str = "text") -> str:
    if not claim:
        return ""
    return (f'<div class="insight"><span class="insight-label">{_esc(label)}</span>'
            f'<p>{_esc(claim.get(text_key) or "")}</p>'
            f'{_evidence_html(claim, item_by_id, translations)}</div>')


def _overview_html(items: List[Dict[str, Any]], group_names: Optional[List[str]],
                   group_analysis: Dict[str, Dict[str, Any]], translations: Dict[str, Dict[str, str]],
                   report_date: str) -> str:
    group_names = group_names or list(group_analysis)
    unique_count = len({item.get("id") or item.get("title") for item in items})
    counts = {name: sum(name in (item.get("groups") or []) for item in items) for name in group_names}
    count_chips = "".join(
        f'<span class="group-count">{_esc(name)} <strong>{counts[name]}</strong></span>'
        for name in group_names
    )
    item_index = {item.get("id"): item for item in items if item.get("id")}
    trend_cards = []
    for name in group_names:
        data = group_analysis.get(name) or {}
        if not counts[name]:
            trend_cards.append(
                f'<article class="analysis-card"><h3>{_esc(name)}</h3>'
                '<p class="meta-line">本方向今日无命中，暂不生成趋势判断。</p></article>'
            )
            continue
        body = [
            _claim_html("研究变化", data.get("direction") or {}, item_index, translations),
            _claim_html("论文联系", data.get("connections") or {}, item_index, translations),
            _claim_html("共同瓶颈", data.get("bottleneck") or {}, item_index, translations),
        ]
        for idx, question in enumerate(data.get("next_steps") or [], 1):
            body.append(_claim_html(f"可验证的问题 {idx}", question, item_index, translations,
                                    text_key="question"))
        trend_cards.append(f'<article class="analysis-card"><h3>{_esc(name)} · {counts[name]} 篇</h3>{"".join(body)}</article>')
    empty_note = '<p class="meta-line">今天没有新增命中；检索仍会按计划继续。当前无论文样本，不生成趋势判断。</p>' if not items else ""
    return (
        '<section class="overview" aria-labelledby="today-heading">'
        '<h2 id="today-heading">今日研究观察</h2>'
        f'<div class="metrics"><span class="metric">日期 <strong>{_esc(report_date)}</strong></span>'
        f'<span class="metric">去重论文 <strong>{unique_count}</strong></span></div>'
        f'<div class="group-counts" aria-label="各方向论文数">{count_chips}</div>'
        f'{empty_note}<div class="analysis-grid">{"".join(trend_cards)}</div>'
        '</section>'
    )


def generate_site(items: List[Dict[str,Any]],
                  summaries_zh: Dict[str,Dict[str,str]],
                  summaries_en: Dict[str,Dict[str,str]],
                  translations: Dict[str,Dict[str,str]],
                  site_dir: str, site_title: str = "arXiv Results",
                  keep_runs: int = 60,
                  theme: str = "light",
                  accent: Optional[str] = None,
                  group_names: Optional[List[str]] = None,
                  group_analysis: Optional[Dict[str, Dict[str, Any]]] = None,
                  report_date: Optional[str] = None) -> Dict[str,str]:
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    archive_dir = os.path.join(site_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)
    open(os.path.join(site_dir, ".nojekyll"), "w").close()

    group_analysis = group_analysis or {}
    cards_html = _body_html(items, summaries_zh, summaries_en, translations, group_names)
    hist_html = "\n".join(_history_list(archive_dir, keep_runs))
    report_date = report_date or datetime.datetime.now().strftime("%Y-%m-%d")
    overview_html = _overview_html(items, group_names, group_analysis, translations, report_date)

    acc = (accent or "#2563eb").strip()

    arch_html = _build_page(site_title, f"Snapshot: {stamp}", overview_html, cards_html, history_html=hist_html,
                            theme_mode=theme, accent=acc)
    arch_path = os.path.join(archive_dir, f"{stamp}.html")
    _write(arch_path, arch_html)

    index_html = _build_page(site_title, "Latest digest", overview_html, cards_html, history_html=hist_html,
                             theme_mode=theme, accent=acc)
    index_path = os.path.join(site_dir, "index.html")
    _write(index_path, index_html)

    return {"index_path": index_path, "archive_path": arch_path, "stamp": stamp}
