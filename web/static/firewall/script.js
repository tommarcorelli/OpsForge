// ============================================================================
// modules/firewall/static/script.js
// Logique du module firewall : presets, switch ufw/nftables, builder de
// regles (mode custom), generation via /firewall/api/generate, onglets
// multi-fichiers, copier/telecharger.
// ============================================================================

const CONFIG = window.OPSFORGE_FIREWALL || {
  backends: [],
  presets: [],
};

const state = {
  backend: "ufw",
  preset: "web-public",
  rules: [],
  lastFiles: [],
  activeFileIndex: 0,
};

const el = {
  presetList: document.getElementById("preset-list"),
  backendSwitch: document.getElementById("backend-switch"),
  fail2banCheckbox: document.getElementById("fail2ban-checkbox"),

  customRulesGroup: document.getElementById("custom-rules-group"),
  rulesList: document.getElementById("rules-list"),
  addRuleBtn: document.getElementById("add-rule-btn"),

  generateBtn: document.getElementById("generate-btn"),
  resetBtn: document.getElementById("reset-btn"),
  errorMsg: document.getElementById("error-msg"),

  fileTabs: document.getElementById("file-tabs"),
  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),

  applyNode: document.querySelector('.node[data-stage="apply"]'),

  tbPreset: document.getElementById("tb-preset"),
  tbBackend: document.getElementById("tb-backend"),
  tbRules: document.getElementById("tb-rules"),
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
    const res = await fetch(`/firewall/api/preset/${encodeURIComponent(name)}`);
    const data = await res.json();
    if (!res.ok) {
      showError(data.error || "Preset introuvable.");
      return;
    }
    state.preset = name;
    setBackend(data.backend || "ufw");
    el.fail2banCheckbox.checked = !!data.fail2ban;
    state.rules = (data.rules || []).map((r) => ({ ...r }));
    renderRulesList();
    toggleCustomRulesVisibility();

    document.querySelectorAll(".preset-chip").forEach((c) => c.classList.remove("active"));
    if (chipEl) chipEl.classList.add("active");

    updateTitleBlock();
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  }
}

function toggleCustomRulesVisibility() {
  // Le builder de regles reste visible pour tous les presets (on peut
  // affiner les regles proposees), mais seul "custom" part d'une liste vide.
  el.customRulesGroup.hidden = false;
}

// ----------------------------------------------------------------------------
// Backend (ufw / nftables)
// ----------------------------------------------------------------------------
function setBackend(backend) {
  state.backend = backend;
  el.backendSwitch.querySelectorAll(".provider-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.backend === backend);
  });
  updateTitleBlock();
}

el.backendSwitch.querySelectorAll(".provider-btn").forEach((btn) => {
  btn.addEventListener("click", () => setBackend(btn.dataset.backend));
});

// ----------------------------------------------------------------------------
// Builder de regles (port / proto / source / action / commentaire)
// ----------------------------------------------------------------------------
function renderRulesList() {
  el.rulesList.innerHTML = "";
  state.rules.forEach((rule, index) => {
    const row = document.createElement("div");
    row.className = "rule-row";

    const portInput = document.createElement("input");
    portInput.type = "text";
    portInput.placeholder = "port (ex: 443)";
    portInput.value = rule.port != null ? rule.port : "";
    portInput.addEventListener("input", () => (state.rules[index].port = portInput.value.trim()));

    const protoSelect = document.createElement("select");
    ["tcp", "udp"].forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      protoSelect.appendChild(opt);
    });
    protoSelect.value = rule.proto || "tcp";
    protoSelect.addEventListener("change", () => (state.rules[index].proto = protoSelect.value));

    const sourceInput = document.createElement("input");
    sourceInput.type = "text";
    sourceInput.placeholder = "source (any, 10.0.0.0/8...)";
    sourceInput.value = rule.source || "any";
    sourceInput.addEventListener("input", () => (state.rules[index].source = sourceInput.value.trim() || "any"));

    const actionSelect = document.createElement("select");
    ["allow", "deny", "limit"].forEach((a) => {
      const opt = document.createElement("option");
      opt.value = a;
      opt.textContent = a;
      actionSelect.appendChild(opt);
    });
    actionSelect.value = rule.action || "allow";
    actionSelect.addEventListener("change", () => (state.rules[index].action = actionSelect.value));

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "rule-remove";
    removeBtn.innerHTML = "&times;";
    removeBtn.title = "Retirer cette règle";
    removeBtn.addEventListener("click", () => {
      state.rules.splice(index, 1);
      renderRulesList();
    });

    row.appendChild(portInput);
    row.appendChild(protoSelect);
    row.appendChild(sourceInput);
    row.appendChild(actionSelect);
    row.appendChild(removeBtn);
    el.rulesList.appendChild(row);
  });

  updateTitleBlock();
}

el.addRuleBtn.addEventListener("click", () => {
  state.rules.push({ port: "", proto: "tcp", source: "any", action: "allow", comment: "" });
  renderRulesList();
});

// ----------------------------------------------------------------------------
// Construction du payload + generation
// ----------------------------------------------------------------------------
function buildPayload() {
  return {
    preset: "custom",
    backend: state.backend,
    fail2ban: el.fail2banCheckbox.checked,
    default_deny_incoming: true,
    rules: state.rules.map((r) => ({
      port: parseInt(r.port, 10),
      proto: r.proto || "tcp",
      source: r.source || "any",
      action: r.action || "allow",
      comment: r.comment || "",
    })),
  };
}

async function handleGenerate() {
  clearError();

  if (!state.rules.length) {
    showError("Ajoute au moins une règle (ou choisis un preset).");
    return;
  }
  for (const r of state.rules) {
    if (!r.port || Number.isNaN(parseInt(r.port, 10))) {
      showError("Chaque règle doit avoir un port numérique valide.");
      return;
    }
  }

  const payload = buildPayload();

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "…";

  try {
    const res = await fetch("/firewall/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Erreur lors de la génération.");
      return;
    }

    state.lastFiles = data.files || [];
    state.activeFileIndex = 0;
    renderResult();
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
  if (el.applyNode) el.applyNode.classList.add("active");
  setTimeout(() => {
    el.generateBtn.textContent = "GÉNÉRER →";
  }, 1200);
}

// ----------------------------------------------------------------------------
// Rendu resultat (onglets multi-fichiers + coloration)
// ----------------------------------------------------------------------------
function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlightFile(text, filename) {
  const escaped = escapeHtml(text);
  return escaped
    .split("\n")
    .map((line) => {
      if (/^\s*#/.test(line)) {
        return `<span class="yaml-comment">${line}</span>`;
      }
      if (filename.endsWith(".local") && /^\[.+\]\s*$/.test(line)) {
        return `<span class="yaml-section">${line}</span>`;
      }
      if (/^\s*(ufw|nft|table|chain)\b/.test(line)) {
        return line.replace(/^(\s*)(ufw|nft|table|chain)\b/, `$1<span class="yaml-key">$2</span>`);
      }
      return line;
    })
    .join("\n");
}

function renderFileTabs() {
  el.fileTabs.innerHTML = "";
  if (state.lastFiles.length <= 1) return;
  state.lastFiles.forEach((f, index) => {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "file-tab";
    if (index === state.activeFileIndex) tab.classList.add("active");
    tab.textContent = f.filename;
    tab.addEventListener("click", () => {
      state.activeFileIndex = index;
      renderResult();
    });
    el.fileTabs.appendChild(tab);
  });
}

function renderResult() {
  renderFileTabs();
  el.resultBox.innerHTML = "";
  const active = state.lastFiles[state.activeFileIndex];
  if (!active) return;
  const pre = document.createElement("pre");
  pre.innerHTML = highlightFile(active.content, active.filename);
  el.resultBox.appendChild(pre);
  el.resultActions.hidden = false;
}

function resetResultBox(message) {
  el.fileTabs.innerHTML = "";
  el.resultBox.innerHTML = "";
  const p = document.createElement("p");
  p.className = "result-placeholder";
  p.textContent = message || "Le ou les fichiers générés apparaîtront ici.";
  el.resultBox.appendChild(p);
  el.resultActions.hidden = true;
  state.lastFiles = [];
  state.activeFileIndex = 0;
  if (el.applyNode) el.applyNode.classList.remove("active");
}

function updateTitleBlock() {
  el.tbPreset.textContent = state.preset || "custom";
  el.tbBackend.textContent = state.backend;
  el.tbRules.textContent = String(state.rules.length);
}

// ----------------------------------------------------------------------------
// Actions resultat : copier / telecharger
// ----------------------------------------------------------------------------
async function handleCopy() {
  const active = state.lastFiles[state.activeFileIndex];
  if (!active) return;
  try {
    await navigator.clipboard.writeText(active.content);
    el.copyBtn.textContent = "Copié !";
    setTimeout(() => (el.copyBtn.textContent = "Copier"), 1500);
  } catch (err) {
    showError("Impossible de copier automatiquement, sélectionne le texte manuellement.");
  }
}

function downloadBlob(content, filename) {
  const blob = new Blob([content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function handleDownload() {
  const active = state.lastFiles[state.activeFileIndex];
  if (!active) return;
  downloadBlob(active.content, active.filename);
}

// ----------------------------------------------------------------------------
// Reset
// ----------------------------------------------------------------------------
function handleReset() {
  setBackend("ufw");
  el.fail2banCheckbox.checked = true;
  state.preset = "web-public";
  state.rules = [];
  renderRulesList();
  document.querySelectorAll(".preset-chip").forEach((c) => c.classList.remove("active"));
  resetResultBox();
  clearError();
  applyPreset("web-public");
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
setBackend("ufw");
applyPreset("web-public");
