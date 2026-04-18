"""ZHS authentication via TUM Shibboleth -> Ory Kratos OIDC flow.

Manages a cached ory-session cookie for authenticated GraphQL calls.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse, urljoin

import httpx

from src.exceptions import TUMAuthenticationError, TUMSystemUnavailableError
from src.lib.logging import get_logger

logger = get_logger(__name__)

ZHS_BASE = "https://kurse.zhs-muenchen.de"
ZHS_LOGIN = f"{ZHS_BASE}/auth/login"
ZHS_GQL = f"{ZHS_BASE}/api/query"

_session_lock = asyncio.Lock()
_cached_cookies: dict[str, str] = {}


def _abs_url(relative: str, base_url: str) -> str:
    """Resolve a possibly-relative URL against a base URL."""
    if relative.startswith("http://") or relative.startswith("https://"):
        return relative
    return urljoin(base_url, relative)


def _extract_action(html: str) -> str | None:
    """Extract the first form action URL from HTML."""
    m = re.search(r'action="([^"]+)"', html)
    if m:
        return m.group(1).replace("&amp;", "&")
    return None


async def authenticate_zhs(
    *,
    tum_username: str,
    tum_password: str,
) -> dict[str, str]:
    """Run the full Kratos -> TUM Shibboleth -> OIDC callback flow.

    Returns:
        Dict of cookies including ory-session for GraphQL auth.

    Raises:
        TUMAuthenticationError: If credentials are invalid.
        TUMSystemUnavailableError: If ZHS or TUM IdP is unreachable.
    """
    logger.info("zhs_auth_start", username=tum_username)

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=False,
        ) as client:
            # Step 1: Initiate Kratos login browser flow
            login_resp = await client.get(ZHS_LOGIN, follow_redirects=True)
            if login_resp.status_code != 200:
                raise TUMSystemUnavailableError(f"ZHS login page returned {login_resp.status_code}")

            # Step 2: Submit OIDC provider selection (oidc-tum)
            page_text = login_resp.text
            action_match = re.search(r'action="([^"]+)"', page_text)
            csrf_match = re.search(r'name="csrf_token"\s+.*?value="([^"]+)"', page_text, re.S)

            if not action_match or not csrf_match:
                raise TUMSystemUnavailableError("Cannot parse Kratos login form")

            action_url = action_match.group(1).replace("&amp;", "&")
            action_url = _abs_url(action_url, str(login_resp.url))
            csrf_token = csrf_match.group(1)

            oidc_resp = await client.post(
                action_url,
                data={"csrf_token": csrf_token, "provider": "oidc-tum"},
                follow_redirects=True,
            )

            # Step 3: We should now be at TUM Shibboleth IdP
            idp_url = str(oidc_resp.url)
            idp_text = oidc_resp.text

            if "username" not in idp_text.lower() and "password" not in idp_text.lower():
                # TUM IdP has a JS "session loading" page — follow its form action
                meta_refresh = re.search(
                    r'<meta[^>]+http-equiv="refresh"[^>]+content="[^;]*;\s*url=([^"]+)"',
                    idp_text,
                    re.I,
                )
                if meta_refresh:
                    refresh_url = _abs_url(meta_refresh.group(1), idp_url)
                    idp_resp2 = await client.get(refresh_url, follow_redirects=True)
                    idp_url = str(idp_resp2.url)
                    idp_text = idp_resp2.text

                form_action = _extract_action(idp_text)
                if form_action:
                    abs_action = _abs_url(form_action, idp_url)
                    idp_resp3 = await client.post(abs_action, data={}, follow_redirects=True)
                    idp_url = str(idp_resp3.url)
                    idp_text = idp_resp3.text

            # Step 4: Submit TUM credentials
            form_action = _extract_action(idp_text)
            if not form_action:
                raise TUMSystemUnavailableError("Cannot find TUM IdP login form")

            action = _abs_url(form_action, idp_url)

            cred_resp = await client.post(
                action,
                data={"j_username": tum_username, "j_password": tum_password},
                follow_redirects=True,
            )

            cred_text = cred_resp.text
            cred_url = str(cred_resp.url)

            # Check for login failure
            if "error" in cred_text.lower() and "password" in cred_text.lower():
                raise TUMAuthenticationError("Invalid TUM credentials")

            # Step 5: Handle SAML response -> OIDC callback
            saml_match = re.search(r'name="SAMLResponse"\s+value="([^"]+)"', cred_text)
            relay_match = re.search(r'name="RelayState"\s+value="([^"]+)"', cred_text)

            if saml_match:
                saml_action_raw = _extract_action(cred_text)
                if saml_action_raw:
                    saml_url = _abs_url(saml_action_raw, cred_url)
                    saml_data: dict[str, str] = {
                        "SAMLResponse": saml_match.group(1),
                    }
                    if relay_match:
                        saml_data["RelayState"] = relay_match.group(1)

                    await client.post(saml_url, data=saml_data, follow_redirects=True)

            # Step 6: Extract session cookies
            all_cookies = dict(client.cookies.items())
            session_cookies = {k: v for k, v in all_cookies.items() if "ory" in k.lower()}

            if not session_cookies:
                raise TUMAuthenticationError(
                    "No ory-session cookie obtained — login may have failed"
                )

            logger.info("zhs_auth_success", cookies=list(session_cookies.keys()))
            return all_cookies

    except (TUMAuthenticationError, TUMSystemUnavailableError):
        raise
    except Exception as exc:
        logger.error("zhs_auth_failed", exc_info=True)
        raise TUMSystemUnavailableError(f"ZHS auth flow failed: {exc}") from exc


async def get_zhs_session(
    *,
    tum_username: str,
    tum_password: str,
    force_refresh: bool = False,
) -> dict[str, str]:
    """Get a cached or fresh ZHS session.

    Thread-safe — only one auth flow runs at a time.
    """
    async with _session_lock:
        if _cached_cookies and not force_refresh:
            return _cached_cookies

        cookies = await authenticate_zhs(tum_username=tum_username, tum_password=tum_password)
        _cached_cookies.clear()
        _cached_cookies.update(cookies)
        return dict(_cached_cookies)


async def gql_query(
    query: str,
    *,
    cookies: dict[str, str],
    variables: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute an authenticated GraphQL query against the ZHS API."""
    payload: dict[str, Any] = {"query": query}
    if variables:
        payload["variables"] = variables

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            ZHS_GQL,
            json=payload,
            cookies=cookies,
            headers={"Content-Type": "application/json"},
        )

        if resp.status_code == 401:
            raise TUMAuthenticationError("ZHS session expired")
        if resp.status_code != 200:
            raise TUMSystemUnavailableError(f"ZHS GraphQL returned {resp.status_code}")

        result: dict[str, Any] = resp.json()
        if "errors" in result:
            error_msg = result["errors"][0].get("message", "Unknown GraphQL error")
            raise TUMSystemUnavailableError(f"ZHS GraphQL error: {error_msg}")

        data: dict[str, Any] = result.get("data", {})
        return data
