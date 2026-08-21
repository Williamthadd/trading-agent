"""Firebase Authentication boundary for TradingAgents API clients."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


class AuthenticationError(Exception):
    """Base class for safe authentication failures returned by the API."""


class AuthenticationConfigurationError(AuthenticationError):
    """Raised when Firebase Authentication is required but not configured."""


class InvalidAuthenticationToken(AuthenticationError):
    """Raised when an Authorization header cannot be verified."""


class AuthenticationForbidden(AuthenticationError):
    """Raised when a valid Firebase user is not allowed to use this server."""


TokenVerifier = Callable[[str], Mapping[str, Any]]


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _client_config() -> tuple[dict[str, str], list[str]]:
    fields = {
        "apiKey": "FIREBASE_WEB_API_KEY",
        "authDomain": "FIREBASE_AUTH_DOMAIN",
        "projectId": "FIREBASE_PROJECT_ID",
        "appId": "FIREBASE_WEB_APP_ID",
        "messagingSenderId": "FIREBASE_MESSAGING_SENDER_ID",
        "storageBucket": "FIREBASE_STORAGE_BUCKET",
        "measurementId": "FIREBASE_MEASUREMENT_ID",
    }
    required = {"apiKey", "authDomain", "projectId", "appId"}
    config: dict[str, str] = {}
    missing: list[str] = []
    for public_name, environment_name in fields.items():
        value = os.getenv(environment_name, "").strip()
        if value:
            config[public_name] = value
        elif public_name in required:
            missing.append(environment_name)
    return config, missing


def _allowed_emails() -> set[str]:
    raw = os.getenv("WEB_AUTH_ALLOWED_EMAILS", "")
    return {email.strip().casefold() for email in raw.split(",") if email.strip()}


class FirebaseAuthManager:
    """Expose public client config and verify Firebase ID tokens server-side."""

    def __init__(
        self,
        *,
        required: bool | None = None,
        token_verifier: TokenVerifier | None = None,
    ) -> None:
        self.required = (
            _env_bool("WEB_AUTH_REQUIRED", default=True) if required is None else required
        )
        self._injected_verifier = token_verifier
        self._firebase_verifier: TokenVerifier | None = None
        self._allowed = _allowed_emails()
        self._config, self._missing = _client_config()
        if self.required and token_verifier is None:
            credential_value = (
                os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip()
                or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
            )
            if not credential_value or not Path(credential_value).expanduser().resolve().is_file():
                self._missing.append("FIREBASE_CREDENTIALS_PATH")

    @property
    def public_config(self) -> dict[str, Any]:
        return {
            "required": self.required,
            "configured": not self._missing,
            "firebase": dict(self._config) if not self._missing else {},
            "missing": list(self._missing),
            "access_restricted": bool(self._allowed),
        }

    def authenticate(self, authorization: str | None) -> dict[str, Any]:
        if not self.required:
            return {"uid": "local-development", "email": None, "auth_disabled": True}
        if self._missing:
            raise AuthenticationConfigurationError(
                "Firebase Authentication is not fully configured on the server."
            )
        if not authorization:
            raise InvalidAuthenticationToken("Authentication is required to access this resource.")

        scheme, separator, token = authorization.strip().partition(" ")
        if not separator or scheme.casefold() != "bearer" or not token.strip():
            raise InvalidAuthenticationToken("The Authorization header must use a Bearer token.")

        try:
            claims = dict(self._verifier()(token.strip()))
        except AuthenticationError:
            raise
        except Exception as exc:
            raise InvalidAuthenticationToken(
                "The Firebase session is invalid or has expired. Please sign in again."
            ) from exc

        uid = str(claims.get("uid") or claims.get("sub") or "").strip()
        if not uid:
            raise InvalidAuthenticationToken("The Firebase ID token does not contain a user ID.")
        email_value = claims.get("email")
        email = str(email_value).strip() if email_value else None
        if self._allowed and (not email or email.casefold() not in self._allowed):
            raise AuthenticationForbidden("This account is not authorized to access TradingAgents.")

        return {
            "uid": uid,
            "email": email,
            "name": str(claims.get("name") or "").strip() or None,
            "picture": str(claims.get("picture") or "").strip() or None,
            "email_verified": bool(claims.get("email_verified", False)),
        }

    def _verifier(self) -> TokenVerifier:
        if self._injected_verifier is not None:
            return self._injected_verifier
        if self._firebase_verifier is not None:
            return self._firebase_verifier

        credential_value = (
            os.getenv("FIREBASE_CREDENTIALS_PATH", "").strip()
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        )
        if not credential_value:
            raise AuthenticationConfigurationError(
                "FIREBASE_CREDENTIALS_PATH is required to verify authentication."
            )
        credential_path = Path(credential_value).expanduser().resolve()
        if not credential_path.is_file():
            raise AuthenticationConfigurationError(
                "The Firebase service-account file was not found on the server."
            )

        try:
            import firebase_admin
            from firebase_admin import auth, credentials

            project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
            identity = f"{credential_path}|{project_id}|auth"
            app_name = (
                "tradingagents-auth-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
            )
            try:
                app = firebase_admin.get_app(app_name)
            except ValueError:
                options = {"projectId": project_id} if project_id else None
                app = firebase_admin.initialize_app(
                    credentials.Certificate(str(credential_path)),
                    options=options,
                    name=app_name,
                )

            def verify(token: str) -> Mapping[str, Any]:
                return auth.verify_id_token(token, app=app)

            self._firebase_verifier = verify
            return verify
        except AuthenticationError:
            raise
        except Exception as exc:
            raise AuthenticationConfigurationError(
                "Firebase Admin SDK failed to initialize for Authentication."
            ) from exc


__all__ = [
    "AuthenticationConfigurationError",
    "AuthenticationForbidden",
    "FirebaseAuthManager",
    "InvalidAuthenticationToken",
]
