from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.forms.models import model_to_dict
from django.shortcuts import redirect
from django.urls import reverse
from django.core import serializers
from pigame.models import (
    BaseGame, ClassicGame, DEFAULT_DECK, DIRID2NAME, DIRNAME2ID, CARDS, DIRID2MOVE,
    GameMaker)
from piplayer.models import Account
from piraterace.settings import MAPSDIR
import datetime
import pytz
import json
import os
import random

# Create your views here.

def determine_next_cards_played(players, ncardslots):
    r = []
    for i in range(0,ncardslots):
        res = []
        for p in players:
            res.extend((p.id, p.deck[(p.next_card+i) % 4]))
        # sort by ranking...
        r.extend(res)
    return r

def determine_starting_locations(initmap, players):
    for layer in initmap["layers"]:
        if layer["name"] == "startinglocs":
            positions = layer["objects"]
            break

    random.shuffle(positions)
    theight = initmap["tileheight"]
    twidth = initmap["tilewidth"]
    for n, player in enumerate(players):
        player.start_loc_x = int(positions[n]["x"] / twidth)
        player.start_loc_y = int(positions[n]["y"] / theight)
        player.start_direction = random.choice(list(DIRID2NAME.keys()))
    return players

def play_stack(game):
    initial_map = load_inital_map(game.mapfile)
    stack = game.cards_played
    Nrounds = len(game.cards_played) // game.ncardslots
    players = {p.pk: p for p in list(game.account_set.all())}

    for pk, player in players.items():
        player.direction = player.start_direction
        player.xpos = player.start_loc_x
        player.ypos = player.start_loc_y

    stack = list(zip(stack[::2], stack[1::2]))
    #for playerid, card in stack:
    #    player = players[playerid]
    #    player.direction = (player.direction + CARDS[card]["rot"]) % 4
    #    player.xpos += DIRID2MOVE[player.direction][0]
    #    player.ypos += DIRID2MOVE[player.direction][1]



    actionstack = []
    for rnd in range(Nrounds):

        stack_start = rnd * game.ncardslots * len(players)
        stack_end = (rnd+1) * game.ncardslots * len(players)
        this_round_cards = stack[stack_start:stack_end]

        for playerid, card in this_round_cards:
            player = players[playerid]
            actions = get_actions_for_card(game, initial_map, players, playerid, card)
            actionstack.extend(actions)

    return players, actionstack


def get_actions_for_card(game, gmap, players, playerid, card):
    player = players[playerid]

    actions = []
    rot = CARDS[card]['rot']
    if rot != 0:
        actions.append(dict(key="rotate", target=playerid, val=rot))
        player.direction = (player.direction + rot) % 4

    for mov in range(abs(CARDS[card]['move'])):
        # here collisions have to happen
        inc = int(CARDS[card]['move'] / abs(CARDS[card]['move']))

        xinc = DIRID2MOVE[player.direction][0] * inc
        yinc = DIRID2MOVE[player.direction][1] * inc

        if xinc != 0:
            actions.extend(move_player_x(game, gmap, players, player, xinc))
        if yinc != 0:
            actions.extend(move_player_y(game, gmap, players, player, yinc))
    return actions


def move_player_x(game, gmap, players, player, inc):
    actions = []
    bg = list(filter(lambda l: l["name"] == "background", gmap["layers"]))[0]
    tile_id = bg["data"][player.ypos * bg["width"] + player.xpos + inc]
    tile_props = gmap["tilesets"][0]["tiles"]
    tile_prop = next(filter(lambda p: p["id"] == tile_id, tile_props))
    if next(filter(lambda p: p["name"] == "collision", tile_prop["properties"]))["value"] == True:
        damage = next(filter(lambda p: p["name"] == "damage", tile_prop["properties"]))["value"]
        actions.append(dict(key="collision_x", target=player.pk, val=inc, damage=damage))
        return actions
    for pid, p in players.items():
        if (p.xpos == player.xpos + inc) and (p.ypos == player.ypos):
            actions.extend(move_player_x(game, gmap, players, p, inc))
            if (p.xpos == player.xpos + inc) and (p.ypos == player.ypos):
                return actions
            break
    player.xpos += inc
    actions.append(dict(key="move_x", target=player.pk, val=inc))
    return actions

def move_player_y(game, gmap, players, player, inc):
    actions = []
    bg = list(filter(lambda l: l["name"] == "background", gmap["layers"]))[0]
    tile_id = bg["data"][(player.ypos + inc) * bg["width"] + player.xpos]
    tile_props = gmap["tilesets"][0]["tiles"]
    tile_prop = next(filter(lambda p: p["id"] == tile_id, tile_props))
    if next(filter(lambda p: p["name"] == "collision", tile_prop["properties"]))["value"] == True:
        damage = next(filter(lambda p: p["name"] == "damage", tile_prop["properties"]))["value"]
        actions.append(dict(key="collision_y", target=player.pk, val=inc, damage=damage))
        return actions
    for pid, p in players.items():
        if (p.xpos == player.xpos) and (p.ypos == player.ypos + inc):
            actions.extend(move_player_y(game, gmap, players, p, inc))
            if (p.xpos == player.xpos) and (p.ypos == player.ypos + inc):
                return actions
            break
    player.ypos += inc
    actions.append(dict(key="move_y", target=player.pk, val=inc))
    return actions

def game(request, game_id, **kwargs):
    game = get_object_or_404(BaseGame, pk=game_id)
    players = game.account_set.all()
    initmap = load_inital_map(game.mapfile)

    payload = dict(
        text='hallo',
        game_id=game_id,
        time_started = game.time_started,
        cards_played = game.cards_played,
        map = initmap,
        mapfile = game.mapfile
    )

    if datetime.datetime.now(pytz.utc) > game.timestamp + datetime.timedelta(seconds=game.round_time):
        cards_played = game.cards_played
        cards_played.extend(
                determine_next_cards_played(
                    players, game.ncardslots)
                )
        game.cards_played = cards_played
        game.timestamp = datetime.datetime.now()
        game.save()

        for p in players: # increment next card pointer
            p.next_card += game.ncardsavail
            p.save()

        payload['text'] = "game increment"

    players, actionstack = play_stack(game)

    payload["actionstack"] = actionstack
    payload["players"] = {}
    for p in players.values():
        payload["players"][p.pk] = dict(
            start_pos_x = p.start_loc_x,
            start_pos_y = p.start_loc_y,
            start_direction = p.start_direction,
            pos_x = p.xpos,
            pos_y = p.ypos,
            direction = p.direction
        )
    return JsonResponse(payload)


def create_debug_game(request, **kwargs):
    players = [
        get_object_or_404(Account, user__username='root'),
    ]
    game = ClassicGame(mapfile="map1.json")
    game.save()

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
            text='game created',
            game_id=game.pk,
            time_started = game.time_started,
            url=f"http://localhost:8000/pigame/game/{game.pk}",
            )
    return JsonResponse(payload)

def create_game(request, gamemaker_id, **kwargs):
    maker = get_object_or_404(GameMaker, pk=gamemaker_id)
    players = Account.objects.filter(user__pk__in=maker.player_ids)
    game = ClassicGame(mapfile=maker.mapfile,
                       mode = maker.mode,
                       nlives = maker.nlives,
                       damage_on_hit = maker.damage_on_hit,
                       npause_on_repair = maker.npause_on_repair,
                       npause_on_destroy = maker.npause_on_destroy,
                       ncardslots = maker.ncardslots,
                       ncardsavail = maker.ncardsavail,
                       allow_transfer = maker.allow_transfer,
                       countdown_mode = maker.countdown_mode,
                       countdown = maker.countdown,
                       round_time = maker.round_time
    )
    game.save()

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
            text='game created',
            game_id=game.pk,
            time_started = game.time_started,
            url=f"http://localhost:8000/pigame/game/{game.pk}",
    )
    return JsonResponse(payload)


def view_gamemaker(request, gamemaker_id):
    return JsonResponse(model_to_dict(get_object_or_404(GameMaker, pk=gamemaker_id)))

def list_gamemakers(request):
    makers = GameMaker.objects.all()
    return JsonResponse(list(makers.values()), safe=False)

def join_gamemaker(request, gamemaker_id, **kwargs):
    maker = get_object_or_404(GameMaker, pk=gamemaker_id)
    player = get_object_or_404(Account, user__username='al')
    maker.add_player(player)
    maker.save()
    return redirect(reverse("pigame:view_gamemaker", kwargs={"gamemaker_id": maker.pk}))

def create_gamemaker(request, **kwargs):
    player = get_object_or_404(Account, user__username='root')
    mapfile="map2.json"
    
    initmap = load_inital_map(mapfile)
    errs = verify_map(initmap)
    if errs:
        return JsonResponse(errs, status=404, safe=False)
    maker = GameMaker(creator_userid=player.pk, mapfile=mapfile, player_ids=[])
    maker.add_player(player)
    maker.save()

    payload = model_to_dict(maker)
    return redirect(reverse("pigame:view_gamemaker", kwargs={"gamemaker_id": maker.pk}))

def load_inital_map(fname):
    with open(os.path.join(MAPSDIR, fname)) as fh:
        dt = json.load(fh)
    # tl = dt.layers[0].data
    # colliding = []
    return dt

def verify_map(mapobj):
    layer_names = [l["name"] for l in mapobj["layers"]]
    err_msg = []
    if not "background" in layer_names:
        err_msg.append("No background layer in map.")
    if not "startinglocs" in layer_names:
        err_msg.append("No startinglocs layer in map.")
    else:
        slayer = list(filter(lambda l: l["name"] == "startinglocs", mapobj["layers"]))[0]
        if len(slayer["objects"]) < 1:
            err_msg.append(f"startinglocs layer has only {len(slayer['objects'])} entries.")
    tilesets = mapobj["tilesets"]
    if len(tilesets) != 1:
        err_msg.append(f"{len(tilesets)} tilesets found. Only supporting 1 tileset.")
    return err_msg
