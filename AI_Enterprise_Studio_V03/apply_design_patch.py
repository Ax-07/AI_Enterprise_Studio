"""Offline, file-only Design 22.6 preview patch. Python 3.11+; no engine import."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import tempfile

SCHEMA='aes.design.patch.v1'
FILES=('serveur.py','campus_preview.py','campus_live.py','preview_campus.py','LANCER_DESIGN.bat',
       'interface/live.js','interface/live-art.js','interface/live.html',
       'interface/original.html','interface/original.css','interface/original-office.js',
       'interface/original-rooms.js')
BASE='f97478171bc865fdfa156b25090cc5a61e3615e6'
PACKAGE=Path(__file__).resolve().parent

def digest(path):
    if path.is_symlink():raise ValueError('Lien symbolique interdit : '+path.name)
    if not path.exists():return None
    if not path.is_file():raise ValueError('Fichier attendu : '+path.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()

def checked(root,name):
    if name not in FILES:raise ValueError('Fichier non autorisé')
    path=root/name
    for q in (path,*path.parents):
        if q==root:break
        if q.is_symlink() or (hasattr(q,'is_junction') and q.is_junction()):
            raise ValueError('Lien ou jonction interdit : '+name)
        if q!=path and not q.is_dir():raise ValueError('Dossier absent : '+name)
    return path

def offline():
    for port in (8790,8765):
        with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
            sock.settimeout(.5)
            if sock.connect_ex(('127.0.0.1',port))==0:raise ValueError('Arrête les serveurs locaux avant toute modification.')

def load_manifest(package):
    m=json.loads((package/'PATCH.json').read_text(encoding='utf8'))
    if m.get('schema')!=SCHEMA or m.get('base')!=BASE or set(m.get('files',{}))!=set(FILES):
        raise ValueError('Manifeste incompatible')
    for name,entry in m['files'].items():
        if set(entry)!= {'before','after'}:raise ValueError('Manifeste invalide')
        for k in ('before','after'):
            v=entry[k]
            if k=='before' and v is None:continue
            if not isinstance(v,str) or len(v)!=64 or any(c not in '0123456789abcdef' for c in v):
                raise ValueError('Empreinte invalide')
        if digest(checked(package/'payload',name))!=entry['after']:raise ValueError('Paquet altéré : '+name)
    return m

def put(src,dst):
    fd,tmp=tempfile.mkstemp(prefix='.aes-design-',dir=dst.parent)
    os.close(fd)
    try:
        shutil.copy2(src,tmp)
        os.replace(tmp,dst)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def restore(root,backup,m):
    # Accept a partially applied patch after interruption, never overwrite unrelated edits.
    if json.loads((backup/'PATCH.json').read_text(encoding='utf8'))!=m:raise ValueError('Sauvegarde incompatible')
    for name,e in m['files'].items():
        if digest(checked(root,name)) not in (e['before'],e['after']):raise ValueError('Fichier modifié depuis la mise à jour : '+name)
        if e['before'] is not None and digest(checked(backup/'files',name))!=e['before']:raise ValueError('Sauvegarde altérée : '+name)
    offline()
    for name,e in m['files'].items():
        dst=checked(root,name)
        if e['before'] is None:
            if dst.exists():dst.unlink()
        else:put(checked(backup/'files',name),dst)
    if any(digest(checked(root,n))!=e['before'] for n,e in m['files'].items()):raise ValueError('Restauration incomplète')
    return {'restored':True,'files':len(FILES),'data_touched':False}

def apply(target,package=PACKAGE,*,confirmed=False,rollback=False):
    if not confirmed:raise ValueError('Confirme l’arrêt de tous les serveurs avec --confirm-offline.')
    root=Path(target).resolve();package=Path(package).resolve()
    if not root.is_dir() or not (root/'PREPARATION.json').is_file() or not (root/'donnees'/'enterprise.sqlite3').is_file():
        raise ValueError('Choisis ton dossier V03 déjà préparé.')
    if root==package or root in package.parents or package in root.parents:raise ValueError('Extrais le correctif dans un dossier séparé.')
    backup=root.with_name(root.name+'-sauvegarde-design-F06')
    m=load_manifest(package);offline()
    if backup.is_symlink():raise ValueError('Sauvegarde symbolique interdite')
    if rollback:
        if not backup.is_dir():raise ValueError('Sauvegarde absente')
        return restore(root,backup,m)
    if backup.exists():raise ValueError('Sauvegarde déjà présente : aucun écrasement. Utilise --restore si nécessaire.')
    for name,e in m['files'].items():
        if digest(checked(root,name))!=e['before']:raise ValueError('Version ou modification locale incompatible : '+name)
    # Publish backup before the first replacement. Keep it even after rollback.
    with tempfile.TemporaryDirectory(prefix='.aes-design-backup-',dir=root.parent) as temp:
        saved=Path(temp)/'backup';(saved/'files'/'interface').mkdir(parents=True)
        for name,e in m['files'].items():
            if e['before'] is not None:
                shutil.copy2(checked(root,name),checked(saved/'files',name))
                if digest(checked(saved/'files',name))!=e['before']:raise ValueError('Copie de sauvegarde non conforme')
        (saved/'PATCH.json').write_text(json.dumps(m,indent=2),encoding='utf8')
        offline()
        if any(digest(checked(root,n))!=e['before'] for n,e in m['files'].items()):raise ValueError('Fichiers modifiés pendant la sauvegarde')
        if backup.exists():raise ValueError('Sauvegarde déjà présente')
        saved.rename(backup)
    try:
        for name in FILES:put(checked(package/'payload',name),checked(root,name))
        if any(digest(checked(root,n))!=e['after'] for n,e in m['files'].items()):raise ValueError('Contrôle final échoué')
    except BaseException:
        try:restore(root,backup,m)
        except BaseException:raise RuntimeError('Restauration automatique incomplète : conserve la sauvegarde et utilise --restore.')
        raise
    return {'schema':SCHEMA,'installed':True,'design':'3.0.1-preview','engine':'3.0.0','files':len(FILES),'data_touched':False,'started':False,'paid_calls':False,'backup':str(backup)}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--target',required=True)
    ap.add_argument('--confirm-offline',action='store_true')
    ap.add_argument('--restore',action='store_true')
    args=ap.parse_args()
    try:
        result=apply(args.target,confirmed=args.confirm_offline,rollback=args.restore)
    except (ValueError,OSError,RuntimeError) as e:
        print('Correctif refusé ou interrompu : '+str(e));return 1
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
