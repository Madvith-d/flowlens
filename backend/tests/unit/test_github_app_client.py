"""Unit tests for the real (httpx) GitHub App client wiring.

The integration suite uses `MockGitHubAppClient`; these tests exercise
`HttpxGitHubAppClient` itself against an in-process httpx `MockTransport`, so
the requests it actually sends (URL, query params, JSON body) are verified
without any network access. Regression guard for Phase 3A:

- `build_installation_token` must send its JSON body (`permissions`,
  `repository_ids`); it previously constructed the body and silently dropped
  it, so installation tokens were never repository-scoped.
- Settings must accept PEM private keys with literal ``\\n`` escapes, as
  documented in `.env.example`.
"""

import json

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app.core.config import Settings
from app.services.github.app_client import (
    HttpxGitHubAppClient,
    INSTALLATION_TOKEN_REJECTED,
    sign_app_jwt,
)

APP_ID = 1234567
INSTALLATION_ID = 4242
REPOSITORY_ID = 99


@pytest.fixture()
def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert isinstance(key, RSAPrivateKey)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


@pytest.fixture()
def settings(private_key_pem: str) -> Settings:
    return Settings(
        github_app_id=APP_ID,
        github_app_slug="flowlens-test",
        github_app_client_id="Iv1.test",
        github_app_client_secret="secret",
        github_app_private_key=private_key_pem,
    )


def test_build_installation_token_sends_repository_scoping_body(settings: Settings) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == f"/app/installations/{INSTALLATION_ID}/access_tokens":
            return httpx.Response(
                201, json={"token": "ghs_test", "expires_at": "2030-01-01T00:00:00Z"}
            )
        return httpx.Response(404, json={"message": "unexpected path"})

    import app.services.github.app_client as app_client_module

    client = HttpxGitHubAppClient(settings)
    original_client_cls = app_client_module.httpx.Client
    app_client_module.httpx.Client = lambda **kwargs: original_client_cls(
        transport=httpx.MockTransport(handler), **kwargs
    )
    try:
        token = client.build_installation_token(INSTALLATION_ID, repository_ids=[REPOSITORY_ID])
    finally:
        app_client_module.httpx.Client = original_client_cls

    assert token.token == "ghs_test"

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == f"/app/installations/{INSTALLATION_ID}/access_tokens"
    # The body must actually be transmitted (regression: previously dropped).
    body = json.loads(request.content)
    assert body["repository_ids"] == [REPOSITORY_ID]
    assert body["permissions"] == {"contents": "read", "metadata": "read"}
    assert request.headers["content-type"].startswith("application/json")
    # App JWT authentication header is present.
    assert request.headers["authorization"].startswith("Bearer ")
    assert sign_app_jwt(APP_ID, settings.github_app_private_key)


def test_token_request_custom_permissions_are_sent(settings: Settings) -> None:
    """Listing needs metadata only; the requested downscoping must be sent."""

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            201, json={"token": "ghs_meta", "expires_at": "2030-01-01T00:00:00Z"}
        )

    import app.services.github.app_client as app_client_module

    client = HttpxGitHubAppClient(settings)
    original_client_cls = app_client_module.httpx.Client
    app_client_module.httpx.Client = lambda **kwargs: original_client_cls(
        transport=httpx.MockTransport(handler), **kwargs
    )
    try:
        client.build_installation_token(
            INSTALLATION_ID, permissions={"metadata": "read"}
        )
    finally:
        app_client_module.httpx.Client = original_client_cls

    body = json.loads(seen[0].content)
    assert body == {"permissions": {"metadata": "read"}}


def test_token_request_422_maps_to_actionable_error(settings: Settings) -> None:
    """422 (permissions not granted by the installation) is not a 404.

    Regression: GitHub returns 422 when the requested downscoping exceeds
    what the installation granted; this must surface as
    INSTALLATION_TOKEN_REJECTED, not INSTALLATION_NOT_FOUND.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            json={
                "message": "The permissions requested are not granted to this installation.",
                "documentation_url": "https://docs.github.com/rest/reference/apps",
            },
        )

    import app.services.github.app_client as app_client_module

    client = HttpxGitHubAppClient(settings)
    original_client_cls = app_client_module.httpx.Client
    app_client_module.httpx.Client = lambda **kwargs: original_client_cls(
        transport=httpx.MockTransport(handler), **kwargs
    )
    try:
        with pytest.raises(Exception) as excinfo:
            client.build_installation_token(INSTALLATION_ID)
    finally:
        app_client_module.httpx.Client = original_client_cls

    assert excinfo.value is INSTALLATION_TOKEN_REJECTED
    assert "Contents" in INSTALLATION_TOKEN_REJECTED.message


def test_list_installation_repositories_parses_page(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/installation/repositories"
        assert request.url.params["page"] == "2"
        assert request.url.params["per_page"] == "30"
        return httpx.Response(
            200,
            json={
                "total_count": 1,
                "repositories": [
                    {
                        "id": REPOSITORY_ID,
                        "full_name": "octo/repo",
                        "owner": {"login": "octo"},
                        "private": True,
                        "visibility": "private",
                        "default_branch": "main",
                        "description": "d",
                    }
                ],
            },
        )

    import app.services.github.app_client as app_client_module

    original_client_cls = app_client_module.httpx.Client
    app_client_module.httpx.Client = lambda **kwargs: original_client_cls(
        transport=httpx.MockTransport(handler), **kwargs
    )
    try:
        client = HttpxGitHubAppClient(settings)
        page = client.list_installation_repositories("ghs_test", page=2, per_page=30)
    finally:
        app_client_module.httpx.Client = original_client_cls

    assert page.total == 1
    [(repo)] = page.items
    assert repo.repository_id == REPOSITORY_ID
    assert repo.visibility == "private"
    assert repo.default_branch == "main"


def test_settings_accepts_escaped_newline_pem(private_key_pem: str) -> None:
    escaped = private_key_pem.replace("\n", "\\n")
    settings = Settings(
        github_app_id=APP_ID,
        github_app_slug="flowlens-test",
        github_app_private_key=escaped,
    )
    # The normalized key must load and sign exactly like the literal PEM.
    key = serialization.load_pem_private_key(
        settings.github_app_private_key.encode("utf-8"), password=None
    )
    assert isinstance(key, RSAPrivateKey)
    assert settings.github_app_private_key == private_key_pem.strip()


def test_settings_leaves_valid_pem_and_empty_value_untouched(private_key_pem: str) -> None:
    settings = Settings(
        github_app_id=APP_ID,
        github_app_slug="flowlens-test",
        github_app_private_key=private_key_pem,
    )
    assert settings.github_app_private_key == private_key_pem.strip()
    empty = Settings(github_app_id=APP_ID, github_app_private_key="")
    assert empty.github_app_private_key == ""
