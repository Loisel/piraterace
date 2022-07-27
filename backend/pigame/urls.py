from django.urls import path

from pigame import views

app_name = 'pigame'

urlpatterns = [
    path('game/<int:game_id>', views.game, name='game'),
    path('create_debug_game', views.create_debug_game),
    path('create_game/<int:gamemaker_id>', views.create_game),
    path('create_gamemaker', views.create_gamemaker),
    path('join_gamemaker/<int:gamemaker_id>', views.join_gamemaker),
    path('view_gamemaker/<int:gamemaker_id>', views.view_gamemaker, name="view_gamemaker"),
    path('list_gamemakers', views.list_gamemakers),
]
