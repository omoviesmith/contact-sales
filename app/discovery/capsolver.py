import time

import requests

from app.config import settings


class CapsolverError(RuntimeError):
    """Raised when Capsolver could not produce a usable token."""


def solve_turnstile(
    *,
    website_url: str,
    website_key: str,
    page_action: str | None = None,
    cdata: str | None = None,
    pagedata: str | None = None,
) -> str:
    if not settings.capsolver_api_key:
        raise CapsolverError("CAPSOLVER_API_KEY is not configured")

    task: dict[str, object] = {
        "type": "AntiTurnstileTaskProxyLess",
        "websiteURL": website_url,
        "websiteKey": website_key,
    }
    if page_action:
        task["metadata"] = {"action": page_action}
    if cdata:
        task["metadata"] = {**task.get("metadata", {}), "cdata": cdata}
    if pagedata:
        task["metadata"] = {**task.get("metadata", {}), "pagedata": pagedata}

    create_response = requests.post(
        "https://api.capsolver.com/createTask",
        json={"clientKey": settings.capsolver_api_key, "task": task},
        timeout=30,
    )
    create_response.raise_for_status()
    create_payload = create_response.json()
    if create_payload.get("errorId"):
        raise CapsolverError(str(create_payload))

    task_id = create_payload.get("taskId")
    if not task_id:
        raise CapsolverError("Capsolver did not return taskId")

    for _ in range(settings.capsolver_max_polls):
        time.sleep(settings.capsolver_poll_seconds)
        result_response = requests.post(
            "https://api.capsolver.com/getTaskResult",
            json={"clientKey": settings.capsolver_api_key, "taskId": task_id},
            timeout=30,
        )
        result_response.raise_for_status()
        result_payload = result_response.json()
        if result_payload.get("errorId"):
            raise CapsolverError(str(result_payload))
        if result_payload.get("status") == "ready":
            solution = result_payload.get("solution", {})
            token = solution.get("token")
            if token:
                return token
            raise CapsolverError("Capsolver ready response did not include solution.token")

    raise CapsolverError("Capsolver timed out waiting for Turnstile solution")
