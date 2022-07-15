from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from pigame.models import BaseGame, ClassicGame, DEFAULT_DECK
from piplayer.models import Account
import datetime
import pytz

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


def game(request, game_id, **kwargs):
    game = get_object_or_404(BaseGame, pk=game_id)
    players = game.account_set.all()

    payload = dict(
            text='hallo',
            game_id=game_id,
            time_started = game.time_started,
            cards_played = game.cards_played,
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

    for p in players:
        payload[f"player{p.pk}"] = dict(
                deck=p.deck,
                )
    return JsonResponse(payload)

def create_debug_game(request, **kwargs):
    players = [
            get_object_or_404(Account, user__username='root'),
            ]
    game = ClassicGame(creator_userid=players[0].pk)
    game.save()

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
