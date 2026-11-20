"""A small stand-in for the Business Central API v2.0.

It behaves like the parts of the real API the pipeline relies on:

* ``GET /api/v2.0/companies`` lists companies.
* ``GET /api/v2.0/companies({id})/{entitySet}`` returns ``{"value": [...]}``.
* Server-driven paging with ``@odata.nextLink`` and ``$skiptoken``.
* ``$filter=lastModifiedDateTime gt <timestamp>`` for incremental loads.
* Bearer tokens are required; ``POST /oauth2/token`` hands one out.
* Optional throttling: the first N data requests return 429 or 503, so the
  client's retry logic can be exercised.

Run it on its own with ``python -m pipeline.mock_bc.server --port 8080``.
"""

from __future__ import annotations

import argparse
import json
import re
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from .data import generate

COMPANY_ID = "6f1e5c1a-0000-4000-8000-000000000001"
FILTER_RE = re.compile(r"^lastModifiedDateTime gt (\S+)$")
ENTITY_RE = re.compile(r"^/api/v2\.0/companies\(([^)]+)\)/(\w+)$")


class MockBusinessCentral:
    def __init__(self, seed: int = 42, page_size: int = 100, fail_first: int = 0, fail_status: int = 429):
        self.data = generate(seed=seed)
        self.page_size = page_size
        self.fail_remaining = fail_first
        self.fail_status = fail_status
        self.requests: list[str] = []
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None

    # -- test helpers -------------------------------------------------------
    def touch(self, entity: str, record_id: str, **changes) -> None:
        """Change a record and bump its lastModifiedDateTime, as an edit in BC would."""
        for row in self.data[entity]:
            if row["id"] == record_id:
                row.update(changes)
                row["lastModifiedDateTime"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                return
        raise KeyError(record_id)

    def add(self, entity: str, row: dict) -> None:
        row.setdefault("lastModifiedDateTime", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        self.data[entity].append(row)

    # -- server lifecycle ---------------------------------------------------
    def start(self, host: str = "127.0.0.1", port: int = 0) -> str:
        self._server = ThreadingHTTPServer((host, port), self._handler())
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://{host}:{self._server.server_address[1]}"

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    def serve_forever(self, host: str, port: int) -> None:
        self._server = ThreadingHTTPServer((host, port), self._handler())
        print(f"Mock Business Central API on http://{host}:{port}")
        self._server.serve_forever()

    # -- request handling ---------------------------------------------------
    def _handler(self):
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep test output quiet
                pass

            def _send(self, status: int, body: dict | None = None, headers: dict | None = None):
                payload = json.dumps(body or {}).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self):
                if urlparse(self.path).path.endswith("/oauth2/token"):
                    length = int(self.headers.get("Content-Length", 0))
                    form = parse_qs(self.rfile.read(length).decode())
                    if form.get("grant_type") != ["client_credentials"]:
                        return self._send(400, {"error": "unsupported_grant_type"})
                    return self._send(200, {"access_token": "mock-token", "token_type": "Bearer", "expires_in": 3599})
                self._send(404, {"error": {"code": "NotFound"}})

            def do_GET(self):
                url = urlparse(self.path)
                mock.requests.append(self.path)
                if not self.headers.get("Authorization", "").startswith("Bearer "):
                    return self._send(401, {"error": {"code": "Unauthorized", "message": "Missing bearer token"}})

                with mock._lock:
                    if mock.fail_remaining > 0:
                        mock.fail_remaining -= 1
                        return self._send(mock.fail_status, {"error": {"code": "TooManyRequests"}}, {"Retry-After": "0"})

                if url.path == "/api/v2.0/companies":
                    return self._send(200, {"value": [{"id": COMPANY_ID, "name": "CRONUS Demo Trading", "displayName": "CRONUS Demo Trading"}]})

                match = ENTITY_RE.match(url.path)
                if not match:
                    return self._send(404, {"error": {"code": "BadRequest_NotFound"}})
                company, entity = match.groups()
                if company != COMPANY_ID or entity not in mock.data:
                    return self._send(404, {"error": {"code": "BadRequest_NotFound", "message": entity}})

                query = {k: v[0] for k, v in parse_qs(url.query).items()}
                rows = mock.data[entity]
                if "$filter" in query:
                    found = FILTER_RE.match(query["$filter"])
                    if not found:
                        return self._send(400, {"error": {"code": "BadRequest", "message": "Unsupported $filter"}})
                    since = found.group(1)
                    rows = [r for r in rows if r["lastModifiedDateTime"] > since]
                rows = sorted(rows, key=lambda r: (r["lastModifiedDateTime"], r["id"]))

                offset = int(query.get("$skiptoken", 0))
                page = rows[offset : offset + mock.page_size]
                body: dict = {"@odata.context": f"{url.path}/$metadata", "value": page}
                if offset + mock.page_size < len(rows):
                    next_query = {k: v for k, v in query.items() if k != "$skiptoken"}
                    next_query["$skiptoken"] = str(offset + mock.page_size)
                    host = self.headers.get("Host")
                    body["@odata.nextLink"] = f"http://{host}{url.path}?{urlencode(next_query)}"
                self._send(200, body)

        return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mock Business Central API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--fail-first", type=int, default=0, help="Throttle the first N data requests")
    args = parser.parse_args()
    MockBusinessCentral(fail_first=args.fail_first).serve_forever(args.host, args.port)


if __name__ == "__main__":
    main()
