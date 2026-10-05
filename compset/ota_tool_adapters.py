"""Strict public projections for the actual Vio and Expedia tool contracts.

Tool fetch timestamps are our capture times, not asserted provider update times.
Calendar holes remain unknown even when a provider says its polling completed.
"""
from __future__ import annotations

from datetime import date, timedelta

from .rate_policy import amount, freshness, public_url

# Reviewed exact Dehradun name/address bindings from current connector profiles
# and the saved official/OSM roster. These are property IDs, not API credentials.
VIO_BINDINGS = {
 'osm:node:11740798982':'1659409', 'osm:node:6123644590':'2331991',
 'osm:node:6147612906':'44325291', 'osm:node:6066360185':'3254234',
 'osm:node:10602916733':'59840658', 'osm:node:4922436521':'2890523',
 'osm:node:6121571816':'3254006', 'osm:node:13520091277':'54117243',
 'official:sarovar-portico-dehradun':'6296133','official:sterling-marbella-dehradun':'9625616',
 'official:spree-kriday-dehradun':'9982822','official:clarks-inn-niranjanpur':'125429847',
 'official:hyatt-centric-rajpur-road':'80845118','official:fairfield-dehradun':'21136362',
 'osm:way:331779423':'1731170'}


def reviewed_binding(task):
    if task['provider']=='vio': return VIO_BINDINGS.get(task['hotel_id'])==task['provider_id']
    if task['provider']=='expedia':
        return task['hotel_id']=='osm:node:11740798982' and task['provider_id']=='92850456'
    return False


def sanitize_capture(raw, task):
    """Persist only fields of these reviewed provider response contracts."""
    if not isinstance(raw,dict): raise ValueError('Capture must be an object')
    # No generic recursive object pass-through, including public-looking extra keys.
    def fields(value,names):
        if not isinstance(value,dict): raise ValueError('Malformed capture object')
        result={name:value[name] for name in names if name in value}
        for name,item in result.items():
            if isinstance(item,(dict,list)) or not isinstance(item,(str,int,float,bool,type(None))):
                raise ValueError('Expected scalar capture leaf: '+name)
            if isinstance(item,str) and len(item)>1000: raise ValueError('Capture text too long')
        return result
    def prices(value):
        result=fields(value,('base','taxes','hotelFees','displayPrice'))
        return {key:amount(item,allow_zero=key in {'taxes','hotelFees'}) for key,item in result.items() if item is not None}
    def rooms(value): return party(value)
    observed=raw['observed_at']
    freshness(observed)
    if task['provider']=='vio':
        out=fields(raw,('currency','startDate','endDate','checkIn','checkOut','nights','priceScope','priceLogic','complete'))
        out['observed_at']=observed
        out['roomConfiguration']=rooms(raw.get('roomConfiguration'))
        if task['mode']=='calendar':
            out['availability']=[]
            for item in raw.get('availability',[]):
                clean=fields(item,('hotelId','checkIn','offerCount'))
                clean['cheapestRate']=prices(item.get('cheapestRate'))
                out['availability'].append(clean)
        else:
            out['hotels']=[]
            for hotel in raw.get('hotels',[]):
                clean=fields(hotel,('id','name'))
                clean['offers']={'items':[]}
                for offer in hotel.get('offers',{}).get('items',[]):
                    rate=fields(offer,('currency','roomName','providerName'))
                    rate['rate']=prices(offer.get('rate'))
                    rate['url']=public_url(offer['url'],{'vio.com','www.vio.com'})
                    if isinstance(offer.get('package'),dict):
                        amenities=offer['package'].get('amenities')
                        if isinstance(amenities,list) and all(isinstance(v,str) for v in amenities):
                            rate['package']={'amenities':amenities}
                    clean['offers']['items'].append(rate)
                out['hotels'].append(clean)
        return out
    if task['provider']=='expedia':
        out={'observed_at':observed,'occupants':[],'data':[]}
        for occupant in raw.get('occupants',[]):
            normalized=party([{'adults':occupant.get('adults'),'children':occupant.get('child_ages')}])[0]
            out['occupants'].append({'adults':normalized['adults'],'child_ages':normalized['children']})
        for row in raw.get('data',[]):
            clean=fields(row,('hotel_id','hotel_name','avg_nightly_price','avg_nightly_rate_with_fees',
                             'total_price','checkin_date','checkout_date','currency'))
            clean['url']=public_url(row['url'],{'www.expedia.com','www.expedia.co.in'})
            out['data'].append(clean)
        return out
    raise ValueError('No reviewed capture schema for this provider')


def party(value):
    if not isinstance(value, list) or not value:
        raise ValueError('Returned room configuration is missing')
    out = []
    for room in value:
        if not isinstance(room, dict) or type(room.get('adults')) is not int or room['adults'] < 1:
            raise ValueError('Returned adult count is not typed')
        ages = room.get('children')
        if not isinstance(ages, list) or any(type(age) is not int or not 0 <= age <= 17 for age in ages):
            raise ValueError('Returned child ages are unknown or malformed')
        out.append({'adults':room['adults'], 'children':ages})
    return out


def _vio_context(capture, task, *, calendar):
    if task['provider'] != 'vio' or task['identity_verified'] is not True or not reviewed_binding(task):
        raise ValueError('Vio requires a reviewed property binding')
    if capture.get('currency') != task['currency'] or type(capture.get('nights')) is not int or capture['nights'] != 1:
        raise ValueError('Returned currency/stay length differs')
    if party(capture.get('roomConfiguration')) != party(task['party']):
        raise ValueError('Returned party differs')
    if capture.get('priceScope') not in {'per_room','all_rooms_combined'} or capture.get('priceLogic') not in {'base','base_fees','base_tax_fees'}:
        raise ValueError('Price scope or inclusion basis missing')
    if calendar:
        if capture.get('startDate') != task['start_date'] or capture.get('endDate') != task['end_date']:
            raise ValueError('Returned date window differs')
    elif capture.get('checkIn') != task['start_date'] or capture.get('checkOut') != str(date.fromisoformat(task['start_date'])+timedelta(days=1)):
        raise ValueError('Returned exact stay differs')


def _base(task, capture, checkin, observed_at, *, calendar):
    return {'hotel_id':task['hotel_id'], 'provider_id':task['provider_id'], 'source':'vio',
            'supplier':None, 'checkin':checkin,
            'checkout':str(date.fromisoformat(checkin)+timedelta(days=1)),
            'currency':capture['currency'], 'party':party(capture['roomConfiguration']),
            'party_verified':True, 'property_identity_verified':True,
            'amount_basis':'one_night_display', 'price_scope':capture['priceScope'],
            'taxes_included':capture['priceLogic']=='base_tax_fees',
            'fees_included':capture['priceLogic'] in {'base_fees','base_tax_fees'},
            'room_product':None,'meals':None,'cancellation':None,'payment':None,
            'membership':None,'coupon':None,'terms_verified':False,
            'evidence_kind':'calendar_indicative' if calendar else 'provider_display',
            'observed_at':observed_at,'freshness':freshness(observed_at),
            'provider_updated_at':None,'uncached_verified':False,
            'direct_supplier_quote':False}


def _money_projection(rate, price_logic):
    from decimal import Decimal
    result={'amount':amount(rate['displayPrice']),'base':amount(rate['base']),
            'taxes':amount(rate['taxes'],allow_zero=True) if rate.get('taxes') is not None else None,
            'hotel_fees':amount(rate['hotelFees'],allow_zero=True) if rate.get('hotelFees') is not None else None}
    expected=Decimal(result['base'])
    if price_logic in {'base_fees','base_tax_fees'}:
        if result['hotel_fees'] is None: raise ValueError('Included fees amount missing')
        expected+=Decimal(result['hotel_fees'])
    if price_logic=='base_tax_fees':
        if result['taxes'] is None: raise ValueError('Included tax amount missing')
        expected+=Decimal(result['taxes'])
    if abs(expected-Decimal(result['amount']))>Decimal('0.02'):
        raise ValueError('Display disagrees with inclusion basis')
    return result


def normalize_vio_calendar(capture, task):
    _vio_context(capture, task, calendar=True)
    observed_at = capture['observed_at']
    start, end = date.fromisoformat(task['start_date']), date.fromisoformat(task['end_date'])
    rows, rejected, conflicts = {}, [], set()
    for i, original in enumerate(capture.get('availability', [])):
        try:
            if not isinstance(original,dict) or original.get('hotelId') != task['provider_id']:
                raise ValueError('Wrong provider property')
            day = date.fromisoformat(original['checkIn'])
            if not start <= day <= end: raise ValueError('Outside requested dates')
            rate = original['cheapestRate']
            row = _base(task,capture,str(day),observed_at,calendar=True)
            row.update(**_money_projection(rate,capture['priceLogic']),
                       source_url='https://www.vio.com/',source_path=f'availability[{i}].cheapestRate')
            if str(day) in rows and rows[str(day)]['amount'] != row['amount']:
                conflicts.add(str(day))
            rows[str(day)] = row
        except (KeyError, TypeError, ValueError) as exc:
            rejected.append({'index':i,'reason':str(exc)})
    rates = [r for day,r in sorted(rows.items()) if day not in conflicts]
    requested_days=(end-start).days+1
    return {'source':'vio','method':'connector_calendar','rates':rates,'rejected':rejected,
            'provider_poll_complete':capture.get('complete') is True,
            'price_date_coverage_complete':len(rates)==requested_days,
            'requested_dates':requested_days,'observed_dates':len(rates),
            'unknown_dates':requested_days-len(rates),'conflicting_dates':sorted(conflicts)}


def normalize_vio_offers(capture, task):
    _vio_context(capture,task,calendar=False)
    hotels = [h for h in capture.get('hotels',[]) if isinstance(h,dict) and h.get('id')==task['provider_id']]
    if len(hotels)!=1: raise ValueError('Expected exactly one reviewed hotel')
    rates=[]
    for i, offer in enumerate(hotels[0].get('offers',{}).get('items',[])):
        if offer.get('currency')!=task['currency']: raise ValueError('Offer currency differs')
        row=_base(task,capture,task['start_date'],capture['observed_at'],calendar=False)
        row.update(**_money_projection(offer['rate'],capture['priceLogic']),
                   supplier=offer.get('providerName'),room_product=offer.get('roomName'),
                   meals=offer.get('package',{}).get('amenities'),
                   source_url=public_url(offer['url'],{'vio.com','www.vio.com'}),
                   source_path=f'hotels.offers.items[{i}]')
        # Empty cancellation penalties do not prove free cancellation.
        rates.append(row)
    return {'source':'vio','method':'connector_offers','rates':rates,'observed_dates':int(bool(rates))}


def normalize_expedia(capture, task):
    if task['provider']!='expedia' or task['identity_verified'] is not True or not reviewed_binding(task):
        raise ValueError('Expedia requires a reviewed property binding')
    occupants=capture.get('occupants')
    if not isinstance(occupants,list) or len(occupants)!=len(task['party']):
        raise ValueError('Returned occupancy missing')
    actual=party([{'adults':r.get('adults'),'children':r.get('child_ages')} for r in occupants])
    if actual!=party(task['party']): raise ValueError('Returned occupancy differs')
    rows=[]
    for original in capture.get('data',[]):
        if original.get('hotel_id')!=task['provider_id']: continue
        if original.get('currency')!=task['currency']: raise ValueError('Returned currency differs')
        arrival=original.get('checkin_date'); departure=original.get('checkout_date')
        if arrival!=task['start_date'] or departure!=str(date.fromisoformat(arrival)+timedelta(days=1)):
            raise ValueError('Returned stay differs')
        import re
        from urllib.parse import urlsplit
        source_url=public_url(original['url'],{'www.expedia.com','www.expedia.co.in'})
        provider_path=re.search(r'\.h(\d+)\.Hotel-Information',urlsplit(source_url).path)
        if not provider_path or provider_path[1]!=task['provider_id']:
            raise ValueError('Expedia property URL differs')
        rows.append({'hotel_id':task['hotel_id'],'provider_id':task['provider_id'],'source':'expedia',
                     'supplier':'Expedia','checkin':arrival,'checkout':departure,'currency':original['currency'],
                     'party':actual,'party_verified':True,'property_identity_verified':True,
                     'amount':amount(original['total_price']),'amount_basis':'one_night_display_total',
                     'price_scope':'all_rooms_combined',
                     'taxes_included':None,'fees_included':None,'room_product':None,'meals':None,
                     'cancellation':None,'payment':None,'membership':None,'coupon':None,'terms_verified':False,
                     'evidence_kind':'provider_display','observed_at':capture['observed_at'],
                     'freshness':freshness(capture['observed_at']),'provider_updated_at':None,'uncached_verified':False,
                     'source_url':source_url,
                     'source_path':'data.total_price','direct_supplier_quote':False})
    return {'source':'expedia','method':'connector_display','rates':rows,'observed_dates':int(bool(rows))}
