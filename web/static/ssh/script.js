// ============================================================================
// web/static/ssh/script.js
// Logique du module ssh : bascule client/serveur, presets, cartes d'hotes et
// de cles autorisees, generation via /ssh/api/generate, onglets multi-fichiers.
// ============================================================================

const CONFIG = window.OPSFORGE_SSH || { roles: [], presets: {} };

const state = {
  role: "client",
  preset: "poste-de-travail",
  hosts: [],
  keys: [],
  files: [],
  activeFileIndex: 0,
};

const el = {
  roleSwitch: document.getElementById("role-switch"),
  presetList: document.getElementById("preset-list"),
  presetHint: document.getElementById("preset-hint"),

  clientForm: document.getElementById("client-form"),
  serverForm: document.getElementById("server-form"),

  hostList: document.getElementById("host-list"),
  addHostBtn: document.getElementById("add-host-btn"),
  keyList: document.getElementById("key-list"),
  addKeyBtn: document.getElementById("add-key-btn"),

  generateBtn: document.getElementById("generate-btn"),
  resetBtn: document.getElementById("reset-btn"),
  errorMsg: document.getElementById("error-msg"),

  fileTabs: document.getElementById("file-tabs"),
  resultBox: document.getElementById("result-box"),
  resultActions: document.getElementById("result-actions"),
  copyBtn: document.getElementById("copy-btn"),
  downloadBtn: document.getElementById("download-btn"),

  node1Label: document.getElementById("node-1-label"),
  applyNode: document.querySelector('.node[data-stage="apply"]'),
};

const DEFAULT_PRESET_BY_ROLE = { client: "poste-de-travail", server: "serveur-durci" };

// ----------------------------------------------------------------------------
// Petits helpers de construction de champs (evite 200 lignes de innerHTML)
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

function textInput(value, placeholder, onInput) {
  const input = document.createElement("input");
  input.type = "text";
  input.className = "text-input";
  input.value = value == null ? "" : value;
  if (placeholder) input.placeholder = placeholder;
  input.addEventListener("input", () => onInput(input.value));
  return input;
}

function numberInput(value, placeholder, onInput) {
  const input = document.createElement("input");
  input.type = "number";
  input.className = "text-input";
  input.value = value == null ? "" : value;
  if (placeholder) input.placeholder = placeholder;
  input.addEventListener("input", () => onInput(input.value));
  return input;
}

function textArea(value, placeholder, onInput) {
  const area = document.createElement("textarea");
  area.className = "text-input";
  area.value = value == null ? "" : value;
  if (placeholder) area.placeholder = placeholder;
  area.addEventListener("input", () => onInput(area.value));
  return area;
}

function checkboxRow(labelText, descText, checked, onChange) {
  const row = document.createElement("label");
  row.className = "toggle-row";

  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = Boolean(checked);
  box.addEventListener("change", () => onChange(box.checked));

  const span = document.createElement("span");
  span.className = "t-label";
  span.textContent = labelText;
  if (descText) {
    const desc = document.createElement("span");
    desc.className = "t-desc";
    desc.textContent = descText;
    span.appendChild(desc);
  }

  row.appendChild(box);
  row.appendChild(span);
  return row;
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
// Role
// ----------------------------------------------------------------------------
function setRole(role, { applyDefaultPreset = true } = {}) {
  state.role = role;
  el.roleSwitch.querySelectorAll(".role-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.role === role);
  });
  el.clientForm.hidden = role !== "client";
  el.serverForm.hidden = role !== "server";
  el.node1Label.textContent = role === "client" ? "CLIENT" : "SERVEUR";

  renderPresetList();
  resetResultBox();

  if (applyDefaultPreset) applyPreset(DEFAULT_PRESET_BY_ROLE[role]);
}

// ----------------------------------------------------------------------------
// Presets (filtres selon le role actif)
// ----------------------------------------------------------------------------
function renderPresetList() {
  el.presetList.innerHTML = "";
  // "custom" n'est pas un point de depart affichable : c'est le preset
  // implicite envoye a l'API quand on genere depuis le formulaire.
  Object.entries(CONFIG.presets)
    .filter(([name, meta]) => meta.role === state.role && name !== "custom")
    .forEach(([name, meta]) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "preset-chip";
      chip.textContent = name;
      chip.title = meta.label;
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
  const meta = CONFIG.presets[name];
  el.presetHint.textContent = meta
    ? meta.label
    : "Choisis un point de départ, puis ajuste les champs ci-dessous.";
}

// Deux clics rapproches (Client puis Serveur) lancent deux requetes : sans
// ce jeton, la reponse la plus lente ecraserait le formulaire deja affiche.
let presetRequestId = 0;

async function applyPreset(name) {
  clearError();
  const requestId = ++presetRequestId;
  // Le formulaire n'est pas encore garni : un clic sur GENERER pendant ce
  // court instant ne produirait rien du tout.
  el.generateBtn.disabled = true;
  try {
    const res = await fetch(`/ssh/api/preset/${encodeURIComponent(name)}`);
    const data = await res.json();
    if (requestId !== presetRequestId) return;
    if (!res.ok) {
      showError(data.error || "Preset introuvable.");
      return;
    }
    state.preset = name;
    if (data.role && data.role !== state.role) {
      setRole(data.role, { applyDefaultPreset: false });
    }
    if (data.role === "client") {
      fillClientForm(data);
    } else {
      fillServerForm(data);
    }
    markActivePreset(name);
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  } finally {
    // Seule la requete la plus recente rend la main : sinon une reponse
    // tardive reactiverait le bouton pendant qu'un autre preset charge.
    if (requestId === presetRequestId) el.generateBtn.disabled = false;
  }
}

// ----------------------------------------------------------------------------
// Formulaire client : hotes + reglages communs
// ----------------------------------------------------------------------------
function fillClientForm(config) {
  state.hosts = (config.hosts || []).map((host) => ({
    alias: host.alias || "",
    hostname: host.hostname || "",
    user: host.user || "",
    port: host.port || "",
    identity_file: host.identity_file || "",
    proxy_jump: host.proxy_jump || "",
    local_forwards: (host.local_forwards || []).join(", "),
    dynamic_forward: host.dynamic_forward || "",
    forward_agent: Boolean(host.forward_agent),
  }));
  renderHostList();

  const defaults = config.defaults || {};
  document.getElementById("def-keepalive").checked = Boolean(defaults.server_alive_interval);
  document.getElementById("def-add-keys").checked = Boolean(defaults.add_keys_to_agent);
  document.getElementById("def-identities-only").checked = Boolean(defaults.identities_only);
  document.getElementById("def-hash-known-hosts").checked = Boolean(defaults.hash_known_hosts);
  document.getElementById("def-control-master").checked = Boolean(defaults.control_master);
  document.getElementById("def-compression").checked = Boolean(defaults.compression);
  document.getElementById("def-forward-agent").checked = Boolean(defaults.forward_agent);
}

function renderHostList() {
  el.hostList.innerHTML = "";
  state.hosts.forEach((host, index) => {
    const card = entryCard(
      host.alias ? `Hôte : ${host.alias}` : `Hôte #${index + 1}`,
      () => {
        state.hosts.splice(index, 1);
        renderHostList();
      },
      [
        grid([
          field("Alias (ce que tu tapes)", textInput(host.alias, "prod-web", (v) => { host.alias = v; })),
          field("Hôte réel (DNS ou IP)", textInput(host.hostname, "203.0.113.10", (v) => { host.hostname = v; })),
        ]),
        grid([
          field("Utilisateur", textInput(host.user, "deploy", (v) => { host.user = v; })),
          field("Port", numberInput(host.port, "22", (v) => { host.port = v; })),
        ]),
        field("Clé privée à utiliser", textInput(host.identity_file, "~/.ssh/id_ed25519_prod", (v) => { host.identity_file = v; })),
        grid([
          field("Rebond via (ProxyJump)", textInput(host.proxy_jump, "bastion", (v) => { host.proxy_jump = v; })),
          field("Proxy SOCKS local (DynamicForward)", numberInput(host.dynamic_forward, "1080", (v) => { host.dynamic_forward = v; })),
        ]),
        field(
          "Tunnels locaux (LocalForward)",
          textInput(host.local_forwards, "5432:localhost:5432, 8080:localhost:80", (v) => { host.local_forwards = v; })
        ),
        checkboxRow(
          "Transférer l'agent SSH vers cet hôte",
          "ForwardAgent — uniquement vers un serveur de confiance",
          host.forward_agent,
          (checked) => { host.forward_agent = checked; }
        ),
      ]
    );
    el.hostList.appendChild(card);
  });

  if (!state.hosts.length) {
    const empty = document.createElement("p");
    empty.className = "field-hint";
    empty.textContent = "Aucun hôte pour l'instant : ajoutes-en un ci-dessous.";
    el.hostList.appendChild(empty);
  }
}

function collectClientPayload() {
  const hosts = state.hosts.map((host) => {
    const entry = {
      alias: host.alias.trim(),
      hostname: host.hostname.trim(),
    };
    if (host.user.trim()) entry.user = host.user.trim();
    if (String(host.port).trim()) entry.port = Number(host.port);
    if (host.identity_file.trim()) entry.identity_file = host.identity_file.trim();
    if (host.proxy_jump.trim()) entry.proxy_jump = host.proxy_jump.trim();
    if (host.forward_agent) entry.forward_agent = true;

    const forwards = String(host.local_forwards)
      .split(",")
      .map((f) => f.trim())
      .filter(Boolean);
    if (forwards.length) {
      entry.local_forwards = forwards;
      entry.exit_on_forward_failure = true;
    }
    if (String(host.dynamic_forward).trim()) {
      entry.dynamic_forward = Number(host.dynamic_forward);
    }
    return entry;
  });

  const keepalive = document.getElementById("def-keepalive").checked;
  const defaults = {
    add_keys_to_agent: document.getElementById("def-add-keys").checked,
    identities_only: document.getElementById("def-identities-only").checked,
    hash_known_hosts: document.getElementById("def-hash-known-hosts").checked,
    control_master: document.getElementById("def-control-master").checked,
    compression: document.getElementById("def-compression").checked,
    forward_agent: document.getElementById("def-forward-agent").checked,
  };
  if (keepalive) {
    defaults.server_alive_interval = 60;
    defaults.server_alive_count_max = 3;
  }

  return { preset: "custom", role: "client", hosts, defaults };
}

// ----------------------------------------------------------------------------
// Formulaire serveur
// ----------------------------------------------------------------------------
function fillServerForm(config) {
  document.getElementById("srv-port").value = config.port || 22;
  document.getElementById("srv-permit-root").value = config.permit_root_login || "no";
  document.getElementById("srv-pubkey-auth").checked = config.pubkey_authentication !== false;
  document.getElementById("srv-password-auth").checked = Boolean(config.password_authentication);
  document.getElementById("srv-allow-groups").value = (config.allow_groups || []).join(", ");
  document.getElementById("srv-allow-users").value = (config.allow_users || []).join(", ");
  document.getElementById("srv-max-auth-tries").value = config.max_auth_tries ?? 3;
  document.getElementById("srv-login-grace").value = config.login_grace_time ?? 30;
  document.getElementById("srv-alive-interval").value = config.client_alive_interval ?? 300;
  document.getElementById("srv-tcp-forwarding").value = String(config.allow_tcp_forwarding ?? "no");
  document.getElementById("srv-agent-forwarding").checked = Boolean(config.allow_agent_forwarding);
  document.getElementById("srv-x11").checked = Boolean(config.x11_forwarding);
  document.getElementById("srv-modern-crypto").checked = config.modern_crypto !== false;
  document.getElementById("srv-banner").value = config.banner || "";
  document.getElementById("srv-sftp-group").value = config.sftp_only_group || "";
  document.getElementById("srv-sftp-chroot").value = config.sftp_chroot_dir || "";

  state.keys = (config.authorized_keys || []).map((entry) => ({
    comment: entry.comment || "",
    key: entry.key || "",
    from: (entry.from || []).join(", "),
    command: entry.command || "",
    restrict: Boolean(entry.restrict),
    no_agent_forwarding: Boolean(entry.no_agent_forwarding),
  }));
  renderKeyList();
}

function renderKeyList() {
  el.keyList.innerHTML = "";
  state.keys.forEach((entry, index) => {
    const card = entryCard(
      entry.comment ? `Clé : ${entry.comment}` : `Clé #${index + 1}`,
      () => {
        state.keys.splice(index, 1);
        renderKeyList();
      },
      [
        field("Description (commentaire)", textInput(entry.comment, "clé du runner CI", (v) => { entry.comment = v; })),
        field("Clé publique (une ligne)", textArea(entry.key, "ssh-ed25519 AAAAC3... tom@laptop", (v) => { entry.key = v; })),
        grid([
          field("Adresses autorisées (from=)", textInput(entry.from, "203.0.113.0/24", (v) => { entry.from = v; })),
          field("Commande forcée (command=)", textInput(entry.command, "/usr/local/bin/deploy.sh", (v) => { entry.command = v; })),
        ]),
        checkboxRow(
          "Tout restreindre (restrict)",
          "Coupe TTY, forwarding et agent — la clé ne sert plus qu'à sa commande",
          entry.restrict,
          (checked) => { entry.restrict = checked; }
        ),
        checkboxRow(
          "Interdire le transfert d'agent",
          "no-agent-forwarding — inutile si « Tout restreindre » est coché",
          entry.no_agent_forwarding,
          (checked) => { entry.no_agent_forwarding = checked; }
        ),
      ]
    );
    el.keyList.appendChild(card);
  });

  if (!state.keys.length) {
    const empty = document.createElement("p");
    empty.className = "field-hint";
    empty.textContent = "Aucune clé : seul le fragment sshd sera généré.";
    el.keyList.appendChild(empty);
  }
}

function splitList(value) {
  return value
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

function collectServerPayload() {
  const config = {
    preset: "custom",
    role: "server",
    port: Number(document.getElementById("srv-port").value || 22),
    permit_root_login: document.getElementById("srv-permit-root").value,
    pubkey_authentication: document.getElementById("srv-pubkey-auth").checked,
    password_authentication: document.getElementById("srv-password-auth").checked,
    kbd_interactive_authentication: false,
    permit_empty_passwords: false,
    max_auth_tries: Number(document.getElementById("srv-max-auth-tries").value || 3),
    login_grace_time: Number(document.getElementById("srv-login-grace").value || 30),
    client_alive_interval: Number(document.getElementById("srv-alive-interval").value || 300),
    client_alive_count_max: 2,
    allow_tcp_forwarding: document.getElementById("srv-tcp-forwarding").value,
    allow_agent_forwarding: document.getElementById("srv-agent-forwarding").checked,
    x11_forwarding: document.getElementById("srv-x11").checked,
    modern_crypto: document.getElementById("srv-modern-crypto").checked,
    gateway_ports: false,
    permit_tunnel: false,
    use_dns: false,
    log_level: "VERBOSE",
  };

  const allowGroups = splitList(document.getElementById("srv-allow-groups").value);
  if (allowGroups.length) config.allow_groups = allowGroups;
  const allowUsers = splitList(document.getElementById("srv-allow-users").value);
  if (allowUsers.length) config.allow_users = allowUsers;

  const banner = document.getElementById("srv-banner").value.trim();
  if (banner) config.banner = banner;

  const sftpGroup = document.getElementById("srv-sftp-group").value.trim();
  if (sftpGroup) {
    config.sftp_only_group = sftpGroup;
    const chroot = document.getElementById("srv-sftp-chroot").value.trim();
    if (chroot) config.sftp_chroot_dir = chroot;
  }

  const keys = state.keys
    .filter((entry) => entry.key.trim())
    .map((entry) => {
      const out = { key: entry.key.trim().replace(/\s*\n\s*/g, " ") };
      if (entry.comment.trim()) out.comment = entry.comment.trim();
      const from = splitList(entry.from);
      if (from.length) out.from = from;
      if (entry.command.trim()) out.command = entry.command.trim();
      if (entry.restrict) out.restrict = true;
      if (entry.no_agent_forwarding) out.no_agent_forwarding = true;
      return out;
    });
  if (keys.length) config.authorized_keys = keys;

  return config;
}

// ----------------------------------------------------------------------------
// Generation
// ----------------------------------------------------------------------------
async function handleGenerate() {
  clearError();

  const payload = state.role === "client" ? collectClientPayload() : collectServerPayload();

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "…";

  try {
    const res = await fetch("/ssh/api/generate", {
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
      if (/^(Host|Match)\s/.test(line)) return `<span class="conf-block">${line}</span>`;
      const match = line.match(/^(\s*)([A-Za-z][A-Za-z0-9]*)(\s+)(.*)$/);
      if (match) {
        const [, indent, key, space, rest] = match;
        return `${indent}<span class="conf-key">${key}</span>${space}${rest}`;
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
  // Le nom de fichier porte le dossier de destination (sshd_config.d/…) :
  // on ne garde que la derniere partie pour le telechargement.
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
el.roleSwitch.querySelectorAll(".role-btn").forEach((btn) => {
  btn.addEventListener("click", () => setRole(btn.dataset.role));
});

el.addHostBtn.addEventListener("click", () => {
  state.hosts.push({
    alias: "",
    hostname: "",
    user: "",
    port: "",
    identity_file: "",
    proxy_jump: "",
    local_forwards: "",
    dynamic_forward: "",
    forward_agent: false,
  });
  renderHostList();
});

el.addKeyBtn.addEventListener("click", () => {
  state.keys.push({
    comment: "",
    key: "",
    from: "",
    command: "",
    restrict: false,
    no_agent_forwarding: false,
  });
  renderKeyList();
});

el.generateBtn.addEventListener("click", handleGenerate);
el.resetBtn.addEventListener("click", () => {
  setRole("client");
});
el.copyBtn.addEventListener("click", handleCopy);
el.downloadBtn.addEventListener("click", handleDownload);

setRole("client");
