// ============================================================================
// modules/monitoring/static/script.js
// Logique du module Monitoring : bascule prometheus/alerts/grafana, builders
// dynamiques (jobs, datasources), presets, generation, copier/telecharger.
// ============================================================================

const CONFIG = window.OPSFORGE_MONITORING || {
  modes: [],
  datasourceTypes: [],
  rules: [],
  presets: [],
};

const FILENAMES = {
  prometheus: "prometheus.yml",
  alerts: "alert.rules.yml",
  grafana: "datasource.yml",
};

const MODE_LABELS = {
  prometheus: "Prometheus",
  alerts: "Alertes",
  grafana: "Grafana",
};

const state = {
  mode: "prometheus",
  jobs: [{ job_name: "node", targets: "localhost:9100" }],
  datasources: [
    { name: "Prometheus", type: "prometheus", url: "http://localhost:9090", is_default: true },
  ],
  lastCombined: "",
  lastFiles: [],
  lastFilename: "prometheus.yml",
};

const el = {
  presetList: document.getElementById("preset-list"),
  modeSwitch: document.getElementById("mode-switch"),

  fieldsPrometheus: document.getElementById("fields-prometheus"),
  scrapeIntervalInput: document.getElementById("scrape-interval-input"),
  evalIntervalInput: document.getElementById("eval-interval-input"),
  jobsList: document.getElementById("jobs-list"),
  addJobBtn: document.getElementById("add-job-btn"),
  alertmanagerCheckbox: document.getElementById("alertmanager-checkbox"),
  rulefilesCheckbox: document.getElementById("rulefiles-checkbox"),

  fieldsAlerts: document.getElementById("fields-alerts"),
  groupNameInput: document.getElementById("group-name-input"),
  rulesList: document.getElementById("rules-list"),
  cpuThresholdInput: document.getElementById("cpu-threshold-input"),
  memThresholdInput: document.getElementById("mem-threshold-input"),
  diskThresholdInput: document.getElementById("disk-threshold-input"),

  fieldsGrafana: document.getElementById("fields-grafana"),
  datasourcesList: document.getElementById("datasources-list"),
  addDatasourceBtn: document.getElementById("add-datasource-btn"),

  generateBtn: document.getElementById("generate-btn"),
  resetBtn: document.getElementById("reset-btn"),
  errorMsg: document.getElementById("error-msg"),

  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),

  alertNode: document.querySelector('.node[data-stage="alert"]'),

  tbMode: document.getElementById("tb-mode"),
  tbFile: document.getElementById("tb-file"),
  tbCount: document.getElementById("tb-count"),
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
    const res = await fetch(`/monitoring/api/preset/${encodeURIComponent(name)}`);
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
  setMode(cfg.mode || "prometheus");

  // Prometheus
  el.scrapeIntervalInput.value = cfg.scrape_interval || "15s";
  el.evalIntervalInput.value = cfg.evaluation_interval || "15s";
  el.alertmanagerCheckbox.checked = !!cfg.alertmanager;
  el.rulefilesCheckbox.checked = !!cfg.rule_files;
  if (Array.isArray(cfg.jobs)) {
    state.jobs = cfg.jobs.map((j) => ({
      job_name: j.job_name || "",
      targets: (j.targets || []).join(", "),
    }));
    renderJobsList();
  }

  // Alerts
  el.groupNameInput.value = cfg.group_name || "";
  el.cpuThresholdInput.value = cfg.cpu_threshold != null ? cfg.cpu_threshold : 85;
  el.memThresholdInput.value = cfg.memory_threshold != null ? cfg.memory_threshold : 85;
  el.diskThresholdInput.value = cfg.disk_threshold != null ? cfg.disk_threshold : 85;
  const selected = new Set(cfg.rules || []);
  el.rulesList.querySelectorAll(".rule-check").forEach((cb) => {
    cb.checked = selected.has(cb.dataset.rule);
  });

  // Grafana
  if (Array.isArray(cfg.datasources)) {
    state.datasources = cfg.datasources.map((d) => ({
      name: d.name || "",
      type: d.type || "prometheus",
      url: d.url || "",
      is_default: !!d.is_default,
    }));
    renderDatasourcesList();
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

  el.fieldsPrometheus.hidden = mode !== "prometheus";
  el.fieldsAlerts.hidden = mode !== "alerts";
  el.fieldsGrafana.hidden = mode !== "grafana";

  updateTitleBlock();
}

el.modeSwitch.querySelectorAll(".provider-btn").forEach((btn) => {
  btn.addEventListener("click", () => setMode(btn.dataset.mode));
});

// ----------------------------------------------------------------------------
// Jobs de scrape (builder dynamique)
// ----------------------------------------------------------------------------
function renderJobsList() {
  el.jobsList.innerHTML = "";
  state.jobs.forEach((job, index) => {
    const row = document.createElement("div");
    row.className = "builder-row";

    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.placeholder = "nom du job (ex : node)";
    nameInput.className = "builder-key";
    nameInput.value = job.job_name || "";
    nameInput.addEventListener("input", () => (state.jobs[index].job_name = nameInput.value));

    const targetsInput = document.createElement("input");
    targetsInput.type = "text";
    targetsInput.placeholder = "cibles : localhost:9100, ...";
    targetsInput.value = job.targets || "";
    targetsInput.addEventListener("input", () => (state.jobs[index].targets = targetsInput.value));

    const removeBtn = makeRemoveBtn(() => {
      state.jobs.splice(index, 1);
      renderJobsList();
      updateTitleBlock();
    });

    row.appendChild(nameInput);
    row.appendChild(targetsInput);
    row.appendChild(removeBtn);
    el.jobsList.appendChild(row);
  });
}

el.addJobBtn.addEventListener("click", () => {
  state.jobs.push({ job_name: "", targets: "" });
  renderJobsList();
  updateTitleBlock();
});

// ----------------------------------------------------------------------------
// Datasources Grafana (builder dynamique)
// ----------------------------------------------------------------------------
function renderDatasourcesList() {
  el.datasourcesList.innerHTML = "";
  state.datasources.forEach((ds, index) => {
    const row = document.createElement("div");
    row.className = "builder-row ds-row";

    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.placeholder = "nom (ex : Prometheus)";
    nameInput.value = ds.name || "";
    nameInput.addEventListener("input", () => (state.datasources[index].name = nameInput.value));

    const typeSelect = document.createElement("select");
    typeSelect.className = "ds-type";
    CONFIG.datasourceTypes.forEach((t) => {
      const opt = document.createElement("option");
      opt.value = t;
      opt.textContent = t;
      typeSelect.appendChild(opt);
    });
    typeSelect.value = ds.type || "prometheus";
    typeSelect.addEventListener("change", () => (state.datasources[index].type = typeSelect.value));

    const urlInput = document.createElement("input");
    urlInput.type = "text";
    urlInput.placeholder = "http://localhost:9090";
    urlInput.value = ds.url || "";
    urlInput.addEventListener("input", () => (state.datasources[index].url = urlInput.value));

    const defaultLabel = document.createElement("label");
    defaultLabel.className = "ds-default";
    defaultLabel.title = "Datasource par défaut";
    const defaultInput = document.createElement("input");
    defaultInput.type = "checkbox";
    defaultInput.checked = !!ds.is_default;
    defaultInput.addEventListener("change", () => {
      // Une seule datasource par defaut a la fois.
      state.datasources.forEach((d, i) => (d.is_default = i === index ? defaultInput.checked : false));
      renderDatasourcesList();
    });
    defaultLabel.appendChild(defaultInput);
    defaultLabel.appendChild(document.createTextNode("défaut"));

    const removeBtn = makeRemoveBtn(() => {
      state.datasources.splice(index, 1);
      renderDatasourcesList();
      updateTitleBlock();
    });

    row.appendChild(nameInput);
    row.appendChild(typeSelect);
    row.appendChild(urlInput);
    row.appendChild(defaultLabel);
    row.appendChild(removeBtn);
    el.datasourcesList.appendChild(row);
  });
}

el.addDatasourceBtn.addEventListener("click", () => {
  state.datasources.push({ name: "", type: "prometheus", url: "", is_default: false });
  renderDatasourcesList();
  updateTitleBlock();
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
// Construction du payload + generation
// ----------------------------------------------------------------------------
function splitTargets(raw) {
  return (raw || "")
    .split(/[\s,]+/)
    .map((t) => t.trim())
    .filter(Boolean);
}

function checkedRules() {
  return Array.from(el.rulesList.querySelectorAll(".rule-check"))
    .filter((cb) => cb.checked)
    .map((cb) => cb.dataset.rule);
}

function buildPayload() {
  if (state.mode === "prometheus") {
    return {
      mode: "prometheus",
      scrape_interval: el.scrapeIntervalInput.value.trim() || "15s",
      evaluation_interval: el.evalIntervalInput.value.trim() || "15s",
      alertmanager: el.alertmanagerCheckbox.checked,
      rule_files: el.rulefilesCheckbox.checked,
      jobs: state.jobs
        .filter((j) => (j.job_name || "").trim())
        .map((j) => ({ job_name: j.job_name.trim(), targets: splitTargets(j.targets) })),
    };
  }
  if (state.mode === "alerts") {
    return {
      mode: "alerts",
      group_name: el.groupNameInput.value.trim() || "opsforge-alerts",
      rules: checkedRules(),
      cpu_threshold: parseInt(el.cpuThresholdInput.value, 10) || 85,
      memory_threshold: parseInt(el.memThresholdInput.value, 10) || 85,
      disk_threshold: parseInt(el.diskThresholdInput.value, 10) || 85,
    };
  }
  return {
    mode: "grafana",
    datasources: state.datasources
      .filter((d) => (d.name || "").trim())
      .map((d) => ({
        name: d.name.trim(),
        type: d.type,
        url: (d.url || "").trim(),
        is_default: !!d.is_default,
      })),
  };
}

function frontValidate() {
  if (state.mode === "prometheus" && !state.jobs.some((j) => (j.job_name || "").trim())) {
    return "Ajoute au moins un job de scrape.";
  }
  if (state.mode === "alerts" && checkedRules().length === 0) {
    return "Sélectionne au moins une règle d'alerte.";
  }
  if (state.mode === "grafana" && !state.datasources.some((d) => (d.name || "").trim())) {
    return "Ajoute au moins une datasource.";
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
    const res = await fetch("/monitoring/api/generate", {
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
    state.lastFilename = data.filename || FILENAMES[state.mode];
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
  if (el.alertNode) el.alertNode.classList.add("active");
  setTimeout(() => {
    el.generateBtn.textContent = "GÉNÉRER →";
  }, 1200);
}

// ----------------------------------------------------------------------------
// Rendu resultat (coloration YAML)
// ----------------------------------------------------------------------------
function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlightYaml(text) {
  const escaped = escapeHtml(text);
  return escaped
    .split("\n")
    .map((line) => {
      if (/^\s*#/.test(line)) {
        return `<span class="yaml-comment">${line}</span>`;
      }
      const kv = line.match(/^(\s*(?:-\s*)?)([A-Za-z_][A-Za-z0-9_]*)(:)(.*)$/);
      if (kv) {
        return `${kv[1]}<span class="yaml-key">${kv[2]}</span>${kv[3]}${kv[4]}`;
      }
      return line;
    })
    .join("\n");
}

function renderResult(combined) {
  state.lastCombined = combined;
  el.resultBox.innerHTML = "";
  const pre = document.createElement("pre");
  pre.innerHTML = highlightYaml(combined);
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
  state.lastCombined = "";
  state.lastFiles = [];
  if (el.alertNode) el.alertNode.classList.remove("active");
}

function currentCount() {
  if (state.mode === "prometheus") {
    return `${state.jobs.filter((j) => (j.job_name || "").trim()).length} job(s)`;
  }
  if (state.mode === "alerts") {
    return `${checkedRules().length} règle(s)`;
  }
  return `${state.datasources.filter((d) => (d.name || "").trim()).length} source(s)`;
}

function updateTitleBlock() {
  el.tbMode.textContent = MODE_LABELS[state.mode] || "—";
  el.tbFile.textContent = FILENAMES[state.mode] || "—";
  el.tbCount.textContent = currentCount();
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
  a.download = state.lastFilename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ----------------------------------------------------------------------------
// Reset
// ----------------------------------------------------------------------------
function handleReset() {
  setMode("prometheus");
  el.scrapeIntervalInput.value = "15s";
  el.evalIntervalInput.value = "15s";
  el.alertmanagerCheckbox.checked = false;
  el.rulefilesCheckbox.checked = false;
  el.groupNameInput.value = "";
  el.cpuThresholdInput.value = 85;
  el.memThresholdInput.value = 85;
  el.diskThresholdInput.value = 85;
  el.rulesList.querySelectorAll(".rule-check").forEach((cb) => (cb.checked = false));

  state.jobs = [{ job_name: "node", targets: "localhost:9100" }];
  state.datasources = [
    { name: "Prometheus", type: "prometheus", url: "http://localhost:9090", is_default: true },
  ];
  renderJobsList();
  renderDatasourcesList();

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
el.rulesList.addEventListener("change", updateTitleBlock);

renderPresetList();
renderJobsList();
renderDatasourcesList();
setMode("prometheus");
