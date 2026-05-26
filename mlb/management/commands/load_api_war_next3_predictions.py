import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mlb.models import MLBApiStatLine, MLBApiWarNext3Prediction


DEFAULT_BATTING_FILE = 'predicted_batting_war_2023_2025.csv'
DEFAULT_PITCHING_FILE = 'predicted_pitching_war_2023_2025.csv'


def _required_text(raw, key, line_number, csv_path):
    value = (raw.get(key) or '').strip()
    if not value:
        raise CommandError(f'Missing {key} value on line {line_number}: {csv_path}')
    return value


def _to_int(value, key, line_number, csv_path):
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise CommandError(f'Invalid {key} value on line {line_number}: {csv_path}') from exc


def _to_float(value, key, line_number, csv_path):
    if value in (None, ''):
        raise CommandError(f'Missing {key} value on line {line_number}: {csv_path}')
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise CommandError(f'Invalid {key} value on line {line_number}: {csv_path}') from exc


class Command(BaseCommand):
    help = 'Load API-facing next-three-year WAR predictions from batting and pitching CSVs.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Delete existing next-three-year WAR prediction rows before loading.',
        )
        parser.add_argument(
            '--base-dir',
            help='Optional base directory containing the data/ folder.',
        )

    def handle(self, *args, **options):
        base_dir = Path(options['base_dir']) if options.get('base_dir') else Path(settings.BASE_DIR)
        batting_path = base_dir / 'data' / DEFAULT_BATTING_FILE
        pitching_path = base_dir / 'data' / DEFAULT_PITCHING_FILE
        if not batting_path.exists():
            raise CommandError(f'Batting WAR next-3 CSV not found: {batting_path}')
        if not pitching_path.exists():
            raise CommandError(f'Pitching WAR next-3 CSV not found: {pitching_path}')

        prediction_rows = (
            self._load_csv(
                batting_path,
                MLBApiStatLine.VIEW_BATTING,
                actual_key='actual_war_next3_avg',
                predicted_key='pred_war_next3_avg',
            )
            + self._load_csv(
                pitching_path,
                MLBApiStatLine.VIEW_PITCHING,
                actual_key='actual_WAR_next3_avg',
                predicted_key='pred_WAR_next3_avg',
            )
        )

        with transaction.atomic():
            if options['replace']:
                deleted_count, _ = MLBApiWarNext3Prediction.objects.all().delete()
                self.stdout.write(f'Deleted {deleted_count} existing WAR next-3 prediction rows.')

            if prediction_rows:
                MLBApiWarNext3Prediction.objects.bulk_create(
                    prediction_rows,
                    batch_size=500,
                    update_conflicts=True,
                    unique_fields=['stat_view', 'season', 'player_name_key', 'team'],
                    update_fields=[
                        'player_name',
                        'name_ascii',
                        'actual_war_next3_avg',
                        'pred_war_next3_avg',
                        'updated_at',
                    ],
                )

        self.stdout.write(
            self.style.SUCCESS(f'Loaded or updated {len(prediction_rows)} WAR next-3 prediction rows.')
        )

    def _load_csv(self, csv_path, stat_view, actual_key, predicted_key):
        objects = []
        seen_keys = set()
        with csv_path.open('r', encoding='utf-8-sig', newline='') as f:
            reader = csv.DictReader(f)
            for line_number, raw in enumerate(reader, start=2):
                player_name_key = _required_text(raw, 'player_name_key', line_number, csv_path)
                player_name = _required_text(raw, 'Name', line_number, csv_path)
                name_ascii = _required_text(raw, 'NameASCII', line_number, csv_path)
                season = _to_int(_required_text(raw, 'Season', line_number, csv_path), 'Season', line_number, csv_path)
                team = _required_text(raw, 'Team', line_number, csv_path).upper()
                actual_war_next3_avg = _to_float(raw.get(actual_key), actual_key, line_number, csv_path)
                pred_war_next3_avg = _to_float(raw.get(predicted_key), predicted_key, line_number, csv_path)

                unique_key = (stat_view, season, player_name_key, team)
                if unique_key in seen_keys:
                    raise CommandError(
                        f'Duplicate prediction key on line {line_number}: {stat_view} {season} {player_name_key} {team}'
                    )
                seen_keys.add(unique_key)

                objects.append(
                    MLBApiWarNext3Prediction(
                        stat_view=stat_view,
                        player_name_key=player_name_key,
                        player_name=player_name,
                        name_ascii=name_ascii,
                        season=season,
                        team=team,
                        actual_war_next3_avg=actual_war_next3_avg,
                        pred_war_next3_avg=pred_war_next3_avg,
                    )
                )
        return objects
