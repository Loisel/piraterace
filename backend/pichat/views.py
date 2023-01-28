from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import redirect
from django.urls import reverse
from django.core.cache import cache


GLOBAL_CHATSLUG = "global_chat"
CHAT_SIZELIMIT = 1000


def chatslug(game):
    return f"game_{game.pk}"


def get_chat(chat_slug):
    return cache.get(chat_slug)


def add_message(chat_slug, user, message):
    chat = get_chat(chat_slug)
    if not chat:
        chat = []
    chat.insert(0, {"pk": user.pk, "name": user.username, "message": message})

    chat = chat[:CHAT_SIZELIMIT]
    cache.set(chat_slug, chat)
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
    # add_message(GLOBAL_CHATSLUG, request.user, f"{datetime.datetime.now()}")
    return JsonResponse({"prefix": "global", "chatslug": GLOBAL_CHATSLUG, "chat": get_chat(GLOBAL_CHATSLUG)})


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
    add_message(chatslug(game), user, message)

    return redirect(reverse("pichat:get_gamechat"))


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
def post_globalchat(request, **kwargs):
    user = request.user
    message = request.data.get("message")

    if not message or len(message.strip()) == 0:
        return JsonResponse(f"Unable to send chat message. Message is empty.", status=404, safe=False)
    add_message(GLOBAL_CHATSLUG, user, message)

    return redirect(reverse("pichat:get_globalchat"))
