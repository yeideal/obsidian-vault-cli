from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests


class CouchError(RuntimeError):
    pass


@dataclass(frozen=True)
class CouchConfig:
    url: str
    database: str
    username: str = ""
    password: str = ""


class CouchClient:
    def __init__(self, config: CouchConfig, timeout: float = 20.0):
        self.config = config
        self.timeout = timeout
        self.base = config.url.rstrip("/")
        self.db_url = f"{self.base}/{quote(config.database, safe='')}"
        self.auth = (config.username, config.password) if config.username else None
        self.session = requests.Session()
        self.session.trust_env = False

    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        response = self.session.request(method, url, auth=self.auth, timeout=self.timeout, **kwargs)
        if response.status_code >= 400:
            body = response.text[:500]
            raise CouchError(f"{method} {url} failed: HTTP {response.status_code}: {body}")
        return response

    def ping(self) -> dict[str, Any]:
        server = self._request("GET", self.base).json()
        db = self._request("GET", self.db_url).json()
        return {"server": server, "database": db}

    def get_doc(self, doc_id: str) -> dict[str, Any] | None:
        url = f"{self.db_url}/{quote(doc_id, safe='')}"
        response = self.session.get(url, auth=self.auth, timeout=self.timeout)
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            raise CouchError(f"GET {url} failed: HTTP {response.status_code}: {response.text[:500]}")
        return response.json()

    def put_doc(self, doc_id: str, doc: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_doc(doc_id)
        payload = dict(doc)
        payload["_id"] = doc_id
        if existing and "_rev" in existing:
            payload["_rev"] = existing["_rev"]
        url = f"{self.db_url}/{quote(doc_id, safe='')}"
        response = self._request(
            "PUT",
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return response.json()

    def bulk_docs(self, docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not docs:
            return []
        prepared: list[dict[str, Any]] = []
        for doc in docs:
            doc_id = str(doc["_id"])
            existing = self.get_doc(doc_id)
            payload = dict(doc)
            if existing and "_rev" in existing:
                payload["_rev"] = existing["_rev"]
            prepared.append(payload)
        response = self._request(
            "POST",
            f"{self.db_url}/_bulk_docs",
            data=json.dumps({"docs": prepared}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return response.json()
