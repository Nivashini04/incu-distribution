
from typing import Optional

from fastapi import FastAPI, BackgroundTasks, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from connectors import get_connector
from destinations import DESTINATIONS
from rules import check_posting_rules
from jobs import create_publish_job
from database import get_job



app = FastAPI(
    title="IncuBrix Distribution Network",
    version="1.0.0",
    description=(
        "A distribution service with posting rules, "
        "background jobs, and connector interfaces."
    ),
)



class PublishRequest(BaseModel):
    destination: str = Field(min_length=1)
    content: str = Field(min_length=1)
    idempotency_key: Optional[str] = None
    is_self_promotional: bool = False
    is_ai_generated: bool = False


def resolve_idempotency_key(
    header_key: Optional[str],
    body_key: Optional[str],
) -> Optional[str]:
    """Prefer the HTTP header; retain compatibility with older clients."""
    if header_key and body_key and header_key != body_key:
        return None
    return header_key or body_key


def error_response(
    status_code: int,
    code: str,
    message: str,
    **details,
):
    """Return a consistent JSON error envelope."""
    error = {
        "code": code,
        "message": message,
    }
    error.update(details)

    return JSONResponse(
        status_code=status_code,
        content={"error": error},
    )


@app.get("/")
def home():
    return {"message": "IncuBrix Distribution API is running"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    return {"status": "ready"}


@app.post("/api/v1/posts")
def create_post(
    request: PublishRequest,
    idempotency_header: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    idempotency_key = resolve_idempotency_key(
        idempotency_header,
        request.idempotency_key,
    )

    if not idempotency_key:
        return error_response(
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Provide an Idempotency-Key header.",
        )

    policy = DESTINATIONS.get(request.destination)

    if policy is None:
        return error_response(
            404,
            "DESTINATION_NOT_FOUND",
            "The requested destination is not configured.",
        )

    rule_result = check_posting_rules(
        content=request.content,
        is_self_promotional=request.is_self_promotional,
        is_ai_generated=request.is_ai_generated,
        allow_self_promotion=policy["allow_self_promotion"],
        allow_links=policy["allow_links"],
        require_ai_disclosure=policy["require_ai_disclosure"],
    )

    if not rule_result["allowed"]:
        return error_response(
            422,
            "POST_BLOCKED",
            "The content violates destination rules.",
            reasons=rule_result["reasons"],
        )

    try:
        connector = get_connector(policy["connector_type"])
        return connector.publish(
            destination=request.destination,
            content=request.content,
            idempotency_key=idempotency_key,
        )
    except ValueError:
        return error_response(
            409,
            "IDEMPOTENCY_CONFLICT",
            "The idempotency key was reused with different content.",
        )


@app.post("/api/v1/jobs", status_code=202)
def submit_job(
    request: PublishRequest,
    background_tasks: BackgroundTasks,
    idempotency_header: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    idempotency_key = resolve_idempotency_key(
        idempotency_header,
        request.idempotency_key,
    )

    if not idempotency_key:
        return error_response(
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Provide an Idempotency-Key header.",
        )

    job_request = request.model_dump()
    job_request["idempotency_key"] = idempotency_key

    result = create_publish_job(
        job_request,
        background_tasks,
    )

    if result.get("conflict"):
        return JSONResponse(
            status_code=409,
            content={"error": result["error"]},
        )

    return result


@app.get("/api/v1/jobs/{job_id}")
def read_job(job_id: str):
    job = get_job(job_id)

    if job is None:
        return error_response(
            404,
            "JOB_NOT_FOUND",
            "The requested job does not exist.",
        )

    return job


@app.post("/connector/v1/{connector_key}/validate")
def connector_validate(
    connector_key: str,
    request: PublishRequest,
    idempotency_header: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    try:
        connector = get_connector(connector_key)
    except ValueError:
        return error_response(
            404,
            "CONNECTOR_NOT_FOUND",
            "The requested connector is not supported.",
        )

    idempotency_key = resolve_idempotency_key(
        idempotency_header,
        request.idempotency_key,
    )

    return connector.validate(
        destination=request.destination,
        content=request.content,
        idempotency_key=idempotency_key,
    )


@app.post("/connector/v1/{connector_key}/publish")
def connector_publish(
    connector_key: str,
    request: PublishRequest,
    idempotency_header: Optional[str] = Header(
        default=None,
        alias="Idempotency-Key",
    ),
):
    idempotency_key = resolve_idempotency_key(
        idempotency_header,
        request.idempotency_key,
    )

    if not idempotency_key:
        return error_response(
            400,
            "IDEMPOTENCY_KEY_REQUIRED",
            "Provide an Idempotency-Key header.",
        )

    try:
        connector = get_connector(connector_key)

        return connector.publish(
            destination=request.destination,
            content=request.content,
            idempotency_key=idempotency_key,
        )
    except ValueError:
        return error_response(
            409,
            "PUBLISH_CONFLICT",
            "The request could not be processed because of a value or idempotency conflict.",
        )


@app.get("/connector/v1/{connector_key}/status/{post_id}")
def connector_status(
    connector_key: str,
    post_id: str,
):
    try:
        connector = get_connector(connector_key)
    except ValueError:
        return error_response(
            404,
            "CONNECTOR_NOT_FOUND",
            "The requested connector is not supported.",
        )

    return connector.get_status(post_id)


@app.delete("/connector/v1/{connector_key}/posts/{post_id}")
def connector_delete(
    connector_key: str,
    post_id: str,
):
    try:
        connector = get_connector(connector_key)
    except ValueError:
        return error_response(
            404,
            "CONNECTOR_NOT_FOUND",
            "The requested connector is not supported.",
        )

    return connector.delete(post_id)
