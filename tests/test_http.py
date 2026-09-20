import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'agent'))
from fastapi.testclient import TestClient
import server

class ServerTests(unittest.TestCase):
    def setUp(self):self.client=TestClient(server.app)
    def test_frontend_served(self):
        r=self.client.get('/');self.assertEqual(r.status_code,200);self.assertIn('Start talking',r.text)
    def test_health_without_credentials(self):
        r=self.client.get('/api/config');self.assertEqual(r.status_code,200)
        self.assertNotIn('general_key',r.json());self.assertNotIn('openai_key',r.json())
    def test_missing_keys_fails_closed(self):
        with patch.dict(server.cfg,{'access_token':'','general_key':''}):
            r=self.client.post('/api/offer',json={'sdp':'test','type':'offer'})
            self.assertEqual(r.status_code,503)
    def test_disallowed_origin(self):
        r=self.client.post('/api/offer',json={'sdp':'test','type':'offer'},headers={'origin':'https://unapproved.example'})
        self.assertEqual(r.status_code,403)
    def test_protected_backend_requires_code(self):
        with patch.dict(server.cfg,{'access_token':'test-private-not-provider-key'}):
            r=self.client.post('/api/offer',json={'sdp':'test','type':'offer'})
            self.assertEqual(r.status_code,401)
    def test_remote_origin_needs_protection(self):
        with patch.dict(server.cfg,{'access_token':'','origins':['https://example.test']}):
            r=self.client.post('/api/offer',json={'sdp':'test','type':'offer'},headers={'origin':'https://example.test'})
            self.assertEqual(r.status_code,403)
    def test_unknown_session(self):self.assertEqual(self.client.get('/api/session/not-a-session').status_code,404)
    def test_secrets_not_static(self):self.assertEqual(self.client.get('/agent/.env').status_code,404)

if __name__=='__main__':unittest.main()
