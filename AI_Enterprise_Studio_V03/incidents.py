"""Narrow, auditable recovery of explicit upstream failures. No network here."""
import re
TRANSIENT=('HTTP 502','HTTP 503','HTTP 504')
LIMIT='Une reprise par campagne de plan, réservations conservées. Timeout, HTTP 429, refus, authentification, quota, résultat incertain et effet outil non rejoués automatiquement.'

def classify(state,error,pending,unreconciled):
    """Local diagnostic only. Never changes state or grants a retry."""
    error=error if isinstance(error,str) else ''
    if pending or state=='en attente':
        category='decision'
    elif state=='interrompue':
        category='interrupted'
    elif unreconciled:
        category='unreconciled'
    elif error in ('Budget logiciel insuffisant pour réserver cet appel.','Budget de mission insuffisant pour réserver cet appel.','Enveloppe Autopilote insuffisante pour réserver cet appel.'):
        category='budget'
    elif error in ('Clé OpenAI manquante','Clé OpenAI manquante.'):
        category='configuration'
    elif re.fullmatch(r'Plafond de tours atteint pour la tâche #[0-9]+',error) or error in ('Plafond des appels IA de mission atteint.','Plafond d’actions de mission atteint'):
        category='limit'
    elif re.fullmatch(r'Trois outils refusés/échoués de suite sur tâche #[0-9]+',error) or error.startswith('Action identique répétée trois fois; tâche #'):
        category='repeated_failure'
    elif error=='Tâches non résolues.':
        category='dependency'
    else:
        category='unknown'
    return {'category':category,'pending_requests':pending,'unreconciled_calls':unreconciled,
            'automatic_retry_authorized':False}

def init(c):
    c.execute("""CREATE TABLE IF NOT EXISTS incident_recoveries(
        campaign INTEGER PRIMARY KEY REFERENCES campaigns(id),mission INTEGER NOT NULL REFERENCES missions(id),
        task INTEGER NOT NULL REFERENCES tasks(id),ledger INTEGER NOT NULL UNIQUE REFERENCES ledger(id),
        diagnostic TEXT NOT NULL,created TEXT DEFAULT CURRENT_TIMESTAMP)""")

def eligible(c,mid,cfg):
    row=c.execute("""SELECT m.error,m.state,m.mode,m.engine,ca.id AS campaign,ca.state AS campaign_state
        FROM missions m JOIN campaign_missions cm ON cm.mission=m.id JOIN campaigns ca ON ca.id=cm.campaign
        WHERE m.id=?""",(mid,)).fetchone()
    if not row or row['state']!='bloquée' or row['mode']!='cloud' or row['engine']!='dynamic' or row['campaign_state']!='bloqué':return None
    if c.execute('SELECT 1 FROM incident_recoveries WHERE campaign=?',(row['campaign'],)).fetchone():return None
    l=c.execute('SELECT * FROM ledger WHERE mission=? ORDER BY id DESC LIMIT 1',(mid,)).fetchone()
    if not l or l['state']!='à rapprocher' or l['actual'] is not None or l['diagnostic'] not in TRANSIENT:return None
    t=c.execute("""SELECT * FROM tasks t WHERE mission=? AND state='prête' AND NOT EXISTS
        (SELECT 1 FROM tasks ch WHERE ch.parent=t.id AND ch.state!='terminée')
        ORDER BY CASE WHEN parent IS NULL THEN 1 ELSE 0 END,id LIMIT 1""",(mid,)).fetchone()
    if not t or l['stage']!=t['id'] or l['agent']!=t['agent'] or t['turns']+1>=cfg['turn_limit']:return None
    if row['error']!=t['agent']+' : appel OpenAI non confirmé; réservation conservée. '+l['diagnostic']:return None
    # Failed provider request occurred before any accepted action for this call.
    count,spent=c.execute('SELECT COUNT(*),COALESCE(SUM(COALESCE(actual,reserved)),0) FROM ledger WHERE mission=?',(mid,)).fetchone()
    if count>=cfg['call_limit'] or spent+l['reserved']>cfg['mission_budget']:return None
    used=c.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM ledger').fetchone()[0]
    budget=c.execute('SELECT budget FROM campaigns WHERE id=?',(row['campaign'],)).fetchone()[0]
    charged=c.execute("""SELECT COALESCE(SUM(COALESCE(l.actual,l.reserved)),0) FROM ledger l
        JOIN campaign_missions cm ON cm.mission=l.mission WHERE cm.campaign=?""",(row['campaign'],)).fetchone()[0]
    if used+l['reserved']>cfg['budget'] or charged+l['reserved']>budget:return None
    return {'campaign':row['campaign'],'mission':mid,'task':t['id'],'ledger':l['id'],'diagnostic':l['diagnostic']}

def record(c,mid,cfg):
    x=eligible(c,mid,cfg)
    if not x:raise ValueError('Incident non éligible à la reprise')
    c.execute('INSERT INTO incident_recoveries(campaign,mission,task,ledger,diagnostic) VALUES(:campaign,:mission,:task,:ledger,:diagnostic)',x)

def history(c,cid):
    return [dict(x) for x in c.execute('SELECT * FROM incident_recoveries WHERE campaign=?',(cid,))]
