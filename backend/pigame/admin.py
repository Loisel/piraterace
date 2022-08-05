from django.contrib import admin
from pigame.models import BaseGame, GameMaker

# Register your models to admin site, then you can add, edit, delete and search your models in Django admin site.
admin.site.register(BaseGame)
admin.site.register(GameMaker)
