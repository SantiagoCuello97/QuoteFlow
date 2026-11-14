import sqlite3
from datetime import datetime, timezone

from app.storage import database, initialize


class DecisionConflict(Exception):
    pass


def apply_decision(request_id, decision, actor):
    with database() as conn:
        conn.execute("BEGIN IMMEDIATE")
        initialize(conn)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS approval_decisions (
                request_id TEXT PRIMARY KEY
                    REFERENCES requests(request_id),
                decision TEXT NOT NULL,
                actor TEXT NOT NULL,
                decided_at TEXT NOT NULL
            )
        """)

        row = conn.execute(
            "SELECT state FROM requests WHERE request_id = ?",
            (request_id,)
        ).fetchone()

        if row is None:
            raise KeyError("Request not found")

        if row["state"] == decision:
            previous = conn.execute(
                """SELECT actor, decided_at
                   FROM approval_decisions
                   WHERE request_id = ?""",
                (request_id,)
            ).fetchone()

            if previous is None:
                raise DecisionConflict("Missing decision audit record")

            return {
                "request_id": request_id,
                "state": decision,
                "actor": previous["actor"],
                "decided_at": previous["decided_at"],
                "replayed": True,
            }

        if row["state"] != "APPROVAL_PENDING":
            raise DecisionConflict(
                f"Cannot transition from {row['state']} to {decision}"
            )

        timestamp = datetime.now(timezone.utc).isoformat()

        updated = conn.execute(
            """UPDATE requests
               SET state = ?
               WHERE request_id = ?
                 AND state = 'APPROVAL_PENDING'""",
            (decision, request_id)
        )

        if updated.rowcount != 1:
            raise DecisionConflict("Concurrent state change")

        conn.execute(
            """INSERT INTO approval_decisions
               (request_id, decision, actor, decided_at)
               VALUES (?, ?, ?, ?)""",
            (request_id, decision, actor, timestamp)
        )

        conn.execute(
            """INSERT INTO audit_events
               (request_id, event_type, created_at)
               VALUES (?, ?, ?)""",
            (request_id, f"REQUEST_{decision}", timestamp)
        )

        return {
            "request_id": request_id,
            "state": decision,
            "actor": actor,
            "decided_at": timestamp,
            "replayed": False,
        }