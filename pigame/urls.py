from django.urls import path

from pigame import views

app_name = 'pigame'

urlpatterns = [
        path('game/<int:game_id>', views.game, name='game'),
        path('create_debug_game', views.create_debug_game),
        ]
