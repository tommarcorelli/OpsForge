// ============================================================================
// script.js
// Logique cote client : detection, selection manuelle, generation, actions.
// ============================================================================

const SUPPORTED_LANGUAGES = ["python", "node", "go", "rust", "java", "php", "ruby", "dotnet"];

const state = {
  detectedStacks: null,   // resultat de /api/detect, ou null si pas encore lance
  manualLanguages: new Set(),
  lastYaml: "",
  provider: "github",
};

const el = {
  projectPath: document.getElementById("project-path"),
  detectBtn: document.getElementById("detect-btn"),
  detectHint: document.getElementById("detect-hint"),
  stackList: document.getElementById("stack-list"),
  branches: document.getElementById("branches"),
  generateBtn: document.getElementById("generate-btn"),
  errorMsg: document.getElementById("error-msg"),
  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),
  pipelineSchematic: document.getElementById("pipeline-schematic"),
  tbProject: document.getElementById("tb-project"),
  tbStacks: document.getElementById("tb-stacks"),
  tbJobs: document.getElementById("tb-jobs"),
  pagesDir: document.getElementById("pages-dir"),
  pagesBuildCmd: document.getElementById("pages-build-cmd"),
  dockerImage: document.getElementById("docker-image"),
  deployPath: document.getElementById("deploy-path"),
  serviceName: document.getElementById("service-name"),
  providerButtons: document.querySelectorAll(".provider-btn"),
  deployPagesCheckbox: document.getElementById("deploy-pages-checkbox"),
  deployPagesLabel: document.getElementById("deploy-pages-label"),
  pagesHint: document.getElementById("pages-hint"),
  dockerHint: document.getElementById("docker-hint"),
  sshHint: document.getElementById("ssh-hint"),
  resetBtn: document.getElementById("reset-btn"),
  matrixVersions: document.getElementById("matrix-versions"),
  scheduleCron: document.getElementById("schedule-cron"),
  s3Bucket: document.getElementById("s3-bucket"),
  awsRegion: document.getElementById("aws-region"),
  badgeRepo: document.getElementById("badge-repo"),
  badgeBox: document.getElementById("badge-box"),
  badgeText: document.getElementById("badge-text"),
  copyBadgeBtn: document.getElementById("copy-badge-btn"),
};

// ----------------------------------------------------------------------------
// Selecteur de provider (GitHub Actions / GitLab CI)
// ----------------------------------------------------------------------------
function switchProvider(provider) {
  state.provider = provider;

  el.providerButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.provider === provider);
  });

  if (provider === "gitlab") {
    el.deployPagesCheckbox.value = "gitlab_pages";
    el.deployPagesLabel.textContent = "GitLab Pages";
    el.pagesHint.textContent = "GitLab Pages nécessite une stack Node dans ta sélection ci-dessus.";
    el.dockerHint.textContent = "Nécessite les variables CI/CD GitLab : DOCKERHUB_USERNAME, DOCKERHUB_TOKEN";
    el.sshHint.textContent = "Nécessite les variables CI/CD GitLab : SSH_HOST, SSH_USER, SSH_PRIVATE_KEY";
  } else {
    el.deployPagesCheckbox.value = "github_pages";
    el.deployPagesLabel.textContent = "GitHub Pages";
    el.pagesHint.textContent = "GitHub Pages nécessite une stack Node dans ta sélection ci-dessus.";
    el.dockerHint.textContent = "Nécessite les secrets GitHub : DOCKERHUB_USERNAME, DOCKERHUB_TOKEN";
    el.sshHint.textContent = "Nécessite les secrets GitHub : SSH_HOST, SSH_USER, SSH_PRIVATE_KEY";
  }

  // Reinitialise le resultat affiche : un playbook GitHub n'a pas de sens
  // une fois qu'on a bascule sur GitLab, et vice versa.
  resetResultBox("Le fichier généré apparaîtra ici.");
}

// ----------------------------------------------------------------------------
// Theme clair/sombre : respecte prefers-color-scheme au premier chargement,
// puis mémorise le choix manuel de l'utilisateur dans localStorage.
// ----------------------------------------------------------------------------
const THEME_KEY = "cicd-generator-theme";
const themeToggleBtn = document.getElementById("theme-toggle");
const themeIcon = document.getElementById("theme-icon");

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  themeIcon.textContent = theme === "dark" ? "☀️" : "🌙";
}

function initTheme() {
  let saved = null;
  try {
    saved = localStorage.getItem(THEME_KEY);
  } catch (err) {
    // ignore
  }

  if (saved === "dark" || saved === "light") {
    applyTheme(saved);
    return;
  }

  const prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  applyTheme(prefersDark ? "dark" : "light");
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);
  try {
    localStorage.setItem(THEME_KEY, next);
  } catch (err) {
    // ignore
  }
}

themeToggleBtn.addEventListener("click", toggleTheme);
initTheme();

// ----------------------------------------------------------------------------
// PWA : bouton d'installation natif (via beforeinstallprompt)
// ----------------------------------------------------------------------------
let deferredInstallPrompt = null;
const installBtn = document.getElementById("install-btn");

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  deferredInstallPrompt = event;
  installBtn.hidden = false;
});

installBtn.addEventListener("click", async () => {
  if (!deferredInstallPrompt) return;
  deferredInstallPrompt.prompt();
  await deferredInstallPrompt.userChoice;
  deferredInstallPrompt = null;
  installBtn.hidden = true;
});

window.addEventListener("appinstalled", () => {
  installBtn.hidden = true;
});

// ----------------------------------------------------------------------------
// PWA : enregistrement du service worker
// ----------------------------------------------------------------------------
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch((err) => {
      console.warn("Service worker non enregistre :", err);
    });
  });
}

// ----------------------------------------------------------------------------
// Persistance locale des reglages (branches, docker image, etc.)
// Uniquement du confort : ce projet tourne en local sur la machine de
// l'utilisateur, localStorage y est donc tout a fait approprie ici
// (contrairement a un artifact Claude.ai qui ne le supporte pas).
// ----------------------------------------------------------------------------
const PREFS_KEY = "cicd-generator-prefs";

function savePrefs() {
  const prefs = {
    branches: el.branches.value,
    pagesDir: el.pagesDir.value,
    pagesBuildCmd: el.pagesBuildCmd.value,
    dockerImage: el.dockerImage.value,
    deployPath: el.deployPath.value,
    serviceName: el.serviceName.value,
    provider: state.provider,
  };
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch (err) {
    // Stockage plein ou indisponible : pas grave, c'est juste du confort.
  }
}

function loadPrefs() {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (!raw) return;
    const prefs = JSON.parse(raw);

    if (prefs.branches) el.branches.value = prefs.branches;
    if (prefs.pagesDir) el.pagesDir.value = prefs.pagesDir;
    if (prefs.pagesBuildCmd) el.pagesBuildCmd.value = prefs.pagesBuildCmd;
    if (prefs.dockerImage) el.dockerImage.value = prefs.dockerImage;
    if (prefs.deployPath) el.deployPath.value = prefs.deployPath;
    if (prefs.serviceName) el.serviceName.value = prefs.serviceName;
    if (prefs.provider) switchProvider(prefs.provider);
  } catch (err) {
    // JSON invalide ou stockage indisponible : on ignore silencieusement.
  }
}

// ----------------------------------------------------------------------------
// Rendu de la liste des stacks (manuelle par defaut, tant qu'aucune detection)
// ----------------------------------------------------------------------------
function renderManualStackPicker() {
  el.stackList.innerHTML = "";

  SUPPORTED_LANGUAGES.forEach((lang) => {
    const item = document.createElement("label");
    item.className = "stack-item";
    item.style.cursor = "pointer";

    const left = document.createElement("span");
    left.textContent = lang;

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = lang;
    checkbox.style.accentColor = "#C97C4B";
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) {
        state.manualLanguages.add(lang);
      } else {
        state.manualLanguages.delete(lang);
      }
    });

    item.appendChild(left);
    item.appendChild(checkbox);
    el.stackList.appendChild(item);
  });
}

function renderDetectedStacks(stacks) {
  el.stackList.innerHTML = "";

  stacks.forEach((stack) => {
    const item = document.createElement("div");
    item.className = "stack-item detected";

    const left = document.createElement("span");
    left.textContent = stack.language;

    const meta = document.createElement("span");
    meta.className = "stack-meta";
    meta.textContent = `${stack.package_manager} · v${stack.version || "?"}`;

    item.appendChild(left);
    item.appendChild(meta);
    el.stackList.appendChild(item);
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
    return;
  }

  el.detectBtn.disabled = true;
  el.detectBtn.textContent = "…";

  try {
    const res = await fetch("/cicd/api/detect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const data = await res.json();

    if (!res.ok) {
      state.detectedStacks = null;
      el.detectHint.textContent = data.error || "Aucun stack détecté.";
      renderManualStackPicker();
      return;
    }

    state.detectedStacks = data.stacks;
    el.detectHint.textContent = `${data.stacks.length} stack(s) détectée(s) avec succès.`;
    renderDetectedStacks(data.stacks);
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  } finally {
    el.detectBtn.disabled = false;
    el.detectBtn.textContent = "Détecter";
  }
}

// ----------------------------------------------------------------------------
// Champs de deploiement conditionnels (affiches selon les cases cochees)
// ----------------------------------------------------------------------------
function updateDeployFieldsVisibility() {
  const checkedTargets = getSelectedDeployTargets();

  ["github_pages", "docker_hub", "ssh", "vercel", "aws_s3"].forEach((target) => {
    const fieldGroup = document.getElementById(`fields-${target}`);
    if (fieldGroup) {
      fieldGroup.hidden = !checkedTargets.includes(target);
    }
  });
}

function getSelectedDeployTargets() {
  return Array.from(
    document.querySelectorAll('input[name="deploy"]:checked')
  ).map((cb) => cb.value);
}

// ----------------------------------------------------------------------------
// Schema de pipeline : mise a jour visuelle selon les jobs coches
// ----------------------------------------------------------------------------
function updateSchematic() {
  const checkedJobs = Array.from(
    document.querySelectorAll('input[name="jobs"]:checked')
  ).map((cb) => cb.value);
  const checkedDeploy = getSelectedDeployTargets();

  const children = Array.from(el.pipelineSchematic.children);

  children.forEach((child) => {
    if (!child.classList.contains("node")) return;
    const job = child.dataset.job;
    if (job === "checkout" || checkedJobs.includes(job)) {
      child.classList.add("active");
    } else if (job === "deploy" && checkedDeploy.length > 0) {
      child.classList.add("active");
    } else {
      child.classList.remove("active");
    }
  });

  // Un connecteur "coule" seulement si le noeud avant ET apres sont actifs
  for (let i = 0; i < children.length; i++) {
    if (!children[i].classList.contains("connector")) continue;
    const prevActive = children[i - 1] && children[i - 1].classList.contains("active");
    const nextActive = children[i + 1] && children[i + 1].classList.contains("active");
    children[i].classList.toggle("flowing", Boolean(prevActive && nextActive));
  }
}

// ----------------------------------------------------------------------------
// Reinitialisation du formulaire
// ----------------------------------------------------------------------------
function handleReset() {
  try {
    localStorage.removeItem(PREFS_KEY);
  } catch (err) {
    // ignore
  }

  el.projectPath.value = "";
  el.branches.value = "main";
  el.pagesDir.value = "dist";
  el.pagesBuildCmd.value = "npm run build";
  el.dockerImage.value = "";
  el.deployPath.value = "";
  el.serviceName.value = "";
  el.matrixVersions.value = "";
  el.scheduleCron.value = "";
  el.s3Bucket.value = "";
  el.awsRegion.value = "us-east-1";
  el.badgeRepo.value = "";
  el.badgeBox.hidden = true;

  state.detectedStacks = null;
  state.manualLanguages.clear();
  renderManualStackPicker();

  document.querySelectorAll('input[name="jobs"]').forEach((cb) => (cb.checked = true));
  document.querySelectorAll('input[name="deploy"]').forEach((cb) => (cb.checked = false));

  switchProvider("github");
  updateDeployFieldsVisibility();
  updateSchematic();
  clearError();
  resetResultBox("Le fichier généré apparaîtra ici.");
}

// ----------------------------------------------------------------------------
// Animation de succes sur le bouton Generer
// ----------------------------------------------------------------------------
function flashSuccess() {
  const originalText = "GÉNÉRER →";
  el.generateBtn.textContent = "✓ GÉNÉRÉ !";
  el.generateBtn.style.background = "linear-gradient(135deg, #2ECC8F, #22B37D)";
  setTimeout(() => {
    el.generateBtn.textContent = originalText;
    el.generateBtn.style.background = "";
  }, 1200);
}

// ----------------------------------------------------------------------------
// Generation du pipeline
// ----------------------------------------------------------------------------
function getSelectedStacksPayload() {
  if (state.detectedStacks && state.detectedStacks.length > 0) {
    return state.detectedStacks;
  }
  return Array.from(state.manualLanguages).map((lang) => ({ language: lang }));
}

function getSelectedJobs() {
  return Array.from(
    document.querySelectorAll('input[name="jobs"]:checked')
  ).map((cb) => cb.value);
}

async function handleGenerate() {
  clearError();

  const stacks = getSelectedStacksPayload();
  const jobs = getSelectedJobs();
  const branches = el.branches.value
    .split(",")
    .map((b) => b.trim())
    .filter(Boolean);
  const deployTargets = getSelectedDeployTargets();

  if (stacks.length === 0) {
    showError("Sélectionne au moins un stack (détection auto ou manuelle).");
    resetResultBox("Aucun stack sélectionné : rien n'a été généré.");
    return;
  }
  if (jobs.length === 0) {
    showError("Sélectionne au moins un job (lint / test / build).");
    resetResultBox("Aucun job sélectionné : rien n'a été généré.");
    return;
  }

  const payload = { stacks, jobs, branches, provider: state.provider };

  const matrixVersions = el.matrixVersions.value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
  if (matrixVersions.length > 1) {
    payload.matrix_versions = matrixVersions;
  }

  const scheduleCron = el.scheduleCron.value.trim();
  if (scheduleCron) {
    payload.schedule_cron = scheduleCron;
  }

  const badgeRepo = el.badgeRepo.value.trim();
  if (badgeRepo) {
    payload.badge_repo = badgeRepo;
  }

  if (deployTargets.length > 0) {
    payload.deploy_targets = deployTargets;
    payload.pages_dir = el.pagesDir.value.trim() || undefined;
    payload.pages_build_cmd = el.pagesBuildCmd.value.trim() || undefined;
    payload.docker_image = el.dockerImage.value.trim() || undefined;
    payload.deploy_path = el.deployPath.value.trim() || undefined;
    payload.service_name = el.serviceName.value.trim() || undefined;
    payload.s3_bucket = el.s3Bucket.value.trim() || undefined;
    payload.aws_region = el.awsRegion.value.trim() || undefined;
  }

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "GÉNÉRATION…";

  try {
    const res = await fetch("/cicd/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Erreur lors de la génération.");
      resetResultBox("La dernière génération a échoué : rien n'a été mis à jour.");
      el.generateBtn.textContent = "GÉNÉRER →";
      return;
    }

    state.lastYaml = data.yaml;
    state.lastFilename = data.filename || "ci.yml";
    renderResult(data.yaml);
    updateTitleBlock(stacks, jobs, deployTargets);
    savePrefs();
    flashSuccess();

    if (data.badge) {
      el.badgeText.textContent = data.badge;
      el.badgeBox.hidden = false;
    } else {
      el.badgeBox.hidden = true;
    }
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
    resetResultBox("Impossible de contacter le serveur local : rien n'a été généré.");
    el.generateBtn.textContent = "GÉNÉRER →";
  } finally {
    el.generateBtn.disabled = false;
  }
}

function resetResultBox(message) {
  el.resultBox.innerHTML = "";
  const p = document.createElement("p");
  p.className = "result-placeholder";
  p.textContent = message || "Le fichier ci.yml généré apparaîtra ici.";
  el.resultBox.appendChild(p);
  el.resultActions.hidden = true;
  state.lastYaml = "";
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function highlightYaml(text) {
  const escaped = escapeHtml(text);
  const lines = escaped.split("\n");

  const highlighted = lines.map((line) => {
    const commentMatch = line.match(/^(\s*)(#.*)$/);
    if (commentMatch) {
      return `${commentMatch[1]}<span class="yaml-comment">${commentMatch[2]}</span>`;
    }

    const kvMatch = line.match(/^(\s*(?:- )?)([\w.\-\/]+)(:)(\s*)(.*)$/);
    if (kvMatch) {
      const [, indent, key, colon, space, rest] = kvMatch;
      const restHighlighted = rest.replace(
        /"([^"]*)"/g,
        '<span class="yaml-string">"$1"</span>'
      );
      return `${indent}<span class="yaml-key">${key}</span>${colon}${space}${restHighlighted}`;
    }

    return line;
  });

  return highlighted.join("\n");
}

function renderResult(yamlText) {
  el.resultBox.innerHTML = "";
  const pre = document.createElement("pre");
  pre.innerHTML = highlightYaml(yamlText);
  el.resultBox.appendChild(pre);
  el.resultActions.hidden = false;
}

function updateTitleBlock(stacks, jobs, deployTargets) {
  const path = el.projectPath.value.trim();
  el.tbProject.textContent = path || "(sélection manuelle)";
  el.tbStacks.textContent = stacks.map((s) => s.language).join(", ") || "—";
  const jobsText = jobs.join(", ") || "—";
  const deployText = deployTargets && deployTargets.length > 0
    ? ` + deploy: ${deployTargets.join(", ")}`
    : "";
  el.tbJobs.textContent = jobsText + deployText;
}

// ----------------------------------------------------------------------------
// Actions resultat : copier / telecharger
// ----------------------------------------------------------------------------
async function handleCopy() {
  if (!state.lastYaml) return;
  try {
    await navigator.clipboard.writeText(state.lastYaml);
    el.copyBtn.textContent = "Copié !";
    setTimeout(() => (el.copyBtn.textContent = "Copier"), 1500);
  } catch (err) {
    showError("Impossible de copier automatiquement, sélectionne le texte manuellement.");
  }
}

async function handleCopyBadge() {
  const text = el.badgeText.textContent;
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    el.copyBadgeBtn.textContent = "Copié !";
    setTimeout(() => (el.copyBadgeBtn.textContent = "Copier le badge"), 1500);
  } catch (err) {
    showError("Impossible de copier automatiquement, sélectionne le texte manuellement.");
  }
}

function handleDownload() {
  if (!state.lastYaml) return;
  const blob = new Blob([state.lastYaml], { type: "text/yaml" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = state.lastFilename || "ci.yml";
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
// Init
// ----------------------------------------------------------------------------
renderManualStackPicker();
updateSchematic();

el.detectBtn.addEventListener("click", handleDetect);
el.generateBtn.addEventListener("click", handleGenerate);
el.copyBtn.addEventListener("click", handleCopy);
el.copyBadgeBtn.addEventListener("click", handleCopyBadge);
el.downloadBtn.addEventListener("click", handleDownload);
document.querySelectorAll('input[name="jobs"]').forEach((cb) => {
  cb.addEventListener("change", updateSchematic);
});
document.querySelectorAll('input[name="deploy"]').forEach((cb) => {
  cb.addEventListener("change", () => {
    updateDeployFieldsVisibility();
    updateSchematic();
  });
});
updateDeployFieldsVisibility();

el.providerButtons.forEach((btn) => {
  btn.addEventListener("click", () => switchProvider(btn.dataset.provider));
});
el.resetBtn.addEventListener("click", handleReset);

loadPrefs();
