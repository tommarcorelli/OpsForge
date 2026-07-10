// ============================================================================
// script.js — module Dockerfile
// Detection, selection du langage, generation, actions (copier/telecharger).
// ============================================================================

const CONFIG = window.OPSFORGE_DOCKERFILE || { languages: [], defaultPorts: {}, defaultEntrypoints: {} };

const LANGUAGE_LABELS = {
  python: "Python",
  node: "Node.js",
  go: "Go",
  rust: "Rust",
  java: "Java",
  php: "PHP",
  ruby: "Ruby",
  dotnet: ".NET",
};

const PACKAGE_MANAGERS_BY_LANGUAGE = {
  python: ["pip", "poetry", "pipenv"],
  node: ["npm", "yarn", "pnpm"],
  go: ["go modules"],
  rust: ["cargo"],
  java: ["maven", "gradle"],
  php: ["composer"],
  ruby: ["bundler"],
  dotnet: ["dotnet"],
};

// Langages pour lesquels le champ "point d'entree" n'est pas utilise
// (java copie le .jar par wildcard, php sert via Apache).
const NO_ENTRYPOINT_LANGUAGES = new Set(["java", "php"]);

const state = {
  selectedLanguage: null,
  detectedStacks: null,
  lastDockerfile: "",
  lastDockerignore: "",
  portTouched: false,
  entrypointTouched: false,
};

const el = {
  projectPath: document.getElementById("project-path"),
  detectBtn: document.getElementById("detect-btn"),
  detectHint: document.getElementById("detect-hint"),
  languageList: document.getElementById("language-list"),
  versionInput: document.getElementById("version-input"),
  packageManagerGroup: document.getElementById("package-manager-group"),
  packageManagerSelect: document.getElementById("package-manager-select"),
  portInput: document.getElementById("port-input"),
  entrypointGroup: document.getElementById("entrypoint-group"),
  entrypointInput: document.getElementById("entrypoint-input"),
  entrypointHint: document.getElementById("entrypoint-hint"),
  workdirInput: document.getElementById("workdir-input"),
  dockerignoreCheckbox: document.getElementById("dockerignore-checkbox"),
  generateBtn: document.getElementById("generate-btn"),
  resetBtn: document.getElementById("reset-btn"),
  errorMsg: document.getElementById("error-msg"),
  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),
  dockerignoreBox: document.getElementById("dockerignore-box"),
  dockerignoreText: document.getElementById("dockerignore-text"),
  copyDockerignoreBtn: document.getElementById("copy-dockerignore-btn"),
  tbProject: document.getElementById("tb-project"),
  tbLanguage: document.getElementById("tb-language"),
  tbPort: document.getElementById("tb-port"),
};

// ----------------------------------------------------------------------------
// Liste des langages (selection unique, façon radio)
// ----------------------------------------------------------------------------
function renderLanguageList(detectedByLanguage) {
  el.languageList.innerHTML = "";
  detectedByLanguage = detectedByLanguage || {};

  CONFIG.languages.forEach((lang) => {
    const detected = detectedByLanguage[lang];

    const item = document.createElement("label");
    item.className = "stack-item" + (detected ? " detected" : "");
    item.style.cursor = "pointer";

    const left = document.createElement("span");
    left.style.display = "flex";
    left.style.alignItems = "center";
    left.style.gap = "10px";

    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "language";
    radio.value = lang;
    radio.checked = state.selectedLanguage === lang;
    radio.addEventListener("change", () => selectLanguage(lang, detected));

    const labelText = document.createElement("span");
    labelText.textContent = LANGUAGE_LABELS[lang] || lang;

    left.appendChild(radio);
    left.appendChild(labelText);

    const meta = document.createElement("span");
    meta.className = "stack-meta";
    meta.textContent = detected
      ? `${detected.package_manager} · v${detected.version || "?"}`
      : "";

    item.appendChild(left);
    item.appendChild(meta);
    el.languageList.appendChild(item);
  });
}

function selectLanguage(lang, detectedStack) {
  state.selectedLanguage = lang;
  state.portTouched = false;
  state.entrypointTouched = false;

  // Package manager : liste des options possibles pour ce langage
  const managers = PACKAGE_MANAGERS_BY_LANGUAGE[lang] || [];
  el.packageManagerSelect.innerHTML = "";
  managers.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m;
    opt.textContent = m;
    el.packageManagerSelect.appendChild(opt);
  });
  if (detectedStack && managers.includes(detectedStack.package_manager)) {
    el.packageManagerSelect.value = detectedStack.package_manager;
  }
  el.packageManagerGroup.hidden = managers.length <= 1;

  // Version
  el.versionInput.value = (detectedStack && detectedStack.version) || "";
  el.versionInput.placeholder = "valeur par défaut du langage si vide";

  // Port
  el.portInput.value = CONFIG.defaultPorts[lang] || "";

  // Entrypoint
  const noEntrypoint = NO_ENTRYPOINT_LANGUAGES.has(lang);
  el.entrypointGroup.hidden = noEntrypoint;
  if (!noEntrypoint) {
    el.entrypointInput.value = CONFIG.defaultEntrypoints[lang] || "";
    el.entrypointHint.textContent =
      lang === "rust"
        ? "Nom du binaire compilé (champ [package].name dans Cargo.toml)."
        : lang === "dotnet"
        ? "Nom de la DLL principale générée par dotnet publish (ex : MonProjet.dll)."
        : "Fichier de démarrage de ton application.";
  }

  // Coche visuellement l'item correspondant
  document.querySelectorAll("#language-list input[type=radio]").forEach((r) => {
    r.checked = r.value === lang;
  });
}

// ----------------------------------------------------------------------------
// Detection auto
// ----------------------------------------------------------------------------
async function handleDetect() {
  const path = el.projectPath.value.trim();
  clearError();

  if (!path) {
    el.detectHint.textContent = "Renseigne un chemin avant de lancer la détection.";
    state.detectedStacks = null;
    renderLanguageList();
    return;
  }

  el.detectBtn.disabled = true;
  el.detectBtn.textContent = "…";

  try {
    const res = await fetch("/dockerfile/api/detect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await res.json();

    if (!res.ok) {
      state.detectedStacks = null;
      el.detectHint.textContent = data.error || "Aucun stack détecté.";
      renderLanguageList();
      return;
    }

    state.detectedStacks = data.stacks;
    const detectedByLanguage = {};
    data.stacks.forEach((s) => (detectedByLanguage[s.language] = s));
    renderLanguageList(detectedByLanguage);

    el.detectHint.textContent =
      data.stacks.length > 1
        ? `${data.stacks.length} stacks détectées — choisis celle à conteneuriser.`
        : "Stack détectée avec succès.";

    // Auto-selectionne si une seule stack detectee
    if (data.stacks.length === 1) {
      selectLanguage(data.stacks[0].language, data.stacks[0]);
    }
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  } finally {
    el.detectBtn.disabled = false;
    el.detectBtn.textContent = "Détecter";
  }
}

// ----------------------------------------------------------------------------
// Generation
// ----------------------------------------------------------------------------
async function handleGenerate() {
  clearError();

  if (!state.selectedLanguage) {
    showError("Choisis un langage (détection auto ou sélection manuelle).");
    return;
  }

  const payload = {
    language: state.selectedLanguage,
    version: el.versionInput.value.trim() || null,
    package_manager: el.packageManagerSelect.value || "",
    port: el.portInput.value ? parseInt(el.portInput.value, 10) : null,
    entrypoint: el.entrypointInput.value.trim() || null,
    workdir: el.workdirInput.value.trim() || "/app",
  };

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "…";

  try {
    const res = await fetch("/dockerfile/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Erreur lors de la génération.");
      return;
    }

    renderResult(data.dockerfile);

    if (el.dockerignoreCheckbox.checked && data.dockerignore) {
      state.lastDockerignore = data.dockerignore;
      el.dockerignoreText.textContent = data.dockerignore;
      el.dockerignoreBox.hidden = false;
    } else {
      state.lastDockerignore = "";
      el.dockerignoreBox.hidden = true;
    }

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

function highlightDockerfile(text) {
  const escaped = escapeHtml(text);
  const lines = escaped.split("\n");

  const highlighted = lines.map((line) => {
    if (/^\s*#/.test(line)) {
      return `<span class="yaml-comment">${line}</span>`;
    }
    const instrMatch = line.match(
      /^(FROM|WORKDIR|COPY|RUN|ENV|EXPOSE|CMD|ENTRYPOINT|USER|ARG|LABEL)(\s|$)/
    );
    if (instrMatch) {
      return `<span class="yaml-key">${instrMatch[1]}</span>${line.slice(instrMatch[1].length)}`;
    }
    return line;
  });

  return highlighted.join("\n");
}

function renderResult(dockerfileText) {
  state.lastDockerfile = dockerfileText;
  el.resultBox.innerHTML = "";
  const pre = document.createElement("pre");
  pre.innerHTML = highlightDockerfile(dockerfileText);
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
  el.dockerignoreBox.hidden = true;
  state.lastDockerfile = "";
  state.lastDockerignore = "";
}

function updateTitleBlock() {
  const path = el.projectPath.value.trim();
  el.tbProject.textContent = path || "(sélection manuelle)";
  el.tbLanguage.textContent = LANGUAGE_LABELS[state.selectedLanguage] || "—";
  el.tbPort.textContent = el.portInput.value || "—";
}

// ----------------------------------------------------------------------------
// Actions resultat : copier / telecharger
// ----------------------------------------------------------------------------
async function handleCopy() {
  if (!state.lastDockerfile) return;
  try {
    await navigator.clipboard.writeText(state.lastDockerfile);
    el.copyBtn.textContent = "Copié !";
    setTimeout(() => (el.copyBtn.textContent = "Copier"), 1500);
  } catch (err) {
    showError("Impossible de copier automatiquement, sélectionne le texte manuellement.");
  }
}

async function handleCopyDockerignore() {
  if (!state.lastDockerignore) return;
  try {
    await navigator.clipboard.writeText(state.lastDockerignore);
    el.copyDockerignoreBtn.textContent = "Copié !";
    setTimeout(() => (el.copyDockerignoreBtn.textContent = "Copier le .dockerignore"), 1500);
  } catch (err) {
    showError("Impossible de copier automatiquement, sélectionne le texte manuellement.");
  }
}

function handleDownload() {
  if (!state.lastDockerfile) return;
  const blob = new Blob([state.lastDockerfile], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "Dockerfile";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// ----------------------------------------------------------------------------
// Reset
// ----------------------------------------------------------------------------
function handleReset() {
  el.projectPath.value = "";
  state.detectedStacks = null;
  state.selectedLanguage = null;
  el.detectHint.textContent = "Laisse vide pour choisir un langage manuellement ci-dessous.";
  el.versionInput.value = "";
  el.portInput.value = "";
  el.entrypointInput.value = "";
  el.workdirInput.value = "/app";
  el.dockerignoreCheckbox.checked = true;
  renderLanguageList();
  resetResultBox();
  clearError();
  el.tbProject.textContent = "—";
  el.tbLanguage.textContent = "—";
  el.tbPort.textContent = "—";
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
el.detectBtn.addEventListener("click", handleDetect);
el.generateBtn.addEventListener("click", handleGenerate);
el.resetBtn.addEventListener("click", handleReset);
el.copyBtn.addEventListener("click", handleCopy);
el.downloadBtn.addEventListener("click", handleDownload);
el.copyDockerignoreBtn.addEventListener("click", handleCopyDockerignore);
el.portInput.addEventListener("input", () => (state.portTouched = true));
el.entrypointInput.addEventListener("input", () => (state.entrypointTouched = true));

renderLanguageList();
