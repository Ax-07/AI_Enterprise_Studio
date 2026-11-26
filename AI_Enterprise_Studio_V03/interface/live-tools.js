/* D04.2/D04.3: on-demand native read tools. No POST and no HTML rendering of stored content. */
(() => {
    'use strict';
    const names=Object.freeze({missions:'Missions',work:'Tâches',files:'Livrables',memory:'Mémoire collective',finance:'Dépenses API',opps:'Opportunités',home:'Autopilote & campagnes',portfolio:'Portefeuille d’activités',laboratory:'Laboratoire',tools:'Connecteurs & outils',agents:'Organisation des agents',goals:'Objectifs & XP',decisions:'Décisions réservées',owner:'Tableau de direction',business:'Activité commerciale',marketing:'Dossiers HERMES & marketing',incidents:'Incidents & reprises',quality:'Preuves qualité des livrables',infrastructure:'Inventaire technique & continuité',economy:'Pilotage économique & scénarios',workforce:'Charge des agents & collaborations',improvements:'Améliorations et non-régression'});
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
            else if(tool==='economy'){
                const eur=n=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(n/100);
                if(r.kind==='summary'){
                    e=entry('Registre économique local','CA vérifié, bénéfice, marge réelle et trésorerie : indisponibles');
                    e.append(entry('Budget API · USD',money(r.committed)+' / '+money(r.budget)+' engagés (estimation) · solde local '+money(r.remaining)));
                    for(const l of r.ledger)e.append(node('small',mode(l.mode)+' · '+l.calls+' appels · '+money(l.measured)+' mesurés · '+money(l.committed-l.measured)+' réservés/non mesurés'));
                    for(const [key,label] of [['owner_declared_live','Déclarations du propriétaire · non vérifiées'],['test','TEST · exclus du CA réel']]){
                        const t=r.receipts[key];e.append(entry(label,t.count+' écriture(s) · encaissements '+eur(t.gross_cents)+' · remboursements '+eur(t.refunds_cents)+' · net '+eur(t.net_cents)));
                    }
                    e.append(node('p','Aucun rapprochement EUR/USD, aucune déduction de bénéfice ou de trésorerie. Aucun investissement autorisé.','muted'));
                }else{
                    e=entry('Évaluation #'+r.assessment_id+' · '+r.title,'Opportunité #'+r.opportunity+' · mission #'+r.mission+' · '+mode(r.mode)+' · '+r.mission_state);
                    if(r.integrity!=='checked')e.append(node('p','Calcul ou références non vérifiables : scénario masqué.','station-pending'));
                    else{
                        const a=r.scenario.assumptions,v=r.scenario.result;
                        e.append(node('small',r.comparable?'Mission Cloud terminée · cohérence locale contrôlée':'Hors comparaison Cloud terminée'));
                        e.append(entry('Hypothèses mensuelles · EUR',a.monthly_units+' unités · prix '+eur(a.price_cents)+' · coût variable '+eur(a.variable_cost_cents)+' / unité · fixe '+eur(a.fixed_month_cents)));
                        e.append(entry('Scénario calculé · non validé','Contribution '+eur(v.contribution_cents)+' / unité · marge contributive '+(v.margin_bp/100).toFixed(2)+' % · résultat mensuel hypothétique '+eur(v.monthly_result_cents)));
                        e.append(node('small','Seuil : '+(v.breakeven_units===null?'non atteignable avec cette contribution':v.breakeven_units+' unités / mois')+' · score indicatif '+v.score+'/100 (pas une probabilité)'));
                        e.append(node('small','Automatisation supposée '+a.automation_pct+' % · risque déclaré '+a.risk+'/5 · '+v.evidence_count+' relevé(s) macro · '+v.page_count+' page(s) lue(s)'));
                    }
                    e.append(node('p',r.limit,'muted'));
                }
            }
            else if(tool==='infrastructure'){
                if(r.kind==='runtime'){
                    e=entry('Moteur local · '+r.version,r.mode==='preview'?'Aperçu sans worker':'Serveur opérationnel · requête locale reçue');
                    e.append(node('small','SQLite lisible · '+(r.database_bytes/1048576).toFixed(2)+' Mio logiques · journal '+r.journal_mode));
                    e.append(node('small','Tables de référence présentes : '+r.tables_present.length+' / '+(r.tables_present.length+r.tables_missing.length)));
                    if(r.tables_missing.length)e.append(node('p','Tables manquantes : '+r.tables_missing.join(', '),'station-pending'));
                    for(const [label,k] of [['OpenAI','openai_configured'],['Brave','brave_configured'],['n8n','n8n_configured'],['Bac à sable HTML','sandbox_enabled']])e.append(node('small',label+' : '+(r[k]?'configuration présente / activé':'non configuré / désactivé')));
                    e.append(node('p','Disponibilité des fournisseurs et intégrité complète non vérifiées dans cette vue.','muted'));
                    e.append(entry('Dernière préparation enregistrée',r.preparation?(r.preparation.integrity_recorded?'Intégrité déclarée OK lors de la préparation':'Intégrité non attestée dans le rapport'):'Rapport absent ou illisible'));
                    if(r.preparation)e.append(node('small','Tables protégées dans le rapport : '+Object.keys(r.preparation.protected_tables).length));
                    e.append(node('p','Sauvegarde actuelle non vérifiée ; aucune restauration testée par cette consultation.','station-pending'));
                    e.append(node('small',r.packaged_commit?'Révision de fabrication déclarée : '+r.packaged_commit.slice(0,12)+' (pas le HEAD Git courant)':'Révision Git locale non mesurée.'));
                }else{
                    e=entry(r.label,r.provider+' · '+(r.implemented?'Implémenté':'Non implémenté')+' · '+(r.authorized?'Politique autorisée':'Non autorisé'));
                    e.append(node('small',r.policy_present?r.calls+' / '+r.max_calls+' tentatives · '+money(r.reserved)+' / '+money(r.budget)+' réservés / plafond':'Politique absente'));
                    e.append(node('small',r.last?'Dernière tentative #'+r.last.id+' : '+r.last.state+' · '+r.last.created:'Aucune tentative enregistrée'));
                    e.append(node('small','Disponibilité actuelle non mesurée'));
                }
            }
            else if(tool==='quality'){
                const states={passed:'Réussi (enregistré)',failed:'Échoué',invalid:'Scénario invalide',unavailable:'Indisponible',unreadable:'Résultat incohérent ou illisible'};
                const integrity={match:'Empreinte du fichier identique',changed:'Fichier modifié : preuve non applicable',unavailable:'Correspondance non vérifiable'};
                e=entry((r.kind==='verification'?'Vérification':'Essai laboratoire')+' #'+r.id+' · '+r.name+' · V'+r.version,(states[r.status]||'Inconnu')+' · '+mode(r.mode)+' · '+r.created);
                e.append(node('small','Livrable #'+r.artifact+' · mission source #'+r.source_mission),node('p',integrity[r.identity]||'Correspondance inconnue',r.identity==='match'?'muted':'station-pending'));
                if(r.kind==='verification'){
                    e.append(node('small','Test par '+r.agent+' · mission #'+r.mission+' · '+mode(r.test_mode)));
                    for(const c of r.checks)e.append(node('small',(c.passed?'✓ ':'✗ ')+c.name));
                }else{
                    e.append(node('small','Profil '+r.profile+' · révision '+r.revision+' · '+r.size+' lignes synthétiques'));
                    const labels={tp:'Anomalies détectées',fp:'Fausses alertes',fn:'Anomalies manquées',recall:'Rappel',false_alert_share:'Part de fausses alertes'};
                    for(const [k,v] of Object.entries(r.metrics))e.append(node('small',labels[k]+' : '+(['recall','false_alert_share'].includes(k)?(100*v).toFixed(1)+' %':v)));
                }
                e.append(node('p',r.limit,'muted'));
            }
            else if(tool==='incidents'){
                if(r.kind==='summary'){
                    e=entry('Supervision enregistrée',r.recovery_count+' reprise(s) inscrite(s) dans le journal');
                    for(const c of r.counts)e.append(node('small',mode(c.mode)+' · '+c.state+' : '+c.count));
                    if(!r.counts.length)e.append(node('small','Aucune mission bloquée, en attente ou interrompue enregistrée.'));
                    e.append(node('p',r.recovery_policy));
                }else if(r.kind==='mission'){
                    e=entry('Mission #'+r.id+' · '+r.title,r.state+' · '+mode(r.mode)+' · '+r.created);
                    const labels={decision:'Décision à examiner',interrupted:'Interruption enregistrée',unreconciled:'Appel à rapprocher · coût incertain',budget:'Enveloppe insuffisante enregistrée',configuration:'Configuration manquante',limit:'Plafond moteur atteint',repeated_failure:'Échecs ou répétitions successifs',dependency:'Tâches non résolues',unknown:'Cause non classée · diagnostic requis'};
                    e.append(node('b',labels[r.category]||labels.unknown),node('small',r.pending_requests+' demande(s) en attente · '+r.unreconciled_calls+' appel(s) à rapprocher'),node('small','Ce diagnostic ne déclenche ni n’autorise aucune reprise. Les règles du moteur restent applicables.'));
                }
                else e=entry('Reprise enregistrée · campagne #'+r.campaign,r.diagnostic+' · mission #'+r.mission+' · tâche #'+r.task+' · réservation #'+r.ledger+' · '+r.created);
            }
            else if(tool==='home'){
                if(r.kind==='campaign'){
                    e=entry('Campagne #'+r.id+' · '+r.goal,r.state+' · '+r.missions+' / '+r.max_missions+' missions');
                    e.append(node('small',money(r.committed)+' / '+money(r.budget)+' engagés / plafond · restant local '+money(r.remaining)),node('small','Brave : '+r.searches+' / '+r.search_cap+' tentatives · restant '+r.search_remaining));
                    if(r.plan_id!==null)e.append(node('small','Incluse dans le plan #'+r.plan_id+(r.grant_id!==null?' · autorisation périodique #'+r.grant_id:'')));
                }else if(r.kind==='plan'){
                    e=entry('Plan #'+r.id,r.state+' · '+r.campaigns+' / '+r.max_campaigns+' campagnes');
                    e.append(node('small',money(r.committed)+' / '+money(r.budget)+' engagés / plafond · restant local '+money(r.remaining)),node('small',money(r.per_campaign)+' par campagne · Brave '+r.searches+' / '+r.search_cap+' · restant '+r.search_remaining));
                    if(r.grant_id!==null)e.append(node('small','Inclus dans l’autorisation périodique #'+r.grant_id+' · reprise manuelle interdite'));
                }else{
                    e=entry('Autorisation périodique #'+r.id,r.state+' · '+r.cadence+' · '+r.slots+' / '+r.periods+' périodes ouvertes');
                    e.append(node('small','Plafond total '+money(r.total_budget)+' · par période '+money(r.period_budget)+' · par campagne '+money(r.per_campaign)),node('small',money(r.committed)+' engagés · restant local '+money(r.remaining)+' · Brave '+r.searches+' / '+r.total_search+' · restant '+r.search_remaining+' · '+r.period_search+' par période'),node('small','Expire '+new Date(r.expires*1000).toLocaleString('fr-FR')+' · '+(r.within_grant_window?'dans la fenêtre globale enregistrée':'hors fenêtre globale ou autorisation inactive')+' · aucune permission d’exécution déduite'));
                    for(const sl of r.slot_details)e.append(entry('Période '+(sl.slot+1)+' · plan #'+sl.plan,sl.state+' · '+money(sl.spent)+' / '+money(sl.budget)+' engagés · Brave '+sl.searches+' / '+sl.search_cap));
                }
                e.append(node('small','Enveloppes imbriquées : ne pas additionner les engagements des campagnes, plans et périodes.','muted'));
                if(r.reason)e.append(node('p',r.reason));
            }
            else if(tool==='portfolio'){e=entry('#'+r.id+' · '+r.title,r.state+' · '+r.missions+' mission(s) · '+r.artifacts+' livrable(s)');e.append(node('small','Engagements API estimés : '+money(r.committed)));}
            else if(tool==='laboratory'){e=entry('Essai #'+r.id+' · '+r.name+' · V'+r.version,r.status+' · '+mode(r.mode)+' · '+r.created);e.append(node('small','Profil '+r.profile+' · révision '+r.revision+' · taille '+r.size+(r.campaign?' · campagne #'+r.campaign:'')));}
            else if(tool==='tools'){
                if(r.kind==='capability'){e=entry(r.label,r.provider+' · '+(r.implemented?'Implémenté':'Non implémenté')+' · '+(r.enabled?'Autorisé par politique':'Non autorisé'));e.append(node('small',r.policy_present?r.calls+' / '+r.max_calls+' tentatives · '+money(r.reserved)+' / '+money(r.budget)+' réservés / plafond':'Politique absente'));e.append(node('small','Disponibilité externe non testée'));}
                else e=entry('Tentative #'+r.id+' · '+r.capability,r.actor+' · '+r.state+' · '+money(r.reserved)+' réservés · '+r.created);
            }
            else if(tool==='business'){
                const eur=n=>new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(n/100);
                if(r.kind==='summary'){
                    e=entry('Registre commercial · EUR','Recettes réelles vérifiées : indisponibles. Aucune vente autorisée.');
                    for(const [key,label] of [['test','TEST'],['owner_declared_live','Déclaré par le propriétaire · non vérifié']]){
                        const t=r.totals[key];e.append(entry(label,'Encaissements '+eur(t.gross_cents)+' · remboursements '+eur(t.refunds_cents)+' · net '+eur(t.net_cents)));
                    }
                }else if(r.kind==='offer'){
                    e=entry('Offre #'+r.id+' · '+r.title,r.state+' · vente non autorisée');
                    if(r.price_cents!==undefined)e.append(node('p','Prix indicatif : '+eur(r.price_cents)),node('small','Résultat mensuel hypothétique : '+(r.monthly_result_hypothesis_cents===null?'non disponible':eur(r.monthly_result_hypothesis_cents))),node('small','Revue : '+(r.review||'non disponible')),node('p','Écarts : '+(r.gaps.join(' · ')||'aucun écart enregistré')));
                    if(r.state!=='unavailable')e.append(button('Consulter le dossier produit et son protocole',()=>loadDetail('offer_detail',r.id)));
                }else if(r.kind==='trial'){
                    e=entry('Protocole #'+r.id+' · offre #'+r.offer,r.state+' · '+r.observations+' / '+r.sample_size+' observations déclarées');e.append(node('small',r.positive+' positives · seuil '+r.success_min+' · non vérifiées'));
                }else if(r.kind==='channel'){
                    e=entry('Canal TEST · '+r.page,r.state+' · '+(r.within_window?'dans la fenêtre locale':'hors fenêtre'));e.append(node('small','État enregistré, pas une sonde de disponibilité externe.'));
                }else{
                    e=entry('Collecte TEST · '+r.page,r.state+' · '+(r.fresh?'instantané récent':'données actuelles indisponibles'));
                    if(r.fresh)e.append(node('small',r.test_signals+' signaux TEST · '+r.qualified_test+' qualifiés TEST ; aucun prospect réel vérifié'));
                }
            }
            else if(tool==='marketing'){
                e=entry('Dossier #'+r.id+' · '+r.title,r.state+' · offre #'+r.offer+' · '+r.language);
                e.append(node('small','Brouillon interne · aucune publication ni vidéo générée'));
                if(r.state==='draft'&&r.hermes_saved)e.append(button('Vérifier et lire le dossier HERMES',()=>loadDetail('hermes_detail',r.id)));
                if(r.state==='draft'&&r.marketing_saved)e.append(button('Vérifier et lire le dossier marketing / scénario YouTube',()=>loadDetail('marketing_detail',r.id)));
                if(!r.hermes_saved&&!r.marketing_saved)e.append(node('p','Aucun dossier enregistré.','muted'));
            }
            else if(tool==='offer_detail'){
                e=entry('Offre #'+r.id,r.state+' · proposition interne · vente non autorisée');
                if(r.content){const c=r.content;
                    e.append(node('p',r.limit),node('small','Projet #'+r.project+' · mission #'+r.mission+' · livrable '+(r.artifact?'#'+r.artifact:'absent')));
                    for(const [label,key] of [['Public cible (hypothèse)','audience'],['Problème','problem'],['Offre','offer'],['Livrables','deliverables'],['Canal envisagé','channel'],['Risques','risks']])e.append(entry(label,c[key]));
                    e.append(entry('Prix indicatif',new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(c.price_cents/100)),entry('Protocole envisagé',c.metric+' · '+c.success_min+' / '+c.sample_size+' · '+c.duration_days+' jours (non exécuté par cette consultation)'),entry('Contrôle avant vente','Revue : '+(r.review||'absente')+' · '+(r.gaps.join(' · ')||'aucun écart enregistré')));
                    if(r.review_gaps)e.append(node('p',r.review_gaps));
                    e.append(node('small',r.draft_eligible?'Préparation interne admissible selon les règles actuelles.':'Préparation interne non admissible selon les règles actuelles.'));
                }else e.append(node('p','Dossier indisponible ou référence invalide.'));
            }
            else if(tool==='marketing_detail'||tool==='hermes_detail'){
                e=entry('Dossier #'+r.id,r.state==='unavailable'?'Référence invalide, révoquée ou dossier indisponible.':'Dossier interne · '+r.state+' · publication non autorisée');
                if(r.content){const c=r.content;e.append(node('p',r.limit));
                    if(tool==='marketing_detail'){
                        e.append(entry('Page de présentation · brouillon',c.landing.title));
                        for(const k of ['summary','evidence','limitations','price','cta'])e.append(node('p',c.landing[k]));
                        e.append(entry('YouTube · scénario textuel',c.youtube.title),node('p',c.youtube.description),node('small','Durée prévue : '+r.storyboard_seconds+' s · aucun média généré'));
                        for(const [i,s] of c.youtube.storyboard.entries())e.append(entry('Séquence '+(i+1)+' · '+s.seconds+' s',s.visual),node('p','Voix prévue : '+s.voice));
                        e.append(entry('Réseaux sociaux · texte interne',c.social.text),entry('Règles média',c.media_policy.assets+' · '+c.media_policy.music),node('p','Contrôle technique du texte uniquement. Aucune diffusion, file de publication, voix, vidéo ou montage disponible.'));
                    }else{
                        e.append(entry('Présentation produit',c.title),node('p',c.offer_text));
                        for(const [label,key] of [['Livrables','deliverables'],['Public cible (hypothèse)','audience_hypothesis'],['Limites','limitations'],['Risques','risks']])e.append(entry(label,Array.isArray(c[key])?c[key].join(' · '):c[key]));
                        e.append(entry('Prix indicatif',new Intl.NumberFormat('fr-FR',{style:'currency',currency:'EUR'}).format(c.price_cents/100)),entry('Démonstration synthétique',c.demo_status));
                        for(const f of c.faq)e.append(entry(f.question,f.answer));
                        e.append(node('p','Étape prévue : contrôle du contenu avant toute activation.'));
                    }
                    e.append(node('pre',JSON.stringify(c,null,2)));
                }
            }
            else if(tool==='improvements'){
                const stateLabels={pending:'En attente',abandoned:'Abandonné',retained:'Retenu automatiquement',retained_manual:'Retenu sur décision',review:'À examiner',rejected:'Non retenu',unknown:'Inconnu'};
                if(r.kind==='summary'){
                    e=entry('Cycles techniques enregistrés','50 derniers cycles au maximum');
                    for(const c of r.counts)e.append(entry(stateLabels[c.state]||c.state,String(c.count)));
                    if(!r.counts.length)e.append(node('p','Aucun cycle d’amélioration enregistré.'));
                    e.append(node('p',r.limit),node('small','Aucune session de formation ou modification des modèles effectuée.'));
                }else{
                    e=entry('Cycle #'+r.id+' · projet #'+r.project,(stateLabels[r.state]||stateLabels.unknown)+' · campagne #'+r.campaign+' · '+r.profile);
                    e.append(node('small','Référence initiale #'+r.baseline+' · intégrité '+r.baseline_identity+' · candidate '+(r.candidate===null?'absente':'#'+r.candidate+' · intégrité '+r.candidate_identity)),node('small','Référence actuellement enregistrée : '+(r.reference===null?'aucune':'#'+r.reference)));
                    for(const p of r.replays)e.append(entry('Rejeu de la preuve #'+p.proof,p.status));
                    e.append(node('small','Non-régression enregistrée : '+(r.non_regression===null?'non renseignée':r.non_regression?'oui':'non')+' · nouvelle fonction avant/après : '+(r.feature_before||'non renseigné')+' / '+(r.feature_after||'non renseigné')));
                    e.append(node('small','Le statut historique ne prouve pas l’intégrité actuelle ni la qualité générale.','muted'));
                }
            }
            else if(tool==='workforce'){
                if(r.kind==='summary'){
                    e=entry('Organisation enregistrée',r.configured+' agents configurés · '+r.unresolved+' tâches non résolues dans des missions actives ou bloquées');
                    e.append(node('p',r.limit),node('small',r.delegation_count+' délégations historiques · '+r.delegations_displayed+' affichées · '+r.unmapped_tasks+' tâches sans agent configuré'));
                }else if(r.kind==='agent'){
                    e=entry(r.id,r.role);
                    const labels={blocked:'Bloquée',waiting:'En attente',dependency:'Dépendance non terminée',running_recorded:'Marquée en cours',selected:'Sélectionnée par le moteur',queued:'Prête / en file'};
                    if(!r.load.length)e.append(node('p','Aucune tâche non résolue dans le périmètre affiché. Disponibilité non mesurée.','muted'));
                    for(const x of r.load)e.append(entry(mode(x.mode),(labels[x.category]||x.category)+' · '+x.count));
                    e.append(node('small','Permissions du moteur (non des compétences mesurées) : '+r.permissions.join(', ')));
                    e.append(node('b','Expérience enregistrée · aucune note de compétence'));
                    if(!r.completed_tasks.length)e.append(node('small','Aucune tâche terminée enregistrée.'));
                    for(const x of r.completed_tasks)e.append(entry(mode(x.mode),'Tâches terminées : '+x.count+' · ne prouve pas leur qualité'));
                    if(!r.tool_evidence.length)e.append(node('small','Aucun événement d’outil enregistré.'));
                    for(const x of r.tool_evidence)e.append(entry((x.action==='other'?'Autres actions historiques':x.action)+' · '+mode(x.mode),x.ok+' OK moteur · '+x.failed+' refus/échecs · '+x.unknown+' résultat(s) inconnu(s)'));
                    if(r.load.some(x=>x.category==='blocked'||x.category==='waiting'))e.append(node('p','Point à examiner : tâches bloquées ou en attente. Leur cause ne démontre pas un manque de compétence.','station-pending'));
                    e.append(button('Consulter les preuves qualité',()=>open('quality')));
                    e.append(button('Consulter les incidents',()=>open('incidents')));
                }else e=entry(r.from_agent+' → '+r.to_agent,'Mission #'+r.mission+' · tâche #'+r.id+' · parent #'+r.parent+' · '+mode(r.mode)+' · '+r.state+' · mission '+r.mission_state);
            }
            else if(tool==='owner'){
                e=node('div',undefined,'owner-summary');
                const a=r.active;
                const metrics=node('div',undefined,'owner-metrics');
                for(const [k,v] of [['Plafond API local',money(r.budget)],['Engagements estimés',money(r.committed)],['Solde local estimé',money(r.remaining)],['Décisions en attente',String(r.pending)],['Brave · tentatives / limite',r.searches+' / '+r.search_limit],['Agents configurés',String(r.configured_agents)],['Missions à examiner',String(r.attention_count)]]){
                    const card=node('div',undefined,'metric');card.append(node('small',k),node('strong',v));metrics.append(card);
                }
                e.append(metrics);
                if(r.over_budget)e.append(node('p','Plafond local dépassé : aucun solde disponible.','error'));
                e.append(entry('Détail des engagements','Usage mesuré : '+money(r.measured)+' · non mesuré / réservé : '+money(r.unmeasured)),
                    entry('Ressources déclarées','OpenAI : '+(r.openai_configured?'configuré':'non configuré')+' · Brave : '+(r.brave_configured?'configuré':'non configuré')+' · bac à sable : '+(r.sandbox_enabled?'activé':'désactivé')),
                    entry('Limites par mission',money(r.mission_budget)+' · '+r.mission_calls+' appels maximum'));
                e.append(node('h3','Points de vigilance'));
                if(r.searches>=r.search_limit)e.append(node('p','Quota Brave local atteint ou nul.','station-pending'));
                if(!r.openai_configured)e.append(node('p','OpenAI non configuré.','station-pending'));
                if(!r.brave_configured)e.append(node('p','Brave non configuré.','station-pending'));
                e.append(entry('Décisions en attente',r.pending+' enregistrée(s) · '+r.pending_decisions.length+' affichée(s)'));
                for(const d of r.pending_decisions)e.append(entry('Demande #'+d.id+' · '+d.title,'Mission #'+d.mission+' · '+mode(d.mode)+(d.may_resume?' · peut reprendre la mission, appels potentiellement facturables':' · examen requis')));
                e.append(button('Consulter les décisions réservées',()=>open('decisions',true)));
                e.append(entry('Missions à examiner',r.attention_count+' enregistrée(s) · '+r.attention.length+' affichée(s)'));
                for(const m of r.attention)e.append(entry('#'+m.id+' · '+m.title,m.state+' · '+mode(m.mode)));
                e.append(button('Consulter les incidents',()=>open('incidents',true)));
                e.append(node('h3','Répartition des missions enregistrées'));
                for(const m of r.mission_counts)e.append(entry(mode(m.mode),m.state+' · '+m.count));
                e.append(node('h3','Pilotage actif enregistré'));
                for(const [key,label] of [['periods','Autorisations périodiques'],['plans','Plans'],['campaigns','Campagnes'],['missions','Missions']]){
                    e.append(node('b',label+' · '+r.active_counts[key]+' au total / '+a[key].length+' affiché(s)'));
                    if(!a[key].length)e.append(node('p','Aucun état actif enregistré.','muted'));
                    for(const row of a[key])e.append(entry('#'+row.id+' · '+(row.title||row.goal||row.cadence||label),row.state+(row.mode?' · '+mode(row.mode):'')+(row.expires?' · expire '+new Date(row.expires*1000).toLocaleString('fr-FR'):'')+(row.budget!==undefined?' · plafond '+money(row.budget):row.total_budget!==undefined?' · plafond '+money(row.total_budget):'')));
                }
                e.append(node('h3','Accès de supervision en lecture seule'));
                for(const [tool,label] of [['home','Campagnes, plans et autorisations'],['economy','Budget et économie'],['business','Activité commerciale'],['quality','Contrôle des livrables'],['infrastructure','Infrastructure et connecteurs'],['agents','Organisation des agents']])e.append(button(label,()=>open(tool,true)));
                if(window.AESCampusCommands?.ownerContext()){
                    e.append(node('h3','Commandes réservées au propriétaire'),node('p','Ouvrir un formulaire ne lance aucune action. Les confirmations, plafonds et contrôles du moteur restent obligatoires.','muted'));
                    for(const [kind,label] of [['missions','Ouvrir les commandes de missions'],['home','Ouvrir les commandes de pilotage'],['decisions','Ouvrir les commandes de décisions']]){
                        const b=button(label,()=>window.AESCampusCommands.open(kind));b.dataset.ownerCommandPanel=kind;e.append(b);
                    }
                }else e.append(node('p','Commandes réservées indisponibles dans ce contexte de consultation.','muted'));
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
    function open(tool,fromOwner=false){
        if(!station||!Object.hasOwn(names,tool))return;
        reset();active=tool;panel.hidden=false;
        const title=node('h3',names[tool]+' · consultation locale');
        const descriptions={improvements:'Historique des comparaisons techniques de produits. Aucun test relancé, aucune promotion de version ni formation d’agent déclenchée.',workforce:'Charge enregistrée par agent et mode, dépendances, 50 dernières délégations et résultats d’outils historiques. Aucune note de compétence, affectation ou nouvelle permission. Les résultats OK ne prouvent pas la qualité d’un travail.',economy:'Registre API USD et encaissements EUR séparés ; 30 évaluations les plus récentes par opportunité, calculs et références contrôlés localement. Aucun nouveau devis, paiement, investissement ou prévision certifiée.',infrastructure:'Inventaire du moteur et des tables SQLite, configuration sans secrets, historique des connecteurs et rapport de préparation éventuel. Aucun ping, contrôle intégral, lancement de maintenance, sauvegarde ou restauration.',quality:'50 dernières vérifications et 50 derniers essais de laboratoire. Correspondance SHA-256 avec le contenu actuel, statut enregistré et assertions limitées. Simulation distincte de Cloud. Aucun test relancé, aucune validation de vente ou de sécurité générale.',incidents:'États persistés et règles réelles de reprise. 50 missions à examiner et 50 reprises les plus récentes au maximum. Aucune reprise déclenchée, aucun diagnostic réseau ; une reprise enregistrée ne prouve pas la résolution.',business:'Offres, protocoles, canaux TEST et registre EUR. Les montants déclarés ne sont pas vérifiés. Les signaux périmés ne sont pas affichés comme actuels. Aucun lancement externe.',marketing:'30 derniers brouillons internes. La présence d’un dossier ne garantit pas sa validité ; chaque ouverture recontrôle les preuves. Scénarios et textes uniquement : aucun média généré, aucun compte ou calendrier de publication opérationnel.',owner:'Vue consolidée des ressources et du pilotage, sans vérification réseau. Aucun chiffre d’affaires ni bénéfice déduit.',decisions:'100 demandes au maximum, en attente en priorité. Les coûts et risques sont déclarés par les agents, pas des devis vérifiés. Le traitement est disponible dans le bureau du propriétaire ; le module historique reste accessible.',home:'États enregistrés des campagnes, plans et autorisations périodiques (15 de chaque, états actifs prioritaires). Enveloppes imbriquées non additionnables ; les restants sont arithmétiques, pas des crédits disponibles ni une autorisation d’exécution. Aucun lancement ni reprise.',portfolio:'100 dernières activités enregistrées. Aucune création de projet ni synchronisation automatique.',laboratory:'100 derniers essais enregistrés ; aucun test déclenché. Un statut ne constitue pas une validation commerciale.',tools:'Catalogue et politiques locales, 50 dernières tentatives. Aucun test de disponibilité ni appel de connecteur.',agents:'Rôles et permissions actuels du moteur, en consultation. Aucun agent créé.',goals:'XP enregistrés par le moteur et tâches par mode. Les XP ne donnent aucun droit ; les objectifs éditables restent dans le module historique.'};
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
                if(['artifact','report','marketing_detail','hermes_detail','offer_detail'].includes(kind))out.append(button('← Retour aux résultats',()=>load(tool,last)));
                renderRows(kind,payload.rows,out,(k,id)=>load(k,{id:String(id)}));
            }catch(e){if(n===epoch){out.replaceChildren();status.textContent='Lecture indisponible'+(e.message==='413'?' : contenu trop volumineux':e.message==='400'?' : paramètres invalides':'')+'.';}}
            finally{clearTimeout(timer);}
        }
        if(fromOwner)actions.append(button('Retour au tableau de direction',()=>open('owner')));
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
