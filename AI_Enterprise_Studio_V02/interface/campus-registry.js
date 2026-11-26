/* D02 — read-only topology adapter. No enterprise state, credentials or transport. */
(() => {
    'use strict';
    // Candidate legacy pages, not permissions or implemented connections.
    const candidates = Object.freeze({
        LOBBY:['home'], ATLAS:['goals','missions','decisions'], MEETING:['missions','work'],
        SUPERVISION:['home','work','missions'], NOTIFICATIONS:['decisions','work'],
        PEOPLE17:['agents'], GROUP:['portfolio'], EXPAND:['portfolio','agents'],
        OWNER:['home','goals','decisions','finance'], ORION:['opps','memory'],
        WORLD:['opps'], OPPORTUNITIES:['opps'], NEXUS:['files','work'],
        FACTORY:['files','missions'], LAB:['laboratory'], PORTFOLIO:['portfolio','files'],
        FULFILL17:[], MIDAS:['finance'], ECON:['opps','finance'],
        INVESTMENTS:['finance','portfolio'], BUY17:[], HERMES:['business'],
        SHOWROOM:['business','portfolio'], SUPPORT17:[], COMMS:['business','work'],
        ADS183:['business'], VIDEO183:[], PUBLISH183:[], ANALYTICS183:['business'],
        SENTINEL:['decisions','work'], INCIDENTS:['work','tools'], LEGAL17:[],
        INFRA:['tools'], CORE:['memory'], ITOPS17:[], ACADEMY:['goals','agents'],
        ARCHIVES:['memory','files']
    });
    const freeze = value => {
        if (value && typeof value === 'object' && !Object.isFrozen(value)) {
            Object.values(value).forEach(freeze);
            Object.freeze(value);
        }
        return value;
    };
    const originalIds = Object.values(floors181).flat().slice();
    const serviceSet = new Set(originalIds);
    const roomFor = id => rooms[id] || annex09[id];
    // The existing layout remains authoritative, including session-only reserve floors.
    function snapshot() {
        const buildings = Object.entries(floors181).map(([id, levels]) => ({
            id, name:org15[id].title,
            floors:levels.map((key, level) => {
                const reserve = reserve221(key);
                const room = reserve ? null : roomFor(key);
                const pages = reserve ? [] : [...(candidates[key] || [])];
                return {
                    id:key, buildingId:id, level, name:name181(key), description:desc181(key),
                    kind:reserve ? 'reserve' : 'service',
                    simulationState:floorState221(key),
                    integration:reserve ? 'unassigned' : pages.length ? 'candidate' : 'future_or_unmapped',
                    legacyPages:pages, operational:false,
                    stations:(room?.stations || []).map((st,index) => ({
                        id:key+':station:'+index, index, name:st[0], kind:st[1],
                        description:st[2], demoDestination:st[3], operational:false
                    }))
                };
            }),
            // These are graphical slots, not identities in the agent engine.
            slots:[
                {id:id+':director',kind:'director',name:org15[id].title},
                ...org15[id].roles.map((name,index)=>({id:id+':'+index,kind:'specialist',name})),
                {id:id+':auto',kind:'automation',name:org15[id].auto}
            ].map(slot=>({...slot,operational:false}))
        }));
        return freeze({schemaVersion:1,design:'22.6',phase:'D02',mode:'simulation',
            operational:false,buildings});
    }
    function service(id) {
        if (!serviceSet.has(id)) return null;
        for (const building of snapshot().buildings) {
            const found = building.floors.find(f=>f.id===id);
            if (found) return found;
        }
        return null;
    }
    function station(id,index) {
        if (!Number.isInteger(index) || index<0) return null;
        return service(id)?.stations[index] || null;
    }
    if (originalIds.length!==37 || serviceSet.size!==37 ||
        Object.keys(candidates).length!==37 ||
        originalIds.some(id=>!Object.hasOwn(candidates,id)||!roomFor(id)?.stations?.length)) {
        throw new Error('D02: inconsistent design topology');
    }
    const registry = Object.freeze({snapshot,service,station});
    Object.defineProperty(window,'AESCampusRegistry',{value:registry,writable:false,configurable:false});
    const originalGo = goFloor181;
    goFloor181 = function(id) {
        const target = registry.service(id);
        if (!target || (liftBuilding181 && target.buildingId!==liftBuilding181)) return;
        return originalGo(id);
    };
    const originalShow = showLift181;
    showLift181 = function(id,from=null) {
        if (!Object.hasOwn(floors181,id)) return;
        const origin = registry.service(from);
        return originalShow(id,origin?.buildingId===id?from:null);
    };
})();
