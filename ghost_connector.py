
import os
import time
from typing import Any

import httpx

from connector_base import Connector


class GhostConnector(Connector):
    """Connector for publishing and managing posts using Ghost Admin API."""

    def __init__(
        self,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ):
        self.timeout = timeout
        self.client = client

    @staticmethod
    def _make_jwt(api_key: str) -> str:
        """Create a short-lived Ghost Admin API JWT."""

        try:
            import jwt
        except ImportError as exc:
            raise RuntimeError(
                "PyJWT is required for Ghost authentication. "
                "Install it with: pip install PyJWT"
            ) from exc

        try:
            key_id, secret = api_key.split(":", 1)
            secret_bytes = bytes.fromhex(secret)
        except ValueError as exc:
            raise ValueError(
                "Ghost Admin API key must have the format id:hex_secret."
            ) from exc

        now = int(time.time())

        return jwt.encode(
            {
                "iat": now,
                "exp": now + 300,
                "aud": "/admin/",
            },
            secret_bytes,
            algorithm="HS256",
            headers={
                "kid": key_id,
                "typ": "JWT",
            },
        )

    def _request(
        self,
        method: str,
        path: str,
        connection: dict[str, Any],
        **kwargs: Any,
    ) -> httpx.Response:
        """Send an authenticated request to the Ghost Admin API."""

        base_url = (
            connection.get("base_url")
            or connection.get("url")
            or os.getenv("GHOST_BASE_URL")
        )

        api_key = (
            connection.get("admin_api_key")
            or connection.get("api_key")
            or os.getenv("GHOST_ADMIN_API_KEY")
        )

        if not base_url:
            raise ValueError(
                "Ghost base URL is required. "
                "Configure base_url or GHOST_BASE_URL."
            )

        if not api_key:
            raise ValueError(
                "Ghost Admin API key is required. "
                "Configure admin_api_key or GHOST_ADMIN_API_KEY."
            )

        token = self._make_jwt(api_key)

        headers = {
            "Authorization": f"Ghost {token}",
            "Accept": "application/json",
        }

        extra_headers = kwargs.pop("headers", {}) or {}
        headers.update(extra_headers)

        url = f"{base_url.rstrip('/')}{path}"

        try:
            if self.client is not None:
                response = self.client.request(
                    method,
                    url,
                    headers=headers,
                    timeout=self.timeout,
                    **kwargs,
                )
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.request(
                        method,
                        url,
                        headers=headers,
                        **kwargs,
                    )

        except httpx.TimeoutException as exc:
            raise RuntimeError("Ghost request timed out.") from exc

        except httpx.RequestError as exc:
            raise RuntimeError(
                "Ghost site is currently unreachable."
            ) from exc

        if response.status_code in (401, 403):
            raise PermissionError(
                "Ghost authentication failed or access was denied."
            )

        if response.status_code == 429:
            raise RuntimeError(
                "Ghost rate limit reached; retry later."
            )

        if response.status_code >= 500:
            raise RuntimeError(
                "Ghost server is temporarily unavailable."
            )

        response.raise_for_status()
        return response

    @staticmethod
    def _content(rendition: Any) -> str:
        """Extract post content from a string or rendition dictionary."""

        if isinstance(rendition, str):
            return rendition

        if isinstance(rendition, dict):
            value = rendition.get("html") or rendition.get("content")
            value = value or rendition.get("text")
            return value if isinstance(value, str) else ""

        return ""

    @staticmethod
    def _destination_data(destination: Any) -> dict[str, Any]:
        if isinstance(destination, str):
            return {"name": destination}

        if isinstance(destination, dict):
            return destination

        return {}

    def validate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Validate destination and post content."""

        destination = kwargs.get("destination")
        rendition = kwargs.get("rendition")
        content = kwargs.get("content")

        if args:
            destination = destination or args[0]

            if len(args) > 1:
                content = content or args[1]

        if rendition is not None:
            content = self._content(rendition)

        destination_data = self._destination_data(destination)

        violations = []

        if not (
            destination_data.get("name")
            or destination_data.get("id")
            or destination_data.get("base_url")
            or destination_data.get("url")
        ):
            violations.append("DESTINATION_REQUIRED")

        if not isinstance(content, str) or not content.strip():
            violations.append("CONTENT_REQUIRED")

        return {
            "ok": not violations,
            "violations": violations,
        }

    def publish(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Publish a post using the Ghost Admin API."""

        destination = kwargs.get("destination")
        rendition = kwargs.get("rendition")
        content = kwargs.get("content")
        connection = kwargs.get("connection") or {}
        idempotency_key = kwargs.get("idempotency_key")

        if args:
            destination = (
                destination if destination is not None else args[0]
            )

            if len(args) > 1:
                content = content or args[1]

            if len(args) > 2:
                idempotency_key = idempotency_key or args[2]

        if rendition is not None:
            content = self._content(rendition)

        destination_data = self._destination_data(destination)

        validation = self.validate(
            destination=destination_data,
            content=content,
        )

        if not validation["ok"]:
            raise ValueError(", ".join(validation["violations"]))

        if not idempotency_key:
            raise ValueError("An idempotency key is required.")

        rendition_data = (
            rendition if isinstance(rendition, dict) else {}
        )

        title = (
            rendition_data.get("title")
            or destination_data.get("post_title")
            or "Community post"
        )

        post_data = {
            "title": title,
            "html": content,
            "status": "published",
        }

        payload = {"posts": [post_data]}

        response = self._request(
            "POST",
            "/ghost/api/admin/posts/?source=html",
            connection,
            json=payload,
            headers={
                "Idempotency-Key": str(idempotency_key),
            },
        )

        data = response.json()
        posts = data.get("posts") or []

        if not posts or not posts[0].get("id"):
            raise RuntimeError(
                "Ghost did not return a post ID."
            )

        post = posts[0]
        post_id = post["id"]

        live_url = post.get("url")

        if not live_url:
            base_url = (
                connection.get("base_url")
                or connection.get("url")
                or os.getenv("GHOST_BASE_URL")
                or ""
            ).rstrip("/")

            if base_url:
                live_url = f"{base_url}/?p={post_id}"

        return {
            "platform_post_id": str(post_id),
            "live_url": live_url,
            "status": post.get("status", "published"),
            "simulation": False,
        }

    def get_status(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Retrieve a Ghost post by its ID."""

        post_id = (
            kwargs.get("platform_post_id")
            or kwargs.get("post_id")
            or (args[0] if args else None)
        )

        connection = kwargs.get("connection") or {}

        if not post_id:
            raise ValueError("A platform post ID is required.")

        response = self._request(
            "GET",
            f"/ghost/api/admin/posts/{post_id}/",
            connection,
            params={"formats": "html"},
        )

        data = response.json()
        posts = data.get("posts") or []

        if not posts:
            return {
                "platform_post_id": str(post_id),
                "status": "not_found",
                "live_url": None,
            }

        post = posts[0]

        return {
            "platform_post_id": str(post.get("id", post_id)),
            "status": post.get("status", "unknown"),
            "live_url": post.get("url"),
            "simulation": False,
        }

    def delete(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Delete a Ghost post by its ID."""

        post_id = (
            kwargs.get("platform_post_id")
            or kwargs.get("post_id")
            or (args[0] if args else None)
        )

        connection = kwargs.get("connection") or {}

        if not post_id:
            raise ValueError("A platform post ID is required.")

        self._request(
            "DELETE",
            f"/ghost/api/admin/posts/{post_id}/",
            connection,
        )

        return {
            "deleted": True,
            "platform_post_id": str(post_id),
        }


ghost_connector = GhostConnector()
