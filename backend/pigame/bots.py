"""
Bot card-picking logic.

Public surface:
    pick_cards(bot_type, playable_cards, *, mapfile, player_id, current_state,
               checkpoints, ncardsavail, map_data=None)  →  List[int]
        Pure function — no DB or Redis access.  Safe to call from the evaluator.
        Pass map_data to skip Redis and use play_one_round (fast path).

    bot_submit_cards(gamecfg, player_idx, bot_type, *, game, player_states)
        Redis-backed wrapper used by the HTTP game view.
"""

import itertools
import math
import random
import types

from pigame.game_logic import (
    BACKEND_USERID,
    ROUNDEND_CARDID,
    determine_checkpoint_locations,
    get_player_deck,
    load_map,
    play_one_round,
    play_stack,
    set_player_deck,
)
from pigame.models import CANNON_DIRECTION, FREE_HEALTH_OFFSET


# ── pure picking API (no Redis) ──────────────────────────────────────────────

def pick_cards(bot_type, playable_cards, *, mapfile=None, player_id=None,
               current_state=None, checkpoints=None, ncardsavail=None,
               map_data=None):
    """
    Reorder `playable_cards` (length == ncardslots) and return the best ordering.

    When map_data is provided, the greedy simulation uses play_one_round (fast,
    no Redis). When only mapfile is given, it falls back to play_stack + Redis.
    """
    if bot_type == "greedy":
        return _greedy_pick(playable_cards, mapfile, player_id, current_state,
                            checkpoints, ncardsavail, map_data)
    cards = list(playable_cards)
    random.shuffle(cards)
    return cards


# ── greedy implementation ────────────────────────────────────────────────────

class _SimObj:
    """Fake game/config whose save() is a no-op so play_stack skips DB writes."""
    def save(self, **kwargs):
        pass


def _simulate_end_pos(mapfile, player_id, current_state, card_list, ncardsavail):
    """Slow path: single-player play_stack simulation via Redis map load."""
    cfg = _SimObj()
    cfg.mapfile = mapfile
    cfg.player_ids = [player_id]
    cfg.player_start_x = [current_state.xpos]
    cfg.player_start_y = [current_state.ypos]
    cfg.player_start_directions = [current_state.direction]
    cfg.player_colors = [getattr(current_state, "color", "#888888")]
    cfg.player_names = [getattr(current_state, "name", "bot")]
    cfg.ncardsavail = ncardsavail

    sim_cards = []
    for card in card_list:
        sim_cards.extend([player_id, card])
    sim_cards.extend([BACKEND_USERID, ROUNDEND_CARDID])

    game = _SimObj()
    game.config = cfg
    game.cards_played = sim_cards
    game.state = "select"

    try:
        end_states, _ = play_stack(game)
        st = end_states[player_id]
        return st.xpos, st.ypos
    except Exception:
        return current_state.xpos, current_state.ypos


def _simulate_end_pos_fast(map_data, player_id, current_state, card_list, ncardsavail):
    """Fast path: uses play_one_round with pre-loaded map data — no Redis hit."""
    player = types.SimpleNamespace(
        id=player_id,
        xpos=current_state.xpos,
        ypos=current_state.ypos,
        direction=current_state.direction,
        health=ncardsavail + FREE_HEALTH_OFFSET,
        next_checkpoint=getattr(current_state, "next_checkpoint", 1),
        last_cp_x=getattr(current_state, "last_cp_x", current_state.xpos),
        last_cp_y=getattr(current_state, "last_cp_y", current_state.ypos),
        cannon_direction=CANNON_DIRECTION.FORWARD,
        powered_down=False,
        color=getattr(current_state, "color", "#888888"),
        name=getattr(current_state, "name", "bot"),
    )
    players = {player_id: player}

    sim_cards = []
    for card in card_list:
        sim_cards.extend([player_id, card])
    sim_cards.extend([BACKEND_USERID, ROUNDEND_CARDID])

    try:
        play_one_round(players, map_data, sim_cards, ncardsavail)
        return player.xpos, player.ypos
    except Exception:
        return current_state.xpos, current_state.ypos


def _greedy_pick(playable_cards, mapfile, player_id, current_state, checkpoints,
                 ncardsavail, map_data=None):
    """Try up to 100 permutations; return the ordering ending closest to next checkpoint."""
    if current_state is None or checkpoints is None:
        cards = list(playable_cards)
        random.shuffle(cards)
        return cards

    next_cp = current_state.next_checkpoint
    if next_cp not in checkpoints:
        next_cp = max(checkpoints.keys())
    cp_x, cp_y = checkpoints[next_cp]

    ncardslots = len(playable_cards)
    N_PERMS = 100
    n_total = math.factorial(ncardslots)

    # Choose simulation backend
    if map_data is not None:
        simulate = lambda perm: _simulate_end_pos_fast(map_data, player_id, current_state, perm, ncardsavail)
    elif mapfile is not None:
        simulate = lambda perm: _simulate_end_pos(mapfile, player_id, current_state, perm, ncardsavail)
    else:
        cards = list(playable_cards)
        random.shuffle(cards)
        return cards

    best_dist = float("inf")
    best_order = list(playable_cards)
    seen = set()

    perm_source = itertools.permutations(playable_cards) if n_total <= N_PERMS else None

    for _ in range(N_PERMS):
        if perm_source is not None:
            try:
                perm = list(next(perm_source))
            except StopIteration:
                break
        else:
            perm = list(playable_cards)
            random.shuffle(perm)

        key = tuple(perm)
        if key in seen:
            continue
        seen.add(key)

        ex, ey = simulate(perm)
        dist = (ex - cp_x) ** 2 + (ey - cp_y) ** 2
        if dist < best_dist:
            best_dist = dist
            best_order = perm

    return best_order


# ── Redis-backed wrapper used by the HTTP game view ──────────────────────────

def bot_submit_cards(gamecfg, player_idx, bot_type, game=None, player_states=None):
    """Fetch deck from Redis, pick cards, write back to Redis."""
    player_id = gamecfg.player_ids[player_idx]
    deck = get_player_deck(gamecfg, player_id)
    next_card = gamecfg.player_next_card[player_idx]
    ncardsavail = gamecfg.ncardsavail
    ncardslots = gamecfg.ncardslots
    hand = list(deck[next_card : next_card + ncardsavail])
    playable = hand[:ncardslots]
    remainder = hand[ncardslots:]

    checkpoints = None
    current_state = None
    if bot_type == "greedy" and player_states and player_id in player_states:
        try:
            initmap = load_map(gamecfg.mapfile)
            checkpoints = determine_checkpoint_locations(initmap)
            current_state = player_states[player_id]
        except Exception:
            pass

    best_playable = pick_cards(
        bot_type,
        playable,
        mapfile=gamecfg.mapfile,
        player_id=player_id,
        current_state=current_state,
        checkpoints=checkpoints,
        ncardsavail=ncardsavail,
        # No map_data here — HTTP path uses Redis-cached map via play_stack
    )
    deck[next_card : next_card + ncardsavail] = best_playable + remainder
    set_player_deck(gamecfg, player_id, deck)
