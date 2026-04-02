import csv
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mlb.models import MLBApiSimilarPlayer, MLBApiStatLine


def _normalize_name(value):
    normalized = unicodedata.normalize('NFKD', value or '')
    ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
    return ''.join(ch.lower() for ch in ascii_only if ch.isalnum())


class Command(BaseCommand):
    help = 'Load batting/pitching similar player CSVs into MLBApiSimilarPlayer.'

    CSV_MAP = {
        MLBApiStatLine.VIEW_BATTING: 'similar_batters_2018_2022.csv',
        MLBApiStatLine.VIEW_PITCHING: 'similar_pitchers_2018_2022.csv',
    }

    def add_arguments(self, parser):
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Delete existing similar-player rows before loading.',
        )
        parser.add_argument(
            '--base-dir',
            help='Optional base directory containing the data/ folder.',
        )

    def handle(self, *args, **options):
        base_dir = Path(options['base_dir']) if options.get('base_dir') else Path(settings.BASE_DIR)
        data_dir = base_dir / 'data'

        if options['replace']:
            deleted_count, _ = MLBApiSimilarPlayer.objects.all().delete()
            self.stdout.write(f'Deleted {deleted_count} existing similar-player rows.')

        stat_line_lookups = {
            stat_view: self._build_stat_line_lookup(stat_view)
            for stat_view in self.CSV_MAP
        }

        objects = []
        for stat_view, filename in self.CSV_MAP.items():
            csv_path = data_dir / filename
            if not csv_path.exists():
                raise CommandError(f'Similar-player CSV not found: {csv_path}')
            objects.extend(self._load_csv(csv_path, stat_view, stat_line_lookups[stat_view]))

        with transaction.atomic():
            if objects:
                MLBApiSimilarPlayer.objects.bulk_create(
                    objects,
                    batch_size=500,
                    update_conflicts=True,
                    unique_fields=['stat_view', 'source_name_ascii', 'rank'],
                    update_fields=[
                        'source_player_name',
                        'source_mlbam_id',
                        'source_external_player_id',
                        'similar_player_name',
                        'similar_name_ascii',
                        'similar_mlbam_id',
                        'similar_external_player_id',
                        'similar_team',
                        'similarity_score',
                        'updated_at',
                    ],
                )

        self.stdout.write(self.style.SUCCESS(f'Loaded or updated {len(objects)} similar-player rows.'))

    def _load_csv(self, path, stat_view, stat_line_lookup):
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            objects = []
            for row in reader:
                source_name = (row.get('name') or '').strip()
                if not source_name:
                    continue

                source_line = stat_line_lookup.get(_normalize_name(source_name))
                source_ascii = _normalize_name(source_name)
                for rank in (1, 2, 3):
                    similar_name = (row.get(f'rank_{rank}_name') or '').strip()
                    score_text = (row.get(f'rank_{rank}_similarity_score') or '').strip()
                    if not similar_name or not score_text:
                        continue

                    similar_line = stat_line_lookup.get(_normalize_name(similar_name))
                    objects.append(
                        MLBApiSimilarPlayer(
                            stat_view=stat_view,
                            source_player_name=source_name,
                            source_name_ascii=source_ascii,
                            source_mlbam_id=(source_line.mlbam_id if source_line else ''),
                            source_external_player_id=(source_line.external_player_id if source_line else ''),
                            similar_player_name=similar_name,
                            similar_name_ascii=_normalize_name(similar_name),
                            similar_mlbam_id=(similar_line.mlbam_id if similar_line else ''),
                            similar_external_player_id=(similar_line.external_player_id if similar_line else ''),
                            similar_team=(similar_line.team if similar_line else ''),
                            similarity_score=int(float(score_text)),
                            rank=rank,
                        )
                    )
        return objects

    def _build_stat_line_lookup(self, stat_view):
        lookup = {}
        for stat_line in (
            MLBApiStatLine.objects.filter(stat_view=stat_view)
            .exclude(team='')
            .order_by('-season', '-war', 'team', 'player_name')
        ):
            candidate_name = stat_line.name_ascii or stat_line.player_name
            normalized_name = _normalize_name(candidate_name)
            if normalized_name and normalized_name not in lookup:
                lookup[normalized_name] = stat_line
        return lookup
