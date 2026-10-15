"""
Convenience entry point for the RAG Cucumber scenario generator.

Usage
-----
  # 1. Index the repository (run once, or after step-definition changes):
  python run_rag.py index

  # 2. Generate a scenario from a plain-English requirement:
  python run_rag.py generate "Verify the user can sign in and see Basis Monitoring tiles"

  # 3. Generate with optional scope tags:
  python run_rag.py generate "Search for a branch named Pune" --tag regression --output my_scenario

  # 4. Start the REST API server:
  python run_rag.py serve

All generated artifacts land in artifacts/cucumber_rag/ relative to this file.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def cmd_index(args: argparse.Namespace) -> int:
    from framework.scenario_generation.service import index_repository

    print("Indexing repository …")
    result = index_repository(
        ROOT,
        application=args.application,
        module=args.module,
        role=args.role,
    )
    print(f"  Step definitions indexed : {result['step_definitions_indexed']}")
    print(f"  Scenario examples indexed: {result['scenario_examples_indexed']}")
    print(f"  Feature files scanned    : {result['feature_files_scanned']}")
    print(f"  Repository revision      : {result['repository_revision']}")
    if result.get("warnings"):
        print("  Warnings:")
        for w in result["warnings"]:
            print(f"    - {w}")
    if result.get("duplicate_expressions"):
        print("  Duplicate step expressions (may cause ambiguous matches):")
        for e in result["duplicate_expressions"]:
            print(f"    - {e}")
    print("Done.")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    from framework.scenario_generation.service import generate_feature

    print(f"Generating scenario for: {args.requirement!r}")
    try:
        result = generate_feature(
            ROOT,
            args.requirement,
            application=args.application,
            module=args.module,
            role=args.role,
            tags=args.tag or [],
            output_name=args.output,
            max_retrieved_steps=args.max_steps,
            max_retrieved_examples=args.max_examples,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    report = result["report"]
    paths = result["artifact_paths"]
    validation = report["validation"]

    sep = "-" * 60
    print()
    print(sep)
    if paths.get("feature"):
        feature_path = Path(paths["feature"])
        print(f"Feature file : {feature_path.relative_to(ROOT)}")
        print()
        print(feature_path.read_text(encoding="utf-8"))
        print(sep)

    print(f"Executable candidate : {report['executable_candidate']}")
    print(f"Syntax valid         : {validation['syntax_valid']}")
    print(f"Scenarios / Steps    : {validation['scenario_count']} / {validation['step_count']}")
    print(f"Reused steps         : {len(validation['reused_steps'])}")

    if validation["missing_steps"]:
        print(f"\nMissing steps ({len(validation['missing_steps'])}):")
        for s in validation["missing_steps"]:
            print(f"  - {s['text']}")

    if validation["ambiguous_steps"]:
        print(f"\nAmbiguous steps ({len(validation['ambiguous_steps'])}):")
        for s in validation["ambiguous_steps"]:
            print(f"  - {s['text']} ({len(s['candidates'])} candidates)")

    if validation["validation_errors"]:
        print(f"\nValidation errors ({len(validation['validation_errors'])}):")
        for e in validation["validation_errors"]:
            print(f"  - {e}")

    if report.get("assumptions"):
        print("\nAssumptions:")
        assumptions = report["assumptions"]
        if isinstance(assumptions, str):
            print(f"  - {assumptions}")
        else:
            for a in assumptions:
                print(f"  - {a}")

    print(f"\nJSON report  : {Path(paths['json_report']).relative_to(ROOT)}")
    print(f"Markdown     : {Path(paths['markdown_report']).relative_to(ROOT)}")
    return 0


def cmd_serve(_args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required: pip install uvicorn", file=sys.stderr)
        return 1

    print("Starting RAG API server at http://localhost:8000")
    print("  POST /index    — scan and index the repository")
    print("  POST /generate — generate a Gherkin feature")
    print("  GET  /health   — readiness check")
    uvicorn.run(
        "framework.scenario_generation.api:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RAG Cucumber Scenario Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    idx = sub.add_parser("index", help="Scan and index feature files and step bindings")
    idx.add_argument("--application", help="Application scope tag stored in the index")
    idx.add_argument("--module", help="Module scope tag")
    idx.add_argument("--role", help="Role scope tag")

    gen = sub.add_parser("generate", help="Generate a Gherkin feature from a requirement")
    gen.add_argument("requirement", help="Plain-English requirement to generate from")
    gen.add_argument("--application")
    gen.add_argument("--module")
    gen.add_argument("--role")
    gen.add_argument("--tag", action="append", default=[], metavar="TAG", help="Gherkin tag (repeatable)")
    gen.add_argument("--output", metavar="NAME", help="Stem for the output .feature filename")
    gen.add_argument("--max-steps", type=int, default=25, metavar="N")
    gen.add_argument("--max-examples", type=int, default=5, metavar="N")

    sub.add_parser("serve", help="Start the FastAPI REST server on port 8000")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    dispatch = {"index": cmd_index, "generate": cmd_generate, "serve": cmd_serve}
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
