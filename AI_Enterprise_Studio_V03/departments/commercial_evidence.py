"""Read-only documentary signals scoped to commercial activities.
Exact excerpts are not verified demand or sales evidence.
"""

def proof(c,row,*,intel):
    p=intel.page_reference(c,row['mission'],row['page'])
    content=intel.decode(c.execute('SELECT content FROM fetched WHERE id=?',(row['page'],)).fetchone()[0])
    if row['quote'] not in content['texte'] or p!=intel.decode(row['proof']):raise ValueError('Citation ou empreinte modifiée')
    return p


def signals(c,pid,mid=None,limit=12,*,intel,research,proof):
    out=[]
    for row in c.execute("""SELECT s.* FROM commercial_signals s JOIN missions m ON m.id=s.mission
        WHERE s.project=? AND m.mode='cloud' AND (m.state='terminée' OR s.mission=?) AND (? IS NULL OR s.mission<=?)
        ORDER BY s.id DESC LIMIT ?""",(pid,mid,mid,mid,limit)):
        try: reference=proof(c,row)
        except (ValueError,TypeError,KeyError,AttributeError):continue
        excerpt=intel.decode(c.execute('SELECT content FROM fetched WHERE id=?',(row['page'],)).fetchone()[0])['texte']
        out.append({**{k:row[k] for k in ('id','mission','kind','quote','interpretation','created')},'proof':reference,'quality':research.excerpt_quality(excerpt)})
    return out


def signal(c,pid,sid,mid,*,proof):
    row=c.execute("""SELECT s.* FROM commercial_signals s JOIN missions m ON m.id=s.mission
        WHERE s.id=? AND s.project=? AND m.mode='cloud' AND (m.state='terminée' OR s.mission=?)""",(sid,pid,mid)).fetchone()
    if not row:raise ValueError('Signal de cette activité requis')
    return row,proof(c,row)
