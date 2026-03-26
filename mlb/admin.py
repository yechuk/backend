from django.contrib import admin

from .models import MLBPlayer, MLBPlayerPrediction, MLBPlayerSeason, MLBRosterEntry, MLBSimilarPlayer


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
