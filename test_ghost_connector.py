
import httpx
import pytest

from ghost_connector import GhostConnector


@pytest.fixture
def connection():
    return {
        "base_url": "https://ghost.example.com",
        "admin_api_key": "testkey:0123456789abcdef0123456789abcdef",
    }


@pytest.fixture
def mock_client():
    def handler(request):
        return httpx.Response(200, json={"posts": []})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_validate_valid_content():
    connector = GhostConnector()

    result = connector.validate(
        destination={"name": "My Ghost Site"},
        content="<p>Hello Ghost!</p>",
    )

    assert result["ok"] is True
    assert result["violations"] == []


def test_validate_missing_content():
    connector = GhostConnector()

    result = connector.validate(
        destination={"name": "My Ghost Site"},
        content="",
    )

    assert result["ok"] is False
    assert "CONTENT_REQUIRED" in result["violations"]


def test_publish_success(connection):
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/ghost/api/admin/posts/"
        assert request.url.params["source"] == "html"
        assert request.headers["Authorization"].startswith("Ghost ")
        assert request.headers["Idempotency-Key"] == "ghost-test-key"

        return httpx.Response(
            201,
            json={
                "posts": [
                    {
                        "id": "ghost-post-123",
                        "title": "Test post",
                        "status": "published",
                        "url": "https://ghost.example.com/test-post/",
                    }
                ]
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client:
        connector = GhostConnector(client=client)

        result = connector.publish(
            destination={"name": "My Ghost Site"},
            rendition={
                "title": "Test post",
                "content": "<p>Hello Ghost!</p>",
            },
            connection=connection,
            idempotency_key="ghost-test-key",
        )

    assert result["platform_post_id"] == "ghost-post-123"
    assert result["live_url"] == "https://ghost.example.com/test-post/"
    assert result["status"] == "published"
    assert result["simulation"] is False


def test_publish_requires_idempotency_key(connection):
    connector = GhostConnector()

    with pytest.raises(ValueError, match="idempotency key"):
        connector.publish(
            destination={"name": "My Ghost Site"},
            content="<p>Hello Ghost!</p>",
            connection=connection,
        )


def test_authentication_failure(connection):
    def handler(request):
        return httpx.Response(
            401,
            json={"errors": [{"message": "Authentication failed"}]},
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client:
        connector = GhostConnector(client=client)

        with pytest.raises(PermissionError, match="authentication"):
            connector.get_status(
                platform_post_id="ghost-post-123",
                connection=connection,
            )


def test_get_status_success(connection):
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == (
            "/ghost/api/admin/posts/ghost-post-123/"
        )

        return httpx.Response(
            200,
            json={
                "posts": [
                    {
                        "id": "ghost-post-123",
                        "status": "published",
                        "url": "https://ghost.example.com/test-post/",
                    }
                ]
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client:
        connector = GhostConnector(client=client)

        result = connector.get_status(
            platform_post_id="ghost-post-123",
            connection=connection,
        )

    assert result["platform_post_id"] == "ghost-post-123"
    assert result["status"] == "published"
    assert result["live_url"] == "https://ghost.example.com/test-post/"


def test_delete_success(connection):
    def handler(request):
        assert request.method == "DELETE"
        assert request.url.path == (
            "/ghost/api/admin/posts/ghost-post-123/"
        )

        return httpx.Response(204)

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client:
        connector = GhostConnector(client=client)

        result = connector.delete(
            platform_post_id="ghost-post-123",
            connection=connection,
        )

    assert result["deleted"] is True
    assert result["platform_post_id"] == "ghost-post-123"
