from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pigame", "0003_add_treasure_preview"),
    ]

    operations = [
        migrations.AddField(
            model_name="gameconfig",
            name="treasures_per_round",
            field=models.FloatField(default=2.0),
        ),
    ]
