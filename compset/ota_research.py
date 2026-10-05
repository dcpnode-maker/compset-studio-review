"""Import reviewed public tool captures and report honest 17-hotel coverage."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import date,timedelta,datetime,timezone
import json
from pathlib import Path

from .ota_tool_adapters import (VIO_BINDINGS,normalize_vio_calendar,normalize_vio_offers,normalize_expedia,sanitize_capture)
from .provider_queue import Queue
from .rate_policy import calendar_windows,comparable_minima,digest,instant
from .pipeline import _write_json,export_csv

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'data/research-pipelines/20260930'


def task(provider,method,hotel_id,provider_id,capture,*,calendar=False):
    start=capture['startDate'] if calendar else capture.get('checkIn') or capture['data'][0]['checkin_date']
    end=capture['endDate'] if calendar else start
    return {'provider':provider,'vertical':'hotel','method':method,'hotel_id':hotel_id,'provider_id':provider_id,
            'identity_verified':True,'start_date':start,'end_date':end,'currency':capture['currency'] if provider=='vio' else capture['data'][0]['currency'],
            'party':[{'adults':1,'children':[]}],'mode':'calendar' if calendar else 'detailed'}


def ingest(input_path,*,root=DEFAULT):
    raw=json.loads(Path(input_path).read_text(encoding='utf-8'))
    queue=Queue(root)
    outputs=[]
    def save(target,captured,normalize):
        captured=sanitize_capture(captured,target)
        normalize(captured,target)  # Validate the recovered receipt before changing durable state.
        ident=queue.plan(target)
        current=queue.get(ident)
        if current['state']=='claimed':
            # This explicit file import supplies the recovered receipt; no remote
            # request is repeated to repair an interrupted import.
            queue.capture(ident,captured)
            outputs.append(queue.interpret(ident,normalize,'ota-tool-contract.v1'))
            return
        # Exact repeated receipt is reparsed without another network request.
        if current['capture_json']:
            previous=json.loads(current['capture_json'])
            if previous['observed_at']==captured['observed_at']:
                if current['state'] in {'completed','captured'}:
                    outputs.append(queue.interpret(ident,normalize,'ota-tool-contract.v1'))
                return
            if instant(previous['observed_at'])>instant(captured['observed_at']): return
            queue.refresh(ident,force=True)
        if queue.claim(ident):
            queue.capture(ident,captured)
            outputs.append(queue.interpret(ident,normalize,'ota-tool-contract.v1'))
    for captured in raw.get('calendars',[]):
        provider_ids={r.get('hotelId') for r in captured.get('availability',[]) if isinstance(r,dict)}
        # An empty completed polling result is still saved for every explicitly
        # requested ID, without inventing zero-price or unavailable observations.
        ids=captured.get('requested_hotel_ids') or list(provider_ids)
        for hotel_id,provider_id in VIO_BINDINGS.items():
            if provider_id not in ids: continue
            split={**captured,'availability':[r for r in captured.get('availability',[]) if r.get('hotelId')==provider_id]}
            save(task('vio','connector_calendar',hotel_id,provider_id,split,calendar=True),split,normalize_vio_calendar)
    canary=raw.get('canary') or {}
    if canary.get('vio_offers'):
        captured={**canary['vio_offers'],'observed_at':canary['fetched_at']}
        save(task('vio','connector_offers','osm:node:11740798982','1659409',captured),captured,normalize_vio_offers)
    if canary.get('expedia',{}).get('data'):
        captured={**canary['expedia'],'observed_at':canary['fetched_at']}
        save(task('expedia','connector_display','osm:node:11740798982','92850456',captured),captured,normalize_expedia)
    return report(root)


def report(root=DEFAULT):
    root=Path(root);queue=Queue(root)
    base=json.loads((ROOT/'data/provider-receipts/20260930/aketa-provider-receipts.json').read_text())
    start=date.fromisoformat(base['start_date']);end=start+timedelta(days=364)
    with closing(queue.connect()) as db:
        jobs=[dict(r) for r in db.execute('SELECT * FROM provider_tasks')]
    rates=[]
    for job in jobs:
        if job['interpretation_json']:
            rates.extend(json.loads(job['interpretation_json']).get('rates',[]))
    unique={digest({k:v for k,v in r.items() if k!='freshness'}):r for r in rates}
    rates=list(unique.values())
    calendars=[r for r in rates if r['evidence_kind']=='calendar_indicative' and start<=date.fromisoformat(r['checkin'])<=end]
    coverage=[]
    for hotel in base['roster']:
        found={r['checkin'] for r in calendars if r['hotel_id']==hotel['id']}
        coverage.append({'hotel_id':hotel['id'],'name':hotel['name'],'annual_dates':365,
                         'vio_observed_dates':len(found),'vio_unknown_dates':365-len(found),
                         'identity_state':'reviewed' if hotel['id'] in VIO_BINDINGS else 'unresolved'})
    annual=set((r['hotel_id'],r['checkin']) for r in calendars)
    original=set((r['hotel_id'],r['checkin']) for r in base['rates']+base.get('direct_rates',[]))
    original.update(('osm:node:11740798982',r['checkin']) for r in base['google_saved']['rates'])
    detailed=[r for r in rates if r['evidence_kind']!='calendar_indicative']
    # Flag separate source views disagreeing; do not turn them into parity quotes.
    discrepancies=[]
    for direct in detailed:
        candidates=[r for r in calendars if r['hotel_id']==direct['hotel_id'] and r['source']==direct['source']
                    and r['checkin']==direct['checkin'] and r['currency']==direct['currency']
                    and r['price_scope']==direct['price_scope'] and r['taxes_included']==direct['taxes_included']]
        if candidates:
            from decimal import Decimal
            calendar=min(Decimal(r['amount']) for r in candidates)
            if calendar!=Decimal(direct['amount']):
                discrepancies.append({'hotel_id':direct['hotel_id'],'checkin':direct['checkin'],
                                      'calendar_amount':str(calendar),'offer_amount':direct['amount'],'currency':direct['currency'],
                                      'state':'unresolved_product_or_source_difference'})
    result={'schema':'ota-research-report.v1','updated_at':datetime.now(timezone.utc).isoformat(),
            'annual_start':str(start),'annual_end':str(end),'detailed_end':base['detailed_end_date'],
            'roster':base['roster'],'coverage':coverage,'rates':rates,'discrepancies':discrepancies,
            'summary':{'hotels':17,'annual_hotel_date_cells':6205,'new_vio_calendar_cells':len(annual),
                       'all_saved_observed_cells':len(annual|original),'all_saved_unknown_cells':6205-len(annual|original),
                       'original_observed_cells':len(original),'annual_complete':len(annual|original)==6205,
                       'new_detail_offers':len(detailed),'comparable_groups':len(comparable_minima(rates)['groups'])},
            'task_states':[{k:j[k] for k in ('task_id','state','attempts','reason')} for j in jobs],
            'limitations':['Local capture recency does not verify provider price-update time or uncached supply.',
                           'Missing prices are unknown even when polling says complete.',
                           'Google, Booking, direct, Vio base displays and Expedia USD remain separate series.',
                           'This importer makes no network calls. Provider transport is injected into the durable Queue runner.',
                           'Vrbo, Goibibo and Google vacation-rental price contracts are not implemented.']}
    _write_json(root/'latest.json',result)
    export_csv(root/'rates.csv',rates,['hotel_id','source','supplier','checkin','checkout','amount','currency','amount_basis',
                                   'price_scope','taxes_included','fees_included','evidence_kind','observed_at','source_url'])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path)
    parser.add_argument('--root',type=Path,default=DEFAULT)
    args=parser.parse_args()
    result=ingest(args.input,root=args.root) if args.input else report(args.root)
    print(json.dumps({'summary':result['summary'],'coverage':result['coverage']},indent=2))


if __name__=='__main__':main()
