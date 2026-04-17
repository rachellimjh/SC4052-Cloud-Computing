# c0der — Project Summary
**NTU SC4052 Cloud Computing | Topic 7: Coding-as-a-Service**

---

## 1. What is c0der?

c0der ("zero code needed") is a web-based Coding-as-a-Service (CaaS) platform designed for beginners. Users describe what they want to build in plain English — the AI agent plans the solution, writes the code, runs it, critiques its own output, and iterates until it works. No programming knowledge is required.

The project is framed around the concept of **vibe coding** (Andrej Karpathy, Feb 2025) — using natural language to drive code generation — and extends it into a full agentic engineering platform where the AI does not just generate but also tests, reviews, and explains.

---

## 2. Key Features

| Feature | Description |
|---|---|
| **3 Agent Modes** | Builder, Mentor, Reviewer — each changes the agent's behaviour via a different system prompt |
| **Self-improving loop** | Agent generates → tests → critiques → improves before reporting done |
| **In-browser code editor** | Edit generated files in the browser; Run button executes and shows output inline |
| **Markdown rendering** | Agent responses render headings, code blocks, bold, lists properly |
| **Session management** | Multiple isolated workspaces; switch between sessions with full chat history preserved |
| **Clear chat** | Reset conversation without deleting workspace files |
| **Multi-provider support** | OpenRouter, Google Gemini, Anthropic Claude — auto-detected from `.env` |
| **Docker sandbox** | Optional isolated execution (no network, 128 MB RAM); falls back to subprocess |
| **Error handling** | Rate limits, auth failures, and API errors shown as clean chat messages |

---

## 3. The Three Modes (Novelty)

### 🧩 Builder Mode (default)
The agent acts as an AI pair programmer. For every request it:
1. Plans the solution in plain English
2. Writes code using `write_file`
3. Runs it using `run_python`
4. Critiques its own output — even if there are no errors
5. Improves if needed, then re-runs
6. Reports what was built and how to use it

This realises a **Generate → Test → Critique → Improve** self-improving loop. The agent only declares success after code has been run and reviewed.

### 🎓 Mentor Mode (Teaching Mode — novelty feature)
Designed for users who want to learn, not just receive code. Every response follows a fixed structure:
- **Plan** — what will be built and why
- **Code** — with a comment above every meaningful line
- **Line-by-Line Walkthrough** — explained with real-world analogies
- **Common Beginner Mistakes** — 2–3 pitfalls to avoid
- **Try It Yourself** — a small challenge for the user

### 🧠 Reviewer Mode (novelty feature)
Designed for users who have existing code and want it improved. Every response follows a fixed structure:
- **Performance** — inefficiencies with Big-O analysis
- **Security** — hardcoded secrets, injection risks, missing validation
- **Code Quality** — bad naming, duplication, missing error handling
- **What's Good** — balanced, not just critical
- **Improved Version** — rewritten code saved and re-run
- **Quality Score** — original code rated X/10 with justification

**Guard:** If Reviewer Mode is selected but the workspace has no files, a message is shown immediately without hitting the backend.

All three modes include a **scope restriction**: if the user asks something unrelated to coding, the agent politely redirects them.

---

## 4. Architecture

```
Browser (HTML / CSS / Vanilla JS)
├── Chat Panel + Mode Selector (Builder | Mentor | Reviewer)
├── File Browser
└── Code Editor + Run button
        │
        │  HTTP REST / JSON
        ▼
Backend (FastAPI / Python)
├── Agent Loop (think → act → observe)
│   ├── System Prompt  ← chosen by mode
│   ├── LLM Provider   ← OpenRouter / Gemini / Claude
│   ├── Tool Executor
│   └── Iteration cap: 25
├── Session Manager
│   ├── Session ID + workspace path
│   ├── LLM conversation history
│   ├── Display history (chat restore)
│   └── Current mode
└── Tools
    ├── read_file     — read workspace files
    ├── write_file    — create/overwrite workspace files
    ├── list_files    — list workspace directory
    ├── run_python    — execute Python files
    └── run_shell     — run any shell command (git, pytest, curl…)
        │
        │  subprocess / Docker API
        ▼
Execution Sandbox
├── Docker (--network none, --memory 128m, read-only FS)  [if available]
└── Subprocess fallback                                    [always available]
```

---

## 5. Agent Loop (How It Works)

Inspired by [Ben Recht's microagent](https://github.com/benjamin-recht/microagent).

1. User message is appended to conversation history
2. LLM receives: system prompt + full history + tool definitions (as JSON schemas)
3. LLM responds with text and/or tool calls (`write_file`, `run_python`, etc.)
4. Agent executes each tool call, captures the result, appends it as an observation
5. Repeat from step 2 until LLM responds with text only (no more tool calls)
6. Final answer is returned to the user

**Key principle:** reasoning is delegated entirely to the LLM; execution is handled deterministically by the agent. The LLM never runs code directly — it can only request that the agent does so through the tool interface.

---

## 6. Provider Abstraction

All LLM-specific logic sits behind an abstract `Provider` interface:

```python
def chat(system_prompt, messages, tools) -> Response
```

| Provider | API | Default model |
|---|---|---|
| `OpenRouterProvider` | OpenAI-compatible | `google/gemma-4-31b-it:free` |
| `GeminiProvider` | Google GenAI SDK | `gemini-2.5-flash` |
| `ClaudeProvider` | Anthropic SDK | `claude-sonnet-4-20250514` |

Priority: `OPENROUTER_API_KEY` > `GEMINI_API_KEY` > `ANTHROPIC_API_KEY`

Swapping providers requires no changes to the agent loop. A notable implementation detail: Gemini requires strictly alternating `user`/`model` roles, so the Gemini provider merges consecutive same-role messages before each API call.

---

## 7. Tool Abstraction

Each tool is a self-describing class with `name`, `description`, and `schema` (JSON Schema). The agent loop passes these to the LLM, which decides when to call them. Adding a new tool requires no changes to the loop.

All file tools enforce **path traversal prevention** — resolved paths are checked to stay within the session workspace.

`run_shell` enables the full coding-agent workflow: `pytest` for testing, `git` for version control, `curl` for GitHub API calls (PR creation).

---

## 8. Session Management

Each session has:
- A unique 12-character ID
- An isolated workspace directory (`workspaces/{id}/`)
- **LLM history** — the raw message list passed to the LLM each turn
- **Display history** — plain-text records of messages and tool events, used to restore the chat panel when switching sessions
- **Mode** — current agent mode (`builder` / `mentor` / `reviewer`)

Sessions persist in memory for the server's lifetime.

---

## 9. Frontend

Single-page application — no framework, no build step.

| Element | Description |
|---|---|
| Sidebar | Session list, New Session button, 3-mode selector |
| Chat panel | Sends messages, renders responses as Markdown, shows tool events |
| File browser | Lists all workspace files; click to open in editor |
| Code editor | Editable textarea; Tab inserts spaces |
| Run button | Saves edits server-side, executes file, shows output inline |
| Clear button | Resets chat history, preserves files |

---

## 10. Evaluation

Benchmarks c0der against the [OpenAI HumanEval dataset](https://arxiv.org/abs/2107.03374) (164 problems).

### 3-Tier Metrics

| Tier | Metric | What it measures |
|---|---|---|
| 1 | **Execution Success Rate** | Does the code run without syntax/runtime errors? |
| 2 | **Pass@k** (unbiased estimator) | Does it pass all functional test cases? |
| 3 | **CodeBLEU** | Does it match expert style? (n-gram + AST + data-flow) |

**Pass@k** uses the unbiased estimator from the Codex paper (Chen et al., 2021):

$$\text{pass@}k = 1 - \frac{\binom{n-c}{k}}{\binom{n}{k}}$$

where $n$ = total samples, $c$ = samples that pass all tests, $k$ = target.

**CodeBLEU** is implemented from scratch with three components:
- N-gram match (token overlap with reference)
- AST match (Jaccard similarity of AST node types)
- Data-flow match (Jaccard similarity of variable-operation edges)

### Running the Benchmark

```bash
python benchmark.py                          # 15 problems, 3 samples
python benchmark.py --problems 20 --k 10    # custom
pytest tests/ -v                             # unit tests
```

---

## 11. API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/sessions` | Create a new session |
| `GET` | `/api/sessions` | List all sessions |
| `GET` | `/api/sessions/{id}/history` | Get chat display history |
| `DELETE` | `/api/sessions/{id}/history` | Clear chat history |
| `GET` | `/api/sessions/{id}/files` | List workspace files |
| `GET` | `/api/sessions/{id}/files/{path}` | Read a file |
| `POST` | `/api/sessions/{id}/chat` | Send a message (`mode`: builder/mentor/reviewer) |
| `POST` | `/api/sessions/{id}/run` | Save and execute edited code |
| `WS` | `/api/sessions/{id}/ws` | WebSocket streaming |

---

## 12. Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI + Uvicorn |
| LLM providers | OpenRouter, Google Gemini, Anthropic Claude |
| Frontend | HTML5, CSS3, Vanilla JavaScript |
| Markdown | marked.js (bundled locally) |
| Sandbox | Docker (optional) + subprocess fallback |
| Evaluation dataset | OpenAI HumanEval (164 problems, JSONL) |
| Tests | pytest + FastAPI TestClient |
| Language | Python 3.11+ |

---

## 13. Project Structure

```
SC4052_group/
├── run.py                          # Start the server
├── benchmark.py                    # HumanEval evaluation script
├── requirements.txt
├── .env.example
│
├── backend/
│   ├── app.py                      # FastAPI routes
│   ├── agent/
│   │   ├── loop.py                 # Agent loop + 3 system prompts
│   │   ├── models.py               # ToolCall, Response dataclasses
│   │   ├── providers/
│   │   │   ├── base.py             # Abstract Provider
│   │   │   ├── claude.py
│   │   │   ├── gemini.py
│   │   │   └── openrouter.py
│   │   └── tools/
│   │       ├── base.py             # Abstract Tool
│   │       ├── read_file.py
│   │       ├── write_file.py
│   │       ├── list_files.py
│   │       ├── run_code.py         # Docker + subprocess sandbox
│   │       └── run_shell.py        # Shell command tool
│   ├── sessions/
│   │   └── manager.py
│   └── evaluation/
│       ├── metrics.py              # Exec rate, Pass@k, CodeBLEU
│       └── humaneval.py            # Dataset loader
│
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── app.js
│       └── marked.min.js
│
├── sandbox/
│   └── Dockerfile
│
├── data/
│   └── HumanEval.jsonl             # 164 problems
│
└── tests/
    ├── test_sessions.py            # 13 endpoint tests
    └── test_run_shell.py           # 8 tool tests
```

---

## 14. Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| System prompt per mode | Cleanest way to change agent behaviour; no branching logic in the loop |
| Separate display history from LLM history | LLM history uses structured message dicts; display history is human-readable for chat restore |
| `run_shell` over a dedicated git tool | One general tool subsumes git, pytest, curl — fewer tools = simpler LLM context |
| Subprocess fallback for Docker | Makes the platform usable without Docker Desktop; isolation is optional for local dev |
| Provider abstraction | Allows swapping models without touching the agent; useful for benchmarking across providers |
| Vanilla JS frontend | Zero build step; anyone can run the project with just `python run.py` |
| Reviewer guard (no files check) | Prevents a confusing empty review; gives the user clear guidance on the right workflow |
