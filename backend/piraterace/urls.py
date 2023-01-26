"""piraterace URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import re_path, path, include

urlpatterns = [
    path("api/admin/", admin.site.urls),
    path("api/pigame/", include("pigame.urls")),
    path("api/piplayer/", include("piplayer.urls")),
    path("api/pichat/", include("pichat.urls")),
    path("api/auth/", include("djoser.urls")),
    path("api/auth/", include("djoser.urls.jwt")),
]


# if in debug mode, redirect static requests to media_ROOT
from django.conf import settings
from django.views import static

if settings.DEBUG == True:
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            static.serve,
            {
                "document_root": settings.MEDIA_ROOT,
            },
        ),
        re_path(
            r"^static/(?P<path>.*)$",
            static.serve,
            {
                "document_root": settings.STATIC_ROOT,
            },
        ),
    ]
