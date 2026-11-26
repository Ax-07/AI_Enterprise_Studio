"""Task selection and mission-state transitions, extracted without policy changes.

Each helper owns precisely the database context previously owned by moteur.run.
No model calls, external transport, recovery scheduling or permission grants.
"""
 
def select_task(s,mid,cfg):
    with s.db() as c:
        if c.execute('SELECT state FROM missions WHERE id=?',(mid,)).fetchone()[0]!='en cours': return None
        # A parent is not runnable until its children finish. Failed tasks block, waiting tasks pause.
        row=c.execute("SELECT t.* FROM tasks t WHERE mission=? AND state='prête' AND NOT EXISTS(SELECT 1 FROM tasks child WHERE child.parent=t.id AND child.state!='terminée') ORDER BY CASE WHEN t.parent IS NULL THEN 1 ELSE 0 END,t.id LIMIT 1",(mid,)).fetchone()
        if not row:
            states={r[0] for r in c.execute('SELECT state FROM tasks WHERE mission=?',(mid,))}
            state='terminée' if states=={'terminée'} else 'en attente' if 'en attente' in states else 'bloquée'
            c.execute('UPDATE missions SET state=?,error=? WHERE id=? AND state=\'en cours\'',(state,'Décision du propriétaire requise.' if state=='en attente' else '' if state=='terminée' else 'Tâches non résolues.',mid));return
        t=dict(row)
        if t['turns']>=cfg['turn_limit']: raise RuntimeError('Plafond de tours atteint pour la tâche #'+str(t['id']))
        if c.execute('SELECT COUNT(*) FROM events WHERE mission=?',(mid,)).fetchone()[0]>=cfg['call_limit']: raise RuntimeError('Plafond d’actions de mission atteint')
        c.execute('UPDATE missions SET step=? WHERE id=?',(t['id'],mid))
    return t


def count_turn_if_running(s,mid,t):
    with s.db() as c:
        if c.execute('SELECT state FROM missions WHERE id=?',(mid,)).fetchone()[0]!='en cours': return False
        c.execute('UPDATE tasks SET turns=turns+1 WHERE id=?',(t['id'],))
    return True


def mark_blocked_if_running(s,mid,e):
    with s.db() as c:c.execute("UPDATE missions SET state='bloquée',error=? WHERE id=? AND state='en cours'",(str(e)[:500],mid))
