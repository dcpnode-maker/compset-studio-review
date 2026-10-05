"""Offline proof of geometry, evidence requirements and auditable relaxation."""
from copy import deepcopy
import csv
import json
import math
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from compset.hotel_compset import (build_inventory, coordinate, csv_safe, enrich,
                                  export_inventory, haversine_km, osm_rows)


STAMP = '2026-09-28T09:00:00+00:00'


def fixture(count=1):
    source = {'url': 'https://example.org/hotel', 'observed_at': STAMP,
              'capture_status': 'observed'}
    elements = [{'type': 'node', 'id': 1, 'lat': 30.3486066, 'lon': 78.0617838,
                 'tags': {'name': 'Subject', 'tourism': 'hotel'}}]
    manifest = {'subject_id': 'osm:node:1', 'sources': {'osm': source, 'official': source},
                'observed_at': STAMP, 'properties': [], 'discovery': {}, 'warnings': []}
    for index in range(count):
        identity = index+2
        elements.append({'type': 'node', 'id': identity, 'lat': 30.35+index*0.00001,
                         'lon': 78.06, 'tags': {'name': f'Hotel {identity}', 'tourism': 'hotel'}})
        amenities = {key: True for key in ('restaurant', 'wifi', 'room_service', 'meeting_space')}
        manifest['properties'].append({'id': f'osm:node:{identity}', 'amenities': amenities,
            'field_sources': {f'amenities.{key}': ['official'] for key in amenities},
            'classification_evidence': [{'stars': 3, 'source_id': 'official',
                                         'currentness': 'observed'}]})
    return {'elements': elements}, manifest


class HotelCompsetTests(unittest.TestCase):
    def test_coordinates_validate_and_distance_is_geodesic(self):
        self.assertIsNone(coordinate(True, 90))
        self.assertIsNone(coordinate(float('nan'), 90))
        self.assertIsNone(coordinate(float('inf'), 90))
        self.assertIsNone(coordinate(91, 90))
        self.assertEqual(coordinate(0, 90), 0)
        self.assertAlmostEqual(haversine_km(0, 0, 0, 1), 111.19508, places=4)
        self.assertIsNone(haversine_km(None, 0, 0, 0))

    def test_radius_bands_and_outside_circle_retained(self):
        osm, manifest = fixture(3)
        osm['elements'][1]['lat'] += 0.025
        osm['elements'][2]['lat'] += 0.06
        osm['elements'][3]['lat'] += 0.10
        result = build_inventory(osm, manifest)
        rows = {r['id']: r for r in result['candidates']}
        self.assertEqual(rows['osm:node:2']['distance_band'], '0–5 km')
        self.assertEqual(rows['osm:node:3']['distance_band'], '5–10 km')
        self.assertEqual(rows['osm:node:4']['eligibility'], 'outside_radius')
        self.assertFalse(rows['osm:node:4']['radius_verified'])
        self.assertEqual(len(rows), 4)

    def test_unknown_amenity_is_not_relaxed_into_match(self):
        osm, manifest = fixture()
        del manifest['properties'][0]['amenities']['room_service']
        result = build_inventory(osm, manifest)
        row = next(r for r in result['candidates'] if r['id'] == 'osm:node:2')
        self.assertFalse(row['selected'])
        self.assertIsNone(row['amenities']['room_service'])
        self.assertIn('room_service', row['missing_fields'])
        self.assertEqual(len(result['relaxation']), 3)

    def test_declared_absent_core_service_excluded(self):
        osm, manifest = fixture()
        manifest['properties'][0]['amenities']['room_service'] = False
        result = build_inventory(osm, manifest)
        self.assertEqual(next(r for r in result['candidates'] if r['id'] == 'osm:node:2')['eligibility'], 'different_service')

    def test_above_ten_stops_relaxation(self):
        osm, manifest = fixture(11)
        result = build_inventory(osm, manifest)
        self.assertEqual(result['summary']['selected_count'], 11)
        self.assertEqual(len(result['relaxation']), 1)
        self.assertEqual(result['relaxation'][0]['radius_km'], 5)

    def test_exactly_ten_allows_expansion(self):
        osm, manifest = fixture(11)
        osm['elements'][-1]['lat'] += 0.06
        result = build_inventory(osm, manifest)
        self.assertEqual([x['selected_count'] for x in result['relaxation']], [10, 11])
        self.assertEqual(len(result['relaxation']), 2)

    def test_optional_service_relaxation_does_not_change_collected_facts(self):
        osm, manifest = fixture()
        del manifest['properties'][0]['amenities']['meeting_space']
        result = build_inventory(osm, manifest)
        self.assertEqual([x['selected_count'] for x in result['relaxation']], [0, 0, 1])
        row = next(r for r in result['candidates'] if r['selected'])
        self.assertIsNone(row['amenities']['meeting_space'])
        self.assertTrue(row['selected'])

    def test_name_alone_does_not_merge_distinct_features(self):
        osm, manifest = fixture(2)
        osm['elements'][1]['tags']['name'] = osm['elements'][2]['tags']['name'] = 'Hotel Sunrise'
        result = build_inventory(osm, manifest)
        self.assertEqual(len(result['candidates']), 3)
        self.assertEqual(len(result['selected_ids']), 2)

    def test_non_hotel_and_unnamed_features_never_selected(self):
        osm, manifest = fixture(2)
        osm['elements'][1]['tags']['tourism'] = 'hostel'
        del osm['elements'][2]['tags']['name']
        result = build_inventory(osm, manifest)
        self.assertEqual(result['summary']['selected_count'], 0)
        states = {r['eligibility'] for r in result['candidates']}
        self.assertTrue({'excluded_non_hotel', 'unresolved_identity'}.issubset(states))

    def test_reviews_never_become_star_classification(self):
        osm, manifest = fixture()
        manifest['properties'][0]['classification_evidence'][0]['stars'] = 4.6
        with self.assertRaisesRegex(ValueError, 'Invalid star'):
            build_inventory(osm, manifest)
        manifest['properties'][0]['classification_evidence'] = []
        manifest['properties'][0]['review_evidence'] = [{'source_id': 'official', 'score': 5, 'scale': 5, 'count': 999}]
        result = build_inventory(osm, manifest)
        self.assertEqual(result['summary']['selected_count'], 0)

    def test_conflicting_classifications_are_retained(self):
        osm, manifest = fixture()
        manifest['properties'][0]['classification_evidence'].append({'stars': 4, 'source_id': 'official', 'currentness': 'observed'})
        result = build_inventory(osm, manifest)
        row = next(r for r in result['candidates'] if r['selected'])
        self.assertTrue(row['classification_conflict'])
        self.assertEqual({x['stars'] for x in row['classification_evidence']}, {3, 4})
        manifest['properties'][0]['classification_evidence'].append({'stars': 5, 'source_id': 'official', 'currentness': 'observed'})
        self.assertEqual(build_inventory(osm, manifest)['summary']['selected_count'], 0)

    def test_rejected_metadata_point_cannot_verify_location(self):
        osm, manifest = fixture()
        del osm['elements'][1]['lat']
        manifest['properties'][0]['location_evidence'] = [{'latitude': 23.81, 'longitude': 86.48,
            'source_id': 'official', 'accepted': False, 'method': 'conflicting schema'}]
        result = build_inventory(osm, manifest)
        row = next(r for r in result['candidates'] if r['id'] == 'osm:node:2')
        self.assertIsNone(row['distance_km'])
        self.assertFalse(row['radius_verified'])
        self.assertEqual(row['eligibility'], 'unverified_location')

    def test_field_without_good_source_cannot_be_applied(self):
        osm, manifest = fixture()
        del manifest['properties'][0]['field_sources']['amenities.wifi']
        with self.assertRaisesRegex(ValueError, 'source IDs'):
            build_inventory(osm, manifest)
        osm, manifest = fixture()
        manifest['sources']['official']['capture_status'] = 'blocked'
        with self.assertRaisesRegex(ValueError, 'failed evidence'):
            build_inventory(osm, manifest)

    def test_partial_overpass_response_is_rejected(self):
        osm, manifest = fixture()
        osm['remark'] = 'runtime error: Query timed out'
        with self.assertRaisesRegex(ValueError, 'partial/error'):
            build_inventory(osm, manifest)

    def test_denominator_and_research_identity_must_be_consistent(self):
        osm, manifest = fixture()
        manifest['discovery']['returned_features'] = 999
        with self.assertRaisesRegex(ValueError, 'denominator'):
            build_inventory(osm, manifest)
        manifest['discovery']['returned_features'] = len(osm['elements'])
        manifest['properties'].append(deepcopy(manifest['properties'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate research'):
            build_inventory(osm, manifest)

    def test_way_bbox_center_and_unknown_room_count(self):
        osm, manifest = fixture()
        osm['elements'].append({'type': 'way', 'id': 77, 'center': {'lat': 30.35, 'lon': 78.06},
                                'tags': {'name': 'Mapped Hotel', 'tourism': 'hotel', 'rooms': 'yes'}})
        rows = osm_rows(osm, manifest['sources']['osm'])
        self.assertEqual(rows[-1]['location_evidence'][0]['method'], 'geometry_bbox_center')
        self.assertIsNone(rows[-1]['product']['room_count'])

    def test_inputs_unchanged_rebuild_deterministic_no_quotes(self):
        osm, manifest = fixture()
        before = deepcopy((osm, manifest))
        a, b = build_inventory(osm, manifest), build_inventory(osm, manifest)
        self.assertEqual((osm, manifest), before)
        self.assertEqual(a, b)
        self.assertEqual(a['summary']['live_rate_count'], 0)
        self.assertFalse(a['search']['exhaustive'])
        self.assertIsNone(a['summary']['unique_real_hotel_count'])
        self.assertTrue(all(r['availability_status'] == 'not_collected' for r in a['candidates']))
        self.assertTrue(all(0 <= r['similarity_score']['total'] <= 100 for r in a['candidates']))

    def test_csv_safe_and_history_preserved(self):
        for value in ('=HYPERLINK("evil")', ' +cmd', '\tfoo', '\rformula', '\u00a0@SUM(1)', '-1'):
            self.assertTrue(csv_safe(value).startswith("'"))
        osm, manifest = fixture()
        osm['elements'][1]['tags']['name'] = '=HYPERLINK("https://example.org")'
        artifact = build_inventory(osm, manifest)
        with TemporaryDirectory() as directory:
            first = export_inventory(artifact, directory)
            old = Path(first['history']).read_bytes()
            same = export_inventory(artifact, directory)
            self.assertEqual(first['sha256'], same['sha256'])
            artifact['warnings'] = ['new research']
            second = export_inventory(artifact, directory)
            self.assertNotEqual(first['sha256'], second['sha256'])
            self.assertEqual(Path(first['history']).read_bytes(), old)
            with (Path(directory)/'candidates.csv').open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(next(r for r in rows if r['id'] == 'osm:node:2')['title'].startswith("'="))

    def test_real_research_snapshot_keeps_rejected_points_and_service_closure(self):
        root = Path(__file__).resolve().parents[1]/'data/hotel-compsets/aketa'
        if not (root/'research.json').exists():
            self.skipTest('Local researched artifacts are not distributed with source checkout')
        manifest = json.loads((root/'research.json').read_text(encoding='utf-8'))
        osm = json.loads((root/'raw/osm-accommodation-bbox.json').read_text(encoding='utf-8'))
        result = build_inventory(osm, manifest)
        rows = {r['id']: r for r in result['candidates']}
        self.assertEqual(result['summary']['osm_features_returned'], 63)
        self.assertEqual(len(rows), 70)
        self.assertFalse(rows['osm:node:6147612906']['amenities']['fitness_center'])
        self.assertFalse(rows['osm:node:6147612906']['amenities']['spa'])
        points = rows['osm:node:6147612906']['location_evidence']
        self.assertEqual([p['source_id'] for p in points if p.get('selected_for_distance')], ['ramada'])
        self.assertEqual(rows['official:clarks-inn-niranjanpur']['eligibility'], 'unverified_location')
        self.assertIn('osm:node:10711801692', rows)  # Separate Old Survey Road identity.
        self.assertTrue(any(not p['accepted'] for p in rows['osm:node:6123644590']['location_evidence']))
        self.assertEqual(result['subject']['product']['room_count_currentness'], 'historical_unverified')
        self.assertEqual(result['summary']['selected_count'], 6)


if __name__ == '__main__':
    unittest.main()
