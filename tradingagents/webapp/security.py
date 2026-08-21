"""Server-side Firebase bearer authorization for analysis API calls."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


class AuthorizationError(Exception):
    """Base class for safe API authorization failures."""


class AuthorizationConfigurationError(AuthorizationError):
    """Raised when Firebase token verification is not configured."""


class InvalidAuthorizationToken(AuthorizationError):
    """Raised when a Firebase Bearer token cannot be verified."""


class AuthorizationForbidden(AuthorizationError):
    """Raised when a valid Firebase user is not allowed to launch analyses."""


TokenVerifier = Callable[[str], Mapping[str, Any]]


def _env_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def _allowed_emails() -> set[str]:
    raw = os.getenv("WEB_AUTH_ALLOWED_EMAILS", "")
    return {email.strip().casefold() for email in raw.split(",") if email.strip()}


class FirebaseBearerAuthorizer:
    """Verify frontend-issued Firebase ID tokens on analysis endpoints.

    Firebase sign-in and client configuration belong to the standalone
    frontend. This class does not create sessions or expose Firebase Web App
    configuration; it only protects backend operations that can consume local
    compute, LLM quota, or market-data quota.
    """

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

    def authorize(self, authorization: str | None) -> dict[str, Any]:
        if not self.required:
            return {"uid": "local-development", "email": None, "auth_disabled": True}
        if not authorization:
            raise InvalidAuthorizationToken("Authentication is required to access this resource.")

        scheme, separator, token = authorization.strip().partition(" ")
        if not separator or scheme.casefold() != "bearer" or not token.strip():
            raise InvalidAuthorizationToken("The Authorization header must use a Bearer token.")

        try:
            claims = dict(self._verifier()(token.strip()))
        except AuthorizationError:
            raise
        except Exception as exc:
            raise InvalidAuthorizationToken(
                "The Firebase session is invalid or has expired. Please sign in again."
            ) from exc

        uid = str(claims.get("uid") or claims.get("sub") or "").strip()
        if not uid:
            raise InvalidAuthorizationToken("The Firebase ID token does not contain a user ID.")
        email_value = claims.get("email")
        email = str(email_value).strip() if email_value else None
        if self._allowed and (not email or email.casefold() not in self._allowed):
            raise AuthorizationForbidden("This account is not authorized to access TradingAgents.")

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
            raise AuthorizationConfigurationError(
                "FIREBASE_CREDENTIALS_PATH is required to verify API authorization."
            )
        credential_path = Path(credential_value).expanduser().resolve()
        if not credential_path.is_file():
            raise AuthorizationConfigurationError(
                "The Firebase service-account file was not found on the server."
            )

        try:
            import firebase_admin
            from firebase_admin import auth, credentials

            project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
            identity = f"{credential_path}|{project_id}|authorization"
            app_name = (
                "tradingagents-api-authz-"
                + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
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
        except AuthorizationError:
            raise
        except Exception as exc:
            raise AuthorizationConfigurationError(
                "Firebase Admin SDK failed to initialize for API authorization."
            ) from exc


__all__ = [
    "AuthorizationConfigurationError",
    "AuthorizationForbidden",
    "FirebaseBearerAuthorizer",
    "InvalidAuthorizationToken",
    "TokenVerifier",
]
