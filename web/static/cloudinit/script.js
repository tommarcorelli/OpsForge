// ============================================================================
// modules/cloudinit/static/script.js
// Logique du module cloud-init : builders utilisateurs + write_files,
// textareas paquets/commandes, presets, generation, copier/telecharger.
// ============================================================================

const CONFIG = window.OPSFORGE_CLOUDINIT || { presets: [] };

const state = {
  users: [],
  writeFiles: [],
  lastCombined: "",
  lastFilename: "user-data",
};

const el = {
  presetList: document.getElementById("preset-list"),

  hostnameInput: document.getElementById("hostname-input"),
  timezoneInput: document.getElementById("timezone-input"),
  pkgUpdateCheckbox: document.getElementById("pkg-update-checkbox"),
  pkgUpgradeCheckbox: document.getElementById("pkg-upgrade-checkbox"),
  disableRootCheckbox: document.getElementById("disable-root-checkbox"),
  noPwauthCheckbox: document.getElementById("no-pwauth-checkbox"),

  usersList: document.getElementById("users-list"),
  addUserBtn: document.getElementById("add-user-btn"),

  packagesInput: document.getElementById("packages-input"),

  wfList: document.getElementById("wf-list"),
  addWfBtn: document.getElementById("add-wf-btn"),

  runcmdInput: document.getElementById("runcmd-input"),

  generateBtn: document.getElementById("generate-btn"),
  resetBtn: document.getElementById("reset-btn"),
  errorMsg: document.getElementById("error-msg"),

  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),

  bootNode: document.querySelector('.node[data-stage="boot"]'),

  tbHostname: document.getElementById("tb-hostname"),
  tbUsers: document.getElementById("tb-users"),
  tbPackages: document.getElementById("tb-packages"),
};

// ----------------------------------------------------------------------------
// Utilitaires
// ----------------------------------------------------------------------------
function splitLines(raw) {
  return (raw || "")
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function groupsToString(groups) {
  if (Array.isArray(groups)) return groups.join(", ");
  return groups || "";
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
    const res = await fetch(`/cloudinit/api/preset/${encodeURIComponent(name)}`);
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
  el.hostnameInput.value = cfg.hostname || "";
  el.timezoneInput.value = cfg.timezone || "";
  el.pkgUpdateCheckbox.checked = !!cfg.package_update;
  el.pkgUpgradeCheckbox.checked = !!cfg.package_upgrade;
  el.disableRootCheckbox.checked = !!cfg.disable_root;
  el.noPwauthCheckbox.checked = cfg.ssh_pwauth === false;

  state.users = (cfg.users || []).map((u) => ({
    name: u.name || "",
    groups: groupsToString(u.groups),
    sudo: !!u.sudo,
    ssh_key: Array.isArray(u.ssh_authorized_keys) ? (u.ssh_authorized_keys[0] || "") : (u.ssh_authorized_keys || ""),
  }));
  renderUsersList();

  el.packagesInput.value = (cfg.packages || []).join("\n");

  state.writeFiles = (cfg.write_files || []).map((wf) => ({
    path: wf.path || "",
    permissions: wf.permissions || "",
    content: wf.content || "",
  }));
  renderWriteFilesList();

  el.runcmdInput.value = (cfg.runcmd || []).join("\n");

  updateTitleBlock();
}

// ----------------------------------------------------------------------------
// Utilisateurs (builder)
// ----------------------------------------------------------------------------
function renderUsersList() {
  el.usersList.innerHTML = "";
  state.users.forEach((user, index) => {
    const card = document.createElement("div");
    card.className = "builder-card";

    const top = document.createElement("div");
    top.className = "builder-row";

    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.placeholder = "nom (ex : deploy)";
    nameInput.className = "builder-key";
    nameInput.value = user.name || "";
    nameInput.addEventListener("input", () => {
      state.users[index].name = nameInput.value;
      updateTitleBlock();
    });

    const groupsInput = document.createElement("input");
    groupsInput.type = "text";
    groupsInput.placeholder = "groupes : sudo, docker";
    groupsInput.value = user.groups || "";
    groupsInput.addEventListener("input", () => (state.users[index].groups = groupsInput.value));

    const sudoLabel = document.createElement("label");
    sudoLabel.className = "inline-check";
    sudoLabel.title = "sudo NOPASSWD";
    const sudoInput = document.createElement("input");
    sudoInput.type = "checkbox";
    sudoInput.checked = !!user.sudo;
    sudoInput.addEventListener("change", () => (state.users[index].sudo = sudoInput.checked));
    sudoLabel.appendChild(sudoInput);
    sudoLabel.appendChild(document.createTextNode("sudo"));

    const removeBtn = makeRemoveBtn(() => {
      state.users.splice(index, 1);
      renderUsersList();
      updateTitleBlock();
    });

    top.appendChild(nameInput);
    top.appendChild(groupsInput);
    top.appendChild(sudoLabel);
    top.appendChild(removeBtn);

    const keyInput = document.createElement("input");
    keyInput.type = "text";
    keyInput.className = "full-input";
    keyInput.placeholder = "clé SSH publique (ssh-ed25519 AAAA...)";
    keyInput.value = user.ssh_key || "";
    keyInput.addEventListener("input", () => (state.users[index].ssh_key = keyInput.value));

    card.appendChild(top);
    card.appendChild(keyInput);
    el.usersList.appendChild(card);
  });
}

el.addUserBtn.addEventListener("click", () => {
  state.users.push({ name: "", groups: "sudo", sudo: true, ssh_key: "" });
  renderUsersList();
  updateTitleBlock();
});

// ----------------------------------------------------------------------------
// write_files (builder)
// ----------------------------------------------------------------------------
function renderWriteFilesList() {
  el.wfList.innerHTML = "";
  state.writeFiles.forEach((wf, index) => {
    const card = document.createElement("div");
    card.className = "builder-card";

    const top = document.createElement("div");
    top.className = "builder-row";

    const pathInput = document.createElement("input");
    pathInput.type = "text";
    pathInput.placeholder = "chemin (ex : /etc/motd)";
    pathInput.value = wf.path || "";
    pathInput.addEventListener("input", () => (state.writeFiles[index].path = pathInput.value));

    const permInput = document.createElement("input");
    permInput.type = "text";
    permInput.className = "perm-input";
    permInput.placeholder = "0644";
    permInput.value = wf.permissions || "";
    permInput.addEventListener("input", () => (state.writeFiles[index].permissions = permInput.value));

    const removeBtn = makeRemoveBtn(() => {
      state.writeFiles.splice(index, 1);
      renderWriteFilesList();
    });

    top.appendChild(pathInput);
    top.appendChild(permInput);
    top.appendChild(removeBtn);

    const contentArea = document.createElement("textarea");
    contentArea.className = "full-input area";
    contentArea.rows = 3;
    contentArea.placeholder = "contenu du fichier";
    contentArea.value = wf.content || "";
    contentArea.addEventListener("input", () => (state.writeFiles[index].content = contentArea.value));

    card.appendChild(top);
    card.appendChild(contentArea);
    el.wfList.appendChild(card);
  });
}

el.addWfBtn.addEventListener("click", () => {
  state.writeFiles.push({ path: "", permissions: "0644", content: "" });
  renderWriteFilesList();
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
function buildPayload() {
  const payload = {
    hostname: el.hostnameInput.value.trim(),
    timezone: el.timezoneInput.value.trim(),
    packages: splitLines(el.packagesInput.value),
    runcmd: splitLines(el.runcmdInput.value),
    users: state.users
      .filter((u) => (u.name || "").trim())
      .map((u) => ({
        name: u.name.trim(),
        groups: u.groups.trim(),
        sudo: u.sudo,
        ssh_authorized_keys: (u.ssh_key || "").trim() ? [u.ssh_key.trim()] : [],
      })),
    write_files: state.writeFiles
      .filter((wf) => (wf.path || "").trim())
      .map((wf) => ({
        path: wf.path.trim(),
        permissions: wf.permissions.trim(),
        content: wf.content,
      })),
  };

  if (el.pkgUpdateCheckbox.checked) payload.package_update = true;
  if (el.pkgUpgradeCheckbox.checked) payload.package_upgrade = true;
  if (el.disableRootCheckbox.checked) payload.disable_root = true;
  if (el.noPwauthCheckbox.checked) payload.ssh_pwauth = false;

  return payload;
}

function frontValidate() {
  const hasContent =
    el.hostnameInput.value.trim() ||
    splitLines(el.packagesInput.value).length ||
    splitLines(el.runcmdInput.value).length ||
    state.users.some((u) => (u.name || "").trim()) ||
    state.writeFiles.some((wf) => (wf.path || "").trim()) ||
    el.pkgUpdateCheckbox.checked ||
    el.pkgUpgradeCheckbox.checked;
  if (!hasContent) {
    return "Ajoute au moins une directive (hostname, paquet, utilisateur, fichier ou commande).";
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
    const res = await fetch("/cloudinit/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showError(data.error || "Erreur lors de la génération.");
      return;
    }

    state.lastFilename = data.filename || "user-data";
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
  if (el.bootNode) el.bootNode.classList.add("active");
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
  if (el.bootNode) el.bootNode.classList.remove("active");
}

function updateTitleBlock() {
  el.tbHostname.textContent = el.hostnameInput.value.trim() || "—";
  el.tbUsers.textContent = String(state.users.filter((u) => (u.name || "").trim()).length);
  el.tbPackages.textContent = String(splitLines(el.packagesInput.value).length);
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
  el.hostnameInput.value = "";
  el.timezoneInput.value = "";
  el.pkgUpdateCheckbox.checked = false;
  el.pkgUpgradeCheckbox.checked = false;
  el.disableRootCheckbox.checked = false;
  el.noPwauthCheckbox.checked = false;
  el.packagesInput.value = "";
  el.runcmdInput.value = "";

  state.users = [];
  state.writeFiles = [];
  renderUsersList();
  renderWriteFilesList();

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
el.generateBtn.addEventListener("click", handleGenerate);
el.resetBtn.addEventListener("click", handleReset);
el.copyBtn.addEventListener("click", handleCopy);
el.downloadBtn.addEventListener("click", handleDownload);
el.hostnameInput.addEventListener("input", updateTitleBlock);
el.packagesInput.addEventListener("input", updateTitleBlock);

renderPresetList();
renderUsersList();
renderWriteFilesList();
updateTitleBlock();
