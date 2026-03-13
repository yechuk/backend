from decimal import Decimal

from django.db import models

from .services import calculate_net_worth


class Player(models.Model):
    STATUS_CHOICES = [
        ('pending', '대기'),
        ('active', '활성'),
        ('released', '방출'),
    ]

    name = models.CharField(max_length=100)
    position = models.CharField(max_length=50)
    jersey_number = models.PositiveIntegerField(null=True, blank=True)
    years_to_retirement = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='Years to retirement',
        help_text='Years left until expected retirement',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.position})"


class Contract(models.Model):
    player = models.OneToOneField(
        Player,
        on_delete=models.CASCADE,
        related_name='contract',
        null=True,
        blank=True,
    )
    total_value = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        help_text='Total contract amount',
    )
    guaranteed_ratio = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal('1.00'),
        help_text='Ratio of guaranteed salary to total (0-1, e.g. 0.8 = 80%)',
    )
    years = models.PositiveIntegerField(help_text='Contract length in years')
    start_year = models.PositiveIntegerField(null=True, blank=True)

    def __str__(self):
        return f"Contract for {self.player.name if self.player else 'Unknown'}"

    @property
    def guaranteed_amount(self):
        return self.total_value * self.guaranteed_ratio

    @property
    def net_worth(self):
        return calculate_net_worth(
            self.total_value,
            self.guaranteed_ratio,
            self.years,
        )
