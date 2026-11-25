"""Optional real public-source smoke, no paid API and no production DB."""
import json,ssl,socket
import intelligence as i
try:
    data=i.fetch('{"countries":["FRA","GBR","CAN"],"year":2023}')
except (OSError,RuntimeError) as e:
    print('World Bank live unavailable:',type(e).__name__,str(e) if isinstance(e,RuntimeError) and str(e).startswith('HTTP ') else '')
else:
    d=data['snapshot'];assert i.digest(d)==data['snapshot_sha256']
    assert d['year']==2023 and set(d['countries'])=={'FRA','GBR','CAN'}
    print('World Bank LIVE validated:',json.dumps({'url':data['url'],'retrieved':data['retrieved'],'observations':d['observations'],'sha256':data['snapshot_sha256']},ensure_ascii=False))
