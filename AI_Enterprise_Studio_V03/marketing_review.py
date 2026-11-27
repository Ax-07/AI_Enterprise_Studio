"""Independent deterministic verification of proposed marketing claims, not editorial/legal approval."""
import json
import business as b
import acquisition as ac
import laboratory as lab
import marketing_templates as templates
from departments import marketing_claims

LIMIT='Contrôle technique déterministe SENTINEL; pas de revue humaine, juridique ou autorisation de publication.'

def evidence(c,did):
    return marketing_claims.evidence(c,did,ac=ac,lab=lab,json=json,b=b)

def review(c,did,payload):
    return marketing_claims.review(c,did,payload,evidence=evidence,templates=templates,b=b,limit=LIMIT)
