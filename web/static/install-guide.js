// Guide d'installation par OS — composant partagé OpsForge.
// Usage : définir window.INSTALL_GUIDE = {...} puis appeler
//   OpsForgeInstallGuide.init("id-du-bouton-ouvrir")
// Structure attendue :
//   { tool, icon, intro, os: [ { id, label, icon, color, steps: [ {title, cmd, note} ] } ] }

window.OpsForgeInstallGuide = (function () {
  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function buildModal(data) {
    const overlay = document.createElement("div");
    overlay.className = "ig-overlay";
    overlay.id = "ig-overlay";

    overlay.innerHTML = `
      <div class="ig-modal" role="dialog" aria-modal="true">
        <div class="ig-head">
          <h2><i class="fa-solid ${data.icon || "fa-download"}"></i> Installer ${esc(data.tool)}</h2>
          <button class="ig-close" aria-label="Fermer">&times;</button>
        </div>
        ${data.intro ? `<p class="ig-intro">${data.intro}</p>` : ""}
        <div class="ig-tabs"></div>
        <div class="ig-body"></div>
      </div>`;

    const tabsEl = overlay.querySelector(".ig-tabs");
    const bodyEl = overlay.querySelector(".ig-body");

    function renderBody(os) {
      bodyEl.innerHTML = os.steps
        .map(
          (s) => `
        <div class="ig-step">
          ${s.title ? `<p class="ig-step-title">${esc(s.title)}</p>` : ""}
          <div class="ig-cmd">${esc(s.cmd)}<button class="ig-copy" title="Copier"><i class="fa-regular fa-copy"></i></button></div>
          ${s.note ? `<p class="ig-note">${s.note}</p>` : ""}
        </div>`
        )
        .join("");
      bodyEl.querySelectorAll(".ig-copy").forEach((btn, i) => {
        btn.addEventListener("click", async () => {
          try {
            await navigator.clipboard.writeText(os.steps[i].cmd);
            btn.innerHTML = '<i class="fa-solid fa-check"></i>';
            setTimeout(() => (btn.innerHTML = '<i class="fa-regular fa-copy"></i>'), 1400);
          } catch (e) {}
        });
      });
    }

    data.os.forEach((os, idx) => {
      const tab = document.createElement("button");
      tab.className = "ig-tab" + (idx === 0 ? " active" : "");
      tab.style.setProperty("color", idx === 0 ? "#fff" : os.color);
      tab.style.background = idx === 0 ? os.color : "";
      tab.innerHTML = `<i class="${os.icon}"></i> ${esc(os.label)}`;
      tab.addEventListener("click", () => {
        tabsEl.querySelectorAll(".ig-tab").forEach((t) => {
          t.classList.remove("active");
          t.style.background = "";
          t.style.color = "";
        });
        tab.classList.add("active");
        tab.style.background = os.color;
        tab.style.color = "#fff";
        renderBody(os);
      });
      tabsEl.appendChild(tab);
    });

    renderBody(data.os[0]);

    overlay.querySelector(".ig-close").addEventListener("click", close);
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
    });

    function close() {
      overlay.classList.remove("open");
    }

    document.body.appendChild(overlay);
    return overlay;
  }

  return {
    init(openBtnId) {
      const data = window.INSTALL_GUIDE;
      if (!data) return;
      const overlay = buildModal(data);
      const btn = document.getElementById(openBtnId);
      if (btn) btn.addEventListener("click", () => overlay.classList.add("open"));
    },
  };
})();
