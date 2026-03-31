from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlb', '0005_mlbrosterentry'),
    ]

    operations = [
        migrations.CreateModel(
            name='MLBRosterPhoto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('team_name', models.CharField(db_index=True, max_length=100)),
                ('player_name', models.CharField(max_length=100)),
                ('normalized_player_name', models.CharField(db_index=True, max_length=120)),
                ('original_filename', models.CharField(max_length=255)),
                ('content_type', models.CharField(max_length=100)),
                ('image_data', models.BinaryField()),
                ('byte_size', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'MLB Roster Photo',
                'verbose_name_plural': 'MLB Roster Photos',
                'ordering': ['team_name', 'player_name'],
                'unique_together': {('team_name', 'normalized_player_name')},
            },
        ),
    ]
