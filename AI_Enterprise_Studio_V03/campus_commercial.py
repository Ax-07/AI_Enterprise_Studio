"""D06.1: bounded commercial projections; existing evidence checks, never publication."""
import json
import business
import commercial
import acquisition
import acquisition_sync
import hermes_acquisition
import marketing

TOOLS=frozenset(('business','marketing','marketing_detail','hermes_detail','offer_detail'))
DETAILS=frozenset(('marketing_detail','hermes_detail','offer_detail'))
EXPECTED=(ValueError,TypeError,KeyError,AttributeError,RuntimeError,IndexError)

def read(db,tool,ident=None):
    def rows(sql,args=()):
        return [dict(r) for r in db.execute(sql,args)]
    if tool=='offer_detail':
        if not db.execute('SELECT 1 FROM commercial_offers WHERE id=?',(ident,)).fetchone():return []
        base={'kind':tool,'id':ident,'sale_authorized':False,'publication_authorized':False,'limit':business.LIMIT}
        try:
            v,eligible,gaps=business.gate(db,business.offer_row(db,ident))
            plan=v['plan']
            # Internal proposal only; never expose raw evidence, receipts or participant references.
            content={k:plan[k] for k in commercial.OFFER_TEXT+('price_cents','metric','sample_size','success_min','duration_days')}
            return [{**base,'state':v['state'],'project':v['project'],'mission':v['mission'],
                     'artifact':v['artifact'],'artifact_sha256':v['artifact_sha256'],'draft_eligible':eligible,
                     'gaps':gaps,'review':(v['review'] or {}).get('verdict'),
                     'review_gaps':(v['review'] or {}).get('gaps'),'content':content}]
        except EXPECTED:return [{**base,'state':'unavailable','content':None}]
    if tool in DETAILS:
        row=db.execute('SELECT id,offer FROM acquisition_drafts WHERE id=?',(ident,)).fetchone()
        if not row:return []
        base={'kind':tool,'id':ident,'offer':row['offer'],'publication_authorized':False}
        try:
            if tool=='marketing_detail':
                packet=marketing.packet(db,ident)
                p=packet['payload']
                # Only the deterministic, independently checked template content.
                content={k:p['content'][k] for k in ('landing','youtube','social','media_policy')}
                return [{**base,'state':'technical_pass','revision':p['revision'],'content':content,
                    'limit':p['limit'],'video_generated':False,'storyboard_seconds':sum(s['seconds'] for s in content['youtube']['storyboard'])}]
            p=hermes_acquisition.packet(db,ident)
            content={k:p[k] for k in ('title','offer_text','deliverables','audience_hypothesis','price_cents','limitations','risks','faq','next_action')}
            content['demo_status']=p['product_demo']['status']
            return [{**base,'state':'internal_ready','content':content,'limit':p['limit']}]
        except EXPECTED:
            return [{**base,'state':'unavailable','content':None}]
    if tool=='marketing':
        result=[]
        for row in db.execute("""SELECT d.*,p.title AS project_title,o.project,
                EXISTS(SELECT 1 FROM hermes_preparations h WHERE h.draft=d.id) AS hermes_saved,
                EXISTS(SELECT 1 FROM marketing_drafts m WHERE m.draft=d.id) AS marketing_saved
                FROM acquisition_drafts d JOIN commercial_offers o ON o.id=d.offer
                JOIN projects p ON p.id=o.project ORDER BY d.id DESC LIMIT 30"""):
            state=acquisition.state(db,row)
            # Presence is not approval: validate packet only on explicit detail request.
            result.append({'kind':'draft','id':row['id'],'offer':row['offer'],'project':row['project'],
                'title':row['project_title'],'state':state,'language':row['language'],'created':row['created'],
                'snapshot_sha256':row['snapshot_sha256'],
                'hermes_saved':bool(row['hermes_saved']),'marketing_saved':bool(row['marketing_saved']),
                'publication_authorized':False,'video_generated':False})
        return result
    result=[]
    totals={mode:{'gross_cents':0,'refunds_cents':0,'net_cents':0} for mode in ('test','owner_declared_live')}
    for row in rows("SELECT mode,kind,SUM(amount_cents) AS amount FROM business_receipts GROUP BY mode,kind"):
        if row['mode'] in totals and row['kind'] in ('payment','refund'):
            totals[row['mode']]['gross_cents' if row['kind']=='payment' else 'refunds_cents']=row['amount']
    for t in totals.values():t['net_cents']=t['gross_cents']-t['refunds_cents']
    result.append({'kind':'summary','currency':'EUR','totals':totals,
        'verified_live_available':False,'verified_live_cents':None,'sale_authorized':False,
        'test_configured':acquisition_sync.configured()})
    # Most recent completed offer per project; gate is the existing read-only eligibility evaluator.
    for row in db.execute("""SELECT o.*,p.title FROM commercial_offers o JOIN projects p ON p.id=o.project
        JOIN missions m ON m.id=o.mission WHERE m.state='terminée' AND o.id=(
        SELECT MAX(x.id) FROM commercial_offers x JOIN missions y ON y.id=x.mission
        WHERE x.project=o.project AND y.state='terminée') ORDER BY o.id DESC LIMIT 20"""):
        base={'kind':'offer','id':row['id'],'project':row['project'],'title':row['title'],'sale_authorized':False}
        try:
            v,eligible,gaps=business.gate(db,business.offer_row(db,row['id']))
            eco=v['economics']
            result.append({**base,'state':v['state'],'price_cents':v['plan']['price_cents'],
                'gaps':gaps,'review':(v['review'] or {}).get('verdict'),
                'monthly_result_hypothesis_cents':eco['result']['monthly_result_cents'] if eco else None,
                'draft_eligible':eligible,'snapshot_sha256':business.digest(business.frozen(v)),
                'observation_eligible':eligible and not bool(db.execute('SELECT 1 FROM business_trials WHERE offer=?',(row['id'],)).fetchone())})
        except EXPECTED:result.append({**base,'state':'unavailable'})
    t=business.now()
    for row in db.execute("SELECT * FROM business_trials ORDER BY id DESC LIMIT 20"):
        counts=db.execute("SELECT COUNT(*),COALESCE(SUM(outcome!='no_interest'),0) FROM business_observations WHERE trial=?",(row['id'],)).fetchone()
        result.append({'kind':'trial','id':row['id'],'offer':row['offer'],'state':business.trial_state(db,row,t),
            'stored_state':row['state'],'metric':row['metric'],'sample_size':row['sample_size'],'success_min':row['success_min'],
            'observations':counts[0],'positive':counts[1],'expires':row['expires']})
    for row in rows("SELECT page,draft,state,starts,expires,stop_requested,confirmed FROM acquisition_test_channels ORDER BY starts DESC,page LIMIT 20"):
        result.append({'kind':'channel',**row,'mode':'test','within_window':row['starts']<=t<row['expires'],
            'remaining_seconds':max(0,row['expires']-t)})
    for row in db.execute("SELECT * FROM acquisition_test_links ORDER BY starts DESC,page LIMIT 20"):
        state=acquisition_sync.state(db,row,t)
        fresh=state=='test_link' and row['last_export'] is not None and 0<=t-row['last_export']<=acquisition_sync.FRESHNESS
        signals=list(db.execute("SELECT kind,segment FROM acquisition_test_signals WHERE page=? AND observed>?",(row['page'],t-acquisition_sync.ch.RETENTION))) if fresh else []
        result.append({'kind':'test_link','page':row['page'],'draft':row['draft'],'state':state,
            'fresh':fresh,'last_export':row['last_export'],'test_signals':len(signals) if fresh else None,
            'qualified_test':sum(acquisition_sync.qualify(x['kind'],bool(x['segment'])) for x in signals) if fresh else None})
    return result
