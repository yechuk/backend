from decimal import Decimal

from django.core.management.base import BaseCommand

from mlb.models import MLBPlayer, MLBPlayerPrediction, MLBPlayerSeason, MLBSimilarPlayer


def _batter_season(year, team, ab, hits, hr, rbi, avg, obp, slg, ops, war, woba, wrc_plus, babip, ops_plus):
    return {'year': year, 'team': team, 'ab': ab, 'hits': hits, 'hr': hr, 'rbi': rbi,
            'avg': avg, 'obp': obp, 'slg': slg, 'ops': ops,
            'war': war, 'woba': woba, 'wrc_plus': wrc_plus, 'babip': babip, 'ops_plus': ops_plus}


def _pitcher_season(year, team, ip, era, so, bb, whip, war, fip, xfip, k_per_9, bb_per_9):
    return {'year': year, 'team': team, 'ip': ip, 'era': era, 'so': so, 'bb': bb, 'whip': whip,
            'war': war, 'fip': fip, 'xfip': xfip, 'k_per_9': k_per_9, 'bb_per_9': bb_per_9}


SAMPLE_PLAYERS = [
    {
        'name': 'Shohei Ohtani',
        'team': 'LAD',
        'position': 'DH',
        'seasons': [
            _batter_season(2024, 'LAD', 500, 155, 44, 95, 0.310, 0.412, 0.654, 1.066, 6.8, 0.420, 185, 0.318, 175),
            _batter_season(2023, 'LAA', 497, 151, 44, 95, 0.304, 0.412, 0.654, 1.066, 10.0, 0.430, 180, 0.305, 180),
            _batter_season(2022, 'LAA', 586, 160, 34, 95, 0.273, 0.356, 0.519, 0.875, 6.2, 0.370, 145, 0.290, 145),
        ],
        'prediction': {'predicted_value': 45000000, 'next_year_avg': 0.305, 'next_year_hr': 42, 'next_year_ops': 1.050,
                       'next_year_war': 6.5, 'next_year_woba': 0.415, 'next_year_wrc_plus': 175},
    },
    {
        'name': 'Aaron Judge',
        'team': 'NYY',
        'position': 'RF',
        'seasons': [
            _batter_season(2024, 'NYY', 520, 156, 37, 98, 0.300, 0.420, 0.613, 1.033, 5.2, 0.405, 165, 0.295, 165),
            _batter_season(2023, 'NYY', 367, 98, 37, 75, 0.267, 0.406, 0.613, 1.019, 4.5, 0.395, 174, 0.275, 170),
            _batter_season(2022, 'NYY', 570, 177, 62, 131, 0.311, 0.425, 0.686, 1.111, 10.6, 0.458, 207, 0.311, 211),
        ],
        'prediction': {'predicted_value': 38000000, 'next_year_avg': 0.285, 'next_year_hr': 42, 'next_year_ops': 1.000,
                       'next_year_war': 5.0, 'next_year_woba': 0.400, 'next_year_wrc_plus': 160},
    },
    {
        'name': 'Mookie Betts',
        'team': 'LAD',
        'position': 'RF',
        'seasons': [
            _batter_season(2024, 'LAD', 580, 174, 28, 85, 0.300, 0.395, 0.528, 0.923, 5.5, 0.375, 155, 0.315, 155),
            _batter_season(2023, 'LAD', 584, 179, 39, 107, 0.307, 0.408, 0.579, 0.987, 8.3, 0.405, 167, 0.312, 163),
        ],
        'prediction': {'predicted_value': 32000000, 'next_year_avg': 0.295, 'next_year_hr': 32, 'next_year_ops': 0.920,
                       'next_year_war': 5.5, 'next_year_woba': 0.380, 'next_year_wrc_plus': 150},
    },
    {
        'name': 'Gerrit Cole',
        'team': 'NYY',
        'position': 'P',
        'seasons': [
            _pitcher_season(2024, 'NYY', 0, 0, 0, 0, 0, None, None, None, None, None),
            _pitcher_season(2023, 'NYY', 209, 2.63, 222, 48, 0.98, 5.2, 2.90, 2.85, 9.56, 2.07),
            _pitcher_season(2022, 'NYY', 200.2, 3.50, 257, 50, 1.02, 4.5, 3.10, 2.95, 11.54, 2.25),
        ],
        'prediction': {'predicted_value': 35000000, 'next_year_era': 3.10, 'next_year_fip': 3.00},
    },
    {
        'name': 'Juan Soto',
        'team': 'NYY',
        'position': 'RF',
        'seasons': [
            _batter_season(2024, 'NYY', 550, 165, 35, 109, 0.300, 0.420, 0.550, 0.970, 6.0, 0.410, 170, 0.305, 168),
            _batter_season(2023, 'SDP', 568, 156, 35, 109, 0.275, 0.410, 0.519, 0.929, 5.5, 0.395, 155, 0.285, 154),
        ],
        'prediction': {'predicted_value': 40000000, 'next_year_avg': 0.295, 'next_year_hr': 38, 'next_year_ops': 0.980,
                       'next_year_war': 6.0, 'next_year_woba': 0.410, 'next_year_wrc_plus': 172},
    },
]


class Command(BaseCommand):
    help = 'Load sample MLB players for development/demo'

    def handle(self, *args, **options):
        MLBPlayer.objects.all().delete()

        created = []
        for data in SAMPLE_PLAYERS:
            seasons_data = data.pop('seasons')
            pred_data = data.pop('prediction')

            player = MLBPlayer.objects.create(**data)
            created.append(player)

            for s in seasons_data:
                MLBPlayerSeason.objects.create(player=player, **s)

            pred = MLBPlayerPrediction.objects.create(player=player, **pred_data)

        # Create similar player relationships (mock)
        if len(created) >= 3:
            MLBSimilarPlayer.objects.create(
                player=created[0],
                similar_player=created[1],
                similarity_score=Decimal('0.92'),
                rank=1,
            )
            MLBSimilarPlayer.objects.create(
                player=created[0],
                similar_player=created[2],
                similarity_score=Decimal('0.85'),
                rank=2,
            )

        self.stdout.write(self.style.SUCCESS(f'Loaded {len(created)} sample MLB players'))
