from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_MESSAGE = "Explain why metrics, logs, and traces work together"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the same CP2 input with a managed prompt label")
    parser.add_argument("--label", choices=("baseline", "candidate", "production"), required=True)
    parser.add_argument("--correlation-id", required=True)
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    os.environ["LANGFUSE_PROMPT_LABEL"] = args.label
    os.environ.setdefault("LANGFUSE_TIMEOUT", "30")

    from app.agent import LabAgent
    from app.tracing import get_langfuse_client

    result = LabAgent().run(
        user_id="cp2-demo-user",
        session_id="cp2-demo-session",
        feature="qa",
        message=DEFAULT_MESSAGE,
        correlation_id=args.correlation_id,
    )
    get_langfuse_client().flush()
    print(f"label={args.label} correlation_id={args.correlation_id} latency_ms={result.latency_ms}")


if __name__ == "__main__":
    main()
