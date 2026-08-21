"""Background TradingAgents execution and polling state management."""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.llm_clients.api_key_env import get_api_key_env

from .models import RunRequest

LOGGER = logging.getLogger(__name__)

ANALYST_AGENT_NAMES = {
    "market": "Market Analyst",
    "social": "Sentiment Analyst",
    "news": "News Analyst",
    "fundamentals": "Fundamentals Analyst",
}
ANALYST_REPORT_KEYS = {
    "market": "market_report",
    "social": "sentiment_report",
    "news": "news_report",
    "fundamentals": "fundamentals_report",
}
FIXED_AGENTS = (
    "Bull Researcher",
    "Bear Researcher",
    "Research Manager",
    "Trader",
    "Aggressive Analyst",
    "Conservative Analyst",
    "Neutral Analyst",
    "Portfolio Manager",
)
REPORT_SPECS = {
    "market_report": ("Market Analyst", "Market Analysis"),
    "sentiment_report": ("Sentiment Analyst", "Sentiment Analysis"),
    "news_report": ("News Analyst", "News Analysis"),
    "fundamentals_report": ("Fundamentals Analyst", "Fundamentals Analysis"),
    "bull_researcher": ("Bull Researcher", "Bull Researcher Analysis"),
    "bear_researcher": ("Bear Researcher", "Bear Researcher Analysis"),
    "research_manager": ("Research Manager", "Research Manager Decision"),
    "investment_plan": ("Research Manager", "Investment Plan"),
    "trader_investment_plan": ("Trader", "Trading Plan"),
    "aggressive_analyst": ("Aggressive Analyst", "Aggressive Risk Analysis"),
    "conservative_analyst": ("Conservative Analyst", "Conservative Risk Analysis"),
    "neutral_analyst": ("Neutral Analyst", "Neutral Risk Analysis"),
    "portfolio_manager": ("Portfolio Manager", "Portfolio Manager Decision"),
    "final_trade_decision": ("Portfolio Manager", "Final Trade Decision"),
}

_SECRET_KEY_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|access[_-]?token|token|password|secret)"
    r"(\s*[=:]\s*)([^\s&,;'\"}]+)"
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b")
_GOOGLE_KEY_RE = re.compile(r"\bAIza[A-Za-z0-9_-]{20,}\b")
_HTTP_URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SENSITIVE_FIELD_RE = re.compile(
    r"(?i)(?:^|_)(?:api_?key|private_?key|access_?token|refresh_?token|"
    r"authorization|password|passwd|secret|client_?secret|credentials?)(?:_|$)"
)
_GRAPH_EXECUTION_LOCK = threading.Lock()


class RunStoreUnavailable(RuntimeError):
    """Raised when a run cannot be persisted or read."""


class RuntimeConfigurationError(RuntimeError):
    """Raised before a run when its server-side credentials are incomplete."""


class RunQueueFull(RuntimeError):
    """Raised when the bounded single-worker run queue has no free slot."""


def configured_backend_url(provider: str) -> str | None:
    """Return a server-approved custom/local endpoint for one provider."""
    provider = provider.strip().lower()
    if provider == "ollama":
        value = os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434/v1"
    elif (
        provider == "openai_compatible"
        and str(DEFAULT_CONFIG.get("llm_provider", "")).strip().lower() == provider
    ):
        value = DEFAULT_CONFIG.get("backend_url")
    else:
        value = None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().rstrip("/")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def local_date_key() -> str:
    """Return the server's local calendar day for the history sidebar."""
    return datetime.now().astimezone().date().isoformat()


def _is_sensitive_field(name: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return normalized == "key" or bool(_SENSITIVE_FIELD_RE.search(normalized))


def _redact_url_auth(match: re.Match[str]) -> str:
    """Remove credentials, query values, and fragments from an error-message URL."""
    raw = match.group(0)
    trailing = ""
    while raw and raw[-1] in ".,;):]":
        trailing = raw[-1] + trailing
        raw = raw[:-1]
    try:
        parsed = urlsplit(raw)
        hostname = parsed.hostname
        if not hostname:
            return "[REDACTED_URL]" + trailing
        safe_host = (
            f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
        )
        if parsed.port is not None:
            safe_host = f"{safe_host}:{parsed.port}"
        safe_url = urlunsplit((parsed.scheme, safe_host, parsed.path, "", ""))
        if parsed.username or parsed.password:
            safe_url = f"{parsed.scheme}://[REDACTED]@{safe_host}{parsed.path}"
        if parsed.query:
            safe_url += "?[REDACTED]"
        if parsed.fragment:
            safe_url += "#[REDACTED]"
        return safe_url + trailing
    except ValueError:
        return "[REDACTED_URL]" + trailing


def _redact_secrets(value: Any, sensitive_environment_values: tuple[str, ...]) -> Any:
    """Recursive implementation sharing one environment-secret snapshot."""
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_field(key_text):
                cleaned[key_text] = "[REDACTED]"
            else:
                cleaned[key_text] = _redact_secrets(item, sensitive_environment_values)
        return cleaned
    if isinstance(value, (list, tuple, set)):
        return [_redact_secrets(item, sensitive_environment_values) for item in value]
    if value is None or isinstance(value, (bool, int, float)):
        return value

    text = str(value)
    # Exact replacement catches credentials embedded in provider exception URLs.
    for secret in sensitive_environment_values:
        text = text.replace(secret, "[REDACTED]")
    text = _SECRET_KEY_RE.sub(r"\1\2[REDACTED]", text)
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _OPENAI_KEY_RE.sub("[REDACTED]", text)
    text = _GOOGLE_KEY_RE.sub("[REDACTED]", text)
    return _HTTP_URL_RE.sub(_redact_url_auth, text)


def redact_secrets(value: Any) -> Any:
    """Recursively remove common credentials before API/storage exposure.

    Environment variables are inspected once per payload instead of once for
    every scalar field. Large polling responses can contain thousands of
    fields, so this avoids repeated process-environment scans without changing
    the redaction rules.
    """
    sensitive_environment_values = tuple(
        secret
        for name, secret in os.environ.items()
        if secret and len(secret) >= 6 and _is_sensitive_field(name)
    )
    return _redact_secrets(value, sensitive_environment_values)


def safe_error(exc: BaseException) -> str:
    """Create a useful, bounded error without a traceback or credential value."""
    message = str(redact_secrets(str(exc))).strip() or exc.__class__.__name__
    return message[:2000]


def build_graph_config(request: RunRequest) -> dict[str, Any]:
    """Build one run's provider config without leaking another provider's endpoint."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    default_provider = str(config.get("llm_provider", "")).strip().lower()
    if request.llm_provider == "ollama":
        backend_url = request.backend_url or configured_backend_url("ollama")
    elif request.llm_provider == "openai_compatible":
        backend_url = request.backend_url or configured_backend_url("openai_compatible")
    elif request.llm_provider == default_provider:
        backend_url = config.get("backend_url")
    else:
        backend_url = None
    config.update(
        {
            "max_debate_rounds": request.research_depth,
            "max_risk_discuss_rounds": request.research_depth,
            "quick_think_llm": request.quick_model,
            "deep_think_llm": request.deep_model,
            "backend_url": backend_url,
            "llm_provider": request.llm_provider,
            "google_thinking_level": request.thinking_level,
            "openai_reasoning_effort": request.reasoning_effort,
            "anthropic_effort": request.anthropic_effort,
            "output_language": request.output_language,
            # Direct graph streaming below does not enter the checkpoint
            # context managed by propagate(); do not claim resume support.
            "checkpoint_enabled": False,
        }
    )
    return config


def _text_content(content: Any) -> str | None:
    if content is None:
        return None
    if isinstance(content, str):
        return content.strip() or None
    if isinstance(content, dict):
        text = content.get("text")
        return str(text).strip() if text else None
    if isinstance(content, list):
        pieces: list[str] = []
        for item in content:
            if isinstance(item, str) and item.strip():
                pieces.append(item.strip())
            elif isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                pieces.append(str(item["text"]).strip())
        return "\n".join(pieces) or None
    return str(content).strip() or None


def _bounded_text(value: Any, limit: int) -> str:
    text = str(redact_secrets(value))
    if len(text) <= limit:
        return text
    return f"{text[: limit - 24]}\n\n[output truncated]"


def _message_signature(message: Any) -> str:
    identifier = getattr(message, "id", None)
    if identifier:
        return f"id:{identifier}"
    raw = {
        "type": message.__class__.__name__,
        "content": getattr(message, "content", None),
        "tool_calls": getattr(message, "tool_calls", None),
    }
    encoded = json.dumps(raw, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class RunManager:
    """Own live state and execute one graph at a time in daemon threads.

    TradingAgents' data vendor configuration is process-global. Serializing
    graph execution prevents concurrent requests with different provider/model
    selections from mutating that shared configuration underneath one another.
    POST requests still return immediately; additional runs remain ``queued``.
    """

    def __init__(self, store: Any):
        self.store = store
        self._lock = threading.RLock()
        self._execution_lock = _GRAPH_EXECUTION_LOCK
        self._live: dict[str, dict[str, Any]] = {}
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._sequences: dict[str, int] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._cache_deadlines: dict[str, float] = {}
        self._reservations = 0
        self.queue_limit = self._read_queue_limit()
        self.cache_ttl_seconds = self._read_cache_ttl()
        self._reconcile_stale_runs()

    @property
    def active_count(self) -> int:
        self._evict_expired_terminal_runs()
        with self._lock:
            return self._reservations + sum(
                record.get("status") in {"queued", "running"} for record in self._live.values()
            )

    @staticmethod
    def _read_queue_limit() -> int:
        raw = os.getenv("WEB_RUN_QUEUE_LIMIT", "4").strip()
        try:
            value = int(raw)
        except ValueError as exc:
            raise RuntimeConfigurationError(
                f"WEB_RUN_QUEUE_LIMIT must be an integer, got {raw!r}"
            ) from exc
        if not 1 <= value <= 100:
            raise RuntimeConfigurationError("WEB_RUN_QUEUE_LIMIT must be between 1 and 100")
        return value

    @staticmethod
    def _read_cache_ttl() -> int:
        raw = os.getenv("WEB_LIVE_CACHE_TTL_SECONDS", "300").strip()
        try:
            value = int(raw)
        except ValueError as exc:
            raise RuntimeConfigurationError(
                f"WEB_LIVE_CACHE_TTL_SECONDS must be an integer, got {raw!r}"
            ) from exc
        if not 0 <= value <= 86_400:
            raise RuntimeConfigurationError(
                "WEB_LIVE_CACHE_TTL_SECONDS must be between 0 and 86400"
            )
        return value

    def _mark_terminal_cache(self, run_id: str) -> None:
        with self._lock:
            self._cache_deadlines[run_id] = time.monotonic() + self.cache_ttl_seconds

    def _evict_expired_terminal_runs(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [
                run_id for run_id, deadline in self._cache_deadlines.items() if deadline <= now
            ]
            for run_id in expired:
                self._live.pop(run_id, None)
                self._events.pop(run_id, None)
                self._sequences.pop(run_id, None)
                self._cache_deadlines.pop(run_id, None)

    def _reconcile_stale_runs(self) -> None:
        """Mark work abandoned by a previous server process as failed."""
        enabled = os.getenv("WEB_RECONCILE_STALE_RUNS", "true").strip().lower()
        if enabled in {"0", "false", "no", "off"}:
            return
        if enabled not in {"1", "true", "yes", "on"}:
            raise RuntimeConfigurationError("WEB_RECONCILE_STALE_RUNS must be true or false")

        stale_statuses = {"queued", "running", "pending", "processing", "in_progress"}
        try:
            # Firestore histories can grow indefinitely. Stores that support a
            # status query should fetch only abandoned work instead of loading
            # every completed run during each cold start.
            list_by_statuses = getattr(self.store, "list_runs_by_statuses", None)
            runs = (
                list_by_statuses(stale_statuses)
                if callable(list_by_statuses)
                else self.store.list_runs(None)
            )
        except Exception as exc:  # startup should survive a transient store failure
            LOGGER.warning("Could not reconcile prior web runs: %s", safe_error(exc))
            return

        for record in runs or []:
            if not isinstance(record, dict) or record.get("status") not in stale_statuses:
                continue
            run_id = str(record.get("run_id") or "").strip()
            if not run_id:
                continue
            timestamp = utc_now()
            message = "Run interrupted because the web server stopped before completion."
            try:
                self.store.update_run(
                    run_id,
                    {
                        "status": "failed",
                        "progress": record.get("progress", 0),
                        "current_phase": "Interrupted",
                        "current_agent": None,
                        "error": message,
                        "completed_at": timestamp,
                    },
                )
                self.store.append_event(
                    run_id,
                    {
                        "event_id": uuid.uuid4().hex,
                        "created_at": timestamp,
                        "timestamp": timestamp,
                        "sequence": int(time.time() * 1000),
                        "agent": "System",
                        "type": "error",
                        "status": "failed",
                        "message": message,
                    },
                )
            except Exception as exc:
                LOGGER.warning("Could not reconcile stale run %s: %s", run_id, safe_error(exc))

    @property
    def storage_info(self) -> dict[str, Any]:
        backend = str(getattr(self.store, "backend_name", "unknown"))
        configured = bool(getattr(self.store, "configured", False))
        firebase = backend == "firestore" and configured
        return {
            "mode": "firebase" if firebase else "local",
            "backend": backend,
            "configured": configured,
            "message": (
                "Firebase Firestore is connected."
                if firebase
                else "Firebase is not configured; runs are stored in the local JSON fallback."
            ),
        }

    def validate_runtime(self, request: RunRequest) -> None:
        """Fail fast when a provider's required server-side secret is absent."""
        provider = request.llm_provider
        custom_urls_enabled = os.getenv("WEB_ALLOW_CUSTOM_BACKEND_URLS", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        approved_url = configured_backend_url(provider)
        if request.backend_url and request.backend_url != approved_url and not custom_urls_enabled:
            raise RuntimeConfigurationError(
                "This custom backend URL is not approved by the server. Configure the endpoint "
                "server-side or set WEB_ALLOW_CUSTOM_BACKEND_URLS=true only for trusted users "
                "and endpoints."
            )
        if provider == "openai_compatible" and not (request.backend_url or approved_url):
            raise RuntimeConfigurationError(
                "openai_compatible needs a backend URL. Configure "
                "TRADINGAGENTS_LLM_BACKEND_URL on the server or enter an approved endpoint."
            )
        if provider not in {"ollama", "openai_compatible", "bedrock"}:
            env_name = get_api_key_env(provider)
            if env_name and not os.environ.get(env_name):
                raise RuntimeConfigurationError(
                    f"{provider} is not configured on the server. Add {env_name} to .env "
                    "and restart the web server."
                )
        if provider == "azure":
            missing = [
                name
                for name in ("AZURE_OPENAI_ENDPOINT", "OPENAI_API_VERSION")
                if not os.environ.get(name)
            ]
            if missing:
                raise RuntimeConfigurationError(
                    "Azure OpenAI is missing server configuration: " + ", ".join(missing)
                )

    def start_run(self, request: RunRequest) -> dict[str, Any]:
        self.validate_runtime(request)
        with self._lock:
            if self.active_count >= self.queue_limit:
                raise RunQueueFull(
                    f"The run queue is full ({self.queue_limit} active/queued). "
                    "Wait for a run to finish and try again."
                )
            self._reservations += 1
        reservation_held = True

        run_id = uuid.uuid4().hex
        created_at = utc_now()
        agent_status = {
            **{ANALYST_AGENT_NAMES[key]: "pending" for key in request.analysts},
            **dict.fromkeys(FIXED_AGENTS, "pending"),
        }
        record = {
            "run_id": run_id,
            **request.public_dict(),
            "asset_type": self._asset_type(request.ticker),
            "status": "queued",
            "progress": 0,
            "current_phase": "Queued",
            "current_agent": None,
            "agent_status": agent_status,
            "reports": {},
            "decision": None,
            "error": None,
            "created_at": created_at,
            "updated_at": created_at,
            "date_key": local_date_key(),
        }

        try:
            try:
                created = self.store.create_run(copy.deepcopy(record))
            except Exception as exc:
                raise RunStoreUnavailable(
                    f"Unable to create run in {self.storage_info['backend']}: {safe_error(exc)}"
                ) from exc
            if isinstance(created, dict):
                record.update(redact_secrets(created))

            with self._lock:
                self._live[run_id] = record
                self._events[run_id] = []
                self._sequences[run_id] = 0
                self._reservations -= 1
                reservation_held = False
        finally:
            if reservation_held:
                with self._lock:
                    self._reservations -= 1

        self._emit(
            run_id,
            event_type="status",
            agent="System",
            status="queued",
            message=f"Analysis for {request.ticker} was queued.",
        )
        try:
            thread = threading.Thread(
                target=self._worker,
                args=(run_id, request),
                name=f"tradingagents-web-{run_id[:8]}",
                daemon=True,
            )
            with self._lock:
                self._threads[run_id] = thread
            thread.start()
        except Exception as exc:
            with self._lock:
                self._threads.pop(run_id, None)
            self._fail(run_id, exc, 0.0)
            raise RuntimeConfigurationError(
                "Unable to start the background analysis worker."
            ) from exc
        return self.get_run(run_id) or copy.deepcopy(record)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        self._evict_expired_terminal_runs()
        # Polling an active run must stay in memory. Reading its Firestore event
        # subcollection on every frontend poll would repeatedly bill all events
        # accumulated so far. Storage is consulted only for runs not owned by
        # this process (for example, history restored after a restart).
        with self._lock:
            live = copy.deepcopy(self._live.get(run_id))
            live_events = copy.deepcopy(self._events.get(run_id, []))

        if live is not None:
            # Live records and events are sanitized before entering the cache.
            # Avoid recursively redacting, de-duplicating, and reconstructing
            # the entire growing response on every 1.6-second frontend poll.
            live["events"] = sorted(
                live_events,
                key=lambda event: (event.get("sequence", 0), event.get("created_at", "")),
            )
            return live

        try:
            stored = self.store.get_run(run_id)
            stored_events = self.store.get_events(run_id) if stored else []
        except Exception as exc:
            raise RunStoreUnavailable(safe_error(exc)) from exc
        if stored is None:
            return None

        record: dict[str, Any] = {}
        if isinstance(stored, dict):
            record.update(redact_secrets(stored))
        events_by_id: dict[str, dict[str, Any]] = {}
        for event in stored_events or []:
            if not isinstance(event, dict):
                continue
            event = redact_secrets(event)
            event_id = str(event.get("event_id") or event.get("id") or uuid.uuid4().hex)
            event.setdefault("event_id", event_id)
            event.setdefault("id", event_id)
            event.setdefault("timestamp", event.get("created_at"))
            events_by_id[event_id] = event
        events = sorted(
            events_by_id.values(),
            key=lambda event: (event.get("sequence", 0), event.get("created_at", "")),
        )
        record["events"] = events

        # Reports are persisted as independent events to stay under Firestore's
        # one-document size limit. Rebuild them when serving historical runs.
        reports = dict(record.get("reports") or {})
        for event in events:
            if event.get("type") == "report" and event.get("report_key"):
                reports[str(event["report_key"])] = event.get("content", "")
        record["reports"] = reports
        return record

    def list_runs(self, date_key: str | None = None) -> list[dict[str, Any]]:
        self._evict_expired_terminal_runs()
        try:
            stored_runs = self.store.list_runs(date_key)
        except Exception as exc:
            raise RunStoreUnavailable(safe_error(exc)) from exc

        by_id: dict[str, dict[str, Any]] = {}
        for record in stored_runs or []:
            if isinstance(record, dict) and record.get("run_id"):
                by_id[str(record["run_id"])] = redact_secrets(record)
        with self._lock:
            live_runs = copy.deepcopy(list(self._live.values()))
        for record in live_runs:
            if date_key and record.get("date_key") != date_key:
                continue
            run_id = str(record["run_id"])
            by_id.setdefault(run_id, {}).update(redact_secrets(record))

        summaries = []
        for record in by_id.values():
            summary = dict(record)
            summary.pop("events", None)
            # Full reports remain available from the detail endpoint.
            summary.pop("reports", None)
            summaries.append(summary)
        return sorted(summaries, key=lambda item: item.get("created_at", ""), reverse=True)

    def _worker(self, run_id: str, request: RunRequest) -> None:
        started: float | None = None
        try:
            with self._execution_lock:
                # Runtime duration measures actual execution, not time waiting
                # behind another process-global graph configuration.
                started = time.monotonic()
                self._update(
                    run_id,
                    status="running",
                    progress=1,
                    current_phase="Initializing graph",
                    started_at=utc_now(),
                )
                self._emit(
                    run_id,
                    event_type="status",
                    agent="System",
                    status="running",
                    message="TradingAgents graph execution started.",
                )
                self._execute_graph(run_id, request)
                self._complete(run_id, time.monotonic() - started)
        except Exception as exc:  # background boundary: persist a safe terminal state
            elapsed = time.monotonic() - started if started is not None else 0.0
            self._fail(run_id, exc, elapsed)
        finally:
            with self._lock:
                self._threads.pop(run_id, None)

    def _execute_graph(self, run_id: str, request: RunRequest) -> None:
        # Importing the trading graph pulls in pandas, LangChain, and every
        # agent definition. Keep the idle web/login process lean and pay that
        # cost only when a user actually starts an analysis.
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = build_graph_config(request)
        graph = TradingAgentsGraph(
            selected_analysts=request.analysts,
            debug=False,
            config=config,
        )
        graph.ticker = request.ticker

        self._update(run_id, progress=2, current_phase="Loading memory and instrument data")
        graph._resolve_pending_entries(request.ticker)
        past_context = graph.memory_log.get_past_context(request.ticker)
        instrument_context = graph.resolve_instrument_context(
            request.ticker, self._asset_type(request.ticker)
        )
        initial_state = graph.propagator.create_initial_state(
            request.ticker,
            request.analysis_date,
            asset_type=self._asset_type(request.ticker),
            past_context=past_context,
            instrument_context=instrument_context,
        )
        args = graph.propagator.get_graph_args()

        first_agent = ANALYST_AGENT_NAMES[request.analysts[0]]
        self._set_statuses(run_id, {first_agent: "running"}, phase="Analyst Team")
        self._emit(
            run_id,
            event_type="status",
            agent=first_agent,
            status="running",
            message=f"{first_agent} started the analysis.",
        )

        final_state: dict[str, Any] = {}
        seen_messages: set[str] = set()
        previous_reports: dict[str, str] = {}
        for chunk in graph.graph.stream(initial_state, **args):
            if not isinstance(chunk, dict):
                continue
            final_state.update(chunk)
            self._process_messages(run_id, chunk, seen_messages)
            self._process_reports(
                run_id,
                chunk,
                request=request,
                previous_reports=previous_reports,
            )

        final_decision = _text_content(final_state.get("final_trade_decision"))
        if not final_decision:
            raise RuntimeError("The graph finished without a final trade decision.")

        # Match TradingAgentsGraph.propagate()'s successful-run persistence.
        graph.curr_state = final_state
        graph._log_state(request.analysis_date, final_state)
        graph.memory_log.store_decision(
            ticker=request.ticker,
            trade_date=request.analysis_date,
            final_trade_decision=final_decision,
        )
        decision = graph.process_signal(final_decision)
        safe_decision = redact_secrets(decision)
        safe_final_decision = _bounded_text(final_decision, 200_000)
        with self._lock:
            record = self._live[run_id]
            record["decision"] = safe_decision
            record["reports"]["final_trade_decision"] = safe_final_decision
        self._update(run_id, decision=safe_decision)

    def _process_messages(
        self,
        run_id: str,
        chunk: dict[str, Any],
        seen_messages: set[str],
    ) -> None:
        with self._lock:
            current_agent = self._live[run_id].get("current_agent") or "System"
        for message in chunk.get("messages") or []:
            signature = _message_signature(message)
            if signature in seen_messages:
                continue
            seen_messages.add(signature)
            class_name = message.__class__.__name__
            content = _text_content(getattr(message, "content", None))
            if content and content != "Continue":
                event_type = "data" if class_name == "ToolMessage" else "message"
                agent = "Market Data" if event_type == "data" else current_agent
                self._emit(
                    run_id,
                    event_type=event_type,
                    agent=agent,
                    status="received" if event_type == "data" else "streaming",
                    message=_bounded_text(content, 12_000),
                )

            for tool_call in getattr(message, "tool_calls", None) or []:
                if isinstance(tool_call, dict):
                    name = tool_call.get("name", "tool")
                    arguments = tool_call.get("args", {})
                else:
                    name = getattr(tool_call, "name", "tool")
                    arguments = getattr(tool_call, "args", {})
                self._emit(
                    run_id,
                    event_type="tool",
                    agent=current_agent,
                    status="called",
                    message=f"Calling {name}",
                    data={"tool": name, "arguments": redact_secrets(arguments)},
                )

    def _process_reports(
        self,
        run_id: str,
        chunk: dict[str, Any],
        *,
        request: RunRequest,
        previous_reports: dict[str, str],
    ) -> None:
        discovered: dict[str, str] = {}
        for report_key in (
            "market_report",
            "sentiment_report",
            "news_report",
            "fundamentals_report",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
        ):
            content = _text_content(chunk.get(report_key))
            if content:
                discovered[report_key] = content

        debate = chunk.get("investment_debate_state") or {}
        for state_key, report_key in (
            ("bull_history", "bull_researcher"),
            ("bear_history", "bear_researcher"),
            ("judge_decision", "research_manager"),
        ):
            content = _text_content(debate.get(state_key))
            if content:
                discovered[report_key] = content

        risk = chunk.get("risk_debate_state") or {}
        for state_key, report_key in (
            ("aggressive_history", "aggressive_analyst"),
            ("conservative_history", "conservative_analyst"),
            ("neutral_history", "neutral_analyst"),
            ("judge_decision", "portfolio_manager"),
        ):
            content = _text_content(risk.get(state_key))
            if content:
                discovered[report_key] = content

        changed = {
            key: value for key, value in discovered.items() if previous_reports.get(key) != value
        }
        if not changed:
            return
        previous_reports.update(changed)
        bounded_changed = {key: _bounded_text(value, 200_000) for key, value in changed.items()}
        with self._lock:
            self._live[run_id]["reports"].update(bounded_changed)

        for report_key, content in bounded_changed.items():
            agent, label = REPORT_SPECS[report_key]
            self._emit(
                run_id,
                event_type="report",
                agent=agent,
                status="updated",
                message=f"{label} updated.",
                report_key=report_key,
                # Firestore documents are capped at 1 MiB. At four UTF-8 bytes
                # per character, 200k leaves room for metadata and field names.
                content=content,
            )

        status_updates: dict[str, str] = {}
        phase = "Analyst Team"
        current_agent: str | None = None

        for analyst in request.analysts:
            report_key = ANALYST_REPORT_KEYS[analyst]
            agent = ANALYST_AGENT_NAMES[analyst]
            if report_key in discovered:
                status_updates[agent] = "completed"
            elif current_agent is None:
                status_updates[agent] = "running"
                current_agent = agent
            else:
                status_updates.setdefault(agent, "pending")

        if debate:
            phase = "Research Debate"
            count = int(debate.get("count", 0) or 0)
            if discovered.get("bull_researcher"):
                status_updates["Bull Researcher"] = "completed"
                status_updates["Bear Researcher"] = "running"
                current_agent = "Bear Researcher"
            if discovered.get("bear_researcher"):
                status_updates["Bear Researcher"] = "completed"
                if count >= 2 * request.research_depth:
                    status_updates["Research Manager"] = "running"
                    current_agent = "Research Manager"
                else:
                    current_agent = "Bull Researcher"
            if discovered.get("research_manager") or discovered.get("investment_plan"):
                phase = "Research Decision"
                status_updates.update(
                    {
                        "Bull Researcher": "completed",
                        "Bear Researcher": "completed",
                        "Research Manager": "completed",
                        "Trader": "running",
                    }
                )
                current_agent = "Trader"

        if discovered.get("trader_investment_plan"):
            phase = "Trading Team"
            status_updates.update({"Trader": "completed", "Aggressive Analyst": "running"})
            current_agent = "Aggressive Analyst"

        if risk:
            phase = "Risk Management"
            count = int(risk.get("count", 0) or 0)
            if discovered.get("aggressive_analyst"):
                status_updates["Aggressive Analyst"] = "completed"
                status_updates["Conservative Analyst"] = "running"
                current_agent = "Conservative Analyst"
            if discovered.get("conservative_analyst"):
                status_updates["Conservative Analyst"] = "completed"
                status_updates["Neutral Analyst"] = "running"
                current_agent = "Neutral Analyst"
            if discovered.get("neutral_analyst"):
                status_updates["Neutral Analyst"] = "completed"
                if count >= 3 * request.research_depth:
                    status_updates["Portfolio Manager"] = "running"
                    current_agent = "Portfolio Manager"
                else:
                    current_agent = "Aggressive Analyst"
            if discovered.get("portfolio_manager") or discovered.get("final_trade_decision"):
                phase = "Portfolio Decision"
                status_updates.update(
                    {
                        "Aggressive Analyst": "completed",
                        "Conservative Analyst": "completed",
                        "Neutral Analyst": "completed",
                        "Portfolio Manager": "completed",
                    }
                )
                current_agent = "Portfolio Manager"

        self._set_statuses(
            run_id,
            status_updates,
            phase=phase,
            current_agent=current_agent,
        )

    def _set_statuses(
        self,
        run_id: str,
        statuses: dict[str, str],
        *,
        phase: str,
        current_agent: str | None = None,
    ) -> None:
        with self._lock:
            record = self._live[run_id]
            record["agent_status"].update(statuses)
            if current_agent:
                record["current_agent"] = current_agent
            completed = sum(status == "completed" for status in record["agent_status"].values())
            total = max(len(record["agent_status"]), 1)
            progress = max(record.get("progress", 0), min(95, int(completed / total * 95)))
            agent_status = copy.deepcopy(record["agent_status"])
        self._update(
            run_id,
            agent_status=agent_status,
            progress=progress,
            current_phase=phase,
            current_agent=current_agent,
        )

    def _complete(self, run_id: str, duration_seconds: float) -> None:
        with self._lock:
            statuses = dict.fromkeys(self._live[run_id]["agent_status"], "completed")
        completed_at = utc_now()
        self._update(
            run_id,
            status="completed",
            progress=100,
            current_phase="Completed",
            current_agent=None,
            agent_status=statuses,
            completed_at=completed_at,
            duration_seconds=round(duration_seconds, 2),
        )
        self._emit(
            run_id,
            event_type="status",
            agent="System",
            status="completed",
            message="TradingAgents analysis completed successfully.",
        )
        self._mark_terminal_cache(run_id)

    def _fail(self, run_id: str, exc: BaseException, duration_seconds: float) -> None:
        error = safe_error(exc)
        with self._lock:
            current_agent = self._live.get(run_id, {}).get("current_agent")
            statuses = copy.deepcopy(self._live.get(run_id, {}).get("agent_status", {}))
        if current_agent and current_agent in statuses:
            statuses[current_agent] = "error"
        self._update(
            run_id,
            status="failed",
            current_phase="Failed",
            agent_status=statuses,
            error=error,
            completed_at=utc_now(),
            duration_seconds=round(duration_seconds, 2),
        )
        self._emit(
            run_id,
            event_type="error",
            agent=current_agent or "System",
            status="failed",
            message=error,
        )
        self._mark_terminal_cache(run_id)

    def _update(self, run_id: str, **updates: Any) -> None:
        safe_updates = redact_secrets(updates)
        safe_updates["updated_at"] = utc_now()
        with self._lock:
            record = self._live.get(run_id)
            if record is None:
                return
            record.update(copy.deepcopy(safe_updates))
        # Reports and events live in event documents, not the size-limited run doc.
        persisted = {
            key: value for key, value in safe_updates.items() if key not in {"reports", "events"}
        }
        try:
            self.store.update_run(run_id, persisted)
        except Exception as exc:
            self._local_storage_warning(run_id, exc)

    def _emit(
        self,
        run_id: str,
        *,
        event_type: str,
        agent: str,
        status: str,
        message: str,
        **extra: Any,
    ) -> dict[str, Any]:
        with self._lock:
            sequence = self._sequences.get(run_id, 0) + 1
            self._sequences[run_id] = sequence
        event_id = uuid.uuid4().hex
        timestamp = utc_now()
        event = redact_secrets(
            {
                "event_id": event_id,
                "id": event_id,
                "run_id": run_id,
                "created_at": timestamp,
                "timestamp": timestamp,
                "sequence": sequence,
                "agent": agent,
                "type": event_type,
                "status": status,
                "message": message,
                **extra,
            }
        )
        with self._lock:
            self._events.setdefault(run_id, []).append(copy.deepcopy(event))
        try:
            self.store.append_event(run_id, copy.deepcopy(event))
        except Exception as exc:
            self._local_storage_warning(run_id, exc)
        return event

    def _local_storage_warning(self, run_id: str, exc: BaseException) -> None:
        """Record a non-recursive live warning when an individual write fails."""
        with self._lock:
            record = self._live.get(run_id)
            if record is None:
                return
            record["storage_warning"] = safe_error(exc)

    @staticmethod
    def _asset_type(ticker: str) -> str:
        return (
            "crypto"
            if ticker.upper().endswith(("-USD", "-USDT", "-USDC", "-BTC", "-ETH"))
            else "stock"
        )
