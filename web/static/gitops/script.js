// Module GitOps — ArgoCD Application / FluxCD (GitRepository + Kustomization|HelmRelease) -> /gitops/api/generate

const $ = (id) => document.getElementById(id);

let currentTool = "argocd";

function parseJSONField(id, label, arrayMode) {
  const raw = ($(id).value || "").trim();
  if (!raw) return arrayMode ? [] : {};
  try {
    return JSON.parse(raw);
  } catch (e) {
    throw new Error(`${label} : JSON invalide (${e.message})`);
  }
}

function updateFieldsVisibility() {
  const sourceType = $("source-type-select").value;
  $("helm-fields").hidden = sourceType !== "helm";

  $("argocd-only-fields").hidden = currentTool !== "argocd";
  $("flux-only-fields").hidden = currentTool !== "flux";
}

function switchTool(tool) {
  currentTool = tool;
  document.querySelectorAll(".tool-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.tool === tool);
  });
  updateFieldsVisibility();
}

function buildConfig() {
  const sourceType = $("source-type-select").value;
  const autoSync = $("auto-sync").value === "true";

  const config = {
    tool: currentTool,
    app_name: $("app-name").value.trim(),
    namespace: $("namespace").value.trim(),
    repo_url: $("repo-url").value.trim(),
    path: $("path").value.trim() || ".",
    revision: $("revision").value.trim() || "main",
    source_type: sourceType,
    auto_sync: autoSync,
    self_heal: autoSync,
    prune: autoSync,
    create_namespace: $("create-namespace").value === "true",
  };

  if (currentTool === "argocd") {
    config.project = $("project").value.trim() || "default";
    config.dest_server = $("dest-server").value.trim() || "https://kubernetes.default.svc";
  } else {
    config.interval = $("interval").value.trim() || "5m";
  }

  if (sourceType === "helm") {
    config.helm_chart_name = $("helm-chart-name").value.trim();
    const valueFiles = parseJSONField("helm-value-files", "Fichiers de valeurs Helm", true);
    const values = parseJSONField("helm-values", "Valeurs Helm inline", false);
    if (valueFiles.length) config.helm_value_files = valueFiles;
    if (Object.keys(values).length) config.helm_values = values;
  }

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
    res = await fetch("/gitops/api/generate", {
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
    res = await fetch("/gitops/api/download", {
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
  a.download = "gitops-manifests.zip";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function loadPreset(nom) {
  if (!nom) return;
  let cfg;
  try {
    const res = await fetch(`/gitops/api/preset/${nom}`);
    cfg = await res.json();
  } catch (e) {
    return show("error", "Preset injoignable : " + e.message);
  }

  switchTool(cfg.tool || "argocd");
  $("app-name").value = cfg.app_name || "";
  $("namespace").value = cfg.namespace || "";
  $("repo-url").value = cfg.repo_url || "";
  $("path").value = cfg.path || ".";
  $("revision").value = cfg.revision || "main";
  $("source-type-select").value = cfg.source_type || "raw";
  $("project").value = cfg.project || "default";
  $("dest-server").value = cfg.dest_server || "https://kubernetes.default.svc";
  $("interval").value = cfg.interval || "5m";
  $("auto-sync").value = cfg.auto_sync === false ? "false" : "true";
  $("create-namespace").value = cfg.create_namespace === false ? "false" : "true";
  $("helm-chart-name").value = cfg.helm_chart_name || "";
  $("helm-value-files").value = cfg.helm_value_files ? JSON.stringify(cfg.helm_value_files, null, 2) : "";
  $("helm-values").value = cfg.helm_values ? JSON.stringify(cfg.helm_values, null, 2) : "";

  updateFieldsVisibility();
}

// ---- Init ----
document.querySelectorAll(".tool-btn").forEach((b) => {
  b.addEventListener("click", () => switchTool(b.dataset.tool));
});
$("generate-btn").addEventListener("click", generer);
$("download-zip-btn").addEventListener("click", telechargerZip);
$("source-type-select").addEventListener("change", updateFieldsVisibility);
$("preset-select").addEventListener("change", (e) => loadPreset(e.target.value));
$("copy-btn").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("output").textContent);
    const b = $("copy-btn"); const t = b.innerHTML;
    b.innerHTML = "✓ Copié"; setTimeout(() => (b.innerHTML = t), 1500);
  } catch (e) {}
});

updateFieldsVisibility();
