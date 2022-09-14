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
import random
from piraterace.settings import MAPSDIR

from pigame.models import BaseGame, ClassicGame, DEFAULT_DECK, GameConfig, CARDS, COLORS, card_id_rank
from piplayer.models import Account
import datetime
import pytz
from pigame.game_logic import (
    determine_next_cards_played,
    determine_starting_locations,
    determine_checkpoint_locations,
    get_cards_on_hand,
    flatten_list_of_tuples,
    load_inital_map,
    play_stack,
    switch_cards_on_hand,
    verify_map,
)

TIME_PER_ACTION = 1
COUNTDOWN_GRACE_TIME = 2


@api_view(["GET", "POST"])
@permission_classes((IsAuthenticated,))
def player_cards(request, **kwargs):
    player = request.user.account

    if player.time_submitted:
        return JsonResponse(f"You already submitted your cards at {player.time_submitted}", status=404, safe=False)

    if request.method == "POST":
        src, target = request.data
        switch_cards_on_hand(player, src, target)

    cards = []
    for playerid, card in get_cards_on_hand(player, player.game.config.ncardsavail):
        cardid, cardrank = card_id_rank(card)
        cards.append([cardid, cardrank, CARDS[cardid]])

    return JsonResponse(cards, safe=False)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def game(request, game_id, **kwargs):
    game = get_object_or_404(BaseGame, pk=game_id)
    player = request.user.account

    player_accounts = game.account_set.all()
    initmap = load_inital_map(game.config.mapfile)
    checkpoints = determine_checkpoint_locations(initmap)

    payload = dict(
        text="hallo",
        game_id=game_id,
        time_started=game.time_started,
        cards_played=game.cards_played,
        map=initmap,
        mapfile=game.config.mapfile,
        checkpoints=checkpoints,
        me=player.pk,
        countdown_duration=game.config.countdown,
        time_per_action=TIME_PER_ACTION,
        countdown=None,
    )

    player_states, actionstack = play_stack(game)

    num_players_submitted = player_accounts.filter(time_submitted__isnull=False).count()
    print(f"Game state {game.state}, player submitted {num_players_submitted}")
    if game.state in ["countdown", "select"]:
        if num_players_submitted == player_accounts.count():
            game.state = "animate"
            game.save(update_fields=["state"])

            old_actionstack = actionstack
            cards_played = game.cards_played
            cards_played_next = determine_next_cards_played(
                list(player_accounts.values_list("pk", flat=True)), game.config.player_ids, game.config.ncardslots
            )
            cards_played.extend(flatten_list_of_tuples(cards_played_next))
            game.cards_played = cards_played
            game.save(update_fields=["cards_played"])
            player_states, actionstack = play_stack(game)

            animation_time = (len(actionstack) - len(old_actionstack)) * TIME_PER_ACTION
            print(f"Animation time is {animation_time}, old stacksize {len(old_actionstack)}, new stacksize {len(actionstack)}")
            game.timestamp = datetime.datetime.now(pytz.utc) + datetime.timedelta(seconds=animation_time)
            game.save(update_fields=["timestamp"])

        elif game.state == "select" and num_players_submitted > 0:
            # check if players submitted their cards an hence countdown should start:
            game.state = "countdown"

            if game.config.countdown_mode == "d":
                if num_players_submitted > 0:
                    game.timestamp = datetime.datetime.now(pytz.utc) + datetime.timedelta(
                        seconds=game.config.countdown + COUNTDOWN_GRACE_TIME
                    )
            elif game.config.countdown_mode == "s":
                if num_players_submitted >= player_accounts.count() - 1:
                    game.timestamp = datetime.datetime.now(pytz.utc) + datetime.timedelta(
                        seconds=game.config.countdown + COUNTDOWN_GRACE_TIME
                    )
            else:
                raise ValueError(f"game.config.countdown_mode {game.config.countdown_mode} not implemented here")
            game.save(update_fields=["state", "timestamp"])

        elif game.state == "countdown":
            if datetime.datetime.now(pytz.utc) <= game.timestamp:
                dt = game.timestamp - datetime.datetime.now(pytz.utc) - datetime.timedelta(seconds=COUNTDOWN_GRACE_TIME)
                payload["countdown"] = dt.total_seconds()
                # print(f"Countdown is {dt.total_seconds()}")
            else:
                for p in player_accounts.filter(time_submitted__isnull=True):
                    p.time_submitted = datetime.datetime.now(pytz.utc)
                    p.save(update_fields=["time_submitted"])

    if (game.state == "animate") and (datetime.datetime.now(pytz.utc) > game.timestamp if game.timestamp else True):
        game.state = "select"
        game.timestamp = None
        game.round += 1
        game.save(update_fields=["state", "timestamp", "round"])

        for p in player_accounts:  # increment next card pointer
            p.next_card += game.config.ncardsavail
            p.time_submitted = None
            p.save()

    payload["actionstack"] = actionstack
    payload["Ngameround"] = game.round
    payload["players"] = {}
    for p in player_states.values():
        payload["players"][p.id] = dict(
            start_pos_x=p.start_loc_x,
            start_pos_y=p.start_loc_y,
            start_direction=p.start_direction,
            pos_x=p.xpos,
            pos_y=p.ypos,
            direction=p.direction,
            next_checkpoint=p.next_checkpoint,
            color=p.color,
            team=p.team,
        )

    return JsonResponse(payload)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def leave_game(request, **kwargs):
    account = request.user.account
    if not account.game:
        return JsonResponse(f"You are currently not in a game", status=404, safe=False)
    else:
        gameid = account.game.pk
        account.game = None
        account.save(update_fields=["game"])
        return JsonResponse(f"Left Game {gameid}", safe=False)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def submit_cards(request, **kwargs):
    account = request.user.account
    if not account.game:
        return JsonResponse(f"You are currently not in a game", status=404, safe=False)

    if account.time_submitted:
        return JsonResponse(f"You already submitted your cards at {account.time_submitted}", status=404, safe=False)

    now = datetime.datetime.now()
    account.time_submitted = now
    account.save(update_fields=["time_submitted"])

    return JsonResponse(f"You submitted your cards at {now}", safe=False)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def create_game(request, gamemaker_id, **kwargs):
    config = get_object_or_404(GameConfig, pk=gamemaker_id)
    if request.user.account.pk != config.creator_userid:
        return JsonResponse(f"Only the user who opened the game may start it", status=404, safe=False)

    if not all(config.player_ready):
        return JsonResponse(f"Not all players ready yet", status=404, safe=False)

    players = Account.objects.filter(pk__in=config.player_ids)
    initmap = load_inital_map(config.mapfile)
    xpos, ypos, dirs = determine_starting_locations(initmap)
    config.player_start_x = xpos[: len(players)]
    config.player_start_y = ypos[: len(players)]
    config.player_start_directions = dirs[: len(players)]
    game = ClassicGame()
    game.save()

    config.game = game
    config.save()

    for n, p in enumerate(players):
        p.game = game
        p.deck = DEFAULT_DECK
        random.shuffle(p.deck)
        p.next_card = 0
        p.save()

    payload = dict(
        text="game created",
        game_id=game.pk,
        time_started=game.time_started,
    )
    return JsonResponse(payload)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def view_gamemaker(request, gamemaker_id):
    caller = request.user.account
    gm = model_to_dict(get_object_or_404(GameConfig, pk=gamemaker_id))
    players = Account.objects.filter(pk__in=gm["player_ids"])
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
    gm = get_object_or_404(GameConfig, pk=gamemaker_id)

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
    if request.user.account.game:
        return JsonResponse(f"You are already in game {request.user.account.game}", status=404, safe=False)
    maker = get_object_or_404(GameConfig, pk=gamemaker_id)
    player = request.user.account
    maker.add_player(player)
    maker.save()
    return redirect(reverse("pigame:view_gamemaker", kwargs={"gamemaker_id": maker.pk}))


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
def create_gamemaker(request, **kwargs):
    if request.user.account.game:
        return JsonResponse(f"You are already in game {request.user.account.game}", status=404, safe=False)
    player = request.user.account

    data = request.data

    mapfile = data["selected_map"]

    initmap = load_inital_map(mapfile)
    errs = verify_map(initmap)
    if errs:
        return JsonResponse(errs, status=404, safe=False)

    game = GameConfig(creator_userid=player.pk, mapfile=mapfile, player_ids=[])
    game.add_player(player)
    game.save()

    payload = model_to_dict(game)
    return redirect(reverse("pigame:view_gamemaker", kwargs={"gamemaker_id": game.pk}))


@api_view(["GET", "POST"])
@permission_classes((IsAuthenticated,))
def create_new_gamemaker(request, **kwargs):
    if request.user.account.game:
        return JsonResponse(f"You are already in game {request.user.account.game}", status=404, safe=False)

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
    games = GameConfig.objects.filter(game=None)
    ret = dict(
        gameMakers=list(games.values()),
        reconnect_game=None,
    )
    try:
        ret["reconnect_game"] = request.user.account.game.pk
    except Exception as e:
        print(e)
        pass
    return JsonResponse(ret)
