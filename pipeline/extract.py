"""Extract records from the Business Central API v2.0.

The client handles the three things that make ERP extraction fiddly:

* **Auth.** OAuth 2.0 client credentials against Microsoft Entra ID (or the
  mock's token endpoint). Tokens are cached until shortly before they expire.
* **Paging.** BC pages server-side and returns ``@odata.nextLink``; the client
  follows it until there is none.
* **Throttling.** BC SaaS returns 429 (and sometimes 5xx) under load. The client
  retries with ``Retry-After`` or exponential backoff, then gives up loudly.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterator

import requests

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}


class ExtractError(RuntimeError):
    pass


@dataclass
class BCConfig:
    base_url: str                    # e.g. https://api.businesscentral.dynamics.com/v2.0/<tenant>/<env>
    company_id: str | None = None    # looked up by name if empty
    company_name: str | None = None
    token_url: str | None = None     # https://login.microsoftonline.com/<tenant>/oauth2/v2.0/token
    client_id: str | None = None
    client_secret: str | None = None
    scope: str = "https://api.businesscentral.dynamics.com/.default"
    max_retries: int = 5
    backoff_seconds: float = 1.0
    timeout_seconds: float = 30.0


class BusinessCentralClient:
    def __init__(self, config: BCConfig, session: requests.Session | None = None, sleep=time.sleep):
        self.config = config
        self.session = session or requests.Session()
        self._sleep = sleep
        self._token: str | None = None
        self._token_expires = 0.0

    # -- auth -----------------------------------------------------------------
    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token
        cfg = self.config
        if not (cfg.token_url and cfg.client_id and cfg.client_secret):
            raise ExtractError("token_url, client_id and client_secret are required")
        response = self.session.post(
            cfg.token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
                "scope": cfg.scope,
            },
            timeout=cfg.timeout_seconds,
        )
        if response.status_code != 200:
            raise ExtractError(f"Token request failed with HTTP {response.status_code}")
        body = response.json()
        self._token = body["access_token"]
        self._token_expires = time.time() + int(body.get("expires_in", 3600))
        return self._token

    # -- http -----------------------------------------------------------------
    def _get(self, url: str, params: dict | None = None) -> dict:
        for attempt in range(1, self.config.max_retries + 1):
            response = self.session.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {self._access_token()}", "Accept": "application/json"},
                timeout=self.config.timeout_seconds,
            )
            if response.status_code == 200:
                return response.json()
            if response.status_code == 401 and attempt == 1:
                self._token = None  # token revoked or expired early: fetch a new one once
                continue
            if response.status_code in RETRY_STATUSES and attempt < self.config.max_retries:
                wait = response.headers.get("Retry-After")
                delay = float(wait) if wait else self.config.backoff_seconds * 2 ** (attempt - 1)
                log.warning("HTTP %s from %s, retry %s in %.1fs", response.status_code, url, attempt, delay)
                self._sleep(delay)
                continue
            raise ExtractError(f"GET {url} failed with HTTP {response.status_code}: {response.text[:200]}")
        raise ExtractError(f"GET {url} still failing after {self.config.max_retries} attempts")

    def company_id(self) -> str:
        if self.config.company_id:
            return self.config.company_id
        companies = self._get(f"{self.config.base_url}/api/v2.0/companies")["value"]
        if not companies:
            raise ExtractError("No companies returned by the API")
        if self.config.company_name:
            matches = [c for c in companies if c["name"] == self.config.company_name]
            if not matches:
                raise ExtractError(f"Company {self.config.company_name!r} not found")
            companies = matches
        self.config.company_id = companies[0]["id"]
        return self.config.company_id

    def fetch(self, entity_set: str, modified_since: str | None = None) -> Iterator[dict]:
        """Yield every record of an entity set, following nextLink pages."""
        url = f"{self.config.base_url}/api/v2.0/companies({self.company_id()})/{entity_set}"
        params = {"$filter": f"lastModifiedDateTime gt {modified_since}"} if modified_since else None
        pages = 0
        while url:
            body = self._get(url, params)
            pages += 1
            yield from body.get("value", [])
            url = body.get("@odata.nextLink")
            params = None  # the nextLink already carries the query
        log.info("%s: %s page(s)", entity_set, pages)
