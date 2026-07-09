/**
 * web/static/theme.js
 * --------------------
 * Bascule clair/sombre partagée par les 5 pages d'OpsForge (hub, cicd,
 * ansible, vagrant, terraform). Respecte prefers-color-scheme au premier
 * chargement, puis mémorise le choix manuel dans localStorage — la même
 * clé sur toutes les pages, pour que le choix se retrouve en naviguant
 * entre le hub et les modules.
 *
 * Attend un bouton #theme-toggle contenant un element #theme-icon
 * (facultatif : si absent, seule l'auto-detection s'applique).
 */
(function () {
  "use strict";

  const THEME_KEY = "opsforge-theme";

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    const icon = document.getElementById("theme-icon");
    if (icon) {
      icon.textContent = theme === "dark" ? "☀️" : "🌙";
    }
    const btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.setAttribute(
        "aria-label",
        theme === "dark" ? "Passer en mode clair" : "Passer en mode sombre"
      );
    }
  }

  function getSavedTheme() {
    try {
      return localStorage.getItem(THEME_KEY);
    } catch (err) {
      return null;
    }
  }

  function saveTheme(theme) {
    try {
      localStorage.setItem(THEME_KEY, theme);
    } catch (err) {
      // localStorage indisponible (navigation privee, etc.) : pas bloquant.
    }
  }

  function initTheme() {
    const saved = getSavedTheme();
    if (saved === "dark" || saved === "light") {
      applyTheme(saved);
      return;
    }
    const prefersDark =
      window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(prefersDark ? "dark" : "light");
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    applyTheme(next);
    saveTheme(next);
  }

  // Applique le theme des le plus tot possible pour eviter un flash de
  // theme clair avant que le JS ne s'execute completement.
  initTheme();

  document.addEventListener("DOMContentLoaded", function () {
    const btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.addEventListener("click", toggleTheme);
    }
    // Reapplique (au cas ou le DOM du bouton/icone n'existait pas encore
    // au moment de l'appel initial ci-dessus).
    initTheme();
  });
})();
