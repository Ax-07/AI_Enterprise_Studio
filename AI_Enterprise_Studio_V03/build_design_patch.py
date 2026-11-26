"""Build the narrow public-source patch from immutable Git blobs."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
from apply_design_patch import FILES,BASE,SCHEMA
ROOT=Path(__file__).resolve().parent
PREFIX='AI_Enterprise_Studio_V03/'
def git(*args):
    return subprocess.check_output(['git','-C',str(ROOT),*args])
def blob(ref,name):
    return git('show',ref+':'+PREFIX+name)
def build(dest):
    revision=git('rev-parse','HEAD').decode().strip()
    old=set(git('ls-tree','-r','--name-only',BASE).decode().splitlines())
    files={}
    def h(b):return hashlib.sha256(b).hexdigest()
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            data=blob(revision,name)
            files[name]={'before':h(blob(BASE,name)) if PREFIX+name in old else None,'after':h(data)}
            z.writestr('payload/'+name,data)
        z.writestr('PATCH.json',json.dumps({'schema':SCHEMA,'base':BASE,'commit':revision,'files':files},indent=2))
        for name in ('apply_design_patch.py','INSTALLATION_DESIGN.md'):
            z.writestr(name,blob(revision,name))
    print('SHA256 '+h(dest.read_bytes())+'  '+dest.name)
if __name__=='__main__':build(sys.argv[1])
