from connector_base import Connector
from assisted_connector import assisted_connector
from database import save_or_get_post, get_post, delete_post
from discourse_connector import discourse_connector
from lemmy_connector import lemmy_connector
from ghost_connector import ghost_connector

class MockConnector(Connector):
    """Simulates a publishing platform using SQLite."""

    def validate(self, *args, **kwargs):
        """Validate the destination and content."""

        destination = kwargs.get("destination")
        rendition = kwargs.get("rendition")
        content = kwargs.get("content")

        if args:
            destination = destination or args[0]

            if len(args) > 1:
                content = content or args[1]

        if isinstance(destination, dict):
            destination_name = (
                destination.get("name")
                or destination.get("id")
            )
        else:
            destination_name = destination

        if isinstance(rendition, dict):
            content = (
                rendition.get("content")
                or rendition.get("text")
                or content
            )

        if not destination_name:
            return {
                "ok": False,
                "violations": ["DESTINATION_REQUIRED"],
            }

        if not isinstance(content, str) or not content.strip():
            return {
                "ok": False,
                "violations": ["CONTENT_REQUIRED"],
            }

        return {
            "ok": True,
            "violations": [],
        }

    def publish(self, *args, **kwargs):
        """Save or retrieve a simulated post using an idempotency key."""

        destination = kwargs.get("destination")
        rendition = kwargs.get("rendition")
        content = kwargs.get("content")
        idempotency_key = kwargs.get("idempotency_key")
        connection = kwargs.get("connection") or {}

        if args:
            destination = destination or args[0]

            if len(args) > 1:
                content = content or args[1]

            if len(args) > 2:
                idempotency_key = idempotency_key or args[2]

        if isinstance(destination, dict):
            destination_name = (
                destination.get("name")
                or destination.get("id")
            )
        else:
            destination_name = destination

        if isinstance(rendition, dict):
            content = (
                rendition.get("content")
                or rendition.get("text")
                or content
            )

        if not isinstance(content, str) or not content.strip():
            raise ValueError("Invalid post content.")

        if not destination_name:
            raise ValueError("Destination is required.")

        if not idempotency_key:
            raise ValueError("An idempotency key is required.")

        validation = self.validate(
            destination=destination_name,
            content=content,
        )

        if not validation["ok"]:
            raise ValueError("Invalid post content.")

        result = save_or_get_post(
            destination=destination_name,
            content=content,
            key=idempotency_key,
        )

        return {
            **result,
            "platform_post_id": result.get("platform_post_id")
            or result.get("post_id")
            or result.get("id"),
            "live_url": None,
            "simulation": True,
            "message": (
                "This is a simulated post, not a real live publication."
            ),
        }

    def get_status(self, *args, **kwargs):
        """Retrieve the status of a simulated post."""

        post_id = (
            kwargs.get("platform_post_id")
            or kwargs.get("post_id")
            or (args[0] if args else None)
        )

        post = get_post(post_id)

        if post is None:
            return {
                "status": "not_found",
                "live_url": None,
            }

        return {
            "status": post["status"],
            "live_url": None,
            "platform_post_id": post_id,
            "simulation": True,
            "message": "This is a simulated post.",
        }

    def delete(self, *args, **kwargs):
        """Delete a simulated post."""

        post_id = (
            kwargs.get("platform_post_id")
            or kwargs.get("post_id")
            or (args[0] if args else None)
        )

        deleted = delete_post(post_id)

        return {
            "deleted": deleted,
            "platform_post_id": post_id,
        }


mock_connector = MockConnector()


CONNECTORS = {
    "mock": mock_connector,
    "assisted": assisted_connector,
    "discourse": discourse_connector,
    "lemmy": lemmy_connector,
    "ghost": ghost_connector,
}


def get_connector(connector_type):
    """Return a registered connector by its type."""

    connector = CONNECTORS.get(connector_type)

    if connector is None:
        raise ValueError(
            f"Unsupported connector: {connector_type}"
        )

    return connector

from webhook_connector import webhook_connector

CONNECTORS["webhook"] = webhook_connector
