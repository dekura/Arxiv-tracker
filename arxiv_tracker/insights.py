# -*- coding: utf-8 -*-
"""One structured LLM call per paper: Chinese title, taxonomy tags and a structured digest."""

import datetime
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

import requests

from .llm import _chat_completions_request, _json_loose

TRAINING_LABELS = ["预训练", "继续预训练", "SFT", "RL", "RLVR", "偏好优化", "蒸馏", "免训练", "评测基准", "其他"]

# Order matters: more specific labels must be checked before the generic ones they contain.
_TRAINING_ALIASES = [
    ("RLVR", ("rlvr", "verifiable reward", "可验证奖励")),
    ("偏好优化", ("偏好", "preference", "dpo", "kto", "orpo", "simpo", "rlhf")),
    ("继续预训练", ("继续预训练", "持续预训练", "continued pre", "continual pre")),
    ("预训练", ("预训练", "pretrain", "pre-train")),
    ("蒸馏", ("蒸馏", "distill")),
    ("SFT", ("sft", "微调", "fine-tun", "finetun", "instruction tun", "指令")),
    ("RL", ("rl", "强化", "reinforcement", "grpo", "ppo")),
    ("免训练", ("免训练", "无训练", "training-free", "training free", "prompt", "推理时", "inference-time", "test-time")),
    ("评测基准", ("评测", "基准", "benchmark", "dataset", "数据集", "evaluation")),
]

TEXT_FIELDS = ("problem", "challenge", "solution", "results", "future")
TAG_TEXT_FIELDS = ("architecture", "application", "innovation")
_FIELD_LIMITS = {
    "title_zh": 120, "architecture": 40, "application": 30, "innovation": 80,
    "problem": 140, "challenge": 140, "solution": 180, "results": 140, "future": 120,
}

SYSTEM_PROMPT = (
    "你是资深的机器学习与软件工程论文分析员。只依据给定的标题、摘要和备注，"
    "输出信息密集、便于检索的结构化要点。禁止空话、套话和营销措辞，禁止编造摘要中没有的数字或结论。"
)

USER_PROMPT = """为下面这篇 arXiv 论文输出严格 JSON（不要 Markdown、不要解释），键如下：
- title_zh：标题的中文翻译，模型名、方法名、缩写保留英文。
- architecture：模型或系统架构，英文短语不超过 6 个词，例如 "Decoder-only LLM"、"MoE LLM"、"Diffusion LM"、"Multi-agent system"、"LLM + tool harness"、"Code LLM + verifier"；无法判断填 ""。
- training：1-2 个训练方法标签组成的数组，只能从 {labels} 中选；纯评测/数据集论文用 "评测基准"，不训练模型的方法用 "免训练"。
- application：应用场景，中文不超过 12 字，例如 "仓库级 Issue 修复"、"竞赛编程"、"工具调用"。
- innovation：核心创新，一句中文不超过 40 字，写出具体机制，不要写"提出了一个新框架"这类空话。
- problem：核心问题，不超过 60 字。
- challenge：关键困难，即现有方法为什么做不好，不超过 60 字。
- solution：解决方案的关键机制，不超过 80 字。
- results：主要结果，尽量写出基准名和数字；摘要没有数字则写定性结论，不超过 60 字。
- future：局限或未来方向；摘要未提及则填 ""，不要编造，不超过 50 字。
每个字段直接写内容，不要以"本文""该论文"开头。

DATA:
{data}"""


def arxiv_base_id(paper_id: str) -> str:
    """'http://arxiv.org/abs/2604.08698v3' -> '2604.08698' (old-style ids keep their archive prefix)."""
    s = (paper_id or "").strip()
    if "/abs/" in s:
        s = s.split("/abs/", 1)[1]
    return re.sub(r"v\d+$", "", s)


def _clean(value: Any, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().strip('"').strip()
    text = re.sub(r"^(本文|该论文|这篇论文|论文)[，,：:\s]*", "", text)
    if len(text) > limit:
        text = text[: limit - 1].rstrip("，,。.;；") + "…"
    return text


def normalize_training(value: Any) -> List[str]:
    raw = value if isinstance(value, list) else re.split(r"[、,，/+|;；]", str(value or ""))
    out: List[str] = []
    for entry in raw:
        entry = str(entry or "").strip()
        if not entry:
            continue
        label = entry if entry in TRAINING_LABELS else None
        if label is None:
            low = entry.lower()
            for candidate, keys in _TRAINING_ALIASES:
                if any(re.search(r"\brl\b", low) if key == "rl" else key in low for key in keys):
                    label = candidate
                    break
        label = label or "其他"
        if label not in out:
            out.append(label)
    return out[:2]


def _first_sentence(text: str) -> str:
    t = re.sub(r"\s+", " ", (text or "").strip())
    parts = re.split(r"(?<=[.!?。！？])\s+", t)
    return parts[0] if parts else t


def fallback_insight(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title_zh": "",
        "tags": {"architecture": "", "training": [], "application": "",
                 "innovation": _clean(_first_sentence(item.get("summary") or ""), 240)},
        **{field: "" for field in TEXT_FIELDS},
        "source": "fallback",
    }


def normalize_insight(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate one LLM JSON object; return None when it lacks the core fields."""
    if not isinstance(raw, dict):
        return None
    tags_raw = raw.get("tags") if isinstance(raw.get("tags"), dict) else raw
    tags = {key: _clean(tags_raw.get(key), _FIELD_LIMITS[key]) for key in TAG_TEXT_FIELDS}
    tags["training"] = normalize_training(tags_raw.get("training"))
    out = {
        "title_zh": _clean(raw.get("title_zh"), _FIELD_LIMITS["title_zh"]),
        "tags": tags,
        **{field: _clean(raw.get(field), _FIELD_LIMITS[field]) for field in TEXT_FIELDS},
        "source": "llm",
    }
    if not (out["title_zh"] and tags["innovation"] and out["problem"] and out["solution"]):
        return None
    return out


def _load_cache(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_cache(path: str, cache: Dict[str, Any], keep_days: int) -> None:
    cutoff = (datetime.date.today() - datetime.timedelta(days=keep_days)).isoformat()
    pruned = {k: v for k, v in cache.items() if isinstance(v, dict) and (v.get("saved") or "") >= cutoff}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pruned, f, ensure_ascii=False, indent=1, sort_keys=True)


def _is_retryable(error: Exception) -> bool:
    if isinstance(error, (requests.exceptions.Timeout, requests.exceptions.ConnectionError, ValueError)):
        return True
    if isinstance(error, requests.exceptions.HTTPError):
        status = getattr(error.response, "status_code", None)
        return status == 429 or (status or 0) >= 500
    return False


def analyze_paper(item: Dict[str, Any], llm_cfg: Dict[str, Any], api_key: str,
                  attempts: int = 3, backoff: float = 2.0) -> Dict[str, Any]:
    data = {"title": item.get("title") or "", "abstract": item.get("summary") or "",
            "comments": item.get("comments") or ""}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT.format(
            labels=json.dumps(TRAINING_LABELS, ensure_ascii=False),
            data=json.dumps(data, ensure_ascii=False))},
    ]
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            text = _chat_completions_request(
                base_url=llm_cfg.get("base_url", ""), api_key=api_key,
                model=llm_cfg.get("model", ""), messages=messages,
                temperature=0.2, max_tokens=int(llm_cfg.get("max_tokens", 4096)),
                timeout=int(llm_cfg.get("timeout", 120)),
                response_format={"type": "json_object"},
            )
            insight = normalize_insight(_json_loose(text))
            if insight is None:
                raise ValueError("LLM returned incomplete insight JSON")
            return insight
        except Exception as error:
            last_error = error
            if attempt == attempts or not _is_retryable(error):
                break
            time.sleep(backoff * (2 ** (attempt - 1)))
    raise last_error or RuntimeError("unknown LLM error")


def analyze_papers(items: List[Dict[str, Any]], llm_cfg: Optional[Dict[str, Any]] = None,
                   insights_cfg: Optional[Dict[str, Any]] = None,
                   use_llm: bool = True,
                   log: Callable[[str], None] = print) -> Dict[str, Dict[str, Any]]:
    """Return {item id: insight}. Cached by base arXiv id, so new versions and reruns cost nothing."""
    llm_cfg = llm_cfg or {}
    cfg = insights_cfg or {}
    workers = max(1, int(cfg.get("workers", 8)))
    cache_path = cfg.get("cache_path", ".state/llm_cache.json")
    keep_days = int(cfg.get("cache_days", 60))
    prompt_version = str(cfg.get("prompt_version", 1))

    api_key = llm_cfg.get("api_key") or os.getenv(llm_cfg.get("api_key_env") or "OPENAI_API_KEY", "")
    if use_llm and not api_key:
        log("[Insights] 未找到 LLM API Key（llm.api_key 或环境变量 {}），使用摘要首句兜底"
            .format(llm_cfg.get("api_key_env") or "OPENAI_API_KEY"))
    use_llm = use_llm and bool(api_key)

    cache = _load_cache(cache_path) if (use_llm and cache_path) else {}
    today = datetime.date.today().isoformat()
    results: Dict[str, Dict[str, Any]] = {}
    pending: List[Dict[str, Any]] = []
    for item in items:
        sid = item.get("id") or ""
        key = f"{arxiv_base_id(sid)}@p{prompt_version}"
        hit = cache.get(key) if use_llm else None
        if hit and isinstance(hit.get("data"), dict):
            results[sid] = dict(hit["data"], source="cache")
        elif use_llm:
            pending.append(item)
        else:
            results[sid] = fallback_insight(item)

    lock = threading.Lock()

    def work(item: Dict[str, Any]) -> None:
        sid = item.get("id") or ""
        try:
            insight = analyze_paper(item, llm_cfg, api_key)
            with lock:
                cache[f"{arxiv_base_id(sid)}@p{prompt_version}"] = {
                    "saved": today, "data": {k: v for k, v in insight.items() if k != "source"}}
        except Exception as error:
            log(f"[Insights] 失败 {arxiv_base_id(sid)}: {error}")
            insight = fallback_insight(item)
        with lock:
            results[sid] = insight

    if pending:
        started = time.monotonic()
        with ThreadPoolExecutor(max_workers=min(workers, len(pending))) as pool:
            list(pool.map(work, pending))
        log(f"[Insights] LLM {len(pending)} 篇，缓存命中 {len(items) - len(pending)} 篇，"
            f"并发 {min(workers, len(pending))}，耗时 {time.monotonic() - started:.1f}s")
    elif use_llm and items:
        log(f"[Insights] 全部 {len(items)} 篇命中缓存")

    if use_llm and cache_path:
        try:
            _save_cache(cache_path, cache, keep_days)
        except Exception as error:
            log(f"[Insights] 缓存写入失败: {error}")
    return results


def training_counts(items: List[Dict[str, Any]], insights: Dict[str, Dict[str, Any]]) -> List[tuple]:
    """Training-method distribution in the fixed vocabulary order, zero counts omitted."""
    counts = {label: 0 for label in TRAINING_LABELS}
    seen = set()
    for item in items:
        sid = item.get("id") or ""
        if sid in seen:
            continue
        seen.add(sid)
        for label in ((insights.get(sid) or {}).get("tags") or {}).get("training") or []:
            counts[label] = counts.get(label, 0) + 1
    return [(label, n) for label, n in counts.items() if n]
