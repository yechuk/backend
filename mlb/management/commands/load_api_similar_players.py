import csv
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mlb.models import MLBApiRecommendedSimilarPlayer, MLBApiSimilarPlayer, MLBApiStatLine


def _normalize_name(value):
    normalized = unicodedata.normalize('NFKD', value or '')
    ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
    return ''.join(ch.lower() for ch in ascii_only if ch.isalnum())


class Command(BaseCommand):
    help = 'Load recommendation-based batting/pitching similar player CSVs into API tables.'

    RECOMMENDATION_CSV_MAP = {
        MLBApiStatLine.VIEW_BATTING: 'batters_recommendations.csv',
        MLBApiStatLine.VIEW_PITCHING: 'pitchers_recommendations.csv',
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
            legacy_deleted_count, _ = MLBApiSimilarPlayer.objects.all().delete()
            recommendation_deleted_count, _ = MLBApiRecommendedSimilarPlayer.objects.all().delete()
            self.stdout.write(
                f'Deleted {legacy_deleted_count} existing legacy rows and '
                f'{recommendation_deleted_count} recommendation rows.'
            )

        stat_line_lookups = {
            stat_view: self._build_stat_line_lookups(stat_view)
            for stat_view in self.RECOMMENDATION_CSV_MAP
        }

        recommendation_objects = []
        for stat_view, filename in self.RECOMMENDATION_CSV_MAP.items():
            csv_path = data_dir / filename
            if not csv_path.exists():
                raise CommandError(f'Recommendation CSV not found: {csv_path}')
            recommendation_objects.extend(
                self._load_recommendation_csv(csv_path, stat_view, stat_line_lookups[stat_view])
            )

        with transaction.atomic():
            if recommendation_objects:
                MLBApiRecommendedSimilarPlayer.objects.bulk_create(
                    recommendation_objects,
                    batch_size=500,
                    update_conflicts=True,
                    unique_fields=['stat_view', 'source_name_ascii', 'rank'],
                    update_fields=[
                        'source_player_name',
                        'source_mlbam_id',
                        'source_external_player_id',
                        'source_player_position',
                        'source_player_age',
                        'similar_player_name',
                        'similar_name_ascii',
                        'similar_mlbam_id',
                        'similar_external_player_id',
                        'similar_team',
                        'similar_player_position',
                        'similar_player_age',
                        'similarity_score',
                        'updated_at',
                    ],
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Loaded or updated {len(recommendation_objects)} recommendation rows.'
            )
        )

    def _load_recommendation_csv(self, path, stat_view, stat_line_lookups):
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            objects = []
            for row in reader:
                source_name = (row.get('query_name') or '').strip()
                if not source_name:
                    continue

                source_mlbam_id = (row.get('query_player_id') or '').strip()
                source_line = self._resolve_stat_line(stat_line_lookups, source_mlbam_id, source_name)
                source_ascii = _normalize_name(source_name)

                for rank in (1, 2, 3):
                    similar_name = (row.get(f'rec_{rank}_name') or '').strip()
                    score_text = (row.get(f'rec_{rank}_similarity') or '').strip()
                    if not similar_name or not score_text:
                        continue

                    similar_mlbam_id = (row.get(f'rec_{rank}_player_id') or '').strip()
                    similar_line = self._resolve_stat_line(stat_line_lookups, similar_mlbam_id, similar_name)
                    objects.append(
                        MLBApiRecommendedSimilarPlayer(
                            stat_view=stat_view,
                            source_player_name=source_name,
                            source_name_ascii=source_ascii,
                            source_mlbam_id=source_mlbam_id or (source_line.mlbam_id if source_line else ''),
                            source_external_player_id=(source_line.external_player_id if source_line else ''),
                            source_player_position=(row.get('query_position') or '').strip(),
                            source_player_age=self._to_optional_int(row.get('query_age')),
                            similar_player_name=similar_name,
                            similar_name_ascii=_normalize_name(similar_name),
                            similar_mlbam_id=similar_mlbam_id or (similar_line.mlbam_id if similar_line else ''),
                            similar_external_player_id=(similar_line.external_player_id if similar_line else ''),
                            similar_team=(similar_line.team if similar_line else ''),
                            similar_player_position=(row.get(f'rec_{rank}_position') or '').strip(),
                            similar_player_age=self._to_optional_int(row.get(f'rec_{rank}_age')),
                            similarity_score=score_text,
                            rank=rank,
                        )
                    )
        return objects

    def _build_stat_line_lookups(self, stat_view):
        by_name = {}
        by_mlbam_id = {}
        for stat_line in (
            MLBApiStatLine.objects.filter(stat_view=stat_view)
            .exclude(team='')
            .order_by('-season', '-war', 'team', 'player_name')
        ):
            if stat_line.mlbam_id and stat_line.mlbam_id not in by_mlbam_id:
                by_mlbam_id[stat_line.mlbam_id] = stat_line
            candidate_name = stat_line.name_ascii or stat_line.player_name
            normalized_name = _normalize_name(candidate_name)
            if normalized_name and normalized_name not in by_name:
                by_name[normalized_name] = stat_line
        return {'by_mlbam_id': by_mlbam_id, 'by_name': by_name}

    def _resolve_stat_line(self, stat_line_lookups, mlbam_id, player_name):
        if mlbam_id:
            stat_line = stat_line_lookups['by_mlbam_id'].get(str(mlbam_id))
            if stat_line is not None:
                return stat_line
        return stat_line_lookups['by_name'].get(_normalize_name(player_name))

    def _to_optional_int(self, value):
        value = (value or '').strip()
        if not value:
            return None
        return int(float(value))
