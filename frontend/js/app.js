/**
 * c0der Frontend — handles sessions, chat, and file browsing.
 */

const API = "";  // Same origin

// --- State ---
let currentSessionId = null;
let isProcessing = false;

// --- DOM refs ---
const sessionList = document.getElementById("session-list");
const newSessionBtn = document.getElementById("new-session-btn");
const messagesDiv = document.getElementById("messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");
const clearBtn = document.getElementById("clear-btn");
const fileList = document.getElementById("file-list");
const codeFilename = document.getElementById("code-filename");
const codeEditor = document.getElementById("code-editor");
const runBtn = document.getElementById("run-btn");
const runOutput = document.getElementById("run-output");
const runOutputContent = document.getElementById("run-output-content");
const modeBtns = document.querySelectorAll(".mode-btn");
let currentMode = "builder";

modeBtns.forEach((btn) => {
  btn.addEventListener("click", () => {
    modeBtns.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentMode = btn.dataset.mode;
  });
});

let currentFilePath = null;

// --- Sessions ---

async function createSession() {
  const res = await fetch(`${API}/api/sessions`, { method: "POST" });
  const session = await res.json();
  currentSessionId = session.id;
  messagesDiv.innerHTML = "";
  fileList.innerHTML = "";
  codeFilename.textContent = "Select a file";
  codeEditor.value = "";
  codeEditor.disabled = true;
  runBtn.disabled = true;
  currentFilePath = null;
  runOutput.classList.add("hidden");
  await refreshSessionList();
}

async function refreshSessionList() {
  const res = await fetch(`${API}/api/sessions`);
  const sessions = await res.json();
  sessionList.innerHTML = "";
  sessions.forEach((s) => {
    const li = document.createElement("li");
    li.textContent = s.title || "New Session";
    li.dataset.id = s.id;
    if (s.id === currentSessionId) li.classList.add("active");
    li.addEventListener("click", () => switchSession(s.id));
    sessionList.appendChild(li);
  });
}

async function switchSession(id) {
  currentSessionId = id;
  messagesDiv.innerHTML = "";
  document.querySelectorAll("#session-list li").forEach((li) => {
    li.classList.toggle("active", li.dataset.id === id);
  });
  await loadHistory(id);
  refreshFiles();
}

async function loadHistory(sessionId) {
  try {
    const res = await fetch(`${API}/api/sessions/${sessionId}/history`);
    if (!res.ok) return;
    const messages = await res.json();
    for (const msg of messages) {
      if (msg.kind === "user") {
        appendMessage("user", msg.content);
      } else if (msg.kind === "assistant") {
        appendMessage("assistant", msg.content);
      } else if (msg.kind === "tool_event") {
        appendToolEvent({ tool: msg.tool, params: msg.params, result: msg.result });
      }
    }
  } catch (e) {
    // Silently fail — session may just be empty
  }
}

// --- Chat ---

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message || isProcessing) return;

  if (!currentSessionId) await createSession();

  // Warn if Reviewer Mode is selected but workspace has no files
  if (currentMode === "reviewer") {
    const files = document.querySelectorAll("#file-list li");
    if (files.length === 0) {
      appendMessage("user", message);
      appendMessage("assistant", "**No files to review.** Write or generate some code first (switch to Builder mode), then come back to Reviewer mode to critique it.");
      chatInput.value = "";
      return;
    }
  }

  appendMessage("user", message);
  chatInput.value = "";
  setProcessing(true);

  try {
    const res = await fetch(`${API}/api/sessions/${currentSessionId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, mode: currentMode }),
    });

    if (!res.ok) {
      const err = await res.json();
      const status = res.status;
      let msg = err.detail || "Something went wrong.";
      if (status === 429) msg = "Rate limited — the model is busy. Wait a moment and try again.";
      else if (status === 401) msg = "Invalid API key. Check your `.env` file.";
      else if (status === 502) msg = `LLM error: ${err.detail}`;
      appendMessage("assistant", `**Error ${status}:** ${msg}`);
      return;
    }

    const data = await res.json();

    // Show tool events
    if (data.events) {
      for (const event of data.events) {
        if (event.type === "tool_result") {
          appendToolEvent(event);
        }
      }
    }

    // Show answer
    appendMessage("assistant", data.answer);

    // Refresh files
    if (data.files) {
      renderFiles(data.files);
    }

    await refreshSessionList();
  } catch (err) {
    appendMessage("assistant", `Connection error: ${err.message}`);
  } finally {
    setProcessing(false);
  }
});

// Ctrl+Enter to send
chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    chatForm.dispatchEvent(new Event("submit"));
  }
});

function setProcessing(on) {
  isProcessing = on;
  sendBtn.disabled = on;
  if (on) {
    appendThinking();
  } else {
    removeThinking();
  }
}

function appendMessage(role, content) {
  const div = document.createElement("div");
  div.className = `message ${role}`;

  const bodyHtml = role === "assistant"
    ? marked.parse(content)
    : escapeHtml(content);

  div.innerHTML = `
    <div class="message-role">${role === "user" ? "You" : "c0der"}</div>
    <div class="message-body markdown-body">${bodyHtml}</div>
  `;
  messagesDiv.appendChild(div);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function appendToolEvent(event) {
  const div = document.createElement("div");
  div.className = "tool-event";

  const paramsStr = Object.entries(event.params || {})
    .map(([k, v]) => {
      const val = typeof v === "string" && v.length > 80
        ? v.substring(0, 80) + "..."
        : v;
      return `${k}: ${val}`;
    })
    .join(", ");

  const resultPreview = (event.result || "").length > 300
    ? event.result.substring(0, 300) + "..."
    : event.result;

  div.innerHTML = `
    <span class="tool-name">${escapeHtml(event.tool)}</span>(${escapeHtml(paramsStr)})
    <div class="tool-result">${escapeHtml(resultPreview)}</div>
  `;
  messagesDiv.appendChild(div);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function appendThinking() {
  const div = document.createElement("div");
  div.className = "thinking";
  div.id = "thinking-indicator";
  div.innerHTML = `<div class="spinner"></div> c0der is working...`;
  messagesDiv.appendChild(div);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

function removeThinking() {
  const el = document.getElementById("thinking-indicator");
  if (el) el.remove();
}

// --- Files ---

async function refreshFiles() {
  if (!currentSessionId) return;
  const res = await fetch(`${API}/api/sessions/${currentSessionId}/files`);
  const files = await res.json();
  renderFiles(files);
}

function renderFiles(files) {
  fileList.innerHTML = "";
  files.forEach((f) => {
    const li = document.createElement("li");
    li.textContent = f;
    li.addEventListener("click", () => viewFile(f));
    fileList.appendChild(li);
  });
}

async function viewFile(path) {
  if (!currentSessionId) return;
  const res = await fetch(
    `${API}/api/sessions/${currentSessionId}/files/${encodeURIComponent(path)}`
  );
  if (!res.ok) return;
  const data = await res.json();
  codeFilename.textContent = data.path;
  codeEditor.value = data.content;
  codeEditor.disabled = false;
  currentFilePath = data.path;
  runBtn.disabled = !path.endsWith(".py");
  runOutput.classList.add("hidden");

  document.querySelectorAll("#file-list li").forEach((li) => {
    li.classList.toggle("active", li.textContent === path);
  });
}

// --- Utilities ---

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// --- Collapse / Expand ---

const sidebar = document.getElementById("sidebar");
const rightPanel = document.getElementById("right-panel");
const collapseSidebarBtn = document.getElementById("collapse-sidebar");
const expandSidebarBtn = document.getElementById("expand-sidebar");
const collapseRightBtn = document.getElementById("collapse-right");
const expandRightBtn = document.getElementById("expand-right");
const resizeLeft = document.getElementById("resize-left");
const resizeRight = document.getElementById("resize-right");

let sidebarWidth = 240;
let rightPanelWidth = 380;

collapseSidebarBtn.addEventListener("click", () => {
  sidebarWidth = sidebar.offsetWidth;
  sidebar.classList.add("collapsed");
  resizeLeft.classList.add("hidden-handle");
  expandSidebarBtn.classList.remove("hidden");
});

expandSidebarBtn.addEventListener("click", () => {
  sidebar.classList.remove("collapsed");
  sidebar.style.width = sidebarWidth + "px";
  resizeLeft.classList.remove("hidden-handle");
  expandSidebarBtn.classList.add("hidden");
});

collapseRightBtn.addEventListener("click", () => {
  rightPanelWidth = rightPanel.offsetWidth;
  rightPanel.classList.add("collapsed");
  resizeRight.classList.add("hidden-handle");
  expandRightBtn.classList.remove("hidden");
});

expandRightBtn.addEventListener("click", () => {
  rightPanel.classList.remove("collapsed");
  rightPanel.style.width = rightPanelWidth + "px";
  resizeRight.classList.remove("hidden-handle");
  expandRightBtn.classList.add("hidden");
});

// --- Drag-to-resize ---

function initResize(handle, getTarget, side) {
  let startX, startWidth, target;

  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    target = getTarget();
    startX = e.clientX;
    startWidth = target.offsetWidth;
    handle.classList.add("active");
    document.body.classList.add("resizing");
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
  });

  function onMouseMove(e) {
    const diff = e.clientX - startX;
    // "left" panel: dragging right = wider. "right" panel: dragging left = wider.
    const newWidth = side === "left"
      ? Math.max(140, startWidth + diff)
      : Math.max(140, startWidth - diff);
    target.style.width = newWidth + "px";
  }

  function onMouseUp() {
    handle.classList.remove("active");
    document.body.classList.remove("resizing");
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", onMouseUp);
  }
}

initResize(resizeLeft, () => sidebar, "left");
initResize(resizeRight, () => rightPanel, "right");


// --- Clear button ---

clearBtn.addEventListener("click", async () => {
  if (!currentSessionId || isProcessing) return;
  if (!confirm("Clear this session's chat history? Workspace files will be kept.")) return;
  await fetch(`${API}/api/sessions/${currentSessionId}/history`, { method: "DELETE" });
  messagesDiv.innerHTML = "";
});

// --- Run button (in-browser editor) ---

runBtn.addEventListener("click", async () => {
  if (!currentSessionId || !currentFilePath) return;
  runBtn.disabled = true;
  runBtn.textContent = "Running...";
  runOutput.classList.remove("hidden");
  runOutputContent.textContent = "Executing...";

  try {
    const res = await fetch(`${API}/api/sessions/${currentSessionId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: currentFilePath, content: codeEditor.value }),
    });
    const data = await res.json();
    runOutputContent.textContent = data.output || "(no output)";
  } catch (err) {
    runOutputContent.textContent = `Error: ${err.message}`;
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = "Run";
  }
});

// Tab key inserts a tab in the editor instead of changing focus
codeEditor.addEventListener("keydown", (e) => {
  if (e.key === "Tab") {
    e.preventDefault();
    const start = codeEditor.selectionStart;
    const end = codeEditor.selectionEnd;
    codeEditor.value = codeEditor.value.substring(0, start) + "    " + codeEditor.value.substring(end);
    codeEditor.selectionStart = codeEditor.selectionEnd = start + 4;
  }
});

// --- Init ---

newSessionBtn.addEventListener("click", createSession);
createSession();
