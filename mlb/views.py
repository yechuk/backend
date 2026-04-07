import csv
import json
import unicodedata
from pathlib import Path

from django.conf import settings
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ValuationSettingsForm
from .models import (
    MLBApiRecommendedSimilarPlayer,
    MLBApiSimilarPlayer,
    MLBApiStatLine,
    MLBPlayer,
    MLBRosterEntry,
    MLBRosterPhoto,
    ValuationSettings,
)


LEADERBOARD_CSV = Path(settings.BASE_DIR) / 'data' / 'bp_export_20260312.csv'
LEADERBOARD_PAGE_SIZE = 60
SUPPORTED_STAT_VIEWS = {'batting', 'pitching'}
PLAYER_HISTORY_LIMIT = 5


def _resolve_leaderboard_player_pk(name, team):
    """Find MLBPlayer pk by name (and optional team). Returns None if not found."""
    if not name or not name.strip():
        return None
    qs = MLBPlayer.objects.filter(name=name.strip())
    if not qs.exists():
        return None
    if qs.count() == 1:
        return qs.values_list('pk', flat=True)[0]
    if team and team.strip():
        by_team = qs.filter(team=team.strip())
        if by_team.exists():
            return by_team.values_list('pk', flat=True)[0]
    return qs.values_list('pk', flat=True)[0]


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_optional_rounded_int(value):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _stat_value(row, *keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ''):
            return value
    return None


def _format_rate(value):
    text = f'{value:.3f}'
    if 0 <= value < 1:
        return text[1:]
    return text


def _normalize_stat_view(raw_view):
    view = (raw_view or 'batting').strip().lower()
    if view not in SUPPORTED_STAT_VIEWS:
        return 'batting'
    return view


def _stat_queryset(view):
    return MLBApiStatLine.objects.filter(stat_view=view)


def _available_stat_seasons(view):
    seasons = list(
        _stat_queryset(view)
        .values_list('season', flat=True)
        .distinct()
        .order_by('-season')
    )
    if not seasons:
        return []

    return seasons


def _resolve_stat_season(view, raw_season):
    seasons = _available_stat_seasons(view)
    if not seasons:
        return None

    requested = _to_int(raw_season, 0)
    if requested in seasons:
        return requested
    return seasons[0]


def _resolve_roster_stat_season(view, roster_season):
    seasons = _available_stat_seasons(view)
    if not seasons:
        return None

    if roster_season is None:
        return seasons[0]

    for season in seasons:
        if season <= roster_season:
            return season
    return None


def _filter_stat_lines(view, season, team_code=None):
    qs = _stat_queryset(view)
    if season is not None:
        qs = qs.filter(season=season)
    if team_code:
        qs = qs.filter(team__iexact=team_code)
    return qs.exclude(team__in=['', '- - -'])


def _player_detail_url(team_code, player_id):
    return f'/api/teams/{team_code}/players/{player_id}/'


def _team_players_url(team_code):
    return f'/api/teams/{team_code}/players/'


def _roster_team_url(team_code):
    return f'/api/rosters/{team_code}/'


def _roster_player_photo_url(team_code, player_id, season=None):
    base_url = f'/api/rosters/{team_code}/players/{player_id}/photo/'
    if season is None:
        return base_url
    return f'{base_url}?season={season}'


def _roster_player_detail_url(team_code, player_id, season=None):
    base_url = f'/api/rosters/{team_code}/players/{player_id}/'
    if season is None:
        return base_url
    return f'{base_url}?season={season}'


def _serialize_stat_player(stat_line):
    row = stat_line.raw_stats or {}
    view = stat_line.stat_view
    api_player_id = stat_line.mlbam_id or stat_line.external_player_id
    base = {
        'id': api_player_id,
        'player_id': api_player_id,
        'mlbam_id': stat_line.mlbam_id,
        'external_player_id': stat_line.external_player_id,
        'name': stat_line.player_name,
        'name_ascii': stat_line.name_ascii,
        'team': stat_line.team,
        'season': stat_line.season,
        'age': stat_line.age,
        'view': view,
        'position': _stat_value(row, 'Position', 'position'),
        'height': _stat_value(row, 'Height', 'height'),
        'weight': _to_int(_stat_value(row, 'Weight', 'weight'), None),
        'bats': _stat_value(row, 'Bats', 'bats'),
        'throws': _stat_value(row, 'Throws', 'throws'),
        'debut_year': _to_int(_stat_value(row, 'DebutYear', 'debut_year'), None),
        'contract_value': _to_float(_stat_value(row, 'ContractValue', 'contract_value'), None),
    }

    if view == 'pitching':
        base['stats'] = {
            'games': _to_int(_stat_value(row, 'G', 'games'), None),
            'games_started': _to_int(_stat_value(row, 'GS', 'games_started'), None),
            'innings_pitched': _to_float(_stat_value(row, 'IP', 'ip'), None),
            'strikeouts': _to_int(_stat_value(row, 'SO', 'so'), None),
            'walks': _to_int(_stat_value(row, 'BB', 'bb'), None),
            'era': _to_float(_stat_value(row, 'ERA', 'era'), None),
            'fip': _to_float(_stat_value(row, 'FIP', 'fip'), None),
            'whip': _to_float(_stat_value(row, 'WHIP', 'whip'), None),
            'k_per_9': _to_float(_stat_value(row, 'K/9', 'k_per_9'), None),
            'bb_per_9': _to_float(_stat_value(row, 'BB/9', 'bb_per_9'), None),
            'hr_per_9': _to_float(_stat_value(row, 'HR/9', 'hr_per_9'), None),
            'strikeout_rate': _to_float(_stat_value(row, 'K%', 'k_pct'), None),
            'x_era': _to_float(_stat_value(row, 'xERA', 'x_era'), None),
            'x_fip': _to_float(_stat_value(row, 'xFIP', 'x_fip'), None),
            'lob_pct': _to_float(_stat_value(row, 'LOB%', 'lob_pct'), None),
            'babip': _to_float(_stat_value(row, 'BABIP', 'babip'), None),
            'velocity': _to_float(_stat_value(row, 'velocity', 'Velocity'), None),
            'war': stat_line.war if stat_line.war is not None else _to_float(_stat_value(row, 'WAR', 'war'), None),
        }
    else:
        base['stats'] = {
            'games': _to_int(_stat_value(row, 'G', 'games'), None),
            'plate_appearances': _to_int(_stat_value(row, 'PA', 'plate_appearances'), None),
            'home_runs': _to_int(_stat_value(row, 'HR', 'hr'), None),
            'rbi': _to_int(_stat_value(row, 'RBI', 'rbi'), None),
            'avg': _to_float(_stat_value(row, 'AVG', 'avg'), None),
            'ops': _to_float(_stat_value(row, 'OPS', 'ops'), None),
            'stolen_bases': _to_int(_stat_value(row, 'SB', 'stolen_bases'), None),
            'iso': _to_float(_stat_value(row, 'ISO', 'iso'), None),
            'walk_rate': _to_float(_stat_value(row, 'BB%', 'bb_pct'), None),
            'strikeout_rate': _to_float(_stat_value(row, 'K%', 'k_pct'), None),
            'woba': _to_float(_stat_value(row, 'wOBA', 'woba'), None),
            'wrc_plus': _to_optional_rounded_int(_stat_value(row, 'wRC+', 'wrc_plus')),
            'babip': _to_float(_stat_value(row, 'BABIP', 'babip'), None),
            'exit_velocity': _to_float(_stat_value(row, 'ExitVelocity', 'Exit_Velocity', 'exit_velocity'), None),
            'launch_angle': _to_float(_stat_value(row, 'LaunchAngle', 'Launch_Angle', 'launch_angle'), None),
            'war': stat_line.war if stat_line.war is not None else _to_float(_stat_value(row, 'WAR', 'war'), None),
        }

    base['detail_url'] = _player_detail_url(base['team'], api_player_id)
    return base


def _player_history_queryset(view, stat_line):
    filters = Q()
    if stat_line.mlbam_id:
        filters |= Q(mlbam_id=str(stat_line.mlbam_id))
    if stat_line.external_player_id:
        filters |= Q(external_player_id=str(stat_line.external_player_id))
    return (
        _stat_queryset(view)
        .filter(filters)
        .exclude(team='')
        .order_by('-season', '-war', 'team', 'player_name')
    )


def _resolve_stat_player_photo_url(stat_line):
    try:
        mlbam_id = int(str(stat_line.mlbam_id).strip())
    except (TypeError, ValueError):
        return None

    roster_entry = MLBRosterEntry.objects.filter(player_id=mlbam_id).order_by('-season').first()
    if roster_entry is None:
        return None

    photo = _find_roster_photo(roster_entry.team_name, roster_entry.player_name)
    if photo is None:
        return None

    return _roster_player_photo_url(
        roster_entry.team_abbreviation,
        roster_entry.player_id,
        season=roster_entry.season,
    )


def _available_roster_seasons():
    return list(
        MLBRosterEntry.objects.values_list('season', flat=True).distinct().order_by('-season')
    )


def _resolve_roster_season(raw_season):
    seasons = _available_roster_seasons()
    if not seasons:
        return None

    requested = _to_int(raw_season, 0)
    if requested in seasons:
        return requested
    return seasons[0]


def _filter_roster_entries(season, team_code=None):
    qs = MLBRosterEntry.objects.all()
    if season is not None:
        qs = qs.filter(season=season)
    if team_code:
        qs = qs.filter(team_abbreviation__iexact=team_code)
    return qs


def _serialize_roster_entry(entry):
    return {
        'season': entry.season,
        'team_id': entry.team_id,
        'team_name': entry.team_name,
        'team_abbreviation': entry.team_abbreviation,
        'league_name': entry.league_name,
        'division_name': entry.division_name,
        'player_id': entry.player_id,
        'player_name': entry.player_name,
        'player_link': entry.player_link,
        'detail_url': _roster_player_detail_url(entry.team_abbreviation, entry.player_id, season=entry.season),
        'photo_url': None,
        'jersey_number': entry.jersey_number,
        'position': {
            'code': entry.position_code,
            'name': entry.position_name,
            'type': entry.position_type,
            'abbreviation': entry.position_abbreviation,
        },
        'status': {
            'code': entry.status_code,
            'description': entry.status_description,
        },
    }

def _serialize_roster_stat_line(stat_line):
    if stat_line is None:
        return None

    payload = _serialize_stat_player(stat_line)
    return {
        'source_player_id': payload['player_id'],
        'source_external_player_id': payload['external_player_id'],
        'mlbam_id': stat_line.mlbam_id,
        'team': payload['team'],
        'season': payload['season'],
        'age': payload['age'],
        'stats': payload['stats'],
        'detail_url': payload['detail_url'],
    }


def _resolve_roster_entry_by_identifier(team_code, roster_season, raw_player_id):
    player_id_text = str(raw_player_id or '').strip()
    if not player_id_text:
        return None

    filtered_entries = _filter_roster_entries(roster_season, team_code=team_code)
    direct_player_id = _to_int(player_id_text, None)
    if direct_player_id is not None:
        return filtered_entries.filter(player_id=direct_player_id).first()
    return None


def _roster_player_stat_identity(entry, requested_player_id):
    return Q(mlbam_id=str(entry.player_id))


def _roster_player_stat_lines_by_season(entry, requested_player_id):
    identity_q = _roster_player_stat_identity(entry, requested_player_id)
    season_map = {}
    for stat_line in (
        MLBApiStatLine.objects.filter(identity_q)
        .exclude(team='')
        .order_by('-season', 'stat_view', '-war', 'team', 'player_name')
    ):
        season_bucket = season_map.setdefault(stat_line.season, {})
        existing = season_bucket.get(stat_line.stat_view)
        if existing is None:
            season_bucket[stat_line.stat_view] = stat_line
    return season_map


def _build_roster_player_history(entry, requested_player_id, requested_stat_season=None):
    season_map = _roster_player_stat_lines_by_season(entry, requested_player_id)

    if requested_stat_season is not None:
        seasons = [requested_stat_season]
    else:
        seasons = sorted(season_map.keys(), reverse=True)[:PLAYER_HISTORY_LIMIT]

    history = []
    for season in seasons:
        season_bucket = season_map.get(season, {})
        batting_payload = _serialize_roster_stat_line(season_bucket.get(MLBApiStatLine.VIEW_BATTING))
        pitching_payload = _serialize_roster_stat_line(season_bucket.get(MLBApiStatLine.VIEW_PITCHING))
        history.append({
            'season': season,
            'batting': batting_payload if _has_meaningful_roster_stats(batting_payload, MLBApiStatLine.VIEW_BATTING) else None,
            'pitching': pitching_payload if _has_meaningful_roster_stats(pitching_payload, MLBApiStatLine.VIEW_PITCHING) else None,
        })

    return history


def _has_meaningful_roster_stats(stat_payload, view):
    if stat_payload is None:
        return False

    stats = stat_payload.get('stats') or {}
    def _num(value):
        return value or 0

    if view == MLBApiStatLine.VIEW_BATTING:
        return (
            _num(stats.get('plate_appearances')) > 0
            or _num(stats.get('games')) > 0
            or _num(stats.get('home_runs')) > 0
            or _num(stats.get('rbi')) > 0
            or stats.get('avg') is not None
            or stats.get('ops') is not None
            or stats.get('wrc_plus') is not None
            or stats.get('war') is not None
        )
    if view == MLBApiStatLine.VIEW_PITCHING:
        return (
            _num(stats.get('innings_pitched')) > 0
            or _num(stats.get('games_started')) > 0
            or _num(stats.get('games')) > 0
        )
    return True


def _normalize_photo_name(value):
    normalized = unicodedata.normalize('NFKD', value or '')
    ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
    return ''.join(ch.lower() for ch in ascii_only if ch.isalnum())


def _normalize_similar_name(value):
    return _normalize_photo_name(value)


def _find_roster_photo(team_name, player_name, photo_map=None):
    normalized_target = _normalize_photo_name(player_name)
    if not normalized_target:
        return None
    if photo_map is not None:
        return photo_map.get(normalized_target)
    return MLBRosterPhoto.objects.filter(
        team_name=team_name,
        normalized_player_name=normalized_target,
    ).first()


def _resolve_roster_detail_url_for_mlbam(mlbam_id):
    if not mlbam_id:
        return None
    roster_entry = MLBRosterEntry.objects.filter(player_id=mlbam_id).order_by('-season').first()
    if roster_entry is None:
        return None
    return _roster_player_detail_url(
        roster_entry.team_abbreviation,
        roster_entry.player_id,
        season=roster_entry.season,
    )


def _serialize_similar_player(similar_player):
    teams_detail_url = None
    if similar_player.similar_team and similar_player.similar_mlbam_id:
        teams_detail_url = (
            f"/api/teams/{similar_player.similar_team}/players/"
            f"{similar_player.similar_mlbam_id}/?view={similar_player.stat_view}"
        )

    roster_detail_url = _resolve_roster_detail_url_for_mlbam(similar_player.similar_mlbam_id)

    return {
        'rank': similar_player.rank,
        'player_name': similar_player.similar_player_name,
        'similarity_score': similar_player.similarity_score,
        'team': similar_player.similar_team or None,
        'mlbam_id': similar_player.similar_mlbam_id or None,
        'external_player_id': similar_player.similar_external_player_id or None,
        'player_id': similar_player.similar_mlbam_id or similar_player.similar_external_player_id or None,
        'view': similar_player.stat_view,
        'teams_detail_url': teams_detail_url,
        'roster_detail_url': roster_detail_url,
    }


def _serialize_recommended_similar_player(similar_player):
    teams_detail_url = None
    if similar_player.similar_team and similar_player.similar_mlbam_id:
        teams_detail_url = (
            f"/api/teams/{similar_player.similar_team}/players/"
            f"{similar_player.similar_mlbam_id}/?view={similar_player.stat_view}"
        )

    roster_detail_url = _resolve_roster_detail_url_for_mlbam(similar_player.similar_mlbam_id)

    return {
        'rank': similar_player.rank,
        'player_name': similar_player.similar_player_name,
        'similarity_score': float(similar_player.similarity_score),
        'team': similar_player.similar_team or None,
        'mlbam_id': similar_player.similar_mlbam_id or None,
        'external_player_id': similar_player.similar_external_player_id or None,
        'player_id': similar_player.similar_mlbam_id or similar_player.similar_external_player_id or None,
        'view': similar_player.stat_view,
        'position': similar_player.similar_player_position or None,
        'age': similar_player.similar_player_age,
        'teams_detail_url': teams_detail_url,
        'roster_detail_url': roster_detail_url,
    }


def _similar_player_queryset(stat_view, *, mlbam_id=None, external_player_id=None, player_name=None):
    filters = Q()
    if mlbam_id:
        filters |= Q(source_mlbam_id=str(mlbam_id))
    normalized_name = _normalize_similar_name(player_name)
    if normalized_name:
        filters |= Q(source_name_ascii=normalized_name)
    if not filters:
        return MLBApiSimilarPlayer.objects.none()
    return MLBApiSimilarPlayer.objects.filter(stat_view=stat_view).filter(filters).order_by('rank')


def _recommended_similar_player_queryset(stat_view, *, mlbam_id=None, external_player_id=None, player_name=None):
    filters = Q()
    if mlbam_id:
        filters |= Q(source_mlbam_id=str(mlbam_id))
    normalized_name = _normalize_similar_name(player_name)
    if normalized_name:
        filters |= Q(source_name_ascii=normalized_name)
    if not filters:
        return MLBApiRecommendedSimilarPlayer.objects.none()
    return MLBApiRecommendedSimilarPlayer.objects.filter(stat_view=stat_view).filter(filters).order_by('rank')


def _team_detail_similar_players(view, stat_line):
    player_name = stat_line.name_ascii or stat_line.player_name
    return [
        _serialize_similar_player(similar_player)
        for similar_player in _similar_player_queryset(
            view,
            mlbam_id=stat_line.mlbam_id,
            player_name=player_name,
        )
    ]


def _team_detail_similar_player_recommendations(view, stat_line):
    player_name = stat_line.name_ascii or stat_line.player_name
    return [
        _serialize_recommended_similar_player(similar_player)
        for similar_player in _recommended_similar_player_queryset(
            view,
            mlbam_id=stat_line.mlbam_id,
            player_name=player_name,
        )
    ]


def _roster_detail_similar_players(entry, requested_player_id):
    similar_players = {}
    for stat_view in (MLBApiStatLine.VIEW_BATTING, MLBApiStatLine.VIEW_PITCHING):
        similar_players[stat_view] = [
            _serialize_similar_player(similar_player)
            for similar_player in _similar_player_queryset(
                stat_view,
                mlbam_id=entry.player_id,
                player_name=entry.player_name,
            )
        ]
    return similar_players


def _roster_detail_similar_player_recommendations(entry, requested_player_id):
    similar_players = {}
    for stat_view in (MLBApiStatLine.VIEW_BATTING, MLBApiStatLine.VIEW_PITCHING):
        similar_players[stat_view] = [
            _serialize_recommended_similar_player(similar_player)
            for similar_player in _recommended_similar_player_queryset(
                stat_view,
                mlbam_id=entry.player_id,
                player_name=entry.player_name,
            )
        ]
    return similar_players


def _ohtani_image_response():
    candidates = [
        ('ohtani.png', 'image/png'),
        ('ohtani.img', 'image/png'),
        ('ohtani.jpeg', 'image/jpeg'),
        ('ohtani.jpg', 'image/jpeg'),
    ]
    for filename, content_type in candidates:
        image_path = settings.BASE_DIR / filename
        if image_path.exists():
            return FileResponse(image_path.open('rb'), content_type=content_type)

    raise Http404('Ohtani image file not found.')


def api_teams(request):
    if 'season' not in request.GET and 'view' not in request.GET:
        return _ohtani_image_response()

    view = _normalize_stat_view(request.GET.get('view'))
    season = _resolve_stat_season(view, request.GET.get('season'))
    filtered_lines = _filter_stat_lines(view, season)
    team_rows = list(
        filtered_lines
        .values('team')
        .annotate(player_count=Count('id'))
        .order_by('team')
    )
    teams = [
        {
            'code': row['team'],
            'name': row['team'],
            'season': season,
            'view': view,
            'player_count': row['player_count'],
            'players_url': _team_players_url(row['team']),
        }
        for row in team_rows
    ]

    return JsonResponse({
        'season': season,
        'view': view,
        'count': len(teams),
        'teams': teams,
        'image_url': '/api/team-image',
    })


def api_team_players(request, team_code):
    view = _normalize_stat_view(request.GET.get('view'))
    season = _resolve_stat_season(view, request.GET.get('season'))
    filtered_lines = _filter_stat_lines(view, season, team_code=team_code)

    if not filtered_lines.exists():
        return JsonResponse({'message': f'Team {team_code} was not found for season {season}.'}, status=404)

    players = [
        _serialize_stat_player(stat_line)
        for stat_line in filtered_lines.order_by('-war', 'player_name')
    ]

    return JsonResponse({
        'season': season,
        'view': view,
        'team': team_code.upper(),
        'count': len(players),
        'players': players,
    })


def api_team_player_detail(request, team_code, player_id):
    view = _normalize_stat_view(request.GET.get('view'))
    requested_season = request.GET.get('season')
    player_identity = Q(mlbam_id=str(player_id))
    if requested_season:
        season = _resolve_stat_season(view, requested_season)
        target_line = _filter_stat_lines(view, season, team_code=team_code).filter(player_identity).first()
    else:
        target_line = (
            _filter_stat_lines(view, None, team_code=team_code)
            .filter(player_identity)
            .order_by('-season', '-war', 'player_name')
            .first()
        )
        season = target_line.season if target_line is not None else _resolve_stat_season(view, None)
    if target_line is None:
        return JsonResponse(
            {'message': f'Player {player_id} was not found for team {team_code} in season {season}.'},
            status=404,
        )

    player_payload = _serialize_stat_player(target_line)
    player_payload['photo_url'] = _resolve_stat_player_photo_url(target_line)
    if requested_season:
        history = [player_payload]
    else:
        history = [
            _serialize_stat_player(stat_line)
            for stat_line in _player_history_queryset(view, target_line)[:PLAYER_HISTORY_LIMIT]
        ]

    euclidean_similar_players = _team_detail_similar_players(view, target_line)
    tabnet_similar_players = _team_detail_similar_player_recommendations(view, target_line)

    return JsonResponse({
        'season': season,
        'view': view,
        'team': team_code.upper(),
        'player': player_payload,
        'euclidean_similar_players': euclidean_similar_players,
        'tabnet_similar_players': tabnet_similar_players,
        'similar_players': euclidean_similar_players,
        'similar_player_recommendations': tabnet_similar_players,
        'history_count': len(history),
        'history': history,
    })


def api_rosters(request):
    season = _resolve_roster_season(request.GET.get('season'))
    filtered_entries = _filter_roster_entries(season)
    team_rows = list(
        filtered_entries
        .values('team_abbreviation', 'team_name')
        .annotate(player_count=Count('id'))
        .order_by('team_abbreviation')
    )
    teams = [
        {
            'code': row['team_abbreviation'],
            'name': row['team_name'],
            'season': season,
            'player_count': row['player_count'],
            'roster_url': _roster_team_url(row['team_abbreviation']),
        }
        for row in team_rows
    ]

    return JsonResponse({
        'season': season,
        'count': len(teams),
        'teams': teams,
    })


def api_team_roster(request, team_code):
    season = _resolve_roster_season(request.GET.get('season'))
    filtered_entries = _filter_roster_entries(season, team_code=team_code)

    if not filtered_entries.exists():
        return JsonResponse({'message': f'Team {team_code} was not found for season {season}.'}, status=404)

    team_name = filtered_entries.values_list('team_name', flat=True).first()
    roster_entries = list(filtered_entries.order_by('player_name', 'player_id'))
    roster_player_ids = [str(entry.player_id) for entry in roster_entries]
    photo_map = {}
    if roster_entries:
        team_name = roster_entries[0].team_name
        normalized_names = [_normalize_photo_name(entry.player_name) for entry in roster_entries]
        photo_map = {
            photo.normalized_player_name: photo
            for photo in MLBRosterPhoto.objects.filter(
                team_name=team_name,
                normalized_player_name__in=normalized_names,
            )
        }
    batting_season = _resolve_roster_stat_season(MLBApiStatLine.VIEW_BATTING, season)
    pitching_season = _resolve_roster_stat_season(MLBApiStatLine.VIEW_PITCHING, season)

    batting_by_mlbam = {}
    if batting_season is not None and roster_player_ids:
        batting_by_mlbam = {
            stat_line.mlbam_id: stat_line
            for stat_line in MLBApiStatLine.objects.filter(
                stat_view=MLBApiStatLine.VIEW_BATTING,
                season=batting_season,
                mlbam_id__in=roster_player_ids,
            )
        }

    pitching_by_mlbam = {}
    if pitching_season is not None and roster_player_ids:
        pitching_by_mlbam = {
            stat_line.mlbam_id: stat_line
            for stat_line in MLBApiStatLine.objects.filter(
                stat_view=MLBApiStatLine.VIEW_PITCHING,
                season=pitching_season,
                mlbam_id__in=roster_player_ids,
            )
        }

    players = []
    for entry in roster_entries:
        player_payload = _serialize_roster_entry(entry)
        mlbam_id = str(entry.player_id)
        if _find_roster_photo(entry.team_name, entry.player_name, photo_map=photo_map) is not None:
            player_payload['photo_url'] = _roster_player_photo_url(entry.team_abbreviation, entry.player_id, season=entry.season)
        batting_payload = _serialize_roster_stat_line(batting_by_mlbam.get(mlbam_id))
        pitching_payload = _serialize_roster_stat_line(pitching_by_mlbam.get(mlbam_id))
        player_payload['batting'] = batting_payload if _has_meaningful_roster_stats(batting_payload, MLBApiStatLine.VIEW_BATTING) else None
        player_payload['pitching'] = pitching_payload if _has_meaningful_roster_stats(pitching_payload, MLBApiStatLine.VIEW_PITCHING) else None
        players.append(player_payload)

    return JsonResponse({
        'season': season,
        'team': team_code.upper(),
        'team_name': team_name,
        'stat_seasons': {
            'batting': batting_season,
            'pitching': pitching_season,
        },
        'count': len(players),
        'players': players,
    })


def api_roster_player_detail(request, team_code, player_id):
    raw_season = request.GET.get('season')
    roster_season = _resolve_roster_season(raw_season)
    roster_entry = _resolve_roster_entry_by_identifier(team_code, roster_season, player_id)

    if roster_entry is None:
        return JsonResponse(
            {'message': f'Player {player_id} was not found for team {team_code} in roster season {roster_season}.'},
            status=404,
        )

    requested_stat_season = _to_int(raw_season, None) if raw_season not in (None, '') else None
    history = _build_roster_player_history(roster_entry, player_id, requested_stat_season=requested_stat_season)

    photo = _find_roster_photo(roster_entry.team_name, roster_entry.player_name)
    current_stats = history[0] if history else {'batting': None, 'pitching': None}
    player_payload = _serialize_roster_entry(roster_entry)
    if photo is not None:
        player_payload['photo_url'] = _roster_player_photo_url(
            roster_entry.team_abbreviation,
            roster_entry.player_id,
            season=roster_entry.season,
        )
    player_payload['batting'] = current_stats.get('batting')
    player_payload['pitching'] = current_stats.get('pitching')

    response_season = requested_stat_season
    if response_season is None and history:
        response_season = history[0]['season']

    euclidean_similar_players = _roster_detail_similar_players(roster_entry, player_id)
    tabnet_similar_players = _roster_detail_similar_player_recommendations(roster_entry, player_id)

    return JsonResponse({
        'season': response_season,
        'roster_season': roster_entry.season,
        'team': roster_entry.team_abbreviation.upper(),
        'team_name': roster_entry.team_name,
        'player': player_payload,
        'euclidean_similar_players': euclidean_similar_players,
        'tabnet_similar_players': tabnet_similar_players,
        'similar_players': euclidean_similar_players,
        'similar_player_recommendations': tabnet_similar_players,
        'history_count': len(history),
        'history': history,
    })


def api_roster_player_photo(request, team_code, player_id):
    season = _resolve_roster_season(request.GET.get('season'))
    entry = _filter_roster_entries(season, team_code=team_code).filter(player_id=player_id).first()
    if entry is None:
        raise Http404(f'Player {player_id} was not found for team {team_code} in season {season}.')

    photo = _find_roster_photo(entry.team_name, entry.player_name)
    if photo is None:
        raise Http404(f'Photo for {entry.player_name} was not found.')

    response = HttpResponse(bytes(photo.image_data), content_type=photo.content_type or 'application/octet-stream')
    response['Content-Disposition'] = f'inline; filename="{photo.original_filename}"'
    return response


def _load_bp_rows():
    rows = []
    with LEADERBOARD_CSV.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for raw in reader:
            rows.append({
                'bpid': _to_int(raw.get('bpid')),
                'mlbid': _to_int(raw.get('mlbid')),
                'name': (raw.get('Name') or '').strip(),
                'age': _to_int(raw.get('Age')),
                'season': _to_int(raw.get('Season')),
                'team': (raw.get('Team') or '').strip(),
                'g': _to_int(raw.get('G')),
                'pa': _to_int(raw.get('PA')),
                'ab': _to_int(raw.get('AB')),
                'r': _to_int(raw.get('R')),
                'hr': _to_int(raw.get('HR')),
                'rbi': _to_int(raw.get('RBI')),
                'sb': _to_int(raw.get('SB')),
                'bb_pct': _to_float(raw.get('BB%')),
                'k_pct': _to_float(raw.get('K%')),
                'iso': _to_float(raw.get('ISO')),
                'avg': _to_float(raw.get('AVG')),
                'obp': _to_float(raw.get('OBP')),
                'slg': _to_float(raw.get('SLG')),
                'ops': _to_float(raw.get('OPS')),
                'drc_plus': _to_int(raw.get('DRC+')),
                'drb': _to_float(raw.get('DRB')),
                'drp': _to_float(raw.get('DRP')),
                'warp': _to_float(raw.get('WARP')),
            })
    return rows


def player_search(request):
    """BP 스타일 리더보드 페이지"""
    if request.GET.get('download') == '1' and LEADERBOARD_CSV.exists():
        return FileResponse(
            LEADERBOARD_CSV.open('rb'),
            as_attachment=True,
            filename=LEADERBOARD_CSV.name,
        )

    rows = _load_bp_rows() if LEADERBOARD_CSV.exists() else []

    seasons = sorted({r['season'] for r in rows if r['season']}, reverse=True)
    selected_season = request.GET.get('season') or (str(seasons[0]) if seasons else '')
    selected_team = request.GET.get('team', '')
    selected_pa_range = request.GET.get('pa_range', '')
    selected_age_range = request.GET.get('age', '')
    active_tab = request.GET.get('tab', 'summary')

    if selected_season:
        rows = [r for r in rows if str(r['season']) == selected_season]

    team_options = sorted({r['team'] for r in rows if r['team']})
    if selected_team:
        rows = [r for r in rows if r['team'] == selected_team]

    pa_values = [r['pa'] for r in rows if r['pa'] > 0]
    pa_min = min(pa_values) if pa_values else 0
    pa_max = max(pa_values) if pa_values else 0
    pa_range_options = [
        {'value': f'{pa_min}-{pa_max}', 'label': f'{pa_min} - {pa_max}'},
        {'value': f'650-{pa_max}', 'label': f'650 - {pa_max}'},
        {'value': f'550-{pa_max}', 'label': f'550 - {pa_max}'},
        {'value': f'450-{pa_max}', 'label': f'450 - {pa_max}'},
    ] if pa_max else []
    pa_range_options = [opt for opt in pa_range_options if _to_int(opt['value'].split('-')[0]) <= pa_max]
    if not selected_pa_range and pa_range_options:
        selected_pa_range = pa_range_options[0]['value']

    if selected_pa_range and '-' in selected_pa_range:
        start_text, end_text = selected_pa_range.split('-', 1)
        pa_start = _to_int(start_text, pa_min)
        pa_end = _to_int(end_text, pa_max)
        rows = [r for r in rows if pa_start <= r['pa'] <= pa_end]

    age_ranges = [
        {'value': '', 'label': 'All Ages'},
        {'value': 'u25', 'label': 'Under 25'},
        {'value': '25_29', 'label': '25 - 29'},
        {'value': '30_34', 'label': '30 - 34'},
        {'value': '35p', 'label': '35+'},
    ]
    if selected_age_range == 'u25':
        rows = [r for r in rows if r['age'] <= 24]
    elif selected_age_range == '25_29':
        rows = [r for r in rows if 25 <= r['age'] <= 29]
    elif selected_age_range == '30_34':
        rows = [r for r in rows if 30 <= r['age'] <= 34]
    elif selected_age_range == '35p':
        rows = [r for r in rows if r['age'] >= 35]

    rows.sort(key=lambda r: r['warp'], reverse=True)
    for idx, row in enumerate(rows, start=1):
        row['rank'] = idx
        row['team_display'] = row['team'] or 'FA'
        row['bb_pct_display'] = f"{row['bb_pct']:.1f}%"
        row['k_pct_display'] = f"{row['k_pct']:.1f}%"
        row['iso_display'] = _format_rate(row['iso'])
        row['avg_display'] = _format_rate(row['avg'])
        row['obp_display'] = _format_rate(row['obp'])
        row['slg_display'] = _format_rate(row['slg'])
        row['ops_display'] = f"{row['ops']:.3f}"
        row['drb_display'] = f"{row['drb']:.1f}"
        row['drp_display'] = f"{row['drp']:.1f}"
        row['warp_display'] = f"{row['warp']:.1f}"

    visible_rows = rows[:LEADERBOARD_PAGE_SIZE]

    for row in visible_rows:
        row['player_pk'] = _resolve_leaderboard_player_pk(row.get('name'), row.get('team'))

    context = {
        'rows': visible_rows,
        'showing_count': len(visible_rows),
        'total_count': len(rows),
        'season_options': seasons,
        'selected_season': selected_season,
        'team_options': team_options,
        'selected_team': selected_team,
        'pa_range_options': pa_range_options,
        'selected_pa_range': selected_pa_range,
        'age_ranges': age_ranges,
        'selected_age_range': selected_age_range,
        'active_tab': active_tab,
    }
    return render(request, 'mlb/search.html', context)


def player_detail(request, pk):
    """선수 상세 페이지"""
    player = get_object_or_404(
        MLBPlayer.objects.select_related('prediction').prefetch_related(
            'seasons',
            'similar_from',
            'similar_from__similar_player',
        ),
        pk=pk,
    )

    seasons = list(player.seasons.all().order_by('-year')[:10])
    similar = list(player.similar_from.select_related('similar_player').order_by('rank')[:5])

    seasons_json = json.dumps([
        {
            'year': s.year,
            'avg': str(s.avg) if s.avg else None,
            'ops': str(s.ops) if s.ops else None,
            'hr': s.hr,
            'era': str(s.era) if s.era else None,
            'war': str(s.war) if s.war is not None else None,
            'woba': str(s.woba) if s.woba is not None else None,
            'wrc_plus': s.wrc_plus,
            'babip': str(s.babip) if s.babip is not None else None,
            'ops_plus': s.ops_plus,
            'fip': str(s.fip) if s.fip is not None else None,
            'xfip': str(s.xfip) if s.xfip is not None else None,
            'k_per_9': str(s.k_per_9) if s.k_per_9 is not None else None,
            'bb_per_9': str(s.bb_per_9) if s.bb_per_9 is not None else None,
        }
        for s in seasons
    ])

    is_batter = bool(seasons and seasons[0].ab > 0)
    pred = getattr(player, 'prediction', None)
    prediction_json = json.dumps({
        'next_year_avg': str(pred.next_year_avg) if pred and pred.next_year_avg is not None else None,
        'next_year_hr': pred.next_year_hr if pred and pred.next_year_hr is not None else None,
        'next_year_ops': str(pred.next_year_ops) if pred and pred.next_year_ops is not None else None,
        'next_year_war': str(pred.next_year_war) if pred and pred.next_year_war is not None else None,
        'next_year_woba': str(pred.next_year_woba) if pred and pred.next_year_woba is not None else None,
        'next_year_wrc_plus': pred.next_year_wrc_plus if pred and pred.next_year_wrc_plus is not None else None,
        'next_year_era': str(pred.next_year_era) if pred and pred.next_year_era is not None else None,
        'next_year_fip': str(pred.next_year_fip) if pred and pred.next_year_fip is not None else None,
    })

    # Next 10 years forecast table (mock data)
    forecast_start_year = (seasons[0].year + 1) if seasons else 2026
    forecast_years = list(range(forecast_start_year, forecast_start_year + 10))

    def _mock_forecast_rows():
        if is_batter:
            base_avg = float(pred.next_year_avg) if pred and pred.next_year_avg else 0.275
            base_hr = (pred.next_year_hr or 25) if pred else 25
            base_ops = float(pred.next_year_ops) if pred and pred.next_year_ops else 0.820
            base_war = float(pred.next_year_war) if pred and pred.next_year_war else 3.0
            base_woba = float(pred.next_year_woba) if pred and pred.next_year_woba else 0.340
            base_wrc = (pred.next_year_wrc_plus or 110) if pred else 110
            rows = []
            for i in range(10):
                decay = 1.0 - (i * 0.012)
                rows.append({
                    'avg': f'{base_avg * decay + (i * 0.001):.3f}',
                    'hr': max(0, int(base_hr * decay + (i % 3 - 1))),
                    'ops': f'{(base_ops * decay + i * 0.005):.3f}',
                    'war': f'{(base_war * decay - i * 0.15):.1f}',
                    'woba': f'{(base_woba * decay):.3f}',
                    'wrc_plus': max(50, int(base_wrc * decay - i * 2)),
                })
            return rows
        else:
            base_era = float(pred.next_year_era) if pred and pred.next_year_era else 3.80
            base_fip = float(pred.next_year_fip) if pred and pred.next_year_fip else 3.70
            base_war = float(pred.next_year_war) if pred and pred.next_year_war else 2.0
            rows = []
            for i in range(10):
                decay = 1.0 + (i * 0.015)
                rows.append({
                    'era': f'{(base_era * decay + i * 0.05):.2f}',
                    'fip': f'{(base_fip * decay + i * 0.04):.2f}',
                    'war': f'{(base_war * (1.0 - i * 0.08)):.1f}',
                    'k_per_9': f'{(9.2 - i * 0.15):.1f}',
                    'bb_per_9': f'{(2.8 + i * 0.05):.1f}',
                })
            return rows

    forecast_rows = _mock_forecast_rows()
    forecast_data = list(zip(forecast_years, forecast_rows))

    context = {
        'player': player,
        'seasons': seasons,
        'seasons_json': seasons_json,
        'prediction_json': prediction_json,
        'similar_data': [(s.similar_player, s.similarity_score) for s in similar],
        'is_batter': is_batter,
        'forecast_years': forecast_years,
        'forecast_rows': forecast_rows,
        'forecast_data': forecast_data,
    }
    return render(request, 'mlb/player_detail.html', context)


def valuation_settings_view(request):
    """Global valuation settings page for choosing $/WAR engine."""
    settings_obj = ValuationSettings.get_solo()
    if request.method == "POST":
        form = ValuationSettingsForm(request.POST, instance=settings_obj)
        if form.is_valid():
            form.save()
            return redirect('mlb:valuation_settings')
    else:
        form = ValuationSettingsForm(instance=settings_obj)

    return render(request, 'mlb/valuation_settings.html', {'form': form})
