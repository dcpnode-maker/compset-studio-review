from datetime import datetime, timezone
import json
from pathlib import Path
import ssl
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import certifi
from routes.owned_devices import OwnedDevices, certificate_identity, private_ipv4, PROBE_URL


# Public CA material only: no test private key, remote requests or real phone required.
PEM = '-----BEGIN CERTIFICATE-----' + Path(certifi.where()).read_text(encoding='ascii').split('-----BEGIN CERTIFICATE-----', 1)[1].split('-----END CERTIFICATE-----', 1)[0] + '-----END CERTIFICATE-----\n'
FINGERPRINT = certificate_identity(PEM)
TOKEN = '1' * 32


class Response:
    status = 200
    body = b'{"origin":"8.8.8.8"}'
    closed = False
    def read(self, amount, **kwargs):
        return self.body[:amount]
    def close(self):
        self.closed = True


class Manager:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.cleared = False
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response
    def clear(self):
        self.cleared = True


class OwnedDevicesTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'owned.json'
        self.registry = OwnedDevices(self.path)

    def register(self, identity='phone1', **changes):
        args = dict(identity=identity, label='My phone', host='192.168.1.10', pem=PEM,
                    fingerprint=FINGERPRINT, token_env='COMPSET_PHONE_ONE')
        args.update(changes)
        return self.registry.register(**args)

    def test_pairing_requires_private_literal_ipv4_and_matching_public_certificate(self):
        for host in ('127.0.0.1', '169.254.1.1', '8.8.8.8', 'phone.local', '::1', '100.64.0.1', '192.168.1.1\n'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                self.register(host=host)
        self.assertFalse(self.path.exists())
        with self.assertRaisesRegex(ValueError, 'fingerprint'):
            self.register(fingerprint='0' * 64)
        with self.assertRaises(ValueError):
            self.register(pem=PEM + '\n-----BEGIN PRIVATE KEY-----\n')
        self.assertEqual(private_ipv4('10.1.2.3'), '10.1.2.3')

    def test_registry_never_persists_the_pairing_token(self):
        self.register()
        self.assertNotIn(TOKEN, self.path.read_text())
        loaded = OwnedDevices(self.path)
        self.assertEqual(loaded.status()[0]['health']['state'], 'not_tested')
        self.assertNotIn('token_env', loaded.status()[0])
        with self.assertRaisesRegex(ValueError, 'No recently'):
            loaded.assign('new')

    def test_proxy_and_target_tls_are_verified_and_auth_is_proxy_only(self):
        self.register()
        with patch('routes.owned_devices.urllib3.ProxyManager') as factory:
            self.registry.manager('phone1', environment={'COMPSET_PHONE_ONE': TOKEN})
        args, kwargs = factory.call_args
        self.assertEqual(args, ('https://192.168.1.10:8443',))
        self.assertEqual(kwargs['proxy_ssl_context'].verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(kwargs['ssl_context'].verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(kwargs['ssl_context'].check_hostname)
        self.assertEqual(kwargs['proxy_assert_fingerprint'], FINGERPRINT)
        self.assertFalse(kwargs['use_forwarding_for_https'])
        self.assertFalse(kwargs['retries'])
        self.assertEqual(set(kwargs['proxy_headers']), {'Proxy-Authorization'})
        self.assertNotIn('headers', kwargs)

    def test_fixed_neutral_probe_has_no_redirect_or_retry_and_closes_resources(self):
        self.register()
        response = Response(); manager = Manager(response)
        with patch.object(self.registry, 'manager', return_value=manager):
            result = self.registry.probe('phone1')
        self.assertEqual(result['state'], 'healthy')
        args, kwargs = manager.calls[0]
        self.assertEqual(args, ('GET', PROBE_URL))
        self.assertFalse(kwargs['redirect']); self.assertFalse(kwargs['retries'])
        self.assertNotIn('Proxy-Authorization', kwargs['headers'])
        self.assertTrue(response.closed); self.assertTrue(manager.cleared)
        self.assertEqual(self.registry.assign('first'), 'phone1')

    def test_invalid_or_oversized_echo_never_becomes_healthy(self):
        self.register()
        cases = [(302, b'{"origin":"8.8.8.8"}'), (200, b'x' * 4097),
                 (200, b'{"origin":"127.0.0.1"}'), (200, b'{"origin":"8.8.8.8, 1.1.1.1"}'),
                 (200, b'{"origin":true}'), (200, b'null')]
        for status, body in cases:
            with self.subTest(status=status, body=body[:60]):
                response = Response(); response.status = status; response.body = body
                with patch.object(self.registry, 'manager', return_value=Manager(response)):
                    self.assertEqual(self.registry.probe('phone1')['state'], 'failed')
                with self.assertRaises(ValueError):
                    self.registry.assign('new')

    def test_session_rotation_is_only_for_new_sessions_without_failure_fallback(self):
        self.register('phone1'); self.register('phone2', host='192.168.1.11')
        for identity in ('phone1', 'phone2'):
            with patch.object(self.registry, 'manager', return_value=Manager(Response())):
                self.registry.probe(identity)
        self.assertEqual(self.registry.assign('one'), 'phone1')
        self.assertEqual(self.registry.assign('two'), 'phone2')
        self.assertEqual(self.registry.assign('one'), 'phone1')
        self.registry.state['devices']['phone1']['health']['state'] = 'failed'
        with self.assertRaisesRegex(ValueError, 'no automatic fallback'):
            self.registry.assign('one')
        self.assertEqual(self.registry.assign('three'), 'phone2')
        with self.assertRaisesRegex(ValueError, 'assigned sessions'):
            self.register('phone2', host='192.168.1.12')

    def test_unavailable_token_or_sensitive_exception_text_is_not_persisted(self):
        self.register()
        with patch.object(self.registry, 'manager', side_effect=OSError('secret-pairing-canary')):
            result = self.registry.probe('phone1')
        self.assertEqual(result['state'], 'failed')
        self.assertNotIn('secret-pairing-canary', self.path.read_text())
        with self.assertRaisesRegex(ValueError, 'token'):
            self.registry.manager('phone1', environment={})

    def test_stale_future_and_missing_health_cannot_supply_routes(self):
        self.register()
        for stamp in ('2000-01-01T00:00:00+00:00', '2999-01-01T00:00:00+00:00', 'invalid'):
            self.registry.state['devices']['phone1']['health'] = {
                'state': 'healthy', 'tested_at': stamp, 'proxy_tls_verified': True, 'target_tls_verified': True}
            with self.assertRaisesRegex(ValueError, 'No recently'):
                self.registry.assign('new')


if __name__ == '__main__':
    unittest.main()
