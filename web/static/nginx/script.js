// ============================================================================
// modules/nginx/static/script.js
// Logique du module Nginx : bascule de mode, backends dynamiques, presets,
// generation via /nginx/api/generate, copier/telecharger.
// ============================================================================

const CONFIG = window.OPSFORGE_NGINX || { modes: [], algorithms: [], presets: [] };

const state = {
  mode: "static",
  backends: [
    { host: "127.0.0.1", port: 3001, weight: "" },
    { host: "127.0.0.1", port: 3002, weight: "" },
  ],
  lastConfig: "",
  lastFilename: "app",
};

const el = {
  presetList: document.getElementById("preset-list"),
  modeSwitch: document.getElementById("mode-switch"),
  serverNameInput: document.getElementById("server-name-input"),

  fieldsStatic: document.getElementById("fields-static"),
  rootInput: document.getElementById("root-input"),
  indexInput: document.getElementById("index-input"),
  spaCheckbox: document.getElementById("spa-checkbox"),

  fieldsReverseProxy: document.getElementById("fields-reverse-proxy"),
  backendHostInput: document.getElementById("backend-host-input"),
  backendPortInput: document.getElementById("backend-port-input"),

  fieldsLoadBalancer: document.getElementById("fields-load-balancer"),
  upstreamNameInput: document.getElementById("upstream-name-input"),
  algorithmSelect: document.getElementById("algorithm-select"),
  backendsList: document.getElementById("backends-list"),
  addBackendBtn: document.getElementById("add-backend-btn"),

  websocketGroup: document.getElementById("websocket-group"),
  websocketCheckbox: document.getElementById("websocket-checkbox"),

  listenPortInput: document.getElementById("listen-port-input"),
  bodySizeInput: document.getElementById("body-size-input"),
  httpsCheckbox: document.getElementById("https-checkbox"),
  gzipCheckbox: document.getElementById("gzip-checkbox"),
  securityHeadersCheckbox: document.getElementById("security-headers-checkbox"),

  generateBtn: document.getElementById("generate-btn"),
  resetBtn: document.getElementById("reset-btn"),
  errorMsg: document.getElementById("error-msg"),

  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),

  reloadNode: document.querySelector('.node[data-stage="reload"]'),

  tbMode: document.getElementById("tb-mode"),
  tbDomain: document.getElementById("tb-domain"),
  tbPort: document.getElementById("tb-port"),
};

const MODE_LABELS = {
  static: "Statique",
  reverse_proxy: "Reverse proxy",
  load_balancer: "Load balancer",
};

// ----------------------------------------------------------------------------
// Presets
// ----------------------------------------------------------------------------
function renderPresetList() {
  el.presetList.innerHTML = "";
  CONFIG.presets.forEach((name) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "preset-chip";
    chip.textContent = name;
    chip.addEventListener("click", () => applyPreset(name, chip));
    el.presetList.appendChild(chip);
  });
}

async function applyPreset(name, chipEl) {
  clearError();
  try {
    const res = await fetch(`/nginx/api/preset/${encodeURIComponent(name)}`);
    const data = await res.json();
    if (!res.ok) {
      showError(data.error || "Preset introuvable.");
      return;
    }
    fillFormFromConfig(data);
    document.querySelectorAll(".preset-chip").forEach((c) => c.classList.remove("active"));
    if (chipEl) chipEl.classList.add("active");
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  }
}

function fillFormFromConfig(cfg) {
  setMode(cfg.mode || "static");
  el.serverNameInput.value = cfg.server_name || "";
  el.rootInput.value = cfg.root || "";
  el.indexInput.value = cfg.index_file || "";
  el.spaCheckbox.checked = !!cfg.spa;
  el.backendHostInput.value = cfg.backend_host || "";
  el.backendPortInput.value = cfg.backend_port || "";
  el.upstreamNameInput.value = cfg.upstream_name || "";
  el.algorithmSelect.value = cfg.lb_algorithm || "round_robin";
  el.websocketCheckbox.checked = !!cfg.websocket;
  el.listenPortInput.value = cfg.listen_port || 80;
  el.bodySizeInput.value = cfg.client_max_body_size || "1m";
  el.httpsCheckbox.checked = !!cfg.https;
  el.gzipCheckbox.checked = !!cfg.gzip;
  el.securityHeadersCheckbox.checked = !!cfg.security_headers;

  if (cfg.mode === "load_balancer" && Array.isArray(cfg.backends)) {
    state.backends = cfg.backends.map((b) => ({
      host: b.host || "",
      port: b.port || "",
      weight: b.weight || "",
    }));
    renderBackendsList();
  }

  updateTitleBlock();
}

// ----------------------------------------------------------------------------
// Bascule de mode
// ----------------------------------------------------------------------------
function setMode(mode) {
  state.mode = mode;
  el.modeSwitch.querySelectorAll(".provider-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });

  el.fieldsStatic.hidden = mode !== "static";
  el.fieldsReverseProxy.hidden = mode !== "reverse_proxy";
  el.fieldsLoadBalancer.hidden = mode !== "load_balancer";
  el.websocketGroup.hidden = mode === "static";

  updateTitleBlock();
}

el.modeSwitch.querySelectorAll(".provider-btn").forEach((btn) => {
  btn.addEventListener("click", () => setMode(btn.dataset.mode));
});

// ----------------------------------------------------------------------------
// Backends (mode load balancer)
// ----------------------------------------------------------------------------
function renderBackendsList() {
  el.backendsList.innerHTML = "";
  state.backends.forEach((backend, index) => {
    const row = document.createElement("div");
    row.className = "backend-row";

    const hostInput = document.createElement("input");
    hostInput.type = "text";
    hostInput.placeholder = "hôte (ex : 127.0.0.1)";
    hostInput.value = backend.host || "";
    hostInput.addEventListener("input", () => (state.backends[index].host = hostInput.value));

    const portInput = document.createElement("input");
    portInput.type = "number";
    portInput.placeholder = "port";
    portInput.value = backend.port || "";
    portInput.addEventListener("input", () => (state.backends[index].port = portInput.value));

    const weightInput = document.createElement("input");
    weightInput.type = "number";
    weightInput.placeholder = "poids";
    weightInput.className = "weight-input";
    weightInput.value = backend.weight || "";
    weightInput.addEventListener("input", () => (state.backends[index].weight = weightInput.value));

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "backend-remove";
    removeBtn.innerHTML = "&times;";
    removeBtn.title = "Retirer ce backend";
    removeBtn.addEventListener("click", () => {
      state.backends.splice(index, 1);
      renderBackendsList();
    });

    row.appendChild(hostInput);
    row.appendChild(portInput);
    row.appendChild(weightInput);
    row.appendChild(removeBtn);
    el.backendsList.appendChild(row);
  });
}

el.addBackendBtn.addEventListener("click", () => {
  state.backends.push({ host: "127.0.0.1", port: "", weight: "" });
  renderBackendsList();
});

// ----------------------------------------------------------------------------
// Construction du payload + generation
// ----------------------------------------------------------------------------
function buildPayload() {
  const payload = {
    mode: state.mode,
    server_name: el.serverNameInput.value.trim(),
    listen_port: parseInt(el.listenPortInput.value, 10) || 80,
    client_max_body_size: el.bodySizeInput.value.trim() || "1m",
    https: el.httpsCheckbox.checked,
    gzip: el.gzipCheckbox.checked,
    security_headers: el.securityHeadersCheckbox.checked,
  };

  if (state.mode === "static") {
    payload.root = el.rootInput.value.trim();
    payload.index_file = el.indexInput.value.trim() || "index.html";
    payload.spa = el.spaCheckbox.checked;
  } else if (state.mode === "reverse_proxy") {
    payload.backend_host = el.backendHostInput.value.trim();
    payload.backend_port = parseInt(el.backendPortInput.value, 10) || null;
    payload.websocket = el.websocketCheckbox.checked;
  } else if (state.mode === "load_balancer") {
    payload.upstream_name = el.upstreamNameInput.value.trim() || "backend_pool";
    payload.lb_algorithm = el.algorithmSelect.value;
    payload.websocket = el.websocketCheckbox.checked;
    payload.backends = state.backends
      .filter((b) => (b.host || "").trim())
      .map((b) => {
        const backend = { host: b.host.trim(), port: parseInt(b.port, 10) || null };
        if (b.weight) backend.weight = parseInt(b.weight, 10);
        return backend;
      });
  }

  return payload;
}

async function handleGenerate() {
  clearError();

  if (!el.serverNameInput.value.trim()) {
    showError("Le nom de domaine est requis.");
    return;
  }

  const payload = buildPayload();

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "…";

  try {
    const res = await fetch("/nginx/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Erreur lors de la génération.");
      return;
    }

    renderResult(data.config);
    state.lastFilename = data.filename || "app";
    updateTitleBlock();
    flashSuccess();
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  } finally {
    el.generateBtn.disabled = false;
    el.generateBtn.textContent = "GÉNÉRER →";
  }
}

function flashSuccess() {
  el.generateBtn.textContent = "✓ Généré";
  if (el.reloadNode) el.reloadNode.classList.add("active");
  setTimeout(() => {
    el.generateBtn.textContent = "GÉNÉRER →";
  }, 1200);
}

// ----------------------------------------------------------------------------
// Rendu resultat
// ----------------------------------------------------------------------------
function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlightConfig(text) {
  const escaped = escapeHtml(text);
  const lines = escaped.split("\n");

  const highlighted = lines.map((line) => {
    if (/^\s*#/.test(line)) {
      return `<span class="yaml-comment">${line}</span>`;
    }
    const directiveMatch = line.match(
      /^(\s*)(server|upstream|listen|server_name|location|proxy_pass|proxy_set_header|proxy_http_version|root|index|return|client_max_body_size|ssl_certificate|ssl_certificate_key|ssl_protocols|ssl_ciphers|ssl_prefer_server_ciphers|gzip|gzip_vary|gzip_min_length|gzip_comp_level|gzip_types|add_header|least_conn|ip_hash|try_files)(\s|$|\{)/
    );
    if (directiveMatch) {
      return `${directiveMatch[1]}<span class="yaml-key">${directiveMatch[2]}</span>${line.slice(
        directiveMatch[1].length + directiveMatch[2].length
      )}`;
    }
    return line;
  });

  return highlighted.join("\n");
}

function renderResult(configText) {
  state.lastConfig = configText;
  el.resultBox.innerHTML = "";
  const pre = document.createElement("pre");
  pre.innerHTML = highlightConfig(configText);
  el.resultBox.appendChild(pre);
  el.resultActions.hidden = false;
}

function resetResultBox(message) {
  el.resultBox.innerHTML = "";
  const p = document.createElement("p");
  p.className = "result-placeholder";
  p.textContent = message || "Le fichier généré apparaîtra ici.";
  el.resultBox.appendChild(p);
  el.resultActions.hidden = true;
  state.lastConfig = "";
  if (el.reloadNode) el.reloadNode.classList.remove("active");
}

function updateTitleBlock() {
  el.tbMode.textContent = MODE_LABELS[state.mode] || "—";
  el.tbDomain.textContent = el.serverNameInput.value.trim() || "—";
  el.tbPort.textContent = el.listenPortInput.value || "80";
}

// ----------------------------------------------------------------------------
// Actions resultat : copier / telecharger
// ----------------------------------------------------------------------------
async function handleCopy() {
  if (!state.lastConfig) return;
  try {
    await navigator.clipboard.writeText(state.lastConfig);
    el.copyBtn.textContent = "Copié !";
    setTimeout(() => (el.copyBtn.textContent = "Copier"), 1500);
  } catch (err) {
    showError("Impossible de copier automatiquement, sélectionne le texte manuellement.");
  }
}

function handleDownload() {
  if (!state.lastConfig) return;
  const blob = new Blob([state.lastConfig], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${state.lastFilename}.conf`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ----------------------------------------------------------------------------
// Reset
// ----------------------------------------------------------------------------
function handleReset() {
  setMode("static");
  el.serverNameInput.value = "";
  el.rootInput.value = "";
  el.indexInput.value = "";
  el.spaCheckbox.checked = false;
  el.backendHostInput.value = "";
  el.backendPortInput.value = "";
  el.upstreamNameInput.value = "";
  el.algorithmSelect.value = "round_robin";
  el.websocketCheckbox.checked = false;
  el.listenPortInput.value = 80;
  el.bodySizeInput.value = "1m";
  el.httpsCheckbox.checked = false;
  el.gzipCheckbox.checked = false;
  el.securityHeadersCheckbox.checked = false;

  state.backends = [
    { host: "127.0.0.1", port: 3001, weight: "" },
    { host: "127.0.0.1", port: 3002, weight: "" },
  ];
  renderBackendsList();

  document.querySelectorAll(".preset-chip").forEach((c) => c.classList.remove("active"));
  resetResultBox();
  clearError();
  updateTitleBlock();
}

// ----------------------------------------------------------------------------
// Utilitaires
// ----------------------------------------------------------------------------
function showError(message) {
  el.errorMsg.textContent = message;
  el.errorMsg.classList.add("visible");
}

function clearError() {
  el.errorMsg.textContent = "";
  el.errorMsg.classList.remove("visible");
}

// ----------------------------------------------------------------------------
// Evenements + init
// ----------------------------------------------------------------------------
el.generateBtn.addEventListener("click", handleGenerate);
el.resetBtn.addEventListener("click", handleReset);
el.copyBtn.addEventListener("click", handleCopy);
el.downloadBtn.addEventListener("click", handleDownload);
el.serverNameInput.addEventListener("input", updateTitleBlock);
el.listenPortInput.addEventListener("input", updateTitleBlock);

renderPresetList();
renderBackendsList();
setMode("static");
