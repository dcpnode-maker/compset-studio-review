"""Independent review of label-only membership projection; no source requests."""
from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from compset.hotel_memberships import load_configured_labels
from compset import intelligence


class HotelMembershipReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'hotel-portfolio' / 'configured-compset-labels.json'
        self.path.parent.mkdir()
        self.profiles = [{'id': 'lighthouse:123', 'title': 'Subject one', 'roles': ['subject']},
                         {'id': 'lighthouse:456', 'title': 'Subject two', 'roles': ['subject']},
                         {'id': 'lighthouse:789', 'title': 'Known competitor', 'roles': ['competitor']}]
        self.raw = {'schema_version': 'lighthouse-configured-labels.v1',
                    'identity_status': 'name_only_competitors_unresolved_provider_ids',
                    'observed_at': '2026-09-28T09:57:29Z',
                    'source_url': 'https://app.mylighthouse.com/hotel/123/rates?token=SECRET_CANARY#fragment',
                    'subjects': [{'subject_id': 'lighthouse:123', 'competitor_labels': ['Known competitor', 'Peer two']}]}

    def write(self, raw=None):
        self.path.write_text(json.dumps(self.raw if raw is None else raw), encoding='utf-8')

    def project(self, full=False):
        portfolio = {'profiles': deepcopy(self.profiles), 'coverage': {}, 'relations': [], 'warnings': []}
        with patch('compset.hotel_portfolio.load_hotel_portfolio', return_value=portfolio):
            return intelligence.hotel(self.root) if full else intelligence.summary(self.root)

    def test_unknown_counts_are_not_observed_zero_and_explicit_empty_group_is_zero(self):
        profiles = self.project()['hotel']['portfolio']['profiles']
        self.assertIsNone(profiles[0]['configured_label_count'])
        self.assertEqual(profiles[0]['configured_label_status'], 'not_observed')
        self.raw['subjects'][0]['competitor_labels'] = []
        self.write()
        profiles = self.project()['hotel']['portfolio']['profiles']
        self.assertEqual(profiles[0]['configured_label_count'], 0)
        self.assertEqual(profiles[0]['configured_label_status'], 'observed_name_only')
        self.assertIsNone(profiles[1]['configured_label_count'])
        self.assertEqual(profiles[1]['configured_label_status'], 'not_observed')

    def test_malformed_or_unknown_subject_cannot_relabel_other_hotel(self):
        for subject_id in ('lighthouse:999', 'lighthouse:789', 'aketa', '../123'):
            self.raw['subjects'][0]['subject_id'] = subject_id
            self.write()
            payload = self.project(full=True)
            self.assertEqual(payload['portfolio']['configured_labels']['status'], 'read_error')
            self.assertEqual(payload['portfolio']['configured_labels']['groups'], [])
            profiles = self.project()['hotel']['portfolio']['profiles']
            self.assertIsNone(profiles[0]['configured_label_count'])
            self.assertEqual(profiles[0]['configured_label_status'], 'read_error')

    def test_exact_name_match_creates_no_identity_link_rate_or_collection_mapping(self):
        self.raw['subjects'][0].update(competitor_id='lighthouse:789', price=100, cookie='SECRET_CANARY')
        self.raw['cookie'] = 'SECRET_CANARY'
        self.write()
        payload = self.project(full=True)['portfolio']
        group = payload['configured_labels']['groups'][0]
        self.assertEqual(group['competitor_labels'], ['Known competitor', 'Peer two'])
        self.assertEqual(payload['relations'], [])
        self.assertEqual(payload['configured_labels']['verified_competitor_id_count'], 0)
        self.assertEqual(payload['configured_labels']['rates_collected_count'], 0)
        self.assertEqual(set(group), {'subject_id', 'competitor_labels', 'identity_status', 'observed_at', 'source_url'})
        self.assertNotIn('SECRET_CANARY', json.dumps(payload))
        self.assertEqual(group['source_url'], 'https://app.mylighthouse.com/hotel/123/rates')
        self.assertEqual(group['observed_at'], self.raw['observed_at'])

    def test_edit_and_delete_change_revision_and_never_reuse_stale_groups(self):
        self.write()
        first = self.project(full=True)
        before = self.path.stat()
        self.raw['subjects'][0]['competitor_labels'][1] = 'Peer new'
        self.write()
        os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000))
        second = self.project(full=True)
        self.assertNotEqual(first['revision'], second['revision'])
        self.assertEqual(second['portfolio']['configured_labels']['groups'][0]['competitor_labels'][-1], 'Peer new')
        self.assertEqual(first['portfolio']['configured_labels']['groups'][0]['competitor_labels'][-1], 'Peer two')
        self.path.unlink()
        third = self.project(full=True)
        self.assertNotEqual(second['revision'], third['revision'])
        self.assertEqual(third['portfolio']['configured_labels']['status'], 'not_observed')
        self.assertEqual(third['portfolio']['configured_labels']['groups'], [])

    def test_bad_source_credentials_schema_and_naive_timestamp_fail_closed(self):
        variants = [('source_url', 'https://user:SECRET_CANARY@app.mylighthouse.com/hotel/123'),
                    ('source_url', 'https://app.mylighthouse.com/token/SECRET_CANARY'),
                    ('source_url', 'https://app.mylighthouse.com.attacker.test/hotel/123'),
                    ('observed_at', '2026-09-28T09:57:29'),
                    ('schema_version', 'untrusted-schema')]
        for key, value in variants:
            raw = deepcopy(self.raw)
            raw[key] = value
            self.write(raw)
            result = load_configured_labels(self.root, self.profiles)
            self.assertEqual(result['status'], 'read_error')
            self.assertEqual(result['groups'], [])
            self.assertNotIn('SECRET_CANARY', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
