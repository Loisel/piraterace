from django.db import models
from django.contrib.auth.models import User, Group
from django.contrib.postgres.fields import ArrayField
from django.db.models.signals import post_save
from django.dispatch import receiver

from pigame.models import BaseGame

class Account(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    start_loc_x = models.PositiveSmallIntegerField(null=True, blank=True)
    start_loc_y = models.PositiveSmallIntegerField(null=True, blank=True)
    start_direction = models.PositiveIntegerField(null=True, blank=True)
    #game_lobby = models.ForeignKey(GameConfig, on_delete=models.CASCADE)
    game = models.ForeignKey(BaseGame, on_delete=models.CASCADE, null=True, blank=True)
    deck = ArrayField(models.IntegerField(null=True, blank=True), null=True, blank=True)

    next_card = models.PositiveSmallIntegerField(default=0)
    lives = models.PositiveSmallIntegerField(default=3)
    damage = models.PositiveSmallIntegerField(default=0)

    # avatar =
    time_submitted = models.DateTimeField(blank=True, null=True)

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Account.objects.create(user=instance)
