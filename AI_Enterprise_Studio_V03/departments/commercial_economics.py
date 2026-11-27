"""Pure offer profitability projections in EUR cents, not observed revenue."""

def economics_result(plan,d):
    contribution=plan['price_cents']-d['variable_cost_cents']
    adverse=plan['price_cents']-(d['variable_cost_cents']*120+99)//100
    return {'contribution_cents':contribution,'monthly_result_cents':contribution*d['monthly_units']-d['fixed_month_cents'],
        'breakeven_units':(d['fixed_month_cents']+contribution-1)//contribution if contribution>0 else None,
        'adverse_monthly_result_cents':adverse*max(1,d['monthly_units']//2)-d['fixed_month_cents'],
        'classification':'hypothèses EUR, avant impôt et coûts initiaux non inclus'}


def adverse_parameters(plan,d):
    v=(d['variable_cost_cents']*120+99)//100;units=max(1,d['monthly_units']//2)
    return {'price_cents':plan['price_cents'],'variable_cost_cents':v,'monthly_units':units,'fixed_month_cents':d['fixed_month_cents'],'breakeven_units':(d['fixed_month_cents']+plan['price_cents']-v-1)//(plan['price_cents']-v) if plan['price_cents']>v else None,'rule':'Volume divisé par deux (arrondi inférieur, minimum 1); coût variable +20 % (arrondi supérieur au centime); prix et fixes inchangés.'}
