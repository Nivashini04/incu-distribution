
from fastapi import BackgroundTasks

from database import create_or_get_job, update_job, get_job
from connectors import get_connector
from destinations import DESTINATIONS
from rules import check_posting_rules


def process_publish_job(job_id: str, request_data: dict):
    """Process a publishing job and update its status and progress."""

    update_job(
        job_id,
        "running",
        progress=10,
    )

    try:
        destination = request_data["destination"]
        content = request_data["content"]
        key = request_data["idempotency_key"]

        # Find the destination configuration.
        policy = DESTINATIONS.get(destination)

        if policy is None:
            update_job(
                job_id,
                "failed",
                progress=100,
                error={
                    "code": "DESTINATION_NOT_FOUND",
                    "message": "Destination is not configured.",
                },
            )
            return

        # Check the destination's posting rules.
        rule_result = check_posting_rules(
            content=content,
            is_self_promotional=request_data["is_self_promotional"],
            is_ai_generated=request_data["is_ai_generated"],
            allow_self_promotion=policy["allow_self_promotion"],
            allow_links=policy["allow_links"],
            require_ai_disclosure=policy["require_ai_disclosure"],
        )

        if not rule_result["allowed"]:
            update_job(
                job_id,
                "failed",
                progress=100,
                error={
                    "code": "POST_BLOCKED",
                    "message": "The post did not pass destination rules.",
                    "reasons": rule_result["reasons"],
                },
            )
            return

        # Get the correct connector.
        connector_type = policy["connector_type"]
        connector = get_connector(connector_type)

        # Record progress before publishing.
        update_job(
            job_id,
            "running",
            progress=50,
        )

        # Execute the connector.
        result = connector.publish(
            destination=destination,
            content=content,
            idempotency_key=key,
        )

        # Provide a URL where the job result can be retrieved.
        result_url = f"/api/v1/jobs/{job_id}"

        update_job(
            job_id,
            "succeeded",
            result=result,
            progress=100,
            result_url=result_url,
        )

    except ValueError as exc:
        message = str(exc)

        if "idempotency" in message.lower():
            error = {
                "code": "IDEMPOTENCY_CONFLICT",
                "message": "The key was reused with different content.",
            }
        else:
            error = {
                "code": "INVALID_REQUEST",
                "message": message,
            }

        update_job(
            job_id,
            "failed",
            progress=100,
            error=error,
        )

    except Exception:
        update_job(
            job_id,
            "failed",
            progress=100,
            error={
                "code": "INTERNAL_ERROR",
                "message": "The publishing job failed.",
            },
        )


def create_publish_job(
    request_data: dict,
    background_tasks: BackgroundTasks,
):
    """Create a job or return an existing job for the same request."""

    job, created, conflict = create_or_get_job(request_data)

    if conflict:
        return {
            "conflict": True,
            "error": {
                "code": "IDEMPOTENCY_CONFLICT",
                "message": (
                    "This key was already used with a different request."
                ),
            },
        }

    # Schedule processing only for newly created jobs.
    if created:
        background_tasks.add_task(
            process_publish_job,
            job["job_id"],
            request_data,
        )

        # The task may finish before this function returns,
        # particularly when using FastAPI's TestClient.
        job = get_job(job["job_id"])

    return job
