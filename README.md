# VibeCoder — Coding-as-a-Service

A Python-based Coding-as-a-Service platform that lets beginners build software through natural-language descriptions (vibe coding). Powered by an AI agent that writes, runs, and debugs code autonomously.

Built for NTU SC4052 — Topic 7: Coding-as-a-Service.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Frontend (HTML/CSS/JS)                                  │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │
│  │ Chat Panel  │  │File Browser│  │   Code Viewer      │  │
│  └──────┬─────┘  └─────┬──────┘  └────────────────────┘  │
│         │              │                                  │
│─────────┼──────────────┼──────────────────────────────────│
│         ▼              ▼                                  │
│  Backend (FastAPI)                                       │
│  ┌──────────────────────────────┐  ┌──────────────────┐  │
│  │  Agent Loop (think-act-observe) │  │ Session Manager │  │
│  │  ┌──────────┐  ┌───────────┐│  └──────────────────┘  │
│  │  │ Provider  │  │   Tools   ││                         │
│  │  │(Gemini or │  │read_file  ││                         │
│  │  │  Claude)  │  │write_file ││                         │
│  │  └──────────┘  │list_files ││                         │
│  │                 │run_python ││                         │
│  │                 └───────────┘│                         │
│  └──────────────────────────────┘                        │
│                                                          │
│  Sandbox (Docker or subprocess)                          │
│  ┌──────────────────────────────┐                        │
│  │ Isolated code execution      │                        │
│  │ No network · 128MB RAM cap   │                        │
│  └──────────────────────────────┘                        │
└──────────────────────────────────────────────────────────┘
```

### How the Agent Loop Works

The agent follows a **think → act → observe** cycle, inspired by [Ben Recht's microagent](https://github.com/benjamin-recht/microagent):

1. **User sends a message** → appended to conversation history
2. **LLM receives** the system prompt + full history + tool definitions
3. **LLM responds** with text and/or tool calls (e.g. `write_file`, `run_python`)
4. **Agent executes** each tool call and appends results to history
5. **Loop repeats** until the LLM responds with text only (no tool calls)
6. **Final answer** is returned to the user

```
User: "Build me a calculator"
  │
  ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  LLM thinks │────▶│ write_file() │────▶│ run_python() │──┐
│  "I'll make │     │ calc.py      │     │ calc.py      │  │
│   calc.py"  │     └──────────────┘     └──────────────┘  │
└─────────────┘                                             │
       ▲                                                    │
       └──── observe output, fix errors if any ◄────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- A Gemini API key (free at [aistudio.google.com](https://aistudio.google.com/apikey)) **or** an Anthropic API key

### Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd SC4052_group

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your .env file with your API key
#    Copy the example and edit it:
cp .env.example .env
#    Then open .env and paste your key:
#    GEMINI_API_KEY=your-key-here
#    (or ANTHROPIC_API_KEY=your-key-here)

# 4. Start the server
python run.py
```

Open **http://localhost:8000** in your browser.

### Optional: Docker Sandbox

For isolated code execution (no network, memory-limited containers):

```bash
# Make sure Docker Desktop is running first
docker build -t vibecoder-sandbox sandbox/
```

If Docker is not available, code runs via subprocess fallback (works fine for local use).

## Usage

1. Open http://localhost:8000
2. Type a description of what you want to build in the chat box
3. Press **Send** or **Ctrl+Enter**
4. Watch the agent write files, run code, and fix errors
5. Browse generated files in the right panel
6. Click any file to view its contents

### Example Prompts

- *"Make a number guessing game where the computer picks a random number and I try to guess it"*
- *"Write a program that reads a CSV file and plots a bar chart"*
- *"Create a to-do list app that saves tasks to a JSON file"*

## Project Structure

```
SC4052_group/
├── run.py                              # Entry point — starts the server
├── requirements.txt                    # Python dependencies
├── benchmark.py                        # Evaluation script (HumanEval)
├── .env.example                        # API key template
│
├── backend/
│   ├── app.py                          # FastAPI REST + WebSocket API
│   ├── agent/
│   │   ├── models.py                   # ToolCall, Response dataclasses
│   │   ├── loop.py                     # Core think-act-observe agent loop
│   │   └── providers/
│   │       ├── base.py                 # Abstract Provider interface
│   │       ├── claude.py               # Anthropic Claude integration
│   │       └── gemini.py               # Google Gemini integration
│   │   └── tools/
│   │       ├── base.py                 # Abstract Tool base class
│   │       ├── read_file.py            # Read workspace files
│   │       ├── write_file.py           # Write workspace files
│   │       ├── list_files.py           # List workspace directory
│   │       └── run_code.py             # Sandboxed Python execution
│   ├── sessions/
│   │   └── manager.py                  # Per-user session + workspace isolation
│   └── evaluation/
│       ├── metrics.py                  # 3-tier metrics (Exec, Pass@k, CodeBLEU)
│       └── humaneval.py                # HumanEval dataset loader
│
├── frontend/
│   ├── index.html                      # Main UI
│   ├── css/style.css                   # Dark-themed styling
│   └── js/app.js                       # Chat, file browser, session switching
│
├── sandbox/
│   └── Dockerfile                      # Docker sandbox image
│
├── data/
│   └── HumanEval.jsonl                 # OpenAI HumanEval dataset (164 problems)
│
└── workspaces/                         # Sandboxed per-session directories (gitignored)
```

## Evaluation

The benchmark script evaluates VibeCoder against the [OpenAI HumanEval dataset](https://arxiv.org/abs/2107.03374) using three tiers of metrics:

| Tier | Metric | Question |
|------|--------|----------|
| 1 | **Execution Success Rate** | Does the generated code run without syntax/runtime errors? |
| 2 | **Pass@k / Functional Correctness** | Does it pass all assertion tests? |
| 3 | **CodeBLEU** | Does it match expert style (n-gram, AST, data-flow similarity)? |

### Running the Benchmark

```bash
# Default: 15 random HumanEval problems, 3 samples each
python benchmark.py

# Customize
python benchmark.py --problems 20 --samples 5 --k 10

# Single problem for quick testing
python benchmark.py --problems 1 --samples 1
```

Results are printed as a table and saved to `benchmark_results.json`.

### Example Output

```
Task                          Exec%  Pass@1  Pass@k  Corr%   BLEU
generate_integers              100%  100.0%  100.0%   100%  0.856
concatenate                    100%  100.0%  100.0%   100%  0.712
is_multiply_prime              100%   66.7%  100.0%    67%  0.634
...
AVERAGE                         93%   78.3%   91.2%    76%  0.694
```

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions` | Create a new session |
| `GET` | `/api/sessions` | List all sessions |
| `GET` | `/api/sessions/{id}/history` | Get chat history for a session |
| `GET` | `/api/sessions/{id}/files` | List files in workspace |
| `GET` | `/api/sessions/{id}/files/{path}` | Read a file |
| `POST` | `/api/sessions/{id}/chat` | Send a message to the agent |
| `WS` | `/api/sessions/{id}/ws` | WebSocket for streaming |

## Tech Stack

- **Backend**: Python, FastAPI, Anthropic SDK, Google GenAI SDK
- **Frontend**: HTML, CSS, JavaScript (no framework — zero build step)
- **Sandbox**: Docker (optional, subprocess fallback)
- **Evaluation**: HumanEval dataset, Pass@k, CodeBLEU
