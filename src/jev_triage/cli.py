import argparse
import csv
import json
import os
import sys

from .jev import JevClient
from .runner import run


def main():
    parser = argparse.ArgumentParser(description="Deterministic-first customer data quality triage")
    parser.add_argument("input", help="CSV, JSON array, or JSONL file")
    parser.add_argument("--output", default="runs", help="Root for immutable run directories")
    parser.add_argument("--provider", choices=["offline", "jev"], default="offline")
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--allow-ai-data", action="store_true",
                        help="Allow age, country, status and notes to be sent to TypeSafe")
    args = parser.parse_args()
    provider = None
    try:
        if args.provider == "jev":
            if not args.allow_ai_data:
                parser.error("Jev mode requires --allow-ai-data; notes may contain personal data")
            provider = JevClient(os.environ.get("TYPESAFE_API_KEY"), args.model)
        path, summary = run(args.input, args.output, provider, args.threshold)
        print(json.dumps({"output": str(path), **summary}, indent=2))
        return 0
    except (ValueError, OSError, csv.Error) as error:
        # Avoid echoing raw input values or server response bodies to logs.
        print(f"Input/configuration failure ({type(error).__name__}); no run published.",
              file=sys.stderr)
        return 2
    finally:
        if provider:
            provider.close()


if __name__ == "__main__":
    sys.exit(main())
