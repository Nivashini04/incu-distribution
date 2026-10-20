from typing import Any


from connector_base import Connector


class AssistedConnector(Connector):
    """Prepare content for manual publishing and review."""

    def validate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if kwargs:
            destination = kwargs.get("destination")
            rendition = kwargs.get("rendition")
            content = kwargs.get("content")
        else:
            destination = args[0] if len(args) > 0 else None
            rendition = None
            content = args[1] if len(args) > 1 else None

        if isinstance(destination, dict):
            destination_name = destination.get("name") or destination.get("id")
        else:
            destination_name = destination

        if isinstance(rendition, dict):
            content = rendition.get("content") or rendition.get("text")

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

        return {"ok": True, "violations": []}

    def publish(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Create an assisted-publishing result instead of publishing externally."""

        destination = kwargs.get("destination")
        rendition = kwargs.get("rendition")
        connection = kwargs.get("connection") or {}
        idempotency_key = kwargs.get("idempotency_key", "")

        if args:
            destination = destination if destination is not None else (
                args[0] if len(args) > 0 else None
            )
            if len(args) > 1:
                rendition = rendition or {"content": args[1]}
            if len(args) > 2 and not idempotency_key:
                idempotency_key = args[2]

        if isinstance(destination, str):
            destination_config = {"name": destination}
        else:
            destination_config = destination or {}

        if isinstance(rendition, str):
            rendition = {"content": rendition}
        rendition = rendition or {}

        validation = self.validate(
            destination=destination_config,
            rendition=rendition,
        )
        if not validation["ok"]:
            raise ValueError(", ".join(validation["violations"]))

        caption = rendition.get("content") or rendition.get("text")
        destination_name = (
            destination_config.get("name")
            or destination_config.get("id")
            or "destination"
        )
        destination_url = (
            destination_config.get("deep_link")
            or destination_config.get("url")
            or connection.get("deep_link")
        )

        checklist = [
            "Review the caption and destination.",
            "Check links, self-promotion, and required AI disclosure.",
            "Sign in to the destination platform.",
            "Publish the content manually.",
            "Record the resulting post URL and publication status.",
        ]

        return {
            "platform_post_id": None,
            "live_url": None,
            "status": "awaiting_manual_publish",
            "destination": destination_name,
            "idempotency_key": idempotency_key,
            "simulation": True,
            "message": "Prepared for manual review; nothing was published automatically.",
            "assist_pack": {
                "files": [
                    {
                        "filename": "caption.txt",
                        "content": caption,
                        "content_type": "text/plain",
                    }
                ],
                "caption": caption,
                "deep_link": destination_url,
                "checklist": checklist,
            },
        }

    def get_status(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        post_id = (
            kwargs.get("platform_post_id")
            or kwargs.get("post_id")
            or (args[0] if args else None)
        )
        return {
            "status": "manual_status_unavailable",
            "platform_post_id": post_id,
            "live_url": None,
            "message": "Manual publication status must be recorded separately.",
        }

    def delete(
        self,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        post_id = (
            kwargs.get("platform_post_id")
            or kwargs.get("post_id")
            or (args[0] if args else None)
        )
        return {
            "deleted": False,
            "platform_post_id": post_id,
            "message": "Assisted publishing does not delete external posts.",
        }

    def build_assist_pack(
        self,
        rendition: dict[str, Any],
        destination: dict[str, Any],
    ) -> dict[str, Any]:
        result = self.publish(
            rendition=rendition,
            destination=destination,
            connection={},
            idempotency_key="",
        )
        return result["assist_pack"]


assisted_connector = AssistedConnector()