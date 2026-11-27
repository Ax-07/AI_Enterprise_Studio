"""Artifact queries and static validation; no execution or transaction ownership.
Shared mission authorization remains with the calling action engine.
"""

def latest(c,mid,name): return c.execute('SELECT * FROM artifacts WHERE mission=? AND name=? ORDER BY version DESC LIMIT 1',(mid,name)).fetchone()


def attached_artifact(c,mid):
    return c.execute("SELECT a.* FROM mission_artifact_refs r JOIN artifacts a ON a.id=r.artifact JOIN missions m ON m.id=a.mission WHERE r.mission=? AND m.mode='cloud'",(mid,)).fetchone()


def resolve_artifact(c,mid,target,*,attached_artifact,latest):
    if target.startswith('ref:'):
        row=attached_artifact(c,mid)
        if not row or target!='ref:'+str(row['id']): raise ValueError('Référence non autorisée pour cette mission')
        return row,True
    return latest(c,mid,target),False


def reference_metadata(row):
    return {'target':'ref:'+str(row['id']),'id':row['id'],'mission_source':row['mission'],'name':row['name'],'version':row['version'],'agent':row['agent'],'lecture_seule':True}


def check(name,content,*,ast,csv,io,json):
    suffix=name.rsplit('.',1)[-1].lower()
    try:
        if suffix=='py': ast.parse(content); label='Syntaxe Python valide'
        elif suffix=='json': json.loads(content); label='JSON décodable'
        elif suffix=='csv':
            rows=list(csv.reader(io.StringIO(content),strict=True)); widths={len(r) for r in rows if r}
            if not rows or len(widths)!=1 or not next(iter(widths),0): raise ValueError('CSV vide ou colonnes incohérentes')
            label=f'CSV rectangulaire : {len(rows)} lignes, {next(iter(widths))} colonnes'
        else: label='Contenu non vide; pas de validateur spécialisé'
        if not content.strip(): raise ValueError('Fichier vide')
        return {'valide':True,'controle':label,'limite':'Aucun code exécuté, aucun test fonctionnel ni conformité garantis.'}
    except (SyntaxError,ValueError,csv.Error) as e: return {'valide':False,'controle':str(e)[:300],'limite':'Contrôle statique uniquement.'}
