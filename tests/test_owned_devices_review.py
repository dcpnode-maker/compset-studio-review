"""Independent owned-phone client tests; temporary registries and no external traffic."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import hashlib
import base64
import socket
import ssl
import subprocess
import threading
import urllib3.connection
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from routes.owned_devices import OwnedDevices, private_ipv4, PROBE_URL, certificate_identity
from tests.test_owned_devices import PEM, FINGERPRINT, TOKEN, Response, Manager


class OwnedDeviceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'phones.json'
        self.registry=OwnedDevices(self.path)
        self.register('phone1','192.168.1.10')

    def register(self, identity, host):
        self.registry.register(identity=identity,label='Review phone',host=host,pem=PEM,
            fingerprint=FINGERPRINT,token_env='COMPSET_PHONE_REVIEW')

    def healthy(self, identity='phone1'):
        with patch.object(self.registry,'manager',return_value=Manager(Response())):
            self.registry.probe(identity)

    def test_invalid_session_bindings_are_rejected_at_load(self):
        original=json.loads(self.path.read_text(encoding='utf-8'))
        for sessions in [{'bad session':'phone1'},{'good':'missing'},{'good':['phone1']},{'good':False},
                         {str(i):'phone1' for i in range(10001)}]:
            with self.subTest(shape=type(next(iter(sessions.values()))).__name__,count=len(sessions)):
                state=deepcopy(original);state['sessions']=sessions
                self.path.write_text(json.dumps(state),encoding='utf-8')
                with self.assertRaises(ValueError):OwnedDevices(self.path)

    def test_malformed_health_and_extra_sensitive_fields_are_rejected_at_load(self):
        self.healthy();original=json.loads(self.path.read_text(encoding='utf-8'))
        valid=original['devices']['phone1']['health']
        bad=[[],True,'healthy',{**valid,'pairing_token':'PRIVATE_SECRET'},
             {**valid,'origin':'192.168.1.7'},{**valid,'origin':134744072},
             {**valid,'validation_url':'https://example.com/ip'},
             {**valid,'latency_ms':float('nan')},{**valid,'latency_ms':-1},
             {**valid,'proxy_tls_verified':1},{**valid,'target_tls_verified':'true'},
             {**valid,'tested_at':'2026-01-01T00:00:00'},{**valid,'tested_at':'broken'}]
        for health in bad:
            with self.subTest(health=health):
                state=deepcopy(original);state['devices']['phone1']['health']=health
                self.path.write_text(json.dumps(state),encoding='utf-8')
                with self.assertRaises(ValueError):OwnedDevices(self.path)

    def test_fixed_echo_requires_string_ip_not_numeric_json_address(self):
        response=Response();response.body=b'{"origin":134744072}'
        with patch.object(self.registry,'manager',return_value=Manager(response)):
            result=self.registry.probe('phone1')
        self.assertEqual(result['state'],'failed')
        with self.assertRaises(ValueError):self.registry.assign('new')

    def test_literal_private_ipv4_does_not_accept_integer_representation(self):
        with self.assertRaises(ValueError):private_ipv4(3232235786)

    def test_separately_loaded_registry_does_not_overwrite_sticky_sessions(self):
        self.register('phone2','192.168.1.11');self.healthy('phone1');self.healthy('phone2')
        left=OwnedDevices(self.path);right=OwnedDevices(self.path)
        self.assertEqual(left.assign('session_a'),'phone1')
        try:
            assigned=right.assign('session_b')
        except ValueError as error:
            self.assertIn('reload',str(error))
            right=OwnedDevices(self.path)
            assigned=right.assign('session_b')
        self.assertEqual(assigned,'phone2')
        loaded=OwnedDevices(self.path)
        self.assertEqual(loaded.assign('session_a'),'phone1')
        self.assertEqual(loaded.assign('session_b'),'phone2')
        self.assertEqual(len(loaded.state['sessions']),2)

    def test_stale_registry_instance_cannot_assign_after_failed_probe(self):
        self.healthy();stale=OwnedDevices(self.path)
        with patch.object(self.registry,'manager',side_effect=OSError('PRIVATE_PAIRING_TOKEN_CANARY')):
            self.registry.probe('phone1')
        with self.assertRaises(ValueError):stale.assign('new')
        self.assertNotIn('PRIVATE_PAIRING_TOKEN_CANARY',self.path.read_text(encoding='utf-8'))

    def test_status_does_not_echo_in_memory_sensitive_health_extension(self):
        self.registry.state['devices']['phone1']['health']['pairing_token']='PRIVATE_SECRET_CANARY'
        try: status=self.registry.status()
        except ValueError:return
        self.assertNotIn('PRIVATE_SECRET_CANARY',json.dumps(status))

    def test_stale_existing_session_does_not_return_after_failed_health_update(self):
        self.healthy();self.registry.assign('existing');stale=OwnedDevices(self.path)
        with patch.object(self.registry,'manager',side_effect=OSError('token-not-for-log')):
            self.registry.probe('phone1')
        with self.assertRaises(ValueError):stale.assign('existing')

    def test_rejected_stale_commit_cannot_be_retried_as_an_in_memory_success(self):
        self.healthy();stale=OwnedDevices(self.path)
        self.registry.assign('first')
        with self.assertRaises(ValueError):stale.assign('second')
        with self.assertRaises(ValueError):stale.assign('second')
        self.assertNotIn('second',OwnedDevices(self.path).state['sessions'])


class OwnedDeviceTLSReviewTests(unittest.TestCase):
    """Actual TLS over a socket pair; urllib3 cannot open any external connection."""
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        jdk=root/'android-gateway'/'.tools'/'jdk-21.0.12.1+1'/'bin'
        if not (jdk/'keytool.exe').exists():
            raise unittest.SkipTest('Optional local JDK fixture generator is unavailable')
        cls.temp=TemporaryDirectory();cls.addClassCleanup(cls.temp.cleanup)
        cls.folder=Path(cls.temp.name)
        helper=cls.folder/'ExportFixture.java'
        helper.write_text('''import java.nio.file.*; import java.security.*; import java.util.*;
class ExportFixture { public static void main(String[] a) throws Exception {
  KeyStore s=KeyStore.getInstance("PKCS12");
  try(var input=Files.newInputStream(Path.of(a[0]))) { s.load(input,"local-test-only".toCharArray()); }
  write(a[1],"CERTIFICATE",s.getCertificate("fixture").getEncoded());
  write(a[2],"PRIVATE KEY",s.getKey("fixture","local-test-only".toCharArray()).getEncoded());
} static void write(String p,String t,byte[] b) throws Exception {
  String e=Base64.getMimeEncoder(64,new byte[]{10}).encodeToString(b);
  Files.writeString(Path.of(p),"-----BEGIN "+t+"-----\\n"+e+"\\n-----END "+t+"-----\\n");
}}''',encoding='utf-8')
        cls.fixtures={}
        for identity in ('paired','other'):
            store=cls.folder/(identity+'.p12');cert=cls.folder/(identity+'.crt');key=cls.folder/(identity+'.key')
            subprocess.run([str(jdk/'keytool.exe'),'-genkeypair','-alias','fixture','-keyalg','RSA',
                '-keysize','2048','-dname','CN=Owned Device Review Fixture '+identity,'-validity','2',
                '-keystore',str(store),'-storetype','PKCS12','-storepass','local-test-only',
                '-keypass','local-test-only','-ext','SAN=dns:httpbin.org,ip:192.168.1.10','-noprompt'],
                check=True,capture_output=True,timeout=30)
            subprocess.run([str(jdk/'java.exe'),str(helper),str(store),str(cert),str(key)],
                check=True,capture_output=True,timeout=30)
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key)
            cls.fixtures[identity]={'pem':cert.read_text(encoding='ascii'),'context':context}

    def run_fixture(self, *, outer='paired', trust_other_proxy=False, inner=False, trust_target=False):
        path=self.folder/('registry-'+self._testMethodName+'.json')
        registry=OwnedDevices(path);pem=self.fixtures['paired']['pem']
        registry.register(identity='phone1',label='Synthetic fixture',host='192.168.1.10',pem=pem,
            fingerprint=certificate_identity(pem),token_env='COMPSET_PHONE_REVIEW')
        manager=registry.manager('phone1',environment={'COMPSET_PHONE_REVIEW':TOKEN})
        if trust_other_proxy:
            # Permit the alternate certificate chain so the independent pin must reject it.
            manager.proxy_config.ssl_context.load_verify_locations(cadata=self.fixtures['other']['pem'])
        if trust_target:
            # A test-only trust root, never written to application configuration or OS trust.
            manager.connection_pool_kw['ssl_context'].load_verify_locations(cadata=self.fixtures['other']['pem'])
        client,server=socket.socketpair();client.settimeout(4);server.settimeout(4)
        observed={'outer_handshake':False,'proxy_bytes':b'','target_bytes':b'','inner_started':False}
        def peer():
            try:
                with self.fixtures[outer]['context'].wrap_socket(server,server_side=True) as secure:
                    observed['outer_handshake']=True
                    while b'\r\n\r\n' not in observed['proxy_bytes'] and len(observed['proxy_bytes'])<16384:
                        chunk=secure.recv(4096)
                        if not chunk:return
                        observed['proxy_bytes']+=chunk
                    if not inner:
                        secure.sendall(b'HTTP/1.1 502 Fixture stopped\r\nContent-Length: 0\r\n\r\n');return
                    secure.sendall(b'HTTP/1.1 200 Connection established\r\n\r\n')
                    incoming,outgoing=ssl.MemoryBIO(),ssl.MemoryBIO()
                    target=self.fixtures['other']['context'].wrap_bio(incoming,outgoing,server_side=True)
                    observed['inner_started']=True;handshaken=False
                    while True:
                        try:
                            if not handshaken:target.do_handshake();handshaken=True
                            chunk=target.read(4096)
                            if not chunk:return
                            observed['target_bytes']+=chunk
                            if b'\r\n\r\n' in observed['target_bytes']:
                                body=b'{"origin":"8.8.8.8"}'
                                target.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body)).encode()+b'\r\nConnection: close\r\n\r\n'+body)
                                while outgoing.pending:secure.sendall(outgoing.read())
                                return
                        except ssl.SSLWantReadError:pass
                        finally:
                            while outgoing.pending:secure.sendall(outgoing.read())
                        chunk=secure.recv(16384)
                        if not chunk:return
                        incoming.write(chunk)
            except (OSError,ssl.SSLError) as error:
                observed['peer_error_type']=type(error).__name__
        thread=threading.Thread(target=peer,daemon=True);thread.start()
        try:
            with patch('urllib3.connection.HTTPSConnection._new_conn',return_value=client) as connect, \
                 patch('urllib3.connection._assert_fingerprint',wraps=urllib3.connection._assert_fingerprint) as pin_check, \
                 patch.object(registry,'manager',return_value=manager):
                result=registry.probe('phone1')
                observed['pin_checks']=[{'peer':hashlib.sha256(call.args[0]).hexdigest(),'expected':call.args[1]}
                                        for call in pin_check.call_args_list]
            self.assertEqual(connect.call_count,1)
        finally:
            client.close();thread.join(timeout=5);server.close()
        self.assertFalse(thread.is_alive(),'Synthetic TLS peer must terminate')
        self.assertNotIn(TOKEN,path.read_text(encoding='utf-8'))
        return result,observed

    def test_valid_chain_but_wrong_proxy_pin_receives_no_authentication_bytes(self):
        result,wire=self.run_fixture(outer='other',trust_other_proxy=True)
        self.assertEqual(wire['pin_checks'],[{'peer':certificate_identity(self.fixtures['other']['pem']),
                                            'expected':certificate_identity(self.fixtures['paired']['pem'])}])
        self.assertEqual(wire['proxy_bytes'],b'')
        self.assertEqual(result['state'],'failed')

    def test_untrusted_proxy_certificate_receives_no_authentication_bytes(self):
        result,wire=self.run_fixture(outer='other')
        self.assertEqual(wire['proxy_bytes'],b'')
        self.assertEqual(result['state'],'failed')

    def test_valid_proxy_pin_does_not_trust_an_unverified_target_certificate(self):
        result,wire=self.run_fixture(inner=True)
        self.assertIn(b'CONNECT httpbin.org:443',wire['proxy_bytes'])
        self.assertIn(b'Proxy-Authorization: Basic ',wire['proxy_bytes'])
        self.assertTrue(wire['inner_started']);self.assertEqual(wire['target_bytes'],b'')
        self.assertEqual(result['state'],'failed')

    def test_authenticated_tunnel_keeps_proxy_credentials_out_of_target_request(self):
        result,wire=self.run_fixture(inner=True,trust_target=True)
        authorization=base64.b64encode(('compset:'+TOKEN).encode())
        self.assertIn(authorization,wire['proxy_bytes'])
        self.assertIn(b'GET /ip HTTP/1.1',wire['target_bytes'])
        self.assertIn(b'Host: httpbin.org',wire['target_bytes'])
        self.assertNotIn(b'Proxy-Authorization',wire['target_bytes'])
        self.assertNotIn(authorization,wire['target_bytes'])
        self.assertEqual(result['state'],'healthy')


if __name__=='__main__':unittest.main()
