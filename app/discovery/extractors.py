import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.schemas import DetailExtractionConfig, ExtractionFieldRule, ListingExtractionConfig


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    collapsed = " ".join(value.split())
    return collapsed or None


def _read_path(payload: object, path: list[str | int] | None) -> object:
    current = payload
    for segment in path or []:
        if isinstance(segment, int):
            if not isinstance(current, list) or segment >= len(current):
                return None
            current = current[segment]
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(segment)
        if current is None:
            return None
    return current


def _extract_from_rule(
    container,
    rule: ExtractionFieldRule,
    *,
    context: dict[str, str | None],
    base_url: str,
    payload: dict | None = None,
) -> str | None:
    if rule.selector == ":scope":
        element = container
    else:
        element = container.select_one(rule.selector) if container is not None and rule.selector else None
    if rule.type == "text":
        value = _normalize_text(element.get_text(" ", strip=True) if element else rule.default)
    elif rule.type == "attr":
        value = element.get(rule.attr) if element else rule.default
        value = _normalize_text(value)
    elif rule.type == "path":
        value = _read_path(payload, rule.path)
        value = _normalize_text(str(value) if value is not None else rule.default)
    else:
        source_value = context.get(rule.source_field or "")
        if source_value is None:
            value = rule.default
        else:
            match = re.search(rule.pattern or "", source_value, re.IGNORECASE | re.DOTALL)
            value = _normalize_text(match.group(rule.group) if match else rule.default)

    if value and rule.absolute_url:
        return urljoin(base_url, value)
    return value


def extract_css_items(html: str, config: ListingExtractionConfig | DetailExtractionConfig, *, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for item in soup.select(config.item_selector or ""):
        context: dict[str, str | None] = {}
        row: dict[str, str | None] = {}
        for field_name, rule in config.fields.items():
            value = _extract_from_rule(item, rule, context=context, base_url=base_url)
            row[field_name] = value
            context[field_name] = value
        rows.append(row)
    return rows


def _load_json_ld_documents(html: str, selector: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    documents: list[dict] = []
    for tag in soup.select(selector):
        raw = (tag.string or tag.get_text()).strip()
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            documents.extend([item for item in parsed if isinstance(item, dict)])
        elif isinstance(parsed, dict):
            documents.append(parsed)
    return documents


def extract_json_ld_items(html: str, config: ListingExtractionConfig | DetailExtractionConfig, *, base_url: str) -> list[dict]:
    rows: list[dict] = []
    for document in _load_json_ld_documents(html, config.json_ld_selector or "script[type='application/ld+json']"):
        items = _read_path(document, config.item_path)
        if not isinstance(items, list):
            continue
        for item in items:
            context: dict[str, str | None] = {}
            row: dict[str, str | None] = {}
            for field_name, rule in config.fields.items():
                value = _extract_from_rule(None, rule, context=context, base_url=base_url, payload=item)
                row[field_name] = value
                context[field_name] = value
            rows.append(row)
        if rows:
            break
    return rows
