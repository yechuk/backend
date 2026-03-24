import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from mlb.models import MLBApiStatLine


def _to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _to_float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


class Command(BaseCommand):
    help = 'Load data/pitching_mock.csv and data/batting_mock.csv into the DB for /api/teams.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Delete existing MLBApiStatLine rows before loading.',
        )
        parser.add_argument(
            '--base-dir',
            default=str(settings.BASE_DIR),
            help='Project base directory containing the data/ folder.',
        )

    def handle(self, *args, **options):
        if options['replace']:
            deleted_count, _ = MLBApiStatLine.objects.all().delete()
            self.stdout.write(f'Deleted {deleted_count} existing API stat rows.')

        base_dir = Path(options['base_dir'])
        files = {
            MLBApiStatLine.VIEW_PITCHING: base_dir / 'data' / 'pitching_mock.csv',
            MLBApiStatLine.VIEW_BATTING: base_dir / 'data' / 'batting_mock.csv',
        }

        total_upserts = 0
        for stat_view, csv_path in files.items():
            if not csv_path.exists():
                self.stderr.write(self.style.WARNING(f'Skipping missing file: {csv_path}'))
                continue

            with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    normalized = {
                        (key or '').strip(): (value or '').strip()
                        for key, value in row.items()
                        if key
                    }
                    season = _to_int(normalized.get('Season'))
                    team = (normalized.get('Team') or '').upper()
                    external_player_id = normalized.get('PlayerId') or ''
                    player_name = normalized.get('Name') or ''

                    if not season or not team or not external_player_id or not player_name:
                        continue

                    MLBApiStatLine.objects.update_or_create(
                        stat_view=stat_view,
                        season=season,
                        team=team,
                        external_player_id=external_player_id,
                        defaults={
                            'player_name': player_name,
                            'name_ascii': normalized.get('NameASCII', ''),
                            'mlbam_id': normalized.get('MLBAMID', ''),
                            'age': _to_int(normalized.get('Age')),
                            'war': _to_float(normalized.get('WAR')),
                            'raw_stats': normalized,
                        },
                    )
                    total_upserts += 1

        self.stdout.write(self.style.SUCCESS(f'Loaded or updated {total_upserts} mock API rows.'))
