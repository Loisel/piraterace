from django.urls import path

from pigame import views

app_name = "pigame"

urlpatterns = [
    path("player_cards", views.player_cards, name="player_cards"),
    path("game/<int:game_id>", views.game, name="game"),
    path("leave_game", views.leave_game, name="leave_game"),
    path("create_game/<int:gameconfig_id>", views.create_game),
    path("update_gamecfg_player_info/<int:gameconfig_id>/<int:request_id>", views.update_gamecfg_player_info),
    path("update_gamecfg_options/<int:gameconfig_id>/<int:request_id>", views.update_gamecfg_options),
    path("create_new_gameconfig", views.create_new_gameconfig),
    path("create_gameconfig", views.create_gameconfig),
    path("join_gameconfig/<int:gameconfig_id>", views.join_gameconfig),
    path("leave_gameconfig", views.leave_gameconfig),
    path("view_gameconfig/<int:gameconfig_id>", views.view_gameconfig, name="view_gameconfig"),
    path("list_gameconfigs", views.list_gameconfigs),
    path("submit_cards", views.submit_cards),
    path("power_down", views.power_down),
    path("cannon_direction", views.player_cannon_direction),
    path("mapinfo/<str:mapfile>", views.get_mapinfo),
]
