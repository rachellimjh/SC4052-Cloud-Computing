# c0der — zero code needed

A Python-based Coding-as-a-Service (CaaS) platform for beginners. Describe what you want to build in plain English — the AI agent plans, writes, runs, and debugs the code for you.

Built for NTU SC4052 — Topic 7: Coding-as-a-Service.

---

## Features

### Three Agent Modes
| Mode | What it does |
|------|-------------|
| 🧩 **Builder** | Plans architecture, writes files, runs code, self-critiques, and iterates until working |
| 🎓 **Mentor** | Annotates every line, gives a step-by-step walkthrough, highlights beginner mistakes, and sets challenges |
| 🧠 **Reviewer** | Analyses existing code for performance, security, and quality issues, rewrites it, and gives a score out of 10 |

### Self-Improving Agent Loop
The agent doesn't just generate and stop. It follows a **Generate → Test → Critique → Improve** loop:

```
User prompt
    │
    ▼
┌─────────────┐    ┌──────────────┐    ┌──────────────┐    ┌─────────────┐
│  Plan &     │───▶│  write_file  │───▶│  run_python  │───▶│  Critique   │
│  explain    │    │  (generate)  │    │  (test)      │    │  & improve  │
└─────────────┘    └──────────────┘    └──────────────┘    └──────┬──────┘
                                                                   │
                                             ◀── fix & retry ──────┘ (if errors)
                                                                   │
                                                            ┌──────▼──────┐
                                                            │  Report to  │
                                                            │    user     │
                                                            └─────────────┘
```

### In-Browser Code Editor
- View and edit generated files directly in the browser
- **Run** button executes the current file and shows output inline
- Tab key inserts spaces correctly

### Other Features
- **Session management** — multiple isolated workspaces, switch between sessions with full chat history preserved
- **Clear chat** — reset conversation without deleting workspace files
- **Markdown rendering** — agent responses render headings, code blocks, bold, lists properly
- **Docker sandbox** — optional isolated execution (no network, 128 MB RAM cap); falls back to subprocess automatically

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (HTML / CSS / Vanilla JS)                         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │  Chat Panel  │  │ File Browser │  │  Code Editor + Run │  │
│  │  3 Modes     │  │              │  │  button            │  │
│  └──────┬──────┘  └──────┬───────┘  └────────────────────┘  │
│─────────┼────────────────┼──────────────────────────────────│
│         ▼                ▼                                   │
│  Backend (FastAPI)                                           │
│  ┌──────────────────────────────────┐  ┌──────────────────┐ │
│  │  Agent Loop (think-act-observe)  │  │ Session Manager  │ │
│  │  ┌────────────┐  ┌────────────┐  │  └──────────────────┘ │
│  │  │  Provider  │  │   Tools    │  │                        │
│  │  │ OpenRouter │  │ read_file  │  │                        │
│  │  │  Gemini    │  │ write_file │  │                        │
│  │  │  Claude    │  │ list_files │  │                        │
│  │  └────────────┘  │ run_python │  │                        │
│  │                  │ run_shell  │  │                        │
│  │                  └────────────┘  │                        │
│  └──────────────────────────────────┘                        │
│                                                              │
│  Sandbox (Docker or subprocess fallback)                     │
│  ┌──────────────────────────────────┐                        │
│  │ Isolated · No network · 128 MB   │                        │
│  └──────────────────────────────────┘                        │
└──────────────────────────────────────────────────────────────┘
```

### How the Agent Loop Works

Inspired by [Ben Recht's microagent](https://github.com/benjamin-recht/microagent):

1. **User sends a message** → appended to conversation history
2. **LLM receives** system prompt (chosen by mode) + full history + tool definitions
3. **LLM responds** with text and/or tool calls (`write_file`, `run_python`, `run_shell`, …)
4. **Agent executes** each tool call and appends results to history
5. **Loop repeats** until the LLM produces a text-only reply (no more tool calls)
6. **Final answer** is streamed back to the user

---

## Quick Start

### Prerequisites

- Python 3.11+
- One of:
  - **OpenRouter API key** — free at [openrouter.ai](https://openrouter.ai) (supports 100+ models)
  - **Gemini API key** — free at [aistudio.google.com](https://aistudio.google.com/apikey)
  - **Anthropic API key** — [console.anthropic.com](https://console.anthropic.com)

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/rachellimjh/SC4052-Cloud-Computing.git
cd SC4052-Cloud-Computing

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create your .env file
cp .env.example .env
```

Edit `.env` and add your API key. Only one is needed:

```env
# Option A — OpenRouter (recommended, access to many free models)
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=google/gemma-4-31b-it:free   # optional, this is the default

# Option B — Google Gemini
GEMINI_API_KEY=AIza...

# Option C — Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-...
```

**Priority:** `OPENROUTER_API_KEY` > `GEMINI_API_KEY` > `ANTHROPIC_API_KEY`

```bash
# 4. Start the server
python run.py
```

Open **http://localhost:8000** in your browser.

### Optional: Docker Sandbox

For fully isolated code execution:

```bash
# Make sure Docker Desktop is running first
docker build -t vibecoder-sandbox sandbox/
```

If Docker is unavailable, code runs via a subprocess fallback automatically.

---

## Usage

1. Open **http://localhost:8000**
2. Select a mode in the sidebar: **Builder**, **Mentor**, or **Reviewer**
3. Type what you want in the chat and press **Send** or **Ctrl+Enter**
4. Watch the agent write files, run code, and iterate
5. Click any file in the right panel to view and edit it
6. Hit **Run** to execute your edits and see output inline

### Example Prompts

**Builder mode**
- *"Build a number guessing game where the computer picks a random number"*
- *"Create a to-do list app that saves tasks to a JSON file"*
- *"Write a web scraper that fetches the top 5 headlines from a news site"*

**Mentor mode**
- *"Explain how a Python dictionary works and show me an example"*
- *"Build a simple calculator and teach me what each line does"*

**Reviewer mode** *(requires files in workspace — use Builder first)*
- *"Review my code for any issues"*
- *"Can you improve the performance of main.py?"*

---

## Project Structure

```
SC4052_group/
├── run.py                          # Entry point — starts the server
├── requirements.txt                # Python dependencies
├── benchmark.py                    # Evaluation script (HumanEval)
├── .env.example                    # API key template
│
├── backend/
│   ├── app.py                      # FastAPI REST API
│   ├── agent/
│   │   ├── models.py               # ToolCall, Response dataclasses
│   │   ├── loop.py                 # Agent loop + 3 system prompts
│   │   ├── providers/
│   │   │   ├── base.py             # Abstract Provider interface
│   │   │   ├── claude.py           # Anthropic Claude
│   │   │   ├── gemini.py           # Google Gemini
│   │   │   └── openrouter.py       # OpenRouter (OpenAI-compatible)
│   │   └── tools/
│   │       ├── base.py             # Abstract Tool base class
│   │       ├── read_file.py        # Read workspace files
│   │       ├── write_file.py       # Write workspace files
│   │       ├── list_files.py       # List workspace directory
│   │       ├── run_code.py         # Sandboxed Python execution
│   │       └── run_shell.py        # Shell commands (git, pytest, etc.)
│   ├── sessions/
│   │   └── manager.py              # Per-session workspace isolation
│   └── evaluation/
│       ├── metrics.py              # Execution rate, Pass@k, CodeBLEU
│       └── humaneval.py            # HumanEval dataset loader
│
├── frontend/
│   ├── index.html                  # Main UI
│   ├── css/style.css               # Styling
│   └── js/
│       ├── app.js                  # Chat, file browser, session switching
│       └── marked.min.js           # Markdown rendering (local copy)
│
├── sandbox/
│   └── Dockerfile                  # Docker sandbox image
│
├── data/
│   └── HumanEval.jsonl             # 164 HumanEval problems
│
├── tests/
│   ├── test_sessions.py            # Session endpoint tests
│   └── test_run_shell.py           # RunShellTool tests
│
└── workspaces/                     # Per-session dirs (gitignored)
```

---

## Evaluation

The benchmark evaluates c0der against the [OpenAI HumanEval dataset](https://arxiv.org/abs/2107.03374) using three tiers:

| Tier | Metric | Question answered |
|------|--------|-------------------|
| 1 | **Execution Success Rate** | Does the code run without errors? |
| 2 | **Pass@k** (unbiased estimator) | Does it pass all functional tests? |
| 3 | **CodeBLEU** | Does it match expert style? (n-gram + AST + data-flow) |

### Running the Benchmark

```bash
# Default: 15 random problems, 3 samples each
python benchmark.py

# Custom run
python benchmark.py --problems 20 --samples 5 --k 10

# Quick single-problem test
python benchmark.py --problems 1 --samples 1
```

Results are printed as a table and saved to `benchmark_results.json`.

### Running Tests

```bash
pytest tests/ -v
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/sessions` | Create a new session |
| `GET` | `/api/sessions` | List all sessions |
| `GET` | `/api/sessions/{id}/history` | Get chat display history |
| `DELETE` | `/api/sessions/{id}/history` | Clear chat history |
| `GET` | `/api/sessions/{id}/files` | List workspace files |
| `GET` | `/api/sessions/{id}/files/{path}` | Read a file |
| `POST` | `/api/sessions/{id}/chat` | Send a message (`mode`: builder/mentor/reviewer) |
| `POST` | `/api/sessions/{id}/run` | Save and run edited code |
| `WS` | `/api/sessions/{id}/ws` | WebSocket for streaming events |

---

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, Uvicorn
- **LLM Providers**: OpenRouter, Google Gemini, Anthropic Claude (auto-detected from `.env`)
- **Frontend**: HTML, CSS, Vanilla JavaScript — no framework, no build step
- **Sandbox**: Docker (optional), subprocess fallback
- **Evaluation**: HumanEval, Pass@k, CodeBLEU (implemented from scratch)
