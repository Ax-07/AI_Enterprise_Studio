"""Deterministic functional assertions; no browser, process or network access.
The caller owns the authorization, size bounds and execution of HTML cases.
"""

def decode(s,*,json,math):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d: raise ValueError('Clé JSON dupliquée')
            d[k]=v
        return d
    def invalid(x): raise ValueError('Nombre JSON non fini')
    def finite(x):
        v=float(x)
        if not math.isfinite(v): raise ValueError('Nombre JSON non fini')
        return v
    return json.loads(s,object_pairs_hook=pairs,parse_constant=invalid,parse_float=finite)


def integer(v,lo,hi):
    if type(v) is not int or not lo<=v<=hi: raise ValueError('Entier hors limites')
    return v


def string(v,limit=500):
    if not isinstance(v,str) or len(v)>limit: raise ValueError('Texte invalide ou trop long')
    return v


def number(v,*,re,decimal):
    if not isinstance(v,str) or not re.fullmatch(r'[+-]?\d{1,14}(?:\.\d{1,8})?',v): raise ValueError('Décimal invalide (chaîne, point décimal)')
    return decimal.Decimal(v)


def same(a,b,*,json):
    # Distinguish booleans from numbers; avoid Python bool/int equivalence.
    return json.dumps(a,sort_keys=True,ensure_ascii=False)==json.dumps(b,sort_keys=True,ensure_ascii=False)


def pointer(data,path):
    if not isinstance(path,list) or len(path)>12: raise ValueError('Chemin JSON invalide')
    for k in path:
        if isinstance(data,dict) and isinstance(k,str): data=data[k]
        elif isinstance(data,list) and type(k) is int and 0<=k<len(data): data=data[k]
        else: raise ValueError('Chemin JSON inaccessible')
    return data


def data_results(name,content,spec,*,csv,io,decimal,json,decode,string,number,integer,pointer,same):
    checks=spec.get('checks')
    if not isinstance(checks,list) or not 1<=len(checks)<=20: raise ValueError('1 à 20 assertions requises')
    csv_mode=name.lower().endswith('.csv')
    if csv_mode:
        sep=spec.get('delimiter',',')
        if sep not in (',',';','\t'): raise ValueError('Séparateur CSV invalide')
        rows=list(csv.reader(io.StringIO(content.lstrip('\ufeff')),delimiter=sep,strict=True))
        if not rows or not rows[0] or any(not k for k in rows[0]) or len(set(rows[0]))!=len(rows[0]): raise ValueError('En-têtes CSV invalides')
        headers=rows[0]
        if any(len(r)!=len(headers) for r in rows[1:]): raise ValueError('Largeur CSV incohérente')
        records=[dict(zip(headers,r)) for r in rows[1:]]
    else: data=decode(content)
    out=[]
    for i,c in enumerate(checks,1):
        if not isinstance(c,dict): raise ValueError('Assertion non objet')
        label=string(c.get('name','Assertion '+str(i)),100); op=c.get('op')
        try:
            expected=c.get('expected')
            if csv_mode:
                where=c.get('where',{})
                if not isinstance(where,dict) or any(k not in headers or not isinstance(v,str) for k,v in where.items()): raise ValueError('Filtre CSV invalide')
                selected=[r for r in records if all(r[k]==v for k,v in where.items())]
                if op=='columns': actual=headers
                elif op=='row_count': actual=len(selected)
                elif op in ('sum','unique','cell'):
                    col=c.get('column')
                    if col not in headers: raise ValueError('Colonne absente')
                    values=[r[col] for r in selected]
                    if op=='sum':
                        if not values: raise ValueError('Aucune ligne sélectionnée')
                        actual=format(sum((number(v) for v in values),decimal.Decimal(0)),'f')
                        passed=number(actual)==number(expected)
                    elif op=='unique': actual=bool(values) and len(set(values))==len(values)
                    else: actual=values[integer(c.get('row'),0,max(0,len(values)-1))]
                else: raise ValueError('Opération CSV inconnue')
            else:
                value=pointer(data,c.get('path',[]))
                if op=='equals': actual=value
                elif op=='length' and isinstance(value,(list,dict,str)): actual=len(value)
                else: raise ValueError('Opération JSON inconnue')
            if op!='sum': passed=same(actual,expected)
            out.append({'name':label,'passed':passed,'actual':json.dumps(actual,ensure_ascii=False)[:250],'expected':json.dumps(expected,ensure_ascii=False)[:250]})
        except (ValueError,TypeError,KeyError,IndexError,decimal.DecimalException) as e:
            out.append({'name':label,'passed':False,'error':str(e)[:200]})
    return out


def html_spec(spec,*,string,re):
    cases=spec.get('cases')
    if not isinstance(cases,list) or not 1<=len(cases)<=4: raise ValueError('1 à 4 cas HTML requis')
    for case in cases:
        if not isinstance(case,dict): raise ValueError('Cas HTML invalide')
        string(case.get('name'),100)
        steps=case.get('steps')
        if not isinstance(steps,list) or not 1<=len(steps)<=12: raise ValueError('1 à 12 étapes par cas')
        assertions=0
        for step in steps:
            if not isinstance(step,dict): raise ValueError('Étape invalide')
            op=step.get('op'); selector=string(step.get('selector'),160)
            if not selector or '>>' in selector or not re.fullmatch(r'[#.a-zA-Z0-9_ :\[\]="\'\-\(\),+~*>]+',selector): raise ValueError('Sélecteur CSS simple requis')
            if op in ('fill','select','contains','text_equals','value_equals','upload'):
                string(step.get('value'),12000 if op=='upload' else 2000)
            elif op not in ('click','visible'): raise ValueError('Action HTML non autorisée')
            if op in ('contains','text_equals','value_equals','visible'): assertions+=1
        if not assertions: raise ValueError('Chaque cas doit contenir une assertion')
    return cases
