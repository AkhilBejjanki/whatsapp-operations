"""Client for Meta's WhatsApp Cloud API (Graph API).

`get_client()` returns a MockWhatsAppClient when WHATSAPP_MOCK=true, so the whole app
can be used before a real WhatsApp Business number is set up.
"""

import json
import uuid
from typing import Any

import httpx
import redis

from .config import settings


class WhatsAppAPIError(Exception):
    def __init__(self, http_status: int, code: int | None, title: str, detail: str = "", raw: Any = None):
        self.http_status = http_status
        self.code = code
        self.title = title
        self.detail = detail
        self.raw = raw
        super().__init__(f"[{code}] {title}: {detail}" if detail else f"[{code}] {title}")

    @classmethod
    def from_response(cls, response: httpx.Response) -> "WhatsAppAPIError":
        try:
            err = response.json().get("error", {})
        except ValueError:
            err = {}
        detail = (err.get("error_data") or {}).get("details") or err.get("error_user_msg") or ""
        return cls(
            http_status=response.status_code,
            code=err.get("code"),
            title=err.get("message") or f"HTTP {response.status_code}",
            detail=detail,
            raw=err,
        )


class WhatsAppClient:
    def __init__(self, access_token: str, timeout: float = 30):
        self.base_url = f"https://graph.facebook.com/{settings.graph_api_version}"
        self._http = httpx.Client(
            timeout=timeout, headers={"Authorization": f"Bearer {access_token}"}
        )

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path_or_url: str, **kwargs) -> dict:
        url = path_or_url if path_or_url.startswith("http") else f"{self.base_url}/{path_or_url.lstrip('/')}"
        response = self._http.request(method, url, **kwargs)
        if response.is_error:
            raise WhatsAppAPIError.from_response(response)
        return response.json() if response.content else {}

    # --- Phone number / account -------------------------------------------------

    def get_phone_number(self, phone_number_id: str) -> dict:
        data = self._request(
            "GET",
            phone_number_id,
            params={"fields": "display_phone_number,verified_name,quality_rating"},
        )
        # Optional field; ignore if Meta has renamed or removed it.
        try:
            extra = self._request("GET", phone_number_id, params={"fields": "messaging_limit_tier"})
            data["messaging_limit_tier"] = extra.get("messaging_limit_tier")
        except WhatsAppAPIError:
            pass
        return data

    def list_phone_number_ids(self, waba_id: str) -> list[str]:
        data = self._request("GET", f"{waba_id}/phone_numbers", params={"fields": "id", "limit": 100})
        return [p["id"] for p in data.get("data", [])]

    def subscribe_app(self, waba_id: str) -> dict:
        """Tell Meta to send this WABA's webhooks (statuses, template updates) to our app."""
        return self._request("POST", f"{waba_id}/subscribed_apps")

    def register_phone(self, phone_number_id: str, pin: str) -> dict:
        return self._request(
            "POST", f"{phone_number_id}/register", json={"messaging_product": "whatsapp", "pin": pin}
        )

    # --- Templates --------------------------------------------------------------

    def list_templates(self, waba_id: str) -> list[dict]:
        fields = "id,name,language,status,category,components,parameter_format,rejected_reason"
        results: list[dict] = []
        data = self._request(
            "GET", f"{waba_id}/message_templates", params={"fields": fields, "limit": 100}
        )
        while True:
            results.extend(data.get("data", []))
            next_url = (data.get("paging") or {}).get("next")
            if not next_url:
                return results
            data = self._request("GET", next_url)

    def create_template(self, waba_id: str, payload: dict) -> dict:
        return self._request("POST", f"{waba_id}/message_templates", json=payload)

    def delete_template(self, waba_id: str, name: str) -> dict:
        return self._request("DELETE", f"{waba_id}/message_templates", params={"name": name})

    # --- Sending ----------------------------------------------------------------

    def send_template(
        self, phone_number_id: str, to: str, name: str, language: str, components: list[dict]
    ) -> dict:
        template: dict[str, Any] = {"name": name, "language": {"code": language}}
        if components:
            template["components"] = components
        return self._request(
            "POST",
            f"{phone_number_id}/messages",
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to.lstrip("+"),
                "type": "template",
                "template": template,
            },
        )


# --- Mock ----------------------------------------------------------------------

MOCK_TEMPLATES = [
    {
        "id": "mock_1",
        "name": "order_update",
        "language": "en",
        "status": "APPROVED",
        "category": "UTILITY",
        "parameter_format": "POSITIONAL",
        "components": [
            {"type": "BODY", "text": "Hi {{1}}, your order {{2}} is ready for pickup. Thank you for shopping with us!"},
            {"type": "FOOTER", "text": "Reply STOP to unsubscribe"},
        ],
    },
    {
        "id": "mock_2",
        "name": "festive_offer",
        "language": "en",
        "status": "APPROVED",
        "category": "MARKETING",
        "parameter_format": "POSITIONAL",
        "components": [
            {"type": "HEADER", "format": "TEXT", "text": "Festive Sale 🎉"},
            {"type": "BODY", "text": "Hello {{1}}, enjoy {{2}} off on everything this week only."},
            {"type": "BUTTONS", "buttons": [{"type": "URL", "text": "Shop now", "url": "https://example.com/{{1}}"}]},
        ],
    },
    {
        "id": "mock_3",
        "name": "new_arrivals",
        "language": "en",
        "status": "PENDING",
        "category": "MARKETING",
        "parameter_format": "POSITIONAL",
        "components": [{"type": "BODY", "text": "Hi {{1}}, new arrivals are in store!"}],
    },
]


class MockWhatsAppClient:
    """Behaves like the real API without calling Meta.

    In mock mode the worker also fakes webhooks. Numbers ending in 00 fail with
    131026 (not on WhatsApp), numbers ending in 1 are delivered but not read, and
    all others are read.
    """

    def __init__(self, access_token: str = "", timeout: float = 30):
        self._redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)

    def close(self) -> None:
        self._redis.close()

    def get_phone_number(self, phone_number_id: str) -> dict:
        return {
            "id": phone_number_id,
            "display_phone_number": "+91 90000 00000",
            "verified_name": "Demo Business (mock)",
            "quality_rating": "GREEN",
            "messaging_limit_tier": "TIER_250",
        }

    def list_phone_number_ids(self, waba_id: str) -> list[str]:
        return []  # mock accepts any phone number id

    def subscribe_app(self, waba_id: str) -> dict:
        return {"success": True}

    def register_phone(self, phone_number_id: str, pin: str) -> dict:
        return {"success": True}

    def list_templates(self, waba_id: str) -> list[dict]:
        created = [json.loads(v) for v in self._redis.hvals(f"mock:templates:{waba_id}")]
        return MOCK_TEMPLATES + created

    def create_template(self, waba_id: str, payload: dict) -> dict:
        template_id = f"mock_{uuid.uuid4().hex[:8]}"
        stored = {**payload, "id": template_id, "status": "APPROVED", "parameter_format": "POSITIONAL"}
        self._redis.hset(f"mock:templates:{waba_id}", payload["name"], json.dumps(stored))
        return {"id": template_id, "status": "APPROVED", "category": payload.get("category")}

    def delete_template(self, waba_id: str, name: str) -> dict:
        self._redis.hdel(f"mock:templates:{waba_id}", name)
        return {"success": True}

    def send_template(self, phone_number_id, to, name, language, components) -> dict:
        return {
            "messaging_product": "whatsapp",
            "contacts": [{"input": to, "wa_id": to.lstrip("+")}],
            "messages": [{"id": f"wamid.MOCK{uuid.uuid4().hex}", "message_status": "accepted"}],
        }


def get_client(access_token: str) -> WhatsAppClient | MockWhatsAppClient:
    if settings.whatsapp_mock:
        return MockWhatsAppClient(access_token)
    return WhatsAppClient(access_token)
