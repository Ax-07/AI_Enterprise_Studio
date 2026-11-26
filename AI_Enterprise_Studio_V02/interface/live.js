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
    const stateNames={blocked:'Mission bloquée · tâche non résolue',waiting:'Attente de décision / tâche',running_recorded:'Tâche marquée en cours',selected:'Dernière tâche sélectionnée',queued:'Tâche non résolue'};
    const statePriority=['blocked','waiting','running_recorded','selected','queued'];
    const modeShort=m=>m==='cloud'?'CLOUD':m==='demo'?'SIMULATION':String(m);
    let lastDelegation=null,flowTimer=null;
    const teams=new Map(window.AESLiveTeams.map(t=>[t.id,t]));
    let selectedSlot=null;
    function buildingActivity(b){
        const items=b.agents.flatMap(a=>a.activity||[]);
        const state=statePriority.find(k=>items.some(x=>x.state===k))||'quiet';
        const counts={};for(const r of items)counts[r.mode]=(counts[r.mode]||0)+r.count;
        return {state,detail:Object.entries(counts).map(([m,n])=>modeShort(m)+' '+n).join(' · ')||'Aucune tâche observée'};
    }
    function renderAlerts(){
        const out=$('alert-list');out.replaceChildren();
        if(!data){out.append(node('p','Données indisponibles · aucun état présumé.','muted'));return;}
        const count=state=>data.mission_counts.filter(x=>x.state===state).reduce((n,x)=>n+x.count,0);
        const alert=(state,title,detail,href,label)=>{
            const e=node('div',undefined,'owner-alert');e.dataset.activity=state;e.append(node('b',title),node('small',detail));
            if(href){const a=node('a',label);a.href=href;e.append(a);}out.append(e);
        };
        const owner='/campus/live/?building=ATLAS&floor=OWNER&station=OWNER%3Astation%3A';
        const pending=data.pending_requests,blocked=count('bloquée'),waiting=count('en attente');
        if(pending)alert('waiting',pending+' demande(s) en attente','Tous modes · décision éventuelle du propriétaire.',owner+'4','Ouvrir les validations');
        if(blocked||waiting){
            const detail=data.attention_missions.map(m=>'#'+m.id+' · '+modeShort(m.mode)+' · '+m.state).join(' / ');
            alert(blocked?'blocked':'waiting',blocked+' mission(s) bloquée(s) · '+waiting+' en attente',detail||'États enregistrés, cause à examiner.','/?page=missions','Consulter les missions');
        }
        const limit=data.budget.limit_micro_usd,used=data.budget.committed_estimate_micro_usd;
        if(used>=limit)alert('blocked','Plafond API local atteint ou dépassé',money(used)+' / '+money(limit)+' · engagements estimés.',owner+'3','Ouvrir les finances');
        else if(used>=limit*.8)alert('waiting','80 % ou plus du plafond API engagé',money(used)+' / '+money(limit)+' · estimation locale.',owner+'3','Ouvrir les finances');
        if(!out.children.length)out.append(node('p','Aucun des points de vigilance surveillés dans cet instantané. Ce n’est pas un contrôle de santé complet.','muted'));
    }
    function agentStatus(a){
        if(!data)return {state:'unknown',detail:'Données indisponibles'};
        if(!a)return {state:'unknown',detail:'Agent non configuré'};
        const items=a.activity||[],state=statePriority.find(k=>items.some(x=>x.state===k))||'quiet';
        return {state,detail:items.length?items.map(r=>modeShort(r.mode)+' · '+(stateNames[r.state]||r.state)+' : '+r.count).join(' / '):'Aucune tâche dynamique non résolue observée'};
    }
    function currentTeam(){return teams.get(selected);}
    function teamAgent(slot){return data?.buildings.find(b=>b.id===selected)?.agents.find(a=>a.id===slot.agent);}
    function renderTeam(){
        const panel=$('team-view'),slots=$('team-slots'),detail=$('team-detail'),team=currentTeam();
        panel.hidden=scene!=='room'||floorId!==team?.floor;
        if(panel.hidden){slots.replaceChildren();detail.hidden=true;detail.replaceChildren();selectedSlot=null;return;}
        // Only rebuild on navigation, never during polling: focus and selections survive.
        if(slots.dataset.team!==selected||slots.children.length!==team.slots.length){
            slots.dataset.team=selected;slots.replaceChildren();selectedSlot=null;
            for(const slot of team.slots){
                const b=node('button',undefined,'team-slot');b.type='button';b.dataset.slot=slot.id;
                const art=svg('svg',{viewBox:'0 0 120 68',class:'team-desk','aria-hidden':'true'});
                art.append(svg('path',{d:'M12 48L60 24L108 48L60 67Z',fill:'#152d40',stroke:'#42627a'}),
                    svg('path',{d:'M20 35L65 12L103 31L58 54Z',fill:'#355168',stroke:'#577a91'}),
                    svg('path',{d:'M20 35V44L58 63V54M58 54L103 31V40L58 63',fill:'#172b3e',stroke:'#42627a'}),
                    svg('path',{d:'M64 12L88 1V20L64 32Z',class:'desk-screen',stroke:'#7895a7'}));
                const robot=svg('g',{class:'desk-avatar',transform:'translate(44 43)'});
                robot.append(svg('rect',{x:-6,y:-12,width:12,height:11,rx:2,fill:'#839eb4'}),svg('rect',{x:-8,y:-23,width:16,height:13,rx:4,fill:'#bccdd9'}),svg('rect',{x:-6,y:-20,width:12,height:6,rx:2,fill:'#102438'}),svg('circle',{cx:-2.5,cy:-17,r:1.4,class:'desk-eye'}),svg('circle',{cx:2.5,cy:-17,r:1.4,class:'desk-eye'}));art.append(robot);
                b.append(art,node('b',slot.name),node('small','','slot-identity'),node('small','','slot-status'));
                b.addEventListener('click',()=>{selectedSlot=slot.id;renderTeam();});slots.append(b);
            }
        }
        for(const slot of team.slots){
            const b=Array.from(slots.children).find(e=>e.dataset.slot===slot.id),a=teamAgent(slot);
            const s=slot.agent?agentStatus(a):{state:'unassigned',detail:slot.kind==='automation'?'Automate graphique · non attribué':'Poste graphique · non attribué'};
            b.dataset.activity=s.state;b.dataset.configured=String(Boolean(a));b.setAttribute('aria-pressed',String(selectedSlot===slot.id));
            b.querySelector('.slot-identity').textContent=slot.agent?(a?slot.agent+' · repère':slot.agent+' · attribution prévue'):'Sans agent associé';
            b.querySelector('.slot-status').textContent=s.detail;
        }
        const slot=team.slots.find(s=>s.id===selectedSlot);detail.hidden=!slot;detail.replaceChildren();
        if(slot){
            const a=teamAgent(slot);detail.append(node('h4',slot.name));
            if(!data){detail.append(node('p','Données indisponibles.','muted'));return;}
            if(!a){detail.append(node('p','Aucun agent configuré associé à cet emplacement. Aucun lancement ni réservation disponible.','muted'));return;}
            detail.append(entry(a.id+' · '+a.role,agentStatus(a).detail),node('p','Tâches récentes de cet agent, tous services confondus (extrait global).','muted'));
            const recent=data.tasks.filter(t=>t.agent===a.id).slice(0,5);
            if(!recent.length)detail.append(node('p','Aucune tâche dans cet extrait.','muted'));
            for(const t of recent)detail.append(entry('Tâche #'+t.id+' · mission #'+t.mission,t.state+' · '+mode(t.mode)));
        }
    }
    function renderLiftStatus(){
        const local=data?.buildings.find(b=>b.id===selected),state=local?buildingActivity(local):{state:'unknown',detail:'Données indisponibles'};
        const info=$('lift-view').querySelector('.lift-activity');
        if(info){info.dataset.activity=state.state;info.textContent='Bâtiment · '+(stateNames[state.state]||state.detail)+' · '+state.detail;}
        const team=currentTeam();
        for(const b of $('lift-view').querySelectorAll('[data-floor]')){
            const marker=b.querySelector('.floor-activity');
            if(!marker)continue;
            if(b.dataset.floor===team?.floor){
                marker.dataset.activity=state.state;
                marker.textContent='Équipe de référence : '+(data?String(local?.agents.length||0)+' agent(s) configuré(s) · '+state.detail:'données indisponibles')+' · activité non localisée';
            }else {marker.dataset.activity='unassigned';marker.textContent='Occupation non mesurée';}
        }
    }
    function clearFlows(){clearTimeout(flowTimer);document.getElementById('live-flows')?.replaceChildren();}
    function renderActivity(){
        for(const b of layout){
            const g=document.querySelector('[data-building="'+b.id+'"]'),badge=g?.querySelector('.activity-label');
            const local=data?.buildings.find(x=>x.id===b.id);
            const s=local?buildingActivity(local):{state:'unknown',detail:'Données indisponibles'};
            if(g){g.dataset.activity=s.state;g.setAttribute('aria-label',labels[b.id]+' · '+(stateNames[s.state]||s.detail)+' · '+s.detail+' · ouvrir l’ascenseur');}
            if(badge)badge.textContent=s.detail;
            const button=document.querySelector('#buildings button[data-id="'+b.id+'"]');
            if(button){button.dataset.activity=s.state;button.title=stateNames[s.state]||s.detail;button.querySelector('small').textContent=s.detail;}
        }
        if(!data){lastDelegation=null;clearFlows();$('collaborations').replaceChildren(node('p','Données indisponibles.','muted'));return;}
        const edges=data.activity.delegations;
        list('collaborations',edges,e=>entry(e.from_agent+' → '+e.to_agent,'Tâche #'+e.id+' · mission #'+e.mission+' · '+mode(e.mode)+' · '+e.state+' · '+e.created),'Aucune délégation inter-agents enregistrée dans cet instantané.');
        const high=edges.reduce((n,e)=>Math.max(n,e.id),0);
        const fresh=lastDelegation===null?[]:edges.filter(e=>e.id>lastDelegation);
        lastDelegation=high;
        clearFlows();
        if(scene!=='campus'||document.hidden||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
        const agentBuilding=new Map(data.buildings.flatMap(b=>b.agents.map(a=>[a.id,b.id])));
        const flows=$('live-flows');if(!flows)return;
        for(const e of fresh.slice(0,5)){
            const from=byId.get(agentBuilding.get(e.from_agent)),to=byId.get(agentBuilding.get(e.to_agent));
            if(!from||!to||from.id===to.id)continue;
            const a=project(from.x,from.y,4),b=project(to.x,to.y,4);
            const path='M '+a.join(' ')+' Q '+((a[0]+b[0])/2)+' '+((a[1]+b[1])/2-35)+' '+b.join(' ');
            const group=svg('g',{'data-delegation':e.id,'aria-hidden':'true',class:e.mode==='demo'?'flow-demo':'flow-cloud'});
            group.append(svg('path',{d:path,class:'flow-path',fill:'none'}));
            const robot=svg('g',{class:'flow-robot'});
            robot.append(svg('rect',{x:-7,y:-6,width:14,height:12,rx:3}),svg('circle',{cx:-2,cy:-1,r:1.2,fill:'#0c1826'}),svg('circle',{cx:2,cy:-1,r:1.2,fill:'#0c1826'}));
            robot.append(svg('animateMotion',{path,dur:'2s',repeatCount:1,fill:'freeze'}));group.append(robot);flows.append(group);
        }
        flowTimer=setTimeout(clearFlows,4500);
    }
    function initMap(){
        const map=svg('svg',{viewBox:'0 0 1000 600',class:'campus-map-svg',role:'group','aria-label':'Campus interactif'});
        map.append(svg('image',{href:'/campus/assets/campus_1_1.webp',x:0,y:0,width:1000,height:600,preserveAspectRatio:'none'}));
        for(const b of [...layout].sort((a,b)=>a.x+a.y-b.x-b.y)){
            const w=b.w*.82,d=b.d*.82,h=b.h*.77,X=b.x-w/2,Y=b.y-d/2,top=b.type==='core'?51:h+(b.type==='hq'?28:8);
            const g=svg('g',{class:'live-map-node',tabindex:0,role:'button','aria-label':labels[b.id]+' · ouvrir l’ascenseur','data-building':b.id,style:'--accent:'+b.color});
            const a=X-9,c=X+w+9,e=Y-9,f=Y+d+9;
            for(const pts of [[[a,f,5],[c,f,5],[c,f,top],[a,f,top]],[[c,e,5],[c,f,5],[c,f,top],[c,e,top]],[[a,e,top],[c,e,top],[c,f,top],[a,f,top]],[[a,e,6],[c,e,6],[c,f,6],[a,f,6]]])g.append(polygon(pts,{class:'live-hit'}));
            const [x,y]=project(b.x,b.y,top+8);const t=svg('text',{x,y,class:'map-label'});t.textContent=b.id==='CORE'?'DATA CORE':b.id;g.append(t);
            const badge=svg('text',{x,y:y+14,class:'activity-label'});badge.textContent='Données indisponibles';g.append(badge);g.dataset.activity='unknown';
            g.addEventListener('click',()=>openLift(b.id));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openLift(b.id);}});map.append(g);
        }
        map.append(svg('g',{id:'live-flows','pointer-events':'none','aria-hidden':'true'}));
        $('campus-map').replaceChildren(map);
        $('buildings').replaceChildren(...layout.map(b=>{const btn=node('button',labels[b.id]);btn.type='button';btn.dataset.id=b.id;btn.dataset.activity='unknown';btn.append(node('small','Données indisponibles'));btn.addEventListener('click',()=>openLift(b.id));return btn;}));
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
            if(page==='home'||page==='missions'||(st.id.startsWith('OWNER:station:')&&page==='decisions')||(selected==='HERMES'&&page==='business'&&['HERMES','SHOWROOM','ADS183','PUBLISH183','ANALYTICS183'].includes(floorId))){const cmd=node('button','Commandes · '+modules.pages[page]);cmd.type='button';cmd.dataset.commands=page;cmd.addEventListener('click',()=>window.AESCampusCommands.open(page));links.append(cmd);}
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
    function openLift(id){if(!byId.has(id))return;clearFlows();selected=id;scene='lift';floorId=null;stationId=null;renderScene();renderBuilding();$('lift-view').querySelector('button')?.focus();}
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
        renderTeam();
        if(scene==='campus'){$('scene-title').textContent='Campus · 7 bâtiments';$('scene-note').textContent='Sélectionne un bâtiment sur le campus ou dans la liste.';return;}
        if(scene==='lift'){
            $('scene-title').textContent='Ascenseur · '+labels[b.id];$('scene-note').textContent='Services du design · leur présence ne signifie pas qu’ils sont opérationnels.';
            const wrap=node('div',undefined,'lift-layout'),list=node('div',undefined,'floor-list');wrap.append(tower(b),list);
            for(const f of [...b.floors].reverse()){const btn=node('button');btn.type='button';btn.dataset.floor=f.id;btn.append(node('b',levelLabel(f.level)+' · '+f.name),node('small',f.description),node('small',f.stations.some(hasModule)?'Accès métier partiel · occupation inconnue':'Service graphique · aucun accès métier associé'),node('small','','floor-activity'));btn.addEventListener('click',()=>openFloor(f.id));list.append(btn);}
            $('lift-view').replaceChildren(node('p','','lift-activity'),wrap);renderLiftStatus();return;
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
        renderTeam();renderLiftStatus();
        if(!data){$('detail-title').textContent=labels[selected]+' · données indisponibles';$('agents').replaceChildren();$('tasks').replaceChildren();renderStation();return;}
        const b=data.buildings.find(x=>x.id===selected);if(!b)return;
        $('detail-title').textContent=labels[b.id]+' · agents du moteur';
        document.querySelectorAll('#buildings button').forEach(btn=>btn.setAttribute('aria-pressed',String(btn.dataset.id===selected)));
        const ids=new Set(b.agents.map(a=>a.id));
        list('agents',b.agents,a=>{const activity=a.activity||[];return entry(a.id+' · '+a.role,activity.length?activity.map(r=>modeShort(r.mode)+' · '+(stateNames[r.state]||r.state)+' : '+r.count).join(' / '):'Aucune tâche dynamique non résolue observée');});
        list('tasks',data.tasks.filter(t=>ids.has(t.agent)),t=>entry('#'+t.id+' · '+t.agent,t.state+' · mission #'+t.mission+' · '+mode(t.mode)));
        if(data.unmapped_agents.length)$('agents').append(node('p','Agents non affectés au campus : '+data.unmapped_agents.map(a=>a.id).join(', '),'muted'));
        renderStation();
    }
    function render(){
        const agents=data.buildings.reduce((n,b)=>n+b.agents.length,0)+data.unmapped_agents.length;
        const count=m=>data.mission_counts.filter(x=>x.mode===m).reduce((n,x)=>n+x.count,0);
        $('metrics').replaceChildren(metric('Agents configurés',agents),metric('Missions CLOUD enregistrées',count('cloud')),metric('Missions SIMULATION enregistrées',count('demo')),metric('Engagement API local estimé (USD)',money(data.budget.committed_estimate_micro_usd)),metric('Plafond API local (USD)',money(data.budget.limit_micro_usd)),metric('Demandes en attente (tous modes)',data.pending_requests));
        renderAlerts();renderActivity();renderBuilding();
        list('missions',data.missions,m=>entry('#'+m.id+' · '+m.title,m.state+' · '+mode(m.mode)+' · '+m.created));
        list('events',data.events,e=>entry(e.agent+' · '+e.action,'Mission #'+e.mission+' · '+mode(e.mode)+' · '+e.created+' · '+(e.ok===1?'OK':e.ok===0?'Échec':'Résultat inconnu')));
        list('artifacts',data.artifacts,a=>entry(a.name+' · V'+a.version,a.agent+' · mission #'+a.mission+' · '+mode(a.mode)));
    }
    function clear(){window.AESCampusCommands.setOnline(false);window.AESNativeTools.reset();data=null;renderAlerts();renderActivity();for(const id of ['metrics','agents','tasks','missions','events','artifacts'])$(id).replaceChildren();renderBuilding();}
    async function refresh(){
        if(busy)return;busy=true;$('refresh').disabled=true;
        const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),8000);
        try{
            const r=await fetch('/campus/live-data',{method:'GET',headers:{'X-Campus-Session':token},cache:'no-store',credentials:'same-origin',signal:controller.signal});
            if(!r.ok)throw Error('HTTP '+r.status);
            const next=await r.json();
            if(next.schema!=='aes.campus.read.v1'||next.source!=='local_sqlite'||next.read_only!==true||next.activity?.schema_version!==1||!Array.isArray(next.activity.delegations)||!Array.isArray(next.attention_missions))throw Error('Source incompatible');
            data=next;window.AESCampusCommands.setOnline(true);render();$('status').className='';$('status').textContent='Connecté · instantané local '+new Date(data.generated_at).toLocaleString('fr-FR');
        }catch(e){clear();$('status').className='error';$('status').textContent='Données indisponibles · aucune valeur de remplacement affichée.';}
        finally{clearTimeout(timer);busy=false;$('refresh').disabled=false;}
    }
    restoreLocation();initMap();renderScene();renderAlerts();renderActivity();renderBuilding();$('campus-back').addEventListener('click',openCampus);$('lift-back').addEventListener('click',()=>openLift(selected));
    document.addEventListener('campus-command-completed',refresh);
    $('refresh').addEventListener('click',refresh);document.addEventListener('visibilitychange',()=>{if(document.hidden){clearFlows();lastDelegation=null;}else refresh();});setInterval(()=>{if(!document.hidden)refresh();},15000);refresh();
})();
