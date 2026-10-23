from __future__ import annotations

import re
import math
from typing import Any


_INJECTION_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.I),
    re.compile(r"(reveal|show|print|输出|泄露).{0,24}(system prompt|developer message|系统提示词|隐藏指令)", re.I),
    re.compile(r"(忽略|无视).{0,12}(之前|以上|前面).{0,12}(指令|规则|提示)", re.I),
    re.compile(r"(developer mode|DAN mode|越狱模式|解除限制)", re.I),
)
_NUMBER = re.compile(r"(?<![\w])(?:[$€£]\s*)?-?\d[\d,]*(?:\.\d+)?\s*%?")
ALLOWED_TOOL_PARAMS = {
    "asins", "max_reviews", "depth", "category_name", "node_name", "selling_price", "cost_price",
    "weight_lb", "length_in", "width_in", "height_in", "shipping", "tax_rate", "size_tier", "currency",
    "min_price", "max_price", "min_order_qty", "platform", "limit", "page", "sort_type", "max_keywords", "scores",
}


def is_prompt_injection(text: str) -> bool:
    return any(pattern.search(text) for pattern in _INJECTION_PATTERNS)


def clean_history(history: list[dict[str, Any]] | None, message_limit: int = 12) -> list[dict[str, str]]:
    clean: list[dict[str, str]] = []
    for item in (history or [])[-message_limit:]:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant"} and isinstance(content, str):
            clean.append({"role": role, "content": content[:4000]})
    return clean


def sanitize_tool_params(params: Any) -> dict[str, Any]:
    if not isinstance(params, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in params.items():
        if key not in ALLOWED_TOOL_PARAMS:
            continue
        if key == "scores" and isinstance(value, dict):
            clean[key] = {name: max(0, min(100, float(score))) for name, score in value.items()
                          if name in {"market_demand", "competition", "profitability", "trend", "supply_chain"}
                          and isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score)}
        elif key == "asins" and isinstance(value, list):
            clean[key] = [str(item)[:32] for item in value[:20] if isinstance(item, str)]
        elif isinstance(value, bool):
            clean[key] = value
        elif isinstance(value, (int, float)) and math.isfinite(value):
            clean[key] = max(-100000, min(100000, value))
        elif isinstance(value, str):
            clean[key] = value[:200]
    return clean


def generated_numbers_are_grounded(generated: str, source_payload: str) -> bool:
    """Reject model-authored summaries that introduce numeric claims absent from source data."""
    source_numbers = {normalize_number(match.group()) for match in _NUMBER.finditer(source_payload)}
    generated_numbers = {normalize_number(match.group()) for match in _NUMBER.finditer(generated)}
    return generated_numbers.issubset(source_numbers)


def normalize_number(value: str) -> str:
    return re.sub(r"[,$€£\s%]", "", value)
