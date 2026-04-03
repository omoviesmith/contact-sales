from pathlib import Path
import os
import unittest

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.discovery.extractors import extract_css_items, extract_json_ld_items
from app.discovery.fetchers import _page_looks_like_challenge
from app.discovery.sample_configs import (
    CLUTCH_GENERIC_CONFIG,
    SHOPIFY_PARTNERS_CONFIG,
    WEBFLOW_CERTIFIED_PARTNERS_CONFIG,
)
from app.schemas import ScraperConfigPayload


FIXTURES = Path(__file__).parent / "fixtures"


class DiscoveryEngineTests(unittest.TestCase):
    def test_shopify_css_listing_config_extracts_cards(self):
        html = (FIXTURES / "shopify_browse.html").read_text(encoding="utf-8")
        config = ScraperConfigPayload.model_validate(SHOPIFY_PARTNERS_CONFIG)

        rows = extract_css_items(html, config.listing, base_url="https://www.shopify.com/ng/partners/directory/services")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["company_name"], "IT-Geeks")
        self.assertEqual(rows[0]["detail_url"], "https://www.shopify.com/partners/directory/partner/it-geeks")
        self.assertEqual(rows[0]["location"], "SALT LAKE CITY, United States")

    def test_webflow_json_ld_listing_config_extracts_item_list(self):
        html = (FIXTURES / "webflow_browse.html").read_text(encoding="utf-8")
        config = ScraperConfigPayload.model_validate(WEBFLOW_CERTIFIED_PARTNERS_CONFIG)

        rows = extract_json_ld_items(html, config.listing, base_url="https://webflow.com/certified-partners/browse")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["company_name"], "Underscore")
        self.assertEqual(rows[0]["price_range"], "$3,500+")
        self.assertEqual(rows[1]["location"], "Switzerland")

    def test_clutch_sample_config_validates_for_browser_mode(self):
        config = ScraperConfigPayload.model_validate(CLUTCH_GENERIC_CONFIG)
        html = (FIXTURES / "clutch_browse_browser.html").read_text(encoding="utf-8")

        rows = extract_css_items(html, config.listing, base_url="https://clutch.co/web-developers")

        self.assertEqual(config.fetch.mode, "browser")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["detail_url"], "https://clutch.co/profile/example-agency")

    def test_challenge_detector_identifies_cloudflare_page(self):
        class FakePage:
            def title(self):
                return "Just a moment..."

            def content(self):
                return "<html><body>cf-turnstile</body></html>"

        self.assertTrue(_page_looks_like_challenge(FakePage()))


if __name__ == "__main__":
    unittest.main()
