// Module Backup — restic / Borg -> /backup/api/generate

const $ = (id) => document.getElementById(id);

let currentTool = "restic";

function linesToArray(id) {
  return ($(id).value || "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}

function updateFieldsVisibility() {
  const backend = $("repo-backend-select").value;
  $("sftp-fields").hidden = backend !== "sftp";
  $("s3-fields").hidden = backend !== "s3";

  const scheduler = $("scheduler-select").value;
  $("oncalendar-field").hidden = scheduler !== "systemd";
  $("cron-field").hidden = scheduler !== "cron";
}

function switchTool(tool) {
  currentTool = tool;
  document.querySelectorAll(".tool-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.tool === tool);
  });
  // Borg ne gere pas le backend S3
  const s3Option = $("repo-backend-select").querySelector('option[value="s3"]');
  if (s3Option) {
    s3Option.hidden = tool === "borg";
    if (tool === "borg" && $("repo-backend-select").value === "s3") {
      $("repo-backend-select").value = "local";
      updateFieldsVisibility();
    }
  }
}

function show(id, msg) { const e = $(id); e.textContent = msg; e.hidden = false; }
function hide(id) { $(id).hidden = true; }

function buildConfig() {
  const config = {
    tool: currentTool,
    app_name: $("app-name").value.trim(),
    repo_backend: $("repo-backend-select").value,
    repo_path: $("repo-path").value.trim(),
    source_paths: linesToArray("source-paths"),
    exclude_patterns: linesToArray("exclude-patterns"),
    passphrase_env_var: $("passphrase-var").value.trim() || "BACKUP_PASSPHRASE",
    scheduler: $("scheduler-select").value,
    retention: {
      keep_daily: parseInt($("keep-daily").value, 10) || 0,
      keep_weekly: parseInt($("keep-weekly").value, 10) || 0,
      keep_monthly: parseInt($("keep-monthly").value, 10) || 0,
      keep_yearly: parseInt($("keep-yearly").value, 10) || 0,
    },
  };

  if (config.repo_backend === "sftp") {
    config.sftp_host = $("sftp-host").value.trim();
    config.sftp_user = $("sftp-user").value.trim();
  }
  if (config.repo_backend === "s3") {
    config.s3_bucket = $("s3-bucket").value.trim();
    config.s3_endpoint = $("s3-endpoint").value.trim() || "s3.amazonaws.com";
  }
  if (config.scheduler === "systemd") {
    config.schedule_oncalendar = $("schedule-oncalendar").value.trim() || "*-*-* 03:00:00";
  } else {
    config.schedule_cron = $("schedule-cron").value.trim() || "0 3 * * *";
  }
  const webhook = $("notify-webhook").value.trim();
  if (webhook) config.notify_webhook_url = webhook;

  return config;
}

function renderFiles(files) {
  return Object.entries(files).map(([nom, contenu]) => `# --- ${nom} ---\n${contenu}`).join("\n\n");
}

async function generer() {
  hide("error");
  const config = buildConfig();

  let res, data;
  try {
    res = await fetch("/backup/api/generate", {
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
  const config = buildConfig();

  let res;
  try {
    res = await fetch("/backup/api/download", {
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
  a.download = "opsforge-backup.zip";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function loadPreset(nom) {
  if (!nom) return;
  let cfg;
  try {
    const res = await fetch(`/backup/api/preset/${nom}`);
    cfg = await res.json();
  } catch (e) {
    return show("error", "Preset injoignable : " + e.message);
  }

  switchTool(cfg.tool || "restic");
  $("app-name").value = cfg.app_name || "";
  $("repo-backend-select").value = cfg.repo_backend || "local";
  $("repo-path").value = cfg.repo_path || "";
  $("source-paths").value = (cfg.source_paths || []).join("\n");
  $("exclude-patterns").value = (cfg.exclude_patterns || []).join("\n");
  $("passphrase-var").value = cfg.passphrase_env_var || "BACKUP_PASSPHRASE";
  $("scheduler-select").value = cfg.scheduler || "systemd";
  $("schedule-oncalendar").value = cfg.schedule_oncalendar || "*-*-* 03:00:00";
  $("schedule-cron").value = cfg.schedule_cron || "0 3 * * *";
  $("sftp-host").value = cfg.sftp_host || "";
  $("sftp-user").value = cfg.sftp_user || "";
  $("s3-bucket").value = cfg.s3_bucket || "";
  $("s3-endpoint").value = cfg.s3_endpoint || "s3.amazonaws.com";
  $("notify-webhook").value = cfg.notify_webhook_url || "";

  const retention = cfg.retention || {};
  $("keep-daily").value = retention.keep_daily ?? 7;
  $("keep-weekly").value = retention.keep_weekly ?? 4;
  $("keep-monthly").value = retention.keep_monthly ?? 6;
  $("keep-yearly").value = retention.keep_yearly ?? 0;

  updateFieldsVisibility();
}

// ---- Init ----
document.querySelectorAll(".tool-btn").forEach((b) => {
  b.addEventListener("click", () => switchTool(b.dataset.tool));
});
$("generate-btn").addEventListener("click", generer);
$("download-zip-btn").addEventListener("click", telechargerZip);
$("repo-backend-select").addEventListener("change", updateFieldsVisibility);
$("scheduler-select").addEventListener("change", updateFieldsVisibility);
$("preset-select").addEventListener("change", (e) => loadPreset(e.target.value));
$("copy-btn").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("output").textContent);
    const b = $("copy-btn"); const t = b.innerHTML;
    b.innerHTML = "✓ Copié"; setTimeout(() => (b.innerHTML = t), 1500);
  } catch (e) {}
});

updateFieldsVisibility();
