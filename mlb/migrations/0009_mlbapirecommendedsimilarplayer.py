from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlb', '0008_mlbapisimilarplayer'),
    ]

    operations = [
        migrations.CreateModel(
            name='MLBApiRecommendedSimilarPlayer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stat_view', models.CharField(choices=[('batting', 'Batting'), ('pitching', 'Pitching')], db_index=True, max_length=20)),
                ('source_player_name', models.CharField(max_length=100)),
                ('source_name_ascii', models.CharField(blank=True, db_index=True, max_length=100)),
                ('source_mlbam_id', models.CharField(blank=True, db_index=True, max_length=32)),
                ('source_external_player_id', models.CharField(blank=True, db_index=True, max_length=32)),
                ('source_player_position', models.CharField(blank=True, max_length=10)),
                ('source_player_age', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('similar_player_name', models.CharField(max_length=100)),
                ('similar_name_ascii', models.CharField(blank=True, db_index=True, max_length=100)),
                ('similar_mlbam_id', models.CharField(blank=True, db_index=True, max_length=32)),
                ('similar_external_player_id', models.CharField(blank=True, db_index=True, max_length=32)),
                ('similar_team', models.CharField(blank=True, max_length=10)),
                ('similar_player_position', models.CharField(blank=True, max_length=10)),
                ('similar_player_age', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('similarity_score', models.DecimalField(decimal_places=9, default=Decimal('0'), max_digits=12)),
                ('rank', models.PositiveSmallIntegerField(default=1)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'MLB API Recommended Similar Player',
                'verbose_name_plural': 'MLB API Recommended Similar Players',
                'ordering': ['stat_view', 'source_player_name', 'rank'],
                'unique_together': {('stat_view', 'source_name_ascii', 'rank')},
            },
        ),
    ]
