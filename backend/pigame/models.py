from django.db import models
from polymorphic.models import PolymorphicModel
from django.contrib.postgres.fields import ArrayField
import matplotlib.colors as mcolors
import random

from piraterace.settings import CARDSURL

DIRID2NAME = {0: "up", 1: "right", 2: "down", 3: "left"}

DIRNAME2ID = {v: k for k, v in DIRID2NAME.items()}

DIRID2MOVE = {0: [0, -1], 1: [1, 0], 2: [0, 1], 3: [-1, 0]}

NRANKINGS = 100

CARDS = {
    1: dict(
        descr="forward move",
        move=1,
        rot=0,
        img="move_forward_1.jpg",
        url=f"{CARDSURL}/move_forward_1.jpg",
    ),
    2: dict(
        descr="forward move 2",
        move=2,
        rot=0,
        img="move_forward_2.jpg",
        url=f"{CARDSURL}/move_forward_2.jpg",
    ),
    10: dict(
        descr="back move 1",
        move=-1,
        rot=0,
        img="move_back_1.jpg",
        url=f"{CARDSURL}/move_back_1.jpg",
    ),
    20: dict(
        descr="rotate left",
        move=0,
        rot=-1,
        img="rot_left.jpg",
        url=f"{CARDSURL}/rot_left.jpg",
    ),
}


def gen_default_deck():
    c = []
    for rank in range(10, NRANKINGS - 1, 10):
        c.append(1 * NRANKINGS + rank)
        c.append(2 * NRANKINGS + rank)
        c.append(10 * NRANKINGS + rank)
        c.append(20 * NRANKINGS + rank)
    return c


def card_id_rank(cardval):
    return cardval // NRANKINGS, cardval % NRANKINGS


DEFAULT_DECK = gen_default_deck()
print(f"DEFAULT_DECK: {DEFAULT_DECK}")

maps = dict(
    default=dict(
        nx=16,
        ny=24,
        tilemap="url",
    )
)
GAME_MODES = [
    ("c", "Classic"),
]
CHOICE_MODES = [
    ("d", "Default, count from first finished"),
    ("s", "Count from second to last finished"),
]

COLORS = mcolors.TABLEAU_COLORS


class GameMaker(models.Model):
    player_ids = ArrayField(models.IntegerField(), default=list)
    player_colors = ArrayField(models.CharField(max_length=7), default=list)
    player_teams = ArrayField(models.IntegerField(), default=list)
    player_ready = ArrayField(models.BooleanField(default=False), default=list)
    nmaxplayers = models.PositiveSmallIntegerField(default=1)
    mode = models.CharField(max_length=1, choices=GAME_MODES, default="c")
    # nplayers = models.PositiveSmallIntegerField(null=True, blank=True)
    # playerlist ist ein account set, oder?
    mapfile = models.CharField(max_length=256)
    nlives = models.PositiveSmallIntegerField(default=3)
    damage_on_hit = models.PositiveSmallIntegerField(default=10)
    npause_on_repair = models.PositiveSmallIntegerField(default=1)
    npause_on_destroy = models.PositiveSmallIntegerField(default=1)
    ncardslots = models.PositiveSmallIntegerField(default=5)
    ncardsavail = models.PositiveSmallIntegerField(default=7)
    allow_transfer = models.BooleanField(default=False)
    creator_userid = models.PositiveIntegerField()
    countdown_mode = models.CharField(max_length=1, choices=CHOICE_MODES, default="d")
    countdown = models.PositiveIntegerField(default=30)

    game = models.OneToOneField("BaseGame", null=True, blank=True, on_delete=models.CASCADE)

    @property
    def nplayers(self):
        return len(self.player_ids)

    def add_player(self, player):
        colors_to_pick = [c for c in COLORS.values() if c not in self.player_colors]
        if player.pk not in self.player_ids:
            self.player_ids.append(player.pk)
            self.player_colors.append(random.choice(colors_to_pick))  # TODO
            self.player_teams.append(-1)
            self.player_ready.append(False)
        return self.player_ids.index(player.pk)


class BaseGame(PolymorphicModel):

    mode = models.CharField(max_length=1, choices=GAME_MODES, default="c")
    # nplayers = models.PositiveSmallIntegerField(null=True, blank=True)
    # playerlist ist ein account set, oder?
    mapfile = models.CharField(max_length=256)
    round = models.PositiveIntegerField(default=1)
    nlives = models.PositiveSmallIntegerField(default=3)
    damage_on_hit = models.PositiveSmallIntegerField(default=10)
    npause_on_repair = models.PositiveSmallIntegerField(default=1)
    npause_on_destroy = models.PositiveSmallIntegerField(default=1)
    ncardslots = models.PositiveSmallIntegerField(default=2)
    ncardsavail = models.PositiveSmallIntegerField(default=3)
    allow_transfer = models.BooleanField(default=False)

    countdown_mode = models.CharField(max_length=1, choices=CHOICE_MODES, default="d")
    countdown = models.PositiveIntegerField(default=30)
    time_started = models.DateTimeField(auto_now_add=True)
    timestamp = models.DateTimeField(blank=True, null=True)  # time when round finishes
    cards_played = ArrayField(models.IntegerField(null=True, blank=True), default=list)
    # chat =


class ClassicGame(BaseGame):
    pass


class TeamsGame(BaseGame):
    fog_of_war = models.BooleanField(default=False)
    pass


# class GameRound(models.Model):
#    game = models.ForeignKey(BaseGame, on_delete=models.CASCADE)
#    time_started = models.DateTimeField(auto_now_add=True)
#    #rmap = models.OneToOneField(
#    #    Map,
#    #    on_delete=models.CASCADE,
#    #    primary_key=True,)

# class Map(models.Model):
#    nx = models.PositiveSmallIntegerField()
#    ny = models.PositiveSmallIntegerField()
#    #start_locations = models.CharField() # with integer validator
