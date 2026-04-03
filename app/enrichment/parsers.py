from __future__ import annotations

import re
from typing import Any


SERVICE_KEYWORDS = {
    "web_design": ["web design", "website design", "ui/ux"],
    "web_development": ["web development", "website development", "frontend", "backend", "full-stack"],
    "seo": ["seo", "search engine optimization"],
    "paid_ads": ["ppc", "paid ads", "google ads", "meta ads"],
    "shopify": ["shopify", "shopify plus"],
    "webflow": ["webflow"],
    "branding": ["branding", "brand strategy"],
    "ecommerce": ["ecommerce", "e-commerce", "online store"],
    "automation": ["automation", "crm", "email automation"],
}

NICHE_KEYWORDS = {
    "agency": ["agency", "studio", "consultancy"],
    "software": ["software", "saas", "platform", "application"],
    "ecommerce": ["shopify", "ecommerce", "e-commerce", "storefront"],
}

DNC_PATTERNS = {
    "no_solicitation": r"no solicit|unsolicited|do not solicit|no sales calls",
    "support_only": r"support requests only|customer support only|support inquiries only",
    "careers_only": r"jobs only|career inquiries|employment inquiries",
    "existing_customers_only": r"existing customers only|customers only",
}

FOUNDER_PATTERNS = [
    r"(?:founder|co-founder|ceo|owner|president)\s*[:,-]?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})",
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}),\s*(?:founder|co-founder|ceo|owner)",
]

ISSUE_KEYWORDS = {
    "slow_site": ["slow site", "performance", "page speed", "core web vitals"],
    "unclear_positioning": ["positioning", "messaging", "conversion", "copywriting"],
    "weak_lead_capture": ["contact us", "get in touch", "book a call", "lead generation"],
    "outdated_design": ["redesign", "brand refresh", "modern website"],
}


def _combined_text(website_snapshot: dict[str, Any], search_snapshot: dict[str, Any]) -> str:
    page_text = " ".join(page.get("text", "") for page in website_snapshot.get("pages", []))
    search_parts: list[str] = []
    for result in search_snapshot.get("results", []):
        payload = result.get("payload") or {}
        search_parts.append(" ".join(payload.get("related_searches", [])))
        kg_description = (payload.get("knowledge_graph") or {}).get("description")
        if kg_description:
            search_parts.append(kg_description)
        for organic in payload.get("organic", []):
            search_parts.append(
                " ".join(filter(None, [organic.get("title"), organic.get("snippet")]))
            )
    search_text = " ".join(part for part in search_parts if part)
    return " ".join(part for part in [page_text, search_text] if part).strip()


def _confidence_band(score: float) -> str:
    if score >= 0.85:
        return "high"
    if score >= 0.60:
        return "medium"
    return "low"


def infer_service_categories(text: str) -> tuple[list[str], float]:
    lowered = text.lower()
    categories = [name for name, keywords in SERVICE_KEYWORDS.items() if any(keyword in lowered for keyword in keywords)]
    if not categories:
        return [], 0.35
    confidence = min(0.55 + 0.08 * len(categories), 0.9)
    return categories, confidence


def infer_company_niche(text: str) -> tuple[str | None, float]:
    lowered = text.lower()
    for niche, keywords in NICHE_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return niche, 0.78
    return None, 0.3


def infer_founder_name(text: str) -> tuple[str | None, float]:
    for pattern in FOUNDER_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(), 0.74
    return None, 0.25


def detect_dnc(text: str) -> tuple[bool, list[str], float]:
    reason_codes = [code for code, pattern in DNC_PATTERNS.items() if re.search(pattern, text.lower())]
    if not reason_codes:
        return False, [], 0.25
    confidence = min(0.7 + 0.08 * len(reason_codes), 0.95)
    return True, reason_codes, confidence


def infer_client_issues(text: str) -> tuple[list[str], float]:
    lowered = text.lower()
    issues = [name for name, keywords in ISSUE_KEYWORDS.items() if any(keyword in lowered for keyword in keywords)]
    if not issues:
        return [], 0.4
    return issues, min(0.6 + 0.1 * len(issues), 0.88)


def build_personalization_context(
    *,
    company_name: str,
    company_niche: str | None,
    service_categories: list[str],
    website_snapshot: dict[str, Any],
) -> tuple[str | None, float]:
    homepage = next((page for page in website_snapshot.get("pages", []) if page.get("page_type") == "homepage"), {})
    title = homepage.get("title")
    if title and service_categories:
        return (
            f"{company_name} appears to operate as a {company_niche or 'digital'} business focused on "
            f"{', '.join(service_categories[:3])}.",
            0.76,
        )
    if title:
        return f"{company_name} has an active website presence with a clearly branded homepage.", 0.62
    return None, 0.3


def derive_partner_client(search_snapshot: dict[str, Any], text: str) -> tuple[str | None, float]:
    kg = next((result.get("payload", {}).get("knowledge_graph", {}) for result in search_snapshot.get("results", [])), {})
    if kg.get("type"):
        return kg["type"], 0.66
    if "partner" in text.lower():
        return "partner_network_member", 0.61
    return None, 0.3


def compute_priority_score(
    *,
    service_categories: list[str],
    company_niche: str | None,
    dnc_recommended: bool,
    website_snapshot: dict[str, Any],
) -> tuple[float, list[str]]:
    score = 20.0
    reasons = []
    if website_snapshot.get("pages"):
        score += 20
        reasons.append("website_reachable")
    if service_categories:
        score += min(30, len(service_categories) * 8)
        reasons.append("service_signals_detected")
    if company_niche:
        score += 10
        reasons.append("niche_identified")
    if dnc_recommended:
        score = max(0.0, score - 50)
        reasons.append("dnc_penalty")
    return min(score, 100.0), reasons


def build_enrichment_result(
    *,
    company_name: str,
    website_snapshot: dict[str, Any],
    search_snapshot: dict[str, Any],
) -> dict[str, Any]:
    text = _combined_text(website_snapshot, search_snapshot)
    founder_name, founder_confidence = infer_founder_name(text)
    company_niche, niche_confidence = infer_company_niche(text)
    service_categories, service_confidence = infer_service_categories(text)
    partner_client, partner_confidence = derive_partner_client(search_snapshot, text)
    client_issues, issues_confidence = infer_client_issues(text)
    personalization_context, personalization_confidence = build_personalization_context(
        company_name=company_name,
        company_niche=company_niche,
        service_categories=service_categories,
        website_snapshot=website_snapshot,
    )
    dnc_recommended, dnc_reason_codes, dnc_confidence = detect_dnc(text)
    priority_score, priority_reasons = compute_priority_score(
        service_categories=service_categories,
        company_niche=company_niche,
        dnc_recommended=dnc_recommended,
        website_snapshot=website_snapshot,
    )

    field_confidence = {
        "founder_name": founder_confidence,
        "company_niche": niche_confidence,
        "service_categories": service_confidence,
        "partner_client": partner_confidence,
        "client_issues": issues_confidence,
        "personalization_context": personalization_confidence,
        "do_not_contact_signal": dnc_confidence,
    }
    overall = round(sum(field_confidence.values()) / len(field_confidence), 2)
    structured_output = {
        "founder_name": founder_name,
        "company_niche": company_niche,
        "service_categories": service_categories,
        "partner_client": partner_client,
        "client_issues": client_issues,
        "total_num_issues": len(client_issues),
        "personalization_context": personalization_context,
        "do_not_contact_signal": dnc_recommended,
        "submission_status_recommendation": "suppress" if dnc_recommended else "submission_pending",
    }
    return {
        "structured_output": structured_output,
        "field_confidence": field_confidence,
        "confidence_summary": {
            "overall": overall,
            "band": _confidence_band(overall),
            "fields": {name: {"score": score, "band": _confidence_band(score)} for name, score in field_confidence.items()},
        },
        "last_agent_decision": {
            "enrichment_extraction": {
                "mode": "deterministic_heuristic",
                "usage_decision": "used",
                "confidence": overall,
            },
            "dnc_classifier": {
                "mode": "deterministic_heuristic",
                "usage_decision": "used" if dnc_recommended else "fallback_used",
                "confidence": dnc_confidence,
                "reason_codes": dnc_reason_codes,
            },
            "lead_prioritization": {
                "mode": "deterministic_heuristic",
                "usage_decision": "used",
                "confidence": 0.72,
                "priority_score": priority_score,
                "priority_reasons": priority_reasons,
            },
        },
        "dnc_recommended": dnc_recommended,
        "dnc_reason_codes": dnc_reason_codes,
        "priority_score": priority_score,
        "priority_reasons": priority_reasons,
    }
