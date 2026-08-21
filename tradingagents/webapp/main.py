"""FastAPI entry point for the TradingAgents backend API."""

import os
from datetime import date as date_type
from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Path as ApiPath, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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


DEFAULT_CORS_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _cors_origins() -> list[str]:
    """Return exact, credential-free frontend origins allowed by the API."""
    raw = os.getenv("WEB_CORS_ORIGINS", "").strip()
    candidates = raw.split(",") if raw else DEFAULT_CORS_ORIGINS
    origins: list[str] = []
    for raw_origin in candidates:
        candidate = raw_origin.strip().rstrip("/")
        parsed = urlsplit(candidate)
        try:
            parsed_port = parsed.port
        except ValueError as exc:
            raise RuntimeConfigurationError(
                f"WEB_CORS_ORIGINS contains an invalid port: {raw_origin.strip()!r}"
            ) from exc
        if (
            not candidate
            or candidate == "*"
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise RuntimeConfigurationError(
                "WEB_CORS_ORIGINS must contain comma-separated http(s) origins only "
                "(for example http://localhost:5173), without paths, credentials, "
                "queries, fragments, or wildcards."
            )
        # Reading ``parsed.port`` above also validates the port range. Keep the
        # user's exact hostname spelling because CORS origin matching is exact.
        _ = parsed_port
        if candidate not in origins:
            origins.append(candidate)
    return origins


WEB_DEFAULT_LLM_PROVIDER = "google"
WEB_LOCAL_LLM_PROVIDER = "ollama"
WEB_LOCAL_LLM_MODEL = "tradingagents-llama3.2:16k"
WEB_LLM_PROVIDERS = frozenset({WEB_DEFAULT_LLM_PROVIDER, WEB_LOCAL_LLM_PROVIDER})

# The frontend options API intentionally exposes one known-good local model. The
# wider CLI/model catalog still supports arbitrary Ollama models, but keeping
# the web choice explicit guarantees that selecting the local provider launches
# the Llama model documented and sized for this application's target laptop.
WEB_MODEL_OPTIONS = {
    WEB_DEFAULT_LLM_PROVIDER: MODEL_OPTIONS[WEB_DEFAULT_LLM_PROVIDER],
    WEB_LOCAL_LLM_PROVIDER: {
        "quick": [
            ("Llama 3.2 3B 16K - Local via Ollama", WEB_LOCAL_LLM_MODEL),
        ],
        "deep": [
            ("Llama 3.2 3B 16K - Local via Ollama", WEB_LOCAL_LLM_MODEL),
        ],
    },
}

PROVIDERS: tuple[dict[str, Any], ...] = (
    {"id": WEB_DEFAULT_LLM_PROVIDER, "label": "Google Gemini"},
    {
        "id": WEB_LOCAL_LLM_PROVIDER,
        "label": "Llama 3.2 3B (Local / Ollama)",
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
    options = WEB_MODEL_OPTIONS.get(provider, {}).get(mode)
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
    return None


def _provider_options() -> list[dict[str, Any]]:
    result = []
    for spec in PROVIDERS:
        provider = spec["id"]
        item = {
            **spec,
            "quick_models": _model_options(provider, "quick"),
            "deep_models": _model_options(provider, "deep"),
            "supports_backend_url": False,
            "requires_backend_url": False,
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
    google_models = WEB_MODEL_OPTIONS[WEB_DEFAULT_LLM_PROVIDER]
    defaults = {
        "ticker": "SPY",
        "analysis_date": date_type.today().isoformat(),
        "output_language": DEFAULT_CONFIG.get("output_language", "English"),
        "analysts": list(ANALYSTS),
        "research_depth": depth,
        "llm_provider": WEB_DEFAULT_LLM_PROVIDER,
        "quick_model": google_models["quick"][0][1],
        "deep_model": google_models["deep"][0][1],
        # A server-side provider override must not be disclosed to API clients.
        "backend_url": None,
        "thinking_level": DEFAULT_CONFIG.get("google_thinking_level"),
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
    # Validate the browser boundary before constructing RunManager. Its startup
    # reconciliation can update persisted runs, so invalid CORS configuration
    # must fail before any storage state is touched.
    cors_origins = _cors_origins()
    run_store = store or build_run_store()
    manager = RunManager(run_store)
    auth_manager = FirebaseAuthManager(required=auth_required, token_verifier=token_verifier)
    api = FastAPI(
        title="TradingAgents API",
        description="Authenticated orchestration and polling API for the TradingAgents graph.",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    api.state.run_manager = manager
    api.state.auth_manager = auth_manager
    api.state.cors_origins = cors_origins
    api.add_middleware(
        CORSMiddleware,
        allow_origins=api.state.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Accept", "Authorization", "Content-Type"],
        expose_headers=["Retry-After", "WWW-Authenticate"],
        max_age=600,
    )
    firebase_bearer = HTTPBearer(
        auto_error=False,
        bearerFormat="Firebase ID token",
        scheme_name="FirebaseBearer",
        description="Firebase Authentication ID token issued to the standalone frontend.",
    )

    def require_user(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(firebase_bearer),
        ],
    ) -> dict[str, Any]:
        authorization = (
            f"{credentials.scheme} {credentials.credentials}" if credentials is not None else None
        )
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

    @api.get("/", include_in_schema=False, tags=["system"])
    def root() -> dict[str, Any]:
        return {
            "service": "tradingagents-api",
            "status": "ok",
            "health": "/api/health",
            "docs": "/api/docs",
            "message": "The frontend is a separate application; this process serves the backend API only.",
        }

    @api.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": "tradingagents-api",
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
        if request.llm_provider not in WEB_LLM_PROVIDERS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "The TradingAgents API supports only Google Gemini and "
                    "Llama 3.2 3B through the local Ollama server."
                ),
            )
        if request.llm_provider == WEB_LOCAL_LLM_PROVIDER and (
            request.quick_model != WEB_LOCAL_LLM_MODEL or request.deep_model != WEB_LOCAL_LLM_MODEL
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "The local API provider requires the TradingAgents Llama 3.2 "
                    "16K model for both the quick and deep model."
                ),
            )
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

    return api


app = create_app()


def cli() -> None:
    """Launch the single-process backend API server."""
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
