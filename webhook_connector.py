
import hashlib
import hmac
import json
import os
import time
import uuid
from typing import Any

import httpx
from connector_base import Connector


class WebhookConnector(Connector):
    """Send payloads to a webhook endpoint with an HMAC-SHA256 signature."""

    def validate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        url = kwargs.get("url") or os.getenv("WEBHOOK_URL")
        secret = kwargs.get("secret") or os.getenv("WEBHOOK_SECRET")
        errors = []

        if not url:
            errors.append("WEBHOOK_URL is required.")
        elif not url.startswith("https://") and not url.startswith("http://localhost"):
            errors.append("Webhook URL must use HTTPS (except localhost tests).")

        if not secret:
            errors.append("WEBHOOK_SECRET is required.")

        return {"ok": not errors, "violations": errors}

    def publish(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        url = kwargs.get("url") or os.getenv("WEBHOOK_URL")
        secret = kwargs.get("secret") or os.getenv("WEBHOOK_SECRET")
        payload = kwargs.get("payload", {})
        validation = self.validate(url=url, secret=secret)

        if not validation["ok"]:
            return {"success": False, "errors": validation["violations"]}

        body = json.dumps(
            payload, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
        timestamp = str(int(time.time()))
        signed_data = timestamp.encode("utf-8") + b"." + body
        signature = hmac.new(
            secret.encode("utf-8"), signed_data, hashlib.sha256
        ).hexdigest()
        delivery_id = str(kwargs.get("idempotency_key") or uuid.uuid4())

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Signature": "sha256=" + signature,
            "X-Webhook-Delivery": delivery_id,
            "Idempotency-Key": delivery_id,
        }

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(url, content=body, headers=headers)

            return {
                "success": response.is_success,
                "status_code": response.status_code,
                "delivery_id": delivery_id,
                "response": response.text[:1000],
            }
        except httpx.HTTPError as exc:
            return {
                "success": False,
                "delivery_id": delivery_id,
                "error": str(exc),
            }

    def get_status(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "status": "unsupported",
            "message": "Generic webhooks have no standard status endpoint.",
        }

    def delete(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {
            "deleted": False,
            "message": "A delivered webhook generally cannot be recalled.",
        }


webhook_connector = WebhookConnector()
