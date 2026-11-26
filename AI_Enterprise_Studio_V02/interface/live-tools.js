/* D04.2: on-demand native read tools. No POST and no HTML rendering of stored content. */
(() => {
    'use strict';
    const names=Object.freeze({missions:'Missions',work:'Tâches',files:'Livrables',memory:'Mémoire collective',finance:'Dépenses API',opps:'Opportunités'});
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
            else {e=entry(tool==='artifact'?r.name+' · V'+r.version:'Rapport #'+r.id,r.agent+' · mission #'+r.mission+' · '+mode(r.mode));e.append(node('pre',r.content));if(tool==='artifact')e.append(button('Télécharger le fichier original',()=>download(r)));}
            out.append(e);
        }
    }
    function open(tool){
        if(!station||!Object.hasOwn(names,tool))return;
        reset();active=tool;panel.hidden=false;
        const title=node('h3',names[tool]+' · consultation locale');
        const desc=node('p',tool==='finance'?'Registre API local, tous modes. Les montants sont des estimations locales, pas des factures ni des revenus. Groupes limités à 100.':tool==='opps'?'Hypothèses enregistrées, pas des marchés ni des revenus validés. 100 dernières entrées.':tool==='memory'?'Recherche littérale dans les rapports enregistrés (50 résultats maximum ; insensibilité à la casse ASCII).': '100 dernières entrées du moteur, tous bâtiments et tous modes.','muted');
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
