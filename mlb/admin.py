from django.contrib import admin

from .models import (
    MLBApiAavPrediction,
    MLBApiPerformanceValuePrediction,
    MLBApiRecommendedSimilarPlayer,
    MLBApiSimilarPlayer,
    MLBPlayer,
    MLBPlayerPrediction,
    MLBPlayerSeason,
    MLBRosterEntry,
    MLBSimilarPlayer,
)


class MLBPlayerSeasonInline(admin.TabularInline):
    model = MLBPlayerSeason
    extra = 0


@admin.register(MLBPlayer)
class MLBPlayerAdmin(admin.ModelAdmin):
    list_display = ['name', 'team', 'position']
    list_filter = ['team', 'position']
    search_fields = ['name']
    inlines = [MLBPlayerSeasonInline]


@admin.register(MLBPlayerPrediction)
class MLBPlayerPredictionAdmin(admin.ModelAdmin):
    list_display = ['player', 'predicted_value', 'next_year_avg', 'next_year_hr', 'next_year_ops', 'next_year_era']


@admin.register(MLBSimilarPlayer)
class MLBSimilarPlayerAdmin(admin.ModelAdmin):
    list_display = ['player', 'similar_player', 'similarity_score', 'rank']


@admin.register(MLBRosterEntry)
class MLBRosterEntryAdmin(admin.ModelAdmin):
    list_display = ['season', 'team_abbreviation', 'player_name', 'position_abbreviation', 'status_code']
    list_filter = ['season', 'team_abbreviation', 'position_abbreviation', 'status_code']
    search_fields = ['player_name', 'team_name', 'player_id']


@admin.register(MLBApiSimilarPlayer)
class MLBApiSimilarPlayerAdmin(admin.ModelAdmin):
    list_display = ['stat_view', 'source_player_name', 'rank', 'similar_player_name', 'similarity_score']
    list_filter = ['stat_view']
    search_fields = ['source_player_name', 'similar_player_name', 'source_mlbam_id', 'similar_mlbam_id']


@admin.register(MLBApiRecommendedSimilarPlayer)
class MLBApiRecommendedSimilarPlayerAdmin(admin.ModelAdmin):
    list_display = ['stat_view', 'source_player_name', 'rank', 'similar_player_name', 'similarity_score']
    list_filter = ['stat_view']
    search_fields = ['source_player_name', 'similar_player_name', 'source_mlbam_id', 'similar_mlbam_id']


@admin.register(MLBApiAavPrediction)
class MLBApiAavPredictionAdmin(admin.ModelAdmin):
    list_display = ['source_label', 'season', 'stat_view', 'player_name', 'predicted_aav_millions']
    list_filter = ['source_label', 'season', 'stat_view']
    search_fields = ['player_name', 'name_ascii', 'team_code_raw']


@admin.register(MLBApiPerformanceValuePrediction)
class MLBApiPerformanceValuePredictionAdmin(admin.ModelAdmin):
    list_display = [
        'source_label',
        'season',
        'stat_view',
        'player_name',
        'target_team',
        'predicted_value_millions',
    ]
    list_filter = ['source_label', 'season', 'stat_view', 'target_team']
    search_fields = ['player_name', 'name_ascii', 'current_team', 'target_team']
