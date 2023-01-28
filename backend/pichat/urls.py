from django.urls import path

from pichat import views

app_name = "pichat"

urlpatterns = [
    path("get_gamechat", views.get_gamechat, name="get_gamechat"),
    path("post_gamechat", views.post_gamechat, name="post_gamechat"),
    path("get_globalchat", views.get_globalchat, name="get_globalchat"),
    path("post_globalchat", views.post_globalchat, name="post_globalchat"),
]
