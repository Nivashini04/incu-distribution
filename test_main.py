
from uuid import uuid4

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ready():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_unknown_destination():
    response = client.post(
        "/api/v1/posts",
        json={
            "destination": "unknown-community",
            "content": "Test content",
            "idempotency_key": f"unknown-{uuid4()}",
            "is_self_promotional": False,
            "is_ai_generated": False,
        },
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DESTINATION_NOT_FOUND"


def test_ai_disclosure_required():
    response = client.post(
        "/api/v1/posts",
        json={
            "destination": "mock-community",
            "content": "A post without an AI disclosure.",
            "idempotency_key": f"disclosure-{uuid4()}",
            "is_self_promotional": False,
            "is_ai_generated": True,
        },
    )

    assert response.status_code == 422
    assert "AI_DISCLOSURE_REQUIRED" in (
        response.json()["error"]["reasons"]
    )


def test_idempotency_conflict():
    key = f"idempotency-{uuid4()}"

    first = client.post(
        "/api/v1/posts",
        json={
            "destination": "mock-community",
            "content": "AI-generated first test post.",
            "idempotency_key": key,
            "is_self_promotional": False,
            "is_ai_generated": True,
        },
    )

    assert first.status_code == 200

    second = client.post(
        "/api/v1/posts",
        json={
            "destination": "mock-community",
            "content": "AI-generated different test post.",
            "idempotency_key": key,
            "is_self_promotional": False,
            "is_ai_generated": True,
        },
    )

    assert second.status_code == 409
    assert (
        second.json()["error"]["code"]
        == "IDEMPOTENCY_CONFLICT"
    )


def test_background_job():
    response = client.post(
        "/api/v1/jobs",
        json={
            "destination": "open-community",
            "content": "Automated background job test.",
            "idempotency_key": f"job-{uuid4()}",
            "is_self_promotional": False,
            "is_ai_generated": False,
        },
    )

    assert response.status_code == 202

    job_id = response.json()["job_id"]

    job_response = client.get(f"/api/v1/jobs/{job_id}")

    assert job_response.status_code == 200
    assert job_response.json()["status"] == "succeeded"
