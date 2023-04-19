from django.urls import path

from piplayer import views

app_name = "piplayer"

urlpatterns = [
    path("userDetail", views.userDetail, name="userDetail"),
    path("randomName", views.randomName, name="randomName"),
]
