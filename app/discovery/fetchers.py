import requests

from app.discovery.capsolver import CapsolverError, solve_turnstile
from app.logging_utils import get_logger


logger = get_logger(__name__)

TURNSTILE_INIT_SCRIPT = """
(() => {
  window.__contactSalesTurnstile = { params: null, lastToken: null };

  const storeParams = (params) => {
    if (!params) return;
    window.__contactSalesTurnstile.params = {
      sitekey: params.sitekey || null,
      action: params.action || null,
      cData: params.cData || params.cdata || null,
      pageData: params.chlPageData || params.pagedata || null,
      hasCallback: typeof params.callback === "function",
    };
    if (typeof params.callback === "function") {
      window.__contactSalesTurnstile.callback = params.callback;
    }
  };

  const patchTurnstile = (turnstile) => {
    if (!turnstile || typeof turnstile.render !== "function" || turnstile.__contactSalesPatched) return turnstile;
    const originalRender = turnstile.render.bind(turnstile);
    turnstile.render = (container, params = {}) => {
      const dataset = container && container.dataset ? container.dataset : {};
      const merged = {
        ...params,
        sitekey: params.sitekey || dataset.sitekey || null,
        action: params.action || dataset.action || null,
        cData: params.cData || params.cdata || dataset.cData || dataset.cdata || null,
        chlPageData: params.chlPageData || params.pagedata || dataset.chlPageData || dataset.pagedata || null,
      };
      storeParams(merged);
      return originalRender(container, params);
    };
    turnstile.__contactSalesPatched = true;
    return turnstile;
  };

  let currentTurnstile = null;
  Object.defineProperty(window, "turnstile", {
    configurable: true,
    get() {
      return currentTurnstile;
    },
    set(value) {
      currentTurnstile = patchTurnstile(value);
    },
  });

  const captureFromDom = () => {
    const el = document.querySelector("[data-sitekey]");
    if (!el) return;
    storeParams({
      sitekey: el.getAttribute("data-sitekey"),
      action: el.getAttribute("data-action"),
      cData: el.getAttribute("data-cdata"),
      chlPageData: el.getAttribute("data-pagedata"),
    });
  };

  document.addEventListener("DOMContentLoaded", captureFromDom);
  captureFromDom();
})();
"""


def fetch_http(url: str, timeout_seconds: int) -> str:
    response = requests.get(
        url,
        timeout=timeout_seconds,
        headers={"User-Agent": "Mozilla/5.0 (compatible; ContactSalesDiscovery/1.0)"},
    )
    response.raise_for_status()
    return response.text


def _get_turnstile_params(page) -> dict | None:
    try:
        params = page.evaluate("() => window.__contactSalesTurnstile?.params || null")
    except Exception:
        return None
    if params and params.get("sitekey"):
        return params
    return None


def _page_looks_like_challenge(page) -> bool:
    html = page.content().lower()
    title = page.title().lower()
    if "just a moment" in title or "challenge" in title:
        return True
    return "cf-turnstile" in html or "challenges.cloudflare.com" in html


def _submit_turnstile_token(page, token: str) -> None:
    page.evaluate(
        """(token) => {
            window.__contactSalesTurnstile.lastToken = token;
            const selectors = [
              'textarea[name="cf-turnstile-response"]',
              'input[name="cf-turnstile-response"]',
              'textarea[name="g-recaptcha-response"]',
              'input[name="g-recaptcha-response"]'
            ];
            for (const selector of selectors) {
              const node = document.querySelector(selector);
              if (node) {
                node.value = token;
                node.dispatchEvent(new Event('input', { bubbles: true }));
                node.dispatchEvent(new Event('change', { bubbles: true }));
              }
            }
            if (window.__contactSalesTurnstile?.callback) {
              window.__contactSalesTurnstile.callback(token);
            }
        }""",
        token,
    )


def _solve_turnstile_if_present(page, url: str, timeout_seconds: int, wait_for_selector: str | None) -> None:
    params = _get_turnstile_params(page)
    if not params and not _page_looks_like_challenge(page):
        return
    if not params:
        raise CapsolverError("Cloudflare challenge detected but no Turnstile params were captured")

    token = solve_turnstile(
        website_url=url,
        website_key=params["sitekey"],
        page_action=params.get("action"),
        cdata=params.get("cData"),
        pagedata=params.get("pageData"),
    )
    _submit_turnstile_token(page, token)
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_seconds * 1000)
    except Exception:
        logger.warning("networkidle wait timed out after Turnstile token submission")
    if wait_for_selector:
        try:
            page.wait_for_selector(wait_for_selector, timeout=timeout_seconds * 1000)
        except Exception:
            logger.warning("target selector did not appear after Turnstile solve", extra={"extra_fields": {"selector": wait_for_selector}})


def fetch_browser(url: str, timeout_seconds: int, wait_for_selector: str | None = None) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
        )
        page.add_init_script(TURNSTILE_INIT_SCRIPT)
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            logger.info("networkidle not reached before continuing browser fetch", extra={"extra_fields": {"url": url}})
        _solve_turnstile_if_present(page, url, timeout_seconds, wait_for_selector)
        if wait_for_selector:
            page.wait_for_selector(wait_for_selector, state="attached", timeout=timeout_seconds * 1000)
        content = page.content()
        browser.close()
        return content
