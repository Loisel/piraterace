"""
Bot card-picking logic.

Public surface:
    pick_cards(bot_type, playable_cards, *, mapfile, player_id, current_state,
               checkpoints, ncardsavail)  →  List[int]
        Pure function — no DB or Redis access.  Safe to call from the evaluator.

    bot_submit_cards(gamecfg, player_idx, bot_type, *, game, player_states)
        Redis-backed wrapper used by the HTTP game view.
"""

import itertools
import math
import random

from pigame.game_logic import (
    BACKEND_USERID,
    ROUNDEND_CARDID,
    determine_checkpoint_locations,
    get_player_deck,
    load_map,
    play_stack,
    set_player_deck,
)


# ── pure picking API (no Redis) ──────────────────────────────────────────────

def pick_cards(bot_type, playable_cards, *, mapfile=None, player_id=None,
               current_state=None, checkpoints=None, ncardsavail=None):
    """
    Reorder `playable_cards` (length == ncardslots) and return the best ordering.

    Args:
        bot_type:       "random" | "greedy"
        playable_cards: list of card values that will be played this round
        mapfile:        map filename (needed by greedy for simulation)
        player_id:      fake or real player id (needed by greedy)
        current_state:  SimpleNamespace with .xpos/.ypos/.direction (from play_stack)
        checkpoints:    dict {cp_num: (x, y)} (pre-computed to avoid re-loading map)
        ncardsavail:    hand size (needed by greedy simulation health init)
    """
    if bot_type == "greedy":
        return _greedy_pick(playable_cards, mapfile, player_id, current_state, checkpoints, ncardsavail)
    # default: random
    cards = list(playable_cards)
    random.shuffle(cards)
    return cards


# ── greedy implementation ────────────────────────────────────────────────────

class _SimObj:
    """Fake game/config whose save() is a no-op so simulations skip DB writes."""
    def save(self, **kwargs):
        pass


def _simulate_end_pos(mapfile, player_id, current_state, card_list, ncardsavail):
    """Single-player play_stack simulation; returns (xpos, ypos) after one round."""
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


def _greedy_pick(playable_cards, mapfile, player_id, current_state, checkpoints, ncardsavail):
    """Try up to 100 permutations of playable_cards; return the one ending closest to next checkpoint."""
    if current_state is None or checkpoints is None or mapfile is None:
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

        ex, ey = _simulate_end_pos(mapfile, player_id, current_state, perm, ncardsavail)
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
    )
    deck[next_card : next_card + ncardsavail] = best_playable + remainder
    set_player_deck(gamecfg, player_id, deck)
