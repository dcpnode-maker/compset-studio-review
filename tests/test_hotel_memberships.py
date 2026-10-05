from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from compset.hotel_memberships import load_configured_labels
from compset.intelligence import _revision


class HotelMembershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'hotel-portfolio' / 'configured-compset-labels.json'
        self.path.parent.mkdir()
        self.profiles = [{'id': 'lighthouse:123', 'roles': ['subject']}]
        self.raw = {'schema_version': 'lighthouse-configured-labels.v1',
            'identity_status': 'name_only_competitors_unresolved_provider_ids',
            'observed_at': '2026-09-28T09:57:29Z',
            'source_url': 'https://app.mylighthouse.com/hotel/123/rates?session=private',
            'subjects': [{'subject_id': 'lighthouse:123', 'competitor_labels': ['Peer A', 'Peer B']}]}

    def read(self):
        self.path.write_text(json.dumps(self.raw), encoding='utf-8')
        return load_configured_labels(self.root, self.profiles)

    def test_labels_remain_names_without_created_identity_or_price(self):
        result = self.read()
        self.assertEqual(result['observed_membership_count'], 2)
        self.assertEqual(result['verified_competitor_id_count'], 0)
        self.assertEqual(result['rates_collected_count'], 0)
        self.assertEqual(result['groups'][0]['competitor_labels'], ['Peer A', 'Peer B'])
        self.assertNotIn('private', json.dumps(result))
        self.assertNotIn('competitor_id', result['groups'][0])

    def test_unknown_or_repeated_subject_never_attaches_names_to_another_hotel(self):
        self.raw['subjects'][0]['subject_id'] = 'lighthouse:999'
        self.assertEqual(self.read()['status'], 'read_error')
        self.raw['subjects'][0]['subject_id'] = 'lighthouse:123'
        self.raw['subjects'] *= 2
        self.assertEqual(self.read()['groups'], [])

    def test_nested_secrets_and_oversized_or_malformed_labels_fail_closed(self):
        original = deepcopy(self.raw)
        for label in ({'cookie': 'canary'}, 'A' * 251, 'Peer\nInjected'):
            self.raw = deepcopy(original)
            self.raw['subjects'][0]['competitor_labels'] = [label]
            result = self.read()
            self.assertEqual(result['status'], 'read_error')
            self.assertNotIn('canary', json.dumps(result))
        self.raw = original
        self.raw['account_cookie'] = 'canary'
        self.assertNotIn('canary', json.dumps(self.read()))

    def test_missing_file_is_unknown_and_new_observation_changes_revision(self):
        self.assertEqual(load_configured_labels(self.root, self.profiles)['status'], 'not_observed')
        before = _revision(self.root)
        self.read()
        self.assertNotEqual(_revision(self.root), before)


if __name__ == '__main__':
    unittest.main()
