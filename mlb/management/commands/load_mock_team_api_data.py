import csv
import unicodedata
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

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


def _to_text(value):
    return str(value).strip() if value is not None else ''


def _pick(row, *keys):
    for key in keys:
        if key in row:
            value = _to_text(row.get(key))
            if value != '':
                return value
    return ''


def _name_ascii(value):
    normalized = unicodedata.normalize('NFKD', _to_text(value))
    return normalized.encode('ascii', 'ignore').decode('ascii')


class Command(BaseCommand):
    help = 'Load local batting/pitching CSVs into the DB for /api/teams.'

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
        parser.add_argument(
            '--batting-file',
            help='Explicit batting CSV path. Defaults to data/batters_2018_2022.csv when present, else data/batting.csv.',
        )
        parser.add_argument(
            '--pitching-file',
            help='Explicit pitching CSV path. Defaults to data/pitchers_2018_2022.csv when present, else data/pitching.csv.',
        )

    def handle(self, *args, **options):
        if options['replace']:
            deleted_count, _ = MLBApiStatLine.objects.all().delete()
            self.stdout.write(f'Deleted {deleted_count} existing API stat rows.')

        base_dir = Path(options['base_dir'])
        files = {
            MLBApiStatLine.VIEW_PITCHING: self._resolve_csv_path(
                options.get('pitching_file'),
                [
                    base_dir / 'data' / 'pitchers_2018_2022.csv',
                    base_dir / 'data' / 'pitching.csv',
                ],
            ),
            MLBApiStatLine.VIEW_BATTING: self._resolve_csv_path(
                options.get('batting_file'),
                [
                    base_dir / 'data' / 'batters_2018_2022.csv',
                    base_dir / 'data' / 'batting.csv',
                ],
            ),
        }

        total_upserts = 0
        for stat_view, csv_path in files.items():
            if not csv_path.exists():
                self.stderr.write(self.style.WARNING(f'Skipping missing file: {csv_path}'))
                continue

            legacy_lookup = self._load_legacy_lookup(stat_view, base_dir, csv_path)
            objects = []

            with csv_path.open('r', encoding='utf-8-sig', newline='') as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    normalized = {
                        (key or '').strip(): (value or '').strip()
                        for key, value in row.items()
                        if key
                    }
                    season = _to_int(_pick(normalized, 'season', 'Season'))
                    source_player_id = _pick(normalized, 'mlbam_id', 'MLBAMID', 'player_id', 'PlayerId')
                    legacy_row = legacy_lookup.get((season, source_player_id)) if season and source_player_id else None
                    merged = dict(legacy_row or {})
                    merged.update(normalized)

                    team = _pick(merged, 'team', 'Team').upper()
                    mlbam_id = _pick(merged, 'mlbam_id', 'MLBAMID', 'player_id', 'PlayerId')
                    external_player_id = _pick(
                        merged,
                        'external_player_id',
                        'PlayerId',
                        'player_id',
                        'MLBAMID',
                    ) or mlbam_id
                    player_name = _pick(merged, 'name', 'Name')
                    name_ascii = _pick(merged, 'name_ascii', 'NameASCII') or _name_ascii(player_name)

                    if not season or not team or not mlbam_id or not external_player_id or not player_name:
                        continue

                    raw_stats = self._build_raw_stats(
                        stat_view=stat_view,
                        row=merged,
                        season=season,
                        team=team,
                        player_name=player_name,
                        name_ascii=name_ascii,
                        external_player_id=external_player_id,
                        mlbam_id=mlbam_id,
                    )

                    objects.append(
                        MLBApiStatLine(
                            stat_view=stat_view,
                            season=season,
                            mlbam_id=mlbam_id,
                            team=team,
                            player_name=player_name,
                            name_ascii=name_ascii,
                            external_player_id=external_player_id,
                            age=_to_int(_pick(merged, 'age', 'Age')),
                            war=_to_float(_pick(merged, 'war', 'WAR')),
                            raw_stats=raw_stats,
                        )
                    )
            if objects:
                with transaction.atomic():
                    MLBApiStatLine.objects.bulk_create(
                        objects,
                        batch_size=500,
                        update_conflicts=True,
                        unique_fields=['stat_view', 'season', 'mlbam_id'],
                        update_fields=[
                            'team',
                            'player_name',
                            'name_ascii',
                            'external_player_id',
                            'age',
                            'war',
                            'raw_stats',
                            'updated_at',
                        ],
                    )
                total_upserts += len(objects)

        self.stdout.write(self.style.SUCCESS(f'Loaded or updated {total_upserts} API rows.'))

    def _resolve_csv_path(self, explicit_path, fallback_paths):
        if explicit_path:
            return Path(explicit_path)
        for path in fallback_paths:
            if path.exists():
                return path
        return fallback_paths[0]

    def _load_legacy_lookup(self, stat_view, base_dir, selected_path):
        legacy_name = 'pitching.csv' if stat_view == MLBApiStatLine.VIEW_PITCHING else 'batting.csv'
        legacy_path = base_dir / 'data' / legacy_name
        if not legacy_path.exists() or legacy_path == selected_path:
            return {}

        lookup = {}
        with legacy_path.open('r', encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                normalized = {
                    (key or '').strip(): (value or '').strip()
                    for key, value in row.items()
                    if key
                }
                season = _to_int(_pick(normalized, 'season', 'Season'))
                player_id = _pick(normalized, 'mlbam_id', 'MLBAMID', 'player_id', 'PlayerId')
                if season and player_id:
                    lookup[(season, player_id)] = normalized
        return lookup

    def _build_raw_stats(
        self,
        *,
        stat_view,
        row,
        season,
        team,
        player_name,
        name_ascii,
        external_player_id,
        mlbam_id,
    ):
        raw_stats = {
            'Season': str(season),
            'Name': player_name,
            'Team': team,
            'Age': _pick(row, 'age', 'Age'),
            'WAR': _pick(row, 'war', 'WAR'),
            'NameASCII': name_ascii,
            'PlayerId': external_player_id,
            'MLBAMID': mlbam_id,
            'Position': _pick(row, 'position', 'Position'),
            'Height': _pick(row, 'height', 'Height'),
            'Weight': _pick(row, 'weight', 'Weight'),
            'Bats': _pick(row, 'bats', 'Bats'),
            'Throws': _pick(row, 'throws', 'Throws'),
            'DebutYear': _pick(row, 'debut_year', 'Debut Year'),
            'ContractValue': _pick(row, 'contract_value', 'Contract Value'),
        }

        if stat_view == MLBApiStatLine.VIEW_PITCHING:
            raw_stats.update(
                {
                    'G': _pick(row, 'games', 'G'),
                    'GS': _pick(row, 'games_started', 'GS'),
                    'IP': _pick(row, 'ip', 'IP'),
                    'SO': _pick(row, 'so', 'SO'),
                    'BB': _pick(row, 'bb', 'BB'),
                    'ERA': _pick(row, 'era', 'ERA'),
                    'FIP': _pick(row, 'fip', 'FIP'),
                    'WHIP': _pick(row, 'whip', 'WHIP'),
                    'K/9': _pick(row, 'k_per_9', 'K/9'),
                    'BB/9': _pick(row, 'bb_per_9', 'BB/9'),
                    'HR/9': _pick(row, 'hr_per_9', 'HR/9'),
                    'K%': _pick(row, 'k_pct', 'K%'),
                    'xERA': _pick(row, 'x_era', 'xERA'),
                    'xFIP': _pick(row, 'x_fip', 'xFIP'),
                    'LOB%': _pick(row, 'lob_pct', 'LOB%'),
                    'BABIP': _pick(row, 'babip', 'BABIP'),
                    'velocity': _pick(row, 'velocity', 'Velocity'),
                }
            )
        else:
            raw_stats.update(
                {
                    'G': _pick(row, 'games', 'G'),
                    'PA': _pick(row, 'plate_appearances', 'PA'),
                    'HR': _pick(row, 'hr', 'HR'),
                    'RBI': _pick(row, 'rbi', 'RBI'),
                    'SB': _pick(row, 'stolen_bases', 'SB'),
                    'AVG': _pick(row, 'avg', 'AVG'),
                    'OPS': _pick(row, 'ops', 'OPS'),
                    'ISO': _pick(row, 'iso', 'ISO'),
                    'BB%': _pick(row, 'bb_pct', 'BB%'),
                    'K%': _pick(row, 'k_pct', 'K%'),
                    'wOBA': _pick(row, 'woba', 'wOBA'),
                    'wRC+': _pick(row, 'wrc_plus', 'wRC+'),
                    'BABIP': _pick(row, 'babip', 'BABIP'),
                    'ExitVelocity': _pick(row, 'exit_velocity', 'Exit_Velocity', 'ExitVelocity'),
                    'LaunchAngle': _pick(row, 'launch_angle', 'Launch_Angle', 'LaunchAngle'),
                }
            )

        return {key: value for key, value in raw_stats.items() if value != ''}
