from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import redirect
from django.urls import reverse
from django.core.cache import cache
import datetime

GLOBAL_CHATSLUG = "global_chat"
ACTIVE_USERSLUG = "active_users"
LAST_CHECKEDSLUG = "last_checked"
CHAT_SIZELIMIT = 1000
TIMEDELTA_MESSAGE_DELETE = datetime.timedelta(seconds=3600)
TIMEDELTA_USER_ACTIVE = datetime.timedelta(seconds=30)


def chatslug(game):
    return f"game_{game.pk}"


def get_chat(chat_slug):
    return cache.get(chat_slug)


def add_message(chat_slug, user, message, lifetime):
    chat = get_chat(chat_slug)
    if not chat:
        chat = []
    if len(chat) and chat[0]["pk"] == user.pk and chat[0]["message"] == message:
        return chat
    chat.insert(0, {"pk": user.pk, "name": user.username, "message": message, "timestamp": datetime.datetime.now()})

    chat = chat[:CHAT_SIZELIMIT]
    cache.set(chat_slug, chat, lifetime)
    return chat


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def get_gamechat(request, **kwargs):
    player = request.user.account
    game = player.game
    if not game:
        return JsonResponse(f"Unable to retrieve chat messages. You are not in a game.", status=404, safe=False)
    return JsonResponse({"prefix": "game", "chatslug": chatslug(game), "chat": get_chat(chatslug(game))})


@api_view(["GET"])
def get_globalchat(request, **kwargs):
    users = cache.get(ACTIVE_USERSLUG, {})
    users[request.user.username] = datetime.datetime.now()

    last_checked = cache.get(LAST_CHECKEDSLUG, datetime.datetime.now())
    if datetime.datetime.now() - last_checked > TIMEDELTA_USER_ACTIVE:
        users = {uname: t for uname, t in users.items() if datetime.datetime.now() - t < TIMEDELTA_USER_ACTIVE}
        cache.set(LAST_CHECKEDSLUG, datetime.datetime.now())
    cache.set(ACTIVE_USERSLUG, users)
    active_users = list(users)

    chat = get_chat(GLOBAL_CHATSLUG)
    if chat:
        for i in range(len(chat) - 1, 0, -1):
            td = datetime.datetime.now() - chat[i]["timestamp"]
            if td > TIMEDELTA_MESSAGE_DELETE:
                chat.pop()
            else:
                cache.set(GLOBAL_CHATSLUG, chat, None)
                break
    return JsonResponse({"prefix": "global", "chatslug": GLOBAL_CHATSLUG, "chat": chat, "active_users": active_users})


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
def post_gamechat(request, **kwargs):
    user = request.user
    game = user.account.game
    if not game:
        return JsonResponse(f"Unable to send chat message. You are not in a game.", status=404, safe=False)
    message = request.data.get("message")
    if not message or len(message.strip()) == 0:
        return JsonResponse(f"Unable to send chat message. Message is empty.", status=404, safe=False)
    add_message(chatslug(game), user, message, 3600)

    return redirect(reverse("pichat:get_gamechat"))


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
def post_globalchat(request, **kwargs):
    user = request.user
    message = request.data.get("message")

    if not message or len(message.strip()) == 0:
        return JsonResponse(f"Unable to send chat message. Message is empty.", status=404, safe=False)
    add_message(GLOBAL_CHATSLUG, user, message, None)

    return redirect(reverse("pichat:get_globalchat"))
