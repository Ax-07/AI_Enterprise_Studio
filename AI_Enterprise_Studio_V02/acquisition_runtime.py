"""Managed TEST child process. No provider secrets, no public bind, no real activation."""
import os
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path

PORT=8765
MAX_STARTS=3
START_TIMEOUT=5
_lock=threading.RLock()
_managed=False
_process=None
_key=None
_attempts=0
_state='not_started'

def managed():
    return _managed

def runtime_key():
    with _lock:
        return _key if _process is not None and _process.poll() is None and _state=='ready' else None

def status():
    with _lock:
        return {'managed':_managed,'ready':runtime_key() is not None,'state':_state,
                'attempts':_attempts,'max_attempts':MAX_STARTS,'mode':'test','port':PORT}

def child_environment():
    # No inherited OpenAI, Brave, n8n, proxy, PYTHONPATH or other application secrets.
    names={'SYSTEMROOT','WINDIR','SYSTEMDRIVE','TEMP','TMP','TMPDIR'}
    return {k:v for k,v in os.environ.items() if k.upper() in names}

def _close(process):
    if process is None:return
    try:
        if process.stdin:process.stdin.close()
    except OSError:pass
    try:process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:process.wait(timeout=2)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2)
    finally:
        if process.stdout:process.stdout.close()

def _start(path):
    global _process,_key,_attempts,_state
    if _attempts>=MAX_STARTS:
        _state='retry_limit';return False
    _attempts+=1
    _state='starting'
    key=secrets.token_bytes(32)
    nonce=secrets.token_hex(16)
    path=Path(path).resolve()
    path.parent.mkdir(parents=True,exist_ok=True)
    process=None
    try:
        process=subprocess.Popen([sys.executable,'-I',str(Path(__file__).resolve().with_name('public_channel_http.py')),
                                  '--managed-test',str(path),nonce],
                                 stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                 env=child_environment(),cwd=str(path.parent))
        process.stdin.write(key.hex().encode('ascii')+b'\n');process.stdin.flush()
        received=[]
        def read_ready():
            try:received.append(process.stdout.readline(200))
            except (OSError,ValueError):pass
        thread=threading.Thread(target=read_ready,daemon=True);thread.start();thread.join(START_TIMEOUT)
        if thread.is_alive() or received!=[('READY '+nonce+'\n').encode()] or process.poll() is not None:
            raise RuntimeError('Child startup not confirmed')
        _process=process;_key=key;_state='ready'
        return True
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
        _close(process);_process=None;_key=None;_state='unavailable'
        return False

def start(path):
    global _managed
    with _lock:
        _managed=True
        if runtime_key() is not None:return True
        return _start(path)

def maintain(path,before_restart):
    """Do not resume old grants after a child failure. Callback must durably stop local links."""
    global _process,_key,_state
    with _lock:
        if not _managed or runtime_key() is not None:return
        _key=None
        _close(_process);_process=None
        if _attempts>=MAX_STARTS:_state='retry_limit';return
        before_restart()
        _start(path)

def stop():
    global _process,_key,_state
    with _lock:
        _key=None
        _close(_process);_process=None;_state='stopped'
