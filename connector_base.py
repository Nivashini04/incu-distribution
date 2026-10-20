from abc import ABC, abstractmethod
from typing import Any


class Connector(ABC):
    """Base interface for IncuBrix publishing connectors."""

    @abstractmethod
    def validate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Validate a rendition against a destination."""
        raise NotImplementedError

    @abstractmethod
    def publish(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Publish content using an idempotency key."""
        raise NotImplementedError

    @abstractmethod
    def get_status(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Retrieve the status of a published post."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Delete a published post when supported."""
        raise NotImplementedError

    def fetch_metrics(
        self,
        platform_post_id: str,
        connection: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "Metrics retrieval is not supported by this connector."
        )

    def refresh_auth(
        self,
        connection: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "Authentication refresh is not supported by this connector."
        )

    def build_assist_pack(
        self,
        rendition: dict[str, Any],
        destination: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError(
            "Assisted publishing is not supported by this connector."
        )