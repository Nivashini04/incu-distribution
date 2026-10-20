
import httpx
import pytest

from lemmy_connector import LemmyConnector


@pytest.fixture
def connector():
    return LemmyConnector()


@pytest.fixture
def connection():
    return {
        "base_url": "https://lemmy.example.com",
        "access_token": "test-token",
    }


def test_validate_valid_content(connector):
    result = connector.validate(
        destination={
            "community": "technology",
            "community_id": 123,
        },
        content="Hello Lemmy!",
    )

    assert result["ok"] is True
    assert result["violations"] == []


def test_validate_missing_content(connector):
    result = connector.validate(
        destination={
            "community": "technology",
            "community_id": 123,
        },
        content="",
    )

    assert result["ok"] is False
    assert "CONTENT_REQUIRED" in result["violations"]


def test_publish_success(connection):
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v3/post"
        assert request.headers["Authorization"] == "Bearer test-token"
        assert request.headers["Idempotency-Key"] == "test-key"

        return httpx.Response(
            200,
            json={
                "post_view": {
                    "post": {
                        "id": 456,
                        "name": "Test post",
                    }
                }
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client:
        connector = LemmyConnector(client=client)

        result = connector.publish(
            destination={
                "community": "technology",
                "community_id": 123,
            },
            content="Hello Lemmy!",
            connection=connection,
            idempotency_key="test-key",
        )

    assert result["platform_post_id"] == "456"
    assert result["live_url"] == "https://lemmy.example.com/post/456"
    assert result["status"] == "published"
    assert result["simulation"] is False


def test_publish_missing_community_id(connection):
    connector = LemmyConnector()

    with pytest.raises(ValueError, match="community_id"):
        connector.publish(
            destination={"community": "technology"},
            content="Hello Lemmy!",
            connection=connection,
            idempotency_key="test-key",
        )


def test_authentication_failure(connection):
    def handler(request):
        return httpx.Response(401, json={"error": "not_logged_in"})

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client:
        connector = LemmyConnector(client=client)

        with pytest.raises(PermissionError, match="authentication"):
            connector.get_status(
                platform_post_id="456",
                connection=connection,
            )


def test_get_status_success(connection):
    def handler(request):
        assert request.method == "GET"
        assert request.url.path == "/api/v3/post"
        assert request.url.params["id"] == "456"

        return httpx.Response(
            200,
            json={
                "post_view": {
                    "post": {
                        "id": 456,
                        "name": "Test post",
                        "deleted": False,
                        "removed": False,
                    }
                }
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client:
        connector = LemmyConnector(client=client)

        result = connector.get_status(
            platform_post_id="456",
            connection=connection,
        )

    assert result["platform_post_id"] == "456"
    assert result["status"] == "published"
    assert result["live_url"] == "https://lemmy.example.com/post/456"


def test_delete_success(connection):
    def handler(request):
        assert request.method == "POST"
        assert request.url.path == "/api/v3/post/delete"

        return httpx.Response(
            200,
            json={
                "post_view": {
                    "post": {
                        "id": 456,
                        "deleted": True,
                    }
                }
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler)
    ) as client:
        connector = LemmyConnector(client=client)

        result = connector.delete(
            platform_post_id="456",
            connection=connection,
        )

    assert result["deleted"] is True
    assert result["platform_post_id"] == "456"
