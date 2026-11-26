"""Offline, side-by-side upgrade: local copies only. Python 3.11+."""
from contextlib import closing
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parent
DB_NAME='enterprise.sqlite3'
# Records that must survive unchanged; old columns only. Recovery may change task/mission states.
PROTECTED={'missions':{'state','error'},'tasks':{'state'},'reports':set(),
           'artifacts':set(),'ledger':set(),'searches':set(),'requests':set(),
           'opportunities':set(),'events':set(),'rewards':set(),'business_receipts':set(),
           'business_observations':set(),'verification_results':set()}
def readonly(path):
    return sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=5)
def quote(name):
    return '"'+name.replace('"','""')+'"'
def integrity(path):
    with closing(readonly(path)) as db:
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
            raise ValueError('Intégrité SQLite non confirmée')
def fingerprint(path,columns=None):
    result={}
    with closing(readonly(path)) as db:
        names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name,excluded in PROTECTED.items():
            if name not in names:
                if columns and name in columns:raise ValueError('Table historique absente : '+name)
                continue
            if columns is not None and name not in columns:continue
            cols=columns[name]['columns'] if columns is not None else [r[1] for r in db.execute('PRAGMA table_info('+quote(name)+')') if r[1] not in excluded]
            if 'id' not in cols:raise ValueError('Identifiant historique absent : '+name)
            h=hashlib.sha256();count=0
            for row in db.execute('SELECT '+','.join(map(quote,cols))+' FROM '+quote(name)+' ORDER BY id'):
                # SQLite values are typed; BLOB encoding is lossless.
                encoded=json.dumps([{'blob':v.hex()} if isinstance(v,bytes) else v for v in row],ensure_ascii=False,separators=(',',':')).encode('utf8')
                h.update(len(encoded).to_bytes(8,'big'));h.update(encoded);count+=1
            result[name]={'columns':cols,'rows':count,'sha256':h.hexdigest()}
    return result
def clone_db(src,dst):
    deadline=time.monotonic()+60
    def progress(status,remaining,total):
        if time.monotonic()>deadline:raise TimeoutError('Sauvegarde SQLite trop longue')
    with closing(readonly(src)) as old,closing(sqlite3.connect(dst)) as new:
        old.backup(new,pages=128,progress=progress,sleep=.05)
    integrity(dst)
def assert_offline():
    # Additional local safety check, not proof that no other process has the database open.
    for port in (8790,8765):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
            sock.settimeout(.5)
            if sock.connect_ex(('127.0.0.1',port))==0:raise ValueError('Ferme les serveurs locaux avant la copie (port '+str(port)+')')
def copy_runtime(candidate,target):
    # Only known public code/assets; never carry a developer config, DB, or cache.
    for f in candidate.iterdir():
        if f.is_file() and not f.is_symlink() and (f.suffix in ('.py','.html','.md','.bat','.ps1','.sh') or f.name=='BUILD_INFO.json'):
            if not f.name.startswith(('test_','smoke_')):shutil.copy2(f,target/f.name)
    for name in ('interface','sandbox','n8n'):
        d=candidate/name
        if d.is_dir():
            if d.is_symlink() or any(x.is_symlink() for x in d.rglob('*')):raise ValueError('Lien symbolique non autorisé dans le paquet')
            shutil.copytree(d,target/name,ignore=shutil.ignore_patterns('__pycache__','*.pyc','.env*','config.json','*.sqlite3*','*.db','*.pem','*.key'))
    for name in ('serveur.py','index.html','preview_campus.py','LANCER_APERCU.bat','interface/live.html','interface/manifest.json'):
        if not (target/name).is_file():raise ValueError('Paquet incomplet : '+name)
def init_copy(target):
    script="""import sys, pathlib
def guard(event,args):
    if event in ('socket.connect','socket.getaddrinfo','subprocess.Popen','os.system','os.exec'):
        raise RuntimeError('Transport interdit pendant la préparation')
sys.addaudithook(guard)
sys.path.insert(0,sys.argv[1])
import serveur
serveur.init()
serveur.acquisition_restart_guard()
serveur.config()
"""
    env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','SYSTEMDRIVE','TEMP','TMP','TMPDIR','PATH')}
    r=subprocess.run([sys.executable,'-I','-c',script,str(target)],cwd=target,env=env,capture_output=True,timeout=120)
    # Never print subprocess output: it may contain user-controlled config values.
    if r.returncode:raise ValueError('Initialisation hors ligne échouée ; installation originale conservée')
def prepare(source,destination,candidate=ROOT,*,confirmed=False):
    if not confirmed:raise ValueError('Confirmation de l’arrêt de tous les serveurs requise')
    source=Path(source).resolve();destination=Path(destination).resolve();candidate=Path(candidate).resolve()
    if not source.is_dir() or not (source/'serveur.py').is_file():raise ValueError('Dossier source invalide')
    srcdb=source/'donnees'/DB_NAME
    if not srcdb.is_file() or srcdb.is_symlink():raise ValueError('Base historique absente ou lien symbolique')
    if not destination.parent.is_dir():raise ValueError('Le dossier parent de destination doit exister')
    backup=destination.with_name(destination.name+'-sauvegarde')
    for path in (destination,backup):
        if path.exists() or path.is_symlink() or path==source or source in path.parents or path==candidate or candidate in path.parents:
            raise ValueError('Destination et sauvegarde doivent être deux nouveaux dossiers indépendants')
    cfg=source/'config.json'
    if cfg.is_symlink():raise ValueError('Configuration symbolique non prise en charge')
    assert_offline()
    # Source directory is the original rollback copy. A separate, pre-migration snapshot is retained.
    with tempfile.TemporaryDirectory(prefix='.aes-update-',dir=destination.parent) as temp:
        stage=Path(temp)/'candidate';stage.mkdir()
        saved=Path(temp)/'backup';saved.mkdir(mode=0o700)
        (saved/'donnees').mkdir()
        clone_db(srcdb,saved/'donnees'/DB_NAME)
        before=fingerprint(saved/'donnees'/DB_NAME)
        if not {'missions','reports','ledger','searches','requests'}.issubset(before):
            raise ValueError('Base historique incompatible ou incomplète')
        if cfg.exists():shutil.copy2(cfg,saved/'config.json')
        copy_runtime(candidate,stage)
        (stage/'donnees').mkdir()
        clone_db(saved/'donnees'/DB_NAME,stage/'donnees'/DB_NAME)
        if cfg.exists():shutil.copy2(saved/'config.json',stage/'config.json')
        init_copy(stage)
        integrity(stage/'donnees'/DB_NAME)
        after=fingerprint(stage/'donnees'/DB_NAME,before)
        if before!=after:raise ValueError('Écart dans les écritures historiques protégées : arrêt de la préparation')
        if fingerprint(srcdb,before)!=before:raise ValueError('La base source a changé pendant la copie ; recommence après arrêt complet')
        if cfg.exists() and cfg.read_bytes()!=(saved/'config.json').read_bytes():raise ValueError('Configuration source modifiée pendant la copie')
        assert_offline()
        report={'schema':'aes.update.preflight.v1','integrity':'ok','protected_tables':{k:v['rows'] for k,v in before.items()},
                'source_unchanged':True,'started':False,'paid_calls':False,'configuration_copied':cfg.exists(),
                'extra_data_entries_not_copied':sum(1 for x in (source/'donnees').iterdir() if x.name not in (DB_NAME,DB_NAME+'-wal',DB_NAME+'-shm',DB_NAME+'-journal'))}
        (stage/'PREPARATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
        # Never replace an existing directory. Backup is published before candidate.
        if destination.exists() or backup.exists():raise ValueError('Destination apparue pendant la préparation')
        saved.rename(backup)
        stage.rename(destination)
    return report
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',required=True,type=Path)
    ap.add_argument('--destination',required=True,type=Path)
    ap.add_argument('--confirm-offline',action='store_true')
    args=ap.parse_args()
    try:
        result=prepare(args.source,args.destination,confirmed=args.confirm_offline)
    except (ValueError,OSError,sqlite3.Error,subprocess.SubprocessError) as exc:
        print('Préparation refusée : '+(str(exc) if isinstance(exc,ValueError) else type(exc).__name__),file=sys.stderr)
        return 1
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print('Préparation terminée, aucun serveur démarré. Conserve la sauvegarde locale.')
    return 0
if __name__=='__main__':sys.exit(main())
