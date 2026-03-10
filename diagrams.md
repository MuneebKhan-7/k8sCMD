# k8sCMD Diagrams

Here are the Mermaid diagrams for the project. By installing a Mermaid extension in VS Code, you can preview these directly in your editor.

## Diagram 1: High-Level System Architecture

```mermaid
flowchart TD
    %% Define styles
    classDef user fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef python fill:#ffd43b,stroke:#306998,stroke-width:2px;
    classDef external fill:#eee,stroke:#999,stroke-width:2px;

    User((User)):::user -->|Natural Language Goal| CLI[CLI Tools<br>hpcsa.py / k8scmd.py]:::python
    
    subgraph k8sCMD Workspace
        CLI -->|Initializes & Routes| Orchestrator[DSPy Orchestrator<br>DspY.py]:::python
        Orchestrator -->|Executes Instructions| K8sClient[K8s REST Client<br>k8s.py]:::python
    end

    Orchestrator <-->|Chat Completions API| LLM[LLM Provider<br>GWDG Academic Cloud]:::external
    K8sClient <-->|HTTP GET/POST/DELETE| Cluster[(Kubernetes Cluster)]:::external
```

## Diagram 2: 4-Agent DSPy Execution Pipeline

```mermaid
flowchart TD
    %% Define Styles
    classDef agent fill:#e1f5fe,stroke:#0288d1,stroke-width:2px
    classDef cluster fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
    classDef decision fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef terminal fill:#333,stroke:#fff,stroke-width:2px,color:#fff

    Start([Plain English Goal]):::terminal --> Planner
    
    subgraph DSPy Execution Pipeline
        Planner[Planner Agent<br>dspy.ChainOfThought]:::agent -->|Ordered Task List| Executor
        Executor[Executor Agent<br>dspy.Predict]:::agent -->|Translates to kubectl| Execution
        
        Execution[[Execute against K8s API]]:::cluster --> Result[Execution Result/State]
        
        Result --> Validator[Validator Agent<br>dspy.ChainOfThought]:::agent
        Validator --> Check{Goal Fully<br>Achieved?}:::decision
        
        Check -->|No| Fix[Corrective Action Prompt]:::terminal
        Fix -->|Inject Error Context| Planner
        
        Check -->|Yes| Summarizer[Summarizer Agent<br>dspy.Predict]:::agent
    end
    
    Summarizer --> End([Plain English Summary Console Output]):::terminal
```
