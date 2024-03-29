from django.db import models
from django.contrib.auth.models import User, Group
from django.contrib.postgres.fields import ArrayField
from django.db.models.signals import post_save
from django.dispatch import receiver

from pigame.models import BaseGame, GameConfig, gen_default_deck


class Account(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, primary_key=True)
    game = models.ForeignKey(BaseGame, on_delete=models.SET_NULL, null=True, blank=True)

    time_submitted = models.DateTimeField(blank=True, null=True)

    @property
    def deck(self):
        return gen_default_deck()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Account.objects.create(user=instance)
