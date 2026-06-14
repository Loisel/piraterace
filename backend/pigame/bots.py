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
               map_data=None, **kwargs):
    """
    Reorder `playable_cards` (length == ncardslots) and return the best ordering.

    When map_data is provided, the greedy simulation uses play_one_round (fast,
    no Redis). When only mapfile is given, it falls back to play_stack + Redis.
    """
    if bot_type == "greedy":
        return _greedy_pick(playable_cards, mapfile, player_id, current_state,
                            checkpoints, ncardsavail, map_data)
    if bot_type.startswith("rl"):
        return _rl_pick(bot_type, playable_cards, current_state, ncardsavail,
                        checkpoints=checkpoints, map_data=map_data,
                        opponent_states=kwargs.get("opponent_states"))
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


# ── RL bot ───────────────────────────────────────────────────────────────────

_rl_session_cache: dict = {}   # tag → onnxruntime.InferenceSession
_rl_map_enc_cache: dict = {}   # id(map_data) → encoded map feature array


def _rl_pick(bot_type: str, playable_cards, current_state, ncardsavail,
             checkpoints=None, map_data=None, opponent_states=None):
    """
    Use a trained PPO policy (exported to ONNX) to pick card play order.

    bot_type routing:
        "rl"           → rl_models/solo_map1.onnx  (default)
        "rl:solo_map1" → rl_models/solo_map1.onnx
        "rl:path/to/x" → that path (no .onnx added if it contains a separator)

    Action space is (N_CARD_TYPES,) type-preference scores.  The hand is
    sorted so the card whose type has the highest score plays first.

    Falls back to random on any error.
    """
    import os
    import math
    import numpy as np

    cards = list(playable_cards)
    if current_state is None:
        random.shuffle(cards)
        return cards

    tag = bot_type[3:] if bot_type.startswith("rl:") else "solo_map1"
    if tag not in _rl_session_cache:
        try:
            import onnxruntime as rt
            model_dir = os.path.join(os.path.dirname(__file__), "rl_models")
            if os.sep in tag or "/" in tag:
                onnx_path = tag if tag.endswith(".onnx") else tag + ".onnx"
            else:
                onnx_path = os.path.join(model_dir, tag + ".onnx")
            _rl_session_cache[tag] = rt.InferenceSession(onnx_path)
        except Exception:
            _rl_session_cache[tag] = None

    sess = _rl_session_cache.get(tag)
    if sess is None:
        random.shuffle(cards)
        return cards

    try:
        from pigame.rl_env import (encode_card, build_tile_feature_array,
                                    ego_crop_flat, _CARD_ID_TO_IDX,
                                    N_CARD_TYPES, N_CROP_FEATS, CARD_FEATURES)
        from pigame.models import card_id_rank

        p = current_state
        max_health = ncardsavail + 3   # FREE_HEALTH_OFFSET = 3

        if map_data is not None:
            map_w = map_data.get("width", 25)
            map_h = map_data.get("height", 20)
        else:
            map_w, map_h = 25, 20
        map_diag = math.sqrt(map_w ** 2 + map_h ** 2)

        n_cps = len(checkpoints) if checkpoints else 1
        next_cp = min(p.next_checkpoint, n_cps)
        if checkpoints and next_cp in checkpoints:
            cp_x, cp_y = checkpoints[next_cp]
        else:
            cp_x, cp_y = p.xpos, p.ypos

        angle = p.direction * math.pi / 2
        state = np.array([
            p.xpos / map_w * 2.0 - 1.0,
            p.ypos / map_h * 2.0 - 1.0,
            math.sin(angle),
            math.cos(angle),
            p.health / max_health * 2.0 - 1.0,
            (p.next_checkpoint - 1) / max(1, n_cps),
            (cp_x - p.xpos) / map_diag,
            (cp_y - p.ypos) / map_diag,
            0.0,   # round fraction unknown at inference time
        ], dtype=np.float32)

        card_vecs = np.concatenate([encode_card(c) for c in playable_cards])

        # Tile feature array — cached per map_data object
        if map_data is not None and id(map_data) not in _rl_map_enc_cache:
            _rl_map_enc_cache[id(map_data)] = build_tile_feature_array(map_data)
        tile_arr = _rl_map_enc_cache.get(id(map_data))

        crop = (ego_crop_flat(tile_arr, p.xpos, p.ypos, map_w, map_h)
                if tile_arr is not None
                else np.zeros(N_CROP_FEATS, dtype=np.float32))

        # Infer how many opponent slots the model expects:
        # obs_dim = n_scalar + N_CROP_FEATS
        # n_scalar = 9 + ncardslots*CARD_FEATURES + n_opp_slots*8
        model_obs_dim = sess.get_inputs()[0].shape[1] or (9 + len(playable_cards) * CARD_FEATURES + N_CROP_FEATS)
        n_base = 9 + len(playable_cards) * CARD_FEATURES
        n_opp_slots = max(0, (model_obs_dim - N_CROP_FEATS - n_base) // 8)

        opp_block = np.zeros(n_opp_slots * 8, dtype=np.float32)
        if n_opp_slots > 0 and opponent_states:
            for i, opp in enumerate(opponent_states[:n_opp_slots]):
                ocp_idx = min(opp.next_checkpoint, n_cps)
                ocx, ocy = (checkpoints.get(ocp_idx, (opp.xpos, opp.ypos))
                            if checkpoints else (opp.xpos, opp.ypos))
                oang = opp.direction * math.pi / 2
                b = i * 8
                opp_block[b+0] = opp.xpos / map_w * 2.0 - 1.0
                opp_block[b+1] = opp.ypos / map_h * 2.0 - 1.0
                opp_block[b+2] = math.sin(oang)
                opp_block[b+3] = math.cos(oang)
                opp_block[b+4] = opp.health / max_health * 2.0 - 1.0
                opp_block[b+5] = (opp.next_checkpoint - 1) / max(1, n_cps)
                opp_block[b+6] = (ocx - opp.xpos) / map_diag
                opp_block[b+7] = (ocy - opp.ypos) / map_diag

        # layout matches PirateEnv._build_obs: [scalar prefix | crop suffix]
        obs = np.concatenate([state, card_vecs, opp_block, crop]).reshape(1, -1)

        type_scores = sess.run(["action_mean"], {"obs": obs})[0].flatten()

        def _sort_key(card_val):
            cid, rank = card_id_rank(card_val)
            tidx = _CARD_ID_TO_IDX.get(cid, N_CARD_TYPES - 1)
            return (-float(type_scores[tidx]), -rank)

        return sorted(cards, key=_sort_key)
    except Exception:
        random.shuffle(cards)
        return cards


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
    map_data = None
    opponent_states = None
    if bot_type in ("greedy", "rl") or bot_type.startswith("rl:"):
        if player_states and player_id in player_states:
            try:
                map_data = load_map(gamecfg.mapfile)
                checkpoints = determine_checkpoint_locations(map_data)
                current_state = player_states[player_id]
                opponent_states = [
                    st for pid, st in player_states.items() if pid != player_id
                ]
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
        map_data=map_data,
        opponent_states=opponent_states,
    )
    deck[next_card : next_card + ncardsavail] = best_playable + remainder
    set_player_deck(gamecfg, player_id, deck)
