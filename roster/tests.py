import json
from decimal import Decimal

from django.test import TestCase

from .models import Contract, Player


class PlayerApiTests(TestCase):
    def setUp(self):
        self.player = Player.objects.create(
            name='Kim Minsoo',
            position='Pitcher',
            jersey_number=11,
            years_to_retirement=4,
            status='active',
        )
        Contract.objects.create(
            player=self.player,
            total_value=Decimal('2500000.00'),
            guaranteed_ratio=Decimal('0.80'),
            years=3,
            start_year=2026,
        )

    def test_list_players_returns_json_payload(self):
        response = self.client.get('/api/players/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['count'], 1)
        self.assertEqual(response.json()['players'][0]['name'], 'Kim Minsoo')
        self.assertEqual(response.json()['players'][0]['contract']['years'], 3)

    def test_create_player_with_contract(self):
        payload = {
            'name': 'Lee Jihun',
            'position': 'Catcher',
            'jersey_number': 27,
            'years_to_retirement': 6,
            'status': 'pending',
            'contract': {
                'total_value': '4000000.00',
                'guaranteed_ratio': '0.75',
                'years': 4,
                'start_year': 2027,
            },
        }

        response = self.client.post(
            '/api/players/',
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Player.objects.count(), 2)
        created_player = Player.objects.get(name='Lee Jihun')
        self.assertEqual(created_player.contract.years, 4)

    def test_patch_player_and_delete_contract(self):
        payload = {
            'status': 'released',
            'contract': None,
        }

        response = self.client.patch(
            f'/api/players/{self.player.pk}/',
            data=json.dumps(payload),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self.player.refresh_from_db()
        self.assertEqual(self.player.status, 'released')
        self.assertFalse(Contract.objects.filter(player=self.player).exists())

    def test_options_request_returns_cors_headers(self):
        response = self.client.options(
            '/api/players/',
            HTTP_ORIGIN='http://localhost:5173',
            HTTP_ACCESS_CONTROL_REQUEST_METHOD='POST',
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS='Content-Type',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Access-Control-Allow-Origin'], 'http://localhost:5173')
        self.assertIn('POST', response['Access-Control-Allow-Methods'])

    def test_teams_endpoint_returns_ohtani_image_without_query_params(self):
        response = self.client.get('/api/teams')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        self.assertNotIn('Cross-Origin-Opener-Policy', response.headers)
        self.assertGreater(len(b''.join(response.streaming_content)), 0)
