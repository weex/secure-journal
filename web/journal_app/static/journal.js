const gate = document.querySelector("#gate");
const app = document.querySelector("#app");
const list = document.querySelector("#list");
const writer = document.querySelector("#writer");
const empty = document.querySelector("#empty");
const titleInput = document.querySelector("#title");
const saveState = document.querySelector("#save-state");
const loginError = document.querySelector("#login-error");

let current = null;
let mounted = null;
let timer = 0;
let dirty = false;

document.querySelector("#login").addEventListener("submit", async (event) => {
  event.preventDefault();
  loginError.textContent = "";
  const response = await fetch("/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password: document.querySelector("#login-password").value }),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    loginError.textContent = body.detail || "Could not sign in.";
    return;
  }
  document.querySelector("#login-password").value = "";
  await openApp();
});

document.querySelector("#logout").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  current = null;
  showGate();
});

document.querySelector("#create").addEventListener("click", async () => {
  const response = await fetch("/api/entries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: "Untitled",
      doc: { type: "doc", content: [{ type: "paragraph" }] },
    }),
  });
  if (response.status === 401) return showGate();
  const body = await response.json();
  await refreshList();
  await openEntry(body.id);
});

document.querySelector("#search").addEventListener("input", () => {
  window.clearTimeout(timer);
  timer = window.setTimeout(() => refreshList(), 250);
});

document.querySelector("#delete").addEventListener("click", async () => {
  if (!current) return;
  if (!window.confirm("Delete this entry?")) return;
  const response = await fetch(`/api/entries/${current.id}`, { method: "DELETE" });
  if (response.status === 401) return showGate();
  current = null;
  writer.hidden = true;
  empty.hidden = false;
  await refreshList();
});

titleInput.addEventListener("input", scheduleSave);

document.querySelector(".toolbar").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-cmd]");
  if (!button || !mounted) return;
  const chain = mounted.chain().focus();
  const cmd = button.dataset.cmd;
  if (cmd === "bold") chain.toggleBold().run();
  if (cmd === "italic") chain.toggleItalic().run();
  if (cmd === "heading") chain.toggleHeading({ level: 2 }).run();
  if (cmd === "bullet") chain.toggleBulletList().run();
  if (cmd === "ordered") chain.toggleOrderedList().run();
  if (cmd === "quote") chain.toggleBlockquote().run();
  paintToolbar();
});

function showGate() {
  gate.hidden = false;
  app.classList.remove("open");
}

function showApp() {
  gate.hidden = true;
  app.classList.add("open");
}

async function openApp() {
  const response = await fetch("/api/session");
  if (!response.ok) return showGate();
  showApp();
  await refreshList();
}

async function refreshList() {
  const query = document.querySelector("#search").value.trim();
  const response = await fetch(`/api/entries?q=${encodeURIComponent(query)}`);
  if (response.status === 401) return showGate();
  const body = await response.json();
  list.replaceChildren();
  body.entries.forEach((entry) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "entry-button";
    if (current && current.id === entry.id) button.setAttribute("aria-current", "true");
    const name = document.createElement("span");
    name.textContent = entry.title;
    const when = document.createElement("small");
    when.textContent = formatWhen(entry.updated_at);
    button.append(name, when);
    if (entry.snippet) {
      const snip = document.createElement("small");
      snip.textContent = entry.snippet;
      button.append(snip);
    }
    button.addEventListener("click", () => openEntry(entry.id));
    list.appendChild(button);
  });
}

async function openEntry(id) {
  const response = await fetch(`/api/entries/${id}`);
  if (response.status === 401) return showGate();
  if (!response.ok) return;
  current = await response.json();
  empty.hidden = true;
  writer.hidden = false;
  titleInput.value = current.title;
  if (!mounted) {
    mounted = window.JournalEditor.mount(document.querySelector("#editor"), {
      content: current.doc,
      placeholder: "Start writing…",
      onChange: () => {
        dirty = true;
        scheduleSave();
        paintToolbar();
      },
    });
  } else {
    mounted.setContent(current.doc);
  }
  dirty = false;
  saveState.textContent = "Saved";
  await refreshList();
  paintToolbar();
}

function scheduleSave() {
  if (!current) return;
  dirty = true;
  saveState.textContent = "Saving…";
  window.clearTimeout(scheduleSave.timer);
  scheduleSave.timer = window.setTimeout(save, 800);
}

async function save() {
  if (!current || !mounted) return;
  const response = await fetch(`/api/entries/${current.id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: titleInput.value, doc: mounted.getJSON() }),
  });
  if (response.status === 401) return showGate();
  if (!response.ok) {
    saveState.textContent = "Could not save";
    return;
  }
  current = await response.json();
  dirty = false;
  saveState.textContent = "Saved";
  refreshList();
}

function paintToolbar() {
  if (!mounted) return;
  const states = {
    bold: mounted.isActive("bold"),
    italic: mounted.isActive("italic"),
    heading: mounted.isActive("heading", { level: 2 }),
    bullet: mounted.isActive("bulletList"),
    ordered: mounted.isActive("orderedList"),
    quote: mounted.isActive("blockquote"),
  };
  document.querySelectorAll(".toolbar button[data-cmd]").forEach((button) => {
    button.setAttribute("aria-pressed", states[button.dataset.cmd] ? "true" : "false");
  });
}

function formatWhen(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

openApp();
