# K8S CMD — System Architecture

## Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          User Interface                                 │
│                                                                         │
│   $ k8scmd                          $ hpcsa "deploy nginx in prod"      │
│   k8scmd> <natural language goal>   (single-shot CLI)                   │
│                  │                              │                       │
│                  └──────────────┬───────────────┘                       │
└─────────────────────────────────┼───────────────────────────────────────┘
                                  │  goal (plain English)
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         k8scmd.py / hpcsa.py                            │
│                                                                         │
│   • Initialises logging  (logs/session_YYYYMMDD_HHMMSS.log)             │
│   • Pings k8s cluster    (abort if unreachable)                         │
│   • Calls run_pipeline() from DspY.py                                   │
│   • Prints clean summary to console                                     │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        DspY.py  — Pipeline Orchestrator                 │
│                                                                         │
│   run_pipeline(goal, max_retries)                                       │
│                                                                         │
│   ┌─────────────┐    tasks     ┌─────────────┐   results  ┌──────────┐ │
│   │   Planner   │ ──────────▶  │  Executor   │ ─────────▶ │Validator │ │
│   │   Agent     │              │   Agent     │            │  Agent   │ │
│   └─────────────┘              └─────────────┘            └──────────┘ │
│          ▲                            │                        │        │
│          │   corrective_action        │  kubectl commands      │        │
│          └────────────────────────────┘  (y/n confirmed)      │        │
│                    retry loop ◀────────────────────────────────┘        │
│                                                                         │
│                                        ┌─────────────┐                 │
│                                        │ Summarizer  │                 │
│                                        │   Agent     │                 │
│                                        └──────┬──────┘                 │
└───────────────────────────────────────────────┼────────────────────────┘
                                                │ plain-English answer
                    ┌───────────────────────────┼───────────────────────┐
                    │       DSPy Framework       │                       │
                    │                            ▼                       │
                    │   ChainOfThought ──▶  [ Planner, Validator ]       │
                    │   Predict        ──▶  [ Executor, Summarizer ]     │
                    │                                                     │
                    │   dspy.LM  (LiteLLM adapter)                       │
                    │        │                                            │
                    └────────┼────────────────────────────────────────── ┘
                             │  HTTP POST /v1/chat/completions
                             ▼
               ┌─────────────────────────────┐
               │     GWDG Academic Cloud      │
               │  chat-ai.academiccloud.de    │
               │                             │
               │  Model: openai-gpt-oss-120b  │
               └─────────────────────────────┘


                    ┌────────────────────────────────────────┐
                    │              k8s.py                    │
                    │          K8sClient                     │
                    │                                        │
                    │  execute(command)                      │
                    │    └─▶ _dispatch(tokens)               │
                    │          ├─▶ create_pod()              │
                    │          ├─▶ list_pods()               │
                    │          ├─▶ delete_pod()              │
                    │          ├─▶ create_deployment()       │
                    │          ├─▶ list_deployments()        │
                    │          ├─▶ create_ingress()          │
                    │          └─▶ list_nodes()              │
                    │                    │                   │
                    └────────────────────┼───────────────────┘
                                         │  REST API calls
                                         │  HTTP GET/POST/DELETE
                                         ▼
                    ┌────────────────────────────────────────┐
                    │   Kubernetes Cluster Mock              │
                    │   (Docker: ezequielmr94/              │
                    │    kubernetes-cluster-mock)            │
                    │                                        │
                    │   localhost:9988                       │
                    │                                        │
                    │   /api/v1/nodes                        │
                    │   /api/v1/namespaces/<ns>/pods         │
                    │   /apis/apps/v1/.../deployments        │
                    │   /apis/extensions/v1beta1/.../ingress │
                    │   /custom_routes/...                   │
                    └────────────────────────────────────────┘
```

---

## Agent Roles

| Agent | DSPy Module | Purpose |
|---|---|---|
| **PlannerAgent** | `ChainOfThought` | Breaks a natural-language goal into an ordered list of atomic k8s tasks |
| **ExecutorAgent** | `Predict` | Translates each task into a kubectl command and runs it via `K8sClient` |
| **ValidatorAgent** | `ChainOfThought` | Checks whether the goal was fully achieved; triggers retry with corrective action if not |
| **SummarizerAgent** | `Predict` | Converts raw command outputs into a plain-English answer for the user |

---

## Data Flow

```
User goal
   │
   ▼
PlannerAgent  ──▶  ["create pod nginx", "verify pod running", ...]
                            │
                            ▼  (for each task)
                   ExecutorAgent  ──▶  "kubectl run nginx-pod --image=nginx -n production"
                            │                  │
                            │           K8sClient.execute()
                            │                  │
                            │           HTTP POST → k8s mock
                            │                  │
                            │           {"success": true, "output": "..."}
                            │
                            ▼  (all results)
                   ValidatorAgent  ──▶  achieved=True / False
                            │
                     ┌──────┴──────┐
                   True          False
                     │              │
                     ▼              ▼
              SummarizerAgent   retry with
                     │          corrective_action
                     ▼          fed back to Planner
              Plain-English
                 answer
                     │
                     ▼
              Console output
```

---

## File Map

```
Project HPCSA/
├── k8scmd.py          ← interactive REPL  (k8scmd command)
├── k8scmd             ← bash launcher
├── hpcsa.py           ← single-shot CLI   (hpcsa "goal")
├── hpcsa              ← bash launcher
├── DspY.py            ← 4-agent pipeline + DSPy configuration
├── k8s.py             ← K8sClient REST wrapper for the mock
├── LLM.py             ← raw requests-based LLM wrapper (standalone use)
├── agents.py          ← (reserved)
├── orchestration.py   ← (reserved)
├── .env               ← API keys, model name, K8S_MOCK_URL
├── requirements.txt   ← python-dotenv, requests, dspy
├── logs/              ← per-session log files (session_YYYYMMDD_HHMMSS.log)
└── tests/
    └── llm_test.py    ← unit tests for LLM.py
```
