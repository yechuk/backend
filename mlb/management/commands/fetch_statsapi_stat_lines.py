import time
import unicodedata
import requests

from django.core.management.base import BaseCommand
from django.db import transaction

from mlb.models import MLBApiStatLine


STATSAPI_BASE = 'https://statsapi.mlb.com/api/v1'
REQUEST_DELAY = 0.3

# Fields to fill from yearByYear (only if currently missing in raw_stats)
PITCHING_FILL_MAP = {
    'era':               'ERA',
    'whip':              'WHIP',
    'strikeOuts':        'SO',
    'inningsPitched':    'IP',
    'gamesPlayed':       'G',
    'gamesStarted':      'GS',
    'baseOnBalls':       'BB',
    'homeRuns':          'HR',
    'strikeoutsPer9Inn': 'K/9',
    'walksPer9Inn':      'BB/9',
    'homeRunsPer9':      'HR/9',
    'wins':              'W',
    'losses':            'L',
    'saves':             'SV',
    'earnedRuns':        'ER',
    'hits':              'H',
}
PITCHING_ADV_FILL_MAP = {
    'babip':            'BABIP',
    'strikeoutsPer9':   'K/9',   # advanced label differs
    'baseOnBallsPer9':  'BB/9',
    'homeRunsPer9':     'HR/9',
}
HITTING_FILL_MAP = {
    'avg':              'AVG',
    'obp':              'OBP',
    'slg':              'SLG',
    'ops':              'OPS',
    'homeRuns':         'HR',
    'rbi':              'RBI',
    'stolenBases':      'SB',
    'gamesPlayed':      'G',
    'plateAppearances': 'PA',
    'hits':             'H',
    'doubles':          '2B',
    'triples':          '3B',
    'baseOnBalls':      'BB',
    'strikeOuts':       'SO',
    'runs':             'R',
    'atBats':           'AB',
}
HITTING_ADV_FILL_MAP = {
    'babip':   'BABIP',
    'obp':     'OBP',
    'slg':     'SLG',
    'ops':     'OPS',
    'iso':     'ISO',
}

# Keys from CSV (FanGraphs-exclusive) — never overwrite these
PRESERVE_KEYS = {'WAR', 'FIP', 'K%', 'wOBA', 'wRC+', 'velocity', 'xFIP', 'xERA', 'LOB%'}


def _normalize_name(value):
    normalized = unicodedata.normalize('NFKD', value or '')
    ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
    return ''.join(ch.lower() for ch in ascii_only if ch.isalnum())


def _fetch_json(url, params=None):
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _fetch_team_map():
    data = _fetch_json(f'{STATSAPI_BASE}/teams', params={'sportId': 1})
    return {t['id']: t['abbreviation'] for t in data.get('teams', [])}


def _fetch_year_by_year(mlbam_id, group, stats_type):
    try:
        data = _fetch_json(
            f'{STATSAPI_BASE}/people/{mlbam_id}/stats',
            params={'stats': stats_type, 'group': group},
        )
        return data.get('stats', [{}])[0].get('splits', [])
    except Exception:
        return []


def _merge_into_raw(raw, api_stat, fill_map):
    for api_key, raw_key in fill_map.items():
        if raw_key in PRESERVE_KEYS:
            continue
        val = api_stat.get(api_key)
        if val is not None and not raw.get(raw_key):
            raw[raw_key] = str(val)


class Command(BaseCommand):
    help = (
        'Fetch yearByYear stats from MLB StatsAPI for all players in MLBApiStatLine. '
        'Fills null fields on existing records and creates new stat lines for missing seasons.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--mlbam-ids',
            nargs='+',
            type=str,
            help='Only process these mlbam_ids (default: all in DB).',
        )
        parser.add_argument(
            '--fill-only',
            action='store_true',
            help='Only fill null fields on existing records; do not create new stat lines.',
        )

    def handle(self, *args, **options):
        fill_only = options['fill_only']

        # 1. Build team_id → abbreviation map
        self.stdout.write('Fetching MLB team abbreviations...')
        team_map = _fetch_team_map()

        # 2. Determine target mlbam_ids
        if options.get('mlbam_ids'):
            mlbam_ids = [str(i) for i in options['mlbam_ids']]
        else:
            mlbam_ids = list(
                MLBApiStatLine.objects
                .exclude(mlbam_id='').exclude(mlbam_id__isnull=True)
                .values_list('mlbam_id', flat=True)
                .distinct()
            )

        self.stdout.write(f'Processing {len(mlbam_ids)} players...')

        # 3. Load existing stat lines into memory for fast lookup
        existing = {}
        for line in MLBApiStatLine.objects.filter(mlbam_id__in=mlbam_ids):
            existing[(line.mlbam_id, str(line.season), line.stat_view)] = line

        to_update = []
        to_create = []

        for idx, mlbam_id in enumerate(mlbam_ids, 1):
            # Fetch player bio to get name (splits don't include player info)
            try:
                bio_data = _fetch_json(f'{STATSAPI_BASE}/people/{mlbam_id}')
                person = bio_data.get('people', [{}])[0]
                player_name = person.get('fullName', '')
                name_ascii = _normalize_name(player_name)
            except Exception:
                player_name = ''
                name_ascii = ''

            for group, stat_view, fill_map, adv_fill_map in [
                ('pitching', MLBApiStatLine.VIEW_PITCHING, PITCHING_FILL_MAP, PITCHING_ADV_FILL_MAP),
                ('hitting',  MLBApiStatLine.VIEW_BATTING,  HITTING_FILL_MAP,  HITTING_ADV_FILL_MAP),
            ]:
                splits = _fetch_year_by_year(mlbam_id, group, 'yearByYear')
                adv_splits_by_season = {}
                for s in _fetch_year_by_year(mlbam_id, group, 'yearByYearAdvanced'):
                    adv_splits_by_season[str(s.get('season', ''))] = s.get('stat', {})

                for split in splits:
                    season_str = str(split.get('season', ''))
                    if not season_str or int(season_str) > 2022:
                        continue

                    api_stat = split.get('stat', {})
                    team_id = split.get('team', {}).get('id')
                    team_abbr = team_map.get(team_id, '') if team_id else ''
                    age = api_stat.get('age')

                    key = (mlbam_id, season_str, stat_view)
                    if key in existing:
                        # Update: fill only null fields
                        line = existing[key]
                        raw = dict(line.raw_stats or {})
                        _merge_into_raw(raw, api_stat, fill_map)
                        _merge_into_raw(raw, adv_splits_by_season.get(season_str, {}), adv_fill_map)
                        line.raw_stats = raw
                        to_update.append(line)
                    elif not fill_only:
                        # Create new stat line
                        if not player_name:
                            continue
                        raw = {
                            'Season': season_str,
                            'Name': player_name,
                            'Team': team_abbr,
                            'Age': str(age) if age else '',
                            'NameASCII': name_ascii or '',
                            'PlayerId': str(mlbam_id),
                            'MLBAMID': str(mlbam_id),
                        }
                        _merge_into_raw(raw, api_stat, fill_map)
                        _merge_into_raw(raw, adv_splits_by_season.get(season_str, {}), adv_fill_map)
                        raw = {k: v for k, v in raw.items() if v not in ('', None)}
                        new_line = MLBApiStatLine(
                            stat_view=stat_view,
                            season=int(season_str),
                            team=team_abbr,
                            player_name=player_name,
                            name_ascii=name_ascii or '',
                            external_player_id=str(mlbam_id),
                            mlbam_id=str(mlbam_id),
                            age=int(age) if age else None,
                            raw_stats=raw,
                        )
                        to_create.append(new_line)
                        existing[key] = new_line  # avoid duplicate creation

                time.sleep(REQUEST_DELAY)

            if idx % 50 == 0:
                self.stdout.write(f'  {idx}/{len(mlbam_ids)} players processed...')

        # 4. Persist
        with transaction.atomic():
            if to_update:
                MLBApiStatLine.objects.bulk_update(to_update, ['raw_stats'], batch_size=500)
            if to_create:
                MLBApiStatLine.objects.bulk_create(
                    to_create,
                    batch_size=500,
                    update_conflicts=True,
                    unique_fields=['stat_view', 'season', 'mlbam_id'],
                    update_fields=['team', 'player_name', 'name_ascii', 'raw_stats', 'updated_at'],
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'Done. Updated {len(to_update)} existing lines, created {len(to_create)} new lines.'
            )
        )
