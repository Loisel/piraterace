from django.urls import path

from pigame import views

app_name = "pigame"

urlpatterns = [
    path("player_cards", views.player_cards, name="player_cards"),
    path("game/<int:game_id>", views.game, name="game"),
    path("leave_game", views.leave_game, name="leave_game"),
    path("create_game/<int:gamemaker_id>", views.create_game),
    path("update_gm_player_info/<int:gamemaker_id>", views.update_gm_player_info),
    path("create_new_gamemaker", views.create_new_gamemaker),
    path("create_gamemaker", views.create_gamemaker),
    path("join_gamemaker/<int:gamemaker_id>", views.join_gamemaker),
    path("view_gamemaker/<int:gamemaker_id>", views.view_gamemaker, name="view_gamemaker"),
    path("list_gamemakers", views.list_gamemakers),
    path("submit_cards", views.submit_cards),
]
