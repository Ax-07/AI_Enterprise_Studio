"""D01: static, non-operational design preview. No enterprise session or data."""
import json
import re
from pathlib import Path

CSP="default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

def read(root,route):
    directory=(Path(root)/'interface').resolve()
    files={'/campus':('index.html','text/html; charset=utf-8'),
           '/campus/design.css':('design.css','text/css; charset=utf-8'),
           '/campus/design.js':('design.js','text/javascript; charset=utf-8')}
    match=re.fullmatch(r'/campus/assets/([A-Za-z0-9_]+\.webp)',route)
    try:
        if match:
            name=match.group(1)
            manifest=json.loads((directory/'manifest.json').read_text(encoding='utf8'))
            if name not in manifest['assets']:return None
            relative,typ='assets/'+name,'image/webp'
        elif route in files:relative,typ=files[route]
        else:return None
        path=(directory/relative).resolve()
        if not path.is_relative_to(directory) or not path.is_file():return None
        return path.read_bytes(),typ
    except (OSError,ValueError,KeyError,TypeError):
        return None
