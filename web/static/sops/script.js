// ============================================================================
// web/static/sops/script.js
// Logique du module sops : presets, cartes de regles (chemin + destinataires
// age + options avancees), generation via /sops/api/generate, onglets
// multi-fichiers.
// ============================================================================

const CONFIG = window.OPSFORGE_SOPS || { presets: {}, inputTypes: [] };

const state = {
  preset: "solo-dev",
  rules: [],
  files: [],
  activeFileIndex: 0,
};

const el = {
  presetList: document.getElementById("preset-list"),
  presetHint: document.getElementById("preset-hint"),
  ruleList: document.getElementById("rule-list"),
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
};

// ----------------------------------------------------------------------------
// Helpers de construction de champs
// ----------------------------------------------------------------------------
function field(labelText, input) {
  const wrap = document.createElement("div");
  const label = document.createElement("label");
  label.className = "sub-label";
  label.textContent = labelText;
  const id = `f-${Math.random().toString(36).slice(2, 9)}`;
  label.htmlFor = id;
  input.id = id;
  wrap.appendChild(label);
  wrap.appendChild(input);
  return wrap;
}

function textInput(value, placeholder, onInput, { mono = false } = {}) {
  const input = document.createElement("input");
  input.type = "text";
  input.className = mono ? "text-input mono" : "text-input";
  input.value = value == null ? "" : value;
  if (placeholder) input.placeholder = placeholder;
  input.addEventListener("input", () => onInput(input.value));
  return input;
}

function selectInput(value, options, onChange) {
  const select = document.createElement("select");
  select.className = "text-input";
  options.forEach(([optValue, label]) => {
    const opt = document.createElement("option");
    opt.value = optValue;
    opt.textContent = label;
    if (optValue === value) opt.selected = true;
    select.appendChild(opt);
  });
  select.addEventListener("change", () => onChange(select.value));
  return select;
}

function grid(children) {
  const wrap = document.createElement("div");
  wrap.className = "grid-2";
  children.forEach((child) => wrap.appendChild(child));
  return wrap;
}

function entryCard(title, onRemove, fields) {
  const card = document.createElement("div");
  card.className = "entry-card";

  const head = document.createElement("div");
  head.className = "entry-head";

  const titleEl = document.createElement("span");
  titleEl.className = "entry-title";
  titleEl.textContent = title;

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "btn-remove";
  removeBtn.textContent = "Retirer";
  removeBtn.addEventListener("click", onRemove);

  head.appendChild(titleEl);
  head.appendChild(removeBtn);

  const body = document.createElement("div");
  body.className = "entry-fields";
  fields.forEach((f) => body.appendChild(f));

  card.appendChild(head);
  card.appendChild(body);
  return card;
}

// ----------------------------------------------------------------------------
// Presets
// ----------------------------------------------------------------------------
function renderPresetList() {
  el.presetList.innerHTML = "";
  Object.entries(CONFIG.presets)
    .filter(([name]) => name !== "custom")
    .forEach(([name, label]) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "preset-chip";
      chip.textContent = name;
      chip.title = label;
      chip.dataset.preset = name;
      if (name === state.preset) chip.classList.add("active");
      chip.addEventListener("click", () => applyPreset(name));
      el.presetList.appendChild(chip);
    });
}

function markActivePreset(name) {
  el.presetList.querySelectorAll(".preset-chip").forEach((chip) => {
    chip.classList.toggle("active", chip.dataset.preset === name);
  });
  el.presetHint.textContent = CONFIG.presets[name] || "Choisis un point de départ, puis ajuste les règles ci-dessous.";
}

let presetRequestId = 0;

async function applyPreset(name) {
  clearError();
  const requestId = ++presetRequestId;
  el.generateBtn.disabled = true;
  try {
    const res = await fetch(`/sops/api/preset/${encodeURIComponent(name)}`);
    const data = await res.json();
    if (requestId !== presetRequestId) return;
    if (!res.ok) {
      showError(data.error || "Preset introuvable.");
      return;
    }
    state.preset = name;
    state.rules = (data.rules || []).map((rule) => ({
      label: rule.label || "",
      path_regex: rule.path_regex || "",
      age_recipients: (rule.age_recipients || []).join(", "),
      encrypted_regex: rule.encrypted_regex || "",
      input_type: rule.input_type || "",
    }));
    renderRuleList();
    markActivePreset(name);
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  } finally {
    if (requestId === presetRequestId) el.generateBtn.disabled = false;
  }
}

// ----------------------------------------------------------------------------
// Cartes de regles
// ----------------------------------------------------------------------------
function renderRuleList() {
  el.ruleList.innerHTML = "";
  state.rules.forEach((rule, index) => {
    const card = entryCard(
      rule.label || rule.path_regex || `Règle #${index + 1}`,
      () => {
        state.rules.splice(index, 1);
        renderRuleList();
      },
      [
        field("Description (optionnel)", textInput(rule.label, "Secrets de production", (v) => { rule.label = v; })),
        field("Expression de chemin (path_regex)", textInput(rule.path_regex, "secrets/.*\\.yaml$", (v) => { rule.path_regex = v; }, { mono: true })),
        field("Destinataires age (clés publiques)", textInput(rule.age_recipients, "age1..., age1...", (v) => { rule.age_recipients = v; }, { mono: true })),
        grid([
          field("Type d'entrée", selectInput(rule.input_type, [
            ["", "Auto (selon l'extension)"],
            ...CONFIG.inputTypes.map((t) => [t, t]),
          ], (v) => { rule.input_type = v; })),
          field("Clés à chiffrer (encrypted_regex)", textInput(rule.encrypted_regex, "^(data|stringData)$", (v) => { rule.encrypted_regex = v; }, { mono: true })),
        ]),
      ]
    );
    el.ruleList.appendChild(card);
  });

  if (!state.rules.length) {
    const empty = document.createElement("p");
    empty.className = "field-hint";
    empty.textContent = "Aucune règle pour l'instant : ajoutes-en une ci-dessous.";
    el.ruleList.appendChild(empty);
  }
}

function collectPayload() {
  const rules = state.rules
    .filter((r) => r.path_regex.trim())
    .map((r) => {
      const rule = {
        path_regex: r.path_regex.trim(),
        age_recipients: r.age_recipients.split(",").map((v) => v.trim()).filter(Boolean),
      };
      if (r.label.trim()) rule.label = r.label.trim();
      if (r.encrypted_regex.trim()) rule.encrypted_regex = r.encrypted_regex.trim();
      if (r.input_type) rule.input_type = r.input_type;
      return rule;
    });

  return { preset: "custom", rules };
}

// ----------------------------------------------------------------------------
// Generation
// ----------------------------------------------------------------------------
async function handleGenerate() {
  clearError();

  const payload = collectPayload();

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "…";

  try {
    const res = await fetch("/sops/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showError((data.error || "Erreur lors de la génération.").split("; ").join("\n"));
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
// Rendu resultat
// ----------------------------------------------------------------------------
function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlightContent(text) {
  return escapeHtml(text)
    .split("\n")
    .map((line) => {
      if (/^\s*#/.test(line)) return `<span class="conf-comment">${line}</span>`;
      if (/^creation_rules:/.test(line)) return `<span class="conf-block">${line}</span>`;
      const match = line.match(/^(\s*-?\s*)([a-z_]+)(:)(\s*)(.*)$/);
      if (match) {
        const [, indent, key, colon, space, rest] = match;
        return `${indent}<span class="conf-key">${key}</span>${colon}${space}${rest}`;
      }
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
  a.download = active.filename.split("/").pop();
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
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
el.addRuleBtn.addEventListener("click", () => {
  state.rules.push({ label: "", path_regex: "", age_recipients: "", encrypted_regex: "", input_type: "" });
  renderRuleList();
});

el.generateBtn.addEventListener("click", handleGenerate);
el.resetBtn.addEventListener("click", () => {
  resetResultBox();
  clearError();
  applyPreset("solo-dev");
});
el.copyBtn.addEventListener("click", handleCopy);
el.downloadBtn.addEventListener("click", handleDownload);

renderPresetList();
applyPreset("solo-dev");
