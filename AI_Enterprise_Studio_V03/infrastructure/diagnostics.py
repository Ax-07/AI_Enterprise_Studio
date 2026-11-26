"""Existing diagnostic formats, without provider calls or new journal writes."""
import urllib.error


def transport_error(error):
    # Do not include exception messages, which may contain credentials or URLs.
    return 'HTTP '+str(error.code) if isinstance(error, urllib.error.HTTPError) else type(error).__name__


def token_detail(message, output_tokens, limit, reasoning_tokens):
    return f'{message} ; sortie {output_tokens}/{limit} tokens ; raisonnement {reasoning_tokens if reasoning_tokens is not None else "non communiqué"}'


def invalid_json(error):
    return f'JSON non décodable (ligne {error.lineno}, colonne {error.colno})'


def mission(c, mid):
    """Local authenticated diagnostic projection; existing excerpts can be private."""
    row=c.execute('SELECT * FROM missions WHERE id=?',(mid,)).fetchone()
    if not row: raise ValueError('Mission absente')
    events=[dict(r) for r in c.execute('SELECT id,task,agent,action,substr(args,1,600) AS args,substr(result,1,800) AS result,ok,created FROM events WHERE mission=? ORDER BY id DESC LIMIT 100',(mid,))]
    tasks=[dict(r) for r in c.execute('SELECT id,agent,state,turns FROM tasks WHERE mission=?',(mid,))]
    calls,cost=c.execute('SELECT COUNT(*),COALESCE(SUM(COALESCE(actual,reserved)),0) FROM ledger WHERE mission=?',(mid,)).fetchone()
    return {'mission':dict(row),'tasks':tasks,'events':events,'calls':calls,'estimated_usd':cost/1e6,'limit':'Extraits de journal local; vérifier avant partage.'}
