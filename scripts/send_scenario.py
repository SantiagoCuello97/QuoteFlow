"""Send one synthetic scenario to an n8n Webhook (standard-library only).

This is a demonstration client for n8n, not a batch-load tool. An HTTP 200
from a Webhook configured to respond immediately acknowledges receipt only.
"""

import argparse
import json
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCENARIOS = Path(__file__).resolve().parents[1] / "data" / "synthetic" / "scenarios.json"
DEFAULT_URL = "http://127.0.0.1:5678/webhook-test/quoteflow-intake"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", default="QF-SYN-002", help="Scenario ID from scenarios.json")
    parser.add_argument("--url", default=DEFAULT_URL, help="n8n Webhook URL")
    parser.add_argument("--unique-id", action="store_true", help="Append a random suffix to create a fresh request")
    args = parser.parse_args()

    scenarios = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    matches = [scenario for scenario in scenarios if scenario["request_id"] == args.scenario]
    if len(matches) != 1:
        parser.error(f"Expected exactly one scenario with ID {args.scenario!r}")

    scenario = matches[0]
    request_id = scenario["request_id"]
    if args.unique_id:
        request_id = f"{request_id}-{uuid.uuid4().hex[:8]}"

    body = json.dumps({"request_id": request_id, "payload": scenario["payload"]}).encode("utf-8")
    request = Request(
        args.url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print(f"Scenario: {scenario['request_id']}")
    print(f"Request ID: {request_id}")
    print(f"Webhook URL: {args.url}")

    try:
        with urlopen(request, timeout=15) as response:
            print(f"Webhook HTTP: {response.status}")
            print("Webhook received the request; inspect n8n execution for validation/approval result.")
    except HTTPError as error:
        print(f"Webhook HTTP error: {error.code}", file=sys.stderr)
        return 1
    except URLError as error:
        print(f"Connection failed: {error.reason}", file=sys.stderr)
        print("Make sure n8n is running and Execute workflow is waiting for the Test URL.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
