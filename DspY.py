"""
DspY.py — DSPy-powered LLM backbone for the 3-agent HPCSA pipeline.

Agent pipeline:
  1. PlannerAgent   — Turns a natural-language goal into an ordered task list.
  2. ExecutorAgent  — Converts each task into a concrete k8s command and runs it.
  3. ValidatorAgent — Checks whether the goal was achieved; signals retry if not.

All three agents call the LLM through typed DSPy Signatures + Modules, which
means DSPy can later auto-optimise the prompts with zero code changes.
"""

import os
import logging
import datetime
import dspy
from dotenv import load_dotenv
from typing import List

from k8s import K8sClient

load_dotenv()

# Silence noisy third-party libraries on the console
for _noisy in ("LiteLLM", "LiteLLM Router", "LiteLLM Proxy", "httpx", "httpcore", "openai"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Logging — one file per session under logs/
# ---------------------------------------------------------------------------

def setup_logging():
    """Create a session log file under logs/ and return the logger."""
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    session_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path   = os.path.join(log_dir, f"session_{session_id}.log")

    logger = logging.getLogger("dspy_pipeline")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # File handler — everything (DEBUG and above)
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(fh)

    return logger, log_path


# Module-level logger — replaced with a real one when configure_lm() is called
_log: logging.Logger = logging.getLogger("dspy_pipeline")


# ---------------------------------------------------------------------------
# Global DSPy LM — configured once, shared by all agents
# ---------------------------------------------------------------------------

def configure_lm(model: str = None):
    """Configure the DSPy language model and initialise session logging.

    Uses the GWDG OpenAI-compatible API. Call this once at startup;
    dspy.configure(lm=...) is applied globally.

    Returns:
        (lm, log_path) tuple.
    """
    global _log
    _log, log_path = setup_logging()
    _log.info("Session started")

    model    = model or os.getenv("AGENT_LLM_MODEL", "openai-gpt-oss-120b")
    base_url = os.getenv("GWDG_MODEL_URL", "https://chat-ai.academiccloud.de/v1")
    api_key  = os.getenv("GWDG_MODEL_API_KEY", "")

    _log.info(f"Using model: {model}  base_url: {base_url}")

    lm = dspy.LM(
        model=f"openai/{model}",
        api_key=api_key,
        api_base=base_url,
        temperature=0.2,
    )
    dspy.configure(lm=lm)
    return lm, log_path


# ---------------------------------------------------------------------------
# DSPy Signatures — typed contracts for each agent's LLM call
# ---------------------------------------------------------------------------

class PlannerSignature(dspy.Signature):
    """Break a high-level goal into a numbered, ordered list of atomic tasks.

    Rules:
    - Each task must be self-contained and executable independently.
    - Tasks must be ordered so that later tasks can depend on earlier ones.
    - Output ONLY the task list, one task per line, numbered 1, 2, 3 ...
    - Do NOT include explanations or commentary outside the list.
    - The k8s cluster already has a 'production' namespace — use it unless told otherwise.
    - Tasks must only use supported operations: create pod, create deployment, delete pod,
      delete deployment, create ingress, delete ingress, get pods, get deployments, get nodes.
    """
    goal: str = dspy.InputField(
        desc="The high-level objective the user wants to achieve on the k8s cluster"
    )
    tasks: str = dspy.OutputField(
        desc="Numbered list of atomic tasks, one per line, e.g.:\n1. Create namespace\n2. Deploy pod"
    )


class ExecutorSignature(dspy.Signature):
    """Convert a single task description into the exact kubectl command to execute it.

    Rules:
    - Output ONLY the kubectl command string, nothing else.
    - The command must be valid and directly executable.
    - Do NOT add --dry-run flags — commands will be executed for real.
    - Do NOT include shell pipes, &&, or multi-command chains — one command only.
    - For creating a pod use: kubectl run <name> --image=<image> -n <namespace> --restart=Never
    - For creating a deployment use: kubectl create deployment <name> --image=<image> -n <namespace>
    - For listing resources use: kubectl get <resource> -n <namespace>
    - For deleting resources use: kubectl delete <resource> <name> -n <namespace>
    """
    task: str = dspy.InputField(
        desc="A single atomic task description"
    )
    context: str = dspy.InputField(
        desc="Results of previously executed commands (for context), or 'None'"
    )
    command: str = dspy.OutputField(
        desc="A single, complete kubectl command ready to run"
    )


class ValidatorSignature(dspy.Signature):
    """Decide whether the original goal has been fully achieved.

    Rules:
    - If all commands returned data or a success response, the goal IS achieved.
    - Only return False if a command explicitly failed (error/not found/exception).
    - A goal like 'list pods' is achieved as soon as the pod list is returned,
      even if the list is empty.
    - Do NOT suggest improvements or next steps — only judge what was done.
    - Do NOT require perfect formatting of the output to consider it achieved.
    """
    goal: str = dspy.InputField(
        desc="The original high-level goal"
    )
    tasks: str = dspy.InputField(
        desc="The planned task list that was executed"
    )
    results: str = dspy.InputField(
        desc="Output/results from executing each task, one per line"
    )
    achieved: bool = dspy.OutputField(
        desc="True if all commands ran successfully and returned relevant data. False only if a command explicitly errored."
    )
    reason: str = dspy.OutputField(
        desc="One sentence: what was done and whether it succeeded."
    )
    corrective_action: str = dspy.OutputField(
        desc="If not achieved: the single next command to fix it. If achieved: 'None'"
    )


# ---------------------------------------------------------------------------
# Agent 1 — PlannerAgent
# ---------------------------------------------------------------------------

class PlannerAgent(dspy.Module):
    """Turns a natural-language goal into an ordered list of k8s tasks.

    Uses ChainOfThought so the model reasons through dependencies before
    committing to a task order — reduces hallucinated or impossible orderings.
    """

    def __init__(self):
        super().__init__()
        self.plan = dspy.ChainOfThought(PlannerSignature)

    def forward(self, goal: str) -> List[str]:
        """Generate a task list for the given goal.

        Args:
            goal: Natural-language description of what to achieve.

        Returns:
            Ordered list of task strings (without numbering).
        """
        result = self.plan(goal=goal)
        # Parse "1. task\n2. task\n..." into a clean list
        tasks = []
        for line in result.tasks.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            # Strip leading "1." / "1)" / "- " etc.
            parts = line.split(".", 1) if "." in line else line.split(")", 1)
            task = parts[1].strip() if len(parts) == 2 and parts[0].strip().isdigit() else line
            tasks.append(task)
        return tasks


# ---------------------------------------------------------------------------
# Agent 2 — ExecutorAgent
# ---------------------------------------------------------------------------

class ExecutorAgent(dspy.Module):
    """Converts a task into a kubectl command and executes it via k8s.py.

    Uses Predict (not CoT) because the command must be a precise, single
    string — reasoning tokens would pollute the output.
    """

    def __init__(self, dry_run: bool = False):
        """
        Args:
            dry_run: If True, print commands without actually calling the k8s mock.
        """
        super().__init__()
        self.generate_command = dspy.Predict(ExecutorSignature)
        self.dry_run = dry_run
        self._k8s = K8sClient()

    def forward(self, task: str, context: str = "None") -> dict:
        """Generate a kubectl command for a task and execute it via k8s.py.

        Args:
            task:    The task description from PlannerAgent.
            context: Accumulated results from previous tasks.

        Returns:
            Dict with keys: task, command, output, success.
        """
        result = self.generate_command(task=task, context=context)
        command = result.command.strip()

        output, success = self._run(command)
        return {
            "task":    task,
            "command": command,
            "output":  output,
            "success": success,
        }

    def _run(self, command: str) -> tuple:
        """Execute via K8sClient or dry-run, with confirmation prompt."""
        if self.dry_run:
            print(f"  [DRY RUN] Would execute: {command}")
            return f"[dry-run] {command}", True

        # Ask for confirmation before executing
        print(f"\n  About to execute: {command}")
        try:
            answer = input("  Run this command? [y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n  [skipped]")
            return "[skipped by user]", False

        if answer != "y":
            print("  [skipped]")
            return "[skipped by user]", False

        result = self._k8s.execute(command)
        lines = result["output"].splitlines()
        preview = "\n    ".join(lines[:5])
        truncated = "\n    ......................................" if len(lines) > 5 else ""
        print(f"  Output:\n    {preview}{truncated}")
        return result["output"], result["success"]


# ---------------------------------------------------------------------------
# Agent 3 — ValidatorAgent
# ---------------------------------------------------------------------------

class ValidatorAgent(dspy.Module):
    """Checks whether the original goal was fully achieved.

    Uses ChainOfThought so the model reasons over all results before
    giving a binary verdict — reduces false positives/negatives.
    """

    def __init__(self):
        super().__init__()
        self.validate = dspy.ChainOfThought(ValidatorSignature)

    def forward(self, goal: str, tasks: List[str], results: List[dict]) -> dict:
        """Evaluate goal achievement.

        Args:
            goal:    The original user goal.
            tasks:   The task list from PlannerAgent.
            results: Execution results from ExecutorAgent.

        Returns:
            Dict with keys: achieved (bool), reason (str), corrective_action (str).
        """
        tasks_str   = "\n".join(f"{i+1}. {t}" for i, t in enumerate(tasks))
        results_str = "\n".join(
            f"Task {i+1}: {'OK' if r['success'] else 'FAIL'} | cmd: {r['command']} | output: {r['output']}"
            for i, r in enumerate(results)
        )

        result = self.validate(
            goal=goal,
            tasks=tasks_str,
            results=results_str,
        )
        return {
            "achieved":          result.achieved,
            "reason":            result.reason,
            "corrective_action": result.corrective_action,
        }


# ---------------------------------------------------------------------------
# Agent 4 — SummarizerAgent
# ---------------------------------------------------------------------------

class SummarizerSignature(dspy.Signature):
    """Produce a concise, human-friendly answer to the user's original goal.

    Rules:
    - Write 1-3 sentences that directly answer the goal using the data from the outputs.
    - State facts only — do NOT suggest next steps, follow-up commands, or improvements.
    - Do NOT use markdown code blocks, bullet points, or backticks.
    - Do NOT start with filler like 'Based on the above' or 'The output shows'.
    - If the output contains a list of names/items, just state them plainly.
    """
    goal:     str = dspy.InputField(desc="The original user goal")
    commands: str = dspy.InputField(desc="Commands that were executed, one per line")
    outputs:  str = dspy.InputField(desc="Output returned by each command, one per line")
    summary:  str = dspy.OutputField(desc="1-3 sentences directly answering the goal, facts only, no suggestions")


class SummarizerAgent(dspy.Module):
    """Turns raw execution results into a plain-English answer for the user."""

    def __init__(self):
        super().__init__()
        self.summarise = dspy.Predict(SummarizerSignature)

    def forward(self, goal: str, results: List[dict]) -> str:
        commands_str = "\n".join(r["command"] for r in results)
        outputs_str  = "\n".join(r["output"]  for r in results)
        result = self.summarise(goal=goal, commands=commands_str, outputs=outputs_str)
        return result.summary.strip()


# ---------------------------------------------------------------------------
# Orchestration helper — runs the full pipeline with retry
# ---------------------------------------------------------------------------

def run_pipeline(goal: str, max_retries: int = 3, dry_run: bool = False) -> dict:
    """Run the full 3-agent pipeline for a given goal.

    Flow:
      PlannerAgent -> ExecutorAgent (per task) -> ValidatorAgent
      If not achieved and retries remain -> feed corrective_action back to Planner.

    Args:
        goal:        The high-level k8s objective.
        max_retries: How many times to retry if the validator says not achieved.
        dry_run:     Pass True to skip real kubectl execution.

    Returns:
        Final validation dict: {achieved, reason, corrective_action}.
    """
    planner   = PlannerAgent()
    executor  = ExecutorAgent(dry_run=dry_run)
    validator = ValidatorAgent()
    summarizer = SummarizerAgent()

    # ── Console: print the goal once ──────────────────────────────────────
    print(f"\nGoal: {goal}")
    print("-" * 60)
    _log.info(f"run_pipeline started | goal={goal!r} max_retries={max_retries} dry_run={dry_run}")

    current_goal = goal
    all_commands = []   # collect for final console summary

    for attempt in range(1, max_retries + 1):
        _log.info(f"--- Attempt {attempt}/{max_retries} ---")
        _log.info(f"Current goal: {current_goal}")

        # --- Step 1: Plan ---
        _log.info("[Planner] generating tasks...")
        tasks = planner(goal=current_goal)
        for i, t in enumerate(tasks, 1):
            _log.info(f"  Task {i}: {t}")

        # --- Step 2: Execute ---
        _log.info("[Executor] running tasks...")
        results = []
        context = "None"
        for task in tasks:
            _log.debug(f"  Executing task: {task}")
            result = executor(task=task, context=context)
            _log.info(f"  Command : {result['command']}")
            _log.info(f"  Success : {result['success']}")
            _log.debug(f"  Output  : {result['output']}")
            all_commands.append(result['command'])
            results.append(result)
            context += f"\nTask '{task}' => {result['output']}"

        # --- Step 3: Validate ---
        _log.info("[Validator] checking goal achievement...")
        verdict = validator(goal=goal, tasks=tasks, results=results)
        _log.info(f"  Achieved : {verdict['achieved']}")
        _log.info(f"  Reason   : {verdict['reason']}")
        _log.info(f"  Corrective action: {verdict['corrective_action']}")

        if verdict["achieved"]:
            _log.info("Goal achieved!")
            _log.info("[Summarizer] generating final answer...")
            verdict["summary"]   = summarizer(goal=goal, results=results)
            verdict["_commands"] = all_commands
            _log.info(f"  Summary: {verdict['summary']}")
            return verdict

        _log.warning(f"Not achieved. Corrective action: {verdict['corrective_action']}")
        if attempt < max_retries:
            current_goal = (
                f"{goal}\n\n"
                f"Previous attempt {attempt} failed.\n"
                f"Corrective action required: {verdict['corrective_action']}"
            )

    _log.error(f"Goal not achieved after {max_retries} attempts.")
    _log.info("[Summarizer] generating final answer...")
    verdict["summary"]   = summarizer(goal=goal, results=results)
    verdict["_commands"] = all_commands
    _log.info(f"  Summary: {verdict['summary']}")
    return verdict


# ---------------------------------------------------------------------------
# Smoke-test when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    lm, log_path = configure_lm()
    print(f"Session log: {log_path}")

    # Check mock is up before running
    from k8s import k8s as k8s_client
    if not k8s_client.ping():
        print("✗ k8s mock is not running. Start it with:")
        print("  docker run -d -p 9988:9988 ezequielmr94/kubernetes-cluster-mock:latest")
        exit(1)

    GOAL = "Deploy a simple nginx pod in a namespace called 'production' and verify it is running"

    verdict = run_pipeline(goal=GOAL, max_retries=2, dry_run=False)

    # ── Console: clean summary only ───────────────────────────────────────
    commands = verdict.pop("_commands", [])
    print("\nCommands executed:")
    for cmd in commands:
        print(f"  $ {cmd}")
    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(verdict.get("summary", verdict["reason"]))
    if not verdict['achieved']:
        print(f"\nNext step: {verdict['corrective_action']}")
    print(f"\nFull details in: {log_path}")
