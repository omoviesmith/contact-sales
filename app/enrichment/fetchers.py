from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ContactSalesEnrichment/1.0)",
}

KEYWORD_PATHS = {
    "about": ["/about", "/about-us", "/company", "/our-story"],
    "services": ["/services", "/what-we-do", "/solutions", "/expertise"],
    "contact": ["/contact", "/contact-us", "/get-in-touch"],
}


@dataclass
class PageSnapshot:
    url: str
    page_type: str
    title: str | None
    meta_description: str | None
    text: str
    status_code: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "page_type": self.page_type,
            "title": self.title,
            "meta_description": self.meta_description,
            "text": self.text,
            "status_code": self.status_code,
        }


def _same_host(base_url: str, candidate_url: str) -> bool:
    return (urlparse(base_url).hostname or "").lower() == (urlparse(candidate_url).hostname or "").lower()


def _extract_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return " ".join(chunk.strip() for chunk in soup.get_text(separator=" ").split() if chunk.strip())


def _page_snapshot(url: str, page_type: str, response: requests.Response) -> PageSnapshot:
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else None
    meta_description_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_description_tag.get("content", "").strip() or None if meta_description_tag else None
    return PageSnapshot(
        url=response.url,
        page_type=page_type,
        title=title,
        meta_description=meta_description,
        text=_extract_text(soup)[:20000],
        status_code=response.status_code,
    )


def _discover_candidate_links(base_url: str, homepage_html: str) -> dict[str, str]:
    soup = BeautifulSoup(homepage_html, "html.parser")
    discovered: dict[str, str] = {}
    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if not href:
            continue
        absolute_url = urljoin(base_url, href)
        if not _same_host(base_url, absolute_url):
            continue
        normalized = absolute_url.rstrip("/")
        text = " ".join(anchor.get_text(" ", strip=True).lower().split())
        for page_type, keyword_paths in KEYWORD_PATHS.items():
            if page_type in discovered:
                continue
            if any(path in normalized.lower() for path in keyword_paths) or page_type in text:
                discovered[page_type] = absolute_url
    return discovered


def fetch_website_snapshot(website_url: str | None, *, timeout_seconds: int) -> dict[str, Any]:
    if not website_url:
        return {"pages": [], "fetched_urls": [], "resolved_website_url": None}

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    fetched_urls: list[str] = []
    pages: list[dict[str, Any]] = []

    homepage_response = session.get(website_url, timeout=timeout_seconds, allow_redirects=True)
    homepage_response.raise_for_status()
    fetched_urls.append(homepage_response.url)
    homepage = _page_snapshot(homepage_response.url, "homepage", homepage_response)
    pages.append(homepage.to_dict())

    discovered_links = _discover_candidate_links(homepage_response.url, homepage_response.text)
    for page_type, fallback_paths in KEYWORD_PATHS.items():
        candidate_url = discovered_links.get(page_type) or urljoin(homepage_response.url, fallback_paths[0])
        if candidate_url.rstrip("/") in {url.rstrip("/") for url in fetched_urls}:
            continue
        try:
            response = session.get(candidate_url, timeout=timeout_seconds, allow_redirects=True)
            if response.status_code >= 400 or not _same_host(homepage_response.url, response.url):
                continue
            fetched_urls.append(response.url)
            pages.append(_page_snapshot(response.url, page_type, response).to_dict())
        except requests.RequestException:
            continue

    return {
        "pages": pages,
        "fetched_urls": fetched_urls,
        "resolved_website_url": homepage_response.url,
    }
