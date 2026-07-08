// Module Terraform (v0) — appelle /terraform/api/generate et affiche le main.tf.

const $ = (id) => document.getElementById(id);

function afficherErreur(msg) {
  const e = $("error");
  e.textContent = msg;
  e.hidden = false;
}

function masquerErreur() {
  $("error").hidden = true;
}

async function generer() {
  masquerErreur();

  let providerConfig, resources;
  try {
    providerConfig = JSON.parse($("provider-config").value || "{}");
  } catch (err) {
    return afficherErreur("Configuration du provider : JSON invalide (" + err.message + ")");
  }
  try {
    resources = JSON.parse($("resources").value || "[]");
  } catch (err) {
    return afficherErreur("Ressources : JSON invalide (" + err.message + ")");
  }

  const payload = {
    provider: $("provider").value,
    provider_config: providerConfig,
    resources: resources,
  };

  let res, data;
  try {
    res = await fetch("/terraform/api/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    data = await res.json();
  } catch (err) {
    return afficherErreur("Serveur injoignable : " + err.message);
  }

  if (!res.ok) {
    return afficherErreur(data.error || "Erreur de génération.");
  }

  $("output").textContent = data.terraform;
  $("copy-btn").hidden = false;
  if (data.avertissements && data.avertissements.length) {
    afficherErreur("Avertissements : " + data.avertissements.join(" ; "));
  }
}

$("generate-btn").addEventListener("click", generer);

$("copy-btn").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("output").textContent);
    const b = $("copy-btn");
    const t = b.textContent;
    b.textContent = "✓ Copié";
    setTimeout(() => (b.textContent = t), 1500);
  } catch (e) {
    afficherErreur("Copie impossible : " + e.message);
  }
});
