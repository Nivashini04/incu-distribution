
import os
from typing import Any

import httpx

from connector_base import Connector


class DiscourseConnector(Connector):
    """Connector for publishing and managing posts on Discourse."""

    def __init__(
        self,
        timeout: float = 15.0,
        client: httpx.Client | None = None,
    ):
        self.timeout = timeout
        self.client = client

    def _request(
        self,
        method: str,
        path: str,
        connection: dict[str, Any],
        **kwargs: Any,
    ) -> httpx.Response:
        """Send an authenticated request to the Discourse API."""

        base_url = (
            connection.get("base_url")
            or connection.get("url")
            or os.getenv("DISCOURSE_BASE_URL")
        )

        api_key = (
            connection.get("api_key")
            or os.getenv("DISCOURSE_API_KEY")
        )

        api_username = (
            connection.get("api_username")
            or os.getenv("DISCOURSE_API_USERNAME")
            or "system"
        )

        if not base_url:
            raise ValueError(
                "Discourse base URL is required. "
                "Configure base_url or DISCOURSE_BASE_URL."
            )

        if not api_key:
            raise ValueError(
                "Discourse API key is required. "
                "Configure api_key or DISCOURSE_API_KEY."
            )

        headers = {
            "Api-Key": api_key,
            "Api-Username": api_username,
            "Accept": "application/json",
        }

        # Merge extra request headers without passing the headers
        # argument twice to httpx.Client.request().
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
            raise RuntimeError(
                "Discourse request timed out."
            ) from exc

        except httpx.RequestError as exc:
            raise RuntimeError(
                "Discourse is currently unreachable."
            ) from exc

        if response.status_code in (401, 403):
            raise PermissionError(
                "Discourse authentication failed or access was denied."
            )

        if response.status_code == 429:
            raise RuntimeError(
                "Discourse rate limit reached; retry later."
            )

        if response.status_code >= 500:
            raise RuntimeError(
                "Discourse server is temporarily unavailable."
            )

        response.raise_for_status()
        return response

    @staticmethod
    def _get_content(rendition: Any) -> str:
        """Extract text content from a string or rendition dictionary."""

        if isinstance(rendition, str):
            return rendition

        if isinstance(rendition, dict):
            content = rendition.get("content") or rendition.get("text")
            return content if isinstance(content, str) else ""

        return ""

    @staticmethod
    def _get_destination_name(destination: Any) -> str | None:
        """Extract the destination name from a string or dictionary."""

        if isinstance(destination, str):
            return destination.strip() or None

        if isinstance(destination, dict):
            name = destination.get("name") or destination.get("id")
            return str(name).strip() if name else None

        return None

    def validate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Validate destination and content before publishing."""

        destination = kwargs.get("destination")
        rendition = kwargs.get("rendition")
        content = kwargs.get("content")

        if args:
            destination = destination or args[0]

            if len(args) > 1:
                content = content or args[1]

        if rendition is not None:
            content = self._get_content(rendition)

        destination_name = self._get_destination_name(destination)

        violations = []

        if not destination_name:
            violations.append("DESTINATION_REQUIRED")

        if not isinstance(content, str) or not content.strip():
            violations.append("CONTENT_REQUIRED")

        return {
            "ok": not violations,
            "violations": violations,
        }

    def publish(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Create a post on Discourse."""

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
            content = self._get_content(rendition)

        destination_name = self._get_destination_name(destination)

        validation = self.validate(
            destination=destination_name,
            content=content,
        )

        if not validation["ok"]:
            raise ValueError(
                ", ".join(validation["violations"])
            )

        if not idempotency_key:
            raise ValueError(
                "An idempotency key is required."
            )

        rendition_data = (
            rendition if isinstance(rendition, dict) else {}
        )

        title = (
            rendition_data.get("title")
            or (
                destination.get("title")
                if isinstance(destination, dict)
                else None
            )
            or "Community post"
        )

        payload: dict[str, Any] = {
            "title": title,
            "raw": content,
        }

        category_id = (
            destination.get("category_id")
            if isinstance(destination, dict)
            else None
        )

        if category_id is not None:
            payload["category"] = category_id

        response = self._request(
            "POST",
            "/posts.json",
            connection,
            json=payload,
            headers={
                "Idempotency-Key": str(idempotency_key),
            },
        )

        data = response.json()

        post_id = data.get("id")
        slug = data.get("slug")

        base_url = (
            connection.get("base_url")
            or connection.get("url")
            or os.getenv("DISCOURSE_BASE_URL")
            or ""
        ).rstrip("/")

        live_url = None

        if base_url and post_id:
            if slug:
                live_url = (
                    f"{base_url}/t/{slug}/{post_id}"
                )
            else:
                live_url = f"{base_url}/posts/{post_id}"

        return {
            "platform_post_id": str(post_id) if post_id else None,
            "live_url": live_url,
            "status": "published" if post_id else "unknown",
            "simulation": False,
        }

    def get_status(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Retrieve the status and URL of an existing Discourse post."""

        platform_post_id = (
            kwargs.get("platform_post_id")
            or kwargs.get("post_id")
            or (args[0] if args else None)
        )

        connection = kwargs.get("connection") or {}

        if not platform_post_id:
            raise ValueError("A platform post ID is required.")

        response = self._request(
            "GET",
            f"/posts/{platform_post_id}.json",
            connection,
        )

        data = response.json()
        post = data.get("post", data)

        post_id = post.get("id", platform_post_id)
        slug = post.get("slug")
        topic_id = post.get("topic_id")

        base_url = (
            connection.get("base_url")
            or connection.get("url")
            or os.getenv("DISCOURSE_BASE_URL")
            or ""
        ).rstrip("/")

        live_url = None

        if base_url:
            if slug and topic_id:
                live_url = f"{base_url}/t/{slug}/{topic_id}"
            elif slug and post_id:
                live_url = f"{base_url}/t/{slug}/{post_id}"
            elif post_id:
                live_url = f"{base_url}/posts/{post_id}"

        return {
            "platform_post_id": str(post_id),
            "status": "published",
            "live_url": live_url,
            "simulation": False,
        }

    def delete(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Delete a post from Discourse."""

        platform_post_id = (
            kwargs.get("platform_post_id")
            or kwargs.get("post_id")
            or (args[0] if args else None)
        )

        connection = kwargs.get("connection") or {}

        if not platform_post_id:
            raise ValueError("A platform post ID is required.")

        self._request(
            "DELETE",
            f"/posts/{platform_post_id}.json",
            connection,
        )

        return {
            "deleted": True,
            "platform_post_id": str(platform_post_id),
        }


discourse_connector = DiscourseConnector()
