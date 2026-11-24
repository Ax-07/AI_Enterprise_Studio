"""Bounded deterministic verification. Never execute generated code in the host process."""
import csv, decimal, hashlib, io, json, math, os, re, subprocess, tempfile, threading, uuid
from pathlib import Path

IMAGE='aes-verifier:0.3.0'
MAX_BYTES=24000
_LOCK=threading.Lock()
LIMIT='Résultat limité aux assertions fournies; aucune validation commerciale ou sécurité générale.'

def decode(s):
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

def number(v):
    if not isinstance(v,str) or not re.fullmatch(r'[+-]?\d{1,14}(?:\.\d{1,8})?',v): raise ValueError('Décimal invalide (chaîne, point décimal)')
    return decimal.Decimal(v)

def same(a,b):
    # Distinguish booleans from numbers; avoid Python bool/int equivalence.
    return json.dumps(a,sort_keys=True,ensure_ascii=False)==json.dumps(b,sort_keys=True,ensure_ascii=False)

def pointer(data,path):
    if not isinstance(path,list) or len(path)>12: raise ValueError('Chemin JSON invalide')
    for k in path:
        if isinstance(data,dict) and isinstance(k,str): data=data[k]
        elif isinstance(data,list) and type(k) is int and 0<=k<len(data): data=data[k]
        else: raise ValueError('Chemin JSON inaccessible')
    return data

def data_results(name,content,spec):
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

def html_spec(spec):
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

def docker_command(config_dir,name):
    host='npipe:////./pipe/docker_engine' if os.name=='nt' else 'unix:///var/run/docker.sock'
    base=['docker','--config',config_dir,'--host',host]
    run=base+['run','--rm','--pull=never','--name',name,'--network=none','--read-only',
              '--cap-drop=ALL','--security-opt=no-new-privileges','--user=1000:1000',
              '--pids-limit=128','--memory=768m','--memory-swap=768m','--cpus=1.5',
              '--shm-size=128m','--tmpfs=/tmp:rw,nosuid,nodev,size=192m,mode=1777',
              '--log-driver=none','--init','-i','--env=HOME=/tmp',
              '--env=PYTHONDONTWRITEBYTECODE=1',IMAGE]
    return base,run

def browser_results(content,cases):
    if not _LOCK.acquire(blocking=False): raise RuntimeError('Un test HTML est déjà en cours')
    try:
        with tempfile.TemporaryDirectory() as directory:
            name='aes-test-'+uuid.uuid4().hex
            base,command=docker_command(directory,name)
            proc=None
            output=bytearray();overflow=threading.Event()
            try:
                proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
                payload=json.dumps({'html':content,'cases':cases},ensure_ascii=False).encode('utf-8')
                def write():
                    try:
                        proc.stdin.write(payload);proc.stdin.close()
                    except (OSError,ValueError): pass
                def read():
                    try:
                        while True:
                            chunk=proc.stdout.read(4096)
                            if not chunk: break
                            if len(output)+len(chunk)>64000:
                                overflow.set();proc.kill();break
                            output.extend(chunk)
                    except OSError: pass
                writer=threading.Thread(target=write,daemon=True);reader=threading.Thread(target=read,daemon=True)
                writer.start();reader.start()
                proc.wait(timeout=60)
                reader.join(timeout=2);writer.join(timeout=2)
                if overflow.is_set() or reader.is_alive() or proc.returncode!=0: raise RuntimeError('Bac à sable indisponible ou limite dépassée')
                result=decode(output.decode('utf-8'))
                if not isinstance(result,list) or len(result)!=len(cases): raise RuntimeError('Résultat navigateur invalide')
                for case,r in zip(cases,result):
                    if not isinstance(r,dict) or r.get('name')!=case['name'] or type(r.get('passed')) is not bool: raise RuntimeError('Résultat navigateur invalide')
                return result
            except (OSError,subprocess.TimeoutExpired,UnicodeError,ValueError) as e:
                raise RuntimeError('Docker local/image requis, ou limite de temps dépassée') from e
            finally:
                if proc is not None:
                    if proc.poll() is None:
                        proc.kill()
                        try:proc.wait(timeout=3)
                        except subprocess.TimeoutExpired:pass
                    if proc.returncode!=0 or overflow.is_set():
                        try: subprocess.run(base+['rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8)
                        except (OSError,subprocess.TimeoutExpired):pass
                    for pipe in (proc.stdin,proc.stdout):
                        if pipe and not pipe.closed:pipe.close()
    finally: _LOCK.release()

def run(name,content,raw_spec,html_enabled=False):
    kind=name.rsplit('.',1)[-1].lower()
    result={'kind':kind,'sha256':hashlib.sha256(content.encode('utf-8')).hexdigest(),'status':'invalid','checks':[],'limit':LIMIT}
    try:
        if len(content.encode('utf-8'))>MAX_BYTES or len(raw_spec.encode('utf-8'))>MAX_BYTES: raise ValueError('Fichier ou scénario trop volumineux')
        spec=decode(raw_spec)
        if not isinstance(spec,dict): raise ValueError('Spécification JSON objet requise')
        if kind in ('csv','json'):
            checks=data_results(name,content,spec)
        elif kind=='html':
            cases=html_spec(spec)
            if not html_enabled:
                return {**result,'status':'unavailable','error':'Bac à sable HTML non activé par le propriétaire'}
            checks=browser_results(content,cases)
        else: return {**result,'status':'unavailable','error':'Format non pris en charge : CSV, JSON ou HTML uniquement'}
        return {**result,'checks':checks,'status':'passed' if checks and all(c['passed'] for c in checks) else 'failed'}
    except RuntimeError as e: return {**result,'status':'unavailable','error':str(e)[:250]}
    except (ValueError,TypeError,KeyError,IndexError,csv.Error,RecursionError,decimal.DecimalException) as e:
        return {**result,'error':str(e)[:250]}

def shopify_spec():
    # Fixed independent expectations. No data from the product is used as the oracle.
    fixture='Payout Date,Payout ID,Type,Amount,Fee,Net,Currency\n2025-01-15,10001,charge,100.00,3.00,97.00,EUR\n2025-01-15,10002,charge,50.00,1.00,49.00,EUR\n2025-01-15,10001,refund,-20.00,0.00,-20.00,EUR\n2025-01-15,,charge,70.00,2.00,68.00,EUR\n'
    def step(op,selector,value=None):
        d={'op':op,'selector':selector}
        if value is not None:d['value']=value
        return d
    return {'cases':[
        {'name':'Exemple intégré EUR et USD','steps':[step('click','#columns'),step('click','#run'),step('contains','#out','137.00'),step('contains','#out','-3.00'),step('contains','#out','28.00')]},
        {'name':'Identifiant prioritaire sur date','steps':[step('fill','#csv',fixture),step('click','#columns'),step('value_equals','#key','2')]},
        {'name':'Versement isolé, frais non redéduits','steps':[step('fill','#csv',fixture),step('click','#columns'),step('select','#key','2'),step('fill','#value','10001'),step('fill','#expected','EUR=77.00'),step('click','#run'),step('contains','#out','net 77.00'),step('contains','#out','difference 0.00')]},
        {'name':'Changement de colonnes invalide le mapping','steps':[step('fill','#csv','Payout ID,Type,Net,Currency\n10001,charge,97.00,EUR'),step('click','#columns'),step('fill','#value','10001'),step('fill','#expected','EUR=97.00'),step('fill','#csv','Payout ID,Type,Fee,Currency,Net\n10001,charge,3.00,EUR,97.00'),step('click','#run'),step('contains','#out','Erreur')]}
    ]}
