# -*- coding: utf-8 -*-
import re
import requests
from html.parser import HTMLParser

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)

# 支持的“代码托管域名”
_CODE_HOSTS = r"(?:github\.com|gitlab\.com|huggingface\.co|gitee\.com)"
_URL_TAIL = r'[^\s\]\)\<\>"\'\u3002\uFF0C\uFF1B\u3001]+'  # 去掉常见结尾标点
_RE_CODE_URL = re.compile(rf"https?://{_CODE_HOSTS}/{_URL_TAIL}", re.I)

def _norm_url(u: str) -> str:
    # 去掉结尾多余的标点/括号
    return u.rstrip('.,;:)]>}’”"\'，。；：）】》')

def _extract_from_text(s: str):
    if not s:
        return []
    return [_norm_url(m.group(0)) for m in _RE_CODE_URL.finditer(s)]

def _get(url: str, timeout: int = 10):
    return requests.get(
        url,
        headers={"User-Agent": UA, "Accept": "*/*"},
        timeout=timeout,
        allow_redirects=True,
    )

def _extract_from_html(url: str, timeout: int):
    try:
        r = _get(url, timeout=timeout)
        r.raise_for_status()
        parser = _PaperLinkParser()
        parser.feed(r.text)
        return _dedup(parser.code_urls)
    except Exception:
        return []


class _PaperLinkParser(HTMLParser):
    """Extract code links only from arXiv paper metadata and abstract content.

    The full abstract page contains global help/navigation links (including
    generic Hugging Face URLs). Treating every page link as paper code caused
    those links to be displayed as Code1/Code2 on the generated site.
    """

    _VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._stack = []
        self._scope_depth = 0
        self.code_urls = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").lower().split())
        in_paper_text = "abstract" in classes or "comments" in classes
        if in_paper_text:
            self._scope_depth += 1

        if self._scope_depth and tag.lower() == "a":
            href = attrs.get("href") or ""
            self.code_urls.extend(_extract_from_text(href))

        if tag.lower() not in self._VOID_TAGS:
            self._stack.append((tag.lower(), in_paper_text))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        for index in range(len(self._stack) - 1, -1, -1):
            stacked_tag, in_paper_text = self._stack[index]
            if in_paper_text:
                self._scope_depth -= 1
            del self._stack[index:]
            if stacked_tag == tag:
                break

def _extract_from_pdf_head(pdf_url: str, timeout: int, head_bytes: int = 256 * 1024):
    """
    只取 PDF 前 head_bytes（默认 256KB），用 bytes 正则匹配 URL。
    """
    try:
        headers = {
            "User-Agent": UA,
            "Range": f"bytes=0-{head_bytes-1}",
            "Accept": "application/pdf,*/*",
        }
        r = requests.get(pdf_url, headers=headers, timeout=timeout, allow_redirects=True)
        # 某些服务器对 Range 不支持会返回 200；也可接受
        if r.status_code not in (200, 206):
            return []
        data = r.content or b""
        # 字节级匹配，避免解码错误
        rx = re.compile(rb"https?://(?:" + _CODE_HOSTS.encode() + rb")/" + _URL_TAIL.encode(), re.I)
        found = [bytes(m.group(0)).decode("latin-1", errors="ignore") for m in rx.finditer(data)]
        return [_norm_url(u) for u in found]
    except Exception:
        return []

def _dedup(urls):
    seen, out = set(), []
    for u in urls:
        k = u.strip()
        if not k:
            continue
        lk = k.lower()
        if lk not in seen:
            seen.add(lk)
            out.append(k)
    return out

def augment_item_links(
    item: dict,
    *,
    html: bool = True,
    pdf_if_missing: bool = True,   # << 关键开关：仅在“没有 code 链接时”才去扫 PDF
    pdf_first_page: bool = False,  # 始终扫 PDF（不建议默认开，性能差）
    timeout: int = 10,
) -> int:
    """
    返回本次新增的链接条数
    """
    code_urls = list(item.get("code_urls") or [])
    before = len(code_urls)

    # 1) 从已有文本（summary / comments / title）里先挖
    code_urls += _extract_from_text(item.get("summary") or "")
    code_urls += _extract_from_text(item.get("comments") or "")
    code_urls += _extract_from_text(item.get("title") or "")

    # 2) 再尝试 HTML 页
    if html and item.get("html_url"):
        code_urls += _extract_from_html(item["html_url"], timeout=timeout)

    code_urls = _dedup(code_urls)

    # 3) 仅当目前还没有 code 链接时，再去扫 PDF 头
    need_pdf = (pdf_if_missing and len(code_urls) == 0) or pdf_first_page
    if need_pdf and item.get("pdf_url"):
        code_urls += _extract_from_pdf_head(item["pdf_url"], timeout=timeout)
        code_urls = _dedup(code_urls)

    item["code_urls"] = code_urls
    return len(code_urls) - before
