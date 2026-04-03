from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests

from app.config import settings


class SerperError(RuntimeError):
    pass


def _normalize_search_response(payload: dict[str, Any]) -> dict[str, Any]:
    organic = []
    for item in payload.get("organic", [])[:5]:
        organic.append(
            {
                "title": item.get("title"),
                "link": item.get("link"),
                "snippet": item.get("snippet"),
                "position": item.get("position"),
            }
        )
    knowledge_graph = payload.get("knowledgeGraph") or {}
    return {
        "organic": organic,
        "knowledge_graph": {
            "title": knowledge_graph.get("title"),
            "type": knowledge_graph.get("type"),
            "description": knowledge_graph.get("description"),
            "website": knowledge_graph.get("website"),
        },
        "related_searches": [item.get("query") for item in payload.get("relatedSearches", [])[:5] if item.get("query")],
    }


def search_company_context(*, company_name: str, website_url: str | None) -> dict[str, Any]:
    if not settings.serper_api_key:
        return {"queries": [], "results": []}

    queries: list[str] = []
    if website_url:
        hostname = urlparse(website_url).hostname or website_url.replace("https://", "").replace("http://", "").rstrip("/")
        queries.append(f"site:{hostname} {company_name}")
    queries.append(f"{company_name} services")

    results = []
    headers = {
        "X-API-KEY": settings.serper_api_key,
        "Content-Type": "application/json",
    }
    for query in queries[:2]:
        response = requests.post(
            settings.serper_search_url,
            headers=headers,
            json={"q": query, "num": 5},
            timeout=settings.serper_timeout_seconds,
        )
        if response.status_code >= 400:
            raise SerperError(f"serper request failed with status {response.status_code}")
        results.append({"query": query, "payload": _normalize_search_response(response.json())})
    return {"queries": queries[:2], "results": results}
