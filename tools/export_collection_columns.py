"""Export actual saved field names and evidence states without provider requests."""
import csv
import json
import sqlite3
import lzma
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / 'data' / 'collection-control'
config = json.loads((CONTROL / 'config.json').read_text(encoding='utf-8-sig'))
rows = []

def add(table, name, states='', note=''):
    rows.append({'table': table, 'column_name': name, 'saved_states': states, 'note': note})

with sqlite3.connect((Path(config['base_root'])/'market.sqlite').as_uri()+'?mode=ro', uri=True) as db:
    db.execute('PRAGMA query_only=ON')
    fields = db.execute('SELECT field_name, GROUP_CONCAT(DISTINCT status) FROM profile_fields GROUP BY field_name ORDER BY field_name').fetchall()
    for name, states in fields:
        note = 'Profile signal for its recorded stay context; not universal eligibility.' if name=='instant_book' else ''
        if states in ('null','missing'): note = 'Column retained; no populated value observed.'
        add('airbnb_listing_profile', name, states, note)
    cal = json.loads(db.execute('SELECT fields_json FROM calendar_days LIMIT 1').fetchone()[0])
    add('airbnb_daily_calendar', 'calendar_date', 'observed')
    for name in sorted(cal):
        add('airbnb_daily_calendar', name, 'per-row evidence state',
            'No validated daily amount collected.' if name in ('price','localPriceFormatted') else '')
    contexts = [json.loads(r[0]) for r in db.execute('SELECT context_json FROM observations')]
    for name in sorted(set().union(*(set(c) for c in contexts))):
        add('observation_context',name,'per-observation value','Null stays unknown.')
for name in ('provider','listing_id','first_seen','last_seen'):
    add('listing_identity', name)
for name in ('observation_id','capture_id','kind','captured_at','raw_sha256','normalized_sha256'):
    add('observation_evidence', name)
for name in ('field_name','status','value_json','source_json'):
    add('field_evidence', name, note='Observed, null and missing are distinct states.')
with sqlite3.connect((Path(config['hotel_root'])/'market.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
    db.execute('PRAGMA query_only=ON')
    for table in ('hotels','profile_versions','profile_observations','rates','occupancy_rules'):
        for row in db.execute('PRAGMA table_info('+table+')'):
            add('hotel_'+table,row[1],note='Saved schema does not establish complete coverage.')
    rate_fields=set()
    for codec,payload in db.execute('SELECT b.codec,b.payload FROM rates r JOIN blobs b ON b.sha=r.payload_sha'):
        if codec=='xz': rate_fields.update(json.loads(lzma.decompress(payload)))
    for name in sorted(rate_fields):
        add('hotel_rate_observation',name,'per-row evidence state',
            'Observed or approximate source amount; not automatically an all-in comparable quote.' if name in ('amount','approximate_amount','display_amount') else '')
with (CONTROL/'data-columns.csv').open('w',encoding='utf-8-sig',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=('table','column_name','saved_states','note'))
    writer.writeheader();writer.writerows(rows)
print(json.dumps({'export':str(CONTROL/'data-columns.csv'),'field_rows':len(rows)}))
