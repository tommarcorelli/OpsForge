// Module Terraform — builder de ressources + presets -> /terraform/api/generate

const $ = (id) => document.getElementById(id);
const CATALOG = window.TF_CATALOG || {};

// État : liste de ressources { type, name, args (chaîne JSON) }
let resources = [];

function catalogFor(provider) {
  return CATALOG[provider] || [];
}

function templateFor(provider, type) {
  const entry = catalogFor(provider).find((e) => e.type === type);
  return entry ? JSON.stringify(entry.template, null, 2) : "{}";
}

function typeOptions(provider, selected) {
  const entries = catalogFor(provider);
  let html = entries
    .map((e) => `<option value="${e.type}" ${e.type === selected ? "selected" : ""}>${e.label} — ${e.type}</option>`)
    .join("");
  // Type personnalisé (hors catalogue) : on le garde
  if (selected && !entries.some((e) => e.type === selected)) {
    html += `<option value="${selected}" selected>${selected} (personnalisé)</option>`;
  }
  html += `<option value="__custom__">Autre type…</option>`;
  return html;
}

function renderResources() {
  const provider = $("provider").value;
  const box = $("resources-builder");
  if (resources.length === 0) {
    box.innerHTML = `<p class="empty">Aucune ressource. Clique sur « Ajouter » ou charge un preset.</p>`;
    return;
  }
  box.innerHTML = resources
    .map(
      (r, i) => `
    <div class="res-card" data-i="${i}">
      <div class="res-head">
        <select class="res-type" data-i="${i}">${typeOptions(provider, r.type)}</select>
        <input class="res-name" data-i="${i}" value="${r.name || ""}" placeholder="nom (ex: web)" />
        <button type="button" class="res-remove" data-i="${i}" title="Supprimer">✕</button>
      </div>
      <textarea class="res-args" data-i="${i}" rows="5" spellcheck="false">${r.args || "{}"}</textarea>
    </div>`
    )
    .join("");

  box.querySelectorAll(".res-type").forEach((el) =>
    el.addEventListener("change", () => onTypeChange(+el.dataset.i, el.value))
  );
  box.querySelectorAll(".res-name").forEach((el) =>
    el.addEventListener("input", () => (resources[+el.dataset.i].name = el.value))
  );
  box.querySelectorAll(".res-args").forEach((el) =>
    el.addEventListener("input", () => (resources[+el.dataset.i].args = el.value))
  );
  box.querySelectorAll(".res-remove").forEach((el) =>
    el.addEventListener("click", () => {
      resources.splice(+el.dataset.i, 1);
      renderResources();
    })
  );
}

function onTypeChange(i, value) {
  const provider = $("provider").value;
  if (value === "__custom__") {
    const t = prompt("Type de ressource Terraform (ex: aws_lb) :", resources[i].type || "");
    resources[i].type = (t || "").trim();
    renderResources();
    return;
  }
  resources[i].type = value;
  // Préremplit les arguments avec le template du catalogue si le champ est vide/trivial
  const current = (resources[i].args || "").trim();
  if (current === "" || current === "{}" ) {
    resources[i].args = templateFor(provider, value);
  }
  renderResources();
}

function addResource() {
  const provider = $("provider").value;
  const first = catalogFor(provider)[0];
  const type = first ? first.type : "";
  resources.push({ type, name: "", args: first ? JSON.stringify(first.template, null, 2) : "{}" });
  renderResources();
}

function parseJSONField(id, label, arrayMode) {
  const raw = ($(id).value || "").trim();
  if (!raw) return arrayMode ? [] : {};
  try {
    return JSON.parse(raw);
  } catch (e) {
    throw new Error(`${label} : JSON invalide (${e.message})`);
  }
}

function buildConfig() {
  const config = {
    provider: $("provider").value,
    provider_config: parseJSONField("provider-config", "Configuration du provider"),
    resources: resources.map((r) => {
      let args = {};
      const raw = (r.args || "").trim();
      if (raw) {
        try {
          args = JSON.parse(raw);
        } catch (e) {
          throw new Error(`Ressource « ${r.name || r.type} » : arguments JSON invalides (${e.message})`);
        }
      }
      return { type: r.type, name: r.name, args };
    }),
  };
  const vars = parseJSONField("variables", "Variables");
  const outs = parseJSONField("outputs", "Outputs");
  if (Object.keys(vars).length) config.variables = vars;
  if (Object.keys(outs).length) config.outputs = outs;
  return config;
}

function show(id, msg) { const e = $(id); e.textContent = msg; e.hidden = false; }
function hide(id) { $(id).hidden = true; }

async function generer() {
  hide("error"); hide("warn");
  let config;
  try {
    config = buildConfig();
  } catch (e) {
    return show("error", e.message);
  }

  let res, data;
  try {
    res = await fetch("/terraform/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(config),
    });
    data = await res.json();
  } catch (e) {
    return show("error", "Serveur injoignable : " + e.message);
  }

  if (!res.ok) return show("error", data.error || "Erreur de génération.");

  $("output").textContent = data.terraform;
  $("copy-btn").hidden = false;
  if (data.avertissements && data.avertissements.length) {
    show("warn", "⚠ " + data.avertissements.join(" · "));
  }
}

async function loadPreset(nom) {
  if (!nom) return;
  let cfg;
  try {
    const res = await fetch(`/terraform/api/preset/${nom}`);
    cfg = await res.json();
  } catch (e) {
    return show("error", "Preset injoignable : " + e.message);
  }
  $("provider").value = cfg.provider || "aws";
  $("provider-config").value = JSON.stringify(cfg.provider_config || {}, null, 2);
  resources = (cfg.resources || []).map((r) => ({
    type: r.type, name: r.name, args: JSON.stringify(r.args || {}, null, 2),
  }));
  $("variables").value = cfg.variables ? JSON.stringify(cfg.variables, null, 2) : "";
  $("outputs").value = cfg.outputs ? JSON.stringify(cfg.outputs, null, 2) : "";
  renderResources();
}

// ---- Init ----
$("add-resource-btn").addEventListener("click", addResource);
$("generate-btn").addEventListener("click", generer);
$("provider").addEventListener("change", renderResources);
$("preset-select").addEventListener("change", (e) => loadPreset(e.target.value));
$("copy-btn").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("output").textContent);
    const b = $("copy-btn"); const t = b.innerHTML;
    b.innerHTML = "✓ Copié"; setTimeout(() => (b.innerHTML = t), 1500);
  } catch (e) {}
});

// Une ressource d'exemple au démarrage
addResource();
