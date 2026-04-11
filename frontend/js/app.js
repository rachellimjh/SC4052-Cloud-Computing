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
const fileList = document.getElementById("file-list");
const codeFilename = document.getElementById("code-filename");
const codeContent = document.getElementById("code-content").querySelector("code");

// --- Sessions ---

async function createSession() {
  const res = await fetch(`${API}/api/sessions`, { method: "POST" });
  const session = await res.json();
  currentSessionId = session.id;
  messagesDiv.innerHTML = "";
  fileList.innerHTML = "";
  codeFilename.textContent = "Select a file";
  codeContent.textContent = "No file selected";
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

  appendMessage("user", message);
  chatInput.value = "";
  setProcessing(true);

  try {
    const res = await fetch(`${API}/api/sessions/${currentSessionId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    if (!res.ok) {
      const err = await res.json();
      appendMessage("assistant", `Error: ${err.detail || "Something went wrong"}`);
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
  div.innerHTML = `
    <div class="message-role">${role === "user" ? "You" : "c0der"}</div>
    <div class="message-body">${escapeHtml(content)}</div>
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
  codeContent.textContent = data.content;

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

// --- Init ---

newSessionBtn.addEventListener("click", createSession);
createSession();
