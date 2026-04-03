import requests

from app.discovery.capsolver import CapsolverError, solve_turnstile
from app.logging_utils import get_logger
from app.schemas import FetchConfig


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


def _selector_ready_expression(state: str) -> str:
    if state == "visible":
        return """(selectors) => selectors.some((selector) => {
            const node = document.querySelector(selector);
            if (!node) return false;
            const style = window.getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
        })"""
    return "(selectors) => selectors.some((selector) => !!document.querySelector(selector))"


def _find_ready_selector(page, selectors: list[str], state: str) -> str | None:
    if not selectors:
        return None
    return page.evaluate(
        f"""(selectors) => selectors.find((selector) => {{
            const node = document.querySelector(selector);
            if (!node) return false;
            if ({'true' if state == 'attached' else 'false'}) return true;
            const style = window.getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            return style.visibility !== "hidden" && style.display !== "none" && rect.width > 0 && rect.height > 0;
        }}) || null""",
        selectors,
    )


def _wait_for_ready_selectors(
    page,
    *,
    selectors: list[str],
    state: str,
    timeout_ms: int,
    soft_wait: bool,
    url: str,
) -> str | None:
    if not selectors:
        return None
    try:
        page.wait_for_function(_selector_ready_expression(state), selectors, timeout=timeout_ms)
    except Exception:
        matched = _find_ready_selector(page, selectors, state)
        if matched:
            return matched
        if soft_wait:
            logger.warning(
                "page readiness selectors not found before timeout",
                extra={
                    "extra_fields": {
                        "url": url,
                        "selectors": selectors,
                        "wait_state": state,
                    }
                },
            )
            return None
        raise
    return _find_ready_selector(page, selectors, state)


def _solve_turnstile_if_present(page, url: str, fetch_config: FetchConfig) -> bool:
    params = _get_turnstile_params(page)
    if not params and not _page_looks_like_challenge(page):
        return False
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
        page.wait_for_load_state("networkidle", timeout=fetch_config.timeout_seconds * 1000)
    except Exception:
        logger.warning("networkidle wait timed out after Turnstile token submission")
    if fetch_config.post_solve_wait_seconds:
        page.wait_for_timeout(int(fetch_config.post_solve_wait_seconds * 1000))
    _wait_for_ready_selectors(
        page,
        selectors=fetch_config.wait_for_selector_any,
        state=fetch_config.wait_for_state,
        timeout_ms=fetch_config.timeout_seconds * 1000,
        soft_wait=True,
        url=url,
    )
    return True


def fetch_browser(url: str, fetch_config: FetchConfig) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
        )
        page.add_init_script(TURNSTILE_INIT_SCRIPT)
        page.goto(url, wait_until="domcontentloaded", timeout=fetch_config.timeout_seconds * 1000)
        selectors = list(dict.fromkeys(fetch_config.wait_for_selector_any))
        max_attempts = fetch_config.challenge_retries + 1

        for attempt in range(max_attempts):
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                logger.info("networkidle not reached before continuing browser fetch", extra={"extra_fields": {"url": url}})

            solved = _solve_turnstile_if_present(page, url, fetch_config)
            matched_selector = _wait_for_ready_selectors(
                page,
                selectors=selectors,
                state=fetch_config.wait_for_state,
                timeout_ms=fetch_config.timeout_seconds * 1000,
                soft_wait=fetch_config.soft_wait_for_ready,
                url=url,
            )
            if matched_selector:
                logger.info(
                    "browser fetch readiness selector matched",
                    extra={"extra_fields": {"url": url, "selector": matched_selector, "attempt": attempt + 1}},
                )
                break
            if selectors and not fetch_config.soft_wait_for_ready and attempt + 1 >= max_attempts:
                raise RuntimeError(f"browser fetch did not reach ready state for {url}")
            if not _page_looks_like_challenge(page):
                break
            if attempt + 1 < max_attempts:
                logger.warning(
                    "challenge page still detected after solve attempt",
                    extra={"extra_fields": {"url": url, "attempt": attempt + 1, "solved": solved}},
                )
                page.reload(wait_until="domcontentloaded", timeout=fetch_config.timeout_seconds * 1000)

        content = page.content()
        browser.close()
        return content
