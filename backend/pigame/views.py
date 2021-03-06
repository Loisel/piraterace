from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from pigame.models import BaseGame, ClassicGame, DEFAULT_DECK, DIRID2NAME, DIRNAME2ID, CARDS, DIRID2MOVE
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
    players = {p.pk: p for p in list(game.account_set.all())}
    
    for pk, player in players.items():
        player.direction = player.start_direction
        player.xpos = player.start_loc_x
        player.ypos = player.start_loc_y

    stack = zip(stack[::2], stack[1::2])
    for playerid, card in stack:
        player = players[playerid]
        player.direction = (player.direction + CARDS[card]["rot"]) % 4
        player.xpos += DIRID2MOVE[player.direction][0]
        player.ypos += DIRID2MOVE[player.direction][1]

    return players
        
        


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

    players = play_stack(game)

    for p in players.values():
        payload[f"player{p.pk}"] = dict(
            start_pos_x = p.start_loc_x,
            start_pos_y = p.start_loc_y,
            pos_x = p.xpos,
            pos_y = p.ypos,
            direction = p.direction
        )
    return JsonResponse(payload)

def create_debug_game(request, **kwargs):
    players = [
            get_object_or_404(Account, user__username='root'),
            ]
    game = ClassicGame(creator_userid=players[0].pk, mapfile="map1.json")
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


def load_inital_map(fname):
    with open(os.path.join(MAPSDIR, fname)) as fh:
        dt = json.load(fh)
    return dt
