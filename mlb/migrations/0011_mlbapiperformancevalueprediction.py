from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlb', '0010_mlbapiaavprediction'),
    ]

    operations = [
        migrations.CreateModel(
            name='MLBApiPerformanceValuePrediction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stat_view', models.CharField(choices=[('batting', 'Batting'), ('pitching', 'Pitching')], db_index=True, max_length=20)),
                ('season', models.PositiveIntegerField(db_index=True)),
                ('source_label', models.CharField(default='M2', max_length=32)),
                ('source_file', models.CharField(blank=True, max_length=255)),
                ('player_name', models.CharField(max_length=100)),
                ('name_ascii', models.CharField(blank=True, db_index=True, max_length=100)),
                ('player_type', models.CharField(blank=True, max_length=20)),
                ('current_team', models.CharField(blank=True, max_length=10)),
                ('target_team', models.CharField(db_index=True, max_length=10)),
                ('war_2022', models.DecimalField(blank=True, decimal_places=3, max_digits=8, null=True)),
                ('predicted_war_avg', models.DecimalField(blank=True, decimal_places=3, max_digits=8, null=True)),
                ('actual_war_avg', models.DecimalField(blank=True, decimal_places=3, max_digits=8, null=True)),
                ('dollars_per_war_millions', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('predicted_value_millions', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'MLB API Performance Value Prediction',
                'verbose_name_plural': 'MLB API Performance Value Predictions',
                'ordering': ['-season', 'player_name', 'target_team'],
                'unique_together': {('season', 'stat_view', 'name_ascii', 'target_team')},
            },
        ),
    ]
