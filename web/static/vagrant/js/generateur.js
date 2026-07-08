/* VagrantForge — génération du Vagrantfile côté client.
   Miroir fidèle de core/generateur.py (aperçu instantané hors-ligne). */

function escRuby(s){ return String(s).replace(/"/g,'\\"'); }
function nomVariable(nom){ let v=String(nom||'vm').replace(/[^a-zA-Z0-9_]/g,'_'); if(/^[0-9]/.test(v)) v='vm_'+v; return v; }

function blocLocale(vn, locale, keymap){
  if(!locale && !keymap) return '';
  let s = '      # ── Langue & clavier (familles Debian/Ubuntu) ──\n      export DEBIAN_FRONTEND=noninteractive\n';
  if(locale){ s += `      sed -i 's/^# *${locale} UTF-8/${locale} UTF-8/' /etc/locale.gen\n      locale-gen\n      update-locale LANG=${locale}\n`; }
  if(keymap){ s += `      echo "XKBLAYOUT=${keymap}" > /etc/default/keyboard\n      setupcon -k --force || true\n`; }
  return `    ${vn}.vm.provision "shell", inline: <<-SHELL\n${s}    SHELL\n`;
}

function buildVagrantfile(cfg){
  const pg = cfg.provider || 'virtualbox';
  const vms = cfg.vms || [];
  const ram = vms.reduce((s,v)=>s+(parseInt(v.memory)||0),0);
  const cpu = vms.reduce((s,v)=>s+(parseInt(v.cpus)||0),0);
  const jour = new Date().toISOString().slice(0,10);
  const barre = '='.repeat(66);
  let o = `# -*- mode: ruby -*-\n# vi: set ft=ruby :\n#\n# ${barre}\n`;
  o += `#  Vagrantfile généré par VagrantForge — ${jour}\n`;
  o += `#  ${vms.length} VM(s) | ${ram} Mo RAM | ${cpu} vCPU | provider : ${pg}\n`;
  o += `#  Démarrage : vagrant up   |   État : vagrant status\n# ${barre}\n\n`;
  o += `Vagrant.require_version ">= 2.3.0"\n\nVagrant.configure("2") do |config|\n`;
  o += `  config.vm.box_check_update = ${cfg.box_check_update?'true':'false'}\n\n`;

  vms.forEach(v=>{
    const vn = nomVariable(v.name);
    const prov = v.provider || pg;
    o += `  # ── ${v.name} — ${v.box} | ${v.memory} Mo | ${v.cpus} vCPU | ${v.ip||'IP dynamique'}\n`;
    o += `  config.vm.define "${escRuby(v.name)}" do |${vn}|\n`;
    o += `    ${vn}.vm.box = "${escRuby(v.box)}"\n`;
    if(v.boxVersion) o += `    ${vn}.vm.box_version = "${escRuby(v.boxVersion)}"\n`;
    o += `    ${vn}.vm.hostname = "${escRuby(v.name)}"\n`;
    if(v.ip) o += `    ${vn}.vm.network "private_network", ip: "${escRuby(v.ip)}"\n`;
    if(v.publicNetwork) o += `    ${vn}.vm.network "public_network"\n`;
    (v.ports||[]).forEach(p=>{ o += `    ${vn}.vm.network "forwarded_port", guest: ${p.guest}, host: ${p.host}, auto_correct: true, id: "port-${p.guest}"\n`; });
    if(v.disableSyncedFolder) o += `    ${vn}.vm.synced_folder ".", "/vagrant", disabled: true\n`;
    else if(v.syncedFolder){ const ft = prov==='vmware_desktop'?'vmware':(prov==='virtualbox'?'virtualbox':null); o += `    ${vn}.vm.synced_folder "${escRuby(v.syncedFolder)}", "/vagrant"${ft?`, type: "${ft}"`:''}\n`; }
    if(v.sshUsername) o += `    ${vn}.ssh.username = "${escRuby(v.sshUsername)}"\n`;
    if(v.sshPassword){ o += `    ${vn}.ssh.password = "${escRuby(v.sshPassword)}"\n    ${vn}.ssh.insert_key = false\n`; }

    if(prov==='virtualbox'){
      o += `    ${vn}.vm.provider "virtualbox" do |vb|\n      vb.name = "${escRuby(v.name)}"\n      vb.memory = ${v.memory}\n      vb.cpus = ${v.cpus}\n      vb.gui = ${v.gui?'true':'false'}\n    end\n`;
    } else if(prov==='vmware_desktop'){
      o += `    ${vn}.vm.provider "vmware_desktop" do |vw|\n      vw.gui = ${v.gui?'true':'false'}\n      vw.vmx["displayName"] = "${escRuby(v.name)}"\n      vw.vmx["memsize"] = "${v.memory}"\n      vw.vmx["numvcpus"] = "${v.cpus}"\n      vw.vmx["cpuid.coresPerSocket"] = "${v.cpus}"\n`;
      if(v.ip) o += `      vw.vmx["ethernet0.virtualDev"] = "vmxnet3"\n`;
      o += `    end\n`;
    } else if(prov==='libvirt'){
      o += `    ${vn}.vm.provider "libvirt" do |lv|\n      lv.memory = ${v.memory}\n      lv.cpus = ${v.cpus}\n    end\n`;
    }

    o += blocLocale(vn, v.locale, v.keymap);

    if(v.provisionType==='shell'){
      let full = v.provisionScript||'';
      if(v.rootPassword) full = `echo "root:${escRuby(v.rootPassword)}" | chpasswd\n` + full;
      const sc = full.split('\n').map(l=>'      '+l).join('\n');
      o += `    ${vn}.vm.provision "shell", inline: <<-SHELL\n${sc}\n    SHELL\n`;
    } else if(v.provisionType==='ansible'){
      o += `    ${vn}.vm.provision "ansible" do |ansible|\n      ansible.playbook = "${escRuby(v.provisionScript)}"\n    end\n`;
      if(v.rootPassword) o += `    ${vn}.vm.provision "shell", inline: 'echo "root:${escRuby(v.rootPassword)}" | chpasswd'\n`;
    } else if(v.rootPassword){
      o += `    ${vn}.vm.provision "shell", inline: 'echo "root:${escRuby(v.rootPassword)}" | chpasswd'\n`;
    }
    o += `  end\n\n`;
  });
  o += `end\n`;
  return o;
}

/* Coloration Ruby + numéros de ligne (rendus par le CSS via .code/.cl). */
function highlightRuby(code){
  const lignes = code.split('\n').map(line=>{
    let l = line.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    if(/^\s*#/.test(l)){ l = `<span class="tok-comment">${l}</span>`; }
    else {
      l = l.replace(/"([^"]*)"/g,'<span class="tok-str">"$1"</span>');
      l = l.replace(/\b(Vagrant|configure|require_version|do|end)\b/g,'<span class="tok-kw">$1</span>');
      l = l.replace(/\b(true|false|nil)\b/g,'<span class="tok-const">$1</span>');
      l = l.replace(/\b(\d+)\b/g,'<span class="tok-num">$1</span>');
    }
    return `<span class="cl">${l || '​'}</span>`;
  }).join('');
  return `<div class="code">${lignes}</div>`;
}
