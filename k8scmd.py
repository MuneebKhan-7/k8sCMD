#!/usr/bin/env python3
"""
k8scmd — interactive HPCSA k8s AI Agent REPL

Type a goal in plain English and press Enter.
Type  q  (or  quit / exit) and press Enter to leave.
Press Ctrl+C at any time to cancel the current goal or exit.
"""

import sys

from DspY import configure_lm, run_pipeline
from k8s import k8s as k8s_client

BANNER = r"""
  _  __  ___  ____     ____ __  __ ____  
 | |/ / ( _ )/ ___|   / ___|  \/  |  _ \ 
 | ' /  / _ \\___ \  | |   | |\/| | | | |
 | . \ | (_) |___) | | |___| |  | | |_| |
 |_|\_\ \___/|____/   \____|_|  |_|____/ 
                           k8s AI agent
                                by
                   Sadaf Shafi and Mojtaba Akbari

 Type a goal and press Enter.
 Type  q  to quit.
"""

QUIT_WORDS = {"q", "quit", "exit", "bye"}


def run_goal(goal: str) -> None:
    """Run one goal through the pipeline and print the clean summary."""
    verdict = run_pipeline(goal=goal, max_retries=3, dry_run=False)

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
    print("=" * 60 + "\n")


def main() -> int:
    # ── Initialise LLM + session logging ────────────────────────────────
    _, log_path = configure_lm()

    # ── Verify k8s mock is up ────────────────────────────────────────────
    if not k8s_client.ping():
        print("✗  k8s cluster is not reachable.")
        print("   Start the mock with:")
        print("     docker run -d -p 9988:9988 ezequielmr94/kubernetes-cluster-mock:latest")
        return 1

    print(BANNER)
    print(f"Session log → {log_path}\n")

    # ── REPL loop ────────────────────────────────────────────────────────
    while True:
        try:
            goal = input("k8scmd> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not goal:
            continue

        if goal.lower() in QUIT_WORDS:
            print("Goodbye!")
            break

        try:
            run_goal(goal)
        except KeyboardInterrupt:
            print("\n[cancelled]\n")
            continue

    return 0


if __name__ == "__main__":
    sys.exit(main())
