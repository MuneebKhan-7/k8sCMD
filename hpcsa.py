#!/usr/bin/env python3
"""
hpcsa — HPCSA k8s AI Agent CLI

Usage:
    hpcsa "your goal here"
    hpcsa "your goal" --retries 5
    hpcsa "your goal" --dry-run
    hpcsa --help

Examples:
    hpcsa "Deploy a simple nginx pod in production and verify it is running"
    hpcsa "List all pods in the production namespace"
    hpcsa "Scale the nginx deployment to 3 replicas" --retries 5
"""

import argparse
import sys

from DspY import configure_lm, run_pipeline
from k8s import k8s as k8s_client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hpcsa",
        description="HPCSA AI Agent — achieves Kubernetes goals via a 3-agent DSPy pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "goal",
        nargs="?",
        help="The natural-language goal for the agent to achieve.",
    )
    parser.add_argument(
        "--retries", "-r",
        type=int,
        default=3,
        metavar="N",
        help="Max number of retry attempts if the goal is not achieved (default: 3).",
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        default=False,
        help="Plan and translate tasks but do NOT execute any k8s commands.",
    )
    parser.add_argument(
        "--model", "-m",
        default=None,
        metavar="MODEL",
        help="Override the LLM model name (default: $AGENT_LLM_MODEL from .env).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args   = parser.parse_args()

    # Interactive mode: prompt for goal if not provided
    if not args.goal:
        try:
            args.goal = input("Enter your goal: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not args.goal:
            parser.print_help()
            return 1

    # ── Initialise LLM + logging ─────────────────────────────────────────
    _, log_path = configure_lm(model=args.model)
    print(f"Session log → {log_path}\n")

    # ── Check k8s mock is reachable ──────────────────────────────────────
    if not k8s_client.ping():
        print("✗  k8s cluster is not reachable.")
        print("   Start the mock with:")
        print("     docker run -d -p 9988:9988 ezequielmr94/kubernetes-cluster-mock:latest")
        return 1

    # ── Run the pipeline ─────────────────────────────────────────────────
    try:
        verdict = run_pipeline(
            goal=args.goal,
            max_retries=args.retries,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        print("\n\nInterrupted.")
        return 130

    # ── Clean console summary ────────────────────────────────────────────
    commands = verdict.pop("_commands", [])
    print("\nCommands executed:")
    if commands:
        for cmd in commands:
            print(f"  $ {cmd}")
    else:
        print("  (none)")

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(verdict.get("summary", verdict["reason"]))
    if not verdict["achieved"]:
        print(f"\nNext step: {verdict['corrective_action']}")
    print(f"\nFull details → {log_path}")

    return 0 if verdict["achieved"] else 1


if __name__ == "__main__":
    sys.exit(main())
