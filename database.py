import hashlib
import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

# Use DATABASE_PATH when configured; otherwise, store the database
# alongside this Python file for local development.
DATABASE_PATH = Path(
    os.getenv(
        "DATABASE_PATH",
    
        str(BASE_DIR / "incu_distribution.db"),
    )
)

# Ensure the parent directory exists before SQLite opens the database.
DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


def connect_db():
    """Create a SQLite connection with dictionary-like rows."""
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def init_db():
    """Create the posts and publishing jobs tables."""
    with closing(connect_db()) as conn:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    result_json TEXT NOT NULL
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL UNIQUE,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    request_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )


def _now():
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _json(value):
    """Serialize data consistently as JSON."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _request_hash(request_data: dict):
    """Create a stable hash of the full request."""
    return hashlib.sha256(
        _json(request_data).encode("utf-8")
    ).hexdigest()


# -------------------------
# Publishing post functions
# -------------------------

def save_or_get_post(destination: str, content: str, key: str):
    """Save a simulated post or reuse a previous post with the same key."""

    if not destination or not destination.strip():
        raise ValueError("Destination is required.")

    if not content or not content.strip():
        raise ValueError("Content is required.")

    if not key or not key.strip():
        raise ValueError("An idempotency key is required.")

    with closing(connect_db()) as conn:
        with conn:
            rows = conn.execute(
                "SELECT result_json FROM posts"
            ).fetchall()

            for row in rows:
                existing = json.loads(row["result_json"])

                if existing.get("idempotency_key") == key:
                    if (
                        existing.get("destination") != destination
                        or existing.get("content") != content
                    ):
                        raise ValueError(
                            "Idempotency key was reused with different content."
                        )

                    return existing

            post = {
                "post_id": str(uuid.uuid4()),
                "destination": destination,
                "content": content,
                "status": "published",
                "idempotency_key": key,
                "created_at": _now(),
                "simulation": True,
                "message": (
                    "Simulated post only; nothing was published "
                    "to a real platform."
                ),
            }

            conn.execute(
                "INSERT INTO posts (result_json) VALUES (?)",
                (_json(post),),
            )

            return post


def get_post(post_id: str):
    """Retrieve a post by its post ID."""

    with closing(connect_db()) as conn:
        row = conn.execute(
            """
            SELECT result_json
            FROM posts
            WHERE json_extract(result_json, '$.post_id') = ?
            """,
            (post_id,),
        ).fetchone()

        return json.loads(row["result_json"]) if row else None


def delete_post(post_id: str):
    """Delete a stored post by its post ID."""

    with closing(connect_db()) as conn:
        with conn:
            cursor = conn.execute(
                """
                DELETE FROM posts
                WHERE json_extract(result_json, '$.post_id') = ?
                """,
                (post_id,),
            )

            return cursor.rowcount > 0


# -------------------------
# Publishing job functions
# -------------------------

def create_or_get_job(request_data: dict):
    """
    Create a publishing job or return the existing job for its key.

    Returns:
        (job, created, conflict)
    """

    key = request_data.get("idempotency_key")

    if not isinstance(key, str) or not key.strip():
        raise ValueError("An idempotency key is required.")

    request_hash = _request_hash(request_data)

    with closing(connect_db()) as conn:
        with conn:
            existing_row = conn.execute(
                """
                SELECT *
                FROM jobs
                WHERE idempotency_key = ?
                """,
                (key,),
            ).fetchone()

            if existing_row:
                existing_job = json.loads(
                    existing_row["result_json"]
                )

                if existing_row["request_hash"] != request_hash:
                    return existing_job, False, True

                return existing_job, False, False

            now = _now()

            job = {
                "job_id": str(uuid.uuid4()),
                "status": "queued",
                "progress": 0,
                "request": request_data,
                "result": None,
                "result_url": None,
                "error": None,
                "created_at": now,
                "updated_at": now,
            }

            conn.execute(
                """
                INSERT INTO jobs (
                    job_id,
                    idempotency_key,
                    request_hash,
                    status,
                    result_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["job_id"],
                    key,
                    request_hash,
                    job["status"],
                    _json(job),
                    now,
                    now,
                ),
            )

            return job, True, False


def get_job(job_id: str):
    """Retrieve a publishing job by ID."""

    with closing(connect_db()) as conn:
        row = conn.execute(
            """
            SELECT result_json
            FROM jobs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()

        return json.loads(row["result_json"]) if row else None


def update_job(
    job_id: str,
    status: str,
    result=None,
    error=None,
    progress=None,
    result_url=None,
):
    """
    Update a publishing job's status, progress, result, or error.
    """

    allowed_statuses = {
        "queued",
        "running",
        "succeeded",
        "failed",
    }

    if status not in allowed_statuses:
        raise ValueError(f"Invalid job status: {status}")

    if progress is not None:
        progress = int(progress)

        if not 0 <= progress <= 100:
            raise ValueError("Job progress must be between 0 and 100.")

    with closing(connect_db()) as conn:
        with conn:
            row = conn.execute(
                """
                SELECT result_json
                FROM jobs
                WHERE job_id = ?
                """,
                (job_id,),
            ).fetchone()

            if row is None:
                return None

            job = json.loads(row["result_json"])

            job["status"] = status
            job["updated_at"] = _now()

            if progress is not None:
                job["progress"] = progress

            if result is not None:
                job["result"] = result

            if error is not None:
                job["error"] = error

            if result_url is not None:
                job["result_url"] = result_url

            conn.execute(
                """
                UPDATE jobs
                SET status = ?,
                    result_json = ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (
                    status,
                    _json(job),
                    job["updated_at"],
                    job_id,
                ),
            )

            return job


# Initialize tables whenever this module is imported.
init_db()