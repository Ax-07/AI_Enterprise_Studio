"""Model response request and one corrective retry, using the existing service.

No direct provider access or budget handling: each call goes through s.call_model.
The caller owns schema selection, permissions and post-response execution guards.
"""

def request_action(s,mid,t,p,cfg,closing,campaign,schema,rules,validator):
    if closing: p+='\nDERNIER TOUR : seul finish est autorisé. Dépose un rapport honnête, même partiel; cite les preuves et les critères non atteints. Aucun autre outil.'
    maxout=2048 if closing else 8192 if t['agent']=='NEXUS' else 4096
    if campaign:
        p+='\nBUDGET ADAPTATIF : réponse JSON concise; ne répète pas la mémoire exacte ni le code déjà enregistré. Un petit rapport ou une délégation doit rester bref. Le moteur peut réduire le plafond de sortie pour respecter l’enveloppe; ne tronque jamais un fichier nécessaire.'
    try: v=s.call_model(mid,t['agent'],p,cfg,maxout,t['id'],schema=schema,rules=rules,validator=validator)
    except (s.TokenLimit,s.InvalidModelOutput) as e:
        # One corrective retry only, subject to the same cumulative and mission budgets.
        # No tool has been executed; retain every billed call and all prior task state.
        hint=('\nTentative de correction unique : la sortie précédente n’a pas été acceptée. '
              'Retourne un objet JSON valide avec exactement action, target, text, detail, tous de type chaîne. '
              'Utilise une seule action autorisée; champs inutilisés vides. Une lecture déjà présente dans FILE_PIN ou un rapport complet déjà lu est redondant et refusé; utilise la mémoire de travail ou finish. '
              'Si tu produis un fichier, choisis un fichier autonome compact (moins de 6000 caractères si possible). '
              'Ne renvoie ni Markdown autour du JSON, ni objet imbriqué, ni texte supplémentaire.')
        try: v=s.call_model(mid,t['agent'],p+hint,cfg,min(maxout*2,16384),t['id'],schema=schema,rules=rules,validator=validator)
        except (s.TokenLimit,s.InvalidModelOutput) as second:
            raise RuntimeError(f'{second} Correction unique épuisée; rapports et fichiers conservés.') from None
    return v
