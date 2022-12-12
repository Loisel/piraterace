from django.db import models
from enum import Enum
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
        repair=0,
        img="forward1-card.png",
        url=f"{CARDSURL}/forward1-card.png",
        tile_url=f"{CARDSURL}/forward1-tile.png",
    ),
    2: dict(
        descr="forward move 2",
        move=2,
        rot=0,
        repair=0,
        img="forward2-card.png",
        url=f"{CARDSURL}/forward2-card.png",
        tile_url=f"{CARDSURL}/forward2-tile.png",
    ),
    3: dict(
        descr="forward move 3",
        move=3,
        rot=0,
        repair=0,
        img="forward3-card.png",
        url=f"{CARDSURL}/forward3-card.png",
        tile_url=f"{CARDSURL}/forward3-tile.png",
    ),
    10: dict(
        descr="back move 1",
        move=-1,
        rot=0,
        repair=0,
        img="backward1-card.png",
        url=f"{CARDSURL}/backward1-card.png",
        tile_url=f"{CARDSURL}/backward1-tile.png",
    ),
    20: dict(
        descr="rotate left",
        move=0,
        rot=-1,
        repair=0,
        img="rotate-left-card.png",
        url=f"{CARDSURL}/rotate-left-card.png",
        tile_url=f"{CARDSURL}/rotate-left-tile.png",
    ),
    30: dict(
        descr="rotate right",
        move=0,
        rot=1,
        repair=0,
        img="rotate-right-card.png",
        url=f"{CARDSURL}/rotate-right-card.png",
        tile_url=f"{CARDSURL}/rotate-right-tile.png",
    ),
    40: dict(
        descr="rotate uturn",
        move=0,
        rot=2,
        repair=0,
        img="rotate-180-card.png",
        url=f"{CARDSURL}/rotate-180-card.png",
        tile_url=f"{CARDSURL}/rotate-180-tile.png",
    ),
    100: dict(
        descr="repair",
        move=0,
        rot=0,
        repair=1,
        img="repair-card.png",
        url=f"{CARDSURL}/repair-card.png",
    ),
}


class CANNON_DIRECTION:
    FORWARD = 0
    RIGHT = 1
    BACKWARD = 2
    LEFT = 3


CANNON_DIRECTION_CARDS = {
    -10: dict(descr="cannon_forward", direction=int(CANNON_DIRECTION.FORWARD)),
    -11: dict(descr="cannon_right", direction=int(CANNON_DIRECTION.RIGHT)),
    -12: dict(descr="cannon_backward", direction=int(CANNON_DIRECTION.BACKWARD)),
    -13: dict(descr="cannon_left", direction=int(CANNON_DIRECTION.LEFT)),
}

CANNON_DIRECTION_DESCR2ID = {val["descr"]: key for key, val in CANNON_DIRECTION_CARDS.items()}

CANNON_DIRECTION_DIRID2CARDID = {val["direction"]: key for key, val in CANNON_DIRECTION_CARDS.items()}


def gen_default_deck():
    c = []
    for rank in range(10, NRANKINGS - 1, 10):
        c.append(1 * NRANKINGS + rank)
        c.append(10 * NRANKINGS + rank)
        c.append(20 * NRANKINGS + rank)
        c.append(30 * NRANKINGS + rank)
        c.append(40 * NRANKINGS + rank)

    for rank in range(10, NRANKINGS // 2, 10):
        c.append(2 * NRANKINGS + rank)
    for rank in range(10, NRANKINGS // 4, 10):
        c.append(3 * NRANKINGS + rank)

    return c


def add_repair_cards(deck, percentage):
    print(f"old deck: {deck}")
    Nrepaircards = (percentage * 1e-2) * len(deck)
    for i in range(int(Nrepaircards + 0.5)):
        deck.append(100 * NRANKINGS)
    print(f"new deck: {deck}")
    return deck


def card_id_rank(cardval):
    return cardval // NRANKINGS, cardval % NRANKINGS


DEFAULT_DECK = gen_default_deck()

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
FREE_HEALTH_OFFSET = 3


class GameConfig(models.Model):
    gamename = models.CharField(max_length=200, blank=True)
    player_ids = ArrayField(models.IntegerField(), default=list)
    player_colors = ArrayField(models.CharField(max_length=7), default=list)
    player_names = ArrayField(models.CharField(max_length=200), default=list)
    player_teams = ArrayField(models.IntegerField(), default=list)
    player_ready = ArrayField(models.BooleanField(default=False), default=list)
    player_start_x = ArrayField(models.PositiveSmallIntegerField(), default=list)
    player_start_y = ArrayField(models.PositiveSmallIntegerField(), default=list)
    player_start_directions = ArrayField(models.PositiveSmallIntegerField(), default=list)
    player_next_card = ArrayField(models.IntegerField(), default=list)
    nmaxplayers = models.PositiveSmallIntegerField(default=1)
    mode = models.CharField(max_length=1, choices=GAME_MODES, default="c")
    # nplayers = models.PositiveSmallIntegerField(null=True, blank=True)
    # playerlist ist ein account set, oder?
    mapfile = models.CharField(max_length=256)
    damage_on_hit = models.PositiveSmallIntegerField(default=10)
    ncardslots = models.PositiveSmallIntegerField(default=5)
    ncardsavail = models.PositiveSmallIntegerField(default=7)
    path_highlighting = models.BooleanField(default=False)
    creator_userid = models.PositiveIntegerField()
    countdown_mode = models.CharField(max_length=1, choices=CHOICE_MODES, default="d")
    countdown = models.PositiveIntegerField(default=30)
    percentage_repaircards = models.PositiveSmallIntegerField(default=5)

    request_id = models.PositiveIntegerField(default=0)

    game = models.OneToOneField("BaseGame", related_name="config", null=True, blank=True, on_delete=models.CASCADE)

    @property
    def nplayers(self):
        return len(self.player_ids)

    def add_player(self, player):
        colors_to_pick = [c for c in COLORS.values() if c not in self.player_colors]
        if player.pk not in self.player_ids:
            self.player_ids.append(player.pk)
            self.player_names.append(player.user.username)
            self.player_colors.append(random.choice(colors_to_pick))  # TODO
            self.player_teams.append(-1)
            self.player_ready.append(False)
        return self.player_ids.index(player.pk)

    def del_player(self, player):
        if player.pk not in self.player_ids:
            raise ValueError(f"Player {player} not in game config")
            return False
        else:
            idx = self.player_ids.index(player.pk)
            self.player_ids.pop(idx)
            self.player_names.pop(idx)
            self.player_colors.pop(idx)
            self.player_teams.pop(idx)
            self.player_ready.pop(idx)
        return True

    def save(self, *args, **kwargs):
        self.request_id += 1
        super(GameConfig, self).save(*args, **kwargs)


class BaseGame(PolymorphicModel):

    mode = models.CharField(max_length=1, choices=GAME_MODES, default="c")
    # nplayers = models.PositiveSmallIntegerField(null=True, blank=True)
    # playerlist ist ein account set, oder?
    mapfile = models.CharField(max_length=256)
    round = models.PositiveIntegerField(default=1)

    time_started = models.DateTimeField(auto_now_add=True)
    timestamp = models.DateTimeField(blank=True, null=True)  # time when round finishes
    cards_played = ArrayField(models.IntegerField(null=True, blank=True), default=list)
    state = models.CharField(max_length=256, default="select")


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
