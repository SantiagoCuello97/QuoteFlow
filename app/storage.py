import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "quoteflow.db"


@contextmanager
def database():
    path = Path(os.environ.get("QUOTEFLOW_DB_PATH", str(DEFAULT_DB)))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS requests (
            request_id TEXT PRIMARY KEY,
            payload_hash TEXT NOT NULL,
            state TEXT NOT NULL,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL REFERENCES requests(request_id),
            event_type TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)


def save_request(request_id, payload, comparison):
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False,
        separators=(",", ":")
    )
    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
    state = (
        "APPROVAL_PENDING"
        if comparison["issues"] else "VALIDATED"
    )

    with database() as conn:
        conn.execute("BEGIN IMMEDIATE")
        initialize(conn)

        existing = conn.execute(
            "SELECT * FROM requests WHERE request_id = ?",
            (request_id,)
        ).fetchone()

        if existing:
            if existing["payload_hash"] != fingerprint:
                raise ValueError(
                    "Request ID already used for different content"
                )
            return {
                "request_id": request_id,
                "state": existing["state"],
                "comparison": json.loads(existing["result_json"])
            }

        timestamp = datetime.now(timezone.utc).isoformat()

        conn.execute(
            """INSERT INTO requests
               (request_id, payload_hash, state, result_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                request_id, fingerprint, state,
                json.dumps(comparison), timestamp
            )
        )

        conn.execute(
            """INSERT INTO audit_events
               (request_id, event_type, created_at)
               VALUES (?, ?, ?)""",
            (request_id, "REQUEST_CREATED", timestamp)
        )

        return {
            "request_id": request_id,
            "state": state,
            "comparison": comparison
        }


def get_request(request_id):
    with database() as conn:
        initialize(conn)

        row = conn.execute(
            "SELECT * FROM requests WHERE request_id = ?",
            (request_id,)
        ).fetchone()

        if row is None:
            return None

        return {
            "request_id": request_id,
            "state": row["state"],
            "comparison": json.loads(row["result_json"])
        }