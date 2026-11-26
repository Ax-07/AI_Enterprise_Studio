/* D04.2/D04.3: on-demand native read tools. No POST and no HTML rendering of stored content. */
(() => {
    'use strict';
    const names=Object.freeze({missions:'Missions',work:'Tâches',files:'Livrables',memory:'Mémoire collective',finance:'Dépenses API',opps:'Opportunités',home:'Autopilote & campagnes',portfolio:'Portefeuille d’activités',laboratory:'Laboratoire',tools:'Connecteurs & outils',agents:'Organisation des agents',goals:'Objectifs & XP',decisions:'Décisions réservées',owner:'Tableau de direction'});
    const token=document.querySelector('meta[name="campus-session"]').content;
    const panel=document.getElementById('native-tool');
    const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
    const button=(label,fn)=>{const e=node('button',label);e.type='button';e.addEventListener('click',fn);return e;};
    const mode=m=>m==='demo'?'SIMULATION enregistrée':m==='cloud'?'CLOUD · moteur':'Mode '+String(m??'inconnu');
    const money=n=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'USD',minimumFractionDigits:4,maximumFractionDigits:6}).format(n/1e6);
    let station=null, controller=null, epoch=0, active=null;
    function reset(){epoch++;controller?.abort();controller=null;active=null;panel.replaceChildren();panel.hidden=true;}
    function setStation(id){if(station!==id){reset();station=id;}}
    function entry(title,detail){const e=node('div',undefined,'entry');e.append(node('b',title),node('small',detail));return e;}
    function safeName(name){return String(name||'livrable.txt').replace(/[\\/<>:"|?*\x00-\x1f\x7f]/g,'_').slice(0,180)||'livrable.txt';}
    function download(row){
        const url=URL.createObjectURL(new Blob([row.content],{type:'application/octet-stream'}));
        const a=node('a');a.href=url;a.download=safeName(row.name);document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
    function renderRows(tool,rows,out,loadDetail){
        if(!rows.length){out.append(node('p','Aucune entrée correspondante.','muted'));return;}
        for(const r of rows){
            let e;
            if(tool==='missions')e=entry('#'+r.id+' · '+r.title,r.state+' · '+mode(r.mode)+' · '+r.created);
            else if(tool==='work'){e=entry('#'+r.id+' · '+r.agent,r.state+' · mission #'+r.mission+' · '+mode(r.mode));e.append(node('p',r.goal));}
            else if(tool==='files'){e=entry(r.name+' · V'+r.version,r.agent+' · mission #'+r.mission+' · '+mode(r.mode)+' · '+r.bytes+' octets');e.append(button('Consulter / télécharger',()=>loadDetail('artifact',r.id)));}
            else if(tool==='memory'){e=entry('#'+r.id+' · '+r.agent,r.title+' · mission #'+r.mission+' · '+mode(r.mode));e.append(node('p',r.excerpt),button('Lire le rapport',()=>loadDetail('report',r.id)));}
            else if(tool==='finance'){e=entry(r.agent+' · '+mode(r.mode),r.calls+' appel(s) · '+money(r.committed_micro_usd)+' engagés (estimation)');e.append(node('small','Usage mesuré : '+money(r.measured_micro_usd)+' · Non mesuré / réservé : '+money(r.unmeasured_micro_usd)));}
            else if(tool==='opps'){e=entry('#'+r.id+' · '+r.title,r.status+' · mission #'+r.mission+' · '+mode(r.mode));e.append(node('p',r.body),node('small','Prochain test : '+(r.next_test||'Non renseigné')));}
            else if(tool==='home'){
                if(r.kind==='campaign'){e=entry('Campagne #'+r.id+' · '+r.goal,r.state+' · '+r.missions+' / '+r.max_missions+' missions');e.append(node('small',money(r.committed)+' / '+money(r.budget)+' engagés / plafond · quota Brave '+r.search_cap));}
                else if(r.kind==='plan'){e=entry('Plan #'+r.id,r.state+' · '+r.campaigns+' / '+r.max_campaigns+' campagnes');e.append(node('small',money(r.committed)+' / '+money(r.budget)+' engagés / plafond · '+money(r.per_campaign)+' par campagne'));}
                else {e=entry('Autorisation périodique #'+r.id,r.state+' · '+r.cadence+' · '+r.slots+' / '+r.periods+' périodes ouvertes');e.append(node('small','Plafond total '+money(r.total_budget)+' · par période '+money(r.period_budget)+' · expire '+new Date(r.expires*1000).toLocaleString('fr-FR')));}
                if(r.reason)e.append(node('p',r.reason));
            }
            else if(tool==='portfolio'){e=entry('#'+r.id+' · '+r.title,r.state+' · '+r.missions+' mission(s) · '+r.artifacts+' livrable(s)');e.append(node('small','Engagements API estimés : '+money(r.committed)));}
            else if(tool==='laboratory'){e=entry('Essai #'+r.id+' · '+r.name+' · V'+r.version,r.status+' · '+mode(r.mode)+' · '+r.created);e.append(node('small','Profil '+r.profile+' · révision '+r.revision+' · taille '+r.size+(r.campaign?' · campagne #'+r.campaign:'')));}
            else if(tool==='tools'){
                if(r.kind==='capability'){e=entry(r.label,r.provider+' · '+(r.implemented?'Implémenté':'Non implémenté')+' · '+(r.enabled?'Autorisé par politique':'Non autorisé'));e.append(node('small',r.policy_present?r.calls+' / '+r.max_calls+' tentatives · '+money(r.reserved)+' / '+money(r.budget)+' réservés / plafond':'Politique absente'));e.append(node('small','Disponibilité externe non testée'));}
                else e=entry('Tentative #'+r.id+' · '+r.capability,r.actor+' · '+r.state+' · '+money(r.reserved)+' réservés · '+r.created);
            }
            else if(tool==='owner'){
                e=node('div',undefined,'owner-summary');
                const a=r.active;
                const metrics=node('div',undefined,'owner-metrics');
                for(const [k,v] of [['Plafond API local',money(r.budget)],['Engagements estimés',money(r.committed)],['Solde local estimé',money(r.remaining)],['Décisions en attente',String(r.pending)],['Brave · tentatives / limite',r.searches+' / '+r.search_limit],['Agents configurés',String(r.configured_agents)]]){
                    const card=node('div',undefined,'metric');card.append(node('small',k),node('strong',v));metrics.append(card);
                }
                e.append(metrics);
                if(r.over_budget)e.append(node('p','Plafond local dépassé : aucun solde disponible.','error'));
                e.append(entry('Détail des engagements','Usage mesuré : '+money(r.measured)+' · non mesuré / réservé : '+money(r.unmeasured)),
                    entry('Ressources déclarées','OpenAI : '+(r.openai_configured?'configuré':'non configuré')+' · Brave : '+(r.brave_configured?'configuré':'non configuré')+' · bac à sable : '+(r.sandbox_enabled?'activé':'désactivé')),
                    entry('Limites par mission',money(r.mission_budget)+' · '+r.mission_calls+' appels maximum'));
                e.append(node('h3','Pilotage actif enregistré'));
                for(const [key,label] of [['periods','Autorisations périodiques'],['plans','Plans'],['campaigns','Campagnes'],['missions','Missions']]){
                    e.append(node('b',label));
                    if(!a[key].length)e.append(node('p','Aucun état actif enregistré.','muted'));
                    for(const row of a[key])e.append(entry('#'+row.id+' · '+(row.title||row.goal||row.cadence||label),row.state+(row.mode?' · '+mode(row.mode):'')+(row.expires?' · expire '+new Date(row.expires*1000).toLocaleString('fr-FR'):'')+(row.budget!==undefined?' · plafond '+money(row.budget):row.total_budget!==undefined?' · plafond '+money(row.total_budget):'')));
                }
                e.append(node('p','Configuration présente ≠ disponibilité externe vérifiée. Les soldes sont les plafonds locaux, pas les crédits restants chez les fournisseurs.','muted'));
            }
            else if(tool==='decisions'){
                e=entry('#'+r.id+' · '+(r.objet||'Demande sans objet lisible'),r.state+' · mission #'+r.mission+' · '+mode(r.mode));
                e.append(node('small',r.title),node('p',r.justification||'Justification non disponible'),node('small','Coût estimé déclaré : '+(r.cout_estime||'Non indiqué')),node('small','Risques déclarés : '+(r.risques||'Non indiqués')));
                if(r.state==='en attente')e.append(node('p',r.may_resume?'Attention : le traitement de cette demande peut reprendre une mission. En mode Cloud, de nouveaux appels peuvent être facturés.':'Décision réservée au propriétaire. Une acceptation pour étude ne constitue pas une autorisation d’achat.','station-pending'));
            }
            else if(tool==='agents'||tool==='goals'){e=entry(r.id+' · '+r.xp+' XP',r.role);e.append(node('small','Tâches enregistrées : '+(Object.entries(r.task_counts).map(([m,n])=>n+' · '+mode(m)).join(' / ')||'aucune')));if(tool==='agents')e.append(node('p','Permissions moteur : '+r.permissions.join(', ')));}
            else {e=entry(tool==='artifact'?r.name+' · V'+r.version:'Rapport #'+r.id,r.agent+' · mission #'+r.mission+' · '+mode(r.mode));e.append(node('pre',r.content));if(tool==='artifact')e.append(button('Télécharger le fichier original',()=>download(r)));}
            out.append(e);
        }
    }
    function open(tool){
        if(!station||!Object.hasOwn(names,tool))return;
        reset();active=tool;panel.hidden=false;
        const title=node('h3',names[tool]+' · consultation locale');
        const descriptions={owner:'Vue consolidée des ressources et du pilotage, sans vérification réseau. Aucun chiffre d’affaires ni bénéfice déduit.',decisions:'100 demandes au maximum, en attente en priorité. Les coûts et risques sont déclarés par les agents, pas des devis vérifiés. Le traitement est disponible dans le bureau du propriétaire ; le module historique reste accessible.',home:'États enregistrés des campagnes, plans et autorisations périodiques (15 de chaque). Aucun lancement ni reprise. Les montants sont des engagements locaux estimés.',portfolio:'100 dernières activités enregistrées. Aucune création de projet ni synchronisation automatique.',laboratory:'100 derniers essais enregistrés ; aucun test déclenché. Un statut ne constitue pas une validation commerciale.',tools:'Catalogue et politiques locales, 50 dernières tentatives. Aucun test de disponibilité ni appel de connecteur.',agents:'Rôles et permissions actuels du moteur, en consultation. Aucun agent créé.',goals:'XP enregistrés par le moteur et tâches par mode. Les XP ne donnent aucun droit ; les objectifs éditables restent dans le module historique.'};
        const desc=node('p',descriptions[tool]|| (tool==='finance'?'Registre API local, tous modes. Les montants sont des estimations locales, pas des factures ni des revenus. Groupes limités à 100.':tool==='opps'?'Hypothèses enregistrées, pas des marchés ni des revenus validés. 100 dernières entrées.':tool==='memory'?'Recherche littérale dans les rapports enregistrés (50 résultats maximum ; insensibilité à la casse ASCII).': '100 dernières entrées du moteur, tous bâtiments et tous modes.'),'muted');
        const actions=node('div',undefined,'native-actions'),status=node('p','','muted'),out=node('div',undefined,'native-results');
        status.setAttribute('role','status');status.setAttribute('aria-live','polite');
        let last={};
        async function load(kind,params={}){
            if(active!==tool)return;
            const n=++epoch;controller?.abort();controller=new AbortController();const signal=controller.signal;
            const timer=setTimeout(()=>controller?.signal===signal&&controller.abort(),8000);
            status.textContent='Lecture locale…';out.replaceChildren();
            try{
                const q=new URLSearchParams({tool:kind,...params});
                const res=await fetch('/campus/read?'+q,{headers:{'X-Campus-Session':token},cache:'no-store',signal});
                if(!res.ok)throw Error(String(res.status));
                const payload=await res.json();
                if(n!==epoch)return;
                if(payload.schema!=='aes.campus.tool.v1'||payload.read_only!==true||payload.tool!==kind||!Array.isArray(payload.rows))throw Error('schema');
                status.textContent=payload.rows.length+' résultat(s) · instantané local';
                if(kind==='artifact'||kind==='report')out.append(button('← Retour aux résultats',()=>load(tool,last)));
                renderRows(kind,payload.rows,out,(k,id)=>load(k,{id:String(id)}));
            }catch(e){if(n===epoch){out.replaceChildren();status.textContent='Lecture indisponible'+(e.message==='413'?' : contenu trop volumineux':e.message==='400'?' : paramètres invalides':'')+'.';}}
            finally{clearTimeout(timer);}
        }
        actions.append(button('Fermer',reset),button('Actualiser',()=>{if(tool!=='memory'||last.q)load(tool,last);}));
        panel.append(title,desc,actions);
        if(tool==='memory'){
            const form=node('form',undefined,'native-form'),input=node('input');input.type='search';input.minLength=2;input.maxLength=120;input.required=true;input.placeholder='Mot-clé, agent, mission';input.setAttribute('aria-label','Recherche mémoire');
            const submit=node('button','Rechercher');submit.type='submit';form.append(input,submit);form.addEventListener('submit',e=>{e.preventDefault();last={q:input.value.trim()};load(tool,last);});panel.append(form);
        }
        panel.append(status,out);
        if(tool!=='memory')load(tool);
    }
    window.AESNativeTools=Object.freeze({names,open,setStation,reset});
})();
