from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('<int:game_id>/player/<int:player_id>', views.playercards, name='playercards'),
    path('<int:game_id>/deal', views.deal, name='deal'),
]