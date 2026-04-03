from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; ContactSalesEnrichment/1.0)",
}

BLOCKED_EXTERNAL_HOSTS = {
    "facebook.com",
    "www.facebook.com",
    "twitter.com",
    "x.com",
    "www.x.com",
    "linkedin.com",
    "www.linkedin.com",
    "youtube.com",
    "www.youtube.com",
    "instagram.com",
    "www.instagram.com",
    "tiktok.com",
    "www.tiktok.com",
    "pinterest.com",
    "www.pinterest.com",
    "shopify.dev",
    "www.shopifyacademy.com",
    "shopifystatus.com",
}

KEYWORD_PATHS = {
    "about": ["/about", "/about-us", "/company", "/our-story"],
    "services": ["/services", "/what-we-do", "/solutions", "/expertise"],
    "contact": [
        "/contact",
        "/contact-us",
        "/kontakt",
        "/en/contact",
        "/get-in-touch",
        "/connect",
        "/work-with-us",
        "/hire-us",
        "/inquiry",
        "/start-a-project",
        "/brief",
        "/",
    ],
    "portfolio": ["/portfolio", "/work", "/case-studies", "/projects", "/clients"],
}


@dataclass
class PageSnapshot:
    url: str
    page_type: str
    title: str | None
    meta_description: str | None
    text: str
    status_code: int
    has_form: bool = False
    form_action_urls: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "page_type": self.page_type,
            "title": self.title,
            "meta_description": self.meta_description,
            "text": self.text,
            "status_code": self.status_code,
            "has_form": self.has_form,
            "form_action_urls": self.form_action_urls or [],
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
    forms = soup.select("form")
    form_action_urls = []
    for form in forms:
        action = (form.get("action") or "").strip()
        if not action:
            form_action_urls.append(response.url)
            continue
        form_action_urls.append(urljoin(response.url, action))
    return PageSnapshot(
        url=response.url,
        page_type=page_type,
        title=title,
        meta_description=meta_description,
        text=_extract_text(soup)[:20000],
        status_code=response.status_code,
        has_form=bool(forms),
        form_action_urls=form_action_urls,
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


def _extract_contact_form_url(pages: list[dict[str, Any]]) -> str | None:
    preferred_types = ["contact", "homepage", "about", "services"]
    by_type = {page.get("page_type"): page for page in pages}
    for page_type in preferred_types:
        page = by_type.get(page_type)
        if page and page.get("has_form"):
            return page.get("url")
    for page in pages:
        if page.get("has_form"):
            return page.get("url")
    return by_type.get("contact", {}).get("url")


def _extract_portfolio_clients(pages: list[dict[str, Any]]) -> list[str]:
    page = next((item for item in pages if item.get("page_type") == "portfolio"), None)
    if not page:
        return []
    text = page.get("text", "")
    matches = re.findall(
        r"(?:clients?|portfolio|case studies?)[:\s]+([A-Z][A-Za-z0-9&.'-]+(?:\s+[A-Z][A-Za-z0-9&.'-]+){0,3})",
        text,
    )
    deduped: list[str] = []
    seen = set()
    for match in matches:
        cleaned = " ".join(match.split()).strip(" ,.-")
        if len(cleaned) < 3 or cleaned.lower() in seen:
            continue
        seen.add(cleaned.lower())
        deduped.append(cleaned)
    return deduped[:10]


def resolve_company_website_url(
    *,
    website_url: str | None,
    source_payload: dict[str, Any] | None,
    timeout_seconds: int,
) -> str | None:
    if website_url:
        return website_url
    source_payload = source_payload or {}
    detail_url = (source_payload.get("directory_candidate") or {}).get("detail_url")
    if not detail_url:
        return None

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    response = session.get(detail_url, timeout=timeout_seconds, allow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        absolute_url = urljoin(response.url, href)
        parsed = urlparse(absolute_url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"}:
            continue
        if not hostname or hostname.endswith("shopify.com") or hostname in BLOCKED_EXTERNAL_HOSTS:
            continue
        return absolute_url
    return None


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
        candidate_urls: list[str] = []
        discovered = discovered_links.get(page_type)
        if discovered:
            candidate_urls.append(discovered)
        for fallback_path in fallback_paths:
            fallback_url = urljoin(homepage_response.url, fallback_path)
            if fallback_url not in candidate_urls:
                candidate_urls.append(fallback_url)

        for candidate_url in candidate_urls:
            if candidate_url.rstrip("/") in {url.rstrip("/") for url in fetched_urls}:
                continue
            try:
                response = session.get(candidate_url, timeout=timeout_seconds, allow_redirects=True)
                if response.status_code >= 400 or not _same_host(homepage_response.url, response.url):
                    continue
                fetched_urls.append(response.url)
                pages.append(_page_snapshot(response.url, page_type, response).to_dict())
                break
            except requests.RequestException:
                continue

    return {
        "pages": pages,
        "fetched_urls": fetched_urls,
        "resolved_website_url": homepage_response.url,
        "contact_form_url": _extract_contact_form_url(pages),
        "portfolio_clients": _extract_portfolio_clients(pages),
    }
