from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from scr.config import settings


def _validate_json_shape(value: Any, *, max_depth: int = 12, max_nodes: int = 5000) -> Any:
    nodes = 0

    def visit(item: Any, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > max_nodes:
            raise ValueError("JSON payload contains too many nested values")
        if depth > max_depth:
            raise ValueError("JSON payload is nested too deeply")
        if isinstance(item, dict):
            if len(item) > 1000:
                raise ValueError("JSON object contains too many fields")
            for key, child in item.items():
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif isinstance(item, list):
            if len(item) > 1000:
                raise ValueError("JSON array contains too many items")
            for child in item:
                visit(child, depth + 1)

    visit(value, 0)
    return value


class ResearchRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    marketplace: Literal["US", "UK", "DE", "JP", "CA"] = "US"
    intent: Literal["market_overview", "trend", "category", "competitor", "review", "keyword", "profit", "supplier", "score", "full_pipeline", "qna"] | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = Field(default=None, min_length=36, max_length=36, pattern=r"^[0-9a-fA-F-]{36}$")
    project_id: str | None = Field(default=None, min_length=36, max_length=36, pattern=r"^[0-9a-fA-F-]{36}$")

    @field_validator("params")
    @classmethod
    def validate_params(cls, params: dict[str, Any]) -> dict[str, Any]:
        _validate_json_shape(params)
        if len(params) > 40:
            raise ValueError("params contains too many fields")
        for key, value in params.items():
            if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,39}", str(key)):
                raise ValueError("invalid parameter name")
            if isinstance(value, str) and len(value) > 500:
                raise ValueError("parameter value is too long")
            if isinstance(value, list) and len(value) > 100:
                raise ValueError("parameter list is too long")
        return params


class ProfitRequest(BaseModel):
    selling_price: float = Field(default=29.99, gt=0, le=100000)
    cost_price: float = Field(default=8.50, ge=0, le=100000)
    weight_lb: float = Field(default=1.5, ge=0, le=500)
    length_in: float = Field(default=10, ge=0, le=500)
    width_in: float = Field(default=7, ge=0, le=500)
    height_in: float = Field(default=5, ge=0, le=500)
    shipping: float = Field(default=1.20, ge=0, le=100000)
    tax_rate: float = Field(default=0.05, ge=0, le=1)
    size_tier: Literal["small_standard", "large_standard", "large_oversize"] = "large_standard"
    currency: Literal["USD"] = "USD"


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    organization_name: str = Field(min_length=1, max_length=160)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("请输入有效邮箱地址。")
        return normalized


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    organization_id: str | None = Field(default=None, min_length=36, max_length=36)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().casefold()


class MemberCreateRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    role: Literal["admin", "analyst", "viewer"] = "analyst"


class FavoriteRequest(BaseModel):
    favorite: bool


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)


class ReviewRequest(BaseModel):
    status: Literal["comment", "approved", "rejected"] = "comment"
    comment: str = Field(min_length=1, max_length=4000)


class CandidateRequest(BaseModel):
    external_key: str = Field(min_length=1, max_length=320)
    title: str = Field(min_length=1, max_length=1000)
    marketplace: Literal["US", "UK", "DE", "JP", "CA"] = "US"
    source: str = Field(min_length=1, max_length=240)
    source_url: str | None = Field(default=None, max_length=2000)
    data: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = Field(default=None, min_length=36, max_length=36, pattern=r"^[0-9a-fA-F-]{36}$")
    task_id: str | None = Field(default=None, min_length=36, max_length=36, pattern=r"^[0-9a-fA-F-]{36}$")

    @field_validator("data")
    @classmethod
    def validate_data(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json_shape(value)


class ComplianceRequest(BaseModel):
    marketplace: Literal["US", "UK", "DE", "JP", "CA"] = "US"
    category: str = Field(min_length=1, max_length=160)
    rule_source: str | None = Field(default=None, max_length=1000)
    rules_updated_at: str | None = Field(default=None, max_length=40)
    findings: dict[str, Any] = Field(default_factory=dict)
    project_id: str | None = Field(default=None, min_length=36, max_length=36, pattern=r"^[0-9a-fA-F-]{36}$")
    candidate_id: str | None = Field(default=None, min_length=36, max_length=36, pattern=r"^[0-9a-fA-F-]{36}$")

    @field_validator("findings")
    @classmethod
    def validate_findings(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json_shape(value)


class FeedbackRequest(BaseModel):
    outcome: Literal["selected", "rejected", "ordered", "launched", "other"]
    task_id: str | None = Field(default=None, min_length=36, max_length=36, pattern=r"^[0-9a-fA-F-]{36}$")
    metrics: dict[str, Any] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=4000)

    @field_validator("metrics")
    @classmethod
    def validate_metrics(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json_shape(value)
