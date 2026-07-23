// ============================================================================
// script.js — generateur de playbook Ansible
// ============================================================================

const state = {
  layout: "flat",
  targetOs: "linux",
  lastPlaybook: "",
  lastInventory: "",
  lastVault: "",
  activeTab: "playbook",
  lastFiles: {},        // mode roles : { chemin: contenu }
  activeFile: null,     // mode roles : fichier actuellement previsualise
};

const el = {
  language: document.getElementById("language"),
  repoUrl: document.getElementById("repo-url"),
  branch: document.getElementById("branch"),
  appDir: document.getElementById("app-dir"),
  buildCmdGroup: document.getElementById("build-cmd-group"),
  buildCmd: document.getElementById("build-cmd"),
  healthCheckPortGroup: document.getElementById("health-check-port-group"),
  healthCheckPort: document.getElementById("health-check-port"),
  notifyWebhookGroup: document.getElementById("notify-webhook-group"),
  notifyWebhookUrl: document.getElementById("notify-webhook-url"),
  httpsFieldsGroup: document.getElementById("https-fields-group"),
  usersFieldsGroup: document.getElementById("users-fields-group"),
  sshPublicKey: document.getElementById("ssh-public-key"),
  sshHardeningWarning: document.getElementById("ssh-hardening-warning"),
  domainName: document.getElementById("domain-name"),
  letsencryptEmail: document.getElementById("letsencrypt-email"),
  databaseFieldsGroup: document.getElementById("database-fields-group"),
  databaseEngine: document.getElementById("database-engine"),
  dbName: document.getElementById("db-name"),
  dbUser: document.getElementById("db-user"),
  backupsFieldsGroup: document.getElementById("backups-fields-group"),
  backupDir: document.getElementById("backup-dir"),
  backupRetentionDays: document.getElementById("backup-retention-days"),
  backupHour: document.getElementById("backup-hour"),
  exportConfigBtn: document.getElementById("export-config-btn"),
  importConfigInput: document.getElementById("import-config-input"),
  serviceName: document.getElementById("service-name"),
  inventoryHost: document.getElementById("inventory-host"),
  sshUser: document.getElementById("ssh-user"),
  targetOsSwitch: document.getElementById("target-os-switch"),
  windowsHint: document.getElementById("windows-hint"),
  winrmFieldsGroup: document.getElementById("winrm-fields-group"),
  winrmPassword: document.getElementById("winrm-password"),
  winrmTransport: document.getElementById("winrm-transport"),
  winrmPort: document.getElementById("winrm-port"),
  vaultVars: document.getElementById("vault-vars"),
  vaultPassword: document.getElementById("vault-password"),
  generateBtn: document.getElementById("generate-btn"),
  errorMsg: document.getElementById("error-msg"),
  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),
  tbLayout: document.getElementById("tb-layout"),
  tbLanguage: document.getElementById("tb-language"),
  tbRepo: document.getElementById("tb-repo"),
  tbServer: document.getElementById("tb-server"),
  tabButtons: document.querySelectorAll(".tab-btn"),
  layoutToggle: document.getElementById("layout-toggle"),
  layoutButtons: document.querySelectorAll(".segmented-btn"),
  flatView: document.getElementById("flat-view"),
  rolesView: document.getElementById("roles-view"),
  nomenclature: document.getElementById("nomenclature"),
  rolesResultBox: document.getElementById("roles-result-box"),
  rolesFileContent: document.getElementById("roles-file-content"),
  downloadZipBtn: document.getElementById("download-zip-btn"),
  nodeTarget: document.getElementById("node-target"),
  nodeTargetLabel: document.getElementById("node-target-label"),
  singleTargetFields: document.getElementById("single-target-fields"),
  multiTargetFields: document.getElementById("multi-target-fields"),
  groupsBuilder: document.getElementById("groups-builder"),
  addGroupBtn: document.getElementById("add-group-btn"),
  groupsJsonPreview: document.getElementById("groups-json-preview"),
  loadExampleBtn: document.getElementById("load-example-btn"),
};

const LANGUAGES = ["python", "node", "go", "rust", "java", "php"];

const PROVISIONING_OPTIONS = [
  { value: "update_system", label: "MAJ système" },
  { value: "base_packages", label: "Paquets de base" },
  { value: "firewall", label: "Pare-feu (UFW/firewalld)" },
  { value: "ssh_hardening", label: "Durcissement SSH" },
  { value: "fail2ban", label: "Fail2ban" },
  { value: "monitoring", label: "Supervision (Netdata)" },
  { value: "runtime", label: "Runtime applicatif" },
  { value: "docker", label: "Docker" },
  { value: "nginx", label: "Nginx" },
  { value: "https", label: "HTTPS (Certbot)" },
  { value: "database", label: "Base de données" },
  { value: "backups", label: "Sauvegardes automatiques" },
];

const DEPLOYMENT_OPTIONS = [
  { value: "backup_previous", label: "Backup avant déploiement" },
  { value: "git_clone", label: "Git clone" },
  { value: "zero_downtime_deploy", label: "Zero-downtime (releases + symlink)" },
  { value: "install_deps", label: "Dépendances" },
  { value: "build", label: "Build" },
  { value: "restart_service", label: "Restart service" },
  { value: "reload_nginx", label: "Reload Nginx" },
  { value: "health_check", label: "Health check" },
  { value: "notify", label: "Notification Slack/Discord" },
];

let groupCounter = 0;

const GROUPS_EXAMPLE = [
  {
    hosts_group: "web",
    provisioning: ["update_system", "base_packages", "nginx", "runtime"],
    language: "node",
    deployment: ["backup_previous", "git_clone", "install_deps", "build", "restart_service", "reload_nginx", "health_check"],
    repo_url: "git@github.com:moi/mon-app.git",
    branch: "main",
    app_dir: "/opt/mon-app",
    service_name: "mon-app",
    build_cmd: "npm run build",
    health_check_port: "3000",
    hosts: ["203.0.113.10", "203.0.113.11"],
    ssh_user: "deploy",
  },
  {
    hosts_group: "db",
    provisioning: ["update_system", "base_packages", "docker"],
    deployment: [],
    hosts: ["203.0.113.20"],
    ssh_user: "deploy",
  },
];

function createGroupCard(prefill) {
  groupCounter += 1;
  const id = groupCounter;
  const data = prefill || {};

  const card = document.createElement("div");
  card.className = "group-card";
  card.dataset.groupId = String(id);

  const provisioningChecked = new Set(data.provisioning || ["update_system", "runtime"]);
  const deploymentChecked = new Set(data.deployment || ["git_clone", "install_deps", "restart_service"]);

  const provisioningHtml = PROVISIONING_OPTIONS.map(
    (opt) => `
    <label class="toggle">
      <input type="checkbox" data-field="provisioning" value="${opt.value}" ${provisioningChecked.has(opt.value) ? "checked" : ""} />
      <span>${opt.label}</span>
    </label>`
  ).join("");

  const deploymentHtml = DEPLOYMENT_OPTIONS.map(
    (opt) => `
    <label class="toggle">
      <input type="checkbox" data-field="deployment" value="${opt.value}" ${deploymentChecked.has(opt.value) ? "checked" : ""} />
      <span>${opt.label}</span>
    </label>`
  ).join("");

  const languageOptionsHtml = LANGUAGES.map(
    (lang) => `<option value="${lang}" ${data.language === lang ? "selected" : ""}>${lang}</option>`
  ).join("");

  card.innerHTML = `
    <div class="group-card-header">
      <input type="text" class="group-card-title" data-field="hosts_group" value="${data.hosts_group || `groupe-${id}`}" />
      <button type="button" class="remove-group-btn" data-action="remove-group">Supprimer</button>
    </div>

    <span class="mini-label">Langage / runtime</span>
    <select class="text-input" data-field="language">${languageOptionsHtml}</select>

    <span class="mini-label">Provisioning</span>
    <div class="checkbox-grid">${provisioningHtml}</div>

    <span class="mini-label">Déploiement</span>
    <div class="checkbox-grid">${deploymentHtml}</div>

    <span class="mini-label">Dépôt Git / déploiement</span>
    <input type="text" class="text-input" data-field="repo_url" placeholder="git@github.com:moi/mon-app.git" value="${data.repo_url || ""}" style="margin-bottom: 6px;" />
    <div class="group-card-row" style="margin-bottom: 6px;">
      <input type="text" class="text-input" data-field="branch" placeholder="Branche (main)" value="${data.branch || ""}" />
      <input type="text" class="text-input" data-field="app_dir" placeholder="/opt/mon-app" value="${data.app_dir || ""}" />
    </div>
    <div class="group-card-row" style="margin-bottom: 6px;">
      <input type="text" class="text-input" data-field="service_name" placeholder="Nom du service" value="${data.service_name || ""}" />
      <input type="text" class="text-input" data-field="build_cmd" placeholder="Commande de build" value="${data.build_cmd || ""}" />
    </div>
    <input type="text" class="text-input" data-field="health_check_port" placeholder="Port health check (80)" value="${data.health_check_port || ""}" style="margin-bottom: 6px;" />

    <div class="group-card-row" style="margin-bottom: 6px;">
      <input type="text" class="text-input" data-field="domain_name" placeholder="Domaine HTTPS (si coché)" value="${data.domain_name || ""}" />
      <input type="text" class="text-input" data-field="letsencrypt_email" placeholder="Email Let's Encrypt" value="${data.letsencrypt_email || ""}" />
    </div>
    <div class="group-card-row" style="margin-bottom: 6px;">
      <select class="text-input" data-field="database_engine">
        <option value="">Moteur DB (si coché)</option>
        <option value="postgresql" ${data.database_engine === "postgresql" ? "selected" : ""}>PostgreSQL</option>
        <option value="mysql" ${data.database_engine === "mysql" ? "selected" : ""}>MySQL/MariaDB</option>
        <option value="redis" ${data.database_engine === "redis" ? "selected" : ""}>Redis</option>
        <option value="mongodb" ${data.database_engine === "mongodb" ? "selected" : ""}>MongoDB</option>
      </select>
      <input type="text" class="text-input" data-field="db_name" placeholder="Nom de la base" value="${data.db_name || ""}" />
    </div>
    <input type="text" class="text-input" data-field="db_user" placeholder="Utilisateur DB" value="${data.db_user || ""}" style="margin-bottom: 6px;" />
    <div class="group-card-row" style="margin-bottom: 6px;">
      <input type="text" class="text-input" data-field="backup_dir" placeholder="Dossier de sauvegarde (/opt/backups)" value="${data.backup_dir || ""}" />
      <input type="number" class="text-input" data-field="backup_retention_days" placeholder="Rétention (jours)" min="1" value="${data.backup_retention_days || ""}" />
    </div>
    <input type="number" class="text-input" data-field="backup_hour" placeholder="Heure d'exécution (0-23)" min="0" max="23" value="${data.backup_hour || ""}" style="margin-bottom: 6px;" />
    <input type="text" class="text-input" data-field="notify_webhook_url" placeholder="Webhook Slack/Discord (si coché)" value="${data.notify_webhook_url || ""}" />

    <span class="mini-label">Hôtes du groupe (un par ligne)</span>
    <textarea class="text-input" data-field="hosts" rows="2" placeholder="203.0.113.10&#10;203.0.113.11">${(data.hosts || []).join("\n")}</textarea>
    <input type="text" class="text-input" data-field="ssh_user" placeholder="Utilisateur SSH (deploy)" value="${data.ssh_user || ""}" style="margin-top: 6px;" />
  `;

  card.addEventListener("input", renderGroupsJsonPreview);
  card.addEventListener("change", renderGroupsJsonPreview);
  card.querySelector('[data-action="remove-group"]').addEventListener("click", () => {
    card.remove();
    renderGroupsJsonPreview();
  });

  el.groupsBuilder.appendChild(card);
  renderGroupsJsonPreview();
}

function collectGroupsFromCards() {
  return Array.from(document.querySelectorAll(".group-card")).map((card) => {
    const get = (field) => card.querySelector(`[data-field="${field}"]`).value.trim();
    const getChecked = (field) =>
      Array.from(card.querySelectorAll(`[data-field="${field}"]:checked`)).map((cb) => cb.value);

    const language = get("language");
    const hosts = get("hosts").split("\n").map((h) => h.trim()).filter(Boolean);

    return {
      hosts_group: get("hosts_group") || "groupe",
      provisioning: getChecked("provisioning"),
      runtime_language: language,
      deployment: getChecked("deployment"),
      deployment_language: language,
      repo_url: get("repo_url"),
      branch: get("branch") || "main",
      app_dir: get("app_dir") || "/opt/mon-application",
      service_name: get("service_name") || "mon-application",
      build_cmd: get("build_cmd") || null,
      health_check_port: get("health_check_port") || null,
      domain_name: get("domain_name") || null,
      letsencrypt_email: get("letsencrypt_email") || null,
      database_engine: get("database_engine") || null,
      db_name: get("db_name") || null,
      db_user: get("db_user") || null,
      backup_dir: get("backup_dir") || null,
      backup_retention_days: get("backup_retention_days") || null,
      backup_hour: get("backup_hour") || null,
      notify_webhook_url: get("notify_webhook_url") || null,
      hosts: hosts,
      ssh_user: get("ssh_user") || "deploy",
    };
  });
}

function renderGroupsJsonPreview() {
  const groups = collectGroupsFromCards();
  el.groupsJsonPreview.textContent = groups.length
    ? JSON.stringify(groups, null, 2)
    : "Aucun groupe pour l'instant. Clique sur \"+ Ajouter un groupe\".";
}

function validateGroups(groups) {
  if (groups.length === 0) {
    return "Ajoute au moins un groupe de serveurs.";
  }
  const names = new Set();
  for (const g of groups) {
    if (!g.hosts_group) return "Chaque groupe doit avoir un nom.";
    if (names.has(g.hosts_group)) return `Nom de groupe en double : "${g.hosts_group}".`;
    names.add(g.hosts_group);
    if (g.provisioning.length === 0 && g.deployment.length === 0) {
      return `Le groupe "${g.hosts_group}" n'a aucune étape sélectionnée.`;
    }
  }
  return null;
}

// ----------------------------------------------------------------------------
// Schema de pipeline vivant : allume les noeuds selon les etapes cochees
// ----------------------------------------------------------------------------
function updateSchematic() {
  const checkedValues = new Set([
    ...getCheckedValues("provisioning"),
    ...getCheckedValues("deployment"),
  ]);
  document.querySelectorAll("#pipeline-schematic .node[data-step]").forEach((node) => {
    node.classList.toggle("active", checkedValues.has(node.dataset.step));
  });

  const host = el.inventoryHost.value.trim();
  el.nodeTargetLabel.textContent = host || "non défini";
  el.nodeTarget.classList.toggle("defined", Boolean(host));
}

// ----------------------------------------------------------------------------
// Toggle de structure (flat / roles)
// ----------------------------------------------------------------------------
function switchLayout(layout) {
  state.layout = layout;
  el.layoutButtons.forEach((btn) => {
    const active = btn.dataset.layout === layout;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  el.flatView.hidden = layout !== "flat";
  el.rolesView.hidden = layout === "flat";
  el.singleTargetFields.hidden = layout === "multi";
  el.multiTargetFields.hidden = layout !== "multi";
  const labels = { flat: "Playbook unique", roles: "Projet en rôles", multi: "Multi-serveurs" };
  el.tbLayout.textContent = labels[layout];
  clearError();
}

// ----------------------------------------------------------------------------
// Onglets playbook / inventory / vault (mode flat)
// ----------------------------------------------------------------------------
function switchTab(tabName) {
  state.activeTab = tabName;
  el.tabButtons.forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tabName);
  });
  renderActiveTabContent();
}

function renderActiveTabContent() {
  const contentMap = {
    playbook: state.lastPlaybook,
    inventory: state.lastInventory,
    vault: state.lastVault,
  };
  const content = contentMap[state.activeTab];

  if (!content) {
    el.resultBox.innerHTML = "";
    const p = document.createElement("p");
    p.className = "result-placeholder";
    const placeholders = {
      playbook: "Le fichier playbook.yml généré apparaîtra ici.",
      inventory: "Renseigne un hôte (section 05) pour générer un inventory.ini.",
      vault: "Renseigne au moins un secret et un mot de passe (section 06) pour générer un vault.yml chiffré.",
    };
    p.textContent = placeholders[state.activeTab];
    el.resultBox.appendChild(p);
    el.resultActions.hidden = true;
    return;
  }

  el.resultBox.innerHTML = "";
  const pre = document.createElement("pre");
  pre.textContent = content;
  el.resultBox.appendChild(pre);
  el.resultActions.hidden = false;
}

// ----------------------------------------------------------------------------
// Nomenclature (mode roles) : arbre de fichiers + previsualisation
// ----------------------------------------------------------------------------
function renderNomenclature() {
  const paths = Object.keys(state.lastFiles).sort();
  el.nomenclature.innerHTML = "";

  if (paths.length === 0) {
    const p = document.createElement("p");
    p.className = "result-placeholder";
    p.textContent = "La liste des fichiers apparaîtra ici après génération.";
    el.nomenclature.appendChild(p);
    el.rolesResultBox.hidden = true;
    el.downloadZipBtn.hidden = true;
    return;
  }

  paths.forEach((path) => {
    const depth = (path.match(/\//g) || []).length;
    const row = document.createElement("button");
    row.type = "button";
    row.className = "nomenclature-row";
    row.style.paddingLeft = `${14 + depth * 18}px`;
    row.dataset.path = path;

    const marker = document.createElement("span");
    marker.className = "nomenclature-marker";
    marker.textContent = depth > 0 ? "└─" : "•";

    const label = document.createElement("span");
    label.className = "nomenclature-label";
    label.textContent = path;

    row.appendChild(marker);
    row.appendChild(label);
    row.addEventListener("click", () => showFileContent(path));
    el.nomenclature.appendChild(row);
  });

  el.downloadZipBtn.hidden = false;

  // Ouvre playbook.yml par defaut
  if (state.lastFiles["playbook.yml"]) {
    showFileContent("playbook.yml");
  }
}

function showFileContent(path) {
  state.activeFile = path;
  document.querySelectorAll(".nomenclature-row").forEach((row) => {
    row.classList.toggle("active", row.dataset.path === path);
  });
  el.rolesFileContent.textContent = state.lastFiles[path] || "";
  el.rolesResultBox.hidden = false;
}

// ----------------------------------------------------------------------------
// Generation
// ----------------------------------------------------------------------------
function getCheckedValues(name) {
  return Array.from(
    document.querySelectorAll(`input[name="${name}"]:checked`)
  ).map((cb) => cb.value);
}

function parseVaultVars() {
  const raw = el.vaultVars.value.trim();
  if (!raw) return {};
  const vars = {};
  raw.split("\n").forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const idx = trimmed.indexOf("=");
    if (idx === -1) return;
    const key = trimmed.slice(0, idx).trim();
    const value = trimmed.slice(idx + 1);
    if (key) vars[key] = value;
  });
  return vars;
}

function buildPayload() {
  const provisioning = getCheckedValues("provisioning");
  const deployment = getCheckedValues("deployment");
  const repoUrl = el.repoUrl.value.trim();
  const vaultVars = parseVaultVars();
  const vaultPassword = el.vaultPassword.value;

  return {
    payload: {
      language: el.language.value,
      provisioning,
      deployment,
      repo_url: repoUrl,
      branch: el.branch.value.trim() || "main",
      app_dir: el.appDir.value.trim() || "/opt/mon-application",
      service_name: el.serviceName.value.trim() || "mon-application",
      build_cmd: el.buildCmd.value.trim() || null,
      health_check_port: el.healthCheckPort.value.trim() || null,
      notify_webhook_url: el.notifyWebhookUrl.value.trim() || null,
      domain_name: el.domainName.value.trim() || null,
      letsencrypt_email: el.letsencryptEmail.value.trim() || null,
      database_engine: el.databaseEngine.value || null,
      db_name: el.dbName.value.trim() || null,
      db_user: el.dbUser.value.trim() || null,
      backup_dir: el.backupDir.value.trim() || null,
      backup_retention_days: el.backupRetentionDays.value.trim() || null,
      backup_hour: el.backupHour.value.trim() || null,
      inventory_host: el.inventoryHost.value.trim() || null,
      ssh_user: el.sshUser.value.trim() || "deploy",
      deploy_user: el.sshUser.value.trim() || "deploy",
      ssh_public_key: el.sshPublicKey.value.trim() || null,
      target_os: state.targetOs,
      winrm_password: el.winrmPassword.value || null,
      winrm_transport: el.winrmTransport.value || "ntlm",
      winrm_port: el.winrmPort.value.trim() || null,
      vault_vars: Object.keys(vaultVars).length > 0 ? vaultVars : null,
      vault_password: vaultPassword || null,
    },
    provisioning,
    deployment,
    repoUrl,
    vaultVars,
    vaultPassword,
  };
}

function validatePayload({ provisioning, deployment, repoUrl, vaultVars, vaultPassword }) {
  if (provisioning.length === 0 && deployment.length === 0) {
    showError("Sélectionne au moins une étape de provisioning ou de déploiement.");
    return false;
  }
  if (deployment.includes("git_clone") && !repoUrl) {
    showError("Renseigne l'URL du dépôt Git pour l'étape de clonage.");
    return false;
  }
  if (Object.keys(vaultVars).length > 0 && !vaultPassword) {
    showError("Renseigne un mot de passe de vault pour chiffrer les secrets (section 06).");
    return false;
  }
  return true;
}

async function handleGenerate() {
  clearError();

  if (state.layout === "multi") {
    const groups = collectGroupsFromCards();
    const validationError = validateGroups(groups);
    if (validationError) {
      showError(validationError);
      state.lastFiles = {};
      renderNomenclature();
      return;
    }
    const vaultVars = parseVaultVars();
    const vaultPassword = el.vaultPassword.value;
    if (Object.keys(vaultVars).length > 0 && !vaultPassword) {
      showError("Renseigne un mot de passe de vault pour chiffrer les secrets (section 06).");
      return;
    }

    el.generateBtn.disabled = true;
    el.generateBtn.textContent = "GÉNÉRATION…";
    try {
      await generateMulti({
        groups,
        vault_vars: Object.keys(vaultVars).length > 0 ? vaultVars : null,
        vault_password: vaultPassword || null,
      });
      el.tbLanguage.textContent = "—";
      el.tbRepo.textContent = groups.map((g) => g.hosts_group).join(" + ");
      el.tbServer.textContent = `${groups.length} groupe(s)`;
    } catch (err) {
      showError("Impossible de contacter le serveur local.");
    } finally {
      el.generateBtn.disabled = false;
      el.generateBtn.textContent = "GÉNÉRER →";
    }
    return;
  }

  const built = buildPayload();

  if (!validatePayload(built)) {
    if (state.layout === "flat") {
      resetResults("Rien n'a été généré : vérifie les champs ci-dessus.");
    } else {
      state.lastFiles = {};
      renderNomenclature();
    }
    return;
  }

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "GÉNÉRATION…";

  try {
    if (state.layout === "flat") {
      await generateFlat(built.payload);
    } else {
      await generateRoles(built.payload);
    }
    updateTitleBlock(built.payload);
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
    if (state.layout === "flat") {
      resetResults("Impossible de contacter le serveur local : rien n'a été généré.");
    }
  } finally {
    el.generateBtn.disabled = false;
    el.generateBtn.textContent = "GÉNÉRER →";
  }
}

async function generateFlat(payload) {
  const res = await fetch("/ansible/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();

  if (!res.ok) {
    showError(data.error || "Erreur lors de la génération.");
    resetResults("La dernière génération a échoué : rien n'a été mis à jour.");
    return;
  }

  state.lastPlaybook = data.playbook || "";
  state.lastInventory = data.inventory || "";
  state.lastVault = data.vault || "";
  renderActiveTabContent();
}

async function generateRoles(payload) {
  const res = await fetch("/ansible/api/generate-roles", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();

  if (!res.ok) {
    showError(data.error || "Erreur lors de la génération.");
    state.lastFiles = {};
    renderNomenclature();
    return;
  }

  state.lastFiles = data.files || {};
  renderNomenclature();
}

async function generateMulti(payload) {
  const res = await fetch("/ansible/api/generate-multi", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();

  if (!res.ok) {
    showError(data.error || "Erreur lors de la génération.");
    state.lastFiles = {};
    renderNomenclature();
    return;
  }

  state.lastFiles = data.files || {};
  renderNomenclature();
}

async function handleDownloadZip() {
  clearError();

  let endpoint = "/ansible/api/generate-roles-zip";
  let bodyPayload;
  let downloadName = "ansible-project.zip";

  if (state.layout === "multi") {
    const groups = collectGroupsFromCards();
    const validationError = validateGroups(groups);
    if (validationError) {
      showError(validationError);
      return;
    }
    const vaultVars = parseVaultVars();
    const vaultPassword = el.vaultPassword.value;
    if (Object.keys(vaultVars).length > 0 && !vaultPassword) {
      showError("Renseigne un mot de passe de vault pour chiffrer les secrets (section 06).");
      return;
    }
    endpoint = "/ansible/api/generate-multi-zip";
    downloadName = "ansible-project-multi.zip";
    bodyPayload = {
      groups,
      vault_vars: Object.keys(vaultVars).length > 0 ? vaultVars : null,
      vault_password: vaultPassword || null,
    };
  } else {
    const built = buildPayload();
    if (!validatePayload(built)) return;
    bodyPayload = built.payload;
  }

  el.downloadZipBtn.disabled = true;
  el.downloadZipBtn.textContent = "GÉNÉRATION DU ZIP…";

  try {
    const res = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(bodyPayload),
    });

    if (!res.ok) {
      const data = await res.json();
      showError(data.error || "Erreur lors de la génération du zip.");
      return;
    }

    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = downloadName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  } finally {
    el.downloadZipBtn.disabled = false;
    el.downloadZipBtn.textContent = "TÉLÉCHARGER LE PROJET (.ZIP) →";
  }
}

function resetResults(message) {
  state.lastPlaybook = "";
  state.lastInventory = "";
  state.lastVault = "";
  el.resultBox.innerHTML = "";
  const p = document.createElement("p");
  p.className = "result-placeholder";
  p.textContent = message;
  el.resultBox.appendChild(p);
  el.resultActions.hidden = true;
}

function updateTitleBlock(payload) {
  el.tbLanguage.textContent = payload.language || "—";
  el.tbRepo.textContent = payload.repo_url || "—";
  el.tbServer.textContent = payload.inventory_host || "(non renseigné)";
}

// ----------------------------------------------------------------------------
// Afficher/cacher le champ "commande de build" selon la case cochee
// ----------------------------------------------------------------------------
function updateBuildCmdVisibility() {
  const buildChecked = document.querySelector(
    'input[name="deployment"][value="build"]'
  ).checked;
  el.buildCmdGroup.hidden = !buildChecked;

  const healthCheckChecked = document.querySelector(
    'input[name="deployment"][value="health_check"]'
  ).checked;
  el.healthCheckPortGroup.hidden = !healthCheckChecked;

  const notifyChecked = document.querySelector(
    'input[name="deployment"][value="notify"]'
  ).checked;
  el.notifyWebhookGroup.hidden = !notifyChecked;

  const httpsChecked = document.querySelector(
    'input[name="provisioning"][value="https"]'
  ).checked;
  el.httpsFieldsGroup.hidden = !httpsChecked;

  const sshHardeningChecked = document.querySelector(
    'input[name="provisioning"][value="ssh_hardening"]'
  ).checked;
  el.sshHardeningWarning.hidden = !sshHardeningChecked;

  const usersChecked = document.querySelector(
    'input[name="provisioning"][value="users"]'
  ).checked;
  el.usersFieldsGroup.hidden = !usersChecked;

  const databaseChecked = document.querySelector(
    'input[name="provisioning"][value="database"]'
  ).checked;
  el.databaseFieldsGroup.hidden = !databaseChecked;

  const backupsChecked = document.querySelector(
    'input[name="provisioning"][value="backups"]'
  ).checked;
  el.backupsFieldsGroup.hidden = !backupsChecked;
}

// ----------------------------------------------------------------------------
// Cible OS (Linux/SSH vs Windows/WinRM) : bascule les champs, grise et
// decoche les etapes/langages non disponibles cote Windows.
// ----------------------------------------------------------------------------
const ANSIBLE_CONFIG = window.OPSFORGE_ANSIBLE || {
  windowsProvisioning: [],
  windowsDeployment: [],
  windowsLanguages: [],
};

function setTargetOs(targetOs) {
  state.targetOs = targetOs;
  const windows = targetOs === "windows";

  el.targetOsSwitch.querySelectorAll(".os-switch-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.targetOs === targetOs);
  });

  el.windowsHint.hidden = !windows;
  el.winrmFieldsGroup.hidden = !windows;

  document.querySelectorAll('input[name="provisioning"]').forEach((cb) => {
    const allowed = !windows || ANSIBLE_CONFIG.windowsProvisioning.includes(cb.value);
    cb.disabled = !allowed;
    cb.closest(".toggle")?.classList.toggle("step-disabled", !allowed);
    if (!allowed) cb.checked = false;
  });

  document.querySelectorAll('input[name="deployment"]').forEach((cb) => {
    const allowed = !windows || ANSIBLE_CONFIG.windowsDeployment.includes(cb.value);
    cb.disabled = !allowed;
    cb.closest(".toggle")?.classList.toggle("step-disabled", !allowed);
    if (!allowed) cb.checked = false;
  });

  Array.from(el.language.options).forEach((opt) => {
    const allowed = !windows || ANSIBLE_CONFIG.windowsLanguages.includes(opt.value);
    opt.disabled = !allowed;
  });
  if (windows && !ANSIBLE_CONFIG.windowsLanguages.includes(el.language.value)) {
    el.language.value = ANSIBLE_CONFIG.windowsLanguages[0] || el.language.value;
  }

  updateBuildCmdVisibility();
}

el.targetOsSwitch.querySelectorAll(".os-switch-btn").forEach((btn) => {
  btn.addEventListener("click", () => setTargetOs(btn.dataset.targetOs));
});

// ----------------------------------------------------------------------------
// Actions resultat : copier / telecharger (mode flat)
// ----------------------------------------------------------------------------
async function handleCopy() {
  const contentMap = {
    playbook: state.lastPlaybook,
    inventory: state.lastInventory,
    vault: state.lastVault,
  };
  const content = contentMap[state.activeTab];
  if (!content) return;
  try {
    await navigator.clipboard.writeText(content);
    el.copyBtn.textContent = "Copié !";
    setTimeout(() => (el.copyBtn.textContent = "Copier"), 1500);
  } catch (err) {
    showError("Impossible de copier automatiquement, sélectionne le texte manuellement.");
  }
}

function handleDownload() {
  const contentMap = {
    playbook: state.lastPlaybook,
    inventory: state.lastInventory,
    vault: state.lastVault,
  };
  const filenameMap = {
    playbook: "playbook.yml",
    inventory: "inventory.ini",
    vault: "vault.yml",
  };
  const content = contentMap[state.activeTab];
  if (!content) return;
  const filename = filenameMap[state.activeTab];
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

// ----------------------------------------------------------------------------
// Export / import de config (mode simple, flat/roles)
// ----------------------------------------------------------------------------
function exportConfig() {
  const built = buildPayload();
  const config = { ...built.payload };
  delete config.vault_password; // jamais exporter le mot de passe en clair
  const blob = new Blob([JSON.stringify(config, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "ansible-generator-config.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function applyImportedConfig(config) {
  setTargetOs(config.target_os === "windows" ? "windows" : "linux");

  if (config.language) el.language.value = config.language;
  if (config.repo_url) el.repoUrl.value = config.repo_url;
  if (config.branch) el.branch.value = config.branch;
  if (config.app_dir) el.appDir.value = config.app_dir;
  if (config.service_name) el.serviceName.value = config.service_name;
  if (config.build_cmd) el.buildCmd.value = config.build_cmd;
  if (config.health_check_port) el.healthCheckPort.value = config.health_check_port;
  if (config.notify_webhook_url) el.notifyWebhookUrl.value = config.notify_webhook_url;
  if (config.domain_name) el.domainName.value = config.domain_name;
  if (config.letsencrypt_email) el.letsencryptEmail.value = config.letsencrypt_email;
  if (config.database_engine) el.databaseEngine.value = config.database_engine;
  if (config.db_name) el.dbName.value = config.db_name;
  if (config.db_user) el.dbUser.value = config.db_user;
  if (config.backup_dir) el.backupDir.value = config.backup_dir;
  if (config.backup_retention_days) el.backupRetentionDays.value = config.backup_retention_days;
  if (config.backup_hour) el.backupHour.value = config.backup_hour;
  if (config.inventory_host) el.inventoryHost.value = config.inventory_host;
  if (config.ssh_user) el.sshUser.value = config.ssh_user;
  if (config.winrm_transport) el.winrmTransport.value = config.winrm_transport;
  if (config.winrm_port) el.winrmPort.value = config.winrm_port;

  const provisioningSet = new Set(config.provisioning || []);
  document.querySelectorAll('input[name="provisioning"]').forEach((cb) => {
    if (!cb.disabled) cb.checked = provisioningSet.has(cb.value);
  });
  const deploymentSet = new Set(config.deployment || []);
  document.querySelectorAll('input[name="deployment"]').forEach((cb) => {
    if (!cb.disabled) cb.checked = deploymentSet.has(cb.value);
  });

  updateBuildCmdVisibility();
  updateSchematic();
}

function importConfig(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const config = JSON.parse(reader.result);
      applyImportedConfig(config);
      clearError();
    } catch (err) {
      showError("Fichier de config invalide : " + err.message);
    }
  };
  reader.readAsText(file);
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
document.querySelectorAll('input[name="deployment"], input[name="provisioning"]').forEach((cb) => {
  cb.addEventListener("change", updateBuildCmdVisibility);
});
document.querySelectorAll('input[name="provisioning"], input[name="deployment"]').forEach((cb) => {
  cb.addEventListener("change", updateSchematic);
});
el.inventoryHost.addEventListener("input", updateSchematic);

el.tabButtons.forEach((btn) => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});
el.layoutButtons.forEach((btn) => {
  btn.addEventListener("click", () => switchLayout(btn.dataset.layout));
});
el.loadExampleBtn.addEventListener("click", () => {
  el.groupsBuilder.innerHTML = "";
  GROUPS_EXAMPLE.forEach((group) => createGroupCard(group));
});
el.addGroupBtn.addEventListener("click", () => createGroupCard());
el.exportConfigBtn.addEventListener("click", exportConfig);
el.importConfigInput.addEventListener("change", (e) => {
  if (e.target.files && e.target.files[0]) {
    importConfig(e.target.files[0]);
    e.target.value = "";
  }
});
el.generateBtn.addEventListener("click", handleGenerate);
el.copyBtn.addEventListener("click", handleCopy);
el.downloadBtn.addEventListener("click", handleDownload);
el.downloadZipBtn.addEventListener("click", handleDownloadZip);

setTargetOs("linux");
updateBuildCmdVisibility();
updateSchematic();
createGroupCard(); // un premier groupe vide pour demarrer
