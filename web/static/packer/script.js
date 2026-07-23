// ============================================================================
// modules/packer/static/script.js
// Logique du module Packer : selection du builder, builder d'arguments,
// builder de provisioners (shell-inline / shell-script / file), toggles
// post-processors (dependants du builder), presets, generation, copier/telecharger.
// ============================================================================

const CONFIG = window.OPSFORGE_PACKER || { presets: [], builders: {} };

const PP_LABELS = {
  "vagrant": "vagrant (export .box)",
  "docker-tag": "docker-tag (tag d'image)",
  "compress": "compress (.tar.gz)",
};

const state = {
  builder: Object.keys(CONFIG.builders)[0] || "",
  args: [],       // [{ key, value }]
  provisioners: [], // [{ type, ... }]
  postProcessors: [], // [{ type, ...args }] ou "type" simple si pas d'args requis
};

const el = {
  presetList: document.getElementById("preset-list"),

  builderSelect: document.getElementById("builder-select"),
  nameInput: document.getElementById("name-input"),
  builderHint: document.getElementById("builder-hint"),

  argsList: document.getElementById("args-list"),
  addArgBtn: document.getElementById("add-arg-btn"),

  provList: document.getElementById("prov-list"),

  ppToggles: document.getElementById("pp-toggles"),

  generateBtn: document.getElementById("generate-btn"),
  resetBtn: document.getElementById("reset-btn"),
  errorMsg: document.getElementById("error-msg"),

  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),

  imageNode: document.querySelector('.node[data-stage="image"]'),

  tbBuilder: document.getElementById("tb-builder"),
  tbName: document.getElementById("tb-name"),
  tbProv: document.getElementById("tb-prov"),
};

// ----------------------------------------------------------------------------
// Utilitaires
// ----------------------------------------------------------------------------
function splitLines(raw) {
  return (raw || "")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

function currentBuilderInfo() {
  return CONFIG.builders[state.builder] || { required: [], defaults: {}, post_processors: [] };
}

// ----------------------------------------------------------------------------
// Builder select
// ----------------------------------------------------------------------------
function renderBuilderSelect() {
  el.builderSelect.innerHTML = "";
  Object.entries(CONFIG.builders).forEach(([key, info]) => {
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = info.label || key;
    el.builderSelect.appendChild(opt);
  });
  el.builderSelect.value = state.builder;
}

function onBuilderChange() {
  state.builder = el.builderSelect.value;
  renderBuilderHint();
  renderPostProcessorToggles();
  updateTitleBlock();
}

function renderBuilderHint() {
  const info = currentBuilderInfo();
  const required = (info.required || []).join(", ") || "aucun";
  el.builderHint.innerHTML = `Champs requis pour <strong>${state.builder}</strong> : <code>${required}</code>. Toute clé/valeur additionnelle est acceptée.`;
}

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
    const res = await fetch(`/packer/api/preset/${encodeURIComponent(name)}`);
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
  state.builder = cfg.builder || state.builder;
  el.builderSelect.value = state.builder;
  renderBuilderHint();

  el.nameInput.value = cfg.name || "";

  state.args = Object.entries(cfg.args || {}).map(([key, value]) => ({
    key,
    value: Array.isArray(value) ? value.join("\n") : String(value),
  }));
  renderArgsList();

  state.provisioners = (cfg.provisioners || []).map((p) => ({ ...p }));
  renderProvList();

  const ppList = cfg.post_processors || [];
  state.postProcessors = ppList.map((pp) =>
    typeof pp === "string" ? { type: pp } : { ...pp }
  );
  renderPostProcessorToggles();

  updateTitleBlock();
}

// ----------------------------------------------------------------------------
// Arguments source (builder key/value)
// ----------------------------------------------------------------------------
function renderArgsList() {
  el.argsList.innerHTML = "";
  state.args.forEach((arg, index) => {
    const card = document.createElement("div");
    card.className = "builder-card";

    const row = document.createElement("div");
    row.className = "builder-row";

    const keyInput = document.createElement("input");
    keyInput.type = "text";
    keyInput.className = "builder-key";
    keyInput.placeholder = "clé (ex : iso_url)";
    keyInput.value = arg.key || "";
    keyInput.addEventListener("input", () => (state.args[index].key = keyInput.value));

    const valueInput = document.createElement("textarea");
    valueInput.className = "full-input area";
    valueInput.rows = 1;
    valueInput.placeholder = "valeur (une par ligne si liste)";
    valueInput.value = arg.value || "";
    valueInput.addEventListener("input", () => (state.args[index].value = valueInput.value));

    const removeBtn = makeRemoveBtn(() => {
      state.args.splice(index, 1);
      renderArgsList();
    });

    row.appendChild(keyInput);
    row.appendChild(removeBtn);
    card.appendChild(row);
    card.appendChild(valueInput);
    el.argsList.appendChild(card);
  });
}

el.addArgBtn.addEventListener("click", () => {
  state.args.push({ key: "", value: "" });
  renderArgsList();
});

// ----------------------------------------------------------------------------
// Provisioners (shell-inline / shell-script / file)
// ----------------------------------------------------------------------------
function renderProvList() {
  el.provList.innerHTML = "";
  state.provisioners.forEach((prov, index) => {
    const card = document.createElement("div");
    card.className = "builder-card";

    const top = document.createElement("div");
    top.className = "builder-row";

    const badge = document.createElement("span");
    badge.className = "prov-type-badge";
    badge.textContent = prov.type;

    const removeBtn = makeRemoveBtn(() => {
      state.provisioners.splice(index, 1);
      renderProvList();
      updateTitleBlock();
    });

    top.appendChild(badge);
    top.appendChild(removeBtn);
    card.appendChild(top);

    if (prov.type === "shell-inline") {
      const area = document.createElement("textarea");
      area.className = "full-input area";
      area.rows = 3;
      area.placeholder = "une commande par ligne&#10;apt-get update";
      area.value = (prov.inline || []).join("\n");
      area.addEventListener("input", () => (prov.inline = splitLines(area.value)));
      card.appendChild(area);
    } else if (prov.type === "shell-script") {
      const pathInput = document.createElement("input");
      pathInput.type = "text";
      pathInput.className = "full-input";
      pathInput.placeholder = "chemin du script (ex : scripts/setup.sh)";
      pathInput.value = prov.script || "";
      pathInput.addEventListener("input", () => (prov.script = pathInput.value));
      card.appendChild(pathInput);
    } else if (prov.type === "file") {
      const row = document.createElement("div");
      row.className = "builder-row";

      const srcInput = document.createElement("input");
      srcInput.type = "text";
      srcInput.placeholder = "source locale (ex : files/motd)";
      srcInput.value = prov.source || "";
      srcInput.addEventListener("input", () => (prov.source = srcInput.value));

      const dstInput = document.createElement("input");
      dstInput.type = "text";
      dstInput.placeholder = "destination distante (ex : /etc/motd)";
      dstInput.value = prov.destination || "";
      dstInput.addEventListener("input", () => (prov.destination = dstInput.value));

      row.appendChild(srcInput);
      row.appendChild(dstInput);
      card.appendChild(row);
    }

    el.provList.appendChild(card);
  });
}

document.querySelectorAll("[data-add-prov]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const type = btn.dataset.addProv;
    if (type === "shell-inline") state.provisioners.push({ type, inline: [] });
    else if (type === "shell-script") state.provisioners.push({ type, script: "" });
    else if (type === "file") state.provisioners.push({ type, source: "", destination: "" });
    renderProvList();
    updateTitleBlock();
  });
});

function makeRemoveBtn(onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "builder-remove";
  btn.innerHTML = "&times;";
  btn.title = "Retirer";
  btn.addEventListener("click", onClick);
  return btn;
}

// ----------------------------------------------------------------------------
// Post-processors (toggles dependants du builder)
// ----------------------------------------------------------------------------
function renderPostProcessorToggles() {
  const info = currentBuilderInfo();
  const available = info.post_processors || [];
  el.ppToggles.innerHTML = "";

  if (!available.length) {
    const hint = document.createElement("p");
    hint.className = "field-hint";
    hint.textContent = "Aucun post-processor disponible pour ce builder.";
    el.ppToggles.appendChild(hint);
    return;
  }

  available.forEach((name) => {
    const label = document.createElement("label");
    label.className = "toggle";

    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = state.postProcessors.some((pp) => pp.type === name);
    input.addEventListener("change", () => {
      if (input.checked) {
        if (!state.postProcessors.some((pp) => pp.type === name)) {
          const extra = name === "docker-tag" ? { repository: "mon-org/app", tag: "latest" } : {};
          state.postProcessors.push({ type: name, ...extra });
        }
      } else {
        state.postProcessors = state.postProcessors.filter((pp) => pp.type !== name);
      }
      renderPostProcessorExtras();
    });

    label.appendChild(input);
    label.appendChild(document.createTextNode(PP_LABELS[name] || name));
    el.ppToggles.appendChild(label);
  });

  renderPostProcessorExtras();
}

function renderPostProcessorExtras() {
  // Retire les blocs d'extras precedents.
  el.ppToggles.querySelectorAll(".pp-extra").forEach((n) => n.remove());

  const dockerTag = state.postProcessors.find((pp) => pp.type === "docker-tag");
  if (dockerTag) {
    const wrap = document.createElement("div");
    wrap.className = "builder-card pp-extra";
    wrap.style.width = "100%";

    const row = document.createElement("div");
    row.className = "builder-row";

    const repoInput = document.createElement("input");
    repoInput.type = "text";
    repoInput.placeholder = "repository (ex : mon-org/app)";
    repoInput.value = dockerTag.repository || "";
    repoInput.addEventListener("input", () => (dockerTag.repository = repoInput.value));

    const tagInput = document.createElement("input");
    tagInput.type = "text";
    tagInput.placeholder = "tag (ex : latest)";
    tagInput.value = dockerTag.tag || "";
    tagInput.addEventListener("input", () => (dockerTag.tag = tagInput.value));

    row.appendChild(repoInput);
    row.appendChild(tagInput);
    wrap.appendChild(row);
    el.ppToggles.appendChild(wrap);
  }
}

// ----------------------------------------------------------------------------
// Construction du payload + generation
// ----------------------------------------------------------------------------
function buildPayload() {
  const args = {};
  state.args.forEach((arg) => {
    const key = (arg.key || "").trim();
    if (!key) return;
    const lines = splitLines(arg.value);
    args[key] = lines.length > 1 ? lines : (arg.value || "").trim();
  });

  return {
    builder: state.builder,
    name: el.nameInput.value.trim(),
    args,
    provisioners: state.provisioners.filter((p) => {
      if (p.type === "shell-inline") return (p.inline || []).length;
      if (p.type === "shell-script") return (p.script || "").trim();
      if (p.type === "file") return (p.source || "").trim() && (p.destination || "").trim();
      return false;
    }),
    post_processors: state.postProcessors,
  };
}

function frontValidate() {
  if (!el.nameInput.value.trim()) {
    return "Le nom du build est requis (ex : ubuntu-base).";
  }
  const info = currentBuilderInfo();
  const args = {};
  state.args.forEach((a) => { if ((a.key || "").trim()) args[a.key.trim()] = a.value; });
  const missing = (info.required || []).filter((f) => !String(args[f] || "").trim());
  if (missing.length) {
    return `Champs requis manquants : ${missing.join(", ")}.`;
  }
  return null;
}

async function handleGenerate() {
  clearError();

  const frontError = frontValidate();
  if (frontError) {
    showError(frontError);
    return;
  }

  const payload = buildPayload();

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "…";

  try {
    const res = await fetch("/packer/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Erreur lors de la génération.");
      return;
    }

    state.lastFilename = data.filename || "build.pkr.hcl";
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
  if (el.imageNode) el.imageNode.classList.add("active");
  setTimeout(() => {
    el.generateBtn.textContent = "GÉNÉRER →";
  }, 1200);
}

// ----------------------------------------------------------------------------
// Rendu resultat (coloration HCL2)
// ----------------------------------------------------------------------------
function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlightHcl(text) {
  const escaped = escapeHtml(text);
  return escaped
    .split("\n")
    .map((line) => {
      const blockMatch = line.match(/^(\s*)([a-z][a-zA-Z0-9_-]*)(\s+"[^"]*"){0,2}(\s*\{)?$/);
      if (blockMatch && /\{$/.test(line.trim())) {
        return `<span class="hcl-block">${line}</span>`;
      }
      const kv = line.match(/^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*=\s*)(.*)$/);
      if (kv) {
        return `${kv[1]}<span class="hcl-key">${kv[2]}</span>${kv[3]}${kv[4]}`;
      }
      return line;
    })
    .join("\n");
}

function renderResult(combined) {
  state.lastCombined = combined;
  el.resultBox.innerHTML = "";
  const pre = document.createElement("pre");
  pre.innerHTML = highlightHcl(combined);
  el.resultBox.appendChild(pre);
  el.resultActions.hidden = false;
}

function resetResultBox(message) {
  el.resultBox.innerHTML = "";
  const p = document.createElement("p");
  p.className = "result-placeholder";
  p.textContent = message || "Le template généré apparaîtra ici.";
  el.resultBox.appendChild(p);
  el.resultActions.hidden = true;
  state.lastCombined = "";
  if (el.imageNode) el.imageNode.classList.remove("active");
}

function updateTitleBlock() {
  el.tbBuilder.textContent = state.builder || "—";
  el.tbName.textContent = el.nameInput.value.trim() || "—";
  el.tbProv.textContent = String(state.provisioners.length);
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

function handleDownload() {
  if (!state.lastCombined) return;
  const blob = new Blob([state.lastCombined], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = state.lastFilename || "build.pkr.hcl";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ----------------------------------------------------------------------------
// Reset
// ----------------------------------------------------------------------------
function handleReset() {
  el.nameInput.value = "";
  state.args = [];
  state.provisioners = [];
  state.postProcessors = [];
  renderArgsList();
  renderProvList();
  renderPostProcessorToggles();

  document.querySelectorAll(".preset-chip").forEach((c) => c.classList.remove("active"));
  resetResultBox();
  clearError();
  updateTitleBlock();
}

// ----------------------------------------------------------------------------
// Utilitaires messages
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
el.builderSelect.addEventListener("change", onBuilderChange);
el.generateBtn.addEventListener("click", handleGenerate);
el.resetBtn.addEventListener("click", handleReset);
el.copyBtn.addEventListener("click", handleCopy);
el.downloadBtn.addEventListener("click", handleDownload);
el.nameInput.addEventListener("input", updateTitleBlock);

renderBuilderSelect();
renderBuilderHint();
renderPresetList();
renderArgsList();
renderProvList();
renderPostProcessorToggles();
updateTitleBlock();
