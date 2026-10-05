"""Explicitly paired phone routes, kept separate from public proxy inventory.

Only public certificate material and a token environment-variable name are saved.
This module does not start a listener, change an OTA route or retry another phone.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import ssl
import tempfile
import time
from contextlib import contextmanager

import urllib3

SCHEMA = 'owned-phone-routes.v1'
PROBE_URL = 'https://httpbin.org/ip'
RFC1918 = tuple(ipaddress.ip_network(v) for v in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))


def private_ipv4(value):
    if not isinstance(value, str):
        raise ValueError('A literal private LAN IPv4 address is required')
    try:
        address = ipaddress.IPv4Address(value)
    except (ValueError, TypeError, ipaddress.AddressValueError):
        raise ValueError('A literal private LAN IPv4 address is required') from None
    if not any(address in network for network in RFC1918):
        raise ValueError('A literal private LAN IPv4 address is required')
    return str(address)


def _name(value, pattern, label):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError('Invalid ' + label)
    return value


def _public_origin(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError('Invalid echo address')
    address = ipaddress.ip_address(value)
    if not address.is_global or address.is_multicast or address.is_reserved:
        raise ValueError('Invalid echo address')
    return str(address)


def _stamp(value):
    if not isinstance(value, str) or len(value) > 60:
        raise ValueError('Invalid observation time')
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Observation time requires timezone')
    return parsed


def _health(value):
    if value == {'state': 'not_tested'}:
        return dict(value)
    common = {'state', 'tested_at', 'validation_url', 'error'}
    healthy = common | {'origin', 'latency_ms', 'proxy_tls_verified', 'target_tls_verified'}
    if not isinstance(value, dict) or value.get('state') not in ('failed', 'healthy'):
        raise ValueError('Invalid route health')
    if set(value) != (healthy if value['state'] == 'healthy' else common):
        raise ValueError('Invalid route health fields')
    _stamp(value['tested_at'])
    if value['validation_url'] != PROBE_URL:
        raise ValueError('Invalid health measurement destination')
    if value['state'] == 'healthy':
        _public_origin(value['origin'])
        latency = value['latency_ms']
        if (type(latency) not in (int, float) or not math.isfinite(latency) or not 0 <= latency <= 120000
                or value['proxy_tls_verified'] is not True or value['target_tls_verified'] is not True
                or value['error'] is not None):
            raise ValueError('Invalid verified health measurement')
    elif value['error'] != 'connection_or_tls_failed':
        raise ValueError('Invalid route error code')
    return dict(value)


@contextmanager
def _registry_lock(path):
    """Serialize the compare/write across processes; stale clients must reload."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(path.suffix + '.lock').open('a+b') as handle:
        deadline = time.monotonic() + 2
        while True:
            try:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError('Owned-device registry busy; retry explicitly') from None
                time.sleep(0.025)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def certificate_identity(pem):
    if not isinstance(pem, str) or len(pem) > 16384 or pem.count('-----BEGIN CERTIFICATE-----') != 1:
        raise ValueError('One public PEM certificate is required')
    if 'PRIVATE KEY' in pem:
        raise ValueError('Private keys are not accepted')
    try:
        der = ssl.PEM_cert_to_DER_cert(pem.strip())
        # OpenSSL validates the actual certificate structure, not just base64.
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=pem)
    except (ValueError, ssl.SSLError):
        raise ValueError('Invalid public PEM certificate') from None
    return hashlib.sha256(der).hexdigest()


def _atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, indent=2, ensure_ascii=True, allow_nan=False)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _validate_route(raw):
    if not isinstance(raw, dict) or set(raw) - {'id', 'label', 'host', 'port', 'token_env', 'certificate_pem', 'fingerprint_sha256', 'paired_at', 'health'}:
        raise ValueError('Invalid paired route fields')
    result = dict(raw)
    result['id'] = _name(raw.get('id'), r'[a-z0-9_-]{1,48}', 'route ID')
    label = raw.get('label')
    if not isinstance(label, str) or not 1 <= len(label) <= 120 or any(ord(c) < 32 for c in label):
        raise ValueError('Invalid phone label')
    result['host'] = private_ipv4(raw.get('host'))
    if type(raw.get('port')) is not int or not 1024 <= raw['port'] <= 65535:
        raise ValueError('Invalid phone port')
    _name(raw.get('token_env'), r'COMPSET_PHONE_[A-Z0-9_]{1,64}', 'token environment variable')
    fingerprint = _name(raw.get('fingerprint_sha256'), r'[0-9a-f]{64}', 'certificate fingerprint')
    if certificate_identity(raw.get('certificate_pem')) != fingerprint:
        raise ValueError('Certificate does not match the displayed phone fingerprint')
    _stamp(raw.get('paired_at'))
    result['health'] = _health(raw.get('health'))
    return result


class OwnedDevices:
    def __init__(self, path):
        self.path = Path(path)
        self._digest = None
        self._write_failed = False
        if not self.path.exists():
            self.state = {'schema_version': SCHEMA, 'devices': {}, 'sessions': {}}
            return
        if self.path.stat().st_size > 2_000_000:
            raise ValueError('Owned-device registry exceeds size limit')
        body = self.path.read_bytes()
        self._digest = hashlib.sha256(body).hexdigest()
        self.state = json.loads(body)
        if (not isinstance(self.state, dict) or set(self.state) != {'schema_version', 'devices', 'sessions'}
                or self.state.get('schema_version') != SCHEMA or not isinstance(self.state['devices'], dict)
                or not isinstance(self.state['sessions'], dict) or len(self.state['devices']) > 32
                or len(self.state['sessions']) > 10000):
            raise ValueError('Invalid owned-device registry')
        for key, route in self.state['devices'].items():
            if _validate_route(route)['id'] != key:
                raise ValueError('Route identity mismatch')
        for session, identity in self.state['sessions'].items():
            _name(session, r'[A-Za-z0-9_-]{1,64}', 'session ID')
            if not isinstance(identity, str) or identity not in self.state['devices']:
                raise ValueError('Session references an unknown paired phone')

    def _ensure_current(self):
        current = hashlib.sha256(self.path.read_bytes()).hexdigest() if self.path.exists() else None
        if self._write_failed or current != self._digest:
            raise ValueError('Owned-device registry changed; reload before using')

    def _commit(self):
        with _registry_lock(self.path):
            try:
                self._ensure_current()
                _atomic(self.path, self.state)
                self._digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
            except Exception:
                self._write_failed = True
                raise

    def register(self, *, identity, label, host, pem, fingerprint, token_env, port=8443):
        self._ensure_current()
        if identity not in self.state['devices'] and len(self.state['devices']) >= 32:
            raise ValueError('At most 32 paired phones are supported')
        route = _validate_route({'id': identity, 'label': label, 'host': host, 'port': port,
            'certificate_pem': pem, 'fingerprint_sha256': fingerprint, 'token_env': token_env,
            'paired_at': datetime.now(timezone.utc).isoformat(), 'health': {'state': 'not_tested'}})
        old = self.state['devices'].get(identity)
        if old and any(old[k] != route[k] for k in ('host', 'port', 'certificate_pem', 'token_env')):
            if identity in self.state['sessions'].values():
                raise ValueError('Paired route has assigned sessions; use a new route ID for changed pairing')
        self.state['devices'][identity] = route
        self._commit()
        return {'id': identity, 'state': 'paired_not_tested'}

    def manager(self, identity, *, environment=None):
        self._ensure_current()
        route = _validate_route(self.state['devices'][identity])
        token = (os.environ if environment is None else environment).get(route['token_env'])
        if not isinstance(token, str) or not re.fullmatch('[0-9a-f]{32}', token):
            raise ValueError('Phone pairing token is absent or invalid')
        proxy_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        proxy_tls.minimum_version = ssl.TLSVersion.TLSv1_2
        proxy_tls.check_hostname = False  # Identity is the exact, separately paired certificate pin.
        proxy_tls.verify_mode = ssl.CERT_REQUIRED
        proxy_tls.load_verify_locations(cadata=route['certificate_pem'])
        authorization = base64.b64encode(('compset:' + token).encode('ascii')).decode('ascii')
        return urllib3.ProxyManager(f"https://{route['host']}:{route['port']}",
            proxy_headers={'Proxy-Authorization': 'Basic ' + authorization},
            proxy_ssl_context=proxy_tls, proxy_assert_hostname=False,
            proxy_assert_fingerprint=route['fingerprint_sha256'], use_forwarding_for_https=False,
            ssl_context=ssl.create_default_context(), cert_reqs=ssl.CERT_REQUIRED,
            retries=False, timeout=urllib3.Timeout(connect=6, read=8, total=15),
            num_pools=2, maxsize=2, block=True)

    def probe(self, identity, *, environment=None):
        started = time.monotonic()
        manager, response = None, None
        health = {'state': 'failed', 'tested_at': datetime.now(timezone.utc).isoformat(),
                  'validation_url': PROBE_URL, 'error': 'connection_or_tls_failed'}
        try:
            manager = self.manager(identity, environment=environment)
            response = manager.request('GET', PROBE_URL, redirect=False, retries=False,
                preload_content=False, headers={'User-Agent': 'CompSet-Owned-Gateway-Probe/1.0', 'Accept': 'application/json'})
            body = response.read(4097, decode_content=False)
            if response.status != 200 or len(body) > 4096:
                raise ValueError('Invalid echo response')
            payload = json.loads(body)
            origin = payload.get('origin') if isinstance(payload, dict) else None
            origin = _public_origin(origin)
            health.update(state='healthy', origin=origin, latency_ms=round((time.monotonic()-started)*1000, 2),
                          proxy_tls_verified=True, target_tls_verified=True, error=None)
        except (OSError, ValueError, KeyError, TypeError, urllib3.exceptions.HTTPError):
            # Never persist exception strings containing URLs, headers or credentials.
            pass
        finally:
            if response is not None:
                response.close()
            if manager is not None:
                manager.clear()
        if identity not in self.state['devices']:
            raise ValueError('Unknown paired phone')
        self.state['devices'][identity]['health'] = health
        self._commit()
        return {'id': identity, **health}

    def assign(self, session_id):
        """Round-robin across recently probed phones for NEW sessions only."""
        self._ensure_current()
        _name(session_id, r'[A-Za-z0-9_-]{1,64}', 'session ID')
        devices, sessions = self.state['devices'], self.state['sessions']
        now = datetime.now(timezone.utc)
        eligible = []
        for identity, route in devices.items():
            try:
                health = _health(route.get('health', {}))
                age = (now - datetime.fromisoformat(health['tested_at'])).total_seconds()
                if (health.get('state') == 'healthy' and health.get('proxy_tls_verified') is True
                        and health.get('target_tls_verified') is True and 0 <= age <= 3600):
                    eligible.append(identity)
            except (TypeError, ValueError, KeyError):
                continue
        if session_id in sessions:
            if sessions[session_id] not in eligible:
                raise ValueError('Assigned phone is unhealthy or stale; no automatic fallback')
            return sessions[session_id]
        if not eligible:
            raise ValueError('No recently verified paired phones')
        if len(sessions) >= 10000:
            raise ValueError('Session registry limit reached')
        identity = min(sorted(eligible), key=lambda key: sum(v == key for v in sessions.values()))
        sessions[session_id] = identity
        self._commit()
        return identity

    def status(self):
        self._ensure_current()
        return [{'id': route['id'], 'label': route['label'], 'host': route['host'], 'port': route['port'],
                 'health': _health(route.get('health', {'state': 'not_tested'})),
                 'session_count': sum(v == route['id'] for v in self.state['sessions'].values())}
                for route in self.state['devices'].values()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, default=Path('routes/data/owned-devices.json'))
    commands = parser.add_subparsers(dest='command', required=True)
    register = commands.add_parser('register')
    for name in ('id', 'label', 'host', 'fingerprint', 'token-env'):
        register.add_argument('--' + name, required=True)
    register.add_argument('--certificate', type=Path, required=True)
    register.add_argument('--port', type=int, default=8443)
    probe = commands.add_parser('probe'); probe.add_argument('--id', required=True)
    assign = commands.add_parser('assign'); assign.add_argument('--session', required=True)
    commands.add_parser('status')
    args = parser.parse_args()
    registry = OwnedDevices(args.registry)
    if args.command == 'register':
        if args.certificate.stat().st_size > 16384:
            parser.error('Public certificate exceeds size limit')
        result = registry.register(identity=args.id, label=args.label, host=args.host,
            pem=args.certificate.read_text(encoding='ascii'), fingerprint=args.fingerprint,
            token_env=args.token_env, port=args.port)
    elif args.command == 'probe':
        result = registry.probe(args.id)
    elif args.command == 'assign':
        result = {'session': args.session, 'device': registry.assign(args.session)}
    else:
        result = registry.status()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
