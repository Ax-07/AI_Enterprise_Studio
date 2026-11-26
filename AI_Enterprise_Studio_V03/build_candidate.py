"""Build a public-source-only candidate ZIP from tracked files; no local data."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parent
def build(dest):
    root=ROOT
    files=subprocess.check_output(['git','ls-files','-z','--','.'],cwd=root).decode('utf8').split('\0')
    revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    selected=[]
    for name in filter(None,files):
        rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts:raise ValueError('Chemin invalide')
        top=rel.parts[0]
        if len(rel.parts)==1:
            ok=rel.suffix in ('.py','.html','.md','.bat','.ps1','.sh') and not name.startswith(('test_','smoke_'))
        else:
            ok=top in ('interface','sandbox','n8n') and not any(x.startswith(('.env','.git')) or x=='__pycache__' for x in rel.parts) and rel.suffix not in ('.pyc','.db','.sqlite','.sqlite3','.pem','.key') and rel.name!='config.json'
        if ok:
            f=root/rel
            if f.is_symlink() or not f.is_file():raise ValueError('Fichier suivi invalide')
            selected.append(rel)
    required={'serveur.py','index.html','prepare_update.py','LANCER_CAMPUS.bat','LANCER_APERCU.bat','preview_campus.py','interface/live.html'}
    if not required.issubset({x.as_posix() for x in selected}):raise ValueError('Paquet incomplet')
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for f in sorted(selected):
            z.write(root/f,'AI_Enterprise_Studio_V03/'+f.as_posix())
        z.writestr('AI_Enterprise_Studio_V03/BUILD_INFO.json',json.dumps({'candidate':'V3.0.0','version':'3.0.0','phase':'D08.3','commit':revision,'contains_local_data':False},indent=2))
    print('SHA256 '+hashlib.sha256(dest.read_bytes()).hexdigest()+'  '+dest.name)
if __name__=='__main__':build(sys.argv[1])
