// ============================================================================
// web/static/authproxy/script.js
// Logique du module authproxy : bascule oauth2-proxy/authelia, presets,
// cartes d'utilisateurs et de regles d'acces, generation via
// /authproxy/api/generate, onglets multi-fichiers.
// ============================================================================

const CONFIG = window.OPSFORGE_AUTHPROXY || { engines: [], presets: {} };

const state = {
  engine: "oauth2-proxy",
  preset: "github-org",
  users: [],
  rules: [],
  files: [],
  activeFileIndex: 0,
};

const el = {
  engineSwitch: document.getElementById("engine-switch"),
  presetList: document.getElementById("preset-list"),
  presetHint: document.getElementById("preset-hint"),

  oauth2Form: document.getElementById("oauth2-form"),
  autheliaForm: document.getElementById("authelia-form"),

  o2Provider: document.getElementById("o2-provider"),
  o2Upstream: document.getElementById("o2-upstream"),
  o2CookieDomain: document.getElementById("o2-cookie-domain"),
  o2Redirect: document.getElementById("o2-redirect"),
  o2ClientId: document.getElementById("o2-client-id"),
  o2ClientSecret: document.getElementById("o2-client-secret"),
  o2GithubFields: document.getElementById("o2-github-fields"),
  o2GithubOrg: document.getElementById("o2-github-org"),
  o2GithubTeam: document.getElementById("o2-github-team"),
  o2OidcFields: document.getElementById("o2-oidc-fields"),
  o2OidcIssuer: document.getElementById("o2-oidc-issuer"),
  o2EmailFields: document.getElementById("o2-email-fields"),
  o2EmailDomains: document.getElementById("o2-email-domains"),

  auDomain: document.getElementById("au-domain"),
  auStorage: document.getElementById("au-storage"),
  auNotifier: document.getElementById("au-notifier"),
  userList: document.getElementById("user-list"),
  addUserBtn: document.getElementById("add-user-btn"),
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

  node1Label: document.getElementById("node-1-label"),
  applyNode: document.querySelector('.node[data-stage="apply"]'),
};

const DEFAULT_PRESET_BY_ENGINE = { "oauth2-proxy": "github-org", authelia: "homelab-simple" };

// ----------------------------------------------------------------------------
// Helpers de construction de champs (cartes utilisateurs / regles)
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
// Moteur
// ----------------------------------------------------------------------------
function setEngine(engine, { applyDefaultPreset = true } = {}) {
  state.engine = engine;
  el.engineSwitch.querySelectorAll(".engine-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.engine === engine);
  });
  el.oauth2Form.hidden = engine !== "oauth2-proxy";
  el.autheliaForm.hidden = engine !== "authelia";
  el.node1Label.textContent = engine === "oauth2-proxy" ? "OAUTH2-PROXY" : "AUTHELIA";

  renderPresetList();
  resetResultBox();

  if (applyDefaultPreset) applyPreset(DEFAULT_PRESET_BY_ENGINE[engine]);
}

// ----------------------------------------------------------------------------
// Presets (filtres selon le moteur actif)
// ----------------------------------------------------------------------------
function renderPresetList() {
  el.presetList.innerHTML = "";
  Object.entries(CONFIG.presets)
    .filter(([name, meta]) => meta.engine === state.engine && name !== "custom")
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

// Deux clics rapproches lancent deux requetes : sans ce jeton, la reponse
// la plus lente ecraserait le formulaire deja affiche.
let presetRequestId = 0;

async function applyPreset(name) {
  clearError();
  const requestId = ++presetRequestId;
  el.generateBtn.disabled = true;
  try {
    const res = await fetch(`/authproxy/api/preset/${encodeURIComponent(name)}`);
    const data = await res.json();
    if (requestId !== presetRequestId) return;
    if (!res.ok) {
      showError(data.error || "Preset introuvable.");
      return;
    }
    state.preset = name;
    if (data.engine && data.engine !== state.engine) {
      setEngine(data.engine, { applyDefaultPreset: false });
    }
    if (data.engine === "oauth2-proxy") {
      fillOauth2Form(data);
    } else {
      fillAutheliaForm(data);
    }
    markActivePreset(name);
  } catch (err) {
    showError("Impossible de contacter le serveur local.");
  } finally {
    if (requestId === presetRequestId) el.generateBtn.disabled = false;
  }
}

// ----------------------------------------------------------------------------
// Formulaire oauth2-proxy
// ----------------------------------------------------------------------------
function updateOauth2FieldsVisibility() {
  const provider = el.o2Provider.value;
  el.o2GithubFields.hidden = provider !== "github";
  el.o2OidcFields.hidden = provider !== "oidc";
  el.o2EmailFields.hidden = provider === "github";
}

function fillOauth2Form(config) {
  el.o2Provider.value = config.provider || "github";
  el.o2Upstream.value = config.upstream || "";
  el.o2CookieDomain.value = config.cookie_domain || "";
  el.o2Redirect.value = config.redirect_url || "";
  el.o2ClientId.value = config.client_id || "";
  el.o2ClientSecret.value = config.client_secret || "";
  el.o2GithubOrg.value = config.github_org || "";
  el.o2GithubTeam.value = config.github_team || "";
  el.o2OidcIssuer.value = config.oidc_issuer_url || "";
  el.o2EmailDomains.value = (config.email_domains || []).join(", ");
  updateOauth2FieldsVisibility();
}

function collectOauth2Payload() {
  const provider = el.o2Provider.value;
  const config = {
    preset: "custom",
    engine: "oauth2-proxy",
    provider,
    upstream: el.o2Upstream.value.trim(),
    cookie_domain: el.o2CookieDomain.value.trim(),
    redirect_url: el.o2Redirect.value.trim(),
    client_id: el.o2ClientId.value.trim(),
    client_secret: el.o2ClientSecret.value.trim(),
  };
  if (provider === "github") {
    config.github_org = el.o2GithubOrg.value.trim();
    const team = el.o2GithubTeam.value.trim();
    if (team) config.github_team = team;
  } else {
    config.email_domains = el.o2EmailDomains.value
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
    if (provider === "oidc") {
      config.oidc_issuer_url = el.o2OidcIssuer.value.trim();
    }
  }
  return config;
}

// ----------------------------------------------------------------------------
// Formulaire Authelia
// ----------------------------------------------------------------------------
function fillAutheliaForm(config) {
  el.auDomain.value = config.domain || "";
  el.auStorage.value = config.storage_backend || "sqlite";
  el.auNotifier.value = config.notifier || "filesystem";

  state.users = (config.users || []).map((u) => ({
    username: u.username || "",
    display_name: u.display_name || "",
    groups: (u.groups || []).join(", "),
  }));
  renderUserList();

  state.rules = (config.access_rules || []).map((r) => ({
    domain: r.domain || "",
    policy: r.policy || "one_factor",
    subject: r.subject || "",
  }));
  renderRuleList();
}

function renderUserList() {
  el.userList.innerHTML = "";
  state.users.forEach((user, index) => {
    const card = entryCard(
      user.username ? `Utilisateur : ${user.username}` : `Utilisateur #${index + 1}`,
      () => {
        state.users.splice(index, 1);
        renderUserList();
      },
      [
        grid([
          field("Nom d'utilisateur", textInput(user.username, "admin", (v) => { user.username = v; })),
          field("Nom affiché", textInput(user.display_name, "Admin", (v) => { user.display_name = v; })),
        ]),
        field("Groupes", textInput(user.groups, "admins, invites", (v) => { user.groups = v; })),
      ]
    );
    el.userList.appendChild(card);
  });

  if (!state.users.length) {
    const empty = document.createElement("p");
    empty.className = "field-hint";
    empty.textContent = "Aucun utilisateur pour l'instant : ajoutes-en un ci-dessous.";
    el.userList.appendChild(empty);
  }
}

function renderRuleList() {
  el.ruleList.innerHTML = "";
  state.rules.forEach((rule, index) => {
    const card = entryCard(
      rule.domain ? `Règle : ${rule.domain}` : `Règle #${index + 1}`,
      () => {
        state.rules.splice(index, 1);
        renderRuleList();
      },
      [
        grid([
          field("Domaine", textInput(rule.domain, "*.exemple.com", (v) => { rule.domain = v; })),
          field("Politique", selectInput(rule.policy, [
            ["bypass", "bypass — aucune authentification"],
            ["one_factor", "one_factor — mot de passe"],
            ["two_factor", "two_factor — mot de passe + MFA"],
            ["deny", "deny — toujours refusé"],
          ], (v) => { rule.policy = v; })),
        ]),
        field("Restreindre à (optionnel)", textInput(rule.subject, "group:admins", (v) => { rule.subject = v; })),
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

function collectAutheliaPayload() {
  const users = state.users
    .filter((u) => u.username.trim())
    .map((u) => ({
      username: u.username.trim(),
      display_name: u.display_name.trim() || undefined,
      groups: u.groups.split(",").map((g) => g.trim()).filter(Boolean),
    }));

  const rules = state.rules
    .filter((r) => r.domain.trim())
    .map((r) => {
      const rule = { domain: r.domain.trim(), policy: r.policy };
      if (r.subject.trim()) rule.subject = r.subject.trim();
      return rule;
    });

  return {
    preset: "custom",
    engine: "authelia",
    domain: el.auDomain.value.trim(),
    storage_backend: el.auStorage.value,
    notifier: el.auNotifier.value,
    users,
    access_rules: rules,
  };
}

// ----------------------------------------------------------------------------
// Generation
// ----------------------------------------------------------------------------
async function handleGenerate() {
  clearError();

  const payload = state.engine === "oauth2-proxy" ? collectOauth2Payload() : collectAutheliaPayload();

  el.generateBtn.disabled = true;
  el.generateBtn.textContent = "…";

  try {
    const res = await fetch("/authproxy/api/generate", {
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
      if (/^(location|access_control|authentication_backend|session|storage|notifier)/.test(line)) {
        return `<span class="conf-block">${line}</span>`;
      }
      const match = line.match(/^(\s*)([A-Za-z_][A-Za-z0-9_.]*)(:|\s*=)(\s*)(.*)$/);
      if (match) {
        const [, indent, key, sep, space, rest] = match;
        return `${indent}<span class="conf-key">${key}</span>${sep}${space}${rest}`;
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
el.engineSwitch.querySelectorAll(".engine-btn").forEach((btn) => {
  btn.addEventListener("click", () => setEngine(btn.dataset.engine));
});

el.o2Provider.addEventListener("change", updateOauth2FieldsVisibility);

el.addUserBtn.addEventListener("click", () => {
  state.users.push({ username: "", display_name: "", groups: "" });
  renderUserList();
});

el.addRuleBtn.addEventListener("click", () => {
  state.rules.push({ domain: "", policy: "one_factor", subject: "" });
  renderRuleList();
});

el.generateBtn.addEventListener("click", handleGenerate);
el.resetBtn.addEventListener("click", () => {
  setEngine("oauth2-proxy");
});
el.copyBtn.addEventListener("click", handleCopy);
el.downloadBtn.addEventListener("click", handleDownload);

setEngine("oauth2-proxy");
