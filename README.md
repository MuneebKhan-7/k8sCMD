# k8sCMD — Documentation

> **k8sCMD** is an AI-powered Kubernetes command system. You describe what you want in plain English and the system plans, executes, validates, and explains the result — all against a real (or mock) Kubernetes cluster.

## Demo Video

<video src="https://github.com/SadafShafi/k8sCMD/raw/main/short_demo.mp4" controls="controls" style="max-width: 100%;">
  Your browser does not support the video tag.
</video>

---

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Project Structure](#project-structure)
4. [Configuration](#configuration)
5. [How to Run](#how-to-run)
6. [System Architecture](#system-architecture)
7. [Agent Pipeline](#agent-pipeline)
   - [PlannerAgent](#1-planneragent)
   - [ExecutorAgent](#2-executoragent)
   - [ValidatorAgent](#3-validatoragent)
   - [SummarizerAgent](#4-summarizeragent)
8. [k8s Client (k8s.py)](#k8s-client-k8spy)
9. [LLM Backbone (LLM.py)](#llm-backbone-llmpy)
10. [Logging](#logging)
11. [CLI Reference](#cli-reference)
12. [Running Tests](#running-tests)
13. [Dependencies](#dependencies)

---

## Overview

k8sCMD connects a large language model to a Kubernetes cluster through a 4-agent DSPy pipeline:

```
You → plain English goal → Planner → Executor → Validator → Summarizer → plain English answer
```

Every step is logged to a per-session file. The console stays clean — you see only the goal, the commands that ran, and the final answer.

---

## Quick Start

### 1. Clone and set up

```bash
git clone https://github.com/SadafShafi/k8sCMD.git
cd k8sCMD
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and fill in your API key and model name
```

### 3. Start the Kubernetes mock

```bash
docker run -d -p 9988:9988 ezequielmr94/kubernetes-cluster-mock:latest
```

### 4. Run

```bash
# Interactive REPL
./k8scmd

# Single-shot
./hpcsa "Deploy a Redis pod in the production namespace and verify it is running"
```

---

## Project Structure

```
k8sCMD/
├── k8scmd.py          # Interactive REPL — type goals, get answers
├── k8scmd             # Bash launcher (no venv activation needed)
├── hpcsa.py           # Single-shot CLI
├── hpcsa              # Bash launcher
├── DspY.py            # 4-agent DSPy pipeline (core of the system)
├── k8s.py             # REST client for the Kubernetes mock API
├── LLM.py             # Standalone raw-requests LLM wrapper
├── agents.py          # (reserved for future agent extensions)
├── orchestration.py   # (reserved for future orchestration logic)
├── .env               # Your secrets — never committed
├── .env.example       # Template with placeholder values
├── .gitignore         # Excludes .env, .venv, logs, __pycache__
├── requirements.txt   # Python dependencies
├── architecture.md    # ASCII system diagram
├── logs/              # Per-session log files (auto-created)
└── tests/
    └── llm_test.py    # Unit tests for LLM.py
```

---

## Configuration

All configuration lives in `.env`. Copy `.env.example` to get started:

| Variable | Description | Example |
|---|---|---|
| `GWDG_MODEL_URL` | Base URL of the OpenAI-compatible LLM API | `https://chat-ai.academiccloud.de/v1` |
| `GWDG_MODEL_API_KEY` | API key for the LLM provider | `your_api_key_here` |
| `K8S_MOCK_URL` | URL of the Kubernetes cluster or mock | `http://localhost:9988` |
| `AGENT_LLM_PROVIDER` | Provider identifier | `GWDG` |
| `AGENT_LLM_MODEL` | Model name to use | `openai-gpt-oss-120b` |

The LLM is accessed through [DSPy](https://github.com/stanfordnlp/dspy)'s LiteLLM adapter using the `openai/<model>` prefix, which means any OpenAI-compatible endpoint works.

---

## How to Run

### Interactive REPL (`k8scmd`)

Start the interactive session:

```bash
./k8scmd
```

You will see a prompt:

```
k8scmd> _
```

Type any goal in plain English and press Enter:

```
k8scmd> List all pods in the production namespace
k8scmd> Deploy a Redis pod named redis-cache in production and verify it is running
k8scmd> Delete the nginx-pod from production and confirm it no longer exists
```

| Input | Action |
|---|---|
| Any text + Enter | Run that as a goal |
| `q` / `quit` / `exit` | Exit the REPL |
| Empty Enter | Ignored |
| Ctrl+C during a run | Cancel current goal, stay in REPL |
| Ctrl+C at prompt | Exit |

### Single-shot CLI (`hpcsa`)

```bash
./hpcsa "your goal here"
./hpcsa "Deploy nginx in production" --retries 5
./hpcsa "List all nodes" --dry-run
./hpcsa "Deploy nginx" --model openai-gpt-4o
```

#### Options

| Flag | Short | Default | Description |
|---|---|---|---|
| `--retries N` | `-r` | `3` | Max retry attempts if goal not achieved |
| `--dry-run` | `-n` | off | Plan commands but do not execute them |
| `--model MODEL` | `-m` | from `.env` | Override the LLM model |

If you omit the goal, `hpcsa` will prompt you interactively.

### Adding to PATH

To run `k8scmd` and `hpcsa` from any directory:

```bash
echo 'export PATH="$PATH:/path/to/k8sCMD"' >> ~/.bashrc
source ~/.bashrc
```

---

## System Architecture

```
User
 │  plain English goal
 ▼
k8scmd / hpcsa
 │  initialise logging + ping cluster
 ▼
DspY.py — run_pipeline()
 │
 ├─▶ PlannerAgent   (dspy.ChainOfThought)
 │      └─▶ LLM: break goal into ordered task list
 │
 ├─▶ ExecutorAgent  (dspy.Predict)  [for each task]
 │      ├─▶ LLM: translate task → kubectl command
 │      ├─▶ Console: "About to execute: <cmd>  [y/n]"
 │      └─▶ K8sClient.execute() → HTTP call → k8s mock
 │
 ├─▶ ValidatorAgent (dspy.ChainOfThought)
 │      └─▶ LLM: did all commands succeed? → achieved: true/false
 │               └─ if false: corrective_action → retry Planner
 │
 └─▶ SummarizerAgent (dspy.Predict)
        └─▶ LLM: turn outputs into plain-English answer
                └─▶ printed to console
```

---

## Agent Pipeline

All agents are defined in `DspY.py` and communicate through typed [DSPy Signatures](https://dspy.ai).

### 1. PlannerAgent

**Role:** Converts a natural-language goal into an ordered list of atomic Kubernetes tasks.

**DSPy module:** `ChainOfThought` — the model reasons through task dependencies before committing to an order.

**Input:** `goal` (string)
**Output:** `List[str]` — numbered tasks parsed into a clean list

**Key rules in its signature:**
- Use the `production` namespace unless told otherwise
- Only use supported operations: create/delete pods, deployments, ingresses; get pods/deployments/nodes
- Output only the task list — no commentary

---

### 2. ExecutorAgent

**Role:** Translates each task into a single `kubectl` command and runs it via `K8sClient`.

**DSPy module:** `Predict` — clean single-string output; no reasoning tokens needed.

**Input:** `task` (string), `context` (accumulated results from previous tasks)
**Output:** `dict` with `task`, `command`, `output`, `success`

**Before each command**, the user is asked for confirmation:
```
  About to execute: kubectl run nginx-pod --image=nginx -n production --restart=Never
  Run this command? [y/n]:
```

Output is shown truncated to **5 lines** on the console; the full output is passed internally to the Validator and logged.

**Key rules in its signature:**
- Output only the kubectl command — nothing else
- No `--dry-run` flags
- No pipes or chained commands — one command only

---

### 3. ValidatorAgent

**Role:** Decides whether the original goal was fully achieved based on all execution results.

**DSPy module:** `ChainOfThought` — reasoning before verdict reduces false positives/negatives.

**Input:** `goal`, `tasks` (list), `results` (list of execution dicts)
**Output:** `dict` with `achieved` (bool), `reason`, `corrective_action`

**Retry logic:** If `achieved=False` and retries remain, the `corrective_action` is fed back into the Planner as additional context for the next attempt.

**Validation rules:**
- If all commands returned data without errors → `achieved = True`
- Only fails on explicit command errors (not-found, exception, etc.)
- A "list pods" goal is achieved as soon as the list is returned

---

### 4. SummarizerAgent

**Role:** Converts raw command outputs into a short, plain-English answer the user actually wants to read.

**DSPy module:** `Predict`

**Input:** `goal`, `commands` (one per line), `outputs` (one per line)
**Output:** 1–3 sentence plain-English answer

**Rules enforced in the signature:**
- State facts only — no suggested next steps, no follow-up commands
- No markdown code blocks or bullet points
- No filler phrases like "Based on the above..."

**Example output:**
```
The production namespace contains 3 running pods: nginx-pod, redis-cache, and web-deploy-aa2d.
```

---

## k8s Client (`k8s.py`)

`K8sClient` wraps the Kubernetes mock REST API. The base URL is read from `K8S_MOCK_URL` in `.env`.

### Key method: `execute(command)`

Parses a kubectl-style string and dispatches to the right HTTP call:

```python
from k8s import k8s

result = k8s.execute("kubectl get pods -n production")
# result = {"success": True, "output": "...", "command": "..."}

result = k8s.execute("kubectl run nginx-pod --image=nginx -n production --restart=Never")
result = k8s.execute("kubectl delete pod nginx-pod -n production")
result = k8s.execute("kubectl create deployment web-app --image=nginx -n production")
```

### Supported API endpoints

| Method | Endpoint | kubectl equivalent |
|---|---|---|
| `list_nodes()` | `GET /api/v1/nodes` | `kubectl get nodes` |
| `list_pods(ns)` | `GET /api/v1/namespaces/<ns>/pods` | `kubectl get pods -n <ns>` |
| `create_pod(ns, name, image)` | `POST /api/v1/namespaces/<ns>/pods` | `kubectl run <name> --image=<image>` |
| `delete_pod(ns, name)` | `DELETE /api/v1/namespaces/<ns>/pods/<name>` | `kubectl delete pod <name>` |
| `list_deployments(ns)` | `GET /apis/apps/v1/namespaces/<ns>/deployments` | `kubectl get deployments` |
| `create_deployment(ns, name, image)` | `POST /apis/apps/v1/namespaces/<ns>/deployments` | `kubectl create deployment` |
| `delete_deployment(ns, name)` | `DELETE /apis/apps/v1/namespaces/<ns>/deployments/<name>` | `kubectl delete deployment` |
| `list_ingresses(ns)` | `GET /apis/extensions/v1beta1/namespaces/<ns>/ingresses` | `kubectl get ingress` |
| `create_ingress(ns, name, ...)` | `POST /apis/extensions/v1beta1/namespaces/<ns>/ingresses` | `kubectl create ingress` |
| `delete_ingress(ns, name)` | `DELETE ...` | `kubectl delete ingress` |
| `ping()` | `GET /api/v1/nodes` | health check |

---

## LLM Backbone (`LLM.py`)

`LLM.py` is a standalone raw-`requests` wrapper for the GWDG OpenAI-compatible API — no `openai` or `httpx` dependency required.

It is **not used by the agent pipeline** (which goes through DSPy/LiteLLM), but is available for direct use or testing:

```python
from LLM import llm

llm.chat("What is Kubernetes?")
llm.set_system_prompt("You are a k8s expert.")
llm.test_connection()
```

---

## Logging

Every run creates a timestamped log file in `logs/`:

```
logs/session_20260302_143012.log
```

**What goes to the log file:**
- Session start time, model, and API URL
- Every attempt number and current goal
- Full task list from the Planner
- Every command, success flag, and complete output
- Validator reasoning, verdict, and corrective action
- Summarizer output

**What the console shows:**
- The goal
- Each command (with y/n confirmation prompt)
- First 5 lines of command output + `......` if truncated
- Final plain-English answer from the Summarizer

Third-party library loggers (`LiteLLM`, `httpx`, `httpcore`, `openai`) are suppressed to `WARNING` level on the console.

---

## CLI Reference

### `k8scmd` (interactive REPL)

```
Usage: ./k8scmd

Starts an interactive session. Type goals in plain English.
Type q to quit.
```

### `hpcsa` (single-shot)

```
Usage: ./hpcsa [goal] [options]

Arguments:
  goal              Natural-language goal (prompted if omitted)

Options:
  -r, --retries N   Max retry attempts (default: 3)
  -n, --dry-run     Plan only, do not execute commands
  -m, --model NAME  Override LLM model from .env
  -h, --help        Show help
```

---

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/llm_test.py -v
```

Tests cover: `LLM.test_connection`, `LLM.send_request`, `LLM.chat`, `LLM.custom_model`, `LLM.system_prompt`.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `dspy` | `>=3.1.0` | Agent framework + LiteLLM adapter |
| `requests` | `==2.32.3` | HTTP calls to k8s mock and LLM API |
| `python-dotenv` | `>=1.1.0` | Load `.env` configuration |

Install:
```bash
pip install -r requirements.txt
```

The `openai` and `httpx` packages are **not required** — DSPy's LiteLLM adapter handles the LLM calls, and `k8s.py` / `LLM.py` use plain `requests`.
