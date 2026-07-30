// Module Vault — config.hcl + policies/*.hcl + bootstrap.sh -> /vault/api/generate

const $ = (id) => document.getElementById(id);

function parseJSONField(id, label, arrayMode) {
  const raw = ($(id).value || "").trim();
  if (!raw) return arrayMode ? [] : {};
  try {
    return JSON.parse(raw);
  } catch (e) {
    throw new Error(`${label} : JSON invalide (${e.message})`);
  }
}

function updateSealArgsVisibility() {
  const seal = $("seal-select").value;
  $("seal-args-field").hidden = seal === "shamir";
}

function updateTlsFields() {
  // Rien de plus a afficher pour l'instant : cert_file/key_file utilisent
  // des chemins par defaut cote serveur si TLS est active sans les fournir.
}

function buildConfig() {
  const storage = $("storage-select").value;
  const storageArgs = parseJSONField("storage-args", "Arguments du storage");
  const seal = $("seal-select").value;
  const sealArgs = seal === "shamir" ? {} : parseJSONField("seal-args", "Arguments du seal");

  const server = {
    storage,
    storage_args: storageArgs,
    listener_address: $("listener-address").value.trim() || "0.0.0.0:8200",
    listener_tls_disable: $("tls-disable").value === "true",
    seal,
    seal_args: sealArgs,
    ui: $("ui-toggle").value === "true",
  };

  const config = { server };

  const policies = parseJSONField("policies", "Policies", true);
  const authMethods = parseJSONField("auth-methods", "Méthodes d'authentification", true);
  const secretsEngines = parseJSONField("secrets-engines", "Moteurs de secrets", true);
  const auditDevices = parseJSONField("audit-devices", "Périphériques d'audit", true);

  if (policies.length) config.policies = policies;
  if (authMethods.length) config.auth_methods = authMethods;
  if (secretsEngines.length) config.secrets_engines = secretsEngines;
  if (auditDevices.length) config.audit_devices = auditDevices;

  return config;
}

function show(id, msg) { const e = $(id); e.textContent = msg; e.hidden = false; }
function hide(id) { $(id).hidden = true; }

function renderFiles(files) {
  const parts = Object.entries(files).map(([nom, contenu]) => `# --- ${nom} ---\n${contenu}`);
  return parts.join("\n\n");
}

async function generer() {
  hide("error");
  let config;
  try {
    config = buildConfig();
  } catch (e) {
    return show("error", e.message);
  }

  let res, data;
  try {
    res = await fetch("/vault/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    data = await res.json();
  } catch (e) {
    return show("error", "Serveur injoignable : " + e.message);
  }

  if (!res.ok) return show("error", data.error || "Erreur de génération.");

  $("output").textContent = renderFiles(data.files);
  $("copy-btn").hidden = false;
}

async function telechargerZip() {
  hide("error");
  let config;
  try {
    config = buildConfig();
  } catch (e) {
    return show("error", e.message);
  }

  let res;
  try {
    res = await fetch("/vault/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
  } catch (e) {
    return show("error", "Serveur injoignable : " + e.message);
  }

  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    return show("error", data.error || "Erreur de génération du .zip.");
  }

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "vault-project.zip";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function loadPreset(nom) {
  if (!nom) return;
  let cfg;
  try {
    const res = await fetch(`/vault/api/preset/${nom}`);
    cfg = await res.json();
  } catch (e) {
    return show("error", "Preset injoignable : " + e.message);
  }

  const server = cfg.server || {};
  $("storage-select").value = server.storage || "file";
  $("storage-args").value = JSON.stringify(server.storage_args || {}, null, 2);
  $("listener-address").value = server.listener_address || "0.0.0.0:8200";
  $("tls-disable").value = server.listener_tls_disable ? "true" : "false";
  $("seal-select").value = server.seal || "shamir";
  $("seal-args").value = JSON.stringify(server.seal_args || {}, null, 2);
  $("ui-toggle").value = server.ui === false ? "false" : "true";
  updateSealArgsVisibility();

  $("policies").value = cfg.policies ? JSON.stringify(cfg.policies, null, 2) : "";
  $("auth-methods").value = cfg.auth_methods ? JSON.stringify(cfg.auth_methods, null, 2) : "";
  $("secrets-engines").value = cfg.secrets_engines ? JSON.stringify(cfg.secrets_engines, null, 2) : "";
  $("audit-devices").value = cfg.audit_devices ? JSON.stringify(cfg.audit_devices, null, 2) : "";
}

// ---- Init ----
$("generate-btn").addEventListener("click", generer);
$("download-zip-btn").addEventListener("click", telechargerZip);
$("seal-select").addEventListener("change", updateSealArgsVisibility);
$("preset-select").addEventListener("change", (e) => loadPreset(e.target.value));
$("copy-btn").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("output").textContent);
    const b = $("copy-btn"); const t = b.innerHTML;
    b.innerHTML = "✓ Copié"; setTimeout(() => (b.innerHTML = t), 1500);
  } catch (e) {}
});

updateSealArgsVisibility();
