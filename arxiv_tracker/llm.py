# -*- coding: utf-8 -*-
import json, re, requests
from typing import Dict, Any, List, Optional

# ========== 通用小工具 ==========

def _json_loose(s: str) -> Dict[str, Any]:
    """
    宽松 JSON 解析：尽力从文本中抽出首个 {...} 为 JSON。
    """
    m = re.search(r"\{[\s\S]*\}", s or "")
    if not m:
        return {}
    raw = m.group(0)
    try:
        return json.loads(raw)
    except Exception:
        # 去掉尾随逗号等常见小问题再试一次
        t = re.sub(r",\s*([}\]])", r"\1", raw)
        try:
            return json.loads(t)
        except Exception:
            return {}

def _normalize_chat_endpoint(base_url: str) -> str:
    """
    允许三种写法：
      1) https://api.xxx.com
      2) https://api.xxx.com/v1
      3) https://api.xxx.com/v1/chat/completions
    统一规范到完整终点：.../v1/chat/completions
    """
    if not base_url:
        raise ValueError("llm.base_url is empty")
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"

def _chat_completions_request(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    max_tokens: int = 1024,
    timeout: int = 120,
    response_format: Optional[Dict[str, str]] = None,
) -> str:
    """
    统一的 OpenAI 兼容 Chat Completions 请求（requests 直连）。
    适配 DeepSeek / SiliconFlow / 其他 OAI 兼容服务。
    response_format 不被支持时（HTTP 400）自动去掉该参数重试一次。
    """
    url = _normalize_chat_endpoint(base_url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if response_format:
        payload["response_format"] = response_format
    resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    if resp.status_code == 400 and response_format:
        payload.pop("response_format", None)
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()

    # 标准 OAI 兼容返回。思考模式的最终答案在 content，推理过程在 reasoning_content。
    try:
        message = data["choices"][0]["message"] or {}
    except Exception:
        message = {}
    content = message.get("content") or message.get("text") or ""
    if not str(content).strip():
        content = message.get("reasoning_content") or ""
    return content
