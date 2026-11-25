"""Disposable n8n instance. No user data, no external provider calls."""
import http.client,json,os,pathlib,secrets,subprocess,tempfile,time
import n8n_bridge as n

IMAGE='docker.n8n.io/n8nio/n8n:2.48.5'
def docker(*args,check=True):
    r=subprocess.run(['docker',*args],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=240)
    if check and r.returncode:
        # All credentials here are ephemeral CI-only; no raw logs or secret printed.
        raise RuntimeError('Docker '+args[0]+' failed (exit '+str(r.returncode)+')')
    return r
def main():
    suffix=secrets.token_hex(5);name='aes-n8n-ci-'+suffix;vol=name
    token=secrets.token_urlsafe(32)
    env=['-e','N8N_DIAGNOSTICS_ENABLED=false','-e','N8N_VERSION_NOTIFICATIONS_ENABLED=false',
         '-e','N8N_TEMPLATES_ENABLED=false','-e','N8N_SECURE_COOKIE=false',
         '-e','N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS=true','-e','N8N_BLOCK_ENV_ACCESS_IN_NODE=true']
    cred_id='AesCiHeader00001';workflow_ids=['AesCiHealth00001','AesCiMetrics0001']
    docker('pull',IMAGE);docker('volume','create',vol)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            path=pathlib.Path(tmp);path.chmod(0o755)
            credentials=[{'id':cred_id,'name':'AES CI','type':'httpHeaderAuth','data':{'name':'X-AES-Token','value':token}}]
            (path/'credentials.json').write_text(json.dumps(credentials),encoding='utf8')
            workflows=[]
            for wid,kind in zip(workflow_ids,['health','metrics']):
                w=json.loads(pathlib.Path('n8n/aes_'+kind+'.json').read_text(encoding='utf8'))
                w['id']=wid;w['nodes'][0]['credentials']={'httpHeaderAuth':{'id':cred_id,'name':'AES CI'}}
                workflows.append(w)
            (path/'workflows.json').write_text(json.dumps(workflows),encoding='utf8')
            mounts=['-v',vol+':/home/node/.n8n','-v',tmp+':/aes-import:ro']
            def cli(*args):docker('run','--rm','--network','none',*env,*mounts,IMAGE,*args)
            cli('import:credentials','--input=/aes-import/credentials.json')
            cli('import:workflow','--input=/aes-import/workflows.json')
        docker('run','-d','--name',name,*env,'-v',vol+':/home/node/.n8n','-p','127.0.0.1:5678:5678',IMAGE)
        for _ in range(60):
            conn=http.client.HTTPConnection('127.0.0.1',5678,timeout=2)
            try:
                conn.request('GET','/healthz/readiness');resp=conn.getresponse();resp.read()
                if resp.status==200:break
            except OSError:pass
            finally:conn.close()
            time.sleep(1)
        else:raise RuntimeError('n8n not ready')
        for wid in workflow_ids:
            pub=docker('exec','-u','node',name,'n8n','publish:workflow','--id='+wid)
            print(pub.stdout.replace(token,'[REDACTED]')[-1200:])
        # Startup health only describes DB readiness. The publication service registers routes asynchronously.
        # Probe with an intentionally incorrect secret, never replay a valid execution.
        for cap in (n.HEALTH,n.METRICS):
            registered=False
            for _ in range(40):
                conn=http.client.HTTPConnection('127.0.0.1',5678,timeout=2)
                try:
                    conn.request('POST',n.PATHS[cap],body='{}',headers={'Content-Type':'application/json','X-AES-Token':'invalid-ci-token'})
                    response=conn.getresponse();response.read(8193)
                    if response.status in (401,403):registered=True;break
                    if response.status!=404:raise RuntimeError('Unexpected unauthenticated webhook HTTP '+str(response.status))
                except OSError:pass
                finally:conn.close()
                time.sleep(1)
            if not registered:
                logs=docker('logs','--tail','35',name,check=False).stdout.replace(token,'[REDACTED]')
                print(logs[-6000:])
                raise RuntimeError('Published webhook not registered: '+cap)
        os.environ['AES_N8N_TOKEN']=token
        result=n.call(n.HEALTH,'{}',secrets.token_hex(16));assert result['result']=={'ready':True}
        result=n.call(n.METRICS,'{"values":[10,-3,7]}',secrets.token_hex(16));assert result['result']=={'count':3,'sum':14,'min':-3,'max':10}
        os.environ['AES_N8N_TOKEN']=secrets.token_urlsafe(32)
        try:n.call(n.HEALTH,'{}',secrets.token_hex(16))
        except n.Unconfirmed as e:assert str(e) in ('HTTP 401','HTTP 403'),str(e)
        else:raise AssertionError('Wrong credential accepted')
        print('n8n Docker: imported and published 2 workflows, authenticated real calls and wrong-token rejection')
    finally:
        os.environ.pop('AES_N8N_TOKEN',None)
        docker('rm','-f',name,check=False);docker('volume','rm',vol,check=False)
if __name__=='__main__':main()
