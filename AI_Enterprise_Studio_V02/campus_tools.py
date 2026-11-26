"""D04.2: explicit, bounded read tools, no engine actions."""
import json
import sqlite3
from pathlib import Path

TOOLS=frozenset(('missions','work','files','artifact','memory','report','finance','opps'))
MAX_ARTIFACT_BYTES=2*1024*1024
MAX_REPORT_BYTES=256*1024

class BadQuery(ValueError): pass
class Missing(LookupError): pass
class TooLarge(ValueError): pass

def read(path, tool, params):
    if tool not in TOOLS: raise BadQuery('Outil inconnu')
    allowed={'id'} if tool in ('artifact','report') else {'q'} if tool=='memory' else set()
    if set(params)-allowed or any(len(v)!=1 for v in params.values()):
        raise BadQuery('Paramètres invalides')
    ident=None
    if tool in ('artifact','report'):
        raw=params.get('id',[''])[0]
        if not raw.isascii() or not raw.isdecimal() or len(raw)>18 or int(raw)<1:
            raise BadQuery('Identifiant invalide')
        ident=int(raw)
    term=params.get('q',[''])[0].strip()
    if tool=='memory' and not 2<=len(term)<=120:
        raise BadQuery('Recherche : 2 à 120 caractères')
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=3)
    try:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        def rows(sql,args=()):
            return [dict(r) for r in db.execute(sql,args)]
        if tool=='missions':
            result=rows("SELECT id,title,mode,state,created FROM missions ORDER BY id DESC LIMIT 100")
        elif tool=='work':
            result=rows("""SELECT t.id,t.mission,t.agent,t.state,t.created,m.mode,substr(t.goal,1,500) AS goal
                FROM tasks t JOIN missions m ON m.id=t.mission ORDER BY t.id DESC LIMIT 100""")
        elif tool=='files':
            result=rows("""SELECT a.id,a.mission,a.name,a.version,a.agent,a.created,m.mode,
                length(CAST(a.content AS BLOB)) AS bytes FROM artifacts a JOIN missions m ON m.id=a.mission
                ORDER BY a.id DESC LIMIT 100""")
        elif tool=='artifact':
            result=rows("""SELECT a.id,a.name,a.version,a.agent,a.mission,m.mode,
                length(CAST(a.content AS BLOB)) AS bytes,
                CASE WHEN length(CAST(a.content AS BLOB))<=? THEN a.content ELSE NULL END AS content
                FROM artifacts a JOIN missions m ON m.id=a.mission WHERE a.id=?""",(MAX_ARTIFACT_BYTES,ident))
            if not result: raise Missing('Livrable absent')
            if result[0]['content'] is None: raise TooLarge('Fichier trop volumineux ou sans contenu')
        elif tool=='memory':
            # Literal substring, no wildcard interpretation, bounded most recent matches.
            result=rows("""SELECT r.id,r.mission,r.agent,r.created,m.mode,m.title,
                substr(r.report,1,400) AS excerpt FROM reports r JOIN missions m ON m.id=r.mission
                WHERE instr(lower(COALESCE(r.report,'')),lower(?))>0
                   OR instr(lower(COALESCE(m.title,'')),lower(?))>0
                   OR instr(lower(COALESCE(r.agent,'')),lower(?))>0
                ORDER BY r.id DESC LIMIT 50""",(term,term,term))
        elif tool=='report':
            result=rows("""SELECT r.id,r.mission,r.agent,r.created,m.mode,m.title,
                length(CAST(r.report AS BLOB)) AS bytes,
                CASE WHEN length(CAST(r.report AS BLOB))<=? THEN r.report ELSE NULL END AS content
                FROM reports r JOIN missions m ON m.id=r.mission WHERE r.id=?""",(MAX_REPORT_BYTES,ident))
            if not result: raise Missing('Rapport absent')
            if result[0]['content'] is None: raise TooLarge('Rapport trop volumineux ou sans contenu')
            try:
                value=json.loads(result[0]['content'])
                if isinstance(value,dict) and isinstance(value.get('rapport'),str):
                    result[0]['content']=value['rapport']
            except (ValueError,TypeError): pass
        elif tool=='finance':
            result=rows("""SELECT COALESCE(NULLIF(l.agent,''),'Non attribué') AS agent,
                COALESCE(m.mode,'inconnu') AS mode, COUNT(*) AS calls,
                COALESCE(SUM(COALESCE(l.actual,l.reserved,0)),0) AS committed_micro_usd,
                COALESCE(SUM(COALESCE(l.actual,0)),0) AS measured_micro_usd,
                COALESCE(SUM(CASE WHEN l.actual IS NULL THEN COALESCE(l.reserved,0) ELSE 0 END),0) AS unmeasured_micro_usd
                FROM ledger l LEFT JOIN missions m ON m.id=l.mission GROUP BY 1,2 ORDER BY 4 DESC,1,2 LIMIT 100""")
        else:
            result=rows("""SELECT o.id,o.mission,o.title,o.status,substr(o.body,1,1200) AS body,
                substr(o.next_test,1,600) AS next_test,o.created,m.mode FROM opportunities o
                JOIN missions m ON m.id=o.mission ORDER BY o.id DESC LIMIT 100""")
        return {'schema':'aes.campus.tool.v1','tool':tool,'read_only':True,'rows':result,
            'limit':50 if tool=='memory' else 1 if tool in ('artifact','report') else 100}
    finally:
        db.close()
