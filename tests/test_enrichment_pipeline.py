import os
import unittest
from unittest.mock import Mock, patch

import requests

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from app.enrichment.fetchers import fetch_website_snapshot, resolve_company_website_url
from app.enrichment.parsers import build_enrichment_result


class EnrichmentPipelineTests(unittest.TestCase):
    def test_resolve_company_website_url_prefers_existing_website(self):
        resolved = resolve_company_website_url(
            website_url="https://acme.example",
            source_payload={},
            timeout_seconds=10,
        )

        self.assertEqual(resolved, "https://acme.example")

    def test_build_enrichment_result_extracts_services_and_priority(self):
        website_snapshot = {
            "pages": [
                {
                    "page_type": "homepage",
                    "title": "Acme Studio | Webflow and Shopify Agency",
                    "text": (
                        "Acme Studio is a web design and web development agency. "
                        "Founder: Jane Doe. We build Webflow and Shopify experiences."
                    ),
                },
                {
                    "page_type": "contact",
                    "title": "Contact Acme Studio",
                    "text": "Book a call with Acme Studio for web design and automation support.",
                    "has_form": True,
                    "url": "https://acme.example/contact",
                },
                {
                    "page_type": "portfolio",
                    "title": "Selected Work",
                    "text": "Clients: Stripe and Notion",
                    "url": "https://acme.example/work",
                },
            ],
            "fetched_urls": ["https://acme.example"],
            "resolved_website_url": "https://acme.example",
            "contact_form_url": "https://acme.example/contact",
            "portfolio_clients": ["Stripe", "Notion"],
        }
        search_snapshot = {
            "results": [
                {
                    "query": "Acme Studio services",
                    "payload": {
                        "organic": [
                            {
                                "title": "Acme Studio",
                                "snippet": "Shopify and Webflow agency helping brands grow online.",
                            }
                        ],
                        "knowledge_graph": {"type": "Agency", "description": "Digital agency"},
                        "related_searches": ["acme studio services"],
                    },
                }
            ]
        }

        result = build_enrichment_result(
            company_name="Acme Studio",
            website_snapshot=website_snapshot,
            search_snapshot=search_snapshot,
        )

        self.assertEqual(result["structured_output"]["founder_name"], "Jane Doe")
        self.assertIn("webflow", result["structured_output"]["service_categories"])
        self.assertIn("shopify", result["structured_output"]["service_categories"])
        self.assertEqual(result["structured_output"]["company_niche"], "agency")
        self.assertEqual(result["structured_output"]["key_client"], "Stripe")
        self.assertEqual(result["structured_output"]["company_contact_form_url"], "https://acme.example/contact")
        self.assertGreater(result["priority_score"], 40)
        self.assertEqual(result["structured_output"]["submission_status_recommendation"], "submission_pending")

    def test_build_enrichment_result_detects_dnc_signals(self):
        website_snapshot = {
            "pages": [
                {
                    "page_type": "homepage",
                    "title": "Support Desk",
                    "text": "Customer support only. Existing customers only. No solicitation.",
                }
            ],
            "fetched_urls": ["https://support.example"],
            "resolved_website_url": "https://support.example",
        }
        search_snapshot = {"results": []}

        result = build_enrichment_result(
            company_name="Support Desk",
            website_snapshot=website_snapshot,
            search_snapshot=search_snapshot,
        )

        self.assertTrue(result["dnc_recommended"])
        self.assertIn("no_solicitation", result["dnc_reason_codes"])
        self.assertEqual(result["structured_output"]["submission_status_recommendation"], "suppress")

    def test_fetch_website_snapshot_tries_ordered_contact_paths(self):
        homepage_html = "<html><head><title>Acme</title></head><body><a href='/about'>About</a></body></html>"
        contact_html = "<html><head><title>Hire Us</title></head><body><form action='/submit'></form></body></html>"

        def fake_response(url, body, status=200):
            response = Mock()
            response.url = url
            response.text = body
            response.status_code = status
            response.raise_for_status = Mock()
            return response

        requested_urls = []

        def fake_get(url, timeout, allow_redirects):
            requested_urls.append(url)
            if url == "https://acme.example":
                return fake_response(url, homepage_html)
            if url == "https://acme.example/about":
                return fake_response(url, "<html><body>About page</body></html>")
            if url == "https://acme.example/services":
                raise requests.RequestException("missing")
            if url == "https://acme.example/what-we-do":
                raise requests.RequestException("missing")
            if url == "https://acme.example/solutions":
                raise requests.RequestException("missing")
            if url == "https://acme.example/expertise":
                raise requests.RequestException("missing")
            if url in {
                "https://acme.example/contact",
                "https://acme.example/contact-us",
                "https://acme.example/kontakt",
                "https://acme.example/en/contact",
                "https://acme.example/get-in-touch",
                "https://acme.example/connect",
                "https://acme.example/work-with-us",
                "https://acme.example/hire-us",
            }:
                if url == "https://acme.example/hire-us":
                    return fake_response(url, contact_html)
                raise requests.RequestException("missing")
            if url == "https://acme.example/portfolio":
                raise requests.RequestException("missing")
            if url == "https://acme.example/work":
                raise requests.RequestException("missing")
            if url == "https://acme.example/case-studies":
                raise requests.RequestException("missing")
            if url == "https://acme.example/projects":
                raise requests.RequestException("missing")
            if url == "https://acme.example/clients":
                raise requests.RequestException("missing")
            raise AssertionError(f"unexpected url {url}")

        with patch("requests.Session.get", side_effect=fake_get):
            snapshot = fetch_website_snapshot("https://acme.example", timeout_seconds=10)

        self.assertEqual(snapshot["contact_form_url"], "https://acme.example/hire-us")
        self.assertIn("https://acme.example/hire-us", requested_urls)
        self.assertLess(
            requested_urls.index("https://acme.example/contact"),
            requested_urls.index("https://acme.example/hire-us"),
        )

    def test_root_fallback_does_not_count_as_contact_form_url_without_form(self):
        homepage_html = "<html><head><title>Acme</title></head><body><a href='/about'>About</a></body></html>"

        def fake_response(url, body, status=200):
            response = Mock()
            response.url = url
            response.text = body
            response.status_code = status
            response.raise_for_status = Mock()
            return response

        def fake_get(url, timeout, allow_redirects):
            if url == "https://acme.example":
                return fake_response(url, homepage_html)
            if url == "https://acme.example/about":
                return fake_response(url, "<html><body>About page</body></html>")
            raise requests.RequestException("missing")

        with patch("requests.Session.get", side_effect=fake_get):
            snapshot = fetch_website_snapshot("https://acme.example", timeout_seconds=10)

        self.assertIsNone(snapshot["contact_form_url"])

    def test_founder_heading_false_positive_is_rejected(self):
        website_snapshot = {
            "pages": [
                {
                    "page_type": "homepage",
                    "title": "Agency Site",
                    "text": "Founder: Our Services. Contact us for ecommerce redesign.",
                }
            ],
            "fetched_urls": ["https://agency.example"],
            "resolved_website_url": "https://agency.example",
            "contact_form_url": None,
            "portfolio_clients": [],
        }

        result = build_enrichment_result(
            company_name="Agency Site",
            website_snapshot=website_snapshot,
            search_snapshot={"results": []},
        )

        self.assertIsNone(result["structured_output"]["founder_name"])
        self.assertEqual(result["last_agent_decision"]["enrichment_extraction"]["usage_decision"], "requires_review")


if __name__ == "__main__":
    unittest.main()
