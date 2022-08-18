from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.forms.models import model_to_dict
from django.shortcuts import redirect
from django.urls import reverse
from django.core import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated

from pigame.models import (
    BaseGame, ClassicGame, DEFAULT_DECK,
    GameMaker)
from piplayer.models import Account
import datetime
import pytz
from pigame.game_logic import (
        determine_next_cards_played,
        determine_starting_locations,
        load_inital_map,
        play_stack,
        verify_map,
        )


@api_view(['GET'])
@permission_classes((IsAuthenticated, ))
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


@api_view(['GET'])
@permission_classes((IsAuthenticated, ))
def create_game(request, gamemaker_id, **kwargs):
    maker = get_object_or_404(GameMaker, pk=gamemaker_id)
    if request.user.pk != maker.creator_userid:
        return JsonResponse(f'Only the user who opened the game may start it', status=404, safe=False)

    players = Account.objects.filter(user__pk__in=maker.player_ids)
    print(f"Players in Game: {players}")
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


@api_view(['GET'])
@permission_classes((IsAuthenticated, ))
def view_gamemaker(request, gamemaker_id):
    return JsonResponse(model_to_dict(get_object_or_404(GameMaker, pk=gamemaker_id)))

@api_view(['GET'])
@permission_classes((IsAuthenticated, ))
def join_gamemaker(request, gamemaker_id, **kwargs):
    maker = get_object_or_404(GameMaker, pk=gamemaker_id)
    player = request.user
    maker.add_player(player)
    maker.save()
    return redirect(reverse("pigame:view_gamemaker", kwargs={"gamemaker_id": maker.pk}))

@api_view(['GET'])
@permission_classes((IsAuthenticated, ))
def create_gamemaker(request, **kwargs):
    player = request.user
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

def list_gamemakers(request):
    makers = GameMaker.objects.all()
    return JsonResponse(list(makers.values()), safe=False)

