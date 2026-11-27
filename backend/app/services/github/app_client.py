"""GitHub App installation API client (github.com only).

Handles:
- RS256 JWT signing for GitHub App authentication (installation tokens).
- Short-lived installation access tokens, scoped to a selected repository
  where possible. Tokens are never logged, never persisted, and never returned
  to clients; they are passed only between server-side service calls.
- Paginated user installations / installation repositories queries.
- Ref resolution and archive (tarball) download restricted to an exact host
  allowlist with validated redirects: no arbitrary URL fetching (SSRF guard),
  no `git clone` and no shell-outs.

The base class in this module is an injectable interface; automated tests use
a scripted mock, so no real GitHub traffic occurs in the test suite.
"""

import base64
import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from urllib.parse import quote, urlparse

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from app.core.config import Settings
from app.core.errors import ApiError

logger = logging.getLogger("flowlens.github_app")

# --------------------------------------------------------------------- errors
INSTALLATION_NOT_FOUND = ApiError(
    status_code=404,
    code="INSTALLATION_NOT_FOUND",
    message="FlowLens could not find this GitHub App installation.",
)
INSTALLATION_TOKEN_REJECTED = ApiError(
    status_code=502,
    code="INSTALLATION_TOKEN_REJECTED",
    message=(
        "GitHub rejected the installation access token request. Make sure the "
        "FlowLens GitHub App has the required repository permissions "
        "(Contents: read-only and Metadata: read-only) and access to the "
        "repository, then re-approve the installation on GitHub."
    ),
)
INSTALLATION_ACCESS_DENIED = ApiError(
    status_code=403,
    code="REPOSITORY_ACCESS_DENIED",
    message="FlowLens does not have access to this installation.",
)
REPOSITORY_ACCESS_DENIED = ApiError(
    status_code=403,
    code="REPOSITORY_ACCESS_DENIED",
    message="FlowLens does not have access to this repository.",
)
REF_NOT_FOUND = ApiError(
    status_code=404,
    code="NOT_FOUND",
    message="The selected branch, tag, or commit could not be found.",
)
RATE_LIMITED = ApiError(
    status_code=429,
    code="RATE_LIMITED",
    message="GitHub is rate limiting FlowLens. Please try again shortly.",
)
GITHUB_API_ERROR = ApiError(
    status_code=502,
    code="GITHUB_API_ERROR",
    message="GitHub returned an error. Please try again shortly.",
)
GITHUB_APP_NOT_CONFIGURED = ApiError(
    status_code=503,
    code="GITHUB_APP_NOT_CONFIGURED",
    message="The FlowLens GitHub App is not configured on the server.",
)
ARCHIVE_DOWNLOAD_FAILED = ApiError(
    status_code=502,
    code="GITHUB_API_ERROR",
    message="The repository source archive could not be downloaded.",
)
USER_TOKEN_UNAVAILABLE = ApiError(
    status_code=401,
    code="GITHUB_TOKEN_ERROR",
    message="Your GitHub authorization is no longer valid. Please sign in again.",
)

API_VERSION_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

MAX_REDIRECT_HOPS = 3
INSTALLATION_TOKEN_TTL_MARGIN_SECONDS = 60  # request tokens valid ~1 hour

# owner/repo names come from GitHub API payloads (or stored provenance); the
# shape is validated before either is placed into a request URL so a tampered
# stored value cannot redirect a request to a different API path.
_SAFE_REPO_PATH_RE = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


# ------------------------------------------------------------------ dataclasses
@dataclass(frozen=True)
class InstallationInfo:
    installation_id: int
    account_login: str
    account_type: str  # "user" | "organization"
    avatar_url: str | None = None


@dataclass(frozen=True)
class RepositoryInfo:
    repository_id: int
    full_name: str
    owner: str
    visibility: str  # "public" | "private" (display only, never an access decision)
    default_branch: str
    description: str | None = None


@dataclass(frozen=True)
class RepositoriesPage:
    items: list[RepositoryInfo] = field(default_factory=list)
    total: int = 0


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: float  # POSIX seconds


@dataclass(frozen=True)
class ResolvedRef:
    ref: str
    commit_sha: str


def _installation_info_from_payload(payload: dict) -> InstallationInfo:
    account = payload.get("account") or {}
    return InstallationInfo(
        installation_id=int(payload["id"]),
        account_login=account.get("login", ""),
        account_type="organization" if account.get("type") == "Organization" else "user",
        avatar_url=account.get("avatar_url"),
    )


def _repository_info_from_payload(payload: dict) -> RepositoryInfo:
    owner = (payload.get("owner") or {}).get("login", "")
    return RepositoryInfo(
        repository_id=int(payload["id"]),
        full_name=payload.get("full_name", ""),
        owner=owner,
        # GitHub reports "visibility" (public/private) and "private" boolean.
        visibility="private" if payload.get("private") else payload.get("visibility", "public"),
        default_branch=payload.get("default_branch", ""),
        description=payload.get("description"),
    )


def safe_repo_path(full_name: str) -> str:
    """Validate an owner/repo pair before it is used in a request URL."""
    if not full_name or not _SAFE_REPO_PATH_RE.match(full_name):
        logger.warning("github request blocked: malformed repository name", extra={"context": {}})
        raise GITHUB_API_ERROR
    return full_name


def safe_ref_segment(ref: str) -> str:
    """Validate and percent-encode a user-supplied ref for a URL path.

    Git references cannot contain `..`, ASCII control characters, leading or
    trailing slashes, or exceed practical length limits; such values are
    rejected outright rather than encoded, so a crafted ref can never walk the
    request path to a different API endpoint or inject query/fragment syntax.
    Remaining unsafe characters (spaces, `?`, `#`, non-ASCII) are
    percent-encoded; `/` separators are preserved because both the commits API
    and the codeload archive endpoint accept slash-separated refs.
    """
    if not ref or len(ref) > 4096:
        raise REF_NOT_FOUND
    if ".." in ref or any(ord(char) < 0x20 or ord(char) == 0x7F for char in ref):
        raise REF_NOT_FOUND
    if ref.startswith("/") or ref.endswith("/"):
        raise REF_NOT_FOUND
    return quote(ref, safe="/")


# ----------------------------------------------------------- app JWT utilities
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def sign_app_jwt(app_id: int, private_key_pem: str, issued_at: int | None = None) -> str:
    """GitHub App JWT (RS256) for app-authenticated API calls.

    Implemented directly with the `cryptography` package to avoid adding a
    JWT dependency; the format follows GitHub's App authentication docs:
    header {"alg": "RS256", "typ": "JWT"} and a short-lived `iss` = App ID.
    """
    if issued_at is None:
        issued_at = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iat": issued_at,
        # GitHub allows max 10 minutes; keep a small safety margin.
        "exp": issued_at + 540,
        "iss": str(app_id),
    }
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(claims, separators=(",", ":")).encode())
    )
    try:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"), password=None
        )
        if not isinstance(private_key, RSAPrivateKey):
            raise ValueError("not an RSA key")
        signature = private_key.sign(
            signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256()
        )
    except (ValueError, TypeError) as exc:
        logger.error("github app private key is invalid", extra={"context": {"error": type(exc).__name__}})
        raise GITHUB_APP_NOT_CONFIGURED from exc
    return signing_input + "." + _b64url(signature)


class GitHubAppClient:
    """Injectable interface for installation-level GitHub operations."""

    def build_installation_token(
        self,
        installation_id: int,
        repository_ids: list[int] | None = None,
        permissions: dict[str, str] | None = None,
    ) -> InstallationToken:
        raise NotImplementedError

    def get_app_installation(self, installation_id: int) -> InstallationInfo:
        raise NotImplementedError

    def list_user_installations(self, user_access_token: str) -> list[InstallationInfo]:
        raise NotImplementedError

    def list_installation_repositories(
        self, installation_token: str, page: int, per_page: int
    ) -> RepositoriesPage:
        raise NotImplementedError

    def get_repository(self, installation_token: str, repository_id: int) -> RepositoryInfo:
        raise NotImplementedError

    def resolve_ref(self, installation_token: str, full_name: str, ref: str) -> ResolvedRef:
        raise NotImplementedError

    def download_archive(self, installation_token: str, full_name: str, ref: str) -> bytes:
        raise NotImplementedError


class HttpxGitHubAppClient(GitHubAppClient):
    """Production client against github.com (mocked in automated tests)."""

    def __init__(self, settings: Settings, timeout: float = 10.0) -> None:
        self._settings = settings
        self._timeout = timeout

    # ------------------------------------------------------------- internals
    def _require_app_config(self) -> None:
        if not self._settings.github_app_id or not self._settings.github_app_private_key:
            raise GITHUB_APP_NOT_CONFIGURED

    def _api_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", **API_VERSION_HEADERS}

    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict | None = None,
        json_body: dict | None = None,
        allow_hosts: set[str] | None = None,
    ) -> httpx.Response:
        """Single-hop request that refuses any non-allowlisted host.

        Redirects are followed manually (bounded) only when the target host
        is inside the allowlist, preventing redirect-based SSRF.
        """
        allowed_hosts = allow_hosts if allow_hosts is not None else {self._settings.github_api_host}
        current_url = url
        for _hop in range(MAX_REDIRECT_HOPS + 1):
            host = urlparse(current_url).hostname or ""
            if host not in allowed_hosts:
                logger.warning("github request blocked: host not allowlisted", extra={"context": {}})
                raise GITHUB_API_ERROR
            try:
                with httpx.Client(timeout=self._timeout, follow_redirects=False) as client:
                    response = client.request(
                        method, current_url, headers=headers, params=params, json=json_body
                    )
            except httpx.HTTPError as exc:
                logger.warning(
                    "github request transport error",
                    extra={"context": {"error": type(exc).__name__}},
                )
                raise GITHUB_API_ERROR from exc
            if response.status_code in (301, 302, 303, 307, 308):
                location = response.headers.get("location", "")
                host = urlparse(location).hostname or ""
                if host not in allowed_hosts:
                    logger.warning("github redirect to non-allowlisted host blocked", extra={"context": {}})
                    raise GITHUB_API_ERROR
                current_url = location
                continue
            return response
        logger.warning("github redirect loop blocked", extra={"context": {}})
        raise GITHUB_API_ERROR

    def _json(self, response: httpx.Response) -> dict:
        try:
            return response.json()
        except ValueError as exc:
            logger.warning("github returned non-JSON payload", extra={"context": {}})
            raise GITHUB_API_ERROR from exc

    def _map_status(self, response: httpx.Response) -> None:
        """Translate GitHub status codes into stable apI error envelopes."""
        if response.status_code == 404:
            # Callers refine the message/code for repository/ref contexts.
            raise GITHUB_API_ERROR
        if response.status_code == 403:
            if response.headers.get("x-ratelimit-remaining") == "0":
                raise RATE_LIMITED
            raise GITHUB_API_ERROR
        if response.status_code == 429:
            raise RATE_LIMITED

    # ------------------------------------------------- installation tokens
    def build_installation_token(
        self,
        installation_id: int,
        repository_ids: list[int] | None = None,
        permissions: dict[str, str] | None = None,
    ) -> InstallationToken:
        """Short-lived installation access token, scoped when supported.

        Tokens live only in server memory for the duration of a request;
        they are never stored in the database or returned to a client.
        `permissions` downscopes the token to what the operation needs; it
        must be a subset of the permissions the installation actually
        granted, otherwise GitHub rejects the request with 422.
        """
        self._require_app_config()
        jwt = sign_app_jwt(self._settings.github_app_id, self._settings.github_app_private_key)
        if permissions is None:
            permissions = {"contents": "read", "metadata": "read"}
        body: dict = {"permissions": permissions}
        if repository_ids:
            body["repository_ids"] = repository_ids
        response = self._request(
            "POST",
            f"{self._settings.github_api_base_url}/app/installations/{installation_id}/access_tokens",
            headers=self._api_headers(jwt),
            json_body=body,
        )
        if response.status_code == 404:
            raise INSTALLATION_NOT_FOUND
        if response.status_code == 422:
            # GitHub rejects downscoping to permissions the installation has
            # not granted (or repository_ids it cannot access).
            logger.warning(
                "installation token request rejected by github",
                extra={"context": {"status": 422, "permissions": permissions}},
            )
            raise INSTALLATION_TOKEN_REJECTED
        if response.status_code != 201:
            self._map_status(response)
            logger.warning(
                "installation token creation failed",
                extra={"context": {"status": response.status_code}},
            )
            raise GITHUB_API_ERROR
        payload = self._json(response)
        expires_at = time.time() + INSTALLATION_TOKEN_TTL_MARGIN_SECONDS
        return InstallationToken(token=payload["token"], expires_at=expires_at)

    def get_app_installation(self, installation_id: int) -> InstallationInfo:
        self._require_app_config()
        jwt = sign_app_jwt(self._settings.github_app_id, self._settings.github_app_private_key)
        response = self._request(
            "GET",
            f"{self._settings.github_api_base_url}/app/installations/{installation_id}",
            headers=self._api_headers(jwt),
        )
        if response.status_code == 404:
            raise INSTALLATION_NOT_FOUND
        if response.status_code != 200:
            self._map_status(response)
            raise GITHUB_API_ERROR
        return _installation_info_from_payload(self._json(response))

    # ------------------------------------------------------ user installations
    def list_user_installations(self, user_access_token: str) -> list[InstallationInfo]:
        """Installations the user can access (GET /user/installations)."""
        results: list[InstallationInfo] = []
        page = 1
        while True:
            response = self._request(
                "GET",
                f"{self._settings.github_api_base_url}/user/installations",
                headers=self._api_headers(user_access_token),
                params={"page": page, "per_page": 100},
            )
            if response.status_code == 401:
                raise USER_TOKEN_UNAVAILABLE
            if response.status_code != 200:
                self._map_status(response)
                raise GITHUB_API_ERROR
            payload = self._json(response)
            batch = payload.get("installations", [])
            results.extend(_installation_info_from_payload(item) for item in batch)
            if len(batch) < 100:
                return results
            page += 1

    # ------------------------------------------------- installation repositories
    def list_installation_repositories(
        self, installation_token: str, page: int, per_page: int
    ) -> RepositoriesPage:
        response = self._request(
            "GET",
            f"{self._settings.github_api_base_url}/installation/repositories",
            headers=self._api_headers(installation_token),
            params={"page": page, "per_page": per_page},
        )
        if response.status_code in (401, 403):
            raise INSTALLATION_ACCESS_DENIED
        if response.status_code != 200:
            self._map_status(response)
            raise GITHUB_API_ERROR
        payload = self._json(response)
        return RepositoriesPage(
            items=[_repository_info_from_payload(item) for item in payload.get("repositories", [])],
            total=int(payload.get("total_count", len(payload.get("repositories", [])))),
        )

    # ------------------------------------------------------------ repositories
    def get_repository(self, installation_token: str, repository_id: int) -> RepositoryInfo:
        """Fetch a canonical repository record with an installation token.

        GitHub returns 404 for repositories the installation cannot access,
        which maps to REPOSITORY_ACCESS_DENIED (never guess, never trust the
        browser-supplied repository ID).
        """
        response = self._request(
            "GET",
            f"{self._settings.github_api_base_url}/repositories/{repository_id}",
            headers=self._api_headers(installation_token),
        )
        if response.status_code == 404:
            raise REPOSITORY_ACCESS_DENIED
        if response.status_code != 200:
            self._map_status(response)
            raise GITHUB_API_ERROR
        return _repository_info_from_payload(self._json(response))

    # -------------------------------------------------------------------- refs
    def resolve_ref(self, installation_token: str, full_name: str, ref: str) -> ResolvedRef:
        """Resolve a branch/tag/commit ref to its immutable commit SHA."""
        encoded_ref = safe_ref_segment(ref)
        response = self._request(
            "GET",
            f"{self._settings.github_api_base_url}/repos/{safe_repo_path(full_name)}/commits/{encoded_ref}",
            headers=self._api_headers(installation_token),
        )
        if response.status_code == 404:
            raise REF_NOT_FOUND
        if response.status_code != 200:
            self._map_status(response)
            raise GITHUB_API_ERROR
        payload = self._json(response)
        sha = payload.get("sha") or ""
        if not sha:
            raise GITHUB_API_ERROR
        return ResolvedRef(ref=ref, commit_sha=sha)

    # ---------------------------------------------------------------- archives
    def download_archive(self, installation_token: str, full_name: str, ref: str) -> bytes:
        """Download the repository tarball from the allowlisted archive host.

        Redirects are followed manually (bounded hop count) and only when the
        target host is inside the SSRF allowlist, mirroring `_request`.
        """
        limit = self._settings.snapshot_max_archive_bytes
        headers = self._api_headers(installation_token)
        url = (
            f"{self._settings.github_archive_base_url}"
            f"/{safe_repo_path(full_name)}/tar.gz/{safe_ref_segment(ref)}"
        )
        try:
            with httpx.Client(
                timeout=self._settings.snapshot_download_timeout_seconds, follow_redirects=False
            ) as client:
                current_url = url
                for _hop in range(MAX_REDIRECT_HOPS + 1):
                    host = urlparse(current_url).hostname or ""
                    if host not in self._settings.github_allowed_hosts:
                        logger.warning("archive host not allowlisted", extra={"context": {}})
                        raise ARCHIVE_DOWNLOAD_FAILED
                    with client.stream("GET", current_url, headers=headers) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            location = response.headers.get("location", "")
                            if (urlparse(location).hostname or "") not in self._settings.github_allowed_hosts:
                                logger.warning("archive redirect blocked", extra={"context": {}})
                                raise ARCHIVE_DOWNLOAD_FAILED
                            current_url = location
                            continue
                        if response.status_code != 200:
                            self._map_status(response)
                            raise ARCHIVE_DOWNLOAD_FAILED
                        chunks: list[bytes] = []
                        total = 0
                        for chunk in response.iter_bytes(64 * 1024):
                            total += len(chunk)
                            if total > limit:
                                logger.warning("archive exceeds configured size limit", extra={"context": {}})
                                raise ARCHIVE_DOWNLOAD_FAILED
                            chunks.append(chunk)
                        return b"".join(chunks)
                logger.warning("archive redirect loop blocked", extra={"context": {}})
                raise ARCHIVE_DOWNLOAD_FAILED
        except httpx.HTTPError as exc:
            logger.warning("archive download transport error", extra={"context": {"error": type(exc).__name__}})
            raise ARCHIVE_DOWNLOAD_FAILED from exc
