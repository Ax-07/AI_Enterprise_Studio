"""Read-only next-step planner. No provider calls, no mutation, no autonomous spend."""
import json
import verification
import recovery

VERSION='2'
RESUMABLE={'bloquée','interrompue','arrêtée','prête'}

def plan(c,cfg):
    def result(action,title,reason,mission=None,artifact=None,proof=None,**extra):
        return {'policy':VERSION,'action':action,'title':title,'reason':reason,
                'mission':mission,'artifact':artifact,'proof':proof,**extra}
    active=c.execute("SELECT id FROM missions WHERE state='en cours' ORDER BY id DESC LIMIT 1").fetchone()
    if active:
        return result('wait','Mission en cours','Attendre le résultat de la mission active. Aucun lancement concurrent.',active['id'])
    pending=c.execute("SELECT mission FROM requests WHERE state='en attente' ORDER BY id DESC LIMIT 1").fetchone()
    if pending:
        return result('decisions','Examiner une décision','Une demande du propriétaire est en attente; aucun engagement automatique.',pending['mission'])
    mission=c.execute("SELECT * FROM missions WHERE mode='cloud' ORDER BY id DESC LIMIT 1").fetchone()
    if not mission:
        if cfg.get('key') and cfg.get('budget',0)>0:
            return result('opportunity','Explorer une opportunité','Aucune mission Cloud enregistrée; préparer une étude, sans lancement automatique.')
        return result('review','Configurer les ressources','Aucune mission Cloud; vérifier les ressources et plafonds avant une étude.')
    mid=mission['id'];state=mission['state']
    spent,calls=c.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0),COUNT(*) FROM ledger WHERE mission=?',(mid,)).fetchone()
    total=c.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM ledger').fetchone()[0]
    events=c.execute('SELECT COUNT(*) FROM events WHERE mission=?',(mid,)).fetchone()[0]
    # Only the latest version of each deliverable; prioritize the newest NEXUS output.
    artifact=c.execute("SELECT * FROM artifacts WHERE mission=? AND agent='NEXUS' ORDER BY id DESC LIMIT 1",(mid,)).fetchone()
    aid=artifact['id'] if artifact else None
    proof=c.execute('SELECT * FROM verification_results WHERE artifact=? ORDER BY id DESC LIMIT 1',(aid,)).fetchone() if aid is not None else None
    evidence=json.loads(proof['result']) if proof else {}
    proof_id=proof['id'] if proof else None
    proof_status=evidence.get('status')
    global_left=max(0,cfg.get('budget',0)-total)
    mission_left=max(0,cfg.get('mission_budget',0)-spent)
    calls_left=max(0,cfg.get('call_limit',0)-calls)
    next_task=c.execute("""SELECT id,turns,agent FROM tasks t WHERE mission=? AND state='prête'
        AND NOT EXISTS(SELECT 1 FROM tasks ch WHERE ch.parent=t.id AND ch.state!='terminée')
        ORDER BY CASE WHEN parent IS NULL THEN 1 ELSE 0 END,id LIMIT 1""",(mid,)).fetchone()
    limits={'estimated_mission_usd':spent/1e6,'global_left_usd':global_left/1e6,
            'mission_left_usd':mission_left/1e6,'calls_left':calls_left,'proof_status':proof_status,
            'proof_agent':proof['agent'] if proof else None}
    def step(action,title,reason):
        return result(action,title,reason,mid,aid,proof_id,**limits)
    if state=='en attente':
        return step('diagnostic','Examiner la mission en attente','La mission attend une résolution; vérifier le journal avant toute reprise.')
    # A known Shopify contract is a specific local, free operation, not a generic HTML validator.
    shopify=bool(artifact and artifact['name'].lower().endswith('.html') and
                 (artifact['name'] in ('prototype_rapprochement_shopify_fr_en.html','prototype_shopify_correction_v2_fr_en.html')
                  or c.execute("""SELECT 1 FROM mission_artifact_refs r JOIN verification_results v ON v.artifact=r.artifact
                     WHERE r.mission=? AND v.spec=? LIMIT 1""",(mid,json.dumps(verification.shopify_spec(),ensure_ascii=False))).fetchone()))
    if shopify and proof_status in (None,'unavailable','invalid'):
        if cfg.get('html_sandbox_enabled',False):
            return step('verify','Tester gratuitement le livrable Shopify','Aucun résultat exploitable pour cette version. Exécuter le scénario prédéfini sans appel IA.')
        return step('files','Activer ou examiner le bac à sable','Le test HTML est indisponible sans sandbox activé. Aucun appel IA nécessaire pour cette configuration.')
    if state in RESUMABLE:
        recover=recovery.candidate(c,mid,cfg)
        if recover:
            return result('close_audit','Clôturer l’audit sur preuve','SENTINEL a réussi les quatre tests puis épuisé ses tours. Synthèse technique partielle gratuite, sans rapport inventé ni remise à zéro. La conclusion ATLAS reste à reprendre.',mid,recover['artifact'],recover['proof'],task=recover['task'],**limits)
        if not cfg.get('key') or global_left<=0 or mission_left<=0 or calls_left<=0 or events>=cfg.get('call_limit',0):
            return step('diagnostic','Examiner les limites de la mission','Clé ou marge budgétaire/appels insuffisants selon les plafonds locaux. Ne pas relancer.')
        if mission['engine']=='dynamic' and (not next_task or next_task['turns']>=cfg.get('turn_limit',0)):
            return step('diagnostic','Examiner le blocage de tâche','Aucune tâche exécutable sous les limites actuelles. Conserver les preuves et ne pas réinitialiser les compteurs.')
        if proof_status=='passed':
            return step('resume','Reprendre la mission existante','Une preuve réussie existe sur le dernier livrable; reprendre les tâches restantes sans refaire le travail terminé. Le modèle reste soumis aux plafonds et réservations.')
        return step('diagnostic','Diagnostiquer la mission bloquée','Ne pas répéter aveuglément une action. Consulter les erreurs et preuves avant de décider d’une reprise.')
    if state!='terminée':
        return step('diagnostic','Examiner la mission','État non reconnu pour une proposition automatique.')
    if not cfg.get('key') or global_left<=0:
        return step('review','Examiner les ressources','Aucune marge Cloud disponible selon les plafonds locaux; les fichiers et preuves restent consultables.')
    if proof_status=='failed':
        return step('improve','Préparer une correction ciblée','Le dernier livrable a échoué à des assertions. Préparer une nouvelle version sans écraser l’original.')
    if aid and proof_status=='passed':
        return step('market','Préparer la validation commerciale','Les assertions fournies ont réussi; cela ne prouve ni demande, ni compatibilité réelle, ni sécurité générale. Étudier les données manquantes et la rentabilité, sans vente.')
    if aid:
        return step('functional','Préparer un audit fonctionnel','Aucune preuve de réussite sur cette version. Définir des assertions indépendantes avant toute étude commerciale.')
    return step('diagnostic','Examiner la conclusion de la mission','Aucun nouveau livrable NEXUS dans cette mission. Lire la conclusion avant de définir un nouvel objectif.')
