"""
PirateRace gymnasium environment for RL training.

Supports solo and multiplayer (with bot opponents) via the `opponent_types`
parameter.  Use `max_opponents` to fix the observation size across curriculum
stages so weights can be transferred between solo and multi-player training.

Observation (flat float32):
    player_state  (9)               x_norm, y_norm, sin(dir), cos(dir),
                                    health_norm, cp_progress, dx_to_cp,
                                    dy_to_cp, round_norm
    per card      (ncardslots × 9)  one-hot card type (8) + rank_norm
    per opp slot  (max_opponents×8) x_norm, y_norm, sin/cos(dir), health_norm,
                                    cp_progress, dx_to_their_cp, dy_to_their_cp
                                    (zero-padded when no opponent in that slot)
    ego-centric crop  (CROP_SIZE × CROP_SIZE × N_TILE_PROPS)
                                    CROP_SIZE×CROP_SIZE tile window centred on
                                    the agent, encoded as N_TILE_PROPS floats
                                    per tile.  Out-of-bounds tiles filled with
                                    collision=1.  Layout is (row, col, channel)
                                    i.e. spatial → CNN-friendly.

The scalar prefix (state + cards + opp) is followed by the spatial suffix
(crop) so the features extractor can split at index n_scalar.

obs_dim is map-independent — the same trained model works on any map.

Action (float32, shape = (N_CARD_TYPES,) = (8,)):
    Preference score per card type.  The hand is sorted so the card whose
    type has the highest preference score plays first; ties broken by rank.

Install deps before use:
    pip install gymnasium stable-baselines3
"""

import copy
import math
import random
import types
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import gymnasium as gym
    from gymnasium import spaces
    HAS_GYM = True
except ImportError:
    HAS_GYM = False

from pigame.bot_eval import _advance_deck, _make_deck
from pigame.game_logic import (
    BACKEND_USERID,
    ROUNDEND_CARDID,
    argsort,
    card_id_rank,
    determine_checkpoint_locations,
    determine_starting_locations,
    get_tile_properties,
    load_map,
    play_one_round,
)
from pigame.models import (
    CANNON_DIRECTION,
    FREE_HEALTH_OFFSET,
    NRANKINGS,
    card_id_rank,
)


# ── card feature encoding ─────────────────────────────────────────────────────

_CARD_ID_TO_IDX: Dict[int, int] = {1: 0, 2: 1, 3: 2, 10: 3, 20: 4, 30: 5, 40: 6, 100: 7}
N_CARD_TYPES = 8
CARD_FEATURES = N_CARD_TYPES + 1   # one-hot type + normalised rank


def encode_card(card_val: int) -> np.ndarray:
    """Return a CARD_FEATURES-dim float32 vector for one card."""
    card_id, rank = card_id_rank(card_val)
    vec = np.zeros(CARD_FEATURES, dtype=np.float32)
    vec[_CARD_ID_TO_IDX.get(card_id, N_CARD_TYPES - 1)] = 1.0
    vec[N_CARD_TYPES] = rank / NRANKINGS
    return vec


# ── map tile encoding ─────────────────────────────────────────────────────────

N_TILE_PROPS = 9  # number of floats per tile in the encoded representation

# Ego-centric crop window size (odd so agent is exactly at centre).
# 21×21 covers 10 tiles in every direction — enough for 5×fwd3 look-ahead.
CROP_SIZE = 21
CROP_HALF = CROP_SIZE // 2  # 10
N_CROP_FEATS = CROP_SIZE * CROP_SIZE * N_TILE_PROPS  # 3969


def _encode_tile(prop) -> np.ndarray:
    """9-float feature vector for one tile property dict."""
    return np.array([
        float(prop["collision"]),
        float(prop["void"]),
        float(prop["current_x"]),
        float(prop["current_y"]),
        float(prop["vortex"]) * 0.5,
        float(prop["damage"]),
        float(prop["turret_x"]),
        float(prop["turret_y"]),
        float(prop.get("fast_current", False)),
    ], dtype=np.float32)


def build_tile_feature_array(gmap) -> np.ndarray:
    """
    Precompute an (W, H, N_TILE_PROPS) float32 array for O(1) crop extraction.
    Indexed as [x, y, channel] — same convention as get_tile_properties(gmap, x, y).
    """
    w, h = gmap["width"], gmap["height"]
    arr = np.zeros((w, h, N_TILE_PROPS), dtype=np.float32)
    for xi in range(w):
        for yi in range(h):
            arr[xi, yi] = _encode_tile(get_tile_properties(gmap, xi, yi))
    return arr


def ego_crop_flat(tile_arr: np.ndarray, px: int, py: int,
                  map_w: int, map_h: int) -> np.ndarray:
    """
    Return a flat float32 array of shape (N_CROP_FEATS,) — the CROP_SIZE×CROP_SIZE
    tile window centred on (px, py).  Out-of-bounds tiles have collision=1.

    Layout: crop[row, col, channel] → flattened row-major.
    row increases with +y (downward), col increases with +x (rightward).
    """
    out = np.zeros((CROP_SIZE, CROP_SIZE, N_TILE_PROPS), dtype=np.float32)
    out[:, :, 0] = 1.0  # default: wall / collision

    # Map crop rows (dy ∈ [-CROP_HALF, CROP_HALF]) to y coords
    y0_map = py - CROP_HALF
    x0_map = px - CROP_HALF

    # Clamp to valid map range
    xi_lo = max(0, x0_map)
    xi_hi = min(map_w, x0_map + CROP_SIZE)
    yi_lo = max(0, y0_map)
    yi_hi = min(map_h, y0_map + CROP_SIZE)

    if xi_lo < xi_hi and yi_lo < yi_hi:
        # Crop output indices
        col_lo = xi_lo - x0_map
        col_hi = col_lo + (xi_hi - xi_lo)
        row_lo = yi_lo - y0_map
        row_hi = row_lo + (yi_hi - yi_lo)
        # tile_arr[xi, yi] → crop[row=yi-y0_map, col=xi-x0_map]
        # Use transpose: tile_arr[xi_lo:xi_hi, yi_lo:yi_hi] has shape (Dx, Dy, C)
        # We need (Dy, Dx, C) = (row, col, C), so transpose axes 0 and 1.
        out[row_lo:row_hi, col_lo:col_hi] = tile_arr[xi_lo:xi_hi, yi_lo:yi_hi].transpose(1, 0, 2)

    return out.flatten()


# ── reward weights ─────────────────────────────────────────────────────────────

@dataclass
class RewardWeights:
    """
    Swap these to shape bot personality without touching the env code.

    Solo weights   → pure racing, no opponent awareness.
    Race weights   → competitive racing; rewards beating opponents.
    Impulsive      → values damage/push over winning (fun to play against).
    """
    distance: float = 1.0      # reward per tile moved closer to next CP
    checkpoint: float = 5.0    # flat reward per checkpoint reached
    win: float = 20.0          # flat reward for clearing all checkpoints
    damage_taken: float = -0.5 # per health-point lost (self-damage)
    time: float = -0.01        # per round (encourages speed)
    # Multiplayer competitive:
    win_race: float = 0.0      # extra bonus for finishing before all opponents
    lose_race: float = 0.0     # penalty when an opponent finishes first
    lead_bonus: float = 0.0    # per checkpoint the agent is ahead of each opponent
    # Impulsive / aggressive:
    damage_dealt: float = 0.0  # per health-point dealt to any opponent
    push_opp: float = 0.0      # per tile an opponent was pushed off-course


SOLO_WEIGHTS = RewardWeights()

RACE_WEIGHTS = RewardWeights(
    distance=1.0,
    checkpoint=5.0,
    win=20.0,
    damage_taken=-0.5,
    time=-0.01,
    win_race=10.0,
    lose_race=-5.0,
    lead_bonus=0.3,
)

IMPULSIVE_WEIGHTS = RewardWeights(
    distance=0.4,
    checkpoint=3.0,
    win=10.0,
    damage_taken=-0.3,
    time=-0.005,
    win_race=5.0,
    lose_race=-2.0,
    damage_dealt=3.0,
    push_opp=1.5,
)


# ── environment ────────────────────────────────────────────────────────────────

class PirateEnv(gym.Env if HAS_GYM else object):
    """
    Gymnasium-compatible PirateRace environment.

    Solo (default):
        env = PirateEnv("map1.json")

    Multiplayer — train against a random bot:
        env = PirateEnv("map1.json", opponent_types=["random"], max_opponents=1)

    Curriculum — fix max_opponents=1 across all stages so obs shape stays
    constant and weights can be resumed between stages:
        stage1 = PirateEnv(..., opponent_types=[],         max_opponents=1)
        stage2 = PirateEnv(..., opponent_types=["random"], max_opponents=1)
        stage3 = PirateEnv(..., opponent_types=["greedy"], max_opponents=1)
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        mapfile: str = "map1.json",
        ncardslots: int = 5,
        ncardsavail: int = 9,
        max_rounds: int = 60,
        pct_repair: int = 0,
        weights: Optional[RewardWeights] = None,
        opponent_types: Optional[List[str]] = None,
        max_opponents: int = 0,
        _map_data=None,
    ):
        if not HAS_GYM:
            raise ImportError("Install gymnasium: pip install gymnasium")

        super().__init__()
        self.mapfile = mapfile
        self.ncardslots = ncardslots
        self.ncardsavail = ncardsavail
        self.max_rounds = max_rounds
        self.pct_repair = pct_repair
        self.weights = weights if weights is not None else RewardWeights()
        self.opponent_types: List[str] = list(opponent_types or [])
        # max_opponents fixes the obs size across curriculum stages.
        # Must be >= len(opponent_types); defaults to len(opponent_types).
        self.max_opponents = max(max_opponents, len(self.opponent_types))

        raw = _map_data if _map_data is not None else load_map(mapfile)
        self._map_data = copy.deepcopy(raw)
        self._checkpoints = determine_checkpoint_locations(self._map_data)
        self._n_checkpoints = len(self._checkpoints)
        self._map_w = self._map_data["width"]
        self._map_h = self._map_data["height"]
        self._map_diag = math.sqrt(self._map_w ** 2 + self._map_h ** 2)
        self._start_positions = [
            layer["objects"]
            for layer in self._map_data["layers"]
            if layer["name"] == "startinglocs"
        ][0]
        self._tile_w = self._map_data["tilewidth"]
        self._tile_h = self._map_data["tileheight"]

        # Precompute (W, H, N_TILE_PROPS) array for O(1) crop extraction
        self._tile_arr: np.ndarray = build_tile_feature_array(self._map_data)

        # obs layout: [scalar prefix] + [ego crop suffix]
        # scalar = state(9) + cards(ncardslots×CARD_FEATURES) + opp(max_opponents×8)
        # crop  = CROP_SIZE×CROP_SIZE×N_TILE_PROPS  (map-independent size)
        self.n_scalar = 9 + ncardslots * CARD_FEATURES + self.max_opponents * 8
        obs_dim = self.n_scalar + N_CROP_FEATS
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
        )
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(N_CARD_TYPES,), dtype=np.float32
        )

        # Runtime state — populated by reset()
        self._player: Optional[object] = None
        self._opponents: Dict[int, object] = {}
        self._opp_decks: List[List[int]] = []
        self._opp_next_cards: List[int] = []
        self._deck: List[int] = []
        self._next_card: int = 0
        self._round: int = 0
        self._prev_dist: float = 0.0

    # ── helpers ────────────────────────────────────────────────────────────────

    def _cp_xy(self, player) -> Tuple[float, float]:
        cp_idx = min(player.next_checkpoint, self._n_checkpoints)
        return self._checkpoints.get(cp_idx, (player.xpos, player.ypos))

    def _dist_to_cp(self, player) -> float:
        cx, cy = self._cp_xy(player)
        return math.sqrt((player.xpos - cx) ** 2 + (player.ypos - cy) ** 2)

    def _opp_obs_block(self) -> np.ndarray:
        block = np.zeros(self.max_opponents * 8, dtype=np.float32)
        max_h = self.ncardsavail + FREE_HEALTH_OFFSET
        for i, opp in enumerate(self._opponents.values()):
            if i >= self.max_opponents:
                break
            cx, cy = self._cp_xy(opp)
            ang = opp.direction * math.pi / 2
            b = i * 8
            block[b + 0] = opp.xpos / self._map_w * 2.0 - 1.0
            block[b + 1] = opp.ypos / self._map_h * 2.0 - 1.0
            block[b + 2] = math.sin(ang)
            block[b + 3] = math.cos(ang)
            block[b + 4] = opp.health / max_h * 2.0 - 1.0
            block[b + 5] = (opp.next_checkpoint - 1) / max(1, self._n_checkpoints)
            block[b + 6] = (cx - opp.xpos) / self._map_diag
            block[b + 7] = (cy - opp.ypos) / self._map_diag
        return block

    def _build_obs(self) -> np.ndarray:
        p = self._player
        cx, cy = self._cp_xy(p)
        angle = p.direction * math.pi / 2
        max_health = self.ncardsavail + FREE_HEALTH_OFFSET

        state = np.array([
            p.xpos / self._map_w * 2.0 - 1.0,
            p.ypos / self._map_h * 2.0 - 1.0,
            math.sin(angle),
            math.cos(angle),
            p.health / max_health * 2.0 - 1.0,
            (p.next_checkpoint - 1) / max(1, self._n_checkpoints),
            (cx - p.xpos) / self._map_diag,
            (cy - p.ypos) / self._map_diag,
            self._round / self.max_rounds,
        ], dtype=np.float32)

        hand = self._deck[self._next_card : self._next_card + self.ncardslots]
        cards = np.concatenate([encode_card(c) for c in hand])
        crop = ego_crop_flat(self._tile_arr, p.xpos, p.ypos, self._map_w, self._map_h)

        # layout: scalar prefix then spatial suffix (CNN extractor splits here)
        return np.concatenate([state, cards, self._opp_obs_block(), crop])

    def _make_player(self, pid, sx, sy, sd, color, name):
        max_health = self.ncardsavail + FREE_HEALTH_OFFSET
        return types.SimpleNamespace(
            id=pid, xpos=sx, ypos=sy,
            last_cp_x=sx, last_cp_y=sy,
            direction=sd,
            cannon_direction=CANNON_DIRECTION.FORWARD,
            next_checkpoint=1,
            health=max_health,
            powered_down=False,
            color=color, name=name,
        )

    # ── gymnasium API ──────────────────────────────────────────────────────────

    def reset(self, *, seed: Optional[int] = None, options=None):
        super().reset(seed=seed)
        if seed is not None:
            random.seed(seed)

        # Shuffle a copy so self._map_data is never mutated.
        positions = list(self._start_positions)
        random.shuffle(positions)

        def _pos(i):
            p = positions[i % len(positions)]
            return int(p["x"] / self._tile_w), int(p["y"] / self._tile_h)

        sx, sy = _pos(0)
        sd = random.randint(0, 3)
        self._player = self._make_player(-1, sx, sy, sd, "#4488CC", "rl")
        self._deck = _make_deck(self.pct_repair)
        self._next_card = 0
        self._round = 0
        self._prev_dist = self._dist_to_cp(self._player)

        self._opponents = {}
        self._opp_decks = []
        self._opp_next_cards = []
        opp_colors = ["#CC4444", "#44CC44", "#CC44CC"]
        for i, opp_type in enumerate(self.opponent_types):
            osx, osy = _pos(i + 1)
            osd = random.randint(0, 3)
            opp_pid = -(i + 2)
            self._opponents[opp_pid] = self._make_player(
                opp_pid, osx, osy, osd,
                opp_colors[i % len(opp_colors)], f"{opp_type}_{i}"
            )
            self._opp_decks.append(_make_deck(self.pct_repair))
            self._opp_next_cards.append(0)

        return self._build_obs(), {}

    def step(self, action: np.ndarray):
        from pigame.bots import pick_cards  # lazy import to avoid circular dep

        w = self.weights
        p = self._player
        pid = p.id

        # Decode action: type preference scores → sort hand
        hand = self._deck[self._next_card : self._next_card + self.ncardslots]
        type_scores = np.asarray(action, dtype=np.float32)

        def _sort_key(card_val):
            cid, rank = card_id_rank(card_val)
            tidx = _CARD_ID_TO_IDX.get(cid, N_CARD_TYPES - 1)
            return (-float(type_scores[tidx]), -rank)

        played = sorted(hand, key=_sort_key)

        # Opponent card selection
        opp_played: Dict[int, List[int]] = {}
        for i, (opp_pid, opp_type) in enumerate(zip(self._opponents.keys(), self.opponent_types)):
            opp = self._opponents[opp_pid]
            opp_hand = self._opp_decks[i][
                self._opp_next_cards[i] : self._opp_next_cards[i] + self.ncardslots
            ]
            opp_played[opp_pid] = pick_cards(
                opp_type, opp_hand,
                current_state=opp,
                checkpoints=self._checkpoints,
                ncardsavail=self.ncardsavail,
                map_data=self._map_data,
            )

        # Interleave by slot, highest rank plays first within each slot
        all_pids = [pid] + list(self._opponents.keys())
        all_played = {pid: played, **opp_played}

        round_cards: List[int] = []
        for slot in range(self.ncardslots):
            slot_entries = [(p_id, all_played[p_id][slot]) for p_id in all_pids]
            ranks = [card_id_rank(c)[1] for _, c in slot_entries]
            for j in argsort(ranks)[::-1]:
                p_id, card = slot_entries[j]
                round_cards.extend([p_id, card])
        round_cards.extend([BACKEND_USERID, ROUNDEND_CARDID])

        prev_cp = p.next_checkpoint
        prev_health = p.health
        prev_dist = self._prev_dist
        opp_prev_cps = {oid: o.next_checkpoint for oid, o in self._opponents.items()}

        all_players = {pid: p, **self._opponents}
        game_over = play_one_round(all_players, self._map_data, round_cards, self.ncardsavail)

        # Write played cards back into agent deck then advance pointer
        remainder = self._deck[self._next_card + self.ncardslots : self._next_card + self.ncardsavail]
        self._deck[self._next_card : self._next_card + self.ncardsavail] = played + remainder
        self._deck, self._next_card = _advance_deck(
            self._deck, self._next_card, self.ncardslots, self.ncardsavail
        )

        # Advance opponent deck pointers
        for i, opp_pid in enumerate(self._opponents.keys()):
            opp_hand_full = self._opp_decks[i][
                self._opp_next_cards[i] : self._opp_next_cards[i] + self.ncardsavail
            ]
            opp_rem = opp_hand_full[self.ncardslots:]
            self._opp_decks[i][
                self._opp_next_cards[i] : self._opp_next_cards[i] + self.ncardsavail
            ] = opp_played[opp_pid] + opp_rem
            self._opp_decks[i], self._opp_next_cards[i] = _advance_deck(
                self._opp_decks[i], self._opp_next_cards[i], self.ncardslots, self.ncardsavail
            )

        self._round += 1
        curr_dist = self._dist_to_cp(p)
        self._prev_dist = curr_dist

        # ── reward ────────────────────────────────────────────────────────────
        reward = 0.0
        reward += w.distance * (prev_dist - curr_dist)
        reward += w.time

        cps_gained = p.next_checkpoint - prev_cp
        if cps_gained > 0:
            reward += w.checkpoint * cps_gained

        health_lost = prev_health - p.health
        if health_lost > 0:
            reward += w.damage_taken * health_lost

        # Lead bonus: checkpoint lead over each opponent
        if w.lead_bonus != 0.0 and self._opponents:
            for opp in self._opponents.values():
                lead = (p.next_checkpoint - 1) - (opp.next_checkpoint - 1)
                reward += w.lead_bonus * lead

        # Race outcome
        agent_done = p.next_checkpoint > self._n_checkpoints
        opp_done = any(o.next_checkpoint > self._n_checkpoints for o in self._opponents.values())

        terminated = False
        if game_over:
            if agent_done:
                reward += w.win
                if self._opponents:
                    reward += w.win_race
            elif opp_done:
                reward += w.lose_race
            terminated = True

        truncated = self._round >= self.max_rounds

        info = {
            "round": self._round,
            "checkpoints": p.next_checkpoint - 1,
            "health": p.health,
            "dist_to_cp": curr_dist,
            "won": agent_done,
        }
        return self._build_obs(), float(reward), terminated, truncated, info
