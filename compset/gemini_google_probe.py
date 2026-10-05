"""Run only the Google scraping section of the supplied Gemini script.

The original source is retained separately. This runner excludes its seeded
prices, fabricated onboarding records, scheduler and optimisation demo. At most
three HTTP attempts are made; challenges stop the probe without fallback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import time
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional


class ProbeStopped(BaseException):
    """Escape the original script's broad exception/retry handlers."""


class BoundedFetcher:
    def __init__(self, output, transport, *, max_requests=3, interval=3):
        self.output = Path(output)
        self.transport = transport
        self.max_requests = max_requests
        self.interval = interval
        self.records = []
        self.last_started = None
        self.stop_reason = None

    def get(self, url, **kwargs):
        return self.request('GET', url, **kwargs)

    def post(self, url, **kwargs):
        return self.request('POST', url, **kwargs)

    def request(self, method, url, **kwargs):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname != 'www.google.com':
            self.stop_reason = 'unexpected_destination'
            raise ProbeStopped(self.stop_reason)
        if len(self.records) >= self.max_requests:
            self.stop_reason = 'request_budget_exhausted'
            raise ProbeStopped(self.stop_reason)
        if self.last_started is not None:
            time.sleep(max(0, self.interval - (time.monotonic() - self.last_started)))
        self.last_started = time.monotonic()
        record = {'method': method, 'url': url,
                  'observed_at': datetime.now(timezone.utc).isoformat()}
        self.records.append(record)
        # One transport attempt, no hidden retries, redirects or proxy rotation.
        kwargs.update(timeout=20, retries=1, follow_redirects=False)
        try:
            response = getattr(self.transport, method.lower())(url, **kwargs)
        except Exception as exc:
            record['error_type'] = type(exc).__name__
            self.stop_reason = 'transport_error'
            raise ProbeStopped(self.stop_reason) from exc
        body = bytes(response.body)
        text = body.decode('utf-8', errors='replace')
        record.update(status=response.status, body_bytes=len(body),
                      body_sha256=hashlib.sha256(body).hexdigest(),
                      rpc_marker_present='wrb.fr' in text,
                      token_attribute_count=len(re.findall(r'data-rpc-id=', text)))
        evidence = self.output / f'response-{len(self.records):02d}.body'
        evidence.write_bytes(body)
        record['body_artifact'] = str(evidence)
        if method == 'GET' and response.status in {301, 302, 303, 307, 308}:
            location = next((v for k, v in response.headers.items() if k.lower() == 'location'), None)
            if not location:
                self.stop_reason = 'redirect_without_location'
                raise ProbeStopped(self.stop_reason)
            destination = urllib.parse.urljoin(url, location)
            redirected = urllib.parse.urlsplit(destination)
            if redirected.scheme != 'https' or redirected.hostname != 'www.google.com':
                self.stop_reason = 'redirect_outside_google'
                raise ProbeStopped(self.stop_reason)
            record['redirect_url'] = destination
            return self.request('GET', destination, **kwargs)
        if response.status in {401, 403, 429}:
            self.stop_reason = f'access_or_rate_limit_{response.status}'
            raise ProbeStopped(self.stop_reason)
        visible = re.sub(r'<[^>]+>', ' ', text)
        if re.search(r'our systems have detected unusual traffic|verify (?:that )?you are human|'
                     r'complete the captcha|access denied', visible, re.I):
            self.stop_reason = 'challenge_detected'
            raise ProbeStopped(self.stop_reason)
        # Scrapling .text is element text, not guaranteed to be the raw JSON/HTML.
        # The original scraper's regex and JSON parsing require decoded body bytes.
        return SimpleNamespace(status=response.status, text=text)


def load_scraping_section(source, fetcher):
    original = Path(source).read_text(encoding='utf-8')
    property_code = original[original.index('@dataclass\nclass PropertyNode:'):
                             original.index('RESEARCH_MASTER_REGISTRY:')]
    start = original.index('class DynamicTokenManager:')
    end = original.index('# MODULE 3:', start)
    scraper_code = original[start:original.rfind('\n# ===', start, end)]
    namespace = {'dataclass': dataclass, 'Dict': Dict, 'List': List, 'Optional': Optional,
                 'Fetcher': lambda: fetcher, 'json': json, 're': re, 'urllib': urllib,
                 'logger': logging.getLogger('GeminiGoogleProbe'), '__name__': __name__}
    exec(compile(property_code + '\n' + scraper_code, str(source), 'exec'), namespace)
    return namespace, hashlib.sha256(original.encode('utf-8')).hexdigest()


def run(source, output, start_date, days=3, *, transport=None, reuse_report=None, route_b_only=False):
    if not 1 <= days <= 30:
        raise ValueError('days must be between 1 and 30')
    start = date.fromisoformat(start_date)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    if transport is None:
        from scrapling.fetchers import Fetcher
        transport = Fetcher
    bounded = BoundedFetcher(output, transport)
    namespace, source_hash = load_scraping_section(source, bounded)
    prop = namespace['PropertyNode']('hotel_aketa', 'Hotel Aketa', 'SUBJECT_HOTEL',
        'Central Rajpur Road', 30.3412, 78.0615,
        'Hotel Aketa 113/1-2 Rajpur Road Dehradun')
    engine = namespace['DualRouteBatchWireEngine']()
    candidates = {}
    started = time.monotonic()
    failure = None
    try:
        if route_b_only:
            candidates = {prop.id: engine.fetch_single_property_route_b(
                prop, start.isoformat(), (start + timedelta(days=days)).isoformat())}
        else:
            candidates = engine.fetch_multi_property_batch(
                [prop], start.isoformat(), (start + timedelta(days=days)).isoformat())
    except ProbeStopped:
        pass
    except Exception as exc:
        failure = type(exc).__name__
    result = {
        'state': 'unverified_candidates' if any(candidates.values()) else 'unknown',
        'source_script': str(Path(source).resolve()), 'source_sha256': source_hash,
        'method': 'gemini_original_google_scraping_section_with_bounded_transport',
        'route_b_only': route_b_only,
        'requested_context': {'hotel': prop.name, 'query': prop.search_query,
            'start_date': start.isoformat(), 'end_date': (start + timedelta(days=days)).isoformat(),
            'adults': 2, 'currency': 'INR', 'rooms': None},
        'observed_at': datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds': round(time.monotonic() - started, 3),
        'requests': bounded.records, 'http_attempts': len(bounded.records),
        'stop_reason': bounded.stop_reason, 'error_type': failure,
        'unverified_candidates': candidates,
        'candidate_count': sum(len(v) for v in candidates.values()),
        'verified_price_count': 0, 'unavailable_count': 0,
        'limitations': [
            'Original RPC id, arguments and response schema are unverified.',
            'Generic date-price matches do not independently prove hotel, party, tax or stay context.',
            'The original script uses two adults; existing one-adult browser data is a separate observation.',
            'No seeded rates, invented unavailable dates, room profiles or solver outputs were executed.'
        ],
    }
    if reuse_report is not None:
        prior = json.loads(Path(reuse_report).read_text(encoding='utf-8'))
        result['separate_existing_browser_evidence'] = {
            'path': str(Path(reuse_report).resolve()), 'observed_at': prior.get('observed_at'),
            'state': prior.get('state'), 'summary': prior.get('summary'),
            'requested_context': prior.get('requested_context'),
            'note': 'Separate existing collector output; no extra browser request and not Gemini RPC proof.'}
    (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--start-date', required=True)
    parser.add_argument('--days', type=int, default=3)
    parser.add_argument('--reuse-report', type=Path)
    parser.add_argument('--route-b-only', action='store_true', help='Test SSR route without repeating a failed RPC')
    args = parser.parse_args()
    result = run(args.source, args.output, args.start_date, args.days,
                 reuse_report=args.reuse_report, route_b_only=args.route_b_only)
    print(json.dumps({k: result[k] for k in ('state', 'http_attempts', 'candidate_count',
        'verified_price_count', 'unavailable_count', 'stop_reason', 'error_type')}, indent=2))
