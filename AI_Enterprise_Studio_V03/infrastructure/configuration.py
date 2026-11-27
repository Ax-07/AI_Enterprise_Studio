"""Configuration loading and validation; no engine import or network access."""
import json
import math
import os


def load_config(root, defaults, prices):
    p=root/'config.json'; cfg=json.loads(p.read_text(encoding='utf-8-sig')) if p.exists() else {}
    budget=float(cfg.get('openai_budget_usd',2)); limit=int(cfg.get('brave_max_searches',10))
    if not math.isfinite(budget) or not 0<=budget<=15 or not 0<=limit<=1000: raise ValueError('Budget invalide (0–15 USD ; 0–1000 recherches).')
    models={**defaults,**cfg.get('models',{})}
    if any(models[a] not in prices for a in defaults): raise ValueError('Modèle non autorisé dans config.json.')
    def bounded(name,default,lo,hi):
        v=int(cfg.get(name,default))
        if not lo<=v<=hi: raise ValueError('Paramètre hors limites : '+name)
        return v
    mission_budget=float(cfg.get('mission_budget_usd',0.75))
    if not math.isfinite(mission_budget) or not 0<mission_budget<=15: raise ValueError('Budget mission invalide')
    sandbox=cfg.get('html_sandbox_enabled',False)
    if type(sandbox) is not bool: raise ValueError('html_sandbox_enabled doit être true ou false')
    return {'html_sandbox_enabled':sandbox,'mission_budget':round(mission_budget*1e6),'call_limit':bounded('mission_max_calls',24,16,100),'task_limit':bounded('mission_max_tasks',8,5,30),'turn_limit':bounded('task_max_turns',10,5,30),'mission_search_limit':bounded('mission_max_searches',6,0,50),'page_limit':bounded('mission_max_pages',8,0,50),'key':os.getenv('OPENAI_API_KEY') or cfg.get('openai_api_key',''),'brave':os.getenv('BRAVE_API_KEY') or cfg.get('brave_api_key',''),'budget':round(budget*1e6),'limit':limit,'models':models}
