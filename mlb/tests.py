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

    def test_team_players_endpoint_rounds_batting_wrc_plus(self):
        MLBApiStatLine.objects.create(
            stat_view='batting',
            season=2023,
            team='BAL',
            player_name='Adley Rutschman',
            name_ascii='Adley Rutschman',
            external_player_id='20001',
            mlbam_id='668939',
            age=25,
            war=5.4,
            raw_stats={
                'Season': '2023',
                'Name': 'Adley Rutschman',
                'Team': 'BAL',
                'G': '154',
                'PA': '687',
                'HR': '20',
                'ISO': '0.192',
                'BB%': '0.133',
                'K%': '0.178',
                'wOBA': '0.374',
                'wRC+': '127.6',
                'SB': '1',
                'BABIP': '0.317',
                'Age': '25',
                'WAR': '5.4',
                'NameASCII': 'Adley Rutschman',
                'PlayerId': '20001',
                'MLBAMID': '668939',
            },
        )

        response = self.client.get('/api/teams/BAL/players/?season=2023&view=batting')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        adley = next(player for player in payload['players'] if player['player_id'] == '20001')
        self.assertEqual(adley['stats']['wrc_plus'], 128)


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
        MLBApiStatLine.objects.create(
            stat_view='pitching',
            season=2022,
            team='ATL',
            player_name='A.J. Minter',
            name_ascii='A.J. Minter',
            external_player_id='30001',
            mlbam_id='621345',
            age=28,
            war=1.8,
            raw_stats={
                'Season': '2022',
                'Name': 'A.J. Minter',
                'Team': 'ATL',
                'HR/9': '0.70',
                'K%': '0.313',
                'BB': '24',
                'IP': '70.0',
                'FIP': '2.53',
                'GS': '0',
                'G': '61',
                'Age': '28',
                'WAR': '1.8',
                'NameASCII': 'A.J. Minter',
                'PlayerId': '30001',
                'MLBAMID': '621345',
            },
        )
        MLBApiStatLine.objects.create(
            stat_view='batting',
            season=2022,
            team='ATL',
            player_name='Dansby Swanson',
            name_ascii='Dansby Swanson',
            external_player_id='30002',
            mlbam_id='621020',
            age=28,
            war=6.4,
            raw_stats={
                'Season': '2022',
                'Name': 'Dansby Swanson',
                'Team': 'ATL',
                'G': '162',
                'PA': '696',
                'HR': '25',
                'ISO': '0.179',
                'BB%': '0.087',
                'K%': '0.261',
                'wOBA': '0.330',
                'wRC+': '116',
                'SB': '18',
                'BABIP': '0.348',
                'Age': '28',
                'WAR': '6.4',
                'NameASCII': 'Dansby Swanson',
                'PlayerId': '30002',
                'MLBAMID': '621020',
            },
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
        self.assertEqual(payload['stat_seasons'], {'batting': 2022, 'pitching': 2022})

        players_by_name = {player['player_name']: player for player in payload['players']}
        self.assertEqual(
            players_by_name['A.J. Minter']['photo_url'],
            '/api/rosters/ATL/players/621345/photo/?season=2022',
        )
        self.assertIsNone(players_by_name['Dansby Swanson']['photo_url'])
        self.assertEqual(players_by_name['A.J. Minter']['pitching']['mlbam_id'], '621345')
        self.assertEqual(players_by_name['A.J. Minter']['pitching']['stats']['games'], 61)
        self.assertIsNone(players_by_name['A.J. Minter']['batting'])
        self.assertEqual(players_by_name['Dansby Swanson']['batting']['mlbam_id'], '621020')
        self.assertEqual(players_by_name['Dansby Swanson']['batting']['stats']['home_runs'], 25)
        self.assertIsNone(players_by_name['Dansby Swanson']['pitching'])

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
    def test_command_loads_csv_rows_into_db(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / 'data'
            data_dir.mkdir(parents=True, exist_ok=True)

            pitching_csv_body = (
                'Season,Name,Team,HR/9,K%,BB,IP,FIP,GS,G,Age,WAR,NameASCII,PlayerId,MLBAMID\n'
                '2023,Kyle Gibson,BAL,1.078125,0.19454771,55,192.0,4.13,33,33,35,2.66114687919617,Kyle Gibson,10123,502043\n'
            )
            batting_csv_body = (
                'Season,Name,Team,G,PA,HR,ISO,BB%,K%,wOBA,wRC+,SB,BABIP,Age,WAR,NameASCII,PlayerId,MLBAMID\n'
                '2023,Adley Rutschman,BAL,154,687,20,0.192,0.133,0.178,0.374,128,1,0.317,25,5.4,Adley Rutschman,20001,668939\n'
            )
            (data_dir / 'pitching.csv').write_text(pitching_csv_body, encoding='utf-8')
            (data_dir / 'batting.csv').write_text(batting_csv_body, encoding='utf-8')

            call_command('load_mock_team_api_data', '--replace', base_dir=str(temp_dir), verbosity=0)

        self.assertEqual(MLBApiStatLine.objects.count(), 2)
        self.assertTrue(MLBApiStatLine.objects.filter(stat_view='pitching', mlbam_id='502043').exists())
        self.assertTrue(MLBApiStatLine.objects.filter(stat_view='batting', mlbam_id='668939').exists())


class LoadRosterPhotosCommandTests(TestCase):
    def test_command_loads_photo_rows_into_db(self):
        with TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / 'data' / 'Atlanta Braves'
            data_dir.mkdir(parents=True, exist_ok=True)
            (data_dir / 'A.J. Minter.jpeg').write_bytes(b'photo-bytes')

            call_command('load_roster_photos', '--replace', base_dir=str(temp_dir), verbosity=0)

        photo = MLBRosterPhoto.objects.get(team_name='Atlanta Braves', normalized_player_name='ajminter')
        self.assertEqual(photo.player_name, 'A.J. Minter')
        self.assertEqual(photo.content_type, 'image/jpeg')
        self.assertEqual(bytes(photo.image_data), b'photo-bytes')
