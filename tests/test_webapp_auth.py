from fastapi.testclient import TestClient

from tradingagents.webapp.main import create_app
from tradingagents.webapp.storage import LocalJsonRunStore


def _set_client_config(monkeypatch):
    monkeypatch.delenv("WEB_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("WEB_AUTH_ALLOWED_EMAILS", raising=False)
    monkeypatch.setenv("FIREBASE_WEB_API_KEY", "public-web-api-key")
    monkeypatch.setenv("FIREBASE_AUTH_DOMAIN", "tradingagents-test.firebaseapp.com")
    monkeypatch.setenv("FIREBASE_PROJECT_ID", "tradingagents-test")
    monkeypatch.setenv("FIREBASE_WEB_APP_ID", "1:123456789:web:abcdef")


def test_private_api_requires_valid_firebase_bearer_token(monkeypatch, tmp_path):
    _set_client_config(monkeypatch)

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
        create_app(
            LocalJsonRunStore(tmp_path),
            auth_required=True,
            token_verifier=verify,
        )
    )

    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["service"] == "tradingagents-api"
    assert client.get("/api/health").status_code == 200
    config = client.get("/api/auth/config")
    assert config.status_code == 200
    assert config.json()["configured"] is True
    assert config.json()["firebase"]["apiKey"] == "public-web-api-key"

    openapi = client.get("/api/openapi.json").json()
    assert openapi["components"]["securitySchemes"]["FirebaseBearer"] == {
        "type": "http",
        "description": "Firebase Authentication ID token issued to the standalone frontend.",
        "scheme": "bearer",
        "bearerFormat": "Firebase ID token",
    }
    assert openapi["paths"]["/api/options"]["get"]["security"] == [{"FirebaseBearer": []}]

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
    session = client.get("/api/auth/session", headers=headers)
    assert session.status_code == 200
    assert session.json()["user"] == {
        "uid": "firebase-user-1",
        "email": "analyst@example.com",
        "name": "Market Analyst",
        "picture": None,
        "email_verified": True,
    }


def test_server_email_allowlist_rejects_other_valid_firebase_users(monkeypatch, tmp_path):
    _set_client_config(monkeypatch)
    monkeypatch.setenv("WEB_AUTH_ALLOWED_EMAILS", "owner@example.com, teammate@example.com")
    client = TestClient(
        create_app(
            LocalJsonRunStore(tmp_path),
            auth_required=True,
            token_verifier=lambda _token: {
                "uid": "firebase-user-2",
                "email": "stranger@example.com",
            },
        )
    )

    response = client.get(
        "/api/history",
        headers={"Authorization": "Bearer otherwise-valid-token"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == ("This account is not authorized to access TradingAgents.")


def test_authentication_can_be_explicitly_disabled_for_local_development(tmp_path):
    client = TestClient(create_app(LocalJsonRunStore(tmp_path), auth_required=False))

    config = client.get("/api/auth/config")
    assert config.json()["required"] is False
    assert client.get("/api/options").status_code == 200
    session = client.get("/api/auth/session")
    assert session.json()["user"]["auth_disabled"] is True
