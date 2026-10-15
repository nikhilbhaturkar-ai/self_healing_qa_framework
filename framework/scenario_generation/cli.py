from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from framework.scenario_generation.service import generate_feature, index_repository


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repository-grounded Cucumber/Gherkin scenario generator")
    commands = parser.add_subparsers(dest="command", required=True)

    index_parser = commands.add_parser("index", help="Scan and incrementally index feature examples and runtime step bindings")
    index_parser.add_argument("--repo", required=True, type=Path, help="Repository root to scan")
    index_parser.add_argument("--application")
    index_parser.add_argument("--module")
    index_parser.add_argument("--role")

    generate_parser = commands.add_parser("generate", help="Generate and validate a review-only Gherkin feature")
    generate_parser.add_argument("--repo", required=True, type=Path, help="Indexed repository root")
    generate_parser.add_argument("--requirement", required=True)
    generate_parser.add_argument("--application")
    generate_parser.add_argument("--module")
    generate_parser.add_argument("--role")
    generate_parser.add_argument("--tag", action="append", default=[])
    generate_parser.add_argument("--output-name", help="Feature filename stem (written under artifacts/cucumber_rag)")
    generate_parser.add_argument("--max-steps", type=int, default=25)
    generate_parser.add_argument("--max-examples", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "index":
            result = index_repository(
                args.repo,
                application=args.application,
                module=args.module,
                role=args.role,
            )
        else:
            result = generate_feature(
                args.repo,
                args.requirement,
                application=args.application,
                module=args.module,
                role=args.role,
                tags=args.tag,
                output_name=args.output_name,
                max_retrieved_steps=args.max_steps,
                max_retrieved_examples=args.max_examples,
            )
    except (ValueError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())