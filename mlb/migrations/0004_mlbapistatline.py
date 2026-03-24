from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlb', '0003_valuationsettings'),
    ]

    operations = [
        migrations.CreateModel(
            name='MLBApiStatLine',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stat_view', models.CharField(choices=[('batting', 'Batting'), ('pitching', 'Pitching')], db_index=True, max_length=20)),
                ('season', models.PositiveIntegerField(db_index=True)),
                ('team', models.CharField(db_index=True, max_length=10)),
                ('player_name', models.CharField(max_length=100)),
                ('name_ascii', models.CharField(blank=True, max_length=100)),
                ('external_player_id', models.CharField(db_index=True, max_length=32)),
                ('mlbam_id', models.CharField(blank=True, max_length=32)),
                ('age', models.PositiveIntegerField(blank=True, null=True)),
                ('war', models.FloatField(blank=True, null=True)),
                ('raw_stats', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'MLB API Stat Line',
                'verbose_name_plural': 'MLB API Stat Lines',
                'ordering': ['stat_view', '-season', 'team', 'player_name'],
                'unique_together': {('stat_view', 'season', 'team', 'external_player_id')},
            },
        ),
    ]
