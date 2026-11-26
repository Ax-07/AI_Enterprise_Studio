/* Explicit local commands; no automatic retry. */
(() => {
 'use strict';
 const panel=document.getElementById('campus-commands');
 const readToken=document.querySelector('meta[name="campus-session"]').content;
 const token=document.querySelector('meta[name="campus-command-session"]').content;
 const ownerToken=document.querySelector('meta[name="campus-owner-session"]').content;
 const isOwner=()=>Boolean(ownerToken&&station?.startsWith('OWNER:station:'));
 const commercialFloor=new Set(['HERMES','SHOWROOM','ADS183','PUBLISH183','ANALYTICS183']);
 const isCommercial=()=>Boolean(station&&commercialFloor.has(station.split(':')[0]));
 const commercialActions=new Set(['draft_prepare','draft_revoke','trial_close','test_publish','test_collect','test_stop','test_sync']);
 const paid=new Set(['decision','mission_cloud','mission_resume','campaign_start','campaign_resume','plan_start','plan_resume','periodic_authorize']);
 const node=(tag,t,cls)=>{const e=document.createElement(tag);if(t!==undefined)e.textContent=t;if(cls)e.className=cls;return e;};
 const btn=(label,fn)=>{const e=node('button',label);e.type='button';e.addEventListener('click',fn);return e;};
 let station=null,active=null,seq=0,pending=false,uncertain=false,online=false;
 function reset(){seq++;active=null;panel.hidden=true;panel.replaceChildren();}
 function setStation(id){if(station!==id){reset();station=id;}}
 function setOnline(value){online=value;if(!value)reset();}
 function open(kind){
  if(!station||!online||pending||!['home','missions','decisions','business'].includes(kind)||(kind==='decisions'&&!isOwner())||(kind==='business'&&!isCommercial()))return;
  reset();active=kind;panel.hidden=false;
  const status=node('p','','muted');status.setAttribute('role','status');
  const out=node('div',undefined,'command-results');
  const controls=node('div',undefined,'command-actions');
  controls.append(btn('Fermer',reset),btn('Actualiser les états',load));
  panel.append(node('h3',kind==='business'?'Pilotage commercial · interne / TEST':'Commandes du propriétaire'),node('p',kind==='business'?'Brouillons locaux et canal fictif isolé. Aucun achat, vente, diffusion publique ni génération de média. La publication TEST et la collecte TEST nécessitent deux confirmations distinctes.':'Simulation et arrêts ; dans le bureau du propriétaire, commandes Cloud et autorisations explicites. Les appels déjà engagés peuvent rester facturables.','muted'),controls,status);
  let textarea;
  if(kind==='missions'){
   const form=node('form',undefined,'command-form');textarea=node('textarea');textarea.required=true;textarea.maxLength=1500;textarea.placeholder='Objectif de la mission de simulation';textarea.setAttribute('aria-label','Objectif de simulation');
   const submit=node('button','Lancer une simulation');submit.type='submit';submit.dataset.command='mission_demo';form.append(textarea,submit);if(isOwner()){const cloud=btn('Lancer en Cloud',()=>{const title=textarea.value.trim();if(title)send({action:'mission_cloud',title},'Lancer en Cloud : '+title+' ? Des appels OpenAI et des recherches Brave peuvent être facturés dans les limites locales.');});cloud.dataset.command='mission_cloud';form.append(cloud);}
   form.addEventListener('submit',e=>{e.preventDefault();const title=textarea.value.trim();if(title)send({action:'mission_demo',title},'Lancer cette mission en simulation locale ? Aucun appel IA payant.');});panel.append(form);
  }
  if(kind==='home'&&isOwner()){
   const field=(form,key,label,type,attrs={})=>{const wrap=node('label',label),input=node('input');input.name=key;input.type=type;for(const [k,v] of Object.entries(attrs))input.setAttribute(k,String(v));if(type!=='checkbox')input.required=true;wrap.append(input);form.append(wrap);return input;};
   function authorization(action,title,setup,collect){
    const details=node('details'),summary=node('summary',title),form=node('form',undefined,'command-form');details.append(summary,form);
    const f=setup(form,field);const submit=node('button','Confirmer '+title);submit.type='submit';submit.dataset.command=action;form.append(submit);
    form.addEventListener('submit',e=>{e.preventDefault();const body=collect(f);send({action,...body},title+' ?\n'+JSON.stringify(body,null,2)+'\nDes appels IA peuvent être facturés. Les limites du moteur restent applicables. Aucun achat, envoi ou lancement commercial externe.');});panel.append(details);
   }
   const amount={min:'0.01',max:'10',step:'0.000001',placeholder:'USD'};
   const num=(max,min=0)=>({min,max,step:1});
   const n=x=>Number(x.value),v=x=>x.value,checked=x=>x.checked;
   authorization('campaign_start','une campagne Cloud',(f,add)=>{
    const goal=add(f,'goal','Objectif','text',{maxlength:600}),budget=add(f,'budget','Budget maximal USD','number',amount),count=add(f,'count','Missions max.','number',num(10,1)),search=add(f,'search','Recherches Brave max.','number',num(10));
    const scope=add(f,'project','Activité : auto, explore ou identifiant','text',{placeholder:'auto'});scope.value='auto';
    const flags={};for(const [key,label] of [['research','Recherche'],['production','Production'],['tests','Tests'],['market','Préparation commerciale']])flags[key]=add(f,key,label,'checkbox');
    return {goal,budget,count,search,scope,flags};
   },f=>({goal:v(f.goal),budget:v(f.budget),max_missions:n(f.count),search_cap:n(f.search),project:/^[1-9][0-9]*$/.test(v(f.scope))?n(f.scope):v(f.scope),permissions:Object.fromEntries(Object.entries(f.flags).map(([k,x])=>[k,checked(x)]))}));
   authorization('plan_start','un plan autonome',(f,add)=>({budget:add(f,'budget','Budget total USD','number',amount),per:add(f,'per','Budget par campagne USD','number',amount),count:add(f,'count','Campagnes max.','number',num(5,1)),search:add(f,'search','Recherches Brave max.','number',num(10)),explore:add(f,'explore','Autoriser l’exploration','checkbox')}),f=>({budget:v(f.budget),per_campaign:v(f.per),max_campaigns:n(f.count),search_cap:n(f.search),explore:checked(f.explore)}));
   authorization('periodic_authorize','une autorisation périodique',(f,add)=>{
    const label=node('label','Cadence'),cadence=node('select');cadence.name='cadence';for(const [key,text] of [['daily','Quotidienne'],['weekly','Hebdomadaire'],['monthly','30 jours']]){const opt=node('option',text);opt.value=key;cadence.append(opt);}label.append(cadence);f.append(label);
    return {cadence,periods:add(f,'periods','Nombre de périodes','number',num(12,1)),total:add(f,'total','Budget total USD','number',amount),period:add(f,'period','Budget par période USD','number',amount),per:add(f,'per','Budget par campagne USD','number',amount),count:add(f,'count','Campagnes par période','number',num(5,1)),totalSearch:add(f,'totalSearch','Brave total','number',num(120)),periodSearch:add(f,'periodSearch','Brave par période','number',num(10)),explore:add(f,'explore','Autoriser l’exploration','checkbox')};
   },f=>({cadence:v(f.cadence),periods:n(f.periods),total_budget:v(f.total),period_budget:v(f.period),per_campaign:v(f.per),max_campaigns:n(f.count),total_search:n(f.totalSearch),period_search:n(f.periodSearch),explore:checked(f.explore)}));
  }
  panel.append(out);
  function lock(value){for(const el of panel.querySelectorAll('[data-command]'))el.disabled=value;}
  function commercialRows(rows){
   const summary=rows.find(r=>r.kind==='summary'),channels=rows.filter(r=>r.kind==='channel');
   const configured=summary?.test_configured===true;
   out.append(node('p',configured?'Canal TEST configuré localement (disponibilité non vérifiée).':'Canal TEST non configuré ; préparation locale et révocation restent possibles.','muted'));
   const add=(e,action,label,body,message)=>{const b=btn(label,()=>send({action,...body},message));b.dataset.command=action;e.append(b);};
   for(const row of rows){
    let e=node('div',undefined,'entry');
    if(row.kind==='offer'){
     if(!row.draft_eligible)continue;
     e.append(node('b','Offre #'+row.id+' · '+row.title));
     add(e,'draft_prepare','Préparer un brouillon interne',{offer:row.id,snapshot_sha256:row.snapshot_sha256},'Préparer l’offre #'+row.id+' en français, sans publication ni collecte ?');
    }else if(row.kind==='draft'){
     if(row.state!=='draft')continue;
     e.append(node('b','Brouillon #'+row.id+' · '+row.title),node('small','Aucune diffusion réelle autorisée.'));
     if(configured&&!channels.some(x=>x.draft===row.id&&x.state!=='revoked'))add(e,'test_publish','Publication locale TEST · 30 min',{draft:row.id,snapshot_sha256:row.snapshot_sha256,duration_seconds:1800},'Autoriser une page fictive TEST pendant 30 minutes sur le service local isolé ? Aucun achat, aucune collecte, aucune donnée client.');
     add(e,'draft_revoke','Révoquer le brouillon',{draft:row.id},'Révoquer définitivement le brouillon #'+row.id+' ? Les canaux associés seront arrêtés et l’historique conservé.');
    }else if(row.kind==='trial'){
     if(row.stored_state!=='open')continue;
     e.append(node('b','Protocole #'+row.id),node('small',row.state));
     add(e,'trial_close','Clore le protocole',{trial:row.id},'Clore définitivement le protocole #'+row.id+' et conserver son historique ?');
    }else if(row.kind==='channel'){
     if(row.state==='revoked')continue;
     e.append(node('b','Canal TEST · '+row.page),node('small',row.state));
     if(configured&&row.state==='published'&&row.within_window&&row.remaining_seconds>0){
      const duration=Math.min(600,row.remaining_seconds);
      add(e,'test_collect','Autoriser la collecte TEST · 10 signaux max.',{page:row.page,quota:10,duration_seconds:duration},'Autoriser au maximum 10 signaux fictifs pendant '+duration+' secondes ? Aucune collecte réelle, aucun achat ni coordonnées.');
     }
     add(e,'test_stop',row.state==='revocation_pending'?'Réessayer la révocation TEST':'Révoquer publication et collecte TEST',{page:row.page},'Arrêter localement et demander la révocation du canal TEST ?');
    }else if(row.kind==='test_link'){
     if(!configured||row.state!=='test_link')continue;
     e.append(node('b','Collecte TEST · '+row.page));
     add(e,'test_sync','Actualiser les signaux TEST',{page:row.page},'Actualiser les signaux fictifs depuis le service local uniquement ?');
    }else continue;
    out.append(e);
   }
   if(!out.querySelector('[data-command]'))out.append(node('p','Aucune commande commerciale applicable dans cet instantané.','muted'));
  }
  async function load(){
   if(active!==kind||pending)return;const n=++seq;out.replaceChildren();lock(true);status.textContent='Lecture des états locaux…';
   try{
    const r=await fetch('/campus/read?tool='+kind,{headers:{'X-Campus-Session':readToken},cache:'no-store'});
    if(!r.ok)throw Error('HTTP '+r.status);const data=await r.json();
    if(n!==seq)return;if(data.schema!=='aes.campus.tool.v1'||data.tool!==kind||data.read_only!==true||!Array.isArray(data.rows))throw Error('Réponse invalide');
    if(kind==='business'){
     const mr=await fetch('/campus/read?tool=marketing',{headers:{'X-Campus-Session':readToken},cache:'no-store'});
     if(!mr.ok)throw Error('HTTP '+mr.status);const md=await mr.json();
     if(n!==seq)return;if(md.schema!=='aes.campus.tool.v1'||md.tool!=='marketing'||md.read_only!==true||!Array.isArray(md.rows))throw Error('Réponse invalide');
     commercialRows([...data.rows,...md.rows]);
    }else for(const row of data.rows){
     let action,label,title;
     if(kind==='decisions'){
      if(row.state!=='en attente')continue;
      const e=node('div',undefined,'entry');e.append(node('b','#'+row.id+' · '+(row.objet||'Demande')),node('p',row.justification||'Justification non disponible'),node('small','Coût déclaré : '+(row.cout_estime||'inconnu')),node('small','Risques déclarés : '+(row.risques||'inconnus')));
      for(const [decision,label] of [['étude acceptée','Accepter pour étude'],['refusée','Refuser']]){const b=btn(label,()=>send({action:'decision',id:row.id,decision},label+' la demande #'+row.id+' ? Le traitement peut reprendre une mission et engendrer des appels facturables. Aucun achat ni envoi autorisé.'));b.dataset.command='decision';e.append(b);}out.append(e);continue;
     }
     if(kind==='missions'){
      if(isOwner()&&['bloquée','interrompue','arrêtée','prête'].includes(row.state)){const e=node('div',undefined,'entry'),b=btn('Reprendre la mission',()=>send({action:'mission_resume',id:row.id},'Reprendre la mission #'+row.id+' ? Nouveaux appels potentiellement facturables.'));b.dataset.command='mission_resume';e.append(node('b','#'+row.id+' · '+row.title+' · '+row.mode),node('small',row.state),b);out.append(e);}

      if(!['en cours','en attente','prête'].includes(row.state))continue;
      action='mission_stop';label='Arrêter la mission';title='Mission #'+row.id+' · '+row.title+' · '+row.mode;
     }else if(isOwner()&&((row.kind==='campaign'&&['interrompu','arrêté','en attente','bloqué'].includes(row.state))||(row.kind==='plan'&&row.state==='paused'))){
      const a=row.kind==='campaign'?'campaign_resume':'plan_resume',e=node('div',undefined,'entry'),b=btn('Reprendre',()=>send({action:a,id:row.id},'Reprendre '+row.kind+' #'+row.id+' ? Nouveaux appels potentiellement facturables, sans remise à zéro des plafonds.'));b.dataset.command=a;e.append(node('b',row.kind+' #'+row.id),node('small',row.state),b);out.append(e);continue;
     }else if(row.kind==='campaign'&&row.state==='actif'){action='campaign_stop';label='Arrêter la campagne';title='Campagne #'+row.id+' · '+row.goal;}
     else if(row.kind==='plan'&&row.state==='active'){action='plan_stop';label='Suspendre le plan';title='Plan #'+row.id;}
     else if(row.kind==='periodic'&&['active','suspended'].includes(row.state)){action='periodic_revoke';label='Révoquer l’autorisation';title='Autorisation périodique #'+row.id;}
     else continue;
     const e=node('div',undefined,'entry'),b=btn(label,()=>send({action,id:row.id},label+' #'+row.id+' ? Les engagements existants sont conservés. Une mission liée peut arrêter sa campagne ; les plans et périodes actifs doivent être arrêtés au niveau approprié.'));
     b.dataset.command=action;e.append(node('b',title),node('small',row.state),b);out.append(e);
    }
    if(!out.children.length)out.append(node('p','Aucune action sur un état existant disponible dans cet instantané.','muted'));
    status.textContent=uncertain?'État relu. Vérifie le résultat précédent avant toute nouvelle commande.':'États locaux relus. Les protections du moteur restent applicables.';lock(false);
   }catch(e){if(n===seq){out.replaceChildren();status.textContent='États indisponibles. Aucune commande proposée.';lock(true);}}
  }
  async function send(body,message){
   if(!online||pending||active!==kind||(paid.has(body.action)&&!isOwner())||(commercialActions.has(body.action)&&!isCommercial())||!confirm(message))return;
   pending=true;lock(true);const n=++seq;status.textContent='Transmission de la commande…';
   const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
   try{
    const owner=paid.has(body.action);const r=await fetch(owner?'/campus/owner-command':'/campus/command',{method:'POST',headers:{[owner?'X-Campus-Owner':'X-Campus-Command']:owner?ownerToken:token,'Content-Type':'application/json'},body:JSON.stringify({...body,confirm:true}),cache:'no-store',signal:controller.signal});
    const result=await r.json();
    if(!r.ok){if(n===seq)status.textContent='Commande refusée : '+(result.error||'HTTP '+r.status);return;}
    uncertain=false;if(n===seq){if(body.action==='mission_demo')textarea.value='';status.textContent=result.state==='revocation_pending'?'Révocation locale demandée · confirmation du canal encore indisponible.':result.state==='published'?'Publication TEST locale confirmée · collecte non autorisée.':result.state==='collecting'?'Collecte TEST locale confirmée.':result.state==='revoked'?'Révocation TEST confirmée.':'Commande acceptée par le moteur. Vérifie son état après actualisation.';out.replaceChildren();}
    document.dispatchEvent(new Event('campus-command-completed'));
   }catch(e){uncertain=true;if(n===seq)status.textContent='Résultat incertain : ne relance pas sans vérifier les états.';}
   finally{clearTimeout(timer);pending=false;if(n===seq)lock(true);}
  }
  load();
 }
 window.AESCampusCommands=Object.freeze({open,setStation,setOnline});
})();
