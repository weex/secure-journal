const countries = [
  ["US", "United States"],
  ["CA", "Canada"],
  ["GB", "United Kingdom"],
  ["IE", "Ireland"],
  ["AU", "Australia"],
  ["NZ", "New Zealand"],
  ["DE", "Germany"],
  ["FR", "France"],
  ["NL", "Netherlands"],
  ["BE", "Belgium"],
  ["SE", "Sweden"],
  ["NO", "Norway"],
  ["DK", "Denmark"],
  ["FI", "Finland"],
  ["ES", "Spain"],
  ["IT", "Italy"],
  ["PT", "Portugal"],
  ["CH", "Switzerland"],
  ["AT", "Austria"],
  ["PL", "Poland"],
  ["JP", "Japan"],
  ["KR", "South Korea"],
  ["SG", "Singapore"],
  ["IN", "India"],
  ["BR", "Brazil"],
  ["MX", "Mexico"],
  ["ZA", "South Africa"],
];

const letters = ["qwertyuiop", "asdfghjkl", "zxcvbnm"];
const symbols = ["1234567890", "@#$%&*-_+=", ".,!?/\\()'"];

const countrySelect = document.querySelector("#country");
const scanButton = document.querySelector("#scan");
const networks = document.querySelector("#networks");
const wifiPassword = document.querySelector("#wifi-password");
const wifiSecret = document.querySelector("#wifi-secret");
const joinButton = document.querySelector("#join");
const ethernetButton = document.querySelector("#use-ethernet");
const wifiStep = document.querySelector("#wifi-step");
const passwordStep = document.querySelector("#password-step");
const ready = document.querySelector("#ready");
const error = document.querySelector("#error");
const meter = document.querySelector("#meter");
const keyboard = document.querySelector("#keyboard");

let selected = null;
let shift = false;
let symbolMode = false;
let focused = null;

countries.forEach(([code, name]) => {
  const option = document.createElement("option");
  option.value = code;
  option.textContent = name;
  countrySelect.appendChild(option);
});

countrySelect.addEventListener("change", async () => {
  scanButton.disabled = !countrySelect.value;
  if (!countrySelect.value) return;
  await post("/api/wifi/country", { country: countrySelect.value });
});

scanButton.addEventListener("click", async () => {
  error.textContent = "";
  scanButton.disabled = true;
  const body = await get("/api/wifi/scan");
  scanButton.disabled = false;
  if (!body || !body.networks) return;
  networks.replaceChildren();
  selected = null;
  joinButton.disabled = true;
  body.networks.forEach((network) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "network";
    const name = document.createElement("span");
    name.textContent = network.ssid;
    const meta = document.createElement("span");
    meta.textContent = network.security ? `${network.signal}` : "open";
    button.append(name, meta);
    button.addEventListener("click", () => {
      selected = network;
      document.querySelectorAll(".network").forEach((item) => item.setAttribute("aria-pressed", "false"));
      button.setAttribute("aria-pressed", "true");
      joinButton.disabled = false;
      wifiSecret.classList.toggle("hidden", !network.security);
    });
    networks.appendChild(button);
  });
  if (!body.networks.length) error.textContent = "No networks found. Check the country and try again.";
});

joinButton.addEventListener("click", async () => {
  if (!selected) return;
  error.textContent = "";
  joinButton.disabled = true;
  const body = await post("/api/wifi/connect", {
    ssid: selected.ssid,
    password: selected.security ? wifiPassword.value : "",
  });
  joinButton.disabled = false;
  if (!body || !body.ok) return;
  showPassword(`Joined ${body.ssid}.`);
});

ethernetButton.addEventListener("click", () => showPassword("Using the Ethernet connection."));

document.querySelector("#finish").addEventListener("click", async () => {
  error.textContent = "";
  const body = await post("/api/setup", {
    password: document.querySelector("#password").value,
    confirmation: document.querySelector("#confirmation").value,
  });
  if (body && body.configured) showReady(body);
});

for (const input of document.querySelectorAll("input")) {
  input.addEventListener("focus", () => {
    focused = input;
  });
  input.addEventListener("input", () => {
    if (input.id === "password" || input.id === "confirmation") checkPassword();
  });
}

function showPassword(message) {
  wifiStep.classList.add("hidden");
  passwordStep.classList.remove("hidden");
  document.querySelector("#joined").textContent = message;
  document.querySelector("#title").textContent = "Choose a security password";
  document.querySelector("#lede").textContent = "At least 14 characters, with three kinds of character. This password opens the journal. It is not stored on the Pi, only a hash of it.";
  document.querySelector("#password").focus();
}

function showReady(state) {
  wifiStep.classList.add("hidden");
  passwordStep.classList.add("hidden");
  keyboard.classList.add("hidden");
  ready.classList.remove("hidden");
  document.querySelector("#title").textContent = "Ready";
  document.querySelector("#lede").textContent = "The journal is on this network.";
  document.querySelector("#url").textContent = state.url;
  document.querySelector("#ips").textContent = state.addresses.length
    ? state.addresses.join("   ")
    : "Waiting for an address";
  document.querySelector("#cert").textContent = state.cert_note;
}

async function checkPassword() {
  const body = await post("/api/password/check", {
    password: document.querySelector("#password").value,
    confirmation: document.querySelector("#confirmation").value,
  });
  if (!body) return;
  meter.textContent = body.summary || "";
}

async function get(url) {
  const response = await fetch(url);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    error.textContent = body.detail || "Something went wrong.";
    return null;
  }
  error.textContent = "";
  return body;
}

async function post(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    error.textContent = body.detail || "Something went wrong.";
    return null;
  }
  error.textContent = "";
  return body;
}

function renderKeyboard() {
  keyboard.replaceChildren();
  const rows = symbolMode ? symbols : letters;
  rows.forEach((row, index) => {
    const line = document.createElement("div");
    line.className = "keys";
    if (!symbolMode && index === 2) line.appendChild(key("Shift", "shift"));
    if (symbolMode && index === 2) line.appendChild(key("ABC", "mode"));
    for (const char of row) line.appendChild(key(shift && !symbolMode ? char.toUpperCase() : char, "char"));
    if (index === 2) line.appendChild(key("Del", "back"));
    keyboard.appendChild(line);
  });
  const bottom = document.createElement("div");
  bottom.className = "keys";
  bottom.appendChild(key(symbolMode ? "ABC" : "123", "mode"));
  bottom.appendChild(key("space", "space"));
  bottom.appendChild(key("Hide", "hide"));
  keyboard.appendChild(bottom);
}

function key(label, kind) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label === "space" ? "space" : label;
  if (kind === "space") button.classList.add("space");
  if (kind === "shift" || kind === "mode" || kind === "back" || kind === "hide") button.classList.add("wide");
  if (kind === "shift" && shift) button.classList.add("on");
  button.addEventListener("click", (event) => {
    event.preventDefault();
    if (kind === "shift") {
      shift = !shift;
      renderKeyboard();
      return;
    }
    if (kind === "mode") {
      symbolMode = !symbolMode;
      shift = false;
      renderKeyboard();
      return;
    }
    if (kind === "hide") {
      keyboard.classList.add("hidden");
      return;
    }
    if (!focused) return;
    if (kind === "back") {
      focused.value = focused.value.slice(0, -1);
    } else if (kind === "space") {
      focused.value += " ";
    } else {
      focused.value += label;
      if (shift) {
        shift = false;
        renderKeyboard();
      }
    }
    focused.dispatchEvent(new Event("input", { bubbles: true }));
    focused.focus();
  });
  return button;
}

document.addEventListener("focusin", (event) => {
  if (event.target instanceof HTMLInputElement) {
    keyboard.classList.remove("hidden");
    focused = event.target;
  }
});

renderKeyboard();

get("/api/state").then((state) => {
  if (!state) return;
  if (state.configured) showReady(state);
  ethernetButton.classList.toggle("hidden", !state.ethernet);
});
