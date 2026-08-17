"""FastAPI entry point for the TradingAgents browser application."""

import os
from datetime import date as date_type
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Header, HTTPException, Path as ApiPath, Query, status
from fastapi.staticfiles import StaticFiles

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS

from . import __version__
from .auth import (
    AuthenticationConfigurationError,
    AuthenticationForbidden,
    FirebaseAuthManager,
    InvalidAuthenticationToken,
    TokenVerifier,
)
from .models import ANALYSTS, RESEARCH_DEPTHS, HealthResponse, RunRequest
from .runner import (
    RunManager,
    RunQueueFull,
    RunStoreUnavailable,
    RuntimeConfigurationError,
    configured_backend_url,
)
from .storage import build_run_store


def _public_backend_url(value: Any) -> str | None:
    """Return a browser-safe HTTP(S) endpoint without embedded credentials."""
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip().rstrip("/")
    parsed = urlsplit(candidate)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return None
    return candidate


PROVIDERS: tuple[dict[str, Any], ...] = (
    {"id": "openai", "label": "OpenAI", "backend_url": "https://api.openai.com/v1"},
    {"id": "google", "label": "Google Gemini", "backend_url": None},
    {"id": "anthropic", "label": "Anthropic Claude", "backend_url": "https://api.anthropic.com"},
    {"id": "xai", "label": "xAI", "backend_url": "https://api.x.ai/v1"},
    {"id": "deepseek", "label": "DeepSeek", "backend_url": "https://api.deepseek.com"},
    {
        "id": "qwen",
        "label": "Qwen (International)",
        "backend_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    },
    {
        "id": "qwen-cn",
        "label": "Qwen (China)",
        "backend_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    {
        "id": "glm",
        "label": "GLM / Z.AI (International)",
        "backend_url": "https://api.z.ai/api/paas/v4",
    },
    {
        "id": "glm-cn",
        "label": "GLM / BigModel (China)",
        "backend_url": "https://open.bigmodel.cn/api/paas/v4",
    },
    {"id": "minimax", "label": "MiniMax (Global)", "backend_url": "https://api.minimax.io/v1"},
    {"id": "minimax-cn", "label": "MiniMax (China)", "backend_url": "https://api.minimaxi.com/v1"},
    {"id": "openrouter", "label": "OpenRouter", "backend_url": "https://openrouter.ai/api/v1"},
    {"id": "mistral", "label": "Mistral", "backend_url": "https://api.mistral.ai/v1"},
    {"id": "kimi", "label": "Kimi (Moonshot)", "backend_url": "https://api.moonshot.ai/v1"},
    {"id": "groq", "label": "Groq", "backend_url": "https://api.groq.com/openai/v1"},
    {"id": "nvidia", "label": "NVIDIA NIM", "backend_url": "https://integrate.api.nvidia.com/v1"},
    {"id": "azure", "label": "Azure OpenAI", "backend_url": None},
    {"id": "bedrock", "label": "Amazon Bedrock", "backend_url": None},
    {
        "id": "ollama",
        "label": "Ollama",
        "backend_url": _public_backend_url(configured_backend_url("ollama")),
    },
    {
        "id": "openai_compatible",
        "label": "OpenAI-compatible endpoint",
        "backend_url": _public_backend_url(configured_backend_url("openai_compatible")),
    },
)

ANALYST_LABELS = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
OUTPUT_LANGUAGES = (
    ("English", "English"),
    ("Indonesian", "Bahasa Indonesia"),
    ("Chinese", "Chinese (中文)"),
    ("Japanese", "Japanese (日本語)"),
    ("Korean", "Korean (한국어)"),
    ("Hindi", "Hindi (हिन्दी)"),
    ("Spanish", "Spanish (Español)"),
    ("Portuguese", "Portuguese (Português)"),
    ("French", "French (Français)"),
    ("German", "German (Deutsch)"),
    ("Arabic", "Arabic (العربية)"),
    ("Russian", "Russian (Русский)"),
    ("custom", "Custom language"),
)
CUSTOM_MODELS = [{"id": "custom", "label": "Custom model ID", "custom": True}]


def _model_options(provider: str, mode: str) -> list[dict[str, Any]]:
    options = MODEL_OPTIONS.get(provider, {}).get(mode)
    if not options:
        return copy_options(CUSTOM_MODELS)
    return [
        {"id": model_id, "label": label, "custom": model_id == "custom"}
        for label, model_id in options
    ]


def copy_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(option) for option in options]


def _thinking_control(provider: str) -> dict[str, Any] | None:
    if provider == "google":
        return {
            "key": "thinking_level",
            "label": "Thinking Mode",
            "default": "minimal",
            "options": [
                {"id": "high", "label": "Enable Thinking"},
                {"id": "minimal", "label": "Minimal / Disable Thinking"},
            ],
        }
    if provider == "openai":
        return {
            "key": "reasoning_effort",
            "label": "Reasoning Effort",
            "default": "medium",
            "options": [
                {"id": "low", "label": "Low"},
                {"id": "medium", "label": "Medium"},
                {"id": "high", "label": "High"},
            ],
        }
    if provider == "anthropic":
        return {
            "key": "anthropic_effort",
            "label": "Claude Effort",
            "default": "high",
            "options": [
                {"id": "low", "label": "Low"},
                {"id": "medium", "label": "Medium"},
                {"id": "high", "label": "High"},
            ],
        }
    return None


def _provider_options() -> list[dict[str, Any]]:
    result = []
    for spec in PROVIDERS:
        provider = spec["id"]
        configured_url = (
            configured_backend_url(provider)
            if provider in {"ollama", "openai_compatible"}
            else None
        )
        item = {
            **spec,
            "backend_url": (
                _public_backend_url(configured_url)
                if provider in {"ollama", "openai_compatible"}
                else spec.get("backend_url")
            ),
            "quick_models": _model_options(provider, "quick"),
            "deep_models": _model_options(provider, "deep"),
            # Hosted-provider endpoint overrides belong to the server config.
            # Only explicitly custom/local runtimes accept a URL per request.
            "supports_backend_url": provider in {"ollama", "openai_compatible"},
            "requires_backend_url": provider == "openai_compatible" and not configured_url,
        }
        control = _thinking_control(provider)
        if control:
            item["thinking_control"] = control
        result.append(item)
    return result


def _defaults() -> dict[str, Any]:
    depth = DEFAULT_CONFIG.get("max_debate_rounds", 1)
    if depth not in RESEARCH_DEPTHS:
        depth = 1
    provider = str(DEFAULT_CONFIG.get("llm_provider", "openai")).lower()
    defaults = {
        "ticker": "SPY",
        "analysis_date": date_type.today().isoformat(),
        "output_language": DEFAULT_CONFIG.get("output_language", "English"),
        "analysts": list(ANALYSTS),
        "research_depth": depth,
        "llm_provider": provider,
        "quick_model": DEFAULT_CONFIG.get("quick_think_llm", "gpt-5.4-mini"),
        "deep_model": DEFAULT_CONFIG.get("deep_think_llm", "gpt-5.5"),
        # A server-side provider override must not be disclosed to the browser.
        "backend_url": None,
        "thinking_level": DEFAULT_CONFIG.get("google_thinking_level"),
        "reasoning_effort": DEFAULT_CONFIG.get("openai_reasoning_effort"),
        "anthropic_effort": DEFAULT_CONFIG.get("anthropic_effort"),
    }
    return defaults


def _valid_date(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return date_type.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date must use YYYY-MM-DD format",
        ) from exc


def create_app(
    store: Any | None = None,
    *,
    auth_required: bool | None = None,
    token_verifier: TokenVerifier | None = None,
) -> FastAPI:
    run_store = store or build_run_store()
    manager = RunManager(run_store)
    auth_manager = FirebaseAuthManager(required=auth_required, token_verifier=token_verifier)
    api = FastAPI(
        title="TradingAgents Web Terminal",
        description="Browser interface and polling API for the TradingAgents graph.",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    api.state.run_manager = manager
    api.state.auth_manager = auth_manager

    def require_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
        try:
            return auth_manager.authenticate(authorization)
        except InvalidAuthenticationToken as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(exc),
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        except AuthenticationForbidden as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        except AuthenticationConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    @api.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "tradingagents-web",
            "version": __version__,
            "storage": manager.storage_info,
            "active_runs": manager.active_count,
        }

    @api.get("/api/auth/config", tags=["authentication"])
    def auth_config() -> dict[str, Any]:
        return auth_manager.public_config

    @api.get("/api/auth/session", tags=["authentication"])
    def auth_session(user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
        return {"authenticated": True, "user": user}

    @api.get("/api/options", tags=["system"])
    def options(_user: Annotated[dict[str, Any], Depends(require_user)]) -> dict[str, Any]:
        languages = [{"id": value, "label": label} for value, label in OUTPUT_LANGUAGES]
        return {
            "analysts": [{"id": analyst, "label": ANALYST_LABELS[analyst]} for analyst in ANALYSTS],
            "research_depths": [
                {
                    "id": depth,
                    "label": {1: "Shallow", 3: "Medium", 5: "Deep"}[depth],
                    "description": {
                        1: "Quick research with one debate and risk round.",
                        3: "Balanced research with three debate and risk rounds.",
                        5: "Comprehensive research with five debate and risk rounds.",
                    }[depth],
                }
                for depth in RESEARCH_DEPTHS
            ],
            "providers": _provider_options(),
            "output_languages": languages,
            "languages": languages,
            "defaults": _defaults(),
            "storage": manager.storage_info,
        }

    @api.post("/api/runs", status_code=status.HTTP_202_ACCEPTED, tags=["runs"])
    def create_run(
        request: RunRequest,
        _user: Annotated[dict[str, Any], Depends(require_user)],
    ) -> dict[str, Any]:
        try:
            return manager.start_run(request)
        except RuntimeConfigurationError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except RunStoreUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except RunQueueFull as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=str(exc),
                headers={"Retry-After": "5"},
            ) from exc

    @api.get("/api/runs/{run_id}", tags=["runs"])
    def get_run(
        _user: Annotated[dict[str, Any], Depends(require_user)],
        run_id: str = ApiPath(pattern=r"^[a-f0-9]{32}$"),
    ) -> dict[str, Any]:
        try:
            result = manager.get_run(run_id)
        except RunStoreUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Run storage is temporarily unavailable: {exc}",
            ) from exc
        if result is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        return result

    @api.get("/api/history", tags=["history"])
    def history(
        _user: Annotated[dict[str, Any], Depends(require_user)],
        date: str | None = Query(default=None, description="Creation day in YYYY-MM-DD"),
    ) -> dict[str, Any]:
        date_key = _valid_date(date)
        try:
            runs = manager.list_runs(date_key)
        except RunStoreUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Run storage is temporarily unavailable: {exc}",
            ) from exc
        return {"date": date_key, "count": len(runs), "runs": runs}

    @api.get("/api/history/{run_id}", tags=["history"])
    def history_detail(
        _user: Annotated[dict[str, Any], Depends(require_user)],
        run_id: str = ApiPath(pattern=r"^[a-f0-9]{32}$"),
    ) -> dict[str, Any]:
        return get_run(_user, run_id)

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        # Mounted last so /api/* always wins. ``html=True`` serves index.html
        # at the root while assets stay relative to the same package directory.
        api.mount("/", StaticFiles(directory=static_dir, html=True), name="web-terminal")

    return api


app = create_app()


def cli() -> None:
    """Launch the single-process web server used by ``tradingagents-web``."""
    import uvicorn

    host = os.getenv("WEB_HOST", "127.0.0.1").strip() or "127.0.0.1"
    raw_port = os.getenv("WEB_PORT", "8000").strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise SystemExit(f"WEB_PORT must be an integer, got {raw_port!r}") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("WEB_PORT must be between 1 and 65535")

    uvicorn.run(
        "tradingagents.webapp.main:app",
        host=host,
        port=port,
        workers=1,
    )


if __name__ == "__main__":
    cli()
