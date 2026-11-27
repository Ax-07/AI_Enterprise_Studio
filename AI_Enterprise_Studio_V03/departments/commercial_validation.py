"""Strict historical commercial and owner-registry input contracts.
No database, external actions or permission grants.
"""

def obj(text,fields,*,intel):
    if not isinstance(text,str) or len(text)>10000:raise ValueError('JSON commercial trop long')
    d=intel.decode(text)
    if not isinstance(d,dict) or set(d)!=set(fields):raise ValueError('Champs requis : '+', '.join(fields))
    return d


def text(d,k,lo=3,hi=1200):
    if not isinstance(d[k],str):raise ValueError(f'Texte invalide : {k}; chaîne JSON de {lo} à {hi} caractères requise, type reçu {type(d[k]).__name__}')
    n=len(d[k].strip())
    if not lo<=n<=hi:raise ValueError(f'Texte invalide : {k}; {n} caractères reçus, {lo} à {hi} requis; raccourcir sans perdre les risques essentiels')


def bounded_field(d,k,lo,hi):
    if type(d[k]) is not int or not lo<=d[k]<=hi:raise ValueError(f'Valeur invalide : {k}; entier JSON de {lo} à {hi} requis')


def numeric_id(target):
    if not target.isascii() or not target.isdigit() or len(target)>12 or int(target)<=0:raise ValueError('ID numérique requis')
    return int(target)


def fields(b,keys):
    if not isinstance(b,dict) or set(b)!=set(keys)|{'confirm'} or b.get('confirm') is not True:
        raise ValueError('Confirmation explicite et champs exacts requis')


def integer(v,lo=1,hi=9007199254740991):
    if type(v) is not int or not lo<=v<=hi:raise ValueError('Entier hors limites')
    return v


def opaque(v,*,re,hashlib):
    if not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,80}',v):raise ValueError('Référence opaque de 16–80 caractères (lettres, chiffres, tiret, underscore); jamais nom, email, clé ou numéro de carte')
    # Store only digests, not the original reference. Pseudonymization is not anonymization.
    return hashlib.sha256(v.encode()).hexdigest()
