import csv
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mlb.models import MLBRosterEntry

BASE_URL = 'https://statsapi.mlb.com/api/v1'


def _to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_text(value):
    return str(value).strip() if value is not None else ''


def fetch_json(path, params):
    query = urlencode(params)
    url = f'{BASE_URL}{path}?{query}'

    try:
        with urlopen(url, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise CommandError(f'HTTP error {exc.code} while requesting {url}') from exc
    except URLError as exc:
        raise CommandError(f'Network error while requesting {url}: {exc.reason}') from exc


class Command(BaseCommand):
    help = 'Load MLB roster snapshot data from data/mlb_rosters_<season>.csv or .json into the DB.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--season',
            type=int,
            default=2022,
            help='Season to load. Used to infer the default file path.',
        )
        parser.add_argument(
            '--file',
            help='Explicit roster file path (.csv or .json). Defaults to data/mlb_rosters_<season>.csv.',
        )
        parser.add_argument(
            '--replace-season',
            action='store_true',
            help='Delete existing rows for the target season before loading.',
        )
        parser.add_argument(
            '--from-api',
            action='store_true',
            help='Fetch the roster directly from MLB StatsAPI instead of reading a local file.',
        )

    def handle(self, *args, **options):
        season = options['season']

        if options['replace_season']:
            deleted_count, _ = MLBRosterEntry.objects.filter(season=season).delete()
            self.stdout.write(f'Deleted {deleted_count} existing roster rows for {season}.')

        if options['from_api']:
            rows = self._load_from_api(season)
            source_label = f'MLB StatsAPI for {season}'
        else:
            input_path = self._resolve_input_path(options.get('file'), season)
            if input_path.suffix.lower() == '.csv':
                rows = self._load_csv(input_path)
            elif input_path.suffix.lower() == '.json':
                rows = self._load_json(input_path)
            else:
                raise CommandError(f'Unsupported file type: {input_path.suffix}')
            source_label = str(input_path)

        objects = []
        with transaction.atomic():
            for row in rows:
                row_season = _to_int(row.get('season'))
                team_id = _to_int(row.get('team_id'))
                player_id = _to_int(row.get('player_id'))
                player_name = _to_text(row.get('player_name'))

                if not row_season or not team_id or not player_id or not player_name:
                    continue

                objects.append(
                    MLBRosterEntry(
                        season=row_season,
                        team_id=team_id,
                        player_id=player_id,
                        team_name=_to_text(row.get('team_name')),
                        team_abbreviation=_to_text(row.get('team_abbreviation')),
                        league_name=_to_text(row.get('league_name')),
                        division_name=_to_text(row.get('division_name')),
                        player_name=player_name,
                        player_link=_to_text(row.get('player_link')),
                        jersey_number=_to_text(row.get('jersey_number')),
                        position_code=_to_text(row.get('position_code')),
                        position_name=_to_text(row.get('position_name')),
                        position_type=_to_text(row.get('position_type')),
                        position_abbreviation=_to_text(row.get('position_abbreviation')),
                        status_code=_to_text(row.get('status_code')),
                        status_description=_to_text(row.get('status_description')),
                        raw_data=row,
                    )
                )

            if objects:
                MLBRosterEntry.objects.bulk_create(
                    objects,
                    batch_size=500,
                    update_conflicts=True,
                    unique_fields=['season', 'team_id', 'player_id'],
                    update_fields=[
                        'team_name',
                        'team_abbreviation',
                        'league_name',
                        'division_name',
                        'player_name',
                        'player_link',
                        'jersey_number',
                        'position_code',
                        'position_name',
                        'position_type',
                        'position_abbreviation',
                        'status_code',
                        'status_description',
                        'raw_data',
                        'updated_at',
                    ],
                )

        self.stdout.write(self.style.SUCCESS(f'Loaded or updated {len(objects)} roster rows from {source_label}.'))

    def _resolve_input_path(self, explicit_path, season):
        if explicit_path:
            path = Path(explicit_path)
        else:
            path = Path(settings.BASE_DIR) / 'data' / f'mlb_rosters_{season}.csv'

        if not path.exists():
            raise CommandError(f'Input file not found: {path}')

        return path

    def _load_csv(self, path):
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            return [
                {(key or '').strip(): _to_text(value) for key, value in row.items() if key}
                for row in reader
            ]

    def _load_json(self, path):
        payload = json.loads(path.read_text(encoding='utf-8'))
        rows = []

        for team_block in payload:
            season = team_block.get('season')
            team = team_block.get('team') or {}
            for entry in team_block.get('roster', []):
                person = entry.get('person') or {}
                position = entry.get('position') or {}
                status = entry.get('status') or {}
                rows.append(
                    {
                        'season': season,
                        'team_id': team.get('id'),
                        'team_name': team.get('name'),
                        'team_abbreviation': team.get('abbreviation'),
                        'league_name': team.get('league'),
                        'division_name': team.get('division'),
                        'player_id': person.get('id'),
                        'player_name': person.get('fullName'),
                        'player_link': person.get('link'),
                        'jersey_number': entry.get('jerseyNumber'),
                        'position_code': position.get('code'),
                        'position_name': position.get('name'),
                        'position_type': position.get('type'),
                        'position_abbreviation': position.get('abbreviation'),
                        'status_code': status.get('code'),
                        'status_description': status.get('description'),
                    }
                )

        return rows

    def _load_from_api(self, season):
        teams_payload = fetch_json('/teams', {'sportId': 1, 'season': season})
        teams = [team for team in teams_payload.get('teams', []) if team.get('active')]
        rows = []

        for team in teams:
            roster_payload = fetch_json(f"/teams/{team['id']}/roster", {'season': season})
            for entry in roster_payload.get('roster', []):
                person = entry.get('person') or {}
                position = entry.get('position') or {}
                status = entry.get('status') or {}
                rows.append(
                    {
                        'season': season,
                        'team_id': team.get('id'),
                        'team_name': team.get('name'),
                        'team_abbreviation': team.get('abbreviation'),
                        'league_name': (team.get('league') or {}).get('name'),
                        'division_name': (team.get('division') or {}).get('name'),
                        'player_id': person.get('id'),
                        'player_name': person.get('fullName'),
                        'player_link': person.get('link'),
                        'jersey_number': entry.get('jerseyNumber'),
                        'position_code': position.get('code'),
                        'position_name': position.get('name'),
                        'position_type': position.get('type'),
                        'position_abbreviation': position.get('abbreviation'),
                        'status_code': status.get('code'),
                        'status_description': status.get('description'),
                    }
                )

        return rows
