from playwright.sync_api import sync_playwright
import requests


def fetch_http(url: str, timeout_seconds: int) -> str:
    response = requests.get(
        url,
        timeout=timeout_seconds,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ContactSalesDiscovery/1.0)"},
    )
    response.raise_for_status()
    return response.text


def fetch_browser(url: str, timeout_seconds: int, wait_for_selector: str | None = None) -> str:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout_seconds * 1000)
        if wait_for_selector:
            page.wait_for_selector(wait_for_selector, timeout=timeout_seconds * 1000)
        content = page.content()
        browser.close()
        return content
