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

    const layout=window.AESLiveLayout;
    const byId=new Map(layout.map(b=>[b.id,b]));
    let scene='campus', floorId=null, stationId=null;
    const svgNS='http://www.w3.org/2000/svg';
    const svg=(tag,attrs={})=>{const el=document.createElementNS(svgNS,tag);for(const [k,v] of Object.entries(attrs))el.setAttribute(k,String(v));return el;};
    const levelLabel=n=>n===0?'RDC':String(n).padStart(2,'0');
    const project=(x,y,z=0)=>[500+(x-y)*.96,103+(x+y)*.46-z];
    const polygon=(points,attrs={})=>svg('polygon',{points:points.map(p=>project(...p).join(',')).join(' '),...attrs});
    function initMap(){
        const map=svg('svg',{viewBox:'0 0 1000 600',class:'campus-map-svg',role:'group','aria-label':'Campus interactif'});
        map.append(svg('image',{href:'/campus/assets/campus_1_1.webp',x:0,y:0,width:1000,height:600,preserveAspectRatio:'none'}));
        for(const b of [...layout].sort((a,b)=>a.x+a.y-b.x-b.y)){
            const w=b.w*.82,d=b.d*.82,h=b.h*.77,X=b.x-w/2,Y=b.y-d/2,top=b.type==='core'?51:h+(b.type==='hq'?28:8);
            const g=svg('g',{class:'live-map-node',tabindex:0,role:'button','aria-label':labels[b.id]+' · ouvrir l’ascenseur','data-building':b.id,style:'--accent:'+b.color});
            const a=X-9,c=X+w+9,e=Y-9,f=Y+d+9;
            for(const pts of [[[a,f,5],[c,f,5],[c,f,top],[a,f,top]],[[c,e,5],[c,f,5],[c,f,top],[c,e,top]],[[a,e,top],[c,e,top],[c,f,top],[a,f,top]],[[a,e,6],[c,e,6],[c,f,6],[a,f,6]]])g.append(polygon(pts,{class:'live-hit'}));
            const [x,y]=project(b.x,b.y,top+8);const t=svg('text',{x,y,class:'map-label'});t.textContent=b.id==='CORE'?'DATA CORE':b.id;g.append(t);
            g.addEventListener('click',()=>openLift(b.id));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openLift(b.id);}});map.append(g);
        }
        $('campus-map').replaceChildren(map);
        $('buildings').replaceChildren(...layout.map(b=>{const btn=node('button',labels[b.id]);btn.type='button';btn.dataset.id=b.id;btn.addEventListener('click',()=>openLift(b.id));return btn;}));
    }
    const modules=window.AESLiveModules;
    const hasModule=st=>Object.hasOwn(modules.stations,st.id)&&modules.stations[st.id].length>0;
    function updateModuleLinks(st){
        const out=$('station-modules');const sig=st?.id||'';
        window.AESNativeTools.setStation(sig||null);
        window.AESCampusCommands.setStation(sig||null);
        if(out.dataset.station===sig)return;out.dataset.station=sig;out.replaceChildren();
        if(!st||!hasModule(st))return;
        out.append(node('h3','Accès aux modules existants'),node('p','Ouvre l’interface historique (module complet, sans filtre automatique). Ses confirmations et permissions restent applicables.','muted'));
        const links=node('div',undefined,'module-links');
        if(st.id.startsWith('OWNER:station:')){const dashboard=node('button','Tableau de direction');dashboard.type='button';dashboard.dataset.native='owner';dashboard.addEventListener('click',()=>window.AESNativeTools.open('owner'));links.append(dashboard);}
        if(selected==='HERMES'&&['HERMES','SHOWROOM','ADS183','VIDEO183','PUBLISH183','SUPPORT17'].includes(floorId)&&modules.stations[st.id].includes('business')){const m=node('button','Dossiers HERMES & marketing · préparation interne');m.type='button';m.dataset.native='marketing';m.addEventListener('click',()=>window.AESNativeTools.open('marketing'));links.append(m);}
        for(const page of modules.stations[st.id]){
            if(!Object.hasOwn(modules.pages,page))continue;
            const a=node('a',modules.pages[page]);a.dataset.module=page;
            a.href='/?'+new URLSearchParams({page,campusBuilding:selected,campusFloor:floorId,campusStation:st.id});
            if(Object.hasOwn(window.AESNativeTools.names,page)){
                const btn=node('button','Consulter ici · '+window.AESNativeTools.names[page]);btn.type='button';btn.dataset.native=page;btn.addEventListener('click',()=>window.AESNativeTools.open(page));links.append(btn);
            }
            if(page==='home'||page==='missions'||(st.id.startsWith('OWNER:station:')&&page==='decisions')){const cmd=node('button','Commandes · '+modules.pages[page]);cmd.type='button';cmd.dataset.commands=page;cmd.addEventListener('click',()=>window.AESCampusCommands.open(page));links.append(cmd);}
            links.append(a);
        }out.append(links);
    }
    function restoreLocation(){
        const q=new URLSearchParams(location.search),b=byId.get(q.get('building'));
        if(!b)return;selected=b.id;scene='lift';
        const f=b.floors.find(x=>x.id===q.get('floor'));if(!f)return;
        scene='room';floorId=f.id;
        const st=f.stations.find(x=>x.id===q.get('station'));stationId=st?.id||null;
    }
    function currentFloor(){return byId.get(selected)?.floors.find(f=>f.id===floorId);}
    function openLift(id){if(!byId.has(id))return;selected=id;scene='lift';floorId=null;stationId=null;renderScene();renderBuilding();$('lift-view').querySelector('button')?.focus();}
    function openFloor(id){const f=byId.get(selected)?.floors.find(f=>f.id===id);if(!f)return;if(id==='OWNER'&&!document.querySelector('meta[name="campus-owner-session"]').content){location.assign('/campus/live/?building=ATLAS&floor=OWNER');return;}scene='room';floorId=id;stationId=null;renderScene();renderBuilding();$('lift-back').focus();}
    function openCampus(){scene='campus';floorId=null;stationId=null;renderScene();renderBuilding();document.querySelector('[data-building="'+selected+'"]')?.focus();}
    function tower(b){
        const h=b.floors.length*28+40,t=svg('svg',{viewBox:'0 0 170 '+h,class:'lift-tower','aria-hidden':'true'});
        for(const f of [...b.floors].reverse()){
            const y=8+(b.floors.length-1-f.level)*28;
            t.append(svg('polygon',{points:'26,'+y+' 85,'+(y+17)+' 145,'+y+' 85,'+(y-10),fill:'#314c63',stroke:b.color}),svg('polygon',{points:'26,'+y+' 85,'+(y+17)+' 85,'+(y+43)+' 26,'+(y+26),fill:'#223b51',stroke:b.color}),svg('polygon',{points:'85,'+(y+17)+' 145,'+y+' 145,'+(y+26)+' 85,'+(y+43),fill:'#172d40',stroke:b.color}));
            const n=svg('text',{x:18,y:y+18,fill:b.color,'font-size':10,'text-anchor':'end'});n.textContent=levelLabel(f.level);t.append(n);
        }
        return t;
    }
    function renderScene(){
        const b=byId.get(selected),f=currentFloor();
        $('campus-map').hidden=scene!=='campus';$('lift-view').hidden=scene!=='lift';$('room-view').hidden=scene!=='room';
        $('campus-back').hidden=scene==='campus';$('lift-back').hidden=scene!=='room';
        document.querySelectorAll('#buildings button').forEach(btn=>btn.setAttribute('aria-pressed',String(btn.dataset.id===selected)));
        if(scene==='campus'){$('scene-title').textContent='Campus · 7 bâtiments';$('scene-note').textContent='Sélectionne un bâtiment sur le campus ou dans la liste.';return;}
        if(scene==='lift'){
            $('scene-title').textContent='Ascenseur · '+labels[b.id];$('scene-note').textContent='Services du design · leur présence ne signifie pas qu’ils sont opérationnels.';
            const wrap=node('div',undefined,'lift-layout'),list=node('div',undefined,'floor-list');wrap.append(tower(b),list);
            for(const f of [...b.floors].reverse()){const btn=node('button');btn.type='button';btn.dataset.floor=f.id;btn.append(node('b',levelLabel(f.level)+' · '+f.name),node('small',f.description));btn.addEventListener('click',()=>openFloor(f.id));list.append(btn);}
            $('lift-view').replaceChildren(wrap);return;
        }
        $('scene-title').textContent=levelLabel(f.level)+' · '+f.name;$('scene-note').textContent='Décor du service · les données de droite sont celles du bâtiment, pas une mesure de l’occupation du service.';
        const room=$('room-view');room.replaceChildren();
        if(f.asset){const im=node('img',undefined,'room-image');im.src='/campus/assets/'+f.asset;im.alt='Décor original : '+f.name;room.append(im);}
        else room.append(node('div','Décor HD dédié non disponible dans la maquette originale. Les postes sont accessibles ci-dessous.','room-missing'));
        const buttons=node('div',undefined,'station-list');
        for(const st of f.stations){const btn=node('button');btn.type='button';btn.dataset.station=st.id;btn.setAttribute('aria-pressed',String(stationId===st.id));btn.append(node('b',st.name),node('small',st.description));if(hasModule(st))btn.append(node('small','Module existant ↗','module-marker'));btn.addEventListener('click',()=>{stationId=st.id;buttons.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.station===stationId)));renderStation();});buttons.append(btn);}room.append(buttons);
    }
    function renderStation(){
        const st=currentFloor()?.stations.find(s=>s.id===stationId),panel=$('station-detail'),out=$('station-content');
        panel.hidden=scene!=='room'||!st;updateModuleLinks(panel.hidden?null:st);if(panel.hidden){out.replaceChildren();return;}
        $('station-title').textContent=st.name;out.replaceChildren();
        if(!data){out.append(node('p','Données indisponibles.','muted'));return;}
        const b=data.buildings.find(b=>b.id===selected),ids=new Set(b?.agents.map(a=>a.id)||[]);
        const note=t=>out.append(node('p',t,'muted'));
        if(st.destination==='agentDetail'){note('Agents configurés du bâtiment, non affectés à ce poste.');for(const a of b?.agents||[])out.append(entry(a.id,a.role));}
        else if(st.destination==='agentLog'){note('Événements récents du bâtiment, tous services confondus.');for(const e of data.events.filter(e=>ids.has(e.agent)))out.append(entry(e.agent+' · '+e.action,mode(e.mode)+' · '+e.created));if(out.children.length===1)note('Aucun événement dans cet instantané.');}
        else if(st.destination==='finance'){note('Registre API global uniquement. Revenus et bénéfices non raccordés.');out.append(entry('Engagement API estimé',money(data.budget.committed_estimate_micro_usd)),entry('Plafond local',money(data.budget.limit_micro_usd)));}
        else if(st.destination==='approval'){note('Demandes globales en attente, tous modes. Aucune validation possible depuis ce poste.');out.append(entry('Demandes en attente',String(data.pending_requests)));}
        else if(st.destination==='classic'){note('Agents configurés du moteur, tous bâtiments.');for(const a of data.buildings.flatMap(b=>b.agents))out.append(entry(a.id,a.role));}
        else out.append(node('p',hasModule(st)?'Données propres à ce poste non intégrées au campus. Le module existant est accessible ci-dessous.':'Fonction métier non raccordée à ce poste. Aucun résultat simulé ni action disponible.','station-pending'));
    }
    function renderBuilding(){
        if(!data){$('detail-title').textContent=labels[selected]+' · données indisponibles';$('agents').replaceChildren();$('tasks').replaceChildren();renderStation();return;}
        const b=data.buildings.find(x=>x.id===selected);if(!b)return;
        $('detail-title').textContent=labels[b.id]+' · agents du moteur';
        document.querySelectorAll('#buildings button').forEach(btn=>btn.setAttribute('aria-pressed',String(btn.dataset.id===selected)));
        const ids=new Set(b.agents.map(a=>a.id));
        list('agents',b.agents,a=>{const active=Object.entries(a.active_tasks_by_mode);return entry(a.id+' · '+a.role,active.length?active.map(([m,n])=>n+' tâche(s) en cours · '+mode(m)).join(' / '):'Aucune tâche dynamique en cours observée');});
        list('tasks',data.tasks.filter(t=>ids.has(t.agent)),t=>entry('#'+t.id+' · '+t.agent,t.state+' · mission #'+t.mission+' · '+mode(t.mode)));
        if(data.unmapped_agents.length)$('agents').append(node('p','Agents non affectés au campus : '+data.unmapped_agents.map(a=>a.id).join(', '),'muted'));
        renderStation();
    }
    function render(){
        const agents=data.buildings.reduce((n,b)=>n+b.agents.length,0)+data.unmapped_agents.length;
        const count=m=>data.mission_counts.filter(x=>x.mode===m).reduce((n,x)=>n+x.count,0);
        $('metrics').replaceChildren(metric('Agents configurés',agents),metric('Missions CLOUD enregistrées',count('cloud')),metric('Missions SIMULATION enregistrées',count('demo')),metric('Engagement API local estimé (USD)',money(data.budget.committed_estimate_micro_usd)),metric('Plafond API local (USD)',money(data.budget.limit_micro_usd)),metric('Demandes en attente (tous modes)',data.pending_requests));
        renderBuilding();
        list('missions',data.missions,m=>entry('#'+m.id+' · '+m.title,m.state+' · '+mode(m.mode)+' · '+m.created));
        list('events',data.events,e=>entry(e.agent+' · '+e.action,'Mission #'+e.mission+' · '+mode(e.mode)+' · '+e.created+' · '+(e.ok===1?'OK':e.ok===0?'Échec':'Résultat inconnu')));
        list('artifacts',data.artifacts,a=>entry(a.name+' · V'+a.version,a.agent+' · mission #'+a.mission+' · '+mode(a.mode)));
    }
    function clear(){window.AESCampusCommands.setOnline(false);window.AESNativeTools.reset();data=null;for(const id of ['metrics','agents','tasks','missions','events','artifacts'])$(id).replaceChildren();renderBuilding();}
    async function refresh(){
        if(busy)return;busy=true;$('refresh').disabled=true;
        const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),8000);
        try{
            const r=await fetch('/campus/live-data',{method:'GET',headers:{'X-Campus-Session':token},cache:'no-store',credentials:'same-origin',signal:controller.signal});
            if(!r.ok)throw Error('HTTP '+r.status);
            const next=await r.json();
            if(next.schema!=='aes.campus.read.v1'||next.source!=='local_sqlite'||next.read_only!==true)throw Error('Source incompatible');
            data=next;window.AESCampusCommands.setOnline(true);render();$('status').className='';$('status').textContent='Connecté · instantané local '+new Date(data.generated_at).toLocaleString('fr-FR');
        }catch(e){clear();$('status').className='error';$('status').textContent='Données indisponibles · aucune valeur de remplacement affichée.';}
        finally{clearTimeout(timer);busy=false;$('refresh').disabled=false;}
    }
    restoreLocation();initMap();renderScene();renderBuilding();$('campus-back').addEventListener('click',openCampus);$('lift-back').addEventListener('click',()=>openLift(selected));
    document.addEventListener('campus-command-completed',refresh);
    $('refresh').addEventListener('click',refresh);document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});setInterval(()=>{if(!document.hidden)refresh();},15000);refresh();
})();
