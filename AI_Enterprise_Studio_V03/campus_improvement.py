"""Bounded read-only evidence of product improvement; not agent training."""
import campus_quality
import improvement
import verification

STATES=('pending','abandoned','retained','retained_manual','review','rejected')
def read(db):
    counts=[{'state':s,'count':n} for s,n in db.execute("SELECT state,COUNT(*) FROM improvement_cycles GROUP BY state") if s in STATES]
    out=[{'kind':'summary','counts':counts,'limit':improvement.LIMIT,
          'training_performed':False}]
    for r in db.execute("""SELECT cy.id,cy.campaign,cy.project,cy.baseline,cy.candidate,
        cy.profile,cy.state,cy.created,cy.baseline_sha,cy.candidate_sha,ref.artifact AS reference,
        CASE WHEN length(CAST(b.content AS BLOB))<=? THEN b.content END AS baseline_content,
        CASE WHEN length(CAST(a.content AS BLOB))<=? THEN a.content END AS candidate_content,
        CASE WHEN length(CAST(cy.result AS BLOB))<=? THEN cy.result END AS payload
        FROM improvement_cycles cy LEFT JOIN artifacts b ON b.id=cy.baseline
        LEFT JOIN artifacts a ON a.id=cy.candidate LEFT JOIN product_references ref ON ref.project=cy.project
        ORDER BY cy.id DESC LIMIT 50""",(verification.MAX_BYTES,verification.MAX_BYTES,campus_quality.DETAIL_LIMIT)):
        data=campus_quality.decode(r['payload'])
        replay=data.get('replays')
        statuses=[]
        if isinstance(replay,list) and len(replay)<=improvement.MAX_REPLAYS:
            for item in replay:
                if isinstance(item,dict) and type(item.get('proof')) is int and isinstance(item.get('result'),dict):
                    statuses.append({'proof':item['proof'],'status':campus_quality.status_of(item['result'])})
        lab=data.get('laboratory')
        non_regression=lab.get('non_regression') if isinstance(lab,dict) else None
        feature=data.get('feature')
        feature=feature if isinstance(feature,dict) else {}
        def status(key):
            v=feature.get(key)
            return campus_quality.status_of(v) if isinstance(v,dict) else None
        out.append({'kind':'cycle',**{k:r[k] for k in ('id','campaign','project','baseline','candidate','created','reference')},
            'profile':r['profile'] if r['profile'] in ('generic',improvement.CSV_PROFILE) else 'unknown',
            'state':r['state'] if r['state'] in STATES else 'unknown',
            'baseline_identity':campus_quality.identity(r['baseline_content'],r['baseline_sha']),
            'candidate_identity':campus_quality.identity(r['candidate_content'],r['candidate_sha']),
            'replays':statuses,'non_regression':non_regression if type(non_regression) is bool else None,
            'feature_before':status('baseline'),'feature_after':status('candidate')})
    return out
