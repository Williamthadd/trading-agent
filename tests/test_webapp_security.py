from fastapi.testclient import TestClient

from tradingagents.webapp.storage import LocalJsonRunStore


def _valid_run_payload() -> dict[str, object]:
    return {
        "ticker": "AAPL",
        "analysis_date": "2025-08-15",
        "analysts": ["market"],
        "research_depth": 1,
        "llm_provider": "google",
        "quick_model": "test-fast",
        "deep_model": "test-deep",
    }


def _create_app(monkeypatch, tmp_path, *args, **kwargs):
    monkeypatch.setenv("FIREBASE_ENABLED", "false")
    monkeypatch.setenv("WEB_RECONCILE_STALE_RUNS", "false")
    monkeypatch.setenv("WEB_LOCAL_DATA_DIR", str(tmp_path / "implicit-api-store"))
    from tradingagents.webapp.main import create_app

    return create_app(*args, **kwargs)


def test_analysis_api_requires_valid_firebase_bearer_token(monkeypatch, tmp_path):
    monkeypatch.delenv("WEB_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("WEB_AUTH_ALLOWED_EMAILS", raising=False)

    def verify(token):
        if token != "valid-id-token":
            raise ValueError("invalid token")
        return {
            "uid": "firebase-user-1",
            "email": "analyst@example.com",
            "name": "Market Analyst",
            "email_verified": True,
        }

    client = TestClient(
        _create_app(
            monkeypatch,
            tmp_path,
            LocalJsonRunStore(tmp_path),
            auth_required=True,
            token_verifier=verify,
        )
    )

    assert client.get("/").status_code == 200
    assert client.get("/api/health").status_code == 200

    openapi = client.get("/api/openapi.json").json()
    assert openapi["components"]["securitySchemes"]["FirebaseBearer"] == {
        "type": "http",
        "description": ("Firebase Authentication ID token issued to the standalone frontend."),
        "scheme": "bearer",
        "bearerFormat": "Firebase ID token",
    }
    assert openapi["paths"]["/api/options"]["get"]["security"] == [{"FirebaseBearer": []}]
    assert openapi["paths"]["/api/runs"]["post"]["security"] == [{"FirebaseBearer": []}]

    missing = client.get(
        "/api/options",
        headers={"Origin": "http://localhost:5173"},
    )
    assert missing.status_code == 401
    assert missing.headers["WWW-Authenticate"] == "Bearer"
    assert missing.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"

    invalid = client.get("/api/options", headers={"Authorization": "Bearer invalid"})
    assert invalid.status_code == 401
    assert "invalid token" not in invalid.text

    headers = {"Authorization": "Bearer valid-id-token"}
    assert client.get("/api/options", headers=headers).status_code == 200
    assert client.post("/api/runs", json=_valid_run_payload()).status_code == 401


def test_server_email_allowlist_rejects_other_valid_firebase_users(monkeypatch, tmp_path):
    monkeypatch.delenv("WEB_CORS_ORIGINS", raising=False)
    monkeypatch.setenv("WEB_AUTH_ALLOWED_EMAILS", "owner@example.com, teammate@example.com")
    client = TestClient(
        _create_app(
            monkeypatch,
            tmp_path,
            LocalJsonRunStore(tmp_path),
            auth_required=True,
            token_verifier=lambda _token: {
                "uid": "firebase-user-2",
                "email": "stranger@example.com",
            },
        )
    )

    response = client.get(
        "/api/options",
        headers={"Authorization": "Bearer otherwise-valid-token"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == ("This account is not authorized to access TradingAgents.")
    post_response = client.post(
        "/api/runs",
        json=_valid_run_payload(),
        headers={"Authorization": "Bearer otherwise-valid-token"},
    )
    assert post_response.status_code == 403


def test_authorized_firebase_user_can_launch_analysis(monkeypatch, tmp_path):
    monkeypatch.delenv("WEB_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("WEB_AUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")
    from tradingagents.webapp.runner import RunManager

    monkeypatch.setattr(RunManager, "_execute_graph", lambda *_args, **_kwargs: None)
    client = TestClient(
        _create_app(
            monkeypatch,
            tmp_path,
            LocalJsonRunStore(tmp_path),
            auth_required=True,
            token_verifier=lambda _token: {
                "uid": "firebase-user-1",
                "email": "analyst@example.com",
            },
        )
    )

    response = client.post(
        "/api/runs",
        json=_valid_run_payload(),
        headers={"Authorization": "Bearer valid-id-token"},
    )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"


def test_missing_admin_credentials_returns_safe_503(monkeypatch, tmp_path):
    monkeypatch.delenv("WEB_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("FIREBASE_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    client = TestClient(
        _create_app(
            monkeypatch,
            tmp_path,
            LocalJsonRunStore(tmp_path),
            auth_required=True,
        )
    )

    response = client.get(
        "/api/options",
        headers={"Authorization": "Bearer unverified-token"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "FIREBASE_CREDENTIALS_PATH is required to verify API authorization."
    )
    assert "unverified-token" not in response.text


def test_authorization_can_be_disabled_for_local_development(monkeypatch, tmp_path):
    client = TestClient(
        _create_app(
            monkeypatch,
            tmp_path,
            LocalJsonRunStore(tmp_path),
            auth_required=False,
        )
    )

    assert client.get("/api/options").status_code == 200


def test_frontend_auth_and_history_routes_are_not_exposed(monkeypatch, tmp_path):
    client = TestClient(
        _create_app(
            monkeypatch,
            tmp_path,
            LocalJsonRunStore(tmp_path),
            auth_required=False,
        )
    )

    removed_paths = (
        "/api/auth/config",
        "/api/auth/session",
        "/api/history",
        "/api/history/" + "a" * 32,
        "/api/runs/" + "a" * 32,
    )
    for path in removed_paths:
        assert client.get(path).status_code == 404

    openapi_paths = client.get("/api/openapi.json").json()["paths"]
    assert set(openapi_paths) == {"/api/health", "/api/options", "/api/runs"}
