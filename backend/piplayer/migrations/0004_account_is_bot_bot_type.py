from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("piplayer", "0003_remove_account_deck_remove_account_gameconfig_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="account",
            name="is_bot",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="account",
            name="bot_type",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
    ]
