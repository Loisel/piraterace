from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.forms.models import model_to_dict
from django.shortcuts import redirect
from django.urls import reverse
from django.core import serializers
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.core.cache import cache

import os
import glob
import random
from piraterace.settings import MAPSDIR

from pigame.models import (
    BaseGame,
    ClassicGame,
    DEFAULT_DECK,
    FREE_HEALTH_OFFSET,
    GameConfig,
    CARDS,
    COLORS,
    card_id_rank,
    add_repair_cards,
)
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
    verify_map,
    BACKEND_USERID,
    ROUNDEND_CARDID,
    POWER_DOWN_CARDID,
)

TIME_PER_ACTION = 0.6
COUNTDOWN_GRACE_TIME = 2


def get_play_stack(game, invalidate_cache=False):
    if not invalidate_cache:
        ret = cache.get(f"play_stack{game.pk}")
        if ret is not None:
            return ret

    ret = play_stack(game)
    cache.set(f"play_stack{game.pk}", ret, 30)

    return ret


@api_view(["GET", "POST"])
@permission_classes((IsAuthenticated,))
@transaction.atomic
def player_cards(request, **kwargs):
    player = request.user.account

    if player.time_submitted:
        return JsonResponse(f"You already submitted your cards at {player.time_submitted}", status=404, safe=False)

    gamecfg = player.game.config
    pidx = gamecfg.player_ids.index(player.pk)

    if request.method == "POST":
        player_states, actionstack = get_play_stack(player.game)
        player_state = player_states[player.pk]
        cards = []
        for playerid, card in get_cards_on_hand(gamecfg, pidx, gamecfg.ncardsavail):
            cardid, cardrank = card_id_rank(card)
            cards.append([cardid, cardrank, CARDS[cardid]])
        if player_state.powered_down:
            return JsonResponse(
                {"message": f"You are not allowed to switch cards because are in a power down.", "cards": cards},
                status=404,
                safe=False,
            )

        src, target = request.data
        if any([_ >= player_state.health for _ in [src, target]]):
            return JsonResponse(
                {"message": f"You are not allowed to switch cards because your boat is damaged.", "cards": cards},
                status=404,
                safe=False,
            )

        # move card into place
        deck = gamecfg.player_decks[pidx]
        next_card = gamecfg.player_next_card[pidx]
        tmp = deck.pop(next_card + src)
        deck.insert(next_card + target, tmp)

        gamecfg.save(update_fields=["player_decks"])

    cards = []
    for playerid, card in get_cards_on_hand(gamecfg, pidx, gamecfg.ncardsavail):
        cardid, cardrank = card_id_rank(card)
        cards.append([cardid, cardrank, CARDS[cardid]])

    return JsonResponse(cards, safe=False)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
@transaction.atomic
def game(request, game_id, **kwargs):
    try:
        game = BaseGame.objects.filter(pk=game_id).select_for_update()[0]
    except IndexError:
        raise Http404("No MyModel matches the given query.")

    player = request.user.account

    player_accounts = game.account_set.all()
    initmap = load_inital_map(game.config.mapfile)
    checkpoints = determine_checkpoint_locations(initmap)

    payload = dict(
        game_id=game_id,
        time_started=game.time_started,
        cardslots=game.config.ncardslots,
        cards_played=game.cards_played,
        map=initmap,
        mapfile=game.config.mapfile,
        checkpoints=checkpoints,
        me=player.pk,
        countdown_duration=game.config.countdown,
        time_per_action=TIME_PER_ACTION,
        countdown=None,
        initial_health=game.config.ncardsavail + FREE_HEALTH_OFFSET,
    )

    player_states, actionstack = get_play_stack(game)
    actionstack = prune_actionstack(actionstack)

    num_players_submitted = player_accounts.filter(time_submitted__isnull=False).count()
    # print(f"Game state {game.state}, player submitted {num_players_submitted}")
    if game.state in ["countdown", "select"]:
        num_players_powerdown = len([p for p in player_states.values() if p.powered_down])
        if num_players_submitted >= player_accounts.count() - num_players_powerdown:
            game.state = "animate"
            game.save(update_fields=["state"])

            old_actionstack = actionstack
            cards_played = game.cards_played
            cards_played_next = determine_next_cards_played(game.config)
            cards_played.extend(flatten_list_of_tuples(cards_played_next))
            cards_played.extend((BACKEND_USERID, ROUNDEND_CARDID))
            game.cards_played = cards_played
            game.save(update_fields=["cards_played"])
            player_states, actionstack = get_play_stack(game, invalidate_cache=True)
            actionstack = prune_actionstack(actionstack)

            animation_time = (len(actionstack) - len(old_actionstack)) * TIME_PER_ACTION
            # print(f"Animation time is {animation_time}, old stacksize {len(old_actionstack)}, new stacksize {len(actionstack)}")
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

    if (game.state == "animate") and (datetime.datetime.now(pytz.utc) > game.timestamp):
        game.state = "select"
        game.timestamp = None
        game.round += 1
        game.save(update_fields=["state", "timestamp", "round"])

        for i in range(len(game.config.player_next_card)):
            game.config.player_next_card[i] += game.config.ncardsavail
            game.config.save(update_fields=["player_next_card"])

        for p in player_accounts:  # increment next card pointer
            p.time_submitted = None
            p.save(update_fields=["time_submitted"])

    payload["actionstack"] = actionstack
    # [print(i, a) for i, a in enumerate(payload["actionstack"])]

    payload["Ngameround"] = game.round
    payload["state"] = game.state
    payload["player_decks"] = game.config.player_decks
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
            health=p.health,
            powered_down=p.powered_down,
        )

    return JsonResponse(payload)


def prune_actionstack(actionstack):
    """remove empty actions"""
    slim_stack = []
    for a in actionstack:
        if len(a) > 0:
            slim_stack.append(a)
    return slim_stack


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def leave_game(request, **kwargs):
    account = request.user.account
    if not account.game:
        return JsonResponse(f"You are currently not in a game", status=404, safe=False)
    else:
        gameid = account.game.pk
        account.game = None
        account.gameconfig = None
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
def power_down(request, **kwargs):
    account = request.user.account
    if not account.game:
        return JsonResponse(f"You are currently not in a game", status=404, safe=False)

    if account.time_submitted:
        return JsonResponse(f"You already submitted your cards at {account.time_submitted}", status=404, safe=False)
    if not account.game:
        return JsonResponse(f"You are currently not in a game", status=404, safe=False)

    for pid, card in zip(account.game.cards_played[-2::-2], account.game.cards_played[-1::-2]):
        if card == ROUNDEND_CARDID:
            break
        elif (card == POWER_DOWN_CARDID) and (pid == account.pk):
            return JsonResponse(f"You already requested a power down.", status=404, safe=False)

    account.game.cards_played.extend((account.pk, POWER_DOWN_CARDID))
    account.game.save(update_fields=["cards_played"])

    return JsonResponse(f"Power down requested", safe=False)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def create_game(request, gameconfig_id, **kwargs):
    config = get_object_or_404(GameConfig, pk=gameconfig_id)
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

    for i, pid in enumerate(config.player_ids):
        deck = players.get(pk=pid).deck
        deck = add_repair_cards(deck, config.percentage_repaircards)
        random.shuffle(deck)
        config.player_decks.append(deck)
        config.player_next_card.append(0)

    game = ClassicGame()
    game.save()

    config.game = game
    config.save()

    for n, p in enumerate(players):
        p.game = game
        p.time_submitted = None
        p.save()

    payload = dict(
        text="game created",
        game_id=game.pk,
        time_started=game.time_started,
    )
    return JsonResponse(payload)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def view_gameconfig(request, gameconfig_id):
    caller = request.user.account

    try:
        game_config = GameConfig.objects.get(pk=gameconfig_id)
    except Exception as e:
        print(f"Could not find game_config with id {gameconfig_id} -> {e}")
        return JsonResponse(f"Game config does not exist anymore", status=404, safe=False)

    cfg = model_to_dict(game_config)
    cfg["player_names"] = [Account.objects.get(pk=pid).user.username for pid in cfg["player_ids"]]
    cfg["all_ready"] = all(game_config.player_ready)

    ## colors_to_pick = [c for c in COLORS.keys() if c not in cfg["player_colors"]]
    ## the callers color can also be chosen
    ## colors_to_pick.append(cfg["player_colors"][cfg["player_ids"].index(caller.pk)])
    cfg["player_color_choices"] = COLORS
    cfg["caller_id"] = caller.pk
    cfg["caller_idx"] = cfg["player_ids"].index(caller.pk)
    cfg["map_info"] = load_inital_map(cfg["mapfile"])
    cfg["startinglocs"] = list(filter(lambda l: l["name"] == "startinglocs", cfg["map_info"]["layers"]))[0]

    return JsonResponse(cfg)


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
def update_gm_player_info(request, gameconfig_id):
    caller = request.user.account
    gm = get_object_or_404(GameConfig, pk=gameconfig_id)

    data = request.data
    idx = gm.player_ids.index(caller.pk)

    gm.player_colors[idx] = data["color"]
    gm.player_teams[idx] = data["team"]
    gm.player_ready[idx] = data["ready"]
    gm.save()

    return redirect(reverse("pigame:view_gameconfig", kwargs={"gameconfig_id": gm.pk}))


def clean_up_configs(player):
    # clean up other open configs
    other_game_cfgs = GameConfig.objects.filter(game=None).filter(player_ids__contains=[player.pk])
    for cfg in other_game_cfgs:
        if player.pk == cfg.creator_userid:
            cfg.delete()
        else:
            cfg.del_player(player)
            cfg.save()


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def join_gameconfig(request, gameconfig_id, **kwargs):
    if request.user.account.game:
        return JsonResponse(f"You are already in game {request.user.account.game}", status=404, safe=False)

    config = get_object_or_404(GameConfig, pk=gameconfig_id)

    if len(config.player_ids) >= config.nmaxplayers:
        return JsonResponse(f"Game Full ({len(config.player_ids)}/{config.nmaxplayers})", status=404, safe=False)

    player = request.user.account
    clean_up_configs(player)

    config.add_player(player)
    config.save()

    return redirect(reverse("pigame:view_gameconfig", kwargs={"gameconfig_id": config.pk}))


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def leave_gameconfig(request, **kwargs):
    player = request.user.account

    if player.game:
        return JsonResponse(f"Game {player.game.pk} running.", safe=False)

    clean_up_configs(player)
    return JsonResponse({"success": f"Detached from gameconfig."})


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
def create_gameconfig(request, **kwargs):
    if request.user.account.game:
        return JsonResponse(f"You are already in game {request.user.account.game}", status=404, safe=False)
    player = request.user.account

    clean_up_configs(player)
    data = request.data

    mapfile = data["selected_map"]

    initmap = load_inital_map(mapfile)
    errs = verify_map(initmap)
    if errs:
        return JsonResponse(errs, status=404, safe=False)

    gameconfig = GameConfig(
        creator_userid=player.pk,
        mapfile=mapfile,
        player_ids=[],
        player_decks=[],
        nmaxplayers=data["Nmaxplayers"],
    )
    gameconfig.add_player(player)
    gameconfig.save()

    payload = model_to_dict(gameconfig)
    return redirect(reverse("pigame:view_gameconfig", kwargs={"gameconfig_id": gameconfig.pk}))


@api_view(["GET", "POST"])
@permission_classes((IsAuthenticated,))
def create_new_gameconfig(request, **kwargs):
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
        ret["startinglocs"] = startinglocslayer
        ret["Nmaxplayers"] = len(startinglocslayer["objects"])

    return JsonResponse(ret)


def list_gameconfigs(request):
    if not request.user.is_anonymous:
        clean_up_configs(request.user.account)

    games = GameConfig.objects.filter(game=None)
    ret = dict(
        gameconfigs=list(games.values()),
        reconnect_game=None,
    )
    try:
        ret["reconnect_game"] = request.user.account.game.pk
    except Exception as e:
        print(e)
        pass
    return JsonResponse(ret)
