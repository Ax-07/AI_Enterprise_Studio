"""D04.4: closed command contract; operations use the original dispatcher."""
STOP_ROUTES={'mission_stop':'/api/stop','campaign_stop':'/api/autopilot/stop',
             'plan_stop':'/api/planner/stop','periodic_revoke':'/api/periodic/revoke'}

def translate(body):
    if not isinstance(body,dict) or body.get('confirm') is not True:
        raise ValueError('Confirmation explicite requise')
    action=body.get('action')
    if not isinstance(action,str):raise ValueError('Commande invalide')
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
