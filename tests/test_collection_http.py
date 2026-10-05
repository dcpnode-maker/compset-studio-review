import hashlib
import json
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import sqlite3
import unittest
from contextlib import closing
from unittest.mock import patch
from compset.server import Handler
from compset.collection_control import save


class CollectionHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.token='a'*43
        self.config={'base_root':str(self.root/'base'),'collector_root':str(self.root/'collector'),
            'proxy_runtime_root':str(self.root/'proxy'),'control_root':str(self.root/'collection-control'),
            'public_origin':'https://compset.example','control_token_sha256':hashlib.sha256(self.token.encode()).hexdigest()}
        save(self.root/'collection-control/config.json',self.config)
        self.patch=patch('compset.server.DATA',self.root);self.patch.start();self.addCleanup(self.patch.stop)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.cleanup_server)

    def cleanup_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2)

    def request(self,path,body,cookie=None):
        h={'Content-Type':'application/json','X-CompSet-Request':'dashboard-v1','Origin':'https://compset.example'}
        if cookie:h['Cookie']=cookie
        conn=HTTPConnection('127.0.0.1',self.server.server_port)
        conn.request('POST',path,json.dumps(body),h);r=conn.getresponse()
        result=(r.status,dict(r.getheaders()),r.read());conn.close();return result

    def test_spoofed_public_headers_cannot_queue_repair(self):
        with patch('compset.collection_control.request_refresh') as refresh:
            self.assertEqual(self.request('/api/collection/refresh',{'dataset':'dubai'})[0],401)
        refresh.assert_not_called()

    def test_owner_exchange_then_refresh(self):
        status,headers,_=self.request('/api/collection/session',{'token':self.token})
        self.assertEqual(status,200);cookie=headers['Set-Cookie']
        self.assertIn('HttpOnly',cookie);self.assertIn('Secure',cookie);self.assertIn('SameSite=Strict',cookie)
        with patch('compset.collection_control.request_refresh',return_value={'state':'already_running'}) as refresh:
            self.assertEqual(self.request('/api/collection/refresh',{'dataset':'dubai'},cookie.split(';')[0])[0],202)
        refresh.assert_called_once()

    def test_invalid_session_never_sets_cookie(self):
        status,headers,_=self.request('/api/collection/session',{'token':'b'*43})
        self.assertEqual(status,401);self.assertNotIn('Set-Cookie',headers)

    def test_saved_owner_session_is_recognized_without_url_token(self):
        for cookie,expected in ((None,False),('compset_control='+self.token,True)):
            conn=HTTPConnection('127.0.0.1',self.server.server_port)
            conn.request('GET','/api/collection/session',headers={'Cookie':cookie} if cookie else {})
            response=conn.getresponse()
            self.assertEqual(json.loads(response.read())['owner'],expected)
            conn.close()

    def test_unreadable_database_returns_sanitized_error(self):
        with patch('compset.live_collection_data.listings',side_effect=sqlite3.OperationalError('private-path locked')):
            conn=HTTPConnection('127.0.0.1',self.server.server_port)
            conn.request('GET','/api/collection/listings')
            response=conn.getresponse();body=response.read()
            self.assertEqual(response.status,503);self.assertNotIn(b'private-path',body)
            conn.close()

    def test_map_route_is_read_only_and_returns_query_filtered_points(self):
        database=Path(self.config['base_root'])/'market.sqlite';database.parent.mkdir(parents=True)
        with closing(sqlite3.connect(database)) as db:
            db.executescript('''CREATE TABLE observations(observation_id TEXT PRIMARY KEY,provider TEXT,
              listing_id TEXT,kind TEXT,captured_at TEXT,context_json TEXT);
              CREATE TABLE profile_fields(observation_id TEXT,field_name TEXT,status TEXT,value_json TEXT);''')
            db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?)',
                ('latest','airbnb','123','profile','2026-01-01T00:00:00Z','{}'))
            db.executemany('INSERT INTO profile_fields VALUES(?,?,?,?)',[
                ('latest','title','observed',json.dumps('Dubai flat')),
                ('latest','bedrooms','observed','2'),
                ('latest','latitude','observed','25.2'),
                ('latest','longitude','observed','55.3'),
                ('latest','guest_capacity','observed','4')])
            db.commit()
        before=database.read_bytes()
        conn=HTTPConnection('127.0.0.1',self.server.server_port)
        conn.request('GET','/api/collection/map?query=Dubai&bedrooms=2&limit=2000',
            headers={'Origin':'https://compset.example'})
        response=conn.getresponse();body=json.loads(response.read());conn.close()
        self.assertEqual(response.status,200)
        self.assertEqual((body['total'],body['mapped_total'],body['unmapped_total']),(1,1,0))
        self.assertEqual(body['points'][0]['listing_id'],'123')
        self.assertIsNone(body['next_offset'])
        self.assertEqual(database.read_bytes(),before)


if __name__=='__main__':unittest.main()
