"""D04.4/D05.2: closed command contracts, shared original dispatcher."""
import re
STOP_ROUTES={'mission_stop':'/api/stop','campaign_stop':'/api/autopilot/stop',
             'plan_stop':'/api/planner/stop','periodic_revoke':'/api/periodic/revoke'}

OWNER_ACTIONS=frozenset(('decision','mission_cloud','mission_resume','campaign_start','campaign_resume','plan_start','plan_resume','periodic_authorize'))

def owner_translate(body):
    if not isinstance(body,dict) or body.get('confirm') is not True:
        raise ValueError('Confirmation explicite requise')
    action=body.get('action')
    if not isinstance(action,str) or action not in OWNER_ACTIONS:
        raise ValueError('Commande de direction non autorisée')
    def fields(*keys):
        if set(body)!={'action','confirm',*keys}:raise ValueError('Paramètres incomplets ou inattendus')
    def ident():
        v=body.get('id')
        if type(v) is not int or not 1<=v<=9007199254740991:raise ValueError('Identifiant invalide')
        return v
    def money(key):
        v=body.get(key)
        if not isinstance(v,str) or not re.fullmatch(r'[0-9]{1,2}(?:\.[0-9]{1,6})?',v) or not 0.01<=float(v)<=10:
            raise ValueError('Budget décimal USD de 0,01 à 10 requis')
        return v
    def integer(key,lo,hi):
        v=body.get(key)
        if type(v) is not int or not lo<=v<=hi:raise ValueError('Quota invalide : '+key)
        return v
    def boolean(key):
        if type(body.get(key)) is not bool:raise ValueError('Autorisation invalide : '+key)
        return body[key]
    if action=='decision':
        fields('id','decision')
        if body['decision'] not in ('étude acceptée','refusée'):raise ValueError('Décision invalide')
        return '/api/decision',{'id':ident(),'decision':body['decision'],'confirm':True}
    if action=='mission_cloud':
        fields('title')
        v=body['title']
        if not isinstance(v,str) or not 1<=len(v.strip())<=1500:raise ValueError('Objectif invalide')
        return '/api/start',{'title':v.strip(),'mode':'cloud','engine':'dynamic','confirm':True}
    if action in ('mission_resume','campaign_resume','plan_resume'):
        fields('id')
        return {'mission_resume':'/api/resume','campaign_resume':'/api/autopilot/resume','plan_resume':'/api/planner/resume'}[action],{'id':ident(),'confirm':True}
    if action=='campaign_start':
        fields('goal','budget','max_missions','search_cap','permissions','project')
        goal=body['goal'];flags=body['permissions'];project=body['project']
        if not isinstance(goal,str) or not 1<=len(goal.strip())<=600:raise ValueError('Objectif invalide')
        if not isinstance(flags,dict) or set(flags)!={'research','production','tests','market'} or any(type(v) is not bool for v in flags.values()) or not any(flags.values()):raise ValueError('Permissions invalides')
        if not (isinstance(project,str) and project in ('auto','explore') or type(project) is int and 1<=project<=9007199254740991):raise ValueError('Activité invalide')
        cap=integer('search_cap',0,10)
        if cap and not flags['research']:raise ValueError('Recherche non autorisée')
        return '/api/autopilot/start',{'goal':goal.strip(),'budget':money('budget'),'max_missions':integer('max_missions',1,10),'search_cap':cap,'permissions':flags,'project':project,'campaign_mode':'explore' if project=='explore' else 'progression','connector_cap':0,'connector_budget':'0','confirm':True}
    if action=='plan_start':
        fields('budget','per_campaign','max_campaigns','search_cap','explore')
        return '/api/planner/start',{'budget':money('budget'),'per_campaign':money('per_campaign'),'max_campaigns':integer('max_campaigns',1,5),'search_cap':integer('search_cap',0,10),'explore':boolean('explore'),'confirm':True}
    fields('cadence','periods','total_budget','period_budget','per_campaign','max_campaigns','total_search','period_search','explore')
    if body['cadence'] not in ('daily','weekly','monthly'):raise ValueError('Cadence invalide')
    return '/api/periodic/authorize',{'cadence':body['cadence'],'periods':integer('periods',1,12),'total_budget':money('total_budget'),'period_budget':money('period_budget'),'per_campaign':money('per_campaign'),'max_campaigns':integer('max_campaigns',1,5),'total_search':integer('total_search',0,120),'period_search':integer('period_search',0,10),'explore':boolean('explore'),'confirm':True}

COMMERCIAL_ACTIONS=frozenset(('draft_prepare','draft_revoke','trial_close','test_publish','test_collect','test_stop','test_sync'))

def commercial_translate(body):
    action=body['action']
    def fields(*keys):
        if set(body)!={'action','confirm',*keys}:raise ValueError('Champs commerciaux invalides')
    def integer(key,lo=1,hi=9007199254740991):
        v=body.get(key)
        if type(v) is not int or not lo<=v<=hi:raise ValueError('Entier hors limites : '+key)
        return v
    def hexvalue(key,size):
        v=body.get(key)
        if not isinstance(v,str) or not re.fullmatch('[0-9a-f]{'+str(size)+'}',v):
            raise ValueError('Référence invalide : '+key)
        return v
    if action=='draft_prepare':
        fields('offer','snapshot_sha256')
        return '/api/acquisition/prepare',{'confirm':True,'offer':integer('offer'),'snapshot_sha256':hexvalue('snapshot_sha256',64),'language':'fr'}
    if action=='draft_revoke':
        fields('draft')
        return '/api/acquisition/revoke',{'confirm':True,'draft':integer('draft')}
    if action=='trial_close':
        fields('trial')
        return '/api/business/close',{'confirm':True,'trial':integer('trial')}
    if action=='test_publish':
        fields('draft','snapshot_sha256','duration_seconds')
        return '/api/acquisition/test_publish',{'confirm':True,'draft':integer('draft'),'snapshot_sha256':hexvalue('snapshot_sha256',64),'duration_seconds':integer('duration_seconds',60,1800)}
    if action=='test_collect':
        fields('page','quota','duration_seconds')
        return '/api/acquisition/test_collect',{'confirm':True,'page':hexvalue('page',32),'quota':integer('quota',1,10),'duration_seconds':integer('duration_seconds',1,600)}
    if action in ('test_stop','test_sync'):
        fields('page')
        return '/api/acquisition/'+action,{'confirm':True,'page':hexvalue('page',32)}
    raise ValueError('Commande commerciale non autorisée')

def translate(body):
    if not isinstance(body,dict) or body.get('confirm') is not True:
        raise ValueError('Confirmation explicite requise')
    action=body.get('action')
    if not isinstance(action,str):raise ValueError('Commande invalide')
    if action in COMMERCIAL_ACTIONS:return commercial_translate(body)
    if action=='mission_demo':
        if set(body)!={'action','confirm','title'} or not isinstance(body['title'],str):
            raise ValueError('Simulation invalide')
        title=body['title'].strip()
        if not 1<=len(title)<=1500:raise ValueError('Titre de 1 à 1500 caractères requis')
        return '/api/start',{'title':title,'mode':'demo','engine':'dynamic'}
    if action not in STOP_ROUTES or set(body)!={'action','confirm','id'}:
        raise ValueError('Commande non autorisée')
    ident=body['id']
    if type(ident) is not int or not 1<=ident<=9007199254740991:
        raise ValueError('Identifiant invalide')
    return STOP_ROUTES[action],{'id':ident,'confirm':True}
