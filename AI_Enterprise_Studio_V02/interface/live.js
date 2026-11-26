(() => {
    'use strict';
    const $=id=>document.getElementById(id);
    const token=document.querySelector('meta[name="campus-session"]').content;
    let data=null, selected='ATLAS', busy=false;
    const labels={ATLAS:'Direction',ORION:'Recherche',NEXUS:'Production',MIDAS:'Finance',HERMES:'Commerce',SENTINEL:'Sécurité',CORE:'DATA CORE'};
    const mode=m=>m==='demo'?'SIMULATION enregistrée':m==='cloud'?'CLOUD · moteur':('Mode '+String(m??'inconnu'));
    const money=n=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'USD',minimumFractionDigits:4,maximumFractionDigits:6}).format(n/1e6);
    const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
    function entry(title,detail){const n=node('div',undefined,'entry');n.append(node('b',title),node('small',detail));return n;}
    function list(id,rows,render,empty='Aucune entrée enregistrée'){ $(id).replaceChildren(...(rows.length?rows.map(render):[node('p',empty,'muted')])); }
    function metric(title,value){const n=node('div',undefined,'metric');n.append(node('small',title),node('strong',String(value)));return n;}
    function renderBuilding(){
        const b=data.buildings.find(x=>x.id===selected);if(!b)return;
        $('detail-title').textContent=labels[b.id]+' · agents du moteur';
        document.querySelectorAll('#buildings button').forEach(btn=>btn.setAttribute('aria-pressed',String(btn.dataset.id===selected)));
        const ids=new Set(b.agents.map(a=>a.id));
        list('agents',b.agents,a=>{const active=Object.entries(a.active_tasks_by_mode);return entry(a.id+' · '+a.role,active.length?active.map(([m,n])=>n+' tâche(s) en cours · '+mode(m)).join(' / '):'Aucune tâche dynamique en cours observée');});
        list('tasks',data.tasks.filter(t=>ids.has(t.agent)),t=>entry('#'+t.id+' · '+t.agent,t.state+' · mission #'+t.mission+' · '+mode(t.mode)));
    }
    function render(){
        const agents=data.buildings.reduce((n,b)=>n+b.agents.length,0)+data.unmapped_agents.length;
        const count=m=>data.mission_counts.filter(x=>x.mode===m).reduce((n,x)=>n+x.count,0);
        $('metrics').replaceChildren(metric('Agents configurés',agents),metric('Missions CLOUD enregistrées',count('cloud')),metric('Missions SIMULATION enregistrées',count('demo')),metric('Engagement API local estimé (USD)',money(data.budget.committed_estimate_micro_usd)),metric('Plafond API local (USD)',money(data.budget.limit_micro_usd)),metric('Demandes en attente (tous modes)',data.pending_requests));
        $('buildings').replaceChildren(...data.buildings.map(b=>{const btn=node('button',labels[b.id]||b.id);btn.type='button';btn.dataset.id=b.id;btn.addEventListener('click',()=>{selected=b.id;renderBuilding();});return btn;}));
        renderBuilding();
        if(data.unmapped_agents.length)$('agents').append(node('p','Agents non affectés au campus : '+data.unmapped_agents.map(a=>a.id).join(', '),'muted'));
        list('missions',data.missions,m=>entry('#'+m.id+' · '+m.title,m.state+' · '+mode(m.mode)+' · '+m.created));
        list('events',data.events,e=>entry(e.agent+' · '+e.action,'Mission #'+e.mission+' · '+mode(e.mode)+' · '+e.created+' · '+(e.ok===1?'OK':e.ok===0?'Échec':'Résultat inconnu')));
        list('artifacts',data.artifacts,a=>entry(a.name+' · V'+a.version,a.agent+' · mission #'+a.mission+' · '+mode(a.mode)));
    }
    function clear(){data=null;for(const id of ['metrics','buildings','agents','tasks','missions','events','artifacts'])$(id).replaceChildren();$('detail-title').textContent='Agents du bâtiment';}
    async function refresh(){
        if(busy)return;busy=true;$('refresh').disabled=true;
        const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),8000);
        try{
            const r=await fetch('/campus/live-data',{method:'GET',headers:{'X-Campus-Session':token},cache:'no-store',credentials:'same-origin',signal:controller.signal});
            if(!r.ok)throw Error('HTTP '+r.status);
            const next=await r.json();
            if(next.schema!=='aes.campus.read.v1'||next.source!=='local_sqlite'||next.read_only!==true)throw Error('Source incompatible');
            data=next;render();$('status').className='';$('status').textContent='Connecté · instantané local '+new Date(data.generated_at).toLocaleString('fr-FR');
        }catch(e){clear();$('status').className='error';$('status').textContent='Données indisponibles · aucune valeur de remplacement affichée.';}
        finally{clearTimeout(timer);busy=false;$('refresh').disabled=false;}
    }
    $('refresh').addEventListener('click',refresh);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});setInterval(()=>{if(!document.hidden)refresh();},15000);refresh();
})();
