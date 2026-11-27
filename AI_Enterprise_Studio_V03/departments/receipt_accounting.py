"""Historical EUR receipt aggregates; declared live is not verified revenue."""


def totals(receipts):
    totals={}
    for mode in ('test','owner_declared_live'):
        gross=sum(x['amount_cents'] for x in receipts if x['mode']==mode and x['kind']=='payment')
        refunds=sum(x['amount_cents'] for x in receipts if x['mode']==mode and x['kind']=='refund')
        totals[mode]={'gross_cents':gross,'refunds_cents':refunds,'net_cents':gross-refunds}
    return totals
