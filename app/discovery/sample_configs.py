CLUTCH_GENERIC_CONFIG = {
    "source_name": "clutch",
    "version": "2026-04-03.1",
    "allowed_domains": ["clutch.co"],
    "fetch": {
        "mode": "browser",
        "timeout_seconds": 45,
        "wait_for_selector": ".provider__title a[href*='/profile/']",
        "wait_for_selector_any": [
            ".provider__title a[href*='/profile/']",
            "h3 a[href*='/profile/']",
            "a.directory_profile[href*='/profile/']",
        ],
        "challenge_retries": 2,
        "post_solve_wait_seconds": 3.0,
    },
    "listing": {
        "extraction_kind": "css",
        "item_selector": ".provider__title a[href*='/profile/']",
        "fields": {
            "company_name": {"type": "text", "selector": ":scope"},
            "detail_url": {"type": "attr", "selector": ":scope", "attr": "href", "absolute_url": True},
        },
        "pagination": {"type": "query_param", "param": "page", "start_page": 1},
    },
    "dedupe_keys": ["detail_url", "company_name"],
}

WEBFLOW_CERTIFIED_PARTNERS_CONFIG = {
    "source_name": "webflow_certified_partners",
    "version": "2026-04-03.1",
    "allowed_domains": ["webflow.com", "experts.webflow.com"],
    "fetch": {"mode": "http", "timeout_seconds": 30},
    "listing": {
        "extraction_kind": "json_ld_item_list",
        "json_ld_selector": "script[type='application/ld+json']",
        "item_path": ["mainEntity", "itemListElement"],
        "fields": {
            "company_name": {"type": "path", "path": ["item", "name"]},
            "website_url": {"type": "path", "path": ["item", "url"]},
            "description": {"type": "path", "path": ["item", "description"]},
            "location": {"type": "path", "path": ["item", "address", "addressCountry"]},
            "price_range": {"type": "path", "path": ["item", "priceRange"]},
        },
        "pagination": {"type": "none"},
    },
    "dedupe_keys": ["company_name", "website_url"],
}

SHOPIFY_PARTNERS_CONFIG = {
    "source_name": "shopify_partners_directory",
    "version": "2026-04-03.1",
    "allowed_domains": ["shopify.com"],
    "fetch": {"mode": "http", "timeout_seconds": 30},
    "listing": {
        "extraction_kind": "css",
        "item_selector": "div[data-component-name='listing-profile-card']",
        "fields": {
            "company_name": {"type": "text", "selector": "h3"},
            "detail_url": {
                "type": "attr",
                "selector": "a[href*='/partners/directory/partner/']",
                "attr": "href",
                "absolute_url": True,
            },
            "card_text": {"type": "text", "selector": "a[href*='/partners/directory/partner/']"},
            "location": {
                "type": "regex",
                "source_field": "card_text",
                "pattern": r"\|\s*(.*?)\s*Price range",
            },
            "services_summary": {
                "type": "regex",
                "source_field": "card_text",
                "pattern": r"(?:Contact for pricing\s+)?Services\s*(.*)$",
            },
        },
        "pagination": {"type": "query_param", "param": "page", "start_page": 1},
    },
    "dedupe_keys": ["detail_url", "company_name"],
}
