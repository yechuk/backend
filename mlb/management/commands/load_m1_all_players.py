from decimal import Decimal
from pathlib import Path
import unicodedata

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook

from mlb.models import MLBApiAavPrediction, MLBApiStatLine


SOURCE_LABEL = 'M1'
SOURCE_FILE = 'M1_2022_전체선수.xlsx'
DEFAULT_SEASON = 2022
BATTER_SHEET = '타자'
PITCHER_SHEET = '투수'


def _normalize_name(value):
    normalized = unicodedata.normalize('NFKD', value or '')
    ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
    return ''.join(ch.lower() for ch in ascii_only if ch.isalnum())


def _to_decimal(value):
    if value in (None, ''):
        return None
    return Decimal(str(value)).quantize(Decimal('0.01'))


class Command(BaseCommand):
    help = 'Load all-player M1 AAV predictions from M1_2022_전체선수.xlsx (batters + pitchers).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Delete existing rows from this source file before loading.',
        )
        parser.add_argument(
            '--base-dir',
            help='Optional base directory containing the data/ folder.',
        )

    def handle(self, *args, **options):
        base_dir = Path(options['base_dir']) if options.get('base_dir') else Path(settings.BASE_DIR)
        workbook_path = base_dir / 'data' / SOURCE_FILE
        if not workbook_path.exists():
            raise CommandError(f'Workbook not found: {workbook_path}')

        if options['replace']:
            deleted_count, _ = MLBApiAavPrediction.objects.filter(source_file=SOURCE_FILE).delete()
            self.stdout.write(f'Deleted {deleted_count} existing rows from {SOURCE_FILE}.')

        objects = self._load_workbook(workbook_path)

        with transaction.atomic():
            if objects:
                MLBApiAavPrediction.objects.bulk_create(
                    objects,
                    batch_size=500,
                    update_conflicts=True,
                    unique_fields=['season', 'stat_view', 'name_ascii'],
                    update_fields=[
                        'source_label',
                        'source_file',
                        'player_name',
                        'team_code_raw',
                        'predicted_aav_millions',
                        'updated_at',
                    ],
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Loaded or updated {len(objects)} M1 all-player AAV prediction rows.'
            )
        )

    def _load_workbook(self, workbook_path):
        workbook = load_workbook(workbook_path, read_only=True, data_only=True)
        objects = []

        sheet_map = {
            BATTER_SHEET: MLBApiStatLine.VIEW_BATTING,
            PITCHER_SHEET: MLBApiStatLine.VIEW_PITCHING,
        }

        for sheet_name, stat_view in sheet_map.items():
            if sheet_name not in workbook.sheetnames:
                self.stdout.write(self.style.WARNING(f'Sheet not found: {sheet_name}'))
                continue

            ws = workbook[sheet_name]
            count = 0
            for row in ws.iter_rows(min_row=4, values_only=True):
                player_name = str(row[0] if len(row) > 0 else '').strip()
                if not player_name:
                    continue
                predicted_aav = _to_decimal(row[2] if len(row) > 2 else None)
                if predicted_aav is None:
                    continue
                objects.append(
                    MLBApiAavPrediction(
                        stat_view=stat_view,
                        season=DEFAULT_SEASON,
                        source_label=SOURCE_LABEL,
                        source_file=SOURCE_FILE,
                        player_name=player_name,
                        name_ascii=_normalize_name(player_name),
                        team_code_raw=str(row[1] if len(row) > 1 else '').strip(),
                        predicted_aav_millions=predicted_aav,
                    )
                )
                count += 1

            self.stdout.write(f'Parsed {count} rows from "{sheet_name}" sheet.')

        workbook.close()
        return objects
