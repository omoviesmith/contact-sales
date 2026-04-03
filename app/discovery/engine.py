from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

from app.discovery.extractors import extract_css_items, extract_json_ld_items
from app.discovery.fetchers import fetch_browser, fetch_http
from app.schemas import ScraperConfigPayload


def _build_page_url(directory_url: str, config: ScraperConfigPayload, page_number: int) -> str:
    pagination = config.listing.pagination
    if pagination.type == "none":
        return directory_url
    parsed = urlparse(directory_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[pagination.param or "page"] = str(page_number)
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _fetch_html(directory_url: str, config: ScraperConfigPayload) -> str:
    if config.fetch.mode == "browser":
        return fetch_browser(directory_url, config.fetch.timeout_seconds, config.fetch.wait_for_selector)
    return fetch_http(directory_url, config.fetch.timeout_seconds)


def _extract_listing(html: str, config: ScraperConfigPayload, *, page_url: str) -> list[dict]:
    if config.listing.extraction_kind == "css":
        return extract_css_items(html, config.listing, base_url=page_url)
    return extract_json_ld_items(html, config.listing, base_url=page_url)


def _extract_detail(html: str, config: ScraperConfigPayload, *, detail_url: str) -> dict:
    if not config.detail:
        return {}
    if config.detail.extraction_kind == "css":
        items = extract_css_items(html, config.detail, base_url=detail_url)
    else:
        items = extract_json_ld_items(html, config.detail, base_url=detail_url)
    return items[0] if items else {}


def run_scraper(
    *,
    directory_url: str,
    config: ScraperConfigPayload,
    max_pages: int,
    max_items: int,
) -> tuple[list[dict], dict]:
    items: list[dict] = []
    pages_fetched = 0
    detail_fetches = 0
    for page_number in range(config.listing.pagination.start_page, config.listing.pagination.start_page + max_pages):
        page_url = _build_page_url(directory_url, config, page_number)
        html = _fetch_html(page_url, config)
        page_items = _extract_listing(html, config, page_url=page_url)
        pages_fetched += 1
        for row in page_items:
            detail_url = row.get("detail_url")
            if detail_url and config.detail:
                detail_html = _fetch_html(detail_url, config)
                row.update(_extract_detail(detail_html, config, detail_url=detail_url))
                detail_fetches += 1
            items.append(row)
            if len(items) >= max_items:
                return items, {
                    "pages_fetched": pages_fetched,
                    "items_extracted": len(items),
                    "detail_fetches": detail_fetches,
                }
    return items, {
        "pages_fetched": pages_fetched,
        "items_extracted": len(items),
        "detail_fetches": detail_fetches,
    }
