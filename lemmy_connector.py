
import os
from typing import Any

import httpx

from connector_base import Connector


class LemmyConnector(Connector):
    """Connector for publishing and managing posts on Lemmy."""

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
        """Send an authenticated request to a Lemmy instance."""

        base_url = (
            connection.get("base_url")
            or connection.get("url")
            or os.getenv("LEMMY_BASE_URL")
        )

        access_token = (
            connection.get("access_token")
            or os.getenv("LEMMY_ACCESS_TOKEN")
        )

        if not base_url:
            raise ValueError(
                "Lemmy base URL is required. "
                "Configure base_url or LEMMY_BASE_URL."
            )

        if not access_token:
            raise ValueError(
                "Lemmy access token is required. "
                "Configure access_token or LEMMY_ACCESS_TOKEN."
            )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        # Merge optional headers without passing headers twice.
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
                "Lemmy request timed out."
            ) from exc

        except httpx.RequestError as exc:
            raise RuntimeError(
                "Lemmy instance is currently unreachable."
            ) from exc

        if response.status_code in (401, 403):
            raise PermissionError(
                "Lemmy authentication failed or access was denied."
            )

        if response.status_code == 429:
            raise RuntimeError(
                "Lemmy rate limit reached; retry later."
            )

        if response.status_code >= 500:
            raise RuntimeError(
                "Lemmy server is temporarily unavailable."
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
    def _get_destination(destination: Any) -> dict[str, Any]:
        """Normalize a destination into a dictionary."""

        if isinstance(destination, str):
            return {"community": destination}

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
            content = self._get_content(rendition)

        destination_data = self._get_destination(destination)

        community = (
            destination_data.get("community")
            or destination_data.get("name")
            or destination_data.get("id")
        )

        violations = []

        if not community:
            violations.append("DESTINATION_REQUIRED")

        if not isinstance(content, str) or not content.strip():
            violations.append("CONTENT_REQUIRED")

        return {
            "ok": not violations,
            "violations": violations,
        }

    def publish(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Create a post in a Lemmy community."""

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

        destination_data = self._get_destination(destination)

        validation = self.validate(
            destination=destination_data,
            content=content,
        )

        if not validation["ok"]:
            raise ValueError(", ".join(validation["violations"]))

        if not idempotency_key:
            raise ValueError("An idempotency key is required.")

        community = (
            destination_data.get("community")
            or destination_data.get("name")
            or destination_data.get("id")
        )

        # Lemmy's API expects a community ID, not its display name.
        community_id = (
            destination_data.get("community_id")
            or destination_data.get("id")
        )

        if not community_id:
            raise ValueError(
                "A Lemmy community_id is required to publish. "
                "Configure the destination with the numeric community ID."
            )

        rendition_data = (
            rendition if isinstance(rendition, dict) else {}
        )

        title = (
            rendition_data.get("title")
            or destination_data.get("post_title")
            or "Community post"
        )

        payload = {
            "community_id": int(community_id),
            "name": title,
            "body": content,
        }

        url = rendition_data.get("url") or destination_data.get("post_url")
        if url:
            payload["url"] = url

        # The application should enforce idempotency before making this
        # request. The header is useful for tracing but does not guarantee
        # that the Lemmy server will deduplicate requests.
        response = self._request(
            "POST",
            "/api/v3/post",
            connection,
            json=payload,
            headers={
                "Idempotency-Key": str(idempotency_key),
            },
        )

        data = response.json()
        post_view = data.get("post_view") or {}
        post = post_view.get("post") or data.get("post") or {}

        post_id = post.get("id")

        if not post_id:
            raise RuntimeError(
                "Lemmy did not return a post ID."
            )

        base_url = (
            connection.get("base_url")
            or connection.get("url")
            or os.getenv("LEMMY_BASE_URL")
            or ""
        ).rstrip("/")

        live_url = (
            f"{base_url}/post/{post_id}"
            if base_url
            else None
        )

        return {
            "platform_post_id": str(post_id),
            "live_url": live_url,
            "status": "published",
            "simulation": False,
        }

    def get_status(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Retrieve information about a Lemmy post."""

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
            "/api/v3/post",
            connection,
            params={"id": int(platform_post_id)},
        )

        data = response.json()
        post_view = data.get("post_view") or {}
        post = post_view.get("post") or data.get("post") or {}

        post_id = post.get("id", platform_post_id)

        base_url = (
            connection.get("base_url")
            or connection.get("url")
            or os.getenv("LEMMY_BASE_URL")
            or ""
        ).rstrip("/")

        live_url = (
            f"{base_url}/post/{post_id}"
            if base_url
            else None
        )

        deleted = post.get("deleted", False)
        removed = post.get("removed", False)

        if deleted or removed:
            status = "deleted"
        else:
            status = "published"

        return {
            "platform_post_id": str(post_id),
            "status": status,
            "live_url": live_url,
            "simulation": False,
        }

    def delete(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Delete a post from Lemmy."""

        platform_post_id = (
            kwargs.get("platform_post_id")
            or kwargs.get("post_id")
            or (args[0] if args else None)
        )

        connection = kwargs.get("connection") or {}

        if not platform_post_id:
            raise ValueError("A platform post ID is required.")

        self._request(
            "POST",
            "/api/v3/post/delete",
            connection,
            json={
                "post_id": int(platform_post_id),
                "deleted": True,
            },
        )

        return {
            "deleted": True,
            "platform_post_id": str(platform_post_id),
        }


lemmy_connector = LemmyConnector()
