/* Explicit local commands; no automatic retry. */
(() => {
 'use strict';
 const panel=document.getElementById('campus-commands');
 const readToken=document.querySelector('meta[name="campus-session"]').content;
 const token=document.querySelector('meta[name="campus-command-session"]').content;
 const node=(tag,t,cls)=>{const e=document.createElement(tag);if(t!==undefined)e.textContent=t;if(cls)e.className=cls;return e;};
 const btn=(label,fn)=>{const e=node('button',label);e.type='button';e.addEventListener('click',fn);return e;};
 let station=null,active=null,seq=0,pending=false,uncertain=false,online=false;
 function reset(){seq++;active=null;panel.hidden=true;panel.replaceChildren();}
 function setStation(id){if(station!==id){reset();station=id;}}
 function setOnline(value){online=value;if(!value)reset();}
 function open(kind){
  if(!station||!online||pending||!['home','missions'].includes(kind))return;
  reset();active=kind;panel.hidden=false;
  const status=node('p','','muted');status.setAttribute('role','status');
  const out=node('div',undefined,'command-results');
  const controls=node('div',undefined,'command-actions');
  controls.append(btn('Fermer',reset),btn('Actualiser les états',load));
  panel.append(node('h3','Commandes du propriétaire'),node('p','Simulation locale et arrêts uniquement. Les appels déjà engagés peuvent rester facturables. Aucun lancement Cloud ni nouvelle autorisation.','muted'),controls,status);
  let textarea;
  if(kind==='missions'){
   const form=node('form',undefined,'command-form');textarea=node('textarea');textarea.required=true;textarea.maxLength=1500;textarea.placeholder='Objectif de la mission de simulation';textarea.setAttribute('aria-label','Objectif de simulation');
   const submit=node('button','Lancer une simulation');submit.type='submit';submit.dataset.command='mission_demo';form.append(textarea,submit);
   form.addEventListener('submit',e=>{e.preventDefault();const title=textarea.value.trim();if(title)send({action:'mission_demo',title},'Lancer cette mission en simulation locale ? Aucun appel IA payant.');});panel.append(form);
  }
  panel.append(out);
  function lock(value){for(const el of panel.querySelectorAll('[data-command]'))el.disabled=value;}
  async function load(){
   if(active!==kind||pending)return;const n=++seq;out.replaceChildren();lock(true);status.textContent='Lecture des états locaux…';
   try{
    const r=await fetch('/campus/read?tool='+kind,{headers:{'X-Campus-Session':readToken},cache:'no-store'});
    if(!r.ok)throw Error('HTTP '+r.status);const data=await r.json();
    if(n!==seq)return;if(data.schema!=='aes.campus.tool.v1'||data.tool!==kind||data.read_only!==true||!Array.isArray(data.rows))throw Error('Réponse invalide');
    for(const row of data.rows){
     let action,label,title;
     if(kind==='missions'){
      if(!['en cours','en attente','prête'].includes(row.state))continue;
      action='mission_stop';label='Arrêter la mission';title='Mission #'+row.id+' · '+row.title+' · '+row.mode;
     }else if(row.kind==='campaign'&&row.state==='actif'){action='campaign_stop';label='Arrêter la campagne';title='Campagne #'+row.id+' · '+row.goal;}
     else if(row.kind==='plan'&&row.state==='active'){action='plan_stop';label='Suspendre le plan';title='Plan #'+row.id;}
     else if(row.kind==='periodic'&&['active','suspended'].includes(row.state)){action='periodic_revoke';label='Révoquer l’autorisation';title='Autorisation périodique #'+row.id;}
     else continue;
     const e=node('div',undefined,'entry'),b=btn(label,()=>send({action,id:row.id},label+' #'+row.id+' ? Les engagements existants sont conservés. Une mission liée peut arrêter sa campagne ; les plans et périodes actifs doivent être arrêtés au niveau approprié.'));
     b.dataset.command=action;e.append(node('b',title),node('small',row.state),b);out.append(e);
    }
    if(!out.children.length)out.append(node('p','Aucun arrêt ou révocation disponible dans cet instantané.','muted'));
    status.textContent=uncertain?'État relu. Vérifie le résultat précédent avant toute nouvelle commande.':'États locaux relus. Les protections du moteur restent applicables.';lock(false);
   }catch(e){if(n===seq){out.replaceChildren();status.textContent='États indisponibles. Aucune commande proposée.';lock(true);}}
  }
  async function send(body,message){
   if(!online||pending||active!==kind||!confirm(message))return;
   pending=true;lock(true);const n=++seq;status.textContent='Transmission de la commande…';
   try{
    const r=await fetch('/campus/command',{method:'POST',headers:{'X-Campus-Command':token,'Content-Type':'application/json'},body:JSON.stringify({...body,confirm:true}),cache:'no-store'});
    const result=await r.json();
    if(!r.ok){if(n===seq)status.textContent='Commande refusée : '+(result.error||'HTTP '+r.status);return;}
    uncertain=false;if(n===seq){if(body.action==='mission_demo')textarea.value='';status.textContent='Commande acceptée par le moteur. Vérifie son état après actualisation.';out.replaceChildren();}
    document.dispatchEvent(new Event('campus-command-completed'));
   }catch(e){uncertain=true;if(n===seq)status.textContent='Résultat incertain : ne relance pas sans vérifier les états.';}
   finally{pending=false;if(n===seq)lock(true);}
  }
  load();
 }
 window.AESCampusCommands=Object.freeze({open,setStation,setOnline});
})();
