// ============================================================================
// script.js — module Kubernetes/Helm
// Bascule manifests/helm, onglets par fichier, generation, copie, zip.
// ============================================================================

const state = {
  mode: "manifests",
  files: {},          // {chemin: contenu} de la derniere generation
  activeFile: null,
  combined: null,     // YAML combine (mode manifests uniquement)
};

const el = {
  modeButtons: document.querySelectorAll(".provider-btn"),
  modeHint: document.getElementById("mode-hint"),
  nameInput: document.getElementById("name-input"),
  imageInput: document.getElementById("image-input"),
  replicasInput: document.getElementById("replicas-input"),
  containerPortInput: document.getElementById("container-port-input"),
  serviceTypeSelect: document.getElementById("service-type-select"),
  servicePortInput: document.getElementById("service-port-input"),
  namespaceInput: document.getElementById("namespace-input"),
  envInput: document.getElementById("env-input"),
  probePathInput: document.getElementById("probe-path-input"),
  ingressCheckbox: document.getElementById("ingress-checkbox"),
  ingressFields: document.getElementById("ingress-fields"),
  ingressHostInput: document.getElementById("ingress-host-input"),
  ingressPathInput: document.getElementById("ingress-path-input"),
  ingressClassInput: document.getElementById("ingress-class-input"),
  tlsCheckbox: document.getElementById("tls-checkbox"),
  generateBtn: document.getElementById("generate-btn"),
  resetBtn: document.getElementById("reset-btn"),
  errorMsg: document.getElementById("error-msg"),
  warningMsg: document.getElementById("warning-msg"),
  fileTabs: document.getElementById("file-tabs"),
  resultLabel: document.getElementById("result-label"),
  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),
  ingressNode: document.getElementById("ingress-node"),
  ingressConnector: document.getElementById("ingress-connector"),
  tbApp: document.getElementById("tb-app"),
  tbMode: document.getElementById("tb-mode"),
  tbObjects: document.getElementById("tb-objects"),
};

// ----------------------------------------------------------------------------
// Mode manifests / helm
// ----------------------------------------------------------------------------
function setMode(mode) {
  state.mode = mode;
  el.modeButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
  el.modeHint.innerHTML =
    mode === "helm"
      ? "Squelette de chart complet : <code>helm install mon-app ./mon-app</code>."
      : "Fichiers YAML directement applicables avec <code>kubectl apply -f</code>.";
  el.tbMode.textContent = mode === "helm" ? "Chart Helm" : "Manifests";
}

el.modeButtons.forEach((btn) => {
  btn.addEventListener("click", () => setMode(btn.dataset.mode));
});

// ----------------------------------------------------------------------------
// Ingress : affichage conditionnel + schema
// ----------------------------------------------------------------------------
function syncIngressUI() {
  const enabled = el.ingressCheckbox.checked;
  el.ingressFields.hidden = !enabled;
  el.ingressNode.classList.toggle("active", enabled);
  el.ingressConnector.classList.toggle("flowing", enabled);
}
el.ingressCheckbox.addEventListener("change", syncIngressUI);

// ----------------------------------------------------------------------------
// Construction du payload
// ----------------------------------------------------------------------------
function parseEnvLines(text) {
  const env = {};
  const invalid = [];
  text.split("\n").forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const idx = trimmed.indexOf("=");
    if (idx <= 0) {
      invalid.push(trimmed);
      return;
    }
    env[trimmed.slice(0, idx).trim()] = trimmed.slice(idx + 1);
  });
  return { env, invalid };
}

function buildPayload() {
  const { env, invalid } = parseEnvLines(el.envInput.value);
  if (invalid.length) {
    return { error: `Variable(s) d'environnement invalide(s) : ${invalid.join(", ")} — format attendu CLE=VALEUR.` };
  }

  const payload = {
    mode: state.mode,
    name: el.nameInput.value.trim(),
    image: el.imageInput.value.trim(),
    replicas: parseInt(el.replicasInput.value, 10) || 2,
    container_port: parseInt(el.containerPortInput.value, 10) || 8080,
    service_type: el.serviceTypeSelect.value,
    service_port: parseInt(el.servicePortInput.value, 10) || 80,
    namespace: el.namespaceInput.value.trim() || null,
    env: env,
    probe_path: el.probePathInput.value.trim() || null,
  };

  if (el.ingressCheckbox.checked) {
    payload.ingress = {
      host: el.ingressHostInput.value.trim(),
      path: el.ingressPathInput.value.trim() || "/",
      class: el.ingressClassInput.value.trim(),
      tls: el.tlsCheckbox.checked,
    };
  }

  return { payload };
}

// ----------------------------------------------------------------------------
// Generation
// ----------------------------------------------------------------------------
async function handleGenerate() {
  clearMessages();

  const { payload, error } = buildPayload();
  if (error) {
    showError(error);
    return;
  }

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "…";

  try {
    const res = await fetch("/k8s/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Erreur lors de la génération.");
      return;
    }

    state.files = data.files;
    state.combined = data.combined;
    renderTabs();

    if (data.warnings && data.warnings.length) {
      el.warningMsg.textContent = "⚠ " + data.warnings.join(" ");
    }

    updateTitleBlock();
    el.generateBtn.textContent = "✓ Généré";
    setTimeout(() => (el.generateBtn.textContent = "GÉNÉRER →"), 1200);
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  } finally {
    el.generateBtn.disabled = false;
    if (el.generateBtn.textContent === "…") el.generateBtn.textContent = "GÉNÉRER →";
  }
}

// ----------------------------------------------------------------------------
// Onglets fichiers + rendu
// ----------------------------------------------------------------------------
function renderTabs() {
  const names = Object.keys(state.files).sort();
  el.fileTabs.innerHTML = "";
  el.fileTabs.hidden = names.length === 0;

  names.forEach((name) => {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "btn btn-ghost file-tab";
    tab.style.padding = "6px 12px";
    tab.style.fontSize = "12px";
    tab.textContent = name;
    tab.addEventListener("click", () => showFile(name));
    el.fileTabs.appendChild(tab);
  });

  if (names.length) showFile(names[0]);
}

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function highlightYaml(text) {
  return escapeHtml(text)
    .split("\n")
    .map((line) => {
      if (/^\s*#/.test(line)) return `<span class="yaml-comment">${line}</span>`;
      const m = line.match(/^(\s*)([A-Za-z_][\w.\/-]*)(:)(\s|$)/);
      if (m) {
        return `${m[1]}<span class="yaml-key">${m[2]}</span>${m[3]}${line.slice(m[1].length + m[2].length + m[3].length)}`;
      }
      return line;
    })
    .join("\n");
}

function showFile(name) {
  state.activeFile = name;
  document.querySelectorAll(".file-tab").forEach((t) => {
    t.style.fontWeight = t.textContent === name ? "700" : "400";
    t.style.borderColor = t.textContent === name ? "var(--primary)" : "";
  });
  el.resultLabel.textContent = name;
  el.resultBox.innerHTML = "";
  const pre = document.createElement("pre");
  pre.innerHTML = highlightYaml(state.files[name]);
  el.resultBox.appendChild(pre);
  el.resultActions.hidden = false;
}

function updateTitleBlock() {
  el.tbApp.textContent = el.nameInput.value.trim() || "—";
  el.tbObjects.textContent = Object.keys(state.files).length || "—";
}

// ----------------------------------------------------------------------------
// Actions : copier / telecharger zip
// ----------------------------------------------------------------------------
async function handleCopy() {
  // En mode manifests on copie le YAML combine (pret pour kubectl apply),
  // en mode helm on copie le fichier actuellement affiche.
  const text = state.mode === "manifests" && state.combined
    ? state.combined
    : state.files[state.activeFile] || "";
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    el.copyBtn.textContent = "Copié !";
    setTimeout(() => (el.copyBtn.textContent = "Copier"), 1500);
  } catch (err) {
    showError("Impossible de copier automatiquement, sélectionne le texte manuellement.");
  }
}

async function handleDownload() {
  const { payload, error } = buildPayload();
  if (error) {
    showError(error);
    return;
  }
  el.downloadBtn.disabled = true;
  try {
    const res = await fetch("/k8s/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      showError(data.error || "Erreur lors du téléchargement.");
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = state.mode === "helm"
      ? `${payload.name}-chart.zip`
      : `${payload.name}-manifests.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  } finally {
    el.downloadBtn.disabled = false;
  }
}

// ----------------------------------------------------------------------------
// Reset + messages
// ----------------------------------------------------------------------------
function handleReset() {
  el.nameInput.value = "";
  el.imageInput.value = "";
  el.replicasInput.value = "2";
  el.containerPortInput.value = "8080";
  el.serviceTypeSelect.value = "ClusterIP";
  el.servicePortInput.value = "80";
  el.namespaceInput.value = "";
  el.envInput.value = "";
  el.probePathInput.value = "";
  el.ingressCheckbox.checked = false;
  el.ingressHostInput.value = "";
  el.ingressPathInput.value = "/";
  el.ingressClassInput.value = "";
  el.tlsCheckbox.checked = false;
  syncIngressUI();
  state.files = {};
  state.combined = null;
  state.activeFile = null;
  el.fileTabs.hidden = true;
  el.fileTabs.innerHTML = "";
  el.resultLabel.textContent = "Résultat";
  el.resultBox.innerHTML = "";
  const p = document.createElement("p");
  p.className = "result-placeholder";
  p.textContent = "Les fichiers générés apparaîtront ici.";
  el.resultBox.appendChild(p);
  el.resultActions.hidden = true;
  clearMessages();
  el.tbApp.textContent = "—";
  el.tbObjects.textContent = "—";
}

function showError(message) {
  el.errorMsg.textContent = message;
  el.errorMsg.classList.add("visible");
}

function clearMessages() {
  el.errorMsg.textContent = "";
  el.errorMsg.classList.remove("visible");
  el.warningMsg.textContent = "";
}

// ----------------------------------------------------------------------------
// Evenements + init
// ----------------------------------------------------------------------------
el.generateBtn.addEventListener("click", handleGenerate);
el.resetBtn.addEventListener("click", handleReset);
el.copyBtn.addEventListener("click", handleCopy);
el.downloadBtn.addEventListener("click", handleDownload);

setMode("manifests");
syncIngressUI();
