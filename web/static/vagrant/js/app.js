/* VagrantForge — contrôleur de l'interface.
   État en mémoire + persistance localStorage + rendu formulaire/aperçu. */

const CLE='vagrantforge.v3';
let vms=[], openStates={};
const $=s=>document.querySelector(s);

function makeVM(i){
  const id='vm'+Date.now()+Math.floor(Math.random()*1000);
  const nom=i===0?'web':'vm'+(i+1);
  return {id, name:nom, box:'debian/bookworm64', boxVersion:'', guestOs:'', locale:'', keymap:'',
    sshUsername:'', sshPassword:'', winrmUsername:'', winrmPassword:'', rootPassword:'', memory:2048, cpus:1, ip:'',
    provider:'', gui:false, publicNetwork:false, syncedFolder:'./'+nom,
    disableSyncedFolder:false, provisionType:'shell', provisionScript:'apt-get update -y\n', ports:[]};
}
function sousReseau(){ return $('#g-subnet').value.trim()||'192.168.56'; }
function nextIP(){ const sr=sousReseau(); const u=vms.map(v=>v.ip).filter(Boolean); let n=10; while(u.includes(sr+'.'+n)) n++; return sr+'.'+n; }

function addVM(){ const v=makeVM(vms.length); v.ip=nextIP(); vms.push(v); openStates[v.id]=true; rendre(); }
function removeVM(id){ vms=vms.filter(v=>v.id!==id); rendre(); }
function dupVM(id){ const s=vms.find(v=>v.id===id); if(!s) return; const c=JSON.parse(JSON.stringify(s)); c.id='vm'+Date.now()+Math.floor(Math.random()*1000); c.name=s.name+'-copie'; c.ip=nextIP(); c.syncedFolder='./'+c.name; vms.splice(vms.findIndex(v=>v.id===id)+1,0,c); openStates[c.id]=true; rendre(); }
function addPort(id){ const v=vms.find(v=>v.id===id); v.ports.push({guest:80,host:8080+v.ports.length}); rendre(); }
function rmPort(id,i){ const v=vms.find(v=>v.id===id); v.ports.splice(i,1); rendre(); }

function configCourante(){
  return { provider:$('#g-provider').value, box_check_update:$('#g-boxcheck').checked,
    vms: vms.map(v=>({ name:v.name, box:v.box, box_version:v.boxVersion, guest_os:v.guestOs||undefined, memory:parseInt(v.memory)||0,
      cpus:parseInt(v.cpus)||0, ip:v.ip, provider:v.provider, gui:v.gui, public_network:v.publicNetwork,
      locale:v.locale, keymap:v.keymap, synced_folder:v.syncedFolder, disable_synced_folder:v.disableSyncedFolder,
      ssh_username:v.sshUsername, ssh_password:v.sshPassword,
      winrm_username:v.winrmUsername, winrm_password:v.winrmPassword, root_password:v.rootPassword,
      ports:v.ports, provision:{type:v.provisionType, script:v.provisionScript} })) };
}

function optionsBox(v){
  let html='', connu=false;
  CATALOGUE.forEach(g=>{
    html+=`<optgroup label="${g.famille}">`;
    g.boxes.forEach(b=>{ const sel=b.id===v.box; if(sel) connu=true; html+=`<option value="${b.id}" ${sel?'selected':''}>${b.nom}</option>`; });
    html+=`</optgroup>`;
  });
  html+=`<optgroup label="Avancé"><option value="__autre__" ${!connu?'selected':''}>Autre box (saisie manuelle)…</option></optgroup>`;
  return html;
}
function optionsSimple(niveaux, cur){ return niveaux.map(([val,lib])=>`<option value="${val}" ${val==cur?'selected':''}>${lib}</option>`).join(''); }
function optionsLocale(v){ return LOCALES.map(([loc,km,lib])=>{ const sel=(loc===(v.locale||'')); return `<option value="${loc}|${km}" ${sel?'selected':''}>${lib}</option>`; }).join(''); }
function optionsSnippets(){ let h='<option value="">＋ insérer une commande…</option>'; SNIPPETS.forEach(([cat,items])=>{ h+=`<optgroup label="${cat}">`; items.forEach(([lib,code])=>{ h+=`<option value="${btoa(unescape(encodeURIComponent(code)))}">${lib}</option>`; }); h+='</optgroup>'; }); return h; }

function warnBox(v){
  const pe=v.provider||$('#g-provider').value;
  if(boxSupportsProvider(v.box,pe)===false){
    const alt=Object.keys(BOX_PROVIDERS).find(b=>BOX_PROVIDERS[b].includes(pe)&&v.box.includes('/')&&b.split('/').pop()===v.box.split('/').pop());
    return `<div class="box-warning">⚠ Cet OS n'a pas d'image <b>${pe}</b>.${alt?` Essaie <code>${NOM_BOX[alt]||alt}</code>.`:''}</div>`;
  }
  return '';
}

function renderForm(nomsErr){
  nomsErr=nomsErr||{};
  const list=$('#vm-list');
  if(vms.length===0){ list.innerHTML='<div class="hint">Aucune VM. Clique sur « + ajouter une VM » ou choisis un démarrage rapide.</div>'; return; }
  const ramCustom = v => !RAM_NIVEAUX.some(([val])=>val==v.memory);

  list.innerHTML = vms.map(v=>{
    const boxAutre = !NOM_BOX[v.box];
    const ports=v.ports.map((p,i)=>`
      <div class="port-row">
        <input type="number" data-vm="${v.id}" data-field="port-guest" data-idx="${i}" value="${p.guest}" placeholder="VM (guest)">
        <span style="color:var(--text-dim);font-family:var(--mono);font-size:11px;">→</span>
        <input type="number" data-vm="${v.id}" data-field="port-host" data-idx="${i}" value="${p.host}" placeholder="PC (host)">
        <span class="rm" data-vm="${v.id}" data-idx="${i}" data-action="rmport">✕</span>
      </div>`).join('');

    return `
    <div class="vm-card${openStates[v.id]?' open':''}">
      <div class="vm-card-head" data-toggle="${v.id}">
        <span class="dot${nomsErr[v.id]?' err':''}"></span>
        <span class="name">${v.name||'(sans nom)'}</span>
        <span class="badge">${(NOM_BOX[v.box]||v.box).split(' — ')[0]} · ${v.memory}Mo</span>
        <span class="toggle">▸</span>
      </div>
      <div class="vm-card-body">
        <label>Nom de la VM</label>
        <input type="text" data-vm="${v.id}" data-field="name" value="${v.name}">

        <label>Système d'exploitation (OS)
          <span class="info" title="L'image de départ de la VM. Choisis par son nom : « Debian 12 » = la version stable actuelle. Les images bento marchent aussi sous VMware.">i</span>
        </label>
        <select data-vm="${v.id}" data-field="box">${optionsBox(v)}</select>
        ${boxAutre?`<input type="text" data-vm="${v.id}" data-field="boxManuel" value="${v.box}" placeholder="ex: monorg/ma-box" style="margin-top:6px;">`:''}
        ${warnBox(v)}

        <label>Version de l'image
          <span class="info" title="Laisse « dernière » pour la plus récente. Fige un numéro pour un lab 100 % reproductible dans le temps. Format propre à chaque box (ex: 12.20240905.1 pour Debian) — utilise le bouton pour voir les vraies versions publiées.">i</span>
        </label>
        <div class="row2">
          <input type="text" data-vm="${v.id}" data-field="boxVersion" value="${v.boxVersion||''}" placeholder="dernière (laisser vide)" list="dl-${v.id}">
          <button type="button" class="btn-secondaire" data-versions="${v.id}">🔎 Versions dispo</button>
        </div>
        <datalist id="dl-${v.id}"></datalist>
        <div class="versions-statut" data-versions-statut="${v.id}"></div>

        <div class="row2">
          <div><label>Mémoire vive (RAM)</label>
            <select data-vm="${v.id}" data-field="memory">
              ${optionsSimple(RAM_NIVEAUX, v.memory)}
              <option value="__custom__" ${ramCustom(v)?'selected':''}>Personnalisé…</option>
            </select>
            ${ramCustom(v)?`<input type="number" data-vm="${v.id}" data-field="memoryCustom" value="${v.memory}" style="margin-top:6px;" placeholder="Mo">`:''}
          </div>
          <div><label>Processeurs (vCPU)</label>
            <select data-vm="${v.id}" data-field="cpus">${optionsSimple(CPU_NIVEAUX, v.cpus)}</select>
          </div>
        </div>

        ${estBoxWindows(v) ? `
        <div class="notice-windows" style="margin:8px 0;padding:10px 12px;border-radius:13px;font-size:.85em;">
          🪟 Box Windows détectée — pilotage en <b>WinRM</b> (pas de SSH), provisioning en <b>PowerShell</b>.
        </div>` : `
        <label>Langue & clavier de la VM
          <span class="info" title="Règle la langue du système et la disposition du clavier au premier démarrage (familles Debian/Ubuntu). Pratique pour un clavier AZERTY.">i</span>
        </label>
        <select data-vm="${v.id}" data-field="locale">${optionsLocale(v)}</select>`}

        <label>IP privée (réseau host-only)
          <span class="info" title="Adresse fixe pour joindre la VM depuis ton PC et entre VMs, sur un réseau isolé. Laisse vide pour une IP automatique.">i</span>
        </label>
        <input type="text" data-vm="${v.id}" data-field="ip" value="${v.ip}" placeholder="vide = IP automatique">

        <label>Provider spécifique (sinon : global)</label>
        <select data-vm="${v.id}" data-field="provider">
          <option value="" ${v.provider===''?'selected':''}>— hérite du global —</option>
          <option value="virtualbox" ${v.provider==='virtualbox'?'selected':''}>VirtualBox</option>
          <option value="vmware_desktop" ${v.provider==='vmware_desktop'?'selected':''}>VMware Desktop</option>
          <option value="libvirt" ${v.provider==='libvirt'?'selected':''}>libvirt</option>
        </select>

        <div class="checkbox-row"><input type="checkbox" data-vm="${v.id}" data-field="gui" ${v.gui?'checked':''}>
          <label>Afficher la fenêtre de la VM (utile pour debug)</label></div>
        <div class="checkbox-row"><input type="checkbox" data-vm="${v.id}" data-field="publicNetwork" ${v.publicNetwork?'checked':''}>
          <label>Interface en pont (public_network) — la VM sur ton vrai réseau</label></div>

        <label>Dossier partagé PC → /vagrant
          <span class="info" title="Un dossier de ton PC visible dans la VM sous /vagrant. Pratique pour éditer du code côté PC et l'exécuter dans la VM.">i</span>
        </label>
        <input type="text" data-vm="${v.id}" data-field="syncedFolder" value="${v.syncedFolder}" ${v.disableSyncedFolder?'disabled':''}>
        <div class="checkbox-row"><input type="checkbox" data-vm="${v.id}" data-field="disableSyncedFolder" ${v.disableSyncedFolder?'checked':''}>
          <label>Désactiver le dossier partagé (contourne un bug du plugin VMware récent)</label></div>

        ${estBoxWindows(v) ? `
        <div class="row2">
          <div><label>WinRM — utilisateur</label>
            <input type="text" data-vm="${v.id}" data-field="winrmUsername" value="${v.winrmUsername||''}" placeholder="vagrant"></div>
          <div><label>WinRM — mot de passe</label>
            <input type="text" data-vm="${v.id}" data-field="winrmPassword" value="${v.winrmPassword||''}" placeholder="vagrant"></div>
        </div>
        <label>Mot de passe Administrator</label>
        <input type="text" data-vm="${v.id}" data-field="rootPassword" value="${v.rootPassword||''}" placeholder="vide = inchangé">` : `
        <div class="row2">
          <div><label>SSH — utilisateur</label>
            <input type="text" data-vm="${v.id}" data-field="sshUsername" value="${v.sshUsername||''}" placeholder="vagrant"></div>
          <div><label>SSH — mot de passe</label>
            <input type="text" data-vm="${v.id}" data-field="sshPassword" value="${v.sshPassword||''}" placeholder="clé par défaut"></div>
        </div>
        <label>Mot de passe root (login console/GUI)</label>
        <input type="text" data-vm="${v.id}" data-field="rootPassword" value="${v.rootPassword||''}" placeholder="vide = inchangé">`}

        <label>Ports redirigés (VM → PC)
          <span class="info" title="Rend un service de la VM accessible depuis ton PC. Ex. guest 80 → host 8080 : http://localhost:8080 ouvre le port 80 de la VM.">i</span>
        </label>
        <div class="ports-list">${ports}</div>
        <div class="btn-row"><button class="btn small" data-action="addport" data-vm="${v.id}">+ port</button></div>

        <label>Provisioning — que faire au démarrage ?</label>
        <select data-vm="${v.id}" data-field="provisionType">
          <option value="shell" ${v.provisionType==='shell'?'selected':''}>script shell</option>
          <option value="ansible" ${v.provisionType==='ansible'?'selected':''}>playbook Ansible</option>
          <option value="none" ${v.provisionType==='none'?'selected':''}>rien</option>
        </select>
        ${v.provisionType==='shell'?`
          <label>Aide : insérer une commande toute prête
            <span class="info" title="Choisis une commande courante, elle s'ajoute au script ci-dessous. Tu peux en empiler plusieurs.">i</span>
          </label>
          <select data-vm="${v.id}" data-field="snippet">${optionsSnippets()}</select>
          <label>Script shell (lancé en root au 1er démarrage)</label>
          <textarea data-vm="${v.id}" data-field="provisionScript" rows="5">${v.provisionScript}</textarea>`:''}
        ${v.provisionType==='ansible'?`
          <label>Chemin du playbook</label>
          <input type="text" data-vm="${v.id}" data-field="provisionScript" value="${(v.provisionScript||'').includes('.yml')?v.provisionScript:'provisioning/playbook.yml'}">`:''}

        <div class="btn-row">
          <button class="btn small" data-action="dup" data-vm="${v.id}">dupliquer</button>
          <button class="btn danger small" data-action="remove" data-vm="${v.id}">supprimer</button>
        </div>
      </div>
    </div>`;
  }).join('');

  cabler(list);
}

function cabler(list){
  list.querySelectorAll('[data-toggle]').forEach(el=>el.addEventListener('click',()=>{ const id=el.getAttribute('data-toggle'); openStates[id]=!openStates[id]; renderForm(); }));
  list.querySelectorAll('input[data-vm], select[data-vm], textarea[data-vm]').forEach(el=>{ el.addEventListener('input',onField); el.addEventListener('change',onField); });
  list.querySelectorAll('[data-action="remove"]').forEach(el=>el.addEventListener('click',()=>removeVM(el.getAttribute('data-vm'))));
  list.querySelectorAll('[data-action="dup"]').forEach(el=>el.addEventListener('click',()=>dupVM(el.getAttribute('data-vm'))));
  list.querySelectorAll('[data-action="addport"]').forEach(el=>el.addEventListener('click',()=>addPort(el.getAttribute('data-vm'))));
  list.querySelectorAll('[data-action="rmport"]').forEach(el=>el.addEventListener('click',()=>rmPort(el.getAttribute('data-vm'),parseInt(el.getAttribute('data-idx')))));
  list.querySelectorAll('[data-versions]').forEach(el=>el.addEventListener('click',()=>chargerVersions(el.getAttribute('data-versions'))));
}

async function chargerVersions(id){
  const v=vms.find(v=>v.id===id); if(!v||!v.box) return;
  const statutEl=document.querySelector(`[data-versions-statut="${id}"]`);
  const dlEl=document.querySelector(`#dl-${id}`);
  if(statutEl) statutEl.textContent='Recherche sur Vagrant Cloud…';
  try{
    const r=await fetch(`/api/box-versions?box=${encodeURIComponent(v.box)}`);
    const data=await r.json();
    if(data.erreur || !data.versions || !data.versions.length){
      if(statutEl) statutEl.textContent=`Aucune version trouvée (${data.erreur||'réponse vide'}).`;
      return;
    }
    if(dlEl) dlEl.innerHTML=data.versions.map(ver=>`<option value="${ver}">`).join('');
    if(statutEl) statutEl.textContent=`${data.versions.length} version(s) trouvée(s) — ouvre le champ pour les voir.`;
  }catch(e){
    if(statutEl) statutEl.textContent="Indisponible en mode autonome : lance le serveur API (python web/api/main.py) pour interroger Vagrant Cloud.";
  }
}

function onField(e){
  const el=e.target, v=vms.find(v=>v.id===el.getAttribute('data-vm')); if(!v) return;
  const f=el.getAttribute('data-field');
  let restructure=false;

  if(f==='port-guest'||f==='port-host'){ v.ports[parseInt(el.getAttribute('data-idx'))][f==='port-guest'?'guest':'host']=parseInt(el.value)||0; }
  else if(f==='cpus'){ v.cpus=parseInt(el.value)||1; }
  else if(f==='memory'){ if(el.value==='__custom__'){ restructure=true; } else { v.memory=parseInt(el.value)||1024; restructure=true; } }
  else if(f==='memoryCustom'){ v.memory=parseInt(el.value)||1024; }
  else if(f==='box'){ if(el.value==='__autre__'){ v.box=v.box&&!NOM_BOX[v.box]?v.box:''; } else { v.box=el.value; } restructure=true; }
  else if(f==='boxManuel'){ v.box=el.value; }
  else if(f==='locale'){ const [loc,km]=el.value.split('|'); v.locale=loc||''; v.keymap=km||''; }
  else if(f==='snippet'){ if(el.value){ const code=decodeURIComponent(escape(atob(el.value))); v.provisionScript=(v.provisionScript||'')+code; restructure=true; el.value=''; } }
  else if(f==='gui'||f==='disableSyncedFolder'||f==='publicNetwork'){ v[f]=el.checked; if(f==='disableSyncedFolder') restructure=true; }
  else { v[f]=el.value; }

  const struct=['name','provider','provisionType'].includes(f);
  if((e.type==='change'&&struct)||restructure){ renderForm(); }
  renderOutput(); sauver();
}

function renderOutput(){
  const code=buildVagrantfile(configCourante());
  $('#output').innerHTML=highlightRuby(code);
  window.__vf=code;
  const {erreurs,avert,nomsErr}=valider($('#g-provider').value,vms);
  document.querySelectorAll('.vm-card').forEach((card,i)=>{ const v=vms[i]; if(!v) return; const dot=card.querySelector('.dot'); if(dot) dot.classList.toggle('err',!!nomsErr[v.id]); });
  const box=$('#diagnostics');
  if(!erreurs.length&&!avert.length){ box.innerHTML='<div class="diag-item ok"><span class="ico">✓</span> Aucun souci détecté. Prêt pour vagrant up.</div>'; }
  else { box.innerHTML = erreurs.map(e=>`<div class="diag-item err"><span class="ico">✗</span> ${e}</div>`).join('') + avert.map(a=>`<div class="diag-item warn"><span class="ico">⚠</span> ${a}</div>`).join(''); }
  const ram=vms.reduce((s,v)=>s+(parseInt(v.memory)||0),0), cpu=vms.reduce((s,v)=>s+(parseInt(v.cpus)||0),0);
  const etat=erreurs.length?`<span class="bad">●</span> ${erreurs.length} erreur(s)`:`<span class="ok">●</span> config valide`;
  $('#status-bar').innerHTML=`<span class="stat"><b>${vms.length}</b> VM(s)</span><span class="stat"><b>${ram}</b> Mo RAM</span><span class="stat"><b>${cpu}</b> vCPU</span><span class="stat push-right">${etat}</span>`;
}

function loadPreset(kind){
  if(kind==='clear'){ vms=[]; openStates={}; rendre(); return; }
  const p=PRESETS[kind]; if(!p) return;
  vms=p.build(sousReseau()).map((m,i)=>{ const v=makeVM(i); Object.assign(v,m); v.syncedFolder=m.syncedFolder||('./'+m.name); openStates[v.id]=i===0; return v; });
  rendre();
}

function sauver(){ try{ localStorage.setItem(CLE,JSON.stringify({provider:$('#g-provider').value,boxCheck:$('#g-boxcheck').checked,subnet:$('#g-subnet').value,vms,openStates})); }catch(e){} }
function restaurer(){ try{ const d=JSON.parse(localStorage.getItem(CLE)); if(!d||!Array.isArray(d.vms)||!d.vms.length) return false; $('#g-provider').value=d.provider||'virtualbox'; $('#g-boxcheck').checked=!!d.boxCheck; $('#g-subnet').value=d.subnet||'192.168.56'; vms=d.vms; openStates=d.openStates||{}; return true; }catch(e){ return false; } }

function telecharger(blob,nom){ const u=URL.createObjectURL(blob); const a=document.createElement('a'); a.href=u; a.download=nom; document.body.appendChild(a); a.click(); document.body.removeChild(a); URL.revokeObjectURL(u); }
function exporter(){ telecharger(new Blob([JSON.stringify(configCourante(),null,2)],{type:'application/json'}),'vagrantforge.config.json'); }
function importer(f){ const r=new FileReader(); r.onload=()=>{ try{ const c=JSON.parse(r.result); $('#g-provider').value=c.provider||'virtualbox'; $('#g-boxcheck').checked=!!c.box_check_update; vms=(c.vms||[]).map((x,i)=>{ const v=makeVM(i); Object.assign(v,{name:x.name??v.name,box:x.box??v.box,boxVersion:x.box_version??'',guestOs:x.guest_os??'',memory:x.memory??2048,cpus:x.cpus??1,ip:x.ip??'',provider:x.provider??'',gui:!!x.gui,publicNetwork:!!x.public_network,locale:x.locale??'',keymap:x.keymap??'',syncedFolder:x.synced_folder??('./'+(x.name||'vm')),disableSyncedFolder:!!x.disable_synced_folder,sshUsername:x.ssh_username??'',sshPassword:x.ssh_password??'',winrmUsername:x.winrm_username??'',winrmPassword:x.winrm_password??'',rootPassword:x.root_password??'',ports:x.ports??[],provisionType:(x.provision&&x.provision.type)||'none',provisionScript:(x.provision&&x.provision.script)||''}); openStates[v.id]=i===0; return v; }); rendre(); }catch(e){ alert('JSON invalide : '+e.message); } }; r.readAsText(f); }

function rendre(){ renderForm(); renderOutput(); sauver(); }

function ouvrirAide(){ $('#overlay').classList.add('open'); }
function fermerAide(){ $('#overlay').classList.remove('open'); }

function init(){
  const ICP={
    solo:['fa-server','ic-blue'], k3s:['fa-diagram-project','ic-cyan'],
    lamp:['fa-globe','ic-green'], devsecops:['fa-shield-halved','ic-amber'],
    pentest:['fa-user-secret','ic-red'], monitoring:['fa-chart-line','ic-cyan'],
    elk:['fa-magnifying-glass-chart','ic-amber'], wordpress:['fa-wordpress','ic-blue'],
    'gitlab-runner':['fa-gitlab','ic-amber'], nextcloud:['fa-cloud','ic-green']};
  $('#presets-grid').innerHTML=Object.entries(PRESETS).map(([k,p])=>{
    const [ic,cls]=ICP[k]||['fa-box','ic-violet'];
    return `<button class="preset-card" data-preset="${k}" data-testid="preset-${k}-btn"><span class="preset-ic ${cls}"><i class="fa-solid ${ic}"></i></span><span class="preset-txt"><span class="t">${p.t}</span><span class="d">${p.d}</span></span></button>`;
  }).join('');
  document.querySelectorAll('[data-preset]').forEach(b=>b.addEventListener('click',()=>loadPreset(b.getAttribute('data-preset'))));
  $('#add-vm').addEventListener('click',addVM);
  $('#g-provider').addEventListener('change',rendre);
  $('#g-boxcheck').addEventListener('change',()=>{ renderOutput(); sauver(); });
  $('#g-subnet').addEventListener('input',()=>{ renderOutput(); sauver(); });

  $('#copy-btn').addEventListener('click',async()=>{ try{ await navigator.clipboard.writeText(window.__vf||''); const f=$('#flash'); f.classList.add('show'); setTimeout(()=>f.classList.remove('show'),1400); }catch(e){} });
  $('#dl-btn').addEventListener('click',()=>telecharger(new Blob([window.__vf||''],{type:'application/octet-stream'}),'Vagrantfile'));
  $('#export-btn').addEventListener('click',exporter);
  $('#import-btn').addEventListener('click',()=>$('#import-file').click());
  $('#import-file').addEventListener('change',e=>{ if(e.target.files[0]) importer(e.target.files[0]); e.target.value=''; });
  $('#aide-btn').addEventListener('click',ouvrirAide);
  $('#modal-close').addEventListener('click',fermerAide);
  $('#overlay').addEventListener('click',e=>{ if(e.target===$('#overlay')) fermerAide(); });
  document.addEventListener('keydown',e=>{ if(e.key==='Escape') fermerAide(); });

  document.querySelectorAll('.mobile-tabs button').forEach(b=>b.addEventListener('click',()=>{ document.body.dataset.vue=b.getAttribute('data-vue'); document.querySelectorAll('.mobile-tabs button').forEach(x=>x.classList.remove('actif')); b.classList.add('actif'); }));

  if(restaurer()) rendre(); else addVM();
}
document.addEventListener('DOMContentLoaded',init);
