# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time
import random
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
import requests
from typing import Dict, Optional

# 首选 HTTPS，失败时回退到 HTTP（某些网络下 HTTPS 易读超）
ARXIV_HTTPS = "https://export.arxiv.org/api/query"
ARXIV_HTTP  = "http://export.arxiv.org/api/query"

# 可通过环境变量调整（Windows PowerShell 示例见下）
DEFAULT_TIMEOUT = float(os.getenv("ARXIV_TIMEOUT", "45"))      # 单次请求超时（秒）
MAX_ATTEMPTS    = int(os.getenv("ARXIV_MAX_ATTEMPTS", "6"))    # 尝试次数
BASE_PAUSE      = float(os.getenv("ARXIV_PAUSE", "1.5"))       # 基础退避（秒）
MAX_SLEEP       = float(os.getenv("ARXIV_MAX_SLEEP", "20"))    # 退避上限（秒）
MIN_REQUEST_INTERVAL = float(os.getenv("ARXIV_MIN_REQUEST_INTERVAL", "3"))
RATE_LIMIT_PAUSE = float(os.getenv("ARXIV_RATE_LIMIT_PAUSE", "30"))
RATE_LIMIT_MAX_SLEEP = float(os.getenv("ARXIV_RATE_LIMIT_MAX_SLEEP", "300"))

RETRYABLE_STATUS = {429, 500, 502, 503, 504}

HEADERS = {
    # 写一个正常 UA，arXiv 官方建议标注用途；邮箱可去掉
    "User-Agent": os.getenv("ARXIV_UA", "arxiv-tracker/0.1 (+https://github.com/colorfulandcjy0806/Arxiv-tracker)"),
    "Accept": "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
}

_session = requests.Session()
_last_request_at = 0.0


def _pace_request() -> None:
    """Keep consecutive arXiv API requests at least three seconds apart."""
    global _last_request_at
    now = time.monotonic()
    wait = MIN_REQUEST_INTERVAL - (now - _last_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


def _sleep_backoff(attempt: int) -> None:
    """
    指数退避 + 抖动。第 1 次失败等待 ~BASE_PAUSE，
    之后 2^n 递增，并加 0~0.5 随机抖动，封顶 MAX_SLEEP。
    """
    delay = min(BASE_PAUSE * (2 ** (attempt - 1)) + random.uniform(0, 0.5), MAX_SLEEP)
    time.sleep(delay)


def _do_get(base_url: str, params: Dict[str, str], timeout: Optional[float] = None) -> requests.Response:
    """
    带重试的 GET：对超时/连接错误/部分 5xx&429 做重试。
    """
    timeout = timeout or DEFAULT_TIMEOUT
    last_err: Optional[Exception] = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            _pace_request()
            resp = _session.get(base_url, params=params, headers=HEADERS, timeout=timeout)
            # 主动对可重试状态码抛出异常，以走重试逻辑
            if resp.status_code in RETRYABLE_STATUS:
                raise requests.exceptions.HTTPError(f"HTTP {resp.status_code}", response=resp)
            return resp  # 成功
        except (requests.exceptions.Timeout,
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError) as e:
            last_err = e
        except requests.exceptions.HTTPError as e:
            last_err = e
            # 仅对可重试状态码重试；其他直接退出循环
            st = getattr(e.response, "status_code", None)
            if st not in RETRYABLE_STATUS:
                break
            if st == 429 and attempt < MAX_ATTEMPTS:
                retry_after = _retry_after_seconds(e.response.headers.get("Retry-After"))
                backoff = min(RATE_LIMIT_PAUSE * (2 ** (attempt - 1)), RATE_LIMIT_MAX_SLEEP)
                time.sleep(max(retry_after or 0, backoff))
                continue

        # 还有机会就退避后继续
        if attempt < MAX_ATTEMPTS:
            _sleep_backoff(attempt)

    # 全部失败
    if last_err:
        raise last_err
    raise RuntimeError("Unknown arXiv request error.")


def _retry_after_seconds(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def fetch_arxiv_feed(query: str,
                     start: int = 0,
                     max_results: int = 10,
                     sort_by: str = "submittedDate",
                     sort_order: str = "descending") -> str:
    """
    拉取 arXiv Atom Feed。先 HTTPS，失败则 HTTP 回退。
    """
    params = {
        "search_query": query,
        "start": str(start),
        "max_results": str(max_results),
        "sortBy": sort_by,
        "sortOrder": sort_order,
    }

    last_err: Optional[Exception] = None
    for base in (ARXIV_HTTPS, ARXIV_HTTP):
        try:
            r = _do_get(base, params, timeout=DEFAULT_TIMEOUT)
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            if getattr(getattr(e, "response", None), "status_code", None) == 429:
                # HTTP and HTTPS endpoints share the same service quota; switching
                # protocol cannot resolve rate limiting and would add more load.
                raise
            # 换下一个 base 继续
            continue

    # 两个 base 都失败
    assert last_err is not None
    raise last_err
