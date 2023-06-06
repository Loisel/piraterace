from django.urls import path

from pichat import views

app_name = "pichat"

urlpatterns = [
    path("get_chat/global", views.get_globalchat, name="get_globalchat"),
    path("get_chat/game", views.get_gamechat, name="get_gamechat"),
    path("get_chat/game_config/<int:gameconfig_id>", views.get_gameconfigchat, name="get_gameconfigchat"),
    path("post_chat/global", views.post_globalchat, name="post_globalchat"),
    path("post_chat/game", views.post_gamechat, name="post_gamechat"),
    path("post_chat/game_config/<int:gameconfig_id>", views.post_gameconfigchat, name="post_gameconfigchat"),
]
