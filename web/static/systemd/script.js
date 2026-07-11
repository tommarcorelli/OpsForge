// ============================================================================
// modules/systemd/static/script.js
// Logique du module systemd : bascule service/timer, variables d'env
// dynamiques, presets, generation via /systemd/api/generate, copier/telecharger.
// ============================================================================

const CONFIG = window.OPSFORGE_SYSTEMD || {
  modes: [],
  serviceTypes: [],
  restartPolicies: [],
  presets: [],
};

const state = {
  mode: "service",
  env: [],
  lastCombined: "",
  lastUnits: [],
  lastName: "unit",
};

const el = {
  presetList: document.getElementById("preset-list"),
  modeSwitch: document.getElementById("mode-switch"),
  nameInput: document.getElementById("name-input"),
  descriptionInput: document.getElementById("description-input"),
  execStartInput: document.getElementById("exec-start-input"),
  typeSelect: document.getElementById("type-select"),
  userInput: document.getElementById("user-input"),
  groupInput: document.getElementById("group-input"),
  workdirInput: document.getElementById("workdir-input"),
  envfileInput: document.getElementById("envfile-input"),

  envList: document.getElementById("env-list"),
  addEnvBtn: document.getElementById("add-env-btn"),

  fieldsRestart: document.getElementById("fields-restart"),
  restartSelect: document.getElementById("restart-select"),
  restartSecInput: document.getElementById("restart-sec-input"),
  afterInput: document.getElementById("after-input"),

  fieldsTimer: document.getElementById("fields-timer"),
  onCalendarInput: document.getElementById("on-calendar-input"),
  persistentCheckbox: document.getElementById("persistent-checkbox"),

  nnpCheckbox: document.getElementById("nnp-checkbox"),
  ptmpCheckbox: document.getElementById("ptmp-checkbox"),
  psysCheckbox: document.getElementById("psys-checkbox"),
  phomeCheckbox: document.getElementById("phome-checkbox"),

  generateBtn: document.getElementById("generate-btn"),
  resetBtn: document.getElementById("reset-btn"),
  errorMsg: document.getElementById("error-msg"),

  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),

  enableNode: document.querySelector('.node[data-stage="enable"]'),

  tbMode: document.getElementById("tb-mode"),
  tbName: document.getElementById("tb-name"),
  tbType: document.getElementById("tb-type"),
};

const MODE_LABELS = {
  service: "Service",
  timer: "Timer",
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
    const res = await fetch(`/systemd/api/preset/${encodeURIComponent(name)}`);
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
  setMode(cfg.mode || "service");
  el.nameInput.value = cfg.name || "";
  el.descriptionInput.value = cfg.description || "";
  el.execStartInput.value = cfg.exec_start || "";
  el.typeSelect.value = cfg.service_type || "simple";
  el.userInput.value = cfg.user || "";
  el.groupInput.value = cfg.group || "";
  el.workdirInput.value = cfg.working_directory || "";
  el.envfileInput.value = cfg.environment_file || "";
  el.restartSelect.value = cfg.restart || "on-failure";
  el.restartSecInput.value = cfg.restart_sec != null ? cfg.restart_sec : 5;
  el.afterInput.value = cfg.after || "";
  el.onCalendarInput.value = cfg.on_calendar || "";
  el.persistentCheckbox.checked = !!cfg.persistent;
  el.nnpCheckbox.checked = !!cfg.no_new_privileges;
  el.ptmpCheckbox.checked = !!cfg.private_tmp;
  el.psysCheckbox.checked = !!cfg.protect_system;
  el.phomeCheckbox.checked = !!cfg.protect_home;

  state.env = normalizeEnv(cfg.environment);
  renderEnvList();

  updateTitleBlock();
}

function normalizeEnv(raw) {
  return (raw || []).map((item) => {
    if (typeof item === "string" && item.includes("=")) {
      const idx = item.indexOf("=");
      return { key: item.slice(0, idx), value: item.slice(idx + 1) };
    }
    return { key: item.key || "", value: item.value || "" };
  });
}

// ----------------------------------------------------------------------------
// Bascule de mode
// ----------------------------------------------------------------------------
function setMode(mode) {
  state.mode = mode;
  el.modeSwitch.querySelectorAll(".provider-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });

  // En mode timer, le service est un oneshot declenche : la politique de
  // redemarrage ne s'applique pas, mais la planification devient necessaire.
  el.fieldsRestart.hidden = mode === "timer";
  el.fieldsTimer.hidden = mode !== "timer";

  updateTitleBlock();
}

el.modeSwitch.querySelectorAll(".provider-btn").forEach((btn) => {
  btn.addEventListener("click", () => setMode(btn.dataset.mode));
});

// ----------------------------------------------------------------------------
// Variables d'environnement (builder dynamique)
// ----------------------------------------------------------------------------
function renderEnvList() {
  el.envList.innerHTML = "";
  state.env.forEach((pair, index) => {
    const row = document.createElement("div");
    row.className = "env-row";

    const keyInput = document.createElement("input");
    keyInput.type = "text";
    keyInput.placeholder = "CLÉ";
    keyInput.value = pair.key || "";
    keyInput.addEventListener("input", () => (state.env[index].key = keyInput.value));

    const valueInput = document.createElement("input");
    valueInput.type = "text";
    valueInput.placeholder = "valeur";
    valueInput.value = pair.value || "";
    valueInput.addEventListener("input", () => (state.env[index].value = valueInput.value));

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "env-remove";
    removeBtn.innerHTML = "&times;";
    removeBtn.title = "Retirer cette variable";
    removeBtn.addEventListener("click", () => {
      state.env.splice(index, 1);
      renderEnvList();
    });

    row.appendChild(keyInput);
    row.appendChild(valueInput);
    row.appendChild(removeBtn);
    el.envList.appendChild(row);
  });
}

el.addEnvBtn.addEventListener("click", () => {
  state.env.push({ key: "", value: "" });
  renderEnvList();
});

// ----------------------------------------------------------------------------
// Construction du payload + generation
// ----------------------------------------------------------------------------
function buildPayload() {
  const payload = {
    mode: state.mode,
    name: el.nameInput.value.trim(),
    description: el.descriptionInput.value.trim(),
    exec_start: el.execStartInput.value.trim(),
    service_type: el.typeSelect.value,
    user: el.userInput.value.trim(),
    group: el.groupInput.value.trim(),
    working_directory: el.workdirInput.value.trim(),
    environment_file: el.envfileInput.value.trim(),
    environment: state.env
      .filter((p) => (p.key || "").trim())
      .map((p) => ({ key: p.key.trim(), value: p.value })),
    no_new_privileges: el.nnpCheckbox.checked,
    private_tmp: el.ptmpCheckbox.checked,
    protect_system: el.psysCheckbox.checked,
    protect_home: el.phomeCheckbox.checked,
  };

  if (state.mode === "service") {
    payload.restart = el.restartSelect.value;
    payload.restart_sec = parseInt(el.restartSecInput.value, 10);
    if (Number.isNaN(payload.restart_sec)) payload.restart_sec = 5;
    payload.after = el.afterInput.value.trim();
  } else {
    payload.on_calendar = el.onCalendarInput.value.trim();
    payload.persistent = el.persistentCheckbox.checked;
  }

  return payload;
}

async function handleGenerate() {
  clearError();

  if (!el.nameInput.value.trim()) {
    showError("Le nom de l'unité est requis.");
    return;
  }
  if (!el.execStartInput.value.trim()) {
    showError("La commande à exécuter (ExecStart) est requise.");
    return;
  }

  const payload = buildPayload();

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "…";

  try {
    const res = await fetch("/systemd/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Erreur lors de la génération.");
      return;
    }

    state.lastUnits = data.units || [];
    state.lastName = data.name || "unit";
    renderResult(data.combined);
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
  if (el.enableNode) el.enableNode.classList.add("active");
  setTimeout(() => {
    el.generateBtn.textContent = "GÉNÉRER →";
  }, 1200);
}

// ----------------------------------------------------------------------------
// Rendu resultat (coloration INI)
// ----------------------------------------------------------------------------
function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlightUnit(text) {
  const escaped = escapeHtml(text);
  return escaped
    .split("\n")
    .map((line) => {
      if (/^\s*#/.test(line)) {
        return `<span class="yaml-comment">${line}</span>`;
      }
      if (/^\[.+\]\s*$/.test(line)) {
        return `<span class="yaml-section">${line}</span>`;
      }
      const kv = line.match(/^([A-Za-z][A-Za-z0-9]*)=(.*)$/);
      if (kv) {
        return `<span class="yaml-key">${kv[1]}</span>=${kv[2]}`;
      }
      return line;
    })
    .join("\n");
}

function renderResult(combined) {
  state.lastCombined = combined;
  el.resultBox.innerHTML = "";
  const pre = document.createElement("pre");
  pre.innerHTML = highlightUnit(combined);
  el.resultBox.appendChild(pre);
  el.resultActions.hidden = false;
}

function resetResultBox(message) {
  el.resultBox.innerHTML = "";
  const p = document.createElement("p");
  p.className = "result-placeholder";
  p.textContent = message || "Le ou les fichiers générés apparaîtront ici.";
  el.resultBox.appendChild(p);
  el.resultActions.hidden = true;
  state.lastCombined = "";
  state.lastUnits = [];
  if (el.enableNode) el.enableNode.classList.remove("active");
}

function updateTitleBlock() {
  el.tbMode.textContent = MODE_LABELS[state.mode] || "—";
  el.tbName.textContent = el.nameInput.value.trim() || "—";
  el.tbType.textContent = el.typeSelect.value || "simple";
}

// ----------------------------------------------------------------------------
// Actions resultat : copier / telecharger
// ----------------------------------------------------------------------------
async function handleCopy() {
  if (!state.lastCombined) return;
  try {
    await navigator.clipboard.writeText(state.lastCombined);
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
  if (!state.lastCombined) return;
  // Une seule unite -> on telecharge le vrai fichier ; plusieurs -> un
  // fichier combine (chaque section porte en commentaire son nom cible).
  if (state.lastUnits.length === 1) {
    downloadBlob(state.lastUnits[0].content, state.lastUnits[0].filename);
  } else {
    downloadBlob(state.lastCombined, `${state.lastName}-units.txt`);
  }
}

// ----------------------------------------------------------------------------
// Reset
// ----------------------------------------------------------------------------
function handleReset() {
  setMode("service");
  el.nameInput.value = "";
  el.descriptionInput.value = "";
  el.execStartInput.value = "";
  el.typeSelect.value = "simple";
  el.userInput.value = "";
  el.groupInput.value = "";
  el.workdirInput.value = "";
  el.envfileInput.value = "";
  el.restartSelect.value = "on-failure";
  el.restartSecInput.value = 5;
  el.afterInput.value = "";
  el.onCalendarInput.value = "";
  el.persistentCheckbox.checked = false;
  el.nnpCheckbox.checked = false;
  el.ptmpCheckbox.checked = false;
  el.psysCheckbox.checked = false;
  el.phomeCheckbox.checked = false;

  state.env = [];
  renderEnvList();

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
el.nameInput.addEventListener("input", updateTitleBlock);
el.typeSelect.addEventListener("change", updateTitleBlock);

renderPresetList();
renderEnvList();
setMode("service");
