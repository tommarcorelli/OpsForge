// ============================================================================
// modules/precommit/static/script.js
// Logique du module precommit : presets, switch pre-commit/husky, checklist
// de hooks, generation via /precommit/api/generate, onglets multi-fichiers.
// ============================================================================

const CONFIG = window.OPSFORGE_PRECOMMIT || { backends: [], presets: [] };

// Catalogue cote client (juste pour l'affichage des labels/descriptions ;
// la verite cote generation reste server-side).
const HOOK_LABELS = {
  "trailing-whitespace": { label: "Espaces en fin de ligne", backends: ["pre-commit"] },
  "end-of-file-fixer": { label: "Ligne vide en fin de fichier", backends: ["pre-commit"] },
  "check-yaml": { label: "Valider la syntaxe YAML", backends: ["pre-commit"] },
  "check-added-large-files": { label: "Bloquer les gros fichiers", backends: ["pre-commit"] },
  "detect-private-key": { label: "Detecter les cles privees", backends: ["pre-commit"] },
  "black": { label: "Formater le code Python (Black)", backends: ["pre-commit"] },
  "ruff": { label: "Linter Python (Ruff)", backends: ["pre-commit"] },
  "mypy": { label: "Verification de types (mypy)", backends: ["pre-commit"] },
  "eslint": { label: "Linter JS/TS (ESLint)", backends: ["husky"] },
  "prettier": { label: "Formater JS/TS/JSON/CSS/MD (Prettier)", backends: ["husky"] },
  "gitleaks": { label: "Scanner les secrets (Gitleaks)", backends: ["pre-commit", "husky"] },
};

const state = {
  backend: "pre-commit",
  preset: "python",
  hooks: [],
  files: [],
  activeFileIndex: 0,
};

const el = {
  presetList: document.getElementById("preset-list"),
  backendSwitch: document.getElementById("backend-switch"),
  hooksList: document.getElementById("hooks-list"),

  generateBtn: document.getElementById("generate-btn"),
  resetBtn: document.getElementById("reset-btn"),
  errorMsg: document.getElementById("error-msg"),

  fileTabs: document.getElementById("file-tabs"),
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
    const res = await fetch(`/precommit/api/preset/${encodeURIComponent(name)}`);
    const data = await res.json();
    if (!res.ok) {
      showError(data.error || "Preset introuvable.");
      return;
    }
    state.preset = name;
    setBackend(data.backend || "pre-commit");
    state.hooks = data.hooks || [];
    renderHooksList();

    document.querySelectorAll(".preset-chip").forEach((c) => c.classList.remove("active"));
    if (chipEl) chipEl.classList.add("active");
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  }
}

// ----------------------------------------------------------------------------
// Backend
// ----------------------------------------------------------------------------
function setBackend(backend) {
  state.backend = backend;
  el.backendSwitch.querySelectorAll(".provider-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.backend === backend);
  });
  renderHooksList();
}

el.backendSwitch.querySelectorAll(".provider-btn").forEach((btn) => {
  btn.addEventListener("click", () => setBackend(btn.dataset.backend));
});

// ----------------------------------------------------------------------------
// Checklist de hooks
// ----------------------------------------------------------------------------
function renderHooksList() {
  el.hooksList.innerHTML = "";
  Object.entries(HOOK_LABELS).forEach(([id, meta]) => {
    const supported = meta.backends.includes(state.backend);

    const label = document.createElement("label");
    label.className = "hook-toggle" + (supported ? "" : " unsupported");

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.hooks.includes(id);
    checkbox.disabled = !supported;
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        if (!state.hooks.includes(id)) state.hooks.push(id);
      } else {
        state.hooks = state.hooks.filter((h) => h !== id);
      }
    });

    const span = document.createElement("span");
    span.className = "hook-label";
    span.textContent = meta.label;
    if (!supported) {
      const small = document.createElement("span");
      small.className = "hook-desc";
      small.textContent = `Indisponible pour ${state.backend}`;
      span.appendChild(small);
    }

    label.appendChild(checkbox);
    label.appendChild(span);
    el.hooksList.appendChild(label);
  });
}

// ----------------------------------------------------------------------------
// Generation
// ----------------------------------------------------------------------------
async function handleGenerate() {
  clearError();

  if (!state.hooks.length) {
    showError("Coche au moins un hook (ou choisis un preset).");
    return;
  }

  const payload = { preset: "custom", backend: state.backend, hooks: state.hooks };

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "…";

  try {
    const res = await fetch("/precommit/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Erreur lors de la génération.");
      return;
    }

    state.files = data.files || [];
    state.activeFileIndex = 0;
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
// Rendu resultat (onglets multi-fichiers + coloration)
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
      if (/^\s*(repos|hooks):/.test(line)) return `<span class="yaml-section">${line}</span>`;
      return line;
    })
    .join("\n");
}

function renderFileTabs() {
  el.fileTabs.innerHTML = "";
  if (state.files.length <= 1) return;
  state.files.forEach((f, index) => {
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
  const active = state.files[state.activeFileIndex];
  if (!active) return;
  const pre = document.createElement("pre");
  pre.innerHTML = highlightContent(active.content);
  el.resultBox.appendChild(pre);
  el.resultActions.hidden = false;
}

function resetResultBox() {
  el.fileTabs.innerHTML = "";
  el.resultBox.innerHTML = "";
  const p = document.createElement("p");
  p.className = "result-placeholder";
  p.textContent = "Le ou les fichiers générés apparaîtront ici.";
  el.resultBox.appendChild(p);
  el.resultActions.hidden = true;
  state.files = [];
  state.activeFileIndex = 0;
  if (el.applyNode) el.applyNode.classList.remove("active");
}

// ----------------------------------------------------------------------------
// Actions resultat
// ----------------------------------------------------------------------------
async function handleCopy() {
  const active = state.files[state.activeFileIndex];
  if (!active) return;
  try {
    await navigator.clipboard.writeText(active.content);
    el.copyBtn.textContent = "Copié !";
    setTimeout(() => (el.copyBtn.textContent = "Copier"), 1500);
  } catch (err) {
    showError("Impossible de copier automatiquement, sélectionne le texte manuellement.");
  }
}

function handleDownload() {
  const active = state.files[state.activeFileIndex];
  if (!active) return;
  const blob = new Blob([active.content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = active.filename.replace("/", "__");
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ----------------------------------------------------------------------------
// Reset
// ----------------------------------------------------------------------------
function handleReset() {
  setBackend("pre-commit");
  state.preset = "python";
  state.hooks = [];
  document.querySelectorAll(".preset-chip").forEach((c) => c.classList.remove("active"));
  resetResultBox();
  clearError();
  applyPreset("python");
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
setBackend("pre-commit");
applyPreset("python");
