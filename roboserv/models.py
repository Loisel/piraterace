from django.db import models
from django.contrib.postgres.fields import ArrayField

import random

movements = {
    "u": "move one field forward",
    "l": "turn left",
    "r": "turn right",
    "t": "turn around",
    "b": "move one field back",
    "f": "move two fields forward",
    "s": "move three fields forward",
}

class Game(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    countdown_started = models.DateTimeField(null=True, blank=True)

    player_count = models.PositiveSmallIntegerField(default=8)
    player_names = ArrayField(models.CharField(max_length=20, blank=True))
    player_pos = ArrayField(
        ArrayField(models.PositiveSmallIntegerField(), size=2), null=True)
    player_moves = ArrayField(models.CharField(max_length=5, blank=True), null=True)
    player_choices = ArrayField(models.CharField(max_length=10, blank=True), null=True)

    arena = {
        "size": 12,
        "maxplayers": 8,
        "startpos": [(x, 0) for x in range(2, 10)]
    }

    def save(self, *args, **kwargs):
        if not self.pk:
            # random starting positions
            self.player_pos = random.sample(self.arena["startpos"], self.player_count)
            # deal cards
            self.player_choices = [
                "".join(random.choices(
                    list(movements.keys()), k=10)) for n in range(self.player_count)]
            # assign names
            for n in range(self.player_count):
                if self.player_names[n] == "":
                    self.player_names[n] = "player {}".format(n)
        super(Game, self).save(*args, **kwargs)

