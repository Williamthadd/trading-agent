"""API models and validation for the TradingAgents backend service."""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tradingagents.dataflows.symbol_utils import normalize_symbol
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS

ANALYSTS = ("market", "social", "news", "fundamentals")
RESEARCH_DEPTHS = (1, 3, 5)
EXTRA_PROVIDERS = ("openrouter", "azure")
SUPPORTED_PROVIDERS = tuple(dict.fromkeys((*MODEL_OPTIONS.keys(), *EXTRA_PROVIDERS)))

_TICKER_RE = re.compile(r"^(?:[A-Za-z0-9._^=\-]{1,32}|[A-Za-z0-9._^=\-]{1,31}\+)$")
_MODEL_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,160}$")
_LANGUAGE_RE = re.compile(r"^[^\x00-\x1f\x7f]{2,48}$")


class RunRequest(BaseModel):
    """A validated, secret-free TradingAgents run request.

    API credentials intentionally are not accepted by this model. They must be
    configured server-side in ``.env`` so they can never be echoed into a run
    document or API response.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ticker: str = Field(min_length=1, max_length=32, examples=["NVDA", "BTC-USD"])
    analysis_date: str = Field(description="Market date in YYYY-MM-DD format")
    output_language: str = Field(default="English", min_length=2, max_length=48)
    analysts: list[str] = Field(default_factory=lambda: list(ANALYSTS), min_length=1)
    research_depth: Literal[1, 3, 5] = 1
    llm_provider: str = Field(min_length=1, max_length=32)
    quick_model: str = Field(min_length=1, max_length=160)
    deep_model: str = Field(min_length=1, max_length=160)
    backend_url: str | None = Field(default=None, max_length=500)
    thinking_level: Literal["high", "minimal"] | None = None
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    anthropic_effort: Literal["low", "medium", "high"] | None = None

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, value: str) -> str:
        value = value.strip().upper()
        if not _TICKER_RE.fullmatch(value):
            raise ValueError(
                "ticker may contain letters, numbers, dot, dash, underscore, ^, or =, "
                "with an optional trailing +"
            )
        return normalize_symbol(value)

    @field_validator("analysis_date")
    @classmethod
    def validate_analysis_date(cls, value: str) -> str:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("analysis_date must use YYYY-MM-DD format") from exc
        if parsed > date.today():
            raise ValueError("analysis_date cannot be in the future")
        return parsed.isoformat()

    @field_validator("output_language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        if value.lower() == "custom":
            raise ValueError("replace 'custom' with the actual output language")
        if not _LANGUAGE_RE.fullmatch(value):
            raise ValueError("output_language contains unsupported control characters")
        return value

    @field_validator("analysts")
    @classmethod
    def validate_analysts(cls, values: list[str]) -> list[str]:
        normalized = [str(value).strip().lower() for value in values]
        invalid = sorted(set(normalized).difference(ANALYSTS))
        if invalid:
            raise ValueError(f"unsupported analysts: {', '.join(invalid)}")
        if len(normalized) != len(set(normalized)):
            raise ValueError("analysts must not contain duplicates")
        # The graph topology follows a fixed canonical order, just like the CLI.
        return [analyst for analyst in ANALYSTS if analyst in normalized]

    @field_validator("llm_provider")
    @classmethod
    def validate_provider(cls, value: str) -> str:
        value = value.lower()
        if value not in SUPPORTED_PROVIDERS:
            raise ValueError(f"unsupported llm_provider: {value}")
        return value

    @field_validator("quick_model", "deep_model")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        if value.lower() == "custom":
            raise ValueError("replace 'custom' with the actual model ID")
        if not _MODEL_RE.fullmatch(value):
            raise ValueError("model ID contains unsupported control characters")
        return value

    @field_validator("backend_url")
    @classmethod
    def validate_backend_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("backend_url must be an absolute http(s) URL")
        # Credentials and query tokens do not belong in a persisted run request.
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "backend_url cannot contain credentials, query parameters, or a fragment"
            )
        return value

    @model_validator(mode="after")
    def validate_provider_controls(self) -> RunRequest:
        if self.backend_url and self.llm_provider not in {"ollama", "openai_compatible"}:
            raise ValueError(
                "backend_url is accepted only for ollama or openai_compatible; "
                "configure hosted-provider overrides in the server environment"
            )
        if self.thinking_level is not None and self.llm_provider != "google":
            raise ValueError("thinking_level is only valid for the google provider")
        if self.reasoning_effort is not None and self.llm_provider != "openai":
            raise ValueError("reasoning_effort is only valid for the openai provider")
        if self.anthropic_effort is not None and self.llm_provider != "anthropic":
            raise ValueError("anthropic_effort is only valid for the anthropic provider")

        # Fundamental statements are not available for crypto instruments.
        ticker = self.ticker.upper()
        crypto_suffixes = ("-USD", "-USDT", "-USDC", "-BTC", "-ETH")
        if ticker.endswith(crypto_suffixes) and "fundamentals" in self.analysts:
            raise ValueError("fundamentals analyst is not available for crypto tickers")
        return self

    def public_dict(self) -> dict[str, Any]:
        """Return the persistence-safe request representation."""
        return self.model_dump(mode="json")


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    storage: dict[str, Any]
    active_runs: int


class ErrorResponse(BaseModel):
    detail: str
