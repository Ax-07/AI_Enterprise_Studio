"""Read-only historical ledger aggregates in integer micro-USD.

Actual (including zero) takes precedence over reserved; missing actual retains
the reservation. Scope totals overlap: never sum global, mission and campaign.
The caller owns the transaction. No accounting writes or revenue claims.
"""


def global_total(c):
    return c.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM ledger').fetchone()[0]


def mission_totals(c,mid):
    return c.execute('SELECT COALESCE(SUM(COALESCE(actual,reserved)),0),COUNT(*) FROM ledger WHERE mission=?',(mid,)).fetchone()


def campaign_total(c,cid):
    return c.execute("""SELECT COALESCE(SUM(COALESCE(l.actual,l.reserved)),0) FROM ledger l
        JOIN campaign_missions cm ON cm.mission=l.mission WHERE cm.campaign=?""",(cid,)).fetchone()[0]
