from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlb', '0009_mlbapirecommendedsimilarplayer'),
    ]

    operations = [
        migrations.CreateModel(
            name='MLBApiAavPrediction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stat_view', models.CharField(choices=[('batting', 'Batting'), ('pitching', 'Pitching')], db_index=True, max_length=20)),
                ('season', models.PositiveIntegerField(db_index=True)),
                ('source_label', models.CharField(default='M1', max_length=32)),
                ('source_file', models.CharField(blank=True, max_length=255)),
                ('player_name', models.CharField(max_length=100)),
                ('name_ascii', models.CharField(blank=True, db_index=True, max_length=100)),
                ('team_code_raw', models.CharField(blank=True, max_length=10)),
                ('position_raw', models.CharField(blank=True, max_length=20)),
                ('actual_aav_millions', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('predicted_aav_millions', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('prediction_error_millions', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'MLB API AAV Prediction',
                'verbose_name_plural': 'MLB API AAV Predictions',
                'ordering': ['-season', 'player_name'],
                'unique_together': {('season', 'stat_view', 'name_ascii')},
            },
        ),
    ]
