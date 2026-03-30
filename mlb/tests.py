from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import TestCase

from .models import MLBApiStatLine, MLBRosterEntry, MLBRosterPhoto


class TeamApiTests(TestCase):
    def setUp(self):
        MLBApiStatLine.objects.create(
            stat_view='pitching',
            season=2023,
            team='BAL',
            player_name='Kyle Gibson',
            name_ascii='Kyle Gibson',
            external_player_id='10123',
            mlbam_id='502043',
            age=35,
            war=2.66114687919617,
            raw_stats={
                'Season': '2023',
                'Name': 'Kyle Gibson',
                'Team': 'BAL',
                'HR/9': '1.078125',
                'K%': '0.19454771',
                'BB': '55',
                'IP': '192.0',
                'FIP': '4.13004035949707',
                'GS': '33',
                'G': '33',
                'Age': '35',
                'WAR': '2.66114687919617',
                'NameASCII': 'Kyle Gibson',
                'PlayerId': '10123',
                'MLBAMID': '502043',
            },
        )
        MLBApiStatLine.objects.create(
            stat_view='pitching',
            season=2023,
            team='ATL',
            player_name='Max Fried',
            name_ascii='Max Fried',
            external_player_id='20456',
            mlbam_id='608331',
            age=29,
            war=3.5,
            raw_stats={
                'Season': '2023',
                'Name': 'Max Fried',
                'Team': 'ATL',
                'HR/9': '0.8',
                'K%': '0.2400',
                'BB': '40',
                'IP': '180.0',
                'FIP': '3.10',
                'GS': '30',
                'G': '30',
                'Age': '29',
                'WAR': '3.5',
                'NameASCII': 'Max Fried',
                'PlayerId': '20456',
                'MLBAMID': '608331',
            },
        )

    def test_team_list_endpoint_returns_2023_pitching_teams(self):
        response = self.client.get('/api/teams/?season=2023&view=pitching')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['season'], 2023)
        self.assertEqual(payload['view'], 'pitching')
        self.assertTrue(any(team['code'] == 'BAL' for team in payload['teams']))

    def test_team_players_endpoint_returns_baltimore_pitchers(self):
        response = self.client.get('/api/teams/BAL/players/?season=2023&view=pitching')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['team'], 'BAL')
        self.assertTrue(any(player['player_id'] == '10123' for player in payload['players']))

    def test_team_player_detail_endpoint_returns_kyle_gibson(self):
        response = self.client.get('/api/teams/BAL/players/10123/?season=2023&view=pitching')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['player']['name'], 'Kyle Gibson')
        self.assertEqual(payload['player']['team'], 'BAL')
        self.assertEqual(payload['player']['stats']['games_started'], 33)


class RosterApiTests(TestCase):
    def setUp(self):
        MLBRosterPhoto.objects.create(
            team_name='Atlanta Braves',
            player_name='A.J. Minter',
            normalized_player_name='ajminter',
            original_filename='A.J. Minter.jpeg',
            content_type='image/jpeg',
            image_data=b'fake-image-bytes',
            byte_size=16,
        )
        MLBRosterEntry.objects.create(
            season=2022,
            team_id=144,
            team_name='Atlanta Braves',
            team_abbreviation='ATL',
            league_name='National League',
            division_name='National League East',
            player_id=621345,
            player_name='A.J. Minter',
            player_link='/api/v1/people/621345',
            jersey_number='33',
            position_code='1',
            position_name='Pitcher',
            position_type='Pitcher',
            position_abbreviation='P',
            status_code='A',
            status_description='Active',
            raw_data={},
        )
        MLBRosterEntry.objects.create(
            season=2022,
            team_id=144,
            team_name='Atlanta Braves',
            team_abbreviation='ATL',
            league_name='National League',
            division_name='National League East',
            player_id=621020,
            player_name='Dansby Swanson',
            player_link='/api/v1/people/621020',
            jersey_number='7',
            position_code='6',
            position_name='Shortstop',
            position_type='Infielder',
            position_abbreviation='SS',
            status_code='A',
            status_description='Active',
            raw_data={},
        )
        MLBRosterEntry.objects.create(
            season=2022,
            team_id=110,
            team_name='Baltimore Orioles',
            team_abbreviation='BAL',
            league_name='American League',
            division_name='American League East',
            player_id=660271,
            player_name='Adley Rutschman',
            player_link='/api/v1/people/660271',
            jersey_number='35',
            position_code='2',
            position_name='Catcher',
            position_type='Catcher',
            position_abbreviation='C',
            status_code='A',
            status_description='Active',
            raw_data={},
        )

    def test_roster_list_endpoint_returns_2022_teams(self):
        response = self.client.get('/api/rosters/?season=2022')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['season'], 2022)
        self.assertEqual(payload['count'], 2)
        self.assertTrue(any(team['code'] == 'ATL' for team in payload['teams']))

    def test_team_roster_endpoint_returns_atlanta_roster(self):
        response = self.client.get('/api/rosters/ATL/?season=2022')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['team'], 'ATL')
        self.assertEqual(payload['count'], 2)
        self.assertTrue(any(player['player_name'] == 'A.J. Minter' for player in payload['players']))
        players_by_name = {player['player_name']: player for player in payload['players']}
        self.assertEqual(
            players_by_name['A.J. Minter']['photo_url'],
            '/api/rosters/ATL/players/621345/photo/?season=2022',
        )
        self.assertIsNone(players_by_name['Dansby Swanson']['photo_url'])

    def test_roster_player_photo_endpoint_returns_image(self):
        response = self.client.get('/api/rosters/ATL/players/621345/photo/?season=2022')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertEqual(response.content, b'fake-image-bytes')

    def test_roster_player_photo_endpoint_returns_404_when_missing(self):
        MLBRosterPhoto.objects.all().delete()

        response = self.client.get('/api/rosters/ATL/players/621345/photo/?season=2022')

        self.assertEqual(response.status_code, 404)


class LoadMockTeamApiDataCommandTests(TestCase):
    def test_command_loads_mock_rows_into_db(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / 'data'
            data_dir.mkdir(parents=True, exist_ok=True)

            csv_body = (
                'Season,Name,Team,HR/9,K%,BB,IP,FIP,GS,G,Age,WAR,NameASCII,PlayerId,MLBAMID\n'
                '2023,Kyle Gibson,BAL,1.078125,0.19454771,55,192.0,4.13,33,33,35,2.66114687919617,Kyle Gibson,10123,502043\n'
            )
            (data_dir / 'pitching_mock.csv').write_text(csv_body, encoding='utf-8')
            (data_dir / 'batting_mock.csv').write_text(csv_body, encoding='utf-8')

            call_command('load_mock_team_api_data', '--replace', base_dir=str(temp_dir), verbosity=0)

        self.assertEqual(MLBApiStatLine.objects.count(), 2)
        self.assertTrue(MLBApiStatLine.objects.filter(stat_view='pitching', external_player_id='10123').exists())


class LoadRosterPhotosCommandTests(TestCase):
    def test_command_loads_photo_rows_into_db(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / 'data' / 'Atlanta Braves'
            nested_dir = data_dir / 'Atlanta Braves'
            nested_dir.mkdir(parents=True, exist_ok=True)
            (nested_dir / 'A.J. Minter.jpeg').write_bytes(b'photo-bytes')

            call_command('load_roster_photos', '--replace', base_dir=str(temp_dir), verbosity=0)

        photo = MLBRosterPhoto.objects.get(team_name='Atlanta Braves', normalized_player_name='ajminter')
        self.assertEqual(photo.player_name, 'A.J. Minter')
        self.assertEqual(photo.content_type, 'image/jpeg')
        self.assertEqual(bytes(photo.image_data), b'photo-bytes')
