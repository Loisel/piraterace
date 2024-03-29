from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.forms.models import model_to_dict
from django.shortcuts import redirect
from django.urls import reverse
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.core.cache import cache

import os
import glob
from piraterace.settings import MAPSDIR

from pigame.models import (
    BaseGame,
    ClassicGame,
    FREE_HEALTH_OFFSET,
    GameConfig,
    CARDS,
    COLORS,
    card_id_rank,
    CANNON_DIRECTION_DESCR2ID,
    CANNON_DIRECTION_DIRID2CARDID,
    CANNON_DIRECTION_CARDS,
)
from piplayer.models import Account
import datetime
import pytz
from pigame.game_logic import (
    determine_next_cards_played,
    determine_starting_locations,
    startinglocs_pixels,
    determine_checkpoint_locations,
    get_cards_on_hand,
    flatten_list_of_tuples,
    load_map,
    play_stack,
    verify_map,
    BACKEND_USERID,
    ROUNDEND_CARDID,
    POWER_DOWN_CARDID,
    get_player_deck,
    set_player_deck,
    calc_stats,
)

from pichat.views import gen_gameconfigchatslug, gen_gamechatslug

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

    if player.game.state in ["end"]:  # if game ended we dont need to serve cards anymore
        return JsonResponse([], safe=False)

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
        deck = get_player_deck(gamecfg, player.pk)
        next_card = gamecfg.player_next_card[pidx]
        tmp = deck.pop(next_card + src)
        deck.insert(next_card + target, tmp)
        set_player_deck(gamecfg, player.pk, deck)

    cards = []
    for playerid, card in get_cards_on_hand(gamecfg, pidx, gamecfg.ncardsavail):
        cardid, cardrank = card_id_rank(card)
        cards.append([cardid, cardrank, CARDS[cardid]])

    return JsonResponse(cards, safe=False)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
@transaction.atomic
def player_cannon_direction(request, direction_id, **kwargs):
    player = request.user.account

    if player.game.state in ["animate", "end"]:
        return JsonResponse(
            f"You are not allowed to modify the cannon direction during the animation phase.",
            status=404,
            safe=False,
        )

    if direction_id not in CANNON_DIRECTION_CARDS:
        return JsonResponse(
            f"Can not change cannon direction: {direction_id} is not a valid cannon direction.",
            status=404,
            safe=False,
        )

    player.game.cards_played.extend((player.pk, direction_id))
    player.game.save(update_fields=["cards_played"])

    return JsonResponse({"success": True}, safe=False)


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
    initmap = load_map(game.config.mapfile)
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
        CARDS=CARDS,
        CANNON_DIRECTION_DESCR2ID=CANNON_DIRECTION_DESCR2ID,
        path_highlighting=game.config.path_highlighting,
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
            if player_states[game.config.player_ids[i]].powered_down:
                continue
            game.config.player_next_card[i] += game.config.ncardslots
            game.config.save(update_fields=["player_next_card"])

        for p in player_accounts:  # increment next card pointer
            p.time_submitted = None
            p.save(update_fields=["time_submitted"])

    payload["actionstack"] = actionstack
    # [print(i, a) for i, a in enumerate(payload["actionstack"])]

    payload["Ngameround"] = game.round
    payload["state"] = game.state
    payload["players"] = {}
    for p in player_states.values():
        payload["players"][p.id] = dict(
            name=p.name,
            pos_x=p.xpos,
            pos_y=p.ypos,
            start_pos_x=p.start_pos_x,
            start_pos_y=p.start_pos_y,
            direction=p.direction,
            start_direction=p.start_direction,
            next_checkpoint=p.next_checkpoint,
            color=p.color,
            health=p.health,
            powered_down=p.powered_down,
            is_zombie=p.id not in game.account_set.values_list("user_id", flat=True),
            cannon_direction=str(CANNON_DIRECTION_DIRID2CARDID[p.cannon_direction]),
        )

    summary = None
    if game.state in ["end"]:
        for a in payload["actionstack"][::-1]:
            if len(a) > 0:
                if a[0]["key"] == "win":
                    winner_id = a[0]["target"]
                    winner = Account.objects.get(pk=winner_id)
                    summary = dict(
                        winner_id=winner_id,
                        winner=winner.user.username,
                    )
                    break

        stats = calc_stats(game)
        stats["summary"] = summary
        payload["stats"] = stats
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
            return JsonResponse(f"You already requested to re-rig the sails.", status=404, safe=False)

    account.game.cards_played.extend((account.pk, POWER_DOWN_CARDID))
    account.game.save(update_fields=["cards_played"])

    return JsonResponse(f"Next round will be used to re-rig the sails.", safe=False)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def create_game(request, gameconfig_id, **kwargs):
    config = get_object_or_404(GameConfig, pk=gameconfig_id)
    if request.user.account.pk != config.creator_userid:
        return JsonResponse(f"Only the user who opened the game may start it", status=404, safe=False)

    creator_index = config.player_ids.index(config.creator_userid)
    config.player_ready[creator_index] = True

    if not all(config.player_ready):
        return JsonResponse(f"Not all players ready yet", status=404, safe=False)

    if config.game is not None:
        return JsonResponse(f"The game is about to start, go grab some grok! {config.game}", status=404, safe=False)

    players = Account.objects.filter(pk__in=config.player_ids)
    initmap = load_map(config.mapfile)
    xpos, ypos, dirs = determine_starting_locations(initmap)
    config.player_start_x = xpos[: len(players)]
    config.player_start_y = ypos[: len(players)]
    config.player_start_directions = dirs[: len(players)]

    for i, pid in enumerate(config.player_ids):
        set_player_deck(config, pid, None)
        config.player_next_card.append(0)

    game = ClassicGame()
    game.save()

    config.game = game
    config.request_id = 2**14

    cfgchatslug = gen_gameconfigchatslug(config.pk)
    gamechatslug = gen_gamechatslug(config.game)
    cache.set(gamechatslug, cache.get(cfgchatslug))

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
    creator_index = game_config.player_ids.index(game_config.creator_userid)
    cfg["player_ready"][creator_index] = True
    cfg["all_ready"] = all(cfg["player_ready"])

    ## colors_to_pick = [c for c in COLORS.keys() if c not in cfg["player_colors"]]
    ## the callers color can also be chosen
    ## colors_to_pick.append(cfg["player_colors"][cfg["player_ids"].index(caller.pk)])
    cfg["player_color_choices"] = COLORS
    cfg["caller_id"] = caller.pk
    cfg["caller_idx"] = cfg["player_ids"].index(caller.pk)

    return JsonResponse(cfg)


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
def update_gamecfg_player_info(request, gameconfig_id, request_id):
    caller = request.user.account
    gamecfg = get_object_or_404(GameConfig, pk=gameconfig_id)

    if request_id <= gamecfg.request_id:
        return JsonResponse(
            f"Found old gamecfg change options request backend {gamecfg.request_id} request {request_id}", status=404, safe=False
        )
    data = request.data
    idx = gamecfg.player_ids.index(caller.pk)

    gamecfg.player_colors[idx] = data["color"]
    gamecfg.player_ready[idx] = data["ready"]
    gamecfg.request_id = request_id
    gamecfg.save()

    return redirect(reverse("pigame:view_gameconfig", kwargs={"gameconfig_id": gamecfg.pk}))


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def predict_path(request):
    player = request.user.account
    if not player.game:
        return JsonResponse(f"Can not predict path. You are not in a game.", status=404, safe=False)
    if not player.game.config.path_highlighting:
        return JsonResponse(f"Can not predict path. Path highlighting is disabled.", status=404, safe=False)
    gamecfg = player.game.config
    game = player.game
    player_states, old_actionstack = get_play_stack(game)

    player_idx = gamecfg.player_ids.index(player.pk)
    cards_played_next = get_cards_on_hand(gamecfg, player_idx, gamecfg.ncardslots)

    # effectively remove other players from game
    # fields that are not overwritten have wrong values but we (hopefully) do not care
    gamecfg.player_ids = [player.pk]
    gamecfg.player_start_x = [player_states[player.pk].xpos]
    gamecfg.player_start_y = [player_states[player.pk].ypos]
    gamecfg.player_start_directions = [player_states[player.pk].direction]

    game.cards_played = flatten_list_of_tuples(cards_played_next)
    game.cards_played.extend((BACKEND_USERID, ROUNDEND_CARDID))

    player_states, actionstack = play_stack(game)
    path = []
    for actiongroup in actionstack:
        for action in actiongroup:
            if "move" in action.get("key", ""):
                path.append(action["target_pos"])

    return JsonResponse(path, safe=False)


@api_view(["POST"])
@permission_classes((IsAuthenticated,))
def update_gamecfg_options(request, gameconfig_id, request_id):
    caller = request.user.account
    gamecfg = get_object_or_404(GameConfig, pk=gameconfig_id)

    if caller.pk != gamecfg.creator_userid:
        return JsonResponse(f"Only the Game Creator can change options", status=404, safe=False)

    if request_id <= gamecfg.request_id:
        return JsonResponse(
            f"Found old gamecfg change options request backend {gamecfg.request_id} request {request_id}", status=404, safe=False
        )

    data = request.data

    if data["ncardslots"] > data["ncardsavail"]:
        return JsonResponse(f"Number of cards to play has to be smaller than number of cards on hand", status=404, safe=False)

    if data["ncardslots"] < 1:
        return JsonResponse(f"Number of cards to play has to be at least 1", status=404, safe=False)

    if data["percentage_repaircards"] < 0:
        return JsonResponse(f"Repair card fraction has to be a positive number", status=404, safe=False)
    if data["percentage_repaircards"] > 100:
        return JsonResponse(f"Repair card fraction has to be less than 100%", status=404, safe=False)

    if data["countdown"] < 0:
        return JsonResponse(f"Countdown has to be a positive number", status=404, safe=False)

    gamecfg.request_id = request_id
    gamecfg.ncardsavail = data["ncardsavail"]
    gamecfg.ncardslots = data["ncardslots"]
    gamecfg.countdown = data["countdown"]
    gamecfg.path_highlighting = data["path_highlighting"]
    gamecfg.percentage_repaircards = data["percentage_repaircards"]
    for i, p in enumerate(gamecfg.player_ready):  # set all player ready flags to false if something in the config changed
        gamecfg.player_ready[i] = False
    gamecfg.save()

    return redirect(reverse("pigame:view_gameconfig", kwargs={"gameconfig_id": gamecfg.pk}))


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
    gamename = data.get("gamename", "")

    initmap = load_map(mapfile)
    errs = verify_map(initmap)
    if errs:
        return JsonResponse(errs, status=404, safe=False)

    gameconfig = GameConfig(
        gamename=gamename,
        creator_userid=player.pk,
        mapfile=mapfile,
        player_ids=[],
        nmaxplayers=data["Nmaxplayers"],
    )
    gameconfig.add_player(player)
    gameconfig.save()

    return redirect(reverse("pigame:view_gameconfig", kwargs={"gameconfig_id": gameconfig.pk}))


@api_view(["GET", "POST"])
@permission_classes((IsAuthenticated,))
def create_new_gameconfig(request, **kwargs):
    if request.user.account.game:
        return JsonResponse(f"You are already in game {request.user.account.game}", status=404, safe=False)

    available_maps = [load_map(f) for f in glob.glob(os.path.join(MAPSDIR, "*.json"))]

    ret = dict(
        available_maps=available_maps,
        selected_map=None,
        map_info=None,
        Nmaxplayers=None,
        gamename=f"{request.user.username}'s Game",
    )

    if request.method == "POST":
        ret.update(**request.data)

    if ret["selected_map"]:
        ret["map_info"] = load_map(ret["selected_map"])
        ret["Nmaxplayers"] = len(startinglocs_pixels(ret["map_info"]))

    return JsonResponse(ret, safe=False)


@api_view(["GET"])
@permission_classes((IsAuthenticated,))
def get_mapinfo(request, mapfile):
    mapinfo = load_map(os.path.join(MAPSDIR, mapfile))
    payload = dict(
        mapfile=mapfile,
        startinglocs=startinglocs_pixels(mapinfo),
        checkpoints=determine_checkpoint_locations(mapinfo),
        map_info=mapinfo,
    )
    return JsonResponse(payload, safe=False)


def list_gameconfigs(request):
    if not request.user.is_anonymous:
        clean_up_configs(request.user.account)

    games = GameConfig.objects.filter(game=None)
    games_info = []
    for game in games.values():
        game["mapinfo"] = load_map(game["mapfile"])
        games_info.append(game)
    ret = dict(
        gameconfigs=games_info,
        reconnect_game=None,
    )
    try:
        ret["reconnect_game"] = request.user.account.game.pk
    except Exception as e:
        print(e)
        pass
    return JsonResponse(ret)
