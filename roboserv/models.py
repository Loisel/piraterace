from django.db import models
from django.contrib.postgres.fields import ArrayField

class Game(models.Model):
    created = models.DateTimeField(auto_now_add=True)

    player_count = models.PositiveSmallIntegerField(default=8)
    player_names = ArrayField(models.CharField(max_length=20, blank=True))
    player_pos = ArrayField(
        ArrayField(models.PositiveSmallIntegerField(), size=2))
    player_moves = ArrayField(models.CharField(max_length=5, blank=True))

