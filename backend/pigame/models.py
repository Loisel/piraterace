from django.db import models
from polymorphic.models import PolymorphicModel
from django.contrib.postgres.fields import ArrayField

DIRID2NAME = {
    0: "up",
    1: "right",
    2: "down",
    3: "left"
}

DIRNAME2ID = {v: k for k,v in DIRID2NAME.items()}

DIRID2MOVE = {
    0: [0, 1],
    1: [1, 0],
    2: [0, -1],
    3: [-1, 0]
}

CARDS = {
        1: dict(
            descr = "forward move",
            move = 1,
            rot = 0,
            ),
        2: dict(
            descr = "forward move 2",
            move = 2,
            rot = 0,
            ),
        10: dict(
            descr = "back move 1",
            move = 1,
            rot = 0,
            ),
        20: dict(
            descr = "rotate left",
            move = 0,
            rot = -1,
            ),
        }

def gen_default_deck():
    c = [1,2,10,20]
    return c

DEFAULT_DECK = gen_default_deck()

maps = dict(
        default=dict(
            nx = 16,
            ny = 24,
            tilemap = "url",
            )
        )

class BaseGame(PolymorphicModel):
    GAME_MODES = [
        ("c", "Classic"),
    ]
    CHOICE_MODES = [
        ("d", "Default, count from first finished"),
        ("s", "Count from second to last finished"),
        ]

    mode = models.CharField(max_length=1, choices=GAME_MODES, default="c")
    # nplayers = models.PositiveSmallIntegerField(null=True, blank=True)
    # playerlist ist ein account set, oder?
    mapfile = models.CharField(max_length=256)
    nlives = models.PositiveSmallIntegerField(default=3)
    damage_on_hit = models.PositiveSmallIntegerField(default=10)
    npause_on_repair = models.PositiveSmallIntegerField(default=1)
    npause_on_destroy = models.PositiveSmallIntegerField(default=1)
    ncardslots = models.PositiveSmallIntegerField(default=2)
    ncardsavail = models.PositiveSmallIntegerField(default=3)
    allow_transfer = models.BooleanField(default=False)
    creator_userid = models.PositiveIntegerField()
    countdown_mode = models.CharField(max_length=1, choices=CHOICE_MODES, default="d")
    countdown = models.PositiveIntegerField(default=30)
    round_time = models.PositiveIntegerField(default=5)
    time_started = models.DateTimeField(auto_now_add=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    cards_played = ArrayField(models.IntegerField(null=True, blank=True), default=[])
    # chat =

class ClassicGame(BaseGame):
    pass

class TeamsGame(BaseGame):
    fog_of_war = models.BooleanField(default=False)
    pass

#class GameRound(models.Model):
#    game = models.ForeignKey(BaseGame, on_delete=models.CASCADE)
#    time_started = models.DateTimeField(auto_now_add=True)
#    #rmap = models.OneToOneField(
#    #    Map,
#    #    on_delete=models.CASCADE,
#    #    primary_key=True,)

#class Map(models.Model):
#    nx = models.PositiveSmallIntegerField()
#    ny = models.PositiveSmallIntegerField()
#    #start_locations = models.CharField() # with integer validator
