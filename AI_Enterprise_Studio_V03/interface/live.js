(() => {
    'use strict';
    const $=id=>document.getElementById(id);
    const token=document.querySelector('meta[name="campus-session"]').content;
    const preview=document.querySelector('meta[name="campus-mode"]').content==='preview';
    if(preview){$('preview-notice').hidden=false;$('legacy-entry').hidden=true;$('operational-footer').textContent='Aperçu en lecture seule · toutes les commandes sont désactivées. Les listes sont limitées aux entrées les plus récentes.';}
    const fidelity=document.querySelector('meta[name="campus-original"]')?.content==='true';
    let topTool=null,officeMode=true;
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
    const art=window.AESLiveArt;
    let day=true,motion=!matchMedia('(prefers-reduced-motion: reduce)').matches,lastFloor=null;
    const roomProjection=(x,y,z=0)=>[500+(x-y)*1.06,160+(x+y)*.51-z];
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
            if(href&&(!preview||href.startsWith('/campus/'))){const a=node('a',label);a.href=href;e.append(a);}out.append(e);
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
                const robot=svg('g',{class:'desk-avatar',transform:'translate(44 43)'});robot.append(window.AESLiveArt.robot(byId.get(selected).color,.8));art.append(robot);
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
        if(fidelity)renderOriginalOffice(team);
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
    function renderOriginalOffice(team){
        const host=$('original-office');if(!host)return;
        const ids=team.slots.filter(s=>teamAgent(s)).map(s=>s.kind==='director'?'director':Number(s.id.split(':').at(-1))).filter(k=>k==='director'||Number.isInteger(k));
        const signature=selected+':'+ids.join(',')+':'+Boolean(data);
        if(host.dataset.signature!==signature){
            host.dataset.signature=signature;
            const graphic=window.AESOriginalOffice.draw(selected,ids,Boolean(data));
            for(const g of graphic.querySelectorAll('[data-seat16]')){
                const key=g.dataset.seat16,slot=team.slots.find(s=>s.id===selected+':'+key);
                if(!slot)continue;
                g.dataset.slot=slot.id;
                const select=()=>{selectedSlot=slot.id;renderTeam();};
                const label=graphic.querySelector('[data-label-seat1631="'+key+'"]');
                const lit=on=>label?.classList.toggle('linkedHover1631',on);
                g.addEventListener('click',select);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select();}});
                g.addEventListener('pointerenter',()=>lit(true));g.addEventListener('pointerleave',()=>lit(false));g.addEventListener('focus',()=>lit(true));g.addEventListener('blur',()=>lit(false));
            }
            host.replaceChildren(graphic);
        }
        for(const g of host.querySelectorAll('[data-slot]')){
            const slot=team.slots.find(s=>s.id===g.dataset.slot),a=teamAgent(slot);
            g.setAttribute('aria-pressed',String(selectedSlot===slot.id));
            g.dataset.activity=slot.agent?agentStatus(a).state:'unassigned';
            g.setAttribute('aria-label',slot.name+' · '+(a?a.id+' · '+agentStatus(a).detail:!data?'Données indisponibles':'Non attribué'));
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
            const g=document.querySelector('[data-building="'+b.id+'"]'),sign=fidelity?document.querySelector('#original-signs [data-id="'+b.id+'"]'):null,badge=(sign||g)?.querySelector('.activity-label');
            const local=data?.buildings.find(x=>x.id===b.id);
            const s=local?buildingActivity(local):{state:'unknown',detail:'Données indisponibles'};
            if(g){g.dataset.activity=s.state;g.setAttribute('aria-label',labels[b.id]+' · '+(stateNames[s.state]||s.detail)+' · '+s.detail+' · ouvrir l’ascenseur');}
            if(sign)sign.dataset.activity=s.state;
            if(badge)badge.textContent=fidelity?(b.id==='CORE'?'DATA CORE':b.id)+' · '+b.floors.length+' niv. · '+(local?local.agents.length+' agent(s)':'—'):s.detail;
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
        if(scene!=='campus'||document.hidden||!motion||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
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
            robot.append(art.robot(to.color,.55));
            robot.append(svg('animateMotion',{path,dur:'2s',repeatCount:1,fill:'freeze'}));group.append(robot);flows.append(group);
        }
        flowTimer=setTimeout(clearFlows,4500);
    }
    function initMap(){
        const map=svg('svg',{viewBox:'0 0 1000 600',class:'campus-map-svg',role:'group','aria-label':'Campus interactif'});
        const signs=svg('g',{id:'original-signs','aria-hidden':'true'});
        map.append(svg('image',{id:'campus-decor',href:'/campus/assets/campus_1_1.webp',class:'live-hd-art',x:0,y:0,width:1000,height:600,preserveAspectRatio:'none'}));
        for(const b of [...layout].sort((a,b)=>a.x+a.y-b.x-b.y)){
            const w=b.w*.82,d=b.d*.82,h=b.h*.77,X=b.x-w/2,Y=b.y-d/2,top=b.type==='core'?51:h+(b.type==='hq'?28:8);
            const g=svg('g',{class:'live-map-node',tabindex:0,role:'button','aria-label':labels[b.id]+' · ouvrir l’ascenseur','data-building':b.id,style:'--accent:'+b.color});
            const a=X-9,c=X+w+9,e=Y-9,f=Y+d+9;
            for(const pts of [[[a,f,5],[c,f,5],[c,f,top],[a,f,top]],[[c,e,5],[c,f,5],[c,f,top],[c,e,top]],[[a,e,top],[c,e,top],[c,f,top],[a,f,top]],[[a,e,6],[c,e,6],[c,f,6],[a,f,6]]])g.append(polygon(pts,{class:'live-hit'}));
            const [px,py]=project(b.x,b.y,0);g.append(svg('ellipse',{class:'building-halo',cx:px,cy:py+3,rx:(w+d)*.48,ry:(w+d)*.23,fill:'none',stroke:b.color,'pointer-events':'none'}));
            const labelHeight=h;
            const y=Math.max(4,py-(b.type==='hq'?labelHeight+71:b.type==='core'?84:labelHeight+54)-12),x=px;
            const label=svg('g',fidelity?{class:'live-domain-label map-node domain15','data-id':b.id,style:'--accent:'+b.color,'aria-hidden':'true'}:{class:'live-domain-label','pointer-events':'none'});
            label.append(svg('path',{d:'M'+x+' '+(y+44)+'v12',stroke:b.color,'stroke-dasharray':'2 3',opacity:.8}),svg('rect',{class:fidelity?'live-label-bg tag label-bg':'live-label-bg',x:x-82,y,width:164,height:44,rx:5,stroke:b.color}),svg('rect',{x:x-78,y:y+5,width:2,height:34,fill:b.color}));
            const t=svg('text',{x,y:y+(fidelity?12:13),class:'map-label'});t.textContent=fidelity?window.AESOriginalOffice.departments[b.id].lines[0]:b.id==='CORE'?'DATA CORE':b.id;label.append(t);
            const sub=svg('text',{x,y:y+(fidelity?24:26),class:'map-subtitle'});sub.textContent=fidelity?window.AESOriginalOffice.departments[b.id].lines[1]:labels[b.id].toUpperCase()+' · '+b.floors.length+' NIV.';label.append(sub);
            const badge=svg('text',{x,y:y+(fidelity?37:38),class:'activity-label'});badge.textContent='Données indisponibles';label.append(badge);if(fidelity){signs.append(label);label.addEventListener('click',()=>openLift(b.id));const light=on=>label.classList.toggle('lit181',on);for(const el of [g,label]){el.addEventListener('pointerenter',()=>light(true));el.addEventListener('pointerleave',()=>light(false));}g.addEventListener('focus',()=>light(true));g.addEventListener('blur',()=>light(false));const [tx,ty]=project(b.x,Y+d+1,22);if(b.type!=='core'){const roof=svg('text',{x:tx,y:ty,transform:'rotate(25 '+tx+' '+ty+')',class:'hd-sign','text-anchor':'middle'});roof.textContent=b.id;g.append(roof);}}else g.append(label);g.dataset.activity='unknown';
            g.addEventListener('click',()=>openLift(b.id));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();openLift(b.id);}});map.append(g);
        }
        map.append(svg('g',{id:'live-flows','pointer-events':'none','aria-hidden':'true'}));
        if(fidelity)map.append(signs);
        $('campus-map').replaceChildren(map);
        $('buildings').replaceChildren(...layout.map(b=>{const btn=node('button',labels[b.id]);btn.type='button';btn.dataset.id=b.id;btn.dataset.activity='unknown';if(fidelity){btn.className='agent';btn.style.setProperty('--c',b.color);btn.replaceChildren();const avatar=node('span',undefined,'avatar'),av=svg('svg',{viewBox:'-20 -40 40 45','aria-hidden':'true'});av.append(art.robot(b.color,.8));avatar.append(av);const desc=node('span');desc.append(node('span',window.AESOriginalOffice.departments[b.id].title,'name'),node('small','Données indisponibles'));btn.append(avatar,desc);}else btn.append(node('small','Données indisponibles'));btn.addEventListener('click',()=>openLift(b.id));return btn;}));
    }
    const modules=window.AESLiveModules;
    const hasModule=st=>Object.hasOwn(modules.stations,st.id)&&modules.stations[st.id].length>0;
    function updateModuleLinks(st){
        const out=$('station-modules');const sig=st?.id||'';
        window.AESNativeTools.setStation(sig||null);
        window.AESCampusCommands.setStation(sig||null);
        if(out.dataset.station===sig)return;out.dataset.station=sig;out.replaceChildren();
        if(!st||!hasModule(st))return;
        out.append(node('h3','Accès aux modules existants'),node('p',preview?'Aperçu : consultation native seulement, les liens historiques et commandes sont désactivés.':'Ouvre l’interface historique (module complet, sans filtre automatique). Ses confirmations et permissions restent applicables.','muted'));
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
            if(!preview&&(page==='home'||page==='missions'||(st.id.startsWith('OWNER:station:')&&page==='decisions')||(selected==='HERMES'&&page==='business'&&['HERMES','SHOWROOM','ADS183','PUBLISH183','ANALYTICS183'].includes(floorId)))){const cmd=node('button','Commandes · '+modules.pages[page]);cmd.type='button';cmd.dataset.commands=page;cmd.addEventListener('click',()=>window.AESCampusCommands.open(page));links.append(cmd);}
            if(!preview)links.append(a);
        }out.append(links);
    }
    function restoreLocation(){
        const q=new URLSearchParams(location.search),b=byId.get(q.get('building'));
        if(!b)return;selected=b.id;scene='lift';
        const f=b.floors.find(x=>x.id===q.get('floor'));if(!f)return;
        scene='room';floorId=f.id;lastFloor=f.id;
        const st=f.stations.find(x=>x.id===q.get('station'));stationId=st?.id||null;
    }
    function currentFloor(){return byId.get(selected)?.floors.find(f=>f.id===floorId);}
    function openLift(id){if(!byId.has(id))return;topTool=null;if(fidelity)document.querySelectorAll('.top [data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view==='campus'));officeMode=true;clearFlows();if(id!==selected)lastFloor=null;else if(scene==='room')lastFloor=floorId;selected=id;scene='lift';floorId=null;stationId=null;renderScene();renderBuilding();sceneTransition();$('lift-view').querySelector('button')?.focus();}
    function openFloor(id){const f=byId.get(selected)?.floors.find(f=>f.id===id);if(!f)return;topTool=null;officeMode=true;if(!preview&&id==='OWNER'&&!document.querySelector('meta[name="campus-owner-session"]').content){location.assign('/campus/live/?building=ATLAS&floor=OWNER');return;}scene='room';floorId=id;lastFloor=id;stationId=null;renderScene();renderBuilding();sceneTransition();$('lift-back').focus();}
    function openCampus(){topTool=null;if(fidelity)document.querySelectorAll('.top [data-view]').forEach(b=>b.classList.toggle('active',b.dataset.view==='campus'));scene='campus';floorId=null;stationId=null;renderScene();renderBuilding();sceneTransition();document.querySelector('[data-building="'+selected+'"]')?.focus();}
    function tower(b){return art.tower(b,lastFloor);}
    function highlightFloor(id){
        for(const g of $('lift-view').querySelectorAll('[data-level-id]'))g.classList.toggle('focus181',g.dataset.levelId===id);
        const preview=$('lift-view').querySelector('.lift-preview'),f=byId.get(selected)?.floors.find(f=>f.id===id);
        if(preview)preview.textContent=f?levelLabel(f.level)+' · '+f.name:'Sélectionne un niveau';
    }
    function activateStation(id){
        if(!currentFloor()?.stations.some(s=>s.id===id))return;
        topTool=null;stationId=id;
        for(const e of $('room-view').querySelectorAll('[data-station],[data-room-station]')){
            const on=(e.dataset.station||e.dataset.roomStation)===id;e.setAttribute('aria-pressed',String(on));
        }
        renderStation();
    }
    function vectorRoomGraphic(b,f){
        const frame=node('div',undefined,'original-vector-room');
        frame.style.setProperty('--room',b.color);
        const graphic=window.AESOriginalRooms.draw(b,f);
        for(const g of graphic.querySelectorAll('[data-station]')){
            const index=Number(g.dataset.station),st=f.stations[index];
            g.removeAttribute('data-station');if(!st)continue;
            g.dataset.roomStation=st.id;g.setAttribute('aria-pressed',String(stationId===st.id));
            const label=graphic.querySelector('[data-label-station1631="'+index+'"]');
            const lit=on=>label?.classList.toggle('linkedHover1631',on);
            g.addEventListener('pointerenter',()=>lit(true));g.addEventListener('pointerleave',()=>lit(false));g.addEventListener('focus',()=>lit(true));g.addEventListener('blur',()=>lit(false));
            g.addEventListener('click',()=>activateStation(st.id));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activateStation(st.id);}});
        }
        frame.append(graphic);return frame;
    }
    function roomGraphic(b,f){
        const frame=node('div',undefined,'room-art-frame'),im=node('img',undefined,'room-image');
        im.src='/campus/assets/'+f.asset;im.alt='Décor original : '+f.name;frame.append(im);
        const overlay=svg('svg',{class:'room-overlay',viewBox:'0 0 1000 565',role:'group','aria-label':'Postes interactifs du service',style:'--room:'+b.color});
        const pos=[[175,175],[225,45],[85,115],[285,153],[153,290]],order=[1,2,0,3,4],labels=[];
        for(const i of order){
            const st=f.stations[i];if(!st)continue;
            const [x,y]=pos[i],wide=['wall','screens','desk','console'].includes(st.kind),w=wide?110:96,d=wide?54:86,h=st.kind==='wall'?75:st.kind==='rack'?69:62;
            const a=x-w/2,c=x+w/2,e=y-d/2,v=y+d/2,g=svg('g',{class:'live-room-station','data-room-station':st.id,role:'button',tabindex:0,'aria-label':st.name,'aria-pressed':String(stationId===st.id)});
            const title=svg('title');title.textContent=st.description;g.append(title);
            for(const pts of [[[a,v,0],[c,v,0],[c,v,h],[a,v,h]],[[c,e,0],[c,v,0],[c,v,h],[c,e,h]],[[a,e,h],[c,e,h],[c,v,h],[a,v,h]],[[a,e,0],[c,e,0],[c,v,0],[a,v,0]]])g.append(svg('polygon',{class:'room-hit',points:pts.map(p=>roomProjection(...p).join(',')).join(' ')}));
            const [px,py]=roomProjection(x,y),ly=py+24,lw=Math.max(112,st.name.length*6.2+35),label=svg('g',{class:'live-room-label','data-room-label':st.id,'aria-hidden':'true'});
            label.append(svg('rect',{x:px-lw/2,y:ly,width:lw,height:25,rx:6}),svg('circle',{cx:px-lw/2+13,cy:ly+12.5,r:8,fill:b.color}));
            const n=svg('text',{x:px-lw/2+13,y:ly+16,'text-anchor':'middle','font-size':10,fill:'#07131f','font-weight':800});n.textContent=i+1;
            const txt=svg('text',{x:px+8,y:ly+16,'text-anchor':'middle','font-size':10.5,fill:'#e9f6ff','font-weight':650});txt.textContent=st.name;label.append(n,txt);labels.push(label);
            const lit=on=>label.classList.toggle('lit',on);
            g.addEventListener('pointerenter',()=>lit(true));g.addEventListener('pointerleave',()=>lit(false));g.addEventListener('focus',()=>lit(true));g.addEventListener('blur',()=>lit(false));
            g.addEventListener('click',()=>activateStation(st.id));g.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();activateStation(st.id);}});overlay.append(g);
        }
        overlay.append(...labels);frame.append(overlay);return frame;
    }
    function sceneTransition(){
        if(!motion||matchMedia('(prefers-reduced-motion: reduce)').matches)return;
        const e=scene==='campus'?$('campus-map'):scene==='lift'?$('lift-view'):$('room-view');
        if(fidelity){const door=$('doorTransition');door.getAnimations().forEach(a=>a.cancel());door.animate([{opacity:1},{opacity:0}],{duration:180,easing:'ease-out'});}
        else e.animate([{opacity:.55,transform:'translateY(3px)'},{opacity:1,transform:'translateY(0)'}],{duration:200,easing:'ease-out'});
    }
    function renderScene(){
        const b=byId.get(selected),f=currentFloor();
        $('campus-map').hidden=scene!=='campus';$('lift-view').hidden=scene!=='lift';$('room-view').hidden=scene!=='room';
        $('campus-back').hidden=scene==='campus';$('lift-back').hidden=scene!=='room';
        if(fidelity){$('roomScene').hidden=scene!=='room';$('campusPanel').classList.toggle('room-open',scene==='room');$('campusPanel').classList.toggle('lift-open181',scene==='lift');}
        document.querySelectorAll('#buildings button').forEach(btn=>btn.setAttribute('aria-pressed',String(btn.dataset.id===selected)));
        if(fidelity){for(const g of $('campus-map').querySelectorAll('[data-building]'))g.setAttribute('aria-pressed',String(g.dataset.building===selected));for(const g of $('campus-map').querySelectorAll('#original-signs [data-id]'))g.classList.toggle('selected',g.dataset.id===selected);}
        renderTeam();
        if(scene==='campus'){$('scene-title').textContent='Campus · 7 bâtiments';$('scene-note').textContent='Sélectionne un bâtiment sur le campus ou dans la liste.';return;}
        if(scene==='lift'){
            $('scene-title').textContent='Ascenseur · '+labels[b.id];$('scene-note').textContent='Services du design · leur présence ne signifie pas qu’ils sont opérationnels.';
            const wrap=node('div',undefined,fidelity?'lift-layout liftLayout181':'lift-layout'),list=node('div',undefined,fidelity?'floor-list liftList181':'floor-list'),towerBox=node('div',undefined,fidelity?'lift-tower-box liftTower181':'lift-tower-box');towerBox.append(tower(b),node('p','','lift-preview'));wrap.append(towerBox,list);$('lift-view').style.setProperty('--lift',b.color);
            for(const f of [...b.floors].reverse()){const btn=node('button');btn.type='button';btn.dataset.floor=f.id;if(fidelity)btn.className='floor181';const body=node('span');body.append(node('b',f.name),node('small',f.description),node('small',f.stations.some(hasModule)?'Accès métier partiel · occupation inconnue':'Service graphique · aucun accès métier associé'),node('small','','floor-activity'));btn.append(node('span',levelLabel(f.level),fidelity?'floor-number num181':'floor-number'),body,node('span','›',fidelity?'floor-arrow arrow181':'floor-arrow'));if(lastFloor===f.id)btn.setAttribute('aria-current','true');btn.addEventListener('pointerenter',()=>highlightFloor(f.id));btn.addEventListener('pointerleave',()=>highlightFloor(lastFloor));btn.addEventListener('focus',()=>highlightFloor(f.id));btn.addEventListener('blur',()=>highlightFloor(lastFloor));btn.addEventListener('click',()=>openFloor(f.id));list.append(btn);}
            if(fidelity){const hero=node('div',undefined,'liftHero181'),heading=node('div'),count=node('div',undefined,'liftCount181');heading.append(node('small','ACCÈS VERTICAL / '+b.id),node('h3',window.AESOriginalOffice.departments[b.id].title),node('p','Ascenseur interactif · services de référence'));count.append(node('strong',String(b.floors.length)),node('span','niveaux accessibles'));hero.append(heading,count);$('lift-view').replaceChildren(hero,node('p','','lift-activity'),wrap);}else $('lift-view').replaceChildren(node('p','','lift-activity'),wrap);renderLiftStatus();highlightFloor(lastFloor);return;
        }
        $('scene-title').textContent=levelLabel(f.level)+' · '+f.name;$('scene-note').textContent='Décor du service · les données de droite sont celles du bâtiment, pas une mesure de l’occupation du service.';
        const room=$('room-view');room.replaceChildren();
        if(fidelity&&f.id===currentTeam()?.floor){const controls=node('div',undefined,'office-switch');const toggle=node('button',officeMode?'◈ Décor historique':'▦ Bureaux modulaires','secondary');toggle.type='button';toggle.addEventListener('click',()=>{officeMode=!officeMode;renderScene();renderBuilding();});controls.append(node('small','Disposition originale · rattachement graphique, pas présence physique.'),toggle);room.append(controls);if(officeMode){const host=node('div');host.id='original-office';room.append(host);renderOriginalOffice(currentTeam());}else if(f.asset)room.append(roomGraphic(b,f));}
        else if(f.asset){room.append(roomGraphic(b,f));}
        else if(fidelity)room.append(vectorRoomGraphic(b,f));
        else room.append(node('div','Décor HD dédié non disponible dans la maquette originale. Les postes sont accessibles ci-dessous.','room-missing'));
        const buttons=node('div',undefined,'station-list');
        for(const st of f.stations){const btn=node('button');btn.type='button';btn.dataset.station=st.id;btn.setAttribute('aria-pressed',String(stationId===st.id));btn.append(node('b',st.name),node('small',st.description));if(hasModule(st))btn.append(node('small','Module existant ↗','module-marker'));btn.addEventListener('click',()=>activateStation(st.id));buttons.append(btn);}room.append(buttons);
    }
    function renderStation(){
        const st=currentFloor()?.stations.find(s=>s.id===stationId),panel=$('station-detail'),out=$('station-content');
        if(fidelity&&topTool){panel.hidden=false;return;}
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
        if(fidelity){$('metrics').replaceChildren(metric('Agents configurés',agents),metric('Missions CLOUD enregistrées',count('cloud')),metric('Missions SIMULATION enregistrées',count('demo')),metric('Engagement API local estimé',money(data.budget.committed_estimate_micro_usd)),metric('Demandes en attente',data.pending_requests));}else $('metrics').replaceChildren(metric('Agents configurés',agents),metric('Missions CLOUD enregistrées',count('cloud')),metric('Missions SIMULATION enregistrées',count('demo')),metric('Engagement API local estimé (USD)',money(data.budget.committed_estimate_micro_usd)),metric('Plafond API local (USD)',money(data.budget.limit_micro_usd)),metric('Demandes en attente (tous modes)',data.pending_requests));
        renderAlerts();renderActivity();renderBuilding();
        list('missions',data.missions,m=>entry('#'+m.id+' · '+m.title,m.state+' · '+mode(m.mode)+' · '+m.created));
        list('events',data.events,e=>entry(e.agent+' · '+e.action,'Mission #'+e.mission+' · '+mode(e.mode)+' · '+e.created+' · '+(e.ok===1?'OK':e.ok===0?'Échec':'Résultat inconnu')));
        list('artifacts',data.artifacts,a=>entry(a.name+' · V'+a.version,a.agent+' · mission #'+a.mission+' · '+mode(a.mode)));
    }
    function clear(){topTool=null;window.AESCampusCommands.setOnline(false);window.AESNativeTools.reset();data=null;renderAlerts();renderActivity();for(const id of ['metrics','agents','tasks','missions','events','artifacts'])$(id).replaceChildren();renderBuilding();}
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
    $('day-toggle').addEventListener('click',()=>{day=!day;if(fidelity)$('campusPanel').classList.toggle('day',day);$('campus-decor').setAttribute('href','/campus/assets/campus_1_'+(day?1:0)+'.webp');$('day-toggle').textContent=day?'☀ Jour':'☾ Nuit';$('day-toggle').setAttribute('aria-pressed',String(day));});
    $('motion-toggle').setAttribute('aria-pressed',String(motion));$('motion-toggle').textContent=motion?'Animations : oui':'Animations : non';
    $('motion-toggle').addEventListener('click',()=>{motion=!motion;if(!motion)clearFlows();$('motion-toggle').textContent=motion?'Animations : oui':'Animations : non';$('motion-toggle').setAttribute('aria-pressed',String(motion));});
    $('focus-toggle').addEventListener('click',()=>{const expanded=fidelity?$('campusView').classList.toggle('immersive'):$('scene-layout').classList.toggle('scene-expanded');$('focus-toggle').setAttribute('aria-pressed',String(expanded));$('focus-toggle').textContent=expanded?'↙ Vue normale':'⛶ Agrandir le campus';});
    if(fidelity){
        const tools={classic:'agents',campaigns:'home',finance:'finance',memory:'memory',connectors:'tools'};
        document.querySelectorAll('.top [data-view]').forEach(btn=>btn.addEventListener('click',()=>{
            if(btn.dataset.view==='campus'){openCampus();return;}
            if(!data)return;
            const tool=tools[btn.dataset.view];if(!tool)return;
            topTool=tool;
            document.querySelectorAll('.top [data-view]').forEach(b=>b.classList.toggle('active',b===btn));
            $('station-detail').hidden=false;$('station-title').textContent=window.AESNativeTools.names[tool];$('station-content').replaceChildren();$('station-modules').replaceChildren();$('station-modules').dataset.station='';window.AESNativeTools.setStation('nav:'+tool);window.AESNativeTools.open(tool);
        }));
    }
    document.addEventListener('campus-command-completed',refresh);
    $('refresh').addEventListener('click',refresh);document.addEventListener('visibilitychange',()=>{if(document.hidden){clearFlows();lastDelegation=null;}else refresh();});setInterval(()=>{if(!document.hidden)refresh();},15000);refresh();
})();
