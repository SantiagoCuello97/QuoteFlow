"""Validate synthetic scenarios using an isolated SQLite database."""

import json
import os
import sqlite3
import sys
import tempfile
from contextlib import closing
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATASET = ROOT / "data" / "synthetic" / "scenarios.json"


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def run_qa():
    scenarios = json.loads(DATASET.read_text(encoding="utf-8"))
    check(len(scenarios) == 9, "Expected 9 scenarios")

    with tempfile.TemporaryDirectory(
        prefix="quoteflow_qa_"
    ) as temp_dir:

        db = Path(temp_dir) / "qa.db"
        os.environ["QUOTEFLOW_DB_PATH"] = str(db)

        from fastapi.testclient import TestClient
        from app.main import app

        expected_states = {}

        with TestClient(app) as client:

            print("=== SCENARIO VALIDATION ===")

            for scenario in scenarios:
                request_id = scenario["request_id"]
                expected_status = scenario["expected_http_status"]

                response = client.post(
                    "/requests",
                    json=scenario["payload"],
                    headers={"X-Request-ID": request_id},
                )

                check(
                    response.status_code == expected_status,
                    f"{request_id}: HTTP {response.status_code}, "
                    f"expected {expected_status}: {response.text}",
                )

                if expected_status == 200:
                    result = response.json()
                    expected_state = scenario["expected_state"]
                    expected_issues = scenario["expected_issues"]

                    check(
                        result["request_id"] == request_id,
                        f"{request_id}: Incorrect request ID",
                    )

                    check(
                        result["state"] == expected_state,
                        f"{request_id}: Incorrect state",
                    )

                    comparison = result["comparison"]

                    check(
                        sorted(comparison["issues"])
                        == sorted(expected_issues),
                        f"{request_id}: Incorrect issues",
                    )

                    expected_comparison = (
                        "MATCH" if not expected_issues
                        else "REVIEW_REQUIRED"
                    )

                    check(
                        comparison["status"] == expected_comparison,
                        f"{request_id}: Incorrect comparison status",
                    )

                    expected_states[request_id] = expected_state

                    print(
                        f"PASS {request_id}: "
                        f"HTTP 200, {expected_state}"
                    )
                else:
                    print(
                        f"PASS {request_id}: "
                        f"HTTP 422, invalid document rejected"
                    )

            print("\n=== IDEMPOTENCY VALIDATION ===")

            valid_scenarios = [
                s for s in scenarios
                if s["expected_http_status"] == 200
            ]

            for scenario in valid_scenarios:
                response = client.post(
                    "/requests",
                    json=scenario["payload"],
                    headers={
                        "X-Request-ID": scenario["request_id"]
                    },
                )

                check(
                    response.status_code == 200,
                    "Identical replay failed",
                )

                check(
                    response.json()["state"]
                    == scenario["expected_state"],
                    "Replay returned an incorrect state",
                )

            print("PASS: 7 identical requests replayed")

            changed = deepcopy(valid_scenarios[0]["payload"])
            changed["quote"]["items"][0]["unit_price"] = "999.00"

            conflict = client.post(
                "/requests",
                json=changed,
                headers={
                    "X-Request-ID":
                    valid_scenarios[0]["request_id"]
                },
            )

            check(
                conflict.status_code == 409,
                "Conflicting request ID was not rejected",
            )

            print("PASS: conflicting duplicate rejected (409)")

        print("\n=== SQLITE INTEGRITY ===")

        with closing(sqlite3.connect(db)) as conn:
            conn.execute("PRAGMA query_only = ON")

            actual_states = dict(conn.execute(
                "SELECT request_id, state FROM requests"
            ).fetchall())

            audit_rows = conn.execute(
                "SELECT request_id, event_type FROM audit_events"
            ).fetchall()

        check(
            actual_states == expected_states,
            "Persisted states do not match expected states",
        )

        check(
            len(audit_rows) == len(expected_states),
            "Unexpected number of audit events",
        )

        expected_events = {
            (request_id, "REQUEST_CREATED")
            for request_id in expected_states
        }

        check(
            set(audit_rows) == expected_events,
            "Audit events do not match expected events",
        )

        print(
            f"PASS: {len(expected_states)} persisted requests"
        )
        print(
            f"PASS: {len(audit_rows)} creation audit events"
        )
        print("PASS: duplicate requests created no extra rows")

    print("\nSTATUS: ALL SYNTHETIC QA CHECKS PASSED")


if __name__ == "__main__":
    try:
        run_qa()
    except Exception as error:
        print(f"QA FAILED: {error}", file=sys.stderr)
        sys.exit(1)