import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import tradingagents.webapp.runner as web_runner
from tradingagents.webapp.models import RunRequest
from tradingagents.webapp.runner import (
    RunManager,
    RunQueueFull,
    RuntimeConfigurationError,
    build_graph_config,
    redact_secrets,
    safe_error,
)
from tradingagents.webapp.storage import LocalJsonRunStore


def _fake_execute_graph(self, run_id, request):
    report = f"Synthetic market report for {request.ticker}."
    with self._lock:
        self._live[run_id]["reports"]["market_report"] = report
    self._emit(
        run_id,
        event_type="report",
        agent="Market Analyst",
        status="updated",
        message="Market Analysis updated.",
        report_key="market_report",
        content=report,
    )
    self._update(run_id, decision={"action": "BUY", "summary": "Synthetic test result."})


def test_secret_redaction_preserves_non_secret_key_fields():
    value = redact_secrets(
        {
            "date_key": "2026-08-16",
            "report_key": "market_report",
            "OPENAI_API_KEY": "sk-example-secret-value",
        }
    )

    assert value["date_key"] == "2026-08-16"
    assert value["report_key"] == "market_report"
    assert value["OPENAI_API_KEY"] == "[REDACTED]"


def test_secret_redaction_reuses_environment_snapshot(monkeypatch):
    monkeypatch.setenv("INTERNAL_API_KEY", "environment-only-secret")

    value = redact_secrets(
        {"items": [{"message": "failed with environment-only-secret"} for _ in range(20)]}
    )

    assert all(item["message"] == "failed with [REDACTED]" for item in value["items"])


def test_importing_web_runner_does_not_eagerly_import_trading_graph():
    command = (
        "import sys; import tradingagents.webapp.runner; "
        "assert 'tradingagents.graph.trading_graph' not in sys.modules"
    )

    completed = subprocess.run(
        [sys.executable, "-c", command],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stderr


def test_safe_error_redacts_url_credentials_query_and_fragment():
    message = safe_error(
        RuntimeError(
            "connect failed: https://alice:s3cr3t@private.example/v1?token=server-only#debug"
        )
    )

    assert "private.example/v1" in message
    assert "alice" not in message
    assert "s3cr3t" not in message
    assert "server-only" not in message
    assert "debug" not in message


def test_cors_origins_are_exact_and_normalized(monkeypatch, tmp_path):
    monkeypatch.setenv("FIREBASE_ENABLED", "false")
    monkeypatch.setenv("WEB_LOCAL_DATA_DIR", str(tmp_path / "cors-import-store"))
    monkeypatch.setenv("WEB_RECONCILE_STALE_RUNS", "false")
    monkeypatch.setenv(
        "WEB_CORS_ORIGINS",
        "http://localhost:3000/, https://frontend.example, http://localhost:3000",
    )

    from tradingagents.webapp.main import _cors_origins

    assert _cors_origins() == ["http://localhost:3000", "https://frontend.example"]


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "localhost:5173",
        "http://user:password@localhost:5173",
        "http://localhost:5173/path",
        "http://localhost:5173?token=secret",
        "http://localhost:5173#fragment",
        "http://localhost:99999",
    ],
)
def test_cors_origins_reject_unsafe_values(monkeypatch, tmp_path, value):
    monkeypatch.setenv("FIREBASE_ENABLED", "false")
    monkeypatch.setenv("WEB_LOCAL_DATA_DIR", str(tmp_path / "cors-import-store"))
    monkeypatch.setenv("WEB_RECONCILE_STALE_RUNS", "false")
    monkeypatch.setenv("WEB_CORS_ORIGINS", "http://localhost:5173")

    from tradingagents.webapp.main import _cors_origins

    monkeypatch.setenv("WEB_CORS_ORIGINS", value)

    with pytest.raises(RuntimeConfigurationError, match="WEB_CORS_ORIGINS"):
        _cors_origins()


def test_create_app_validates_cors_before_constructing_run_manager(monkeypatch, tmp_path):
    monkeypatch.setenv("FIREBASE_ENABLED", "false")
    monkeypatch.setenv("WEB_LOCAL_DATA_DIR", str(tmp_path / "cors-import-store"))
    monkeypatch.setenv("WEB_RECONCILE_STALE_RUNS", "false")
    monkeypatch.setenv("WEB_CORS_ORIGINS", "http://localhost:5173")

    import tradingagents.webapp.main as web_main

    constructed = False

    def unexpected_manager(_store):
        nonlocal constructed
        constructed = True
        raise AssertionError("RunManager must not be constructed for invalid CORS")

    monkeypatch.setattr(web_main, "RunManager", unexpected_manager)
    monkeypatch.setenv("WEB_CORS_ORIGINS", "*")

    with pytest.raises(RuntimeConfigurationError, match="WEB_CORS_ORIGINS"):
        web_main.create_app(object(), auth_required=False)

    assert constructed is False


def test_run_manager_reconciles_interrupted_run(tmp_path):
    store = LocalJsonRunStore(tmp_path)
    store.create_run({"run_id": "stale-run", "status": "running", "progress": 42})

    RunManager(store)

    run = store.get_run("stale-run")
    assert run["status"] == "failed"
    assert run["current_phase"] == "Interrupted"
    assert "server stopped" in run["error"]
    assert store.get_events("stale-run")[-1]["type"] == "error"


def test_reconciliation_uses_status_query_instead_of_full_history(monkeypatch, tmp_path):
    store = LocalJsonRunStore(tmp_path)
    store.create_run({"run_id": "finished-run", "status": "completed"})
    store.create_run({"run_id": "stale-run", "status": "running"})

    def fail_full_scan(_date_key=None):
        raise AssertionError("startup must not scan all historical runs")

    monkeypatch.setattr(store, "list_runs", fail_full_scan)

    RunManager(store)

    assert store.get_run("finished-run")["status"] == "completed"
    assert store.get_run("stale-run")["status"] == "failed"


def test_run_manager_can_disable_stale_run_reconciliation(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_RECONCILE_STALE_RUNS", "false")
    store = LocalJsonRunStore(tmp_path)
    store.create_run({"run_id": "externally-owned", "status": "running", "progress": 42})

    RunManager(store)

    run = store.get_run("externally-owned")
    assert run["status"] == "running"
    assert run["progress"] == 42
    assert store.get_events("externally-owned") == []


def test_run_manager_rejects_when_bounded_queue_is_full(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_RUN_QUEUE_LIMIT", "1")
    manager = RunManager(LocalJsonRunStore(tmp_path))
    manager._live["existing"] = {"status": "running"}
    request = RunRequest.model_validate(
        {
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "ollama",
            "quick_model": "test-fast",
            "deep_model": "test-deep",
        }
    )

    with pytest.raises(RunQueueFull, match="queue is full"):
        manager.start_run(request)


def test_queue_reservation_blocks_a_concurrent_submission(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_RUN_QUEUE_LIMIT", "1")
    store = LocalJsonRunStore(tmp_path)
    manager = RunManager(store)
    request = RunRequest.model_validate(
        {
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "ollama",
            "quick_model": "test-fast",
            "deep_model": "test-deep",
        }
    )
    create_entered = threading.Event()
    release_create = threading.Event()
    original_create = store.create_run

    def blocking_create(record):
        create_entered.set()
        assert release_create.wait(timeout=2)
        return original_create(record)

    monkeypatch.setattr(store, "create_run", blocking_create)
    outcome = {}

    def submit_first():
        try:
            outcome["run"] = manager.start_run(request)
        except Exception as exc:  # pragma: no cover - asserted below
            outcome["error"] = exc

    first = threading.Thread(target=submit_first)
    first.start()
    assert create_entered.wait(timeout=2)
    assert manager._reservations == 1
    monkeypatch.setattr(web_runner.threading.Thread, "start", lambda _thread: None)

    with pytest.raises(RunQueueFull, match="queue is full"):
        manager.start_run(request)

    release_create.set()
    first.join(timeout=2)
    assert not first.is_alive()
    assert "error" not in outcome
    assert outcome["run"]["status"] == "queued"
    assert manager._reservations == 0
    assert len(store.list_runs()) == 1


def test_terminal_run_cache_expires_and_falls_back_to_persisted_data(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_LIVE_CACHE_TTL_SECONDS", "0")
    store = LocalJsonRunStore(tmp_path)
    run_id = "a" * 32
    store.create_run(
        {
            "run_id": run_id,
            "status": "completed",
            "date_key": "2026-08-16",
            "decision": "Buy",
        }
    )
    store.append_event(
        run_id,
        {
            "event_id": "persisted-report",
            "sequence": 1,
            "type": "report",
            "report_key": "market_report",
            "content": "Persisted market report",
        },
    )
    manager = RunManager(store)
    manager._live[run_id] = {
        "run_id": run_id,
        "status": "completed",
        "reports": {"market_report": "Live-only report"},
    }
    manager._events[run_id] = []
    manager._sequences[run_id] = 99
    manager._mark_terminal_cache(run_id)

    detail = manager.get_run(run_id)

    assert run_id not in manager._live
    assert run_id not in manager._events
    assert run_id not in manager._sequences
    assert run_id not in manager._cache_deadlines
    assert detail["status"] == "completed"
    assert detail["reports"]["market_report"] == "Persisted market report"


def test_live_poll_uses_pre_sanitized_cache_without_reprocessing(monkeypatch, tmp_path):
    manager = RunManager(LocalJsonRunStore(tmp_path))
    run_id = "b" * 32
    manager._live[run_id] = {
        "run_id": run_id,
        "status": "running",
        "reports": {"market_report": "Safe cached report"},
    }
    manager._events[run_id] = [
        {
            "event_id": "safe-event",
            "sequence": 1,
            "created_at": "2026-08-17T00:00:00Z",
            "message": "Safe cached event",
        }
    ]

    def fail_reprocessing(_value):
        raise AssertionError("live polling should not redact the full cache again")

    monkeypatch.setattr(web_runner, "redact_secrets", fail_reprocessing)

    detail = manager.get_run(run_id)

    assert detail["reports"]["market_report"] == "Safe cached report"
    assert detail["events"][0]["message"] == "Safe cached event"


def test_web_api_returns_429_when_run_queue_is_full(monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_RUN_QUEUE_LIMIT", "1")
    monkeypatch.setenv("WEB_HOST", "127.0.0.1")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")

    from tradingagents.webapp.main import create_app

    store = LocalJsonRunStore(tmp_path)
    app = create_app(store, auth_required=False)
    app.state.run_manager._live["occupied"] = {"status": "running"}
    client = TestClient(app)

    response = client.post(
        "/api/runs",
        json={
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "google",
            "quick_model": "test-fast",
            "deep_model": "test-deep",
        },
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "5"
    assert "queue is full" in response.json()["detail"]
    assert store.list_runs() == []


def test_configured_backend_url_is_the_only_custom_url_allowed_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://approved.internal:11434/v1/")
    monkeypatch.delenv("WEB_ALLOW_CUSTOM_BACKEND_URLS", raising=False)
    manager = RunManager(LocalJsonRunStore(tmp_path))
    base_payload = {
        "ticker": "AAPL",
        "analysis_date": "2025-08-15",
        "analysts": ["market"],
        "research_depth": 1,
        "llm_provider": "ollama",
        "quick_model": "test-fast",
        "deep_model": "test-deep",
    }
    approved = RunRequest.model_validate(
        {**base_payload, "backend_url": "http://approved.internal:11434/v1"}
    )
    unapproved = RunRequest.model_validate(
        {**base_payload, "backend_url": "http://unapproved.internal:11434/v1"}
    )

    manager.validate_runtime(approved)
    with pytest.raises(RuntimeConfigurationError, match="not approved by the server"):
        manager.validate_runtime(unapproved)

    monkeypatch.setenv("WEB_ALLOW_CUSTOM_BACKEND_URLS", "true")
    manager.validate_runtime(unapproved)


def test_openai_compatible_uses_hidden_server_url_without_browser_leak(monkeypatch, tmp_path):
    monkeypatch.setitem(web_runner.DEFAULT_CONFIG, "llm_provider", "openai_compatible")
    monkeypatch.setitem(
        web_runner.DEFAULT_CONFIG,
        "backend_url",
        "https://user:secret@private.example/v1?token=server-only",
    )
    manager = RunManager(LocalJsonRunStore(tmp_path))
    request = RunRequest.model_validate(
        {
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai_compatible",
            "quick_model": "private-fast",
            "deep_model": "private-deep",
        }
    )

    manager.validate_runtime(request)

    from tradingagents.webapp.main import _provider_options

    providers = _provider_options()
    assert [provider["id"] for provider in providers] == ["google", "ollama"]
    assert "secret" not in repr(providers)


def test_openai_compatible_without_any_endpoint_fails_at_runtime(monkeypatch, tmp_path):
    monkeypatch.setitem(web_runner.DEFAULT_CONFIG, "llm_provider", "openai")
    monkeypatch.setitem(web_runner.DEFAULT_CONFIG, "backend_url", "https://api.openai.com/v1")
    manager = RunManager(LocalJsonRunStore(tmp_path))
    request = RunRequest.model_validate(
        {
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai_compatible",
            "quick_model": "local-fast",
            "deep_model": "local-deep",
        }
    )

    with pytest.raises(RuntimeConfigurationError, match="needs a backend URL"):
        manager.validate_runtime(request)


def test_switching_provider_does_not_inherit_private_default_endpoint(monkeypatch):
    private_url = "https://user:secret@private.example/v1?token=server-only"
    monkeypatch.setitem(web_runner.DEFAULT_CONFIG, "llm_provider", "openai_compatible")
    monkeypatch.setitem(web_runner.DEFAULT_CONFIG, "backend_url", private_url)
    hosted_request = RunRequest.model_validate(
        {
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
        }
    )
    private_request = RunRequest.model_validate(
        {
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai_compatible",
            "quick_model": "private-fast",
            "deep_model": "private-deep",
        }
    )

    assert build_graph_config(hosted_request)["backend_url"] is None
    assert build_graph_config(private_request)["backend_url"] == private_url


def test_thread_start_failure_marks_persisted_run_failed(monkeypatch, tmp_path):
    store = LocalJsonRunStore(tmp_path)
    manager = RunManager(store)
    request = RunRequest.model_validate(
        {
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "ollama",
            "quick_model": "test-fast",
            "deep_model": "test-deep",
        }
    )

    def fail_to_start(_thread):
        raise OSError("worker creation refused")

    monkeypatch.setattr(web_runner.threading.Thread, "start", fail_to_start)

    with pytest.raises(RuntimeConfigurationError, match="Unable to start"):
        manager.start_run(request)

    runs = store.list_runs()
    assert len(runs) == 1
    run = runs[0]
    assert run["status"] == "failed"
    assert run["current_phase"] == "Failed"
    assert run["error"] == "worker creation refused"
    assert manager.active_count == 0
    assert manager._threads == {}
    assert run["run_id"] in manager._cache_deadlines
    events = store.get_events(run["run_id"])
    assert [event["type"] for event in events] == ["status", "error"]
    assert events[-1]["message"] == "worker creation refused"


def test_web_api_runs_mock_graph_and_returns_daily_history(monkeypatch, tmp_path):
    monkeypatch.setenv("FIREBASE_ENABLED", "false")
    monkeypatch.delenv("WEB_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("WEB_LOCAL_DATA_DIR", str(tmp_path / "implicit-store"))
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    monkeypatch.setattr(RunManager, "_execute_graph", _fake_execute_graph)

    # Import after WEB_LOCAL_DATA_DIR is isolated because the module also exports
    # a ready-to-run global ASGI app.
    from tradingagents.webapp.main import _public_backend_url, create_app

    assert _public_backend_url("https://example.com/v1/") == "https://example.com/v1"
    assert _public_backend_url("https://user:secret@example.com/v1") is None
    assert _public_backend_url("https://example.com/v1?api_key=secret") is None

    store = LocalJsonRunStore(tmp_path / "api-store")
    client = TestClient(create_app(store, auth_required=False))

    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["service"] == "tradingagents-api"
    assert health.json()["storage"]["backend"] == "local-json"

    preflight = client.options(
        "/api/options",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
    assert "Authorization" in preflight.headers["Access-Control-Allow-Headers"]

    rejected_preflight = client.options(
        "/api/options",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert rejected_preflight.status_code == 400
    assert "Access-Control-Allow-Origin" not in rejected_preflight.headers

    cors_health = client.get(
        "/api/health",
        headers={"Origin": "http://127.0.0.1:5173"},
    )
    assert cors_health.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    assert "Origin" in cors_health.headers["Vary"]
    assert "Retry-After" in cors_health.headers["Access-Control-Expose-Headers"]
    assert "WWW-Authenticate" in cors_health.headers["Access-Control-Expose-Headers"]

    denied_cors_health = client.get(
        "/api/health",
        headers={"Origin": "https://untrusted.example"},
    )
    assert denied_cors_health.status_code == 200
    assert "Access-Control-Allow-Origin" not in denied_cors_health.headers

    options = client.get("/api/options")
    assert options.status_code == 200
    providers = {provider["id"]: provider for provider in options.json()["providers"]}
    assert list(providers) == ["google", "ollama"]
    assert providers["google"]["label"] == "Google Gemini"
    assert providers["google"]["supports_backend_url"] is False
    assert providers["ollama"]["label"] == "Llama 3.2 3B (Local / Ollama)"
    assert providers["ollama"]["supports_backend_url"] is False
    assert providers["ollama"]["requires_backend_url"] is False
    assert providers["ollama"]["quick_models"] == [
        {
            "id": "tradingagents-llama3.2:16k",
            "label": "Llama 3.2 3B 16K - Local via Ollama",
            "custom": False,
        }
    ]
    assert providers["ollama"]["deep_models"] == providers["ollama"]["quick_models"]
    assert "thinking_control" not in providers["ollama"]
    assert "backend_url" not in providers["ollama"]
    assert options.json()["defaults"]["llm_provider"] == "google"
    assert options.json()["defaults"]["quick_model"].startswith("gemini-")
    assert options.json()["defaults"]["deep_model"].startswith("gemini-")

    response = client.post(
        "/api/runs",
        json={
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "output_language": "Bahasa Indonesia",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "google",
            "quick_model": "test-fast",
            "deep_model": "test-deep",
            "thinking_level": "minimal",
        },
    )
    assert response.status_code == 202
    run_id = response.json()["run_id"]

    detail = None
    for _ in range(50):
        detail_response = client.get(f"/api/runs/{run_id}")
        assert detail_response.status_code == 200
        detail = detail_response.json()
        if detail["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)

    assert detail is not None
    assert detail["status"] == "completed"
    assert detail["reports"]["market_report"].startswith("Synthetic")
    report_events = [event for event in detail["events"] if event["type"] == "report"]
    assert report_events[0]["report_key"] == "market_report"
    assert detail["decision"]["action"] == "BUY"

    # A live run is served entirely from memory, avoiding repeated Firestore
    # document/subcollection reads on every browser polling interval.
    monkeypatch.setattr(store, "get_run", lambda _run_id: (_ for _ in ()).throw(AssertionError))
    monkeypatch.setattr(store, "get_events", lambda _run_id: (_ for _ in ()).throw(AssertionError))
    assert client.get(f"/api/runs/{run_id}").status_code == 200

    history = client.get("/api/history", params={"date": detail["date_key"]})
    assert history.status_code == 200
    assert history.json()["count"] == 1
    assert history.json()["runs"][0]["run_id"] == run_id

    index = client.get("/")
    assert index.status_code == 200
    assert index.headers["content-type"].startswith("application/json")
    assert index.json() == {
        "service": "tradingagents-api",
        "status": "ok",
        "health": "/api/health",
        "docs": "/api/docs",
        "message": "The frontend is a separate application; this process serves the backend API only.",
    }
    for removed_asset in (
        "/index.html",
        "/app.js",
        "/auth.js",
        "/report-markdown.js",
        "/styles.css",
        "/logo.png",
    ):
        assert client.get(removed_asset).status_code == 404


def test_web_api_accepts_local_llama_without_google_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setattr(RunManager, "_execute_graph", _fake_execute_graph)

    from tradingagents.webapp.main import create_app

    store = LocalJsonRunStore(tmp_path)
    client = TestClient(create_app(store, auth_required=False))

    response = client.post(
        "/api/runs",
        json={
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "ollama",
            "quick_model": "tradingagents-llama3.2:16k",
            "deep_model": "tradingagents-llama3.2:16k",
        },
    )

    assert response.status_code == 202
    run_id = response.json()["run_id"]
    for _ in range(50):
        detail = client.get(f"/api/runs/{run_id}").json()
        if detail["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)

    assert detail["status"] == "completed"
    assert detail["llm_provider"] == "ollama"
    assert detail["quick_model"] == "tradingagents-llama3.2:16k"
    assert detail["deep_model"] == "tradingagents-llama3.2:16k"
    assert detail["thinking_level"] is None


def test_web_api_rejects_another_model_for_local_provider(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")

    from tradingagents.webapp.main import create_app

    store = LocalJsonRunStore(tmp_path)
    client = TestClient(create_app(store, auth_required=False))

    response = client.post(
        "/api/runs",
        json={
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "ollama",
            "quick_model": "llama3.2:latest",
            "deep_model": "llama3.2:latest",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "The local API provider requires the TradingAgents Llama 3.2 "
        "16K model for both the quick and deep model."
    )
    assert store.list_runs() == []


def test_local_llama_modelfile_pins_a_16k_context():
    model_file = Path(__file__).parents[1] / "ollama" / "llama3.2-16k.Modelfile"
    content = model_file.read_text(encoding="utf-8")

    assert "FROM llama3.2:latest" in content
    assert "PARAMETER num_ctx 16384" in content


def test_web_api_rejects_a_third_provider_before_runtime_validation(tmp_path):
    from tradingagents.webapp.main import create_app

    store = LocalJsonRunStore(tmp_path)
    client = TestClient(create_app(store, auth_required=False))

    response = client.post(
        "/api/runs",
        json={
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "openai",
            "quick_model": "gpt-5.4-mini",
            "deep_model": "gpt-5.5",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == (
        "The TradingAgents API supports only Google Gemini and "
        "Llama 3.2 3B through the local Ollama server."
    )
    assert store.list_runs() == []


def test_local_llama_graph_config_uses_server_side_ollama_endpoint(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")
    request = RunRequest.model_validate(
        {
            "ticker": "AAPL",
            "analysis_date": "2025-08-15",
            "analysts": ["market"],
            "research_depth": 1,
            "llm_provider": "ollama",
            "quick_model": "tradingagents-llama3.2:16k",
            "deep_model": "tradingagents-llama3.2:16k",
        }
    )

    config = build_graph_config(request)

    assert config["llm_provider"] == "ollama"
    assert config["quick_think_llm"] == "tradingagents-llama3.2:16k"
    assert config["deep_think_llm"] == "tradingagents-llama3.2:16k"
    assert config["backend_url"] == "http://127.0.0.1:11434/v1"
