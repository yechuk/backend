from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mlb', '0005_mlbrosterentry'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mlbapistatline',
            name='mlbam_id',
            field=models.CharField(blank=True, db_index=True, max_length=32),
        ),
        migrations.AlterUniqueTogether(
            name='mlbapistatline',
            unique_together={('stat_view', 'season', 'mlbam_id')},
        ),
    ]
