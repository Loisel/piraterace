from django.db import models
from django.contrib.auth.models import User, Group

from pigame.models import BaseGame, GameConfig

class Account(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    game_lobby = models.ForeignKey(GameConfig)

class Player(models.Model):
    account = models.OneToOneField(Account, on_delete=models.CASCADE)
    loc_x = models.PositiveSmallIntegerField(null=True, blank=True)
    loc_y = models.PositiveSmallIntegerField(null=True, blank=True)
    direction = models.PositiveIntegerField(null=True, blank=True)
    game = models.OneToOneField(BaseGame, on_delete=models.CASCADE)
    nslots = models.PositiveSmallIntegerField(default=5)
    cards = models.CharField()
    deck = models.CharField()

    next_card = models.PositiveSmallIntegerField(default=0)
    lives = models.PositiveSmallIntegerField(default=3)
    damage = models.PositiveSmallIntegerField(default=0)

    # avatar =
    time_submitted = models.DateTimeField(blank=True, null=True)
