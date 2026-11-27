"""Bounded deterministic verification. Never execute generated code in the host process."""
import csv, decimal, hashlib, io, json, math, os, re, subprocess, tempfile, threading, uuid
from pathlib import Path
from departments import functional_checks

IMAGE='aes-verifier:0.3.0'
MAX_BYTES=24000
_LOCK=threading.Lock()
LIMIT='Résultat limité aux assertions fournies; aucune validation commerciale ou sécurité générale.'

def decode(s):
    return functional_checks.decode(s,json=json,math=math)

def integer(v,lo,hi):
    return functional_checks.integer(v,lo,hi)

def string(v,limit=500):
    return functional_checks.string(v,limit)

def number(v):
    return functional_checks.number(v,re=re,decimal=decimal)

def same(a,b):
    return functional_checks.same(a,b,json=json)

def pointer(data,path):
    return functional_checks.pointer(data,path)

def data_results(name,content,spec):
    return functional_checks.data_results(name,content,spec,csv=csv,io=io,decimal=decimal,json=json,decode=decode,string=string,number=number,integer=integer,pointer=pointer,same=same)

def html_spec(spec):
    return functional_checks.html_spec(spec,string=string,re=re)

def docker_command(config_dir,name,image=IMAGE):
    host='npipe:////./pipe/docker_engine' if os.name=='nt' else 'unix:///var/run/docker.sock'
    base=['docker','--config',config_dir,'--host',host]
    run=base+['run','--rm','--pull=never','--name',name,'--network=none','--read-only',
              '--cap-drop=ALL','--security-opt=no-new-privileges','--user=1000:1000',
              '--pids-limit=128','--memory=768m','--memory-swap=768m','--cpus=1.5',
              '--shm-size=128m','--tmpfs=/tmp:rw,nosuid,nodev,size=192m,mode=1777',
              '--log-driver=none','--init','-i','--env=HOME=/tmp',
              '--env=PYTHONDONTWRITEBYTECODE=1',image]
    return base,run

def browser_results(content,cases,image=IMAGE,mode=None):
    if not _LOCK.acquire(blocking=False): raise RuntimeError('Un test HTML est déjà en cours')
    try:
        with tempfile.TemporaryDirectory() as directory:
            name='aes-test-'+uuid.uuid4().hex
            base,command=docker_command(directory,name,image)
            proc=None
            output=bytearray();overflow=threading.Event()
            try:
                proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
                payload=json.dumps({'html':content,'cases':cases,**({'mode':mode} if mode else {})},ensure_ascii=False,separators=(',',':')).encode('utf-8')
                if len(payload)>160000:raise RuntimeError('Entrée navigateur trop volumineuse')
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
