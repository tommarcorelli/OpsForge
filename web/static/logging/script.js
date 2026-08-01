// ============================================================================
// modules/logging/static/script.js
// Logique du module logging : presets, switch fluent-bit/vector, builder de
// sources, destination, generation via /logging/api/generate, copier/telecharger.
// ============================================================================

const CONFIG = window.OPSFORGE_LOGGING || { backends: [], presets: [] };

const state = {
  backend: "fluent-bit",
  preset: "docker-loki",
  sources: [],
  destination: { type: "loki", host: "localhost", port: 3100, index: "", path: "" },
  lastFilename: null,
  lastContent: null,
};

const el = {
  presetList: document.getElementById("preset-list"),
  backendSwitch: document.getElementById("backend-switch"),

  sourcesList: document.getElementById("sources-list"),
  addSourceBtn: document.getElementById("add-source-btn"),

  destType: document.getElementById("dest-type"),
  destHost: document.getElementById("dest-host"),
  destPort: document.getElementById("dest-port"),
  destIndex: document.getElementById("dest-index"),
  destPath: document.getElementById("dest-path"),
  destHostGroup: document.getElementById("dest-host-group"),
  destPortGroup: document.getElementById("dest-port-group"),
  destIndexGroup: document.getElementById("dest-index-group"),
  destPathGroup: document.getElementById("dest-path-group"),

  generateBtn: document.getElementById("generate-btn"),
  resetBtn: document.getElementById("reset-btn"),
  errorMsg: document.getElementById("error-msg"),

  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),

  applyNode: document.querySelector('.node[data-stage="apply"]'),
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
    if (name === state.preset) chip.classList.add("active");
    chip.addEventListener("click", () => applyPreset(name, chip));
    el.presetList.appendChild(chip);
  });
}

async function applyPreset(name, chipEl) {
  clearError();
  try {
    const res = await fetch(`/logging/api/preset/${encodeURIComponent(name)}`);
    const data = await res.json();
    if (!res.ok) {
      showError(data.error || "Preset introuvable.");
      return;
    }
    state.preset = name;
    setBackend(data.backend || "fluent-bit");
    state.sources = (data.sources || []).map((s) => ({ ...s }));
    state.destination = data.destination || state.destination;
    renderSourcesList();
    renderDestination();

    document.querySelectorAll(".preset-chip").forEach((c) => c.classList.remove("active"));
    if (chipEl) chipEl.classList.add("active");
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  }
}

// ----------------------------------------------------------------------------
// Backend (fluent-bit / vector)
// ----------------------------------------------------------------------------
function setBackend(backend) {
  state.backend = backend;
  el.backendSwitch.querySelectorAll(".provider-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.backend === backend);
  });
}

el.backendSwitch.querySelectorAll(".provider-btn").forEach((btn) => {
  btn.addEventListener("click", () => setBackend(btn.dataset.backend));
});

// ----------------------------------------------------------------------------
// Builder de sources (type / path-ou-port / tag)
// ----------------------------------------------------------------------------
function renderSourcesList() {
  el.sourcesList.innerHTML = "";
  state.sources.forEach((src, index) => {
    const row = document.createElement("div");
    row.className = "source-row";

    const typeSelect = document.createElement("select");
    ["tail", "docker", "syslog"].forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      typeSelect.appendChild(opt);
    });
    typeSelect.value = src.type || "tail";
    typeSelect.addEventListener("change", () => {
      state.sources[index].type = typeSelect.value;
      renderSourcesList();
    });

    const detailInput = document.createElement("input");
    detailInput.type = "text";
    if (src.type === "syslog") {
      detailInput.placeholder = "port (ex: 5140)";
      detailInput.value = src.port != null ? src.port : "";
      detailInput.addEventListener("input", () => (state.sources[index].port = detailInput.value.trim()));
    } else if (src.type === "docker") {
      detailInput.placeholder = "(auto : /var/lib/docker/containers/*)";
      detailInput.disabled = true;
    } else {
      detailInput.placeholder = "chemin (ex: /var/log/nginx/*.log)";
      detailInput.value = src.path || "";
      detailInput.addEventListener("input", () => (state.sources[index].path = detailInput.value.trim()));
    }

    const tagInput = document.createElement("input");
    tagInput.type = "text";
    tagInput.placeholder = "tag";
    tagInput.value = src.tag || "";
    tagInput.addEventListener("input", () => (state.sources[index].tag = tagInput.value.trim()));

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "source-remove";
    removeBtn.innerHTML = "&times;";
    removeBtn.title = "Retirer cette source";
    removeBtn.addEventListener("click", () => {
      state.sources.splice(index, 1);
      renderSourcesList();
    });

    row.appendChild(typeSelect);
    row.appendChild(detailInput);
    row.appendChild(tagInput);
    row.appendChild(removeBtn);
    el.sourcesList.appendChild(row);
  });
}

el.addSourceBtn.addEventListener("click", () => {
  state.sources.push({ type: "tail", path: "", tag: "" });
  renderSourcesList();
});

// ----------------------------------------------------------------------------
// Destination
// ----------------------------------------------------------------------------
function renderDestination() {
  const d = state.destination || {};
  el.destType.value = d.type || "loki";
  el.destHost.value = d.host || "";
  el.destPort.value = d.port || "";
  el.destIndex.value = d.index || "";
  el.destPath.value = d.path || "";
  updateDestFieldsVisibility();
}

function updateDestFieldsVisibility() {
  const type = el.destType.value;
  el.destHostGroup.hidden = !(type === "loki" || type === "elasticsearch");
  el.destPortGroup.hidden = !(type === "loki" || type === "elasticsearch");
  el.destIndexGroup.hidden = type !== "elasticsearch";
  el.destPathGroup.hidden = type !== "file";
}

el.destType.addEventListener("change", updateDestFieldsVisibility);

function buildDestinationPayload() {
  const type = el.destType.value;
  const dest = { type };
  if (type === "loki" || type === "elasticsearch") {
    dest.host = el.destHost.value.trim();
    dest.port = parseInt(el.destPort.value, 10);
  }
  if (type === "elasticsearch") {
    dest.index = el.destIndex.value.trim();
  }
  if (type === "file") {
    dest.path = el.destPath.value.trim();
  }
  return dest;
}

// ----------------------------------------------------------------------------
// Generation
// ----------------------------------------------------------------------------
function buildPayload() {
  return {
    preset: "custom",
    backend: state.backend,
    sources: state.sources.map((s) => ({
      type: s.type,
      path: s.path,
      port: s.port ? parseInt(s.port, 10) : undefined,
      tag: s.tag || s.type,
    })),
    destination: buildDestinationPayload(),
  };
}

async function handleGenerate() {
  clearError();

  if (!state.sources.length) {
    showError("Ajoute au moins une source (ou choisis un preset).");
    return;
  }

  const payload = buildPayload();

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "…";

  try {
    const res = await fetch("/logging/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Erreur lors de la génération.");
      return;
    }

    const file = data.files[0];
    state.lastFilename = file.filename;
    state.lastContent = file.content;
    renderResult();
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
  if (el.applyNode) el.applyNode.classList.add("active");
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

function highlightContent(text) {
  const escaped = escapeHtml(text);
  return escaped
    .split("\n")
    .map((line) => {
      if (/^\s*#/.test(line)) return `<span class="yaml-comment">${line}</span>`;
      if (/^\s*\[.+\]\s*$/.test(line)) return `<span class="yaml-section">${line}</span>`;
      return line;
    })
    .join("\n");
}

function renderResult() {
  el.resultBox.innerHTML = "";
  if (!state.lastContent) return;
  const pre = document.createElement("pre");
  pre.innerHTML = highlightContent(state.lastContent);
  el.resultBox.appendChild(pre);
  el.resultActions.hidden = false;
}

function resetResultBox() {
  el.resultBox.innerHTML = "";
  const p = document.createElement("p");
  p.className = "result-placeholder";
  p.textContent = "Le fichier généré apparaîtra ici.";
  el.resultBox.appendChild(p);
  el.resultActions.hidden = true;
  state.lastFilename = null;
  state.lastContent = null;
  if (el.applyNode) el.applyNode.classList.remove("active");
}

// ----------------------------------------------------------------------------
// Actions resultat : copier / telecharger
// ----------------------------------------------------------------------------
async function handleCopy() {
  if (!state.lastContent) return;
  try {
    await navigator.clipboard.writeText(state.lastContent);
    el.copyBtn.textContent = "Copié !";
    setTimeout(() => (el.copyBtn.textContent = "Copier"), 1500);
  } catch (err) {
    showError("Impossible de copier automatiquement, sélectionne le texte manuellement.");
  }
}

function handleDownload() {
  if (!state.lastContent) return;
  const blob = new Blob([state.lastContent], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = state.lastFilename || "logging-config.conf";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ----------------------------------------------------------------------------
// Reset
// ----------------------------------------------------------------------------
function handleReset() {
  setBackend("fluent-bit");
  state.preset = "docker-loki";
  state.sources = [];
  document.querySelectorAll(".preset-chip").forEach((c) => c.classList.remove("active"));
  resetResultBox();
  clearError();
  applyPreset("docker-loki");
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

renderPresetList();
setBackend("fluent-bit");
applyPreset("docker-loki");
