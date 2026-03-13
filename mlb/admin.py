from django.contrib import admin

from .models import MLBPlayer, MLBPlayerPrediction, MLBPlayerSeason, MLBSimilarPlayer


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
