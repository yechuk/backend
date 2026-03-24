import csv
import json
from pathlib import Path

from django.conf import settings
from django.db.models import Count
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ValuationSettingsForm
from .models import MLBApiStatLine, MLBPlayer, ValuationSettings


LEADERBOARD_CSV = Path(settings.BASE_DIR) / 'data' / 'bp_export_20260312.csv'
LEADERBOARD_PAGE_SIZE = 60
SUPPORTED_STAT_VIEWS = {'batting', 'pitching'}


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


def _serialize_stat_player(stat_line):
    row = stat_line.raw_stats or {}
    view = stat_line.stat_view
    base = {
        'id': stat_line.external_player_id,
        'player_id': stat_line.external_player_id,
        'mlbam_id': stat_line.mlbam_id,
        'name': stat_line.player_name,
        'name_ascii': stat_line.name_ascii,
        'team': stat_line.team,
        'season': stat_line.season,
        'age': stat_line.age,
        'view': view,
    }

    if view == 'pitching':
        base['stats'] = {
            'games': _to_int(row.get('G')),
            'games_started': _to_int(row.get('GS')),
            'innings_pitched': _to_float(row.get('IP')),
            'walks': _to_int(row.get('BB')),
            'hr_per_9': _to_float(row.get('HR/9')),
            'strikeout_rate': _to_float(row.get('K%')),
            'fip': _to_float(row.get('FIP')),
            'war': stat_line.war if stat_line.war is not None else _to_float(row.get('WAR')),
        }
    else:
        base['stats'] = {
            'games': _to_int(row.get('G')),
            'plate_appearances': _to_int(row.get('PA')),
            'home_runs': _to_int(row.get('HR')),
            'stolen_bases': _to_int(row.get('SB')),
            'iso': _to_float(row.get('ISO')),
            'walk_rate': _to_float(row.get('BB%')),
            'strikeout_rate': _to_float(row.get('K%')),
            'woba': _to_float(row.get('wOBA')),
            'wrc_plus': _to_int(row.get('wRC+')) if row.get('wRC+') else None,
            'babip': _to_float(row.get('BABIP')),
            'war': stat_line.war if stat_line.war is not None else _to_float(row.get('WAR')),
        }

    base['detail_url'] = _player_detail_url(base['team'], base['player_id'])
    return base


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
    season = _resolve_stat_season(view, request.GET.get('season'))
    target_line = _filter_stat_lines(view, season, team_code=team_code).filter(
        external_player_id=str(player_id)
    ).first()
    if target_line is None:
        return JsonResponse(
            {'message': f'Player {player_id} was not found for team {team_code} in season {season}.'},
            status=404,
        )

    return JsonResponse({
        'season': season,
        'view': view,
        'team': team_code.upper(),
        'player': _serialize_stat_player(target_line),
    })


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
