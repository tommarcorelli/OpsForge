// ============================================================================
// web/static/dns/script.js
// Logique du module dns : bascule BIND/Route53, presets, cartes
// d'enregistrements (type + champs specifiques), generation via
// /dns/api/generate.
// ============================================================================

const CONFIG = window.OPSFORGE_DNS || { engines: [], presets: {}, recordTypes: [], caaTags: [] };

const state = {
  engine: "bind",
  preset: "site-statique",
  records: [],
  lastFile: null, // { filename, content }
};

const el = {
  engineSwitch: document.getElementById("engine-switch"),
  presetList: document.getElementById("preset-list"),
  presetHint: document.getElementById("preset-hint"),

  domain: document.getElementById("domain"),
  ttl: document.getElementById("ttl"),
  nameservers: document.getElementById("nameservers"),
  soaPrimaryNs: document.getElementById("soa-primary-ns"),
  soaAdminEmail: document.getElementById("soa-admin-email"),
  soaRefresh: document.getElementById("soa-refresh"),
  soaRetry: document.getElementById("soa-retry"),
  soaExpire: document.getElementById("soa-expire"),

  recordList: document.getElementById("record-list"),
  addRecordBtn: document.getElementById("add-record-btn"),

  generateBtn: document.getElementById("generate-btn"),
  resetBtn: document.getElementById("reset-btn"),
  errorMsg: document.getElementById("error-msg"),

  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),

  node1Label: document.getElementById("node-1-label"),
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

function numberInput(value, onInput) {
  const input = document.createElement("input");
  input.type = "number";
  input.className = "text-input";
  input.value = value == null ? "" : value;
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

function grid(children, columns) {
  const wrap = document.createElement("div");
  wrap.className = columns === 3 ? "grid-3" : "grid-2";
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
// Moteur (format de sortie uniquement : ne change pas les enregistrements)
// ----------------------------------------------------------------------------
function setEngine(engine) {
  state.engine = engine;
  el.engineSwitch.querySelectorAll(".engine-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.engine === engine);
  });
  el.node1Label.textContent = engine === "bind" ? "ZONE BIND" : "ROUTE53";
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
  el.presetHint.textContent = CONFIG.presets[name] || "Choisis un point de départ, puis ajuste les enregistrements ci-dessous.";
}

let presetRequestId = 0;

async function applyPreset(name) {
  clearError();
  const requestId = ++presetRequestId;
  el.generateBtn.disabled = true;
  try {
    const res = await fetch(`/dns/api/preset/${encodeURIComponent(name)}?engine=${encodeURIComponent(state.engine)}`);
    const data = await res.json();
    if (requestId !== presetRequestId) return;
    if (!res.ok) {
      showError(data.error || "Preset introuvable.");
      return;
    }
    state.preset = name;
    fillForm(data);
    markActivePreset(name);
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  } finally {
    if (requestId === presetRequestId) el.generateBtn.disabled = false;
  }
}

// ----------------------------------------------------------------------------
// Formulaire
// ----------------------------------------------------------------------------
function fillForm(config) {
  el.domain.value = config.domain || "";
  el.ttl.value = config.ttl || 3600;
  el.nameservers.value = (config.nameservers || []).join(", ");

  const soa = config.soa || {};
  el.soaPrimaryNs.value = soa.primary_ns || "";
  el.soaAdminEmail.value = soa.admin_email || "";
  el.soaRefresh.value = soa.refresh ?? 3600;
  el.soaRetry.value = soa.retry ?? 900;
  el.soaExpire.value = soa.expire ?? 1209600;

  state.records = (config.records || []).map((r) => ({
    type: r.type || "A",
    name: r.name || "",
    value: r.value || "",
    priority: r.priority ?? "",
    weight: r.weight ?? "",
    port: r.port ?? "",
    flag: r.flag ?? 0,
    tag: r.tag || "issue",
  }));
  renderRecordList();
}

function typeSpecificFields(record) {
  if (record.type === "MX") {
    return [field("Priorité", numberInput(record.priority, (v) => { record.priority = v; }))];
  }
  if (record.type === "SRV") {
    return [grid([
      field("Priorité", numberInput(record.priority, (v) => { record.priority = v; })),
      field("Poids", numberInput(record.weight, (v) => { record.weight = v; })),
      field("Port", numberInput(record.port, (v) => { record.port = v; })),
    ], 3)];
  }
  if (record.type === "CAA") {
    return [grid([
      field("Tag", selectInput(record.tag, CONFIG.caaTags.map((t) => [t, t]), (v) => { record.tag = v; })),
      field("Flag", selectInput(String(record.flag), [["0", "0 (non critique)"], ["128", "128 (critique)"]], (v) => { record.flag = Number(v); })),
    ])];
  }
  return [];
}

function renderRecordList() {
  el.recordList.innerHTML = "";
  state.records.forEach((record, index) => {
    const title = record.name
      ? `${record.type} · ${record.name}`
      : `Enregistrement #${index + 1}`;

    const card = entryCard(
      title,
      () => {
        state.records.splice(index, 1);
        renderRecordList();
      },
      [
        grid([
          field("Type", selectInput(record.type, CONFIG.recordTypes.map((t) => [t, t]), (v) => {
            record.type = v;
            renderRecordList();
          })),
          field("Nom", textInput(record.name, "@ ou www", (v) => { record.name = v; }, { mono: true })),
        ]),
        field("Valeur", textInput(record.value, "203.0.113.10", (v) => { record.value = v; }, { mono: true })),
        ...typeSpecificFields(record),
      ]
    );
    el.recordList.appendChild(card);
  });

  if (!state.records.length) {
    const empty = document.createElement("p");
    empty.className = "field-hint";
    empty.textContent = "Aucun enregistrement pour l'instant : ajoutes-en un ci-dessous.";
    el.recordList.appendChild(empty);
  }
}

function collectPayload() {
  const records = state.records
    .filter((r) => r.name.trim() && r.value.trim())
    .map((r) => {
      const record = { type: r.type, name: r.name.trim(), value: r.value.trim() };
      if (r.type === "MX") record.priority = Number(r.priority) || 0;
      if (r.type === "SRV") {
        record.priority = Number(r.priority) || 0;
        record.weight = Number(r.weight) || 0;
        record.port = Number(r.port) || 0;
      }
      if (r.type === "CAA") {
        record.flag = Number(r.flag) || 0;
        record.tag = r.tag;
      }
      return record;
    });

  return {
    preset: "custom",
    engine: state.engine,
    domain: el.domain.value.trim(),
    ttl: Number(el.ttl.value) || 3600,
    nameservers: el.nameservers.value.split(",").map((v) => v.trim()).filter(Boolean),
    soa: {
      primary_ns: el.soaPrimaryNs.value.trim(),
      admin_email: el.soaAdminEmail.value.trim(),
      refresh: Number(el.soaRefresh.value) || 3600,
      retry: Number(el.soaRetry.value) || 900,
      expire: Number(el.soaExpire.value) || 1209600,
      minimum: Number(el.ttl.value) || 3600,
    },
    records,
  };
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
    const res = await fetch("/dns/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showError((data.error || "Erreur lors de la génération.").split("; ").join("\n"));
      return;
    }

    state.lastFile = (data.files || [])[0] || null;
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
      if (/^\s*[;#]/.test(line)) return `<span class="conf-comment">${line}</span>`;
      if (/^\$(ORIGIN|TTL)/.test(line)) return `<span class="conf-block">${line}</span>`;
      const match = line.match(/^(\s*"?[\w.@*_-]*"?\s*)(IN)(\s+)([A-Z]+)(\s)/);
      if (match) {
        const [, name, inKw, sp1, type, sp2] = match;
        const rest = line.slice(match[0].length);
        return `${name}<span class="conf-key">${inKw}</span>${sp1}<span class="conf-key">${type}</span>${sp2}${rest}`;
      }
      return line;
    })
    .join("\n");
}

function renderResult() {
  el.resultBox.innerHTML = "";
  if (!state.lastFile) return;
  const pre = document.createElement("pre");
  pre.innerHTML = highlightContent(state.lastFile.content);
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
  state.lastFile = null;
  if (el.applyNode) el.applyNode.classList.remove("active");
}

// ----------------------------------------------------------------------------
// Actions resultat
// ----------------------------------------------------------------------------
async function handleCopy() {
  if (!state.lastFile) return;
  try {
    await navigator.clipboard.writeText(state.lastFile.content);
    el.copyBtn.textContent = "Copié !";
    setTimeout(() => (el.copyBtn.textContent = "Copier"), 1500);
  } catch (err) {
    showError("Impossible de copier automatiquement, sélectionne le texte manuellement.");
  }
}

function handleDownload() {
  if (!state.lastFile) return;
  const blob = new Blob([state.lastFile.content], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = state.lastFile.filename.split("/").pop();
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
el.engineSwitch.querySelectorAll(".engine-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    setEngine(btn.dataset.engine);
    resetResultBox();
  });
});

el.addRecordBtn.addEventListener("click", () => {
  state.records.push({ type: "A", name: "", value: "", priority: "", weight: "", port: "", flag: 0, tag: "issue" });
  renderRecordList();
});

el.generateBtn.addEventListener("click", handleGenerate);
el.resetBtn.addEventListener("click", () => {
  resetResultBox();
  clearError();
  setEngine("bind");
  applyPreset("site-statique");
});
el.copyBtn.addEventListener("click", handleCopy);
el.downloadBtn.addEventListener("click", handleDownload);

renderPresetList();
applyPreset("site-statique");
