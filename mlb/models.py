from decimal import Decimal

from django.db import models


class MLBPlayer(models.Model):
    """MLB 선수 기본 정보"""

    POSITION_CHOICES = [
        ('P', 'Pitcher'),
        ('C', 'Catcher'),
        ('1B', 'First Base'),
        ('2B', 'Second Base'),
        ('3B', 'Third Base'),
        ('SS', 'Shortstop'),
        ('LF', 'Left Field'),
        ('CF', 'Center Field'),
        ('RF', 'Right Field'),
        ('DH', 'Designated Hitter'),
    ]

    name = models.CharField(max_length=100)
    team = models.CharField(max_length=50, blank=True)
    position = models.CharField(max_length=10, choices=POSITION_CHOICES, blank=True)
    photo_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'MLB Player'
        verbose_name_plural = 'MLB Players'

    def __str__(self):
        return f"{self.name} ({self.team or 'FA'})"


class MLBPlayerSeason(models.Model):
    """선수 시즌별 성적"""

    player = models.ForeignKey(MLBPlayer, on_delete=models.CASCADE, related_name='seasons')
    year = models.PositiveIntegerField()
    team = models.CharField(max_length=50, blank=True)
    # Batter stats
    ab = models.PositiveIntegerField(default=0)
    hits = models.PositiveIntegerField(default=0)
    hr = models.PositiveIntegerField(default=0)
    rbi = models.PositiveIntegerField(default=0)
    avg = models.DecimalField(max_digits=4, decimal_places=3, default=Decimal('0'))
    obp = models.DecimalField(max_digits=4, decimal_places=3, default=Decimal('0'))
    slg = models.DecimalField(max_digits=4, decimal_places=3, default=Decimal('0'))
    ops = models.DecimalField(max_digits=5, decimal_places=3, default=Decimal('0'))
    # Sabermetrics — Batter
    war = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, help_text='Wins Above Replacement')
    woba = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True, help_text='Weighted On-Base Average')
    wrc_plus = models.PositiveIntegerField(null=True, blank=True, help_text='wRC+ (100 = league average)')
    babip = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True, help_text='Batting Average on Balls in Play')
    ops_plus = models.PositiveIntegerField(null=True, blank=True, help_text='OPS+ (100 = league average)')
    # Pitcher stats
    ip = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'))
    era = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('0'))
    so = models.PositiveIntegerField(default=0)
    bb = models.PositiveIntegerField(default=0)
    whip = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('0'))
    # Sabermetrics — Pitcher
    fip = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text='Fielding Independent Pitching')
    xfip = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text='Expected FIP')
    k_per_9 = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, help_text='Strikeouts per 9 IP')
    bb_per_9 = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, help_text='Walks per 9 IP')

    class Meta:
        ordering = ['-year']
        unique_together = ['player', 'year']
        verbose_name = 'MLB Player Season'
        verbose_name_plural = 'MLB Player Seasons'

    def __str__(self):
        return f"{self.player.name} {self.year}"


class MLBApiStatLine(models.Model):
    """DB-backed stat lines used by the /api/teams endpoints."""

    VIEW_BATTING = 'batting'
    VIEW_PITCHING = 'pitching'
    VIEW_CHOICES = [
        (VIEW_BATTING, 'Batting'),
        (VIEW_PITCHING, 'Pitching'),
    ]

    stat_view = models.CharField(max_length=20, choices=VIEW_CHOICES, db_index=True)
    season = models.PositiveIntegerField(db_index=True)
    team = models.CharField(max_length=10, db_index=True)
    player_name = models.CharField(max_length=100)
    name_ascii = models.CharField(max_length=100, blank=True)
    external_player_id = models.CharField(max_length=32, db_index=True)
    mlbam_id = models.CharField(max_length=32, blank=True, db_index=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    war = models.FloatField(null=True, blank=True)
    raw_stats = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['stat_view', '-season', 'team', 'player_name']
        unique_together = ['stat_view', 'season', 'mlbam_id']
        verbose_name = 'MLB API Stat Line'
        verbose_name_plural = 'MLB API Stat Lines'

    def __str__(self):
        return f'{self.stat_view} {self.season} {self.player_name} ({self.team})'


class MLBRosterEntry(models.Model):
    """Season roster snapshot imported from MLB StatsAPI."""

    season = models.PositiveIntegerField(db_index=True)
    team_id = models.PositiveIntegerField(db_index=True)
    team_name = models.CharField(max_length=100)
    team_abbreviation = models.CharField(max_length=10, db_index=True)
    league_name = models.CharField(max_length=100, blank=True)
    division_name = models.CharField(max_length=100, blank=True)
    player_id = models.PositiveIntegerField(db_index=True)
    player_name = models.CharField(max_length=100)
    player_link = models.CharField(max_length=100, blank=True)
    jersey_number = models.CharField(max_length=10, blank=True)
    position_code = models.CharField(max_length=10, blank=True)
    position_name = models.CharField(max_length=50, blank=True)
    position_type = models.CharField(max_length=50, blank=True)
    position_abbreviation = models.CharField(max_length=10, blank=True)
    status_code = models.CharField(max_length=10, blank=True)
    status_description = models.CharField(max_length=50, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-season', 'team_abbreviation', 'player_name']
        unique_together = ['season', 'team_id', 'player_id']
        verbose_name = 'MLB Roster Entry'
        verbose_name_plural = 'MLB Roster Entries'

    def __str__(self):
        return f'{self.season} {self.team_abbreviation} {self.player_name}'


class MLBRosterPhoto(models.Model):
    """Player photo assets loaded from data/<Team Name>/ into the DB."""

    team_name = models.CharField(max_length=100, db_index=True)
    player_name = models.CharField(max_length=100)
    normalized_player_name = models.CharField(max_length=120, db_index=True)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    image_data = models.BinaryField()
    byte_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['team_name', 'player_name']
        unique_together = ['team_name', 'normalized_player_name']
        verbose_name = 'MLB Roster Photo'
        verbose_name_plural = 'MLB Roster Photos'

    def __str__(self):
        return f'{self.team_name} {self.player_name}'


class MLBApiSimilarPlayer(models.Model):
    """API-facing similar player rows imported from CSVs for batting/pitching detail endpoints."""

    stat_view = models.CharField(max_length=20, choices=MLBApiStatLine.VIEW_CHOICES, db_index=True)
    source_player_name = models.CharField(max_length=100)
    source_name_ascii = models.CharField(max_length=100, blank=True, db_index=True)
    source_mlbam_id = models.CharField(max_length=32, blank=True, db_index=True)
    source_external_player_id = models.CharField(max_length=32, blank=True, db_index=True)
    similar_player_name = models.CharField(max_length=100)
    similar_name_ascii = models.CharField(max_length=100, blank=True, db_index=True)
    similar_mlbam_id = models.CharField(max_length=32, blank=True, db_index=True)
    similar_external_player_id = models.CharField(max_length=32, blank=True, db_index=True)
    similar_team = models.CharField(max_length=10, blank=True)
    similarity_score = models.PositiveIntegerField(default=0)
    rank = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['stat_view', 'source_player_name', 'rank']
        unique_together = ['stat_view', 'source_name_ascii', 'rank']
        verbose_name = 'MLB API Similar Player'
        verbose_name_plural = 'MLB API Similar Players'

    def __str__(self):
        return f'{self.stat_view} {self.source_player_name} -> {self.similar_player_name} ({self.rank})'


class MLBApiRecommendedSimilarPlayer(models.Model):
    """Recommendation-based similar player rows imported from recommendation CSVs."""

    stat_view = models.CharField(max_length=20, choices=MLBApiStatLine.VIEW_CHOICES, db_index=True)
    source_player_name = models.CharField(max_length=100)
    source_name_ascii = models.CharField(max_length=100, blank=True, db_index=True)
    source_mlbam_id = models.CharField(max_length=32, blank=True, db_index=True)
    source_external_player_id = models.CharField(max_length=32, blank=True, db_index=True)
    source_player_position = models.CharField(max_length=10, blank=True)
    source_player_age = models.PositiveSmallIntegerField(null=True, blank=True)
    similar_player_name = models.CharField(max_length=100)
    similar_name_ascii = models.CharField(max_length=100, blank=True, db_index=True)
    similar_mlbam_id = models.CharField(max_length=32, blank=True, db_index=True)
    similar_external_player_id = models.CharField(max_length=32, blank=True, db_index=True)
    similar_team = models.CharField(max_length=10, blank=True)
    similar_player_position = models.CharField(max_length=10, blank=True)
    similar_player_age = models.PositiveSmallIntegerField(null=True, blank=True)
    similarity_score = models.DecimalField(max_digits=12, decimal_places=9, default=Decimal('0'))
    rank = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['stat_view', 'source_player_name', 'rank']
        unique_together = ['stat_view', 'source_name_ascii', 'rank']
        verbose_name = 'MLB API Recommended Similar Player'
        verbose_name_plural = 'MLB API Recommended Similar Players'

    def __str__(self):
        return f'{self.stat_view} {self.source_player_name} -> {self.similar_player_name} ({self.rank})'


class MLBApiAavPrediction(models.Model):
    """API-facing AAV prediction rows imported from offline workbook exports."""

    stat_view = models.CharField(max_length=20, choices=MLBApiStatLine.VIEW_CHOICES, db_index=True)
    season = models.PositiveIntegerField(db_index=True)
    source_label = models.CharField(max_length=32, default='M1')
    source_file = models.CharField(max_length=255, blank=True)
    player_name = models.CharField(max_length=100)
    name_ascii = models.CharField(max_length=100, blank=True, db_index=True)
    team_code_raw = models.CharField(max_length=10, blank=True)
    position_raw = models.CharField(max_length=20, blank=True)
    actual_aav_millions = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    predicted_aav_millions = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    prediction_error_millions = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-season', 'player_name']
        unique_together = ['season', 'stat_view', 'name_ascii']
        verbose_name = 'MLB API AAV Prediction'
        verbose_name_plural = 'MLB API AAV Predictions'

    def __str__(self):
        return f'{self.source_label} {self.season} {self.player_name}'


class MLBApiPerformanceValuePrediction(models.Model):
    """API-facing WAR-based performance value rows imported from offline workbook exports."""

    stat_view = models.CharField(max_length=20, choices=MLBApiStatLine.VIEW_CHOICES, db_index=True)
    season = models.PositiveIntegerField(db_index=True)
    source_label = models.CharField(max_length=32, default='M2')
    source_file = models.CharField(max_length=255, blank=True)
    player_name = models.CharField(max_length=100)
    name_ascii = models.CharField(max_length=100, blank=True, db_index=True)
    player_type = models.CharField(max_length=20, blank=True)
    current_team = models.CharField(max_length=10, blank=True)
    target_team = models.CharField(max_length=10, db_index=True)
    war_2022 = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    predicted_war_avg = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    actual_war_avg = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    dollars_per_war_millions = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    predicted_value_millions = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-season', 'player_name', 'target_team']
        unique_together = ['season', 'stat_view', 'name_ascii', 'target_team']
        verbose_name = 'MLB API Performance Value Prediction'
        verbose_name_plural = 'MLB API Performance Value Predictions'

    def __str__(self):
        return f'{self.source_label} {self.season} {self.player_name} -> {self.target_team}'


class MLBApiFa2022Analysis(models.Model):
    """API-facing 2022 FA analysis rows imported from the final workbook."""

    stat_view = models.CharField(max_length=20, choices=MLBApiStatLine.VIEW_CHOICES, db_index=True)
    season = models.PositiveIntegerField(db_index=True)
    player_name = models.CharField(max_length=100)
    name_ascii = models.CharField(max_length=100, blank=True, db_index=True)
    previous_team = models.CharField(max_length=10, db_index=True)
    contract_team = models.CharField(max_length=10, blank=True)
    position = models.CharField(max_length=20, blank=True)
    is_re_signing = models.BooleanField(default=False)
    predicted_war = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    actual_aav_millions = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    predicted_aav_millions = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    position_scarcity_level = models.CharField(max_length=20, blank=True)
    position_scarcity_war_threshold = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    position_scarcity_comp_count = models.PositiveSmallIntegerField(null=True, blank=True)
    is_boras = models.BooleanField(default=False)
    age = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    age_signal_level = models.CharField(max_length=32, blank=True)
    age_signal_is_aging_risk = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['stat_view', 'previous_team', 'player_name']
        unique_together = ['season', 'stat_view', 'name_ascii', 'previous_team']
        verbose_name = 'MLB API FA 2022 Analysis'
        verbose_name_plural = 'MLB API FA 2022 Analyses'

    def __str__(self):
        return f'{self.season} {self.stat_view} {self.player_name} ({self.previous_team})'


class MLBApiTeamDollarPerWar(models.Model):
    """Team-level $/WAR rows imported from team_dollar_per_war.csv."""

    team = models.CharField(max_length=10, unique=True, db_index=True)
    avg_payroll_m_3yr = models.FloatField(null=True, blank=True)
    avg_batting_war_3yr = models.FloatField(null=True, blank=True)
    avg_pitching_war_3yr = models.FloatField(null=True, blank=True)
    avg_team_war_3yr = models.FloatField(null=True, blank=True)
    n_years = models.PositiveSmallIntegerField(null=True, blank=True)
    avg_team_war_3yr_safe = models.FloatField(null=True, blank=True)
    dollar_per_war_millions = models.FloatField(null=True, blank=True)
    dollar_per_war = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-dollar_per_war_millions', 'team']
        verbose_name = 'MLB API Team Dollar Per WAR'
        verbose_name_plural = 'MLB API Team Dollars Per WAR'

    def __str__(self):
        return f'{self.team} ${self.dollar_per_war_millions}/WAR'


class MLBApiWarNext3Prediction(models.Model):
    """API-facing next-three-year WAR predictions imported from CSV exports."""

    stat_view = models.CharField(max_length=20, choices=MLBApiStatLine.VIEW_CHOICES, db_index=True)
    player_name_key = models.CharField(max_length=120, db_index=True)
    player_name = models.CharField(max_length=100)
    name_ascii = models.CharField(max_length=100, blank=True)
    season = models.PositiveIntegerField(db_index=True)
    team = models.CharField(max_length=10, db_index=True)
    actual_war_next3_avg = models.FloatField(null=True, blank=True)
    pred_war_next3_avg = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['stat_view', '-season', 'team', 'player_name']
        unique_together = ['stat_view', 'season', 'player_name_key', 'team']
        verbose_name = 'MLB API WAR Next 3 Prediction'
        verbose_name_plural = 'MLB API WAR Next 3 Predictions'

    def __str__(self):
        return f'{self.stat_view} {self.season} {self.player_name} ({self.team})'


class MLBPlayerPrediction(models.Model):
    """선수 예측 데이터 (미래 성적, 적정 가치)"""

    player = models.OneToOneField(
        MLBPlayer,
        on_delete=models.CASCADE,
        related_name='prediction',
        null=True,
        blank=True,
    )
    predicted_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0'),
        help_text='Predicted market value (MRP)',
    )
    next_year_avg = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    next_year_hr = models.PositiveIntegerField(null=True, blank=True)
    next_year_ops = models.DecimalField(max_digits=5, decimal_places=3, null=True, blank=True)
    next_year_war = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    next_year_woba = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    next_year_wrc_plus = models.PositiveIntegerField(null=True, blank=True)
    next_year_era = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    next_year_fip = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'MLB Player Prediction'
        verbose_name_plural = 'MLB Player Predictions'

    def __str__(self):
        return f"Prediction for {self.player.name}"


class MLBSimilarPlayer(models.Model):
    """유사 선수 관계 (선수 A와 유사한 선수 B)"""

    player = models.ForeignKey(
        MLBPlayer,
        on_delete=models.CASCADE,
        related_name='similar_from',
    )
    similar_player = models.ForeignKey(
        MLBPlayer,
        on_delete=models.CASCADE,
        related_name='similar_to',
    )
    similarity_score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=Decimal('0'),
        help_text='0-1, higher = more similar',
    )
    rank = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['player', 'rank']
        unique_together = ['player', 'similar_player']
        verbose_name = 'MLB Similar Player'
        verbose_name_plural = 'MLB Similar Players'


class ValuationSettings(models.Model):
    """
    Global valuation settings for the MLB app.

    Currently only stores which $/WAR engine to use when valuing players:
    - 'linear': linear regression-based $/WAR by position (from scripts/estimate_position_dollars_per_war.py)
    - 'ml': nonlinear ML/DL-based engine.
    """

    VALUATION_METHOD_LINEAR = "linear"
    VALUATION_METHOD_ML = "ml"

    VALUATION_METHOD_CHOICES = [
        (VALUATION_METHOD_LINEAR, "Linear regression (recommended)"),
        (VALUATION_METHOD_ML, "Nonlinear ML/DL (experimental)"),
    ]

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    valuation_method = models.CharField(
        max_length=16,
        choices=VALUATION_METHOD_CHOICES,
        default=VALUATION_METHOD_LINEAR,
    )

    class Meta:
        verbose_name = "Valuation Settings"
        verbose_name_plural = "Valuation Settings"

    @classmethod
    def get_solo(cls) -> "ValuationSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
