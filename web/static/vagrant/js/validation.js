/* VagrantForge — validation côté client (miroir de core/schema.py).
   Retourne { erreurs, avert, nomsErr } à partir du modèle UI (liste de VMs). */

const PROVIDERS_CONNUS = ['virtualbox','vmware_desktop','libvirt'];
const RE_NOM = /^[a-zA-Z0-9][a-zA-Z0-9_-]*$/;
const RE_IPV4 = /^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$/;
function ipPrivee(ip){ return ip.startsWith('10.')||ip.startsWith('192.168.')||/^172\.(1[6-9]|2\d|3[01])\./.test(ip); }

function valider(pg, vms){
  const erreurs=[], avert=[], nomsErr={}; const noms={},ips={},portsHote={}; let ram=0;
  if(vms.length===0) avert.push('Aucune VM : le Vagrantfile sera vide.');
  vms.forEach(v=>{
    const n=v.name||'(sans nom)'; nomsErr[v.id]=false;
    if(!v.name||!RE_NOM.test(v.name)){ erreurs.push(`${n} : nom invalide (lettres/chiffres, puis - ou _).`); nomsErr[v.id]=true; }
    else if(noms[v.name]){ erreurs.push(`Nom « ${v.name} » utilisé par deux VMs.`); nomsErr[v.id]=true; } else noms[v.name]=true;
    if(!v.box){ erreurs.push(`${n} : aucun OS choisi.`); nomsErr[v.id]=true; }
    const mem=parseInt(v.memory);
    if(!Number.isInteger(mem)||mem<128){ erreurs.push(`${n} : RAM invalide (≥ 128 Mo).`); nomsErr[v.id]=true; }
    else { ram+=mem; if(mem<512) avert.push(`${n} : ${mem} Mo, c'est peu pour la plupart des OS.`); }
    if(v.ip){
      if(!RE_IPV4.test(v.ip)){ erreurs.push(`${n} : IP invalide « ${v.ip} ».`); nomsErr[v.id]=true; }
      else if(ips[v.ip]){ erreurs.push(`IP ${v.ip} donnée à « ${ips[v.ip]} » ET « ${n} ».`); nomsErr[v.id]=true; }
      else { ips[v.ip]=n; if(!ipPrivee(v.ip)) avert.push(`${n} : ${v.ip} n'est pas une IP privée, risque de conflit réseau.`); }
    }
    const pe = v.provider||pg;
    if(v.box && boxSupportsProvider(v.box,pe)===false){
      const alt = Object.keys(BOX_PROVIDERS).find(b=>BOX_PROVIDERS[b].includes(pe)&&v.box.includes('/')&&b.split('/').pop()===v.box.split('/').pop());
      avert.push(`${n} : « ${NOM_BOX[v.box]||v.box} » n'existe pas pour ${pe}.`+(alt?` Essaie « ${NOM_BOX[alt]||alt} ».`:''));
    }
    (v.ports||[]).forEach(p=>{
      ['guest','host'].forEach(k=>{ const x=parseInt(p[k]); if(!Number.isInteger(x)||x<1||x>65535){ erreurs.push(`${n} : port ${k} hors bornes (1–65535).`); nomsErr[v.id]=true; } });
      const h=parseInt(p.host); if(Number.isInteger(h)){ if(portsHote[h]) avert.push(`Port hôte ${h} partagé (${portsHote[h]} & ${n}) — auto_correct le décalera.`); else portsHote[h]=n; }
    });
    if(v.provisionType==='ansible'&&!v.provisionScript){ erreurs.push(`${n} : Ansible sans chemin de playbook.`); nomsErr[v.id]=true; }
    if(v.sshPassword||v.rootPassword) avert.push(`${n} : mot de passe en clair — OK pour un lab jetable seulement.`);
  });
  if(ram>32768) avert.push(`RAM totale : ${ram} Mo — vérifie que ton PC encaisse.`);
  return {erreurs, avert, nomsErr};
}
