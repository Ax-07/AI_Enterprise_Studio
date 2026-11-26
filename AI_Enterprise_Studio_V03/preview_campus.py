"""Local first-look server: read-only campus, no worker, initialization or TEST service."""
import argparse
import webbrowser
import serveur as s

class PreviewHandler(s.Handler):
    def do_GET(self):
        if not self.local():return self.send({'error':'Hôte refusé'},403)
        route=self.route()
        if route=='/':
            self.send_response(302)
            self.send_header('Location','/campus/live/')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length','0')
            self.end_headers()
            return
        if route=='/api/health':
            return self.send({'application':'AI Enterprise Studio','version':s.VERSION,'mode':'preview_read_only','paid_call':False})
        if route=='/campus/live':
            if self.headers.get('Sec-Fetch-Site') not in (None,'none','same-origin'):
                return self.send({'error':'Accès local direct requis'},403)
            asset=s.campus_preview.read(s.ROOT,route)
            if asset is None:return self.missing()
            data,typ=asset
            data=data.replace(b'__CAMPUS_READ_SESSION__',s.CAMPUS_READ_SESSION.encode()).replace(b'__CAMPUS_COMMAND_SESSION__',b'').replace(b'__CAMPUS_OWNER_SESSION__',b'').replace(b'content="operational" name="campus-mode"',b'content="preview" name="campus-mode"')
            return self.send(data,typ=typ,csp=s.campus_preview.LIVE_CSP)
        if route=='/campus' or route.startswith('/campus/'):
            # Only the already isolated static assets and read-only GET projections.
            return super().do_GET()
        return self.send({'error':'Interface historique désactivée dans cet aperçu'},403)
    def do_POST(self):
        return self.send({'error':'Aperçu en lecture seule : commandes interdites'},403)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--no-browser',action='store_true')
    ap.add_argument('--original',action='store_true',help='Ouvrir le Design 22.6 connecté')
    args=ap.parse_args()
    if not s.DB.is_file() or not (s.ROOT/'PREPARATION.json').is_file():
        print('Prépare d’abord le dossier candidat avec prepare_update.py.')
        return 1
    try:server=s.ThreadingHTTPServer(('127.0.0.1',s.PORT),PreviewHandler)
    except OSError:
        print('Port local indisponible : ferme le serveur existant.')
        return 1
    url=f'http://127.0.0.1:{s.PORT}/campus/'+('original/' if args.original else 'live/')
    print('Aperçu en lecture seule : '+url,flush=True)
    print('Aucun worker, aucune commande, aucun service TEST démarré. Ctrl+C pour fermer.',flush=True)
    if not args.no_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0
if __name__=='__main__':raise SystemExit(main())
