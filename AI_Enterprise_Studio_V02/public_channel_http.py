"""Loopback-only HTTP harness for the isolated TEST channel, not a production server."""
import html
import json
import hmac
import os
import re
import time
from http.cookies import SimpleCookie, CookieError
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server, WSGIRequestHandler
from contextlib import closing
import public_channel as ch

MAX_BODY=16000
CSP="default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"

def application(path,key,clock=None):
    clock=time.time if clock is None else clock
    auth=ch.sign(key,'admin-bearer-v1',{'service':'test-only'})
    with closing(ch.connect(path)) as c:ch.init(c)
    def app(env,start):
        def send(code,data,typ='application/json; charset=utf-8',extra=()):
            body=(ch.canonical(data) if isinstance(data,dict) else data).encode('utf8')
            start(code,[('Content-Type',typ),('Content-Length',str(len(body))),
                        ('Cache-Control','no-store'),('Content-Security-Policy',CSP),
                        ('Referrer-Policy','no-referrer'),('X-Content-Type-Options','nosniff'),
                        ('X-Robots-Tag','noindex, nofollow'),*extra])
            return [body]
        def fail(code):return send(code,{'error':'Request rejected'})
        def read():
            n=int(env.get('CONTENT_LENGTH') or '0')
            if not 1<=n<=MAX_BODY:raise ValueError('Invalid size')
            raw=env['wsgi.input'].read(n)
            if len(raw)!=n:raise ValueError('Truncated request')
            return raw.decode('utf8')
        def form():
            if env.get('CONTENT_TYPE','').split(';')[0]!='application/x-www-form-urlencoded':
                raise ValueError('Invalid content type')
            d=parse_qs(read(),keep_blank_values=True,strict_parsing=True,max_num_fields=8)
            if any(len(v)!=1 for v in d.values()):raise ValueError('Duplicate form field')
            return {k:v[0] for k,v in d.items()}
        def cookie_token():
            jar=SimpleCookie()
            try:jar.load(env.get('HTTP_COOKIE',''))
            except CookieError:return ''
            return jar['aes_test_participant'].value if 'aes_test_participant' in jar else ''
        e=lambda x:html.escape(str(x),quote=True)
        route=env.get('PATH_INFO','');method=env.get('REQUEST_METHOD','')
        host=env.get('HTTP_HOST','')
        if not re.fullmatch(r'(?:127\.0\.0\.1|localhost)(?::[0-9]{1,5})?',host):return fail('403 Forbidden')
        if method=='POST' and env.get('HTTP_ORIGIN') not in (None,'http://'+host):return fail('403 Forbidden')
        t=int(clock())
        try:
            with closing(ch.connect(path)) as c:
                c.execute('BEGIN IMMEDIATE')
                ch.purge(c,t)
                if route=='/health' and method=='GET':
                    c.commit();return send('200 OK',{'service':'aes-isolated-acquisition','mode':'test','live_enabled':False})
                if route.startswith('/admin/'):
                    if not hmac.compare_digest(env.get('HTTP_AUTHORIZATION',''),'Bearer '+auth):
                        c.rollback();return fail('403 Forbidden')
                    if method!='POST' or env.get('CONTENT_TYPE','').split(';')[0]!='application/json':
                        raise ValueError('Invalid admin request')
                    body=json.loads(read())
                    if route=='/admin/export':
                        ch.exact(body,('page',))
                        result=ch.export(c,key,body['page'],t)
                    else:
                        ch.exact(body,('payload','signature'))
                        fn={'/admin/publish':ch.publish,'/admin/collect':ch.authorize_collection,
                            '/admin/revoke':ch.revoke}.get(route)
                        if fn is None:raise ValueError('Unknown route')
                        result={'id':fn(c,key,body['payload'],body['signature'],t)}
                    c.commit();return send('200 OK',result)
                match=re.fullmatch(r'/p/([0-9a-f]{32})',route)
                if match:
                    pid=match.group(1)
                    p=ch.page(c,pid,t)
                    if method=='GET':
                        token=cookie_token()
                        try:ch._participant(key,pid,token)
                        except ValueError:token=ch.participant_token(key,pid)
                        body='<!doctype html><html lang="fr"><meta charset="utf-8"><title>Test interne</title><h1>'+e(p['title'])+'</h1><p>MODE TEST — aucune vente, aucun suivi commercial réel.</p><p>'+e(p['description'])+'</p><p>'+e(p['limitations'])+'</p><p>Prix indicatif : '+e(f"{p['price_cents']/100:.2f} EUR")+'</p>'
                        if p['collection_open']:
                            body+='<form method="post"><input type="hidden" name="token" value="'+e(token)+'"><label>Intention <select name="kind"><option value="interest">Intérêt</option><option value="demo_request">Démonstration</option><option value="purchase_question">Question achat</option></select></label><p><label><input type="checkbox" name="segment" value="yes">Je corresponds à la cible présentée</label></p><p><label><input type="checkbox" name="consent" value="yes" required>Je consens à ce test fictif sans coordonnées. Signal pseudonymisé effaçable avec le code fourni, purgé au prochain traitement après 7 jours.</label></p><button>Envoyer un signal de test</button></form>'
                        else:body+='<p>Collecte désactivée.</p>'
                        c.commit()
                        return send('200 OK',body,'text/html; charset=utf-8',
                            [('Set-Cookie','aes_test_participant='+token+'; Path='+route+'; HttpOnly; SameSite=Strict; Max-Age=86400')])
                    if method=='POST':
                        d=form()
                        if set(d) not in ({'kind','token','consent'},{'kind','token','consent','segment'}):
                            raise ValueError('Unexpected form fields')
                        if not hmac.compare_digest(d['token'],cookie_token()):
                            raise ValueError('Invalid form token')
                        if d['consent']!='yes' or d.get('segment','yes')!='yes':
                            raise ValueError('Invalid consent')
                        result=ch.record(c,key,pid,d['token'],{'kind':d['kind'],
                            'segment':'segment' in d,'consent':True,'notice':ch.NOTICE_VERSION},t)
                        c.commit()
                        body='<!doctype html><html lang="fr"><meta charset="utf-8"><title>Test reçu</title><h1>Signal de test reçu</h1><p>Conserve ces références pour effacer le signal avant expiration.</p><form action="/withdraw" method="post"><label>Signal <input name="id" value="'+e(result['id'])+'"></label><label>Code de retrait <input name="token" value="'+e(result['delete_token'])+'"></label><button>Effacer le signal</button></form>'
                        return send('200 OK',body,'text/html; charset=utf-8')
                if route=='/withdraw' and method=='POST':
                    d=form();ch.exact(d,('id','token'))
                    ok=ch.withdraw(c,d['id'],d['token']);c.commit()
                    return send('200 OK',{'withdrawn':ok})
                c.rollback();return fail('404 Not Found')
        except (ValueError,TypeError,KeyError,AttributeError,UnicodeError):
            return fail('400 Bad Request')
    return app

class QuietHandler(WSGIRequestHandler):
    def log_message(self,*args):pass

if __name__=='__main__':
    # No default secret, no default database, no external bind and no production mode.
    key=bytes.fromhex(os.environ['AES_CHANNEL_TEST_KEY_HEX'])
    path=os.environ['AES_CHANNEL_TEST_DB']
    if len(key)<32:raise ValueError('Test key too short')
    with make_server('127.0.0.1',8765,application(path,key),handler_class=QuietHandler) as server:
        server.serve_forever()
