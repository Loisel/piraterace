from django.db import models

from piplayer.models import Player, Account

class GameConfig(models.Model):
    GAME_MODES = (
        ("c", "Classic")
    )
    CHOICE_MODES = (
        ("d", "Default, count from first finished"),
        ("s", "Count from second to last finished")
    )
    mode = models.CharField(max_length=1, choices=GAME_MODES, default="c")
    nplayers = models.PositiveSmallIntegerField(null=True, blank=True)
    # playerlist ist ein account set, oder?
    selected_map_id = models.PositiveIntegerField(null=True, blank=True)
    fog_of_war = models.BooleanField(default=False)
    nlives = models.PositiveSmallIntegerField(default=3)
    damage_on_hit = models.PositiveSmallIntegerField(default=10)
    npause_on_repair = models.PositiveSmallIntegerField(default=1)
    npause_on_destroy = models.PositiveSmallIntegerField(default=1)
    ncardslots = models.PositiveSmallIntegerField(default=5)
    allow_transfer = models.BooleanField(default=False)
    creator = models.OneToOneField(
        Account,
        on_delete=models.CASCADE)
    countdown_mode = models.CharField(max_length=1, choices=CHOICE_MODES, default="d")
    countdown = models.PositiveIntegerField(null=True, blank=True)
    round_time = models.PositiveIntegerField(null=True, blank=True)
    # chat =

class BaseGame(models.Model):
    config = models.OneToOneField(
        GameConfig,
        on_delete=models.CASCADE,
        primary_key=True,
    )

    class Meta:
        abstract = True


class ClassicGame(BaseGame):
    pass

class GameRound(models.Model):
    game = models.ForeignKey(BaseGame, on_delete=models.CASCADE)
    time_started = models.DateTimeField(auto_now_add=True)
    rmap = models.OneToOneField(
        "Map",
        on_delete=models.CASCADE,
        primary_key=True,)

class Map(models.Model):
    nx = models.PositiveSmallIntegerField()
    ny = models.PositiveSmallIntegerField()
    start_locations = models.CharField() # with integer validator
    features = models.CharField() # integer array?
