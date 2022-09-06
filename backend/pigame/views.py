from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.forms.models import model_to_dict
from django.shortcuts import redirect
from django.urls import reverse
from django.core import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

import os
import glob
from piraterace.settings import MAPSDIR

from pigame.models import BaseGame, ClassicGame, DEFAULT_DECK, GameMaker, CARDS, COLORS
from piplayer.models import Account
import datetime
import pytz
from pigame.game_logic import (
    determine_next_cards_played,
    determine_starting_locations,
    determine_checkpoint_locations,
    get_cards_on_hand,
    load_inital_map,
    play_stack,
    switch_cards_on_hand,
    verify_map,
)


@api_view(["GET", "POST"])
@permission_classes((IsAuthenticated,))
def player_cards(request, **kwargs):
    player = request.user.account

    if request.method == "POST":
        src, target = request.data
        switch_cards_on_hand(player, src, target)

    cards = []
    for card in get_cards_on_hand(player, player.game.ncardsavail)[1::2]:
        cards.append([card, CARDS[card]])

    return JsonResponse(cards, safe=False)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def game(request, game_id, **kwargs):
    game = get_object_or_404(BaseGame, pk=game_id)
    player = request.user.account

    players = game.account_set.all()
    initmap = load_inital_map(game.mapfile)
    checkpoints = determine_checkpoint_locations(initmap)

    payload = dict(
        text="hallo",
        game_id=game_id,
        time_started=game.time_started,
        cards_played=game.cards_played,
        map=initmap,
        mapfile=game.mapfile,
        checkpoints=checkpoints,
    )

    if datetime.datetime.now(pytz.utc) > game.timestamp + datetime.timedelta(seconds=game.round_time):
        cards_played = game.cards_played
        cards_on_hand = determine_next_cards_played(players, game.ncardsavail)
        cards_played.extend(cards_on_hand[: game.ncardslots * 2])  # times 2 because it is a playerid, card tuple
        game.cards_played = cards_played
        game.timestamp = datetime.datetime.now()
        game.round += 1
        game.save()

        for p in players:  # increment next card pointer
            p.next_card += game.ncardsavail
            p.save()

        payload["new_round"] = True

    players, actionstack = play_stack(game)

    payload["actionstack"] = actionstack
    payload["Ngameround"] = game.round
    payload["players"] = {}
    for p in players.values():
        payload["players"][p.pk] = dict(
            start_pos_x=p.start_loc_x,
            start_pos_y=p.start_loc_y,
            start_direction=p.start_direction,
            pos_x=p.xpos,
            pos_y=p.ypos,
            direction=p.direction,
        )

    return JsonResponse(payload)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def create_game(request, gamemaker_id, **kwargs):
    maker = get_object_or_404(GameMaker, pk=gamemaker_id)
    if request.user.account.pk != maker.creator_userid:
        return JsonResponse(f"Only the user who opened the game may start it", status=404, safe=False)

    if not all(maker.player_ready):
        return JsonResponse(f"Player not ready", status=404, safe=False)

    players = Account.objects.filter(pk__in=maker.player_ids)
    game = ClassicGame(
        mapfile=maker.mapfile,
        mode=maker.mode,
        nlives=maker.nlives,
        damage_on_hit=maker.damage_on_hit,
        npause_on_repair=maker.npause_on_repair,
        npause_on_destroy=maker.npause_on_destroy,
        ncardslots=maker.ncardslots,
        ncardsavail=maker.ncardsavail,
        allow_transfer=maker.allow_transfer,
        countdown_mode=maker.countdown_mode,
        countdown=maker.countdown,
        round_time=maker.round_time,
    )
    game.save()

    maker.game = game
    maker.save()
    initmap = load_inital_map(game.mapfile)
    players = determine_starting_locations(initmap, players)

    for p in players:
        p.game = game
        p.deck = DEFAULT_DECK
        p.next_card = 0
        p.lives = game.nlives
        p.damage = 0
        p.save()

    payload = dict(
        text="game created",
        game_id=game.pk,
        time_started=game.time_started,
        url=f"http://localhost:8000/pigame/game/{game.pk}",
    )
    return JsonResponse(payload)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def view_gamemaker(request, gamemaker_id):
    caller = request.user.account
    gm = model_to_dict(get_object_or_404(GameMaker, pk=gamemaker_id))
    players = Account.objects.filter(id__in=gm["player_ids"])
    gm["player_names"] = [p.user.username for p in players]

    ## colors_to_pick = [c for c in COLORS.keys() if c not in gm["player_colors"]]
    ## the callers color can also be chosen
    ## colors_to_pick.append(gm["player_colors"][gm["player_ids"].index(caller.pk)])
    gm["player_color_choices"] = COLORS
    gm["caller_idx"] = gm["player_ids"].index(caller.pk)

    return JsonResponse(gm)


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
def update_gm_player_info(request, gamemaker_id):
    caller = request.user.account
    gm = get_object_or_404(GameMaker, pk=gamemaker_id)

    data = request.data
    idx = gm.player_ids.index(caller.pk)

    gm.player_colors[idx] = data["color"]
    gm.player_teams[idx] = data["team"]
    gm.player_ready[idx] = data["ready"]
    gm.save()

    return redirect(reverse("pigame:view_gamemaker", kwargs={"gamemaker_id": gm.pk}))


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def join_gamemaker(request, gamemaker_id, **kwargs):
    maker = get_object_or_404(GameMaker, pk=gamemaker_id)
    player = request.user.account
    maker.add_player(player)
    maker.save()
    return redirect(reverse("pigame:view_gamemaker", kwargs={"gamemaker_id": maker.pk}))


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
def create_gamemaker(request, **kwargs):
    player = request.user.account

    data = request.data

    mapfile = data["selected_map"]

    initmap = load_inital_map(mapfile)
    errs = verify_map(initmap)
    if errs:
        return JsonResponse(errs, status=404, safe=False)

    maker = GameMaker(creator_userid=player.pk, mapfile=mapfile, player_ids=[])
    maker.add_player(player)
    maker.save()

    payload = model_to_dict(maker)
    return redirect(reverse("pigame:view_gamemaker", kwargs={"gamemaker_id": maker.pk}))


@api_view(["GET", "POST"])
@permission_classes((IsAuthenticated,))
def create_new_gamemaker(request, **kwargs):

    available_maps = [os.path.basename(f) for f in glob.glob(os.path.join(MAPSDIR, "*.json"))]

    ret = dict(
        available_maps=available_maps,
        selected_map=None,
        map_info=None,
        Nmaxplayers=None,
    )

    if request.method == "POST":
        ret.update(**request.data)

    if ret["selected_map"]:
        ret["map_info"] = load_inital_map(ret["selected_map"])
        startinglocslayer = list(filter(lambda l: l["name"] == "startinglocs", ret["map_info"]["layers"]))[0]
        ret["Nmaxplayers"] = len(startinglocslayer["objects"])
        ret["startinglocs"] = startinglocslayer

    return JsonResponse(ret)


def list_gamemakers(request):
    makers = GameMaker.objects.filter(game=None)
    return JsonResponse(list(makers.values()), safe=False)
