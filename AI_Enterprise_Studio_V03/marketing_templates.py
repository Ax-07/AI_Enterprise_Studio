"""Versioned, constrained French marketing copy. No free-form agent text leaves the registry."""
from departments import marketing_content

REVISION=1
LIMIT='Brouillon de communication interne; aucune publication ni preuve de demande.'
PROFILE='catalogue-v1'

def render(price_cents,size,tp,fp,fn):
    return marketing_content.render(price_cents,size,tp,fp,fn)
