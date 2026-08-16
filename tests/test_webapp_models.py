import pytest
from pydantic import ValidationError

from tradingagents.webapp.models import RunRequest


def valid_request(**updates):
    payload = {
        "ticker": "AAPL",
        "analysis_date": "2025-08-15",
        "analysts": ["market", "news"],
        "research_depth": 1,
        "llm_provider": "openai",
        "quick_model": "gpt-5.4-mini",
        "deep_model": "gpt-5.5",
        "reasoning_effort": "medium",
    }
    payload.update(updates)
    return payload


def test_run_request_normalizes_ticker_and_analyst_order():
    request = RunRequest.model_validate(
        valid_request(ticker=" btcusd ", analysts=["news", "market"])
    )

    assert request.ticker == "BTC-USD"
    assert request.analysts == ["market", "news"]


def test_run_request_accepts_a_trailing_broker_qualifier():
    request = RunRequest.model_validate(valid_request(ticker="XAUUSD+"))

    assert request.ticker == "GC=F"


def test_run_request_rejects_fundamentals_for_crypto():
    with pytest.raises(ValidationError, match="fundamentals analyst"):
        RunRequest.model_validate(
            valid_request(ticker="BTC-USD", analysts=["market", "fundamentals"])
        )


def test_run_request_requires_real_custom_model_id():
    with pytest.raises(ValidationError, match="actual model ID"):
        RunRequest.model_validate(valid_request(quick_model="custom"))


def test_openai_compatible_provider_allows_server_configured_backend_url():
    request = RunRequest.model_validate(
        valid_request(
            llm_provider="openai_compatible",
            quick_model="local-fast",
            deep_model="local-deep",
            reasoning_effort=None,
        )
    )

    assert request.backend_url is None


def test_hosted_provider_rejects_request_level_backend_url():
    with pytest.raises(ValidationError, match="accepted only for ollama or openai_compatible"):
        RunRequest.model_validate(valid_request(backend_url="https://proxy.example.com/v1"))


@pytest.mark.parametrize("provider", ["ollama", "openai_compatible"])
def test_custom_runtime_provider_accepts_safe_backend_url(provider):
    request = RunRequest.model_validate(
        valid_request(
            llm_provider=provider,
            quick_model="local-fast",
            deep_model="local-deep",
            reasoning_effort=None,
            backend_url="http://localhost:11434/v1/",
        )
    )

    assert request.backend_url == "http://localhost:11434/v1"


@pytest.mark.parametrize(
    "backend_url",
    [
        "https://user:secret@example.com/v1",
        "https://example.com/v1?api_key=secret",
        "https://example.com/v1#secret",
    ],
)
def test_backend_url_rejects_embedded_credentials_and_tokens(backend_url):
    with pytest.raises(
        ValidationError,
        match="cannot contain credentials, query parameters, or a fragment",
    ):
        RunRequest.model_validate(
            valid_request(
                llm_provider="ollama",
                quick_model="local-fast",
                deep_model="local-deep",
                reasoning_effort=None,
                backend_url=backend_url,
            )
        )
