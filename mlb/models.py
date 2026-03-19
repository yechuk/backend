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

