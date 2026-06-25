"""
PirateRace gymnasium environment for RL training.

Supports solo and multiplayer (with bot opponents) via the `opponent_types`
parameter.  Use `max_opponents` to fix the observation size across curriculum
stages so weights can be transferred between solo and multi-player training.

Observation (flat float32, total = 9 + ncardsavail×14 + max_opponents×8):
    player_state  (9)                x_norm, y_norm, sin(dir), cos(dir),
                                     health_norm, cp_progress, dx_to_cp,
                                     dy_to_cp, round_norm
    per card      (ncardsavail × 13) one-hot card type (12) + rank_norm
    path_preview  (ncardsavail)      per-card distance improvement to current
                                     checkpoint when played solo as slot-1,
                                     normalised by map diagonal.  Positive =
                                     moves toward checkpoint.
    per opp slot  (max_opponents×8)  x_norm, y_norm, sin/cos(dir), health_norm,
                                     cp_progress, dx_to_their_cp, dy_to_their_cp
                                     (zero-padded when no opponent in that slot)

No egocentric crop: path_preview already encodes spatial card effects.
Removing the 3969-feature CNN crop speeds up training ~15× and makes a
simple flat MLP sufficient (no custom CNN extractor needed).

obs_dim is map-independent — the same trained model works on any map.

Action (float32, shape = (ncardsavail,)):
    Priority score per card in the full available hand.  The ncardslots cards
    with the highest scores are selected and played in score order (highest
    first).  Only relative order matters.

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

# Cannon direction cards use their raw card_val (-10 … -13) as dict key —
# they are NOT stored as id*NRANKINGS+rank like movement cards.
_CANNON_VALS = frozenset({-10, -11, -12, -13})

_CARD_ID_TO_IDX: Dict[int, int] = {
    1: 0, 2: 1, 3: 2,           # rotate-left, backup, u-turn
    10: 3, 20: 4, 30: 5, 40: 6, # rotate-right, fwd1, fwd2, fwd3
    100: 7,                      # repair
    -10: 8, -11: 9, -12: 10, -13: 11,  # cannon fwd/right/back/left
}
N_CARD_TYPES = 12
CARD_FEATURES = N_CARD_TYPES + 1   # one-hot type (12) + normalised rank


def encode_card(card_val: int) -> np.ndarray:
    """Return a CARD_FEATURES-dim float32 vector for one card."""
    vec = np.zeros(CARD_FEATURES, dtype=np.float32)
    if card_val in _CANNON_VALS:
        # Cannon direction cards have no rank — keyed by raw card_val
        vec[_CARD_ID_TO_IDX[card_val]] = 1.0
    else:
        card_id, rank = card_id_rank(card_val)
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
    out[:, :, 1] = 1.0  # default: void (OOB = deadly zone, not wall)

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

AGGRESSIVE_WEIGHTS = RewardWeights(
    distance=0.5,        # still navigate toward CPs
    checkpoint=3.0,      # still care about reaching CPs
    win=10.0,
    damage_taken=-0.2,   # light self-damage penalty (tanks hits)
    time=-0.005,
    win_race=5.0,
    lose_race=-1.0,      # mild lose penalty — damage is its own reward
    lead_bonus=0.1,
    damage_dealt=3.0,    # strong reward for hitting opponent
    push_opp=1.5,        # reward for pushing opponent off course
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
        max_ncardsavail: Optional[int] = None,
        max_rounds: int = 60,
        pct_repair: int = 0,
        pct_cannon: int = 0,
        weights: Optional[RewardWeights] = None,
        opponent_types: Optional[List[str]] = None,
        max_opponents: int = 0,
        _map_data=None,
        mapfiles: Optional[List[str]] = None,
        ncardsavail_options: Optional[List[int]] = None,
    ):
        if not HAS_GYM:
            raise ImportError("Install gymnasium: pip install gymnasium")

        super().__init__()
        self.mapfile = mapfile
        self.ncardslots = ncardslots
        self.ncardsavail = ncardsavail
        # max_ncardsavail fixes obs/action size so the same model can handle
        # any number of available cards (≤ max_ncardsavail) via zero-padding.
        # Defaults to the max of ncardsavail_options (or ncardsavail) when not set.
        self._ncardsavail_options: List[int] = list(ncardsavail_options or [ncardsavail])
        self.max_ncardsavail = max_ncardsavail if max_ncardsavail is not None else max(self._ncardsavail_options)
        self.max_rounds = max_rounds
        self.pct_repair = pct_repair
        self.pct_cannon = pct_cannon
        self.weights = weights if weights is not None else RewardWeights()
        self.opponent_types: List[str] = list(opponent_types or [])
        # max_opponents fixes the obs size across curriculum stages.
        # Must be >= len(opponent_types); defaults to len(opponent_types).
        self.max_opponents = max(max_opponents, len(self.opponent_types))

        # Pre-cache all maps so reset() can switch without filesystem I/O.
        self._all_mapfiles: List[str] = list(mapfiles or [mapfile])
        self._map_cache: Dict[str, dict] = {}
        for mf in self._all_mapfiles:
            if mf == mapfile and _map_data is not None:
                self._map_cache[mf] = copy.deepcopy(_map_data)
            else:
                self._map_cache[mf] = copy.deepcopy(load_map(mf))

        # Initialise with the first map (reset() will randomise)
        self._load_map(self._all_mapfiles[0])

        # obs = state(9) + cards(max_ncardsavail×CARD_FEATURES) + preview(max_ncardsavail)
        #       + opp(max_opponents×8)
        # Slots beyond ncardsavail are zero-padded so obs/action size stays fixed
        # regardless of how many cards are actually in hand this game.
        self.n_scalar = 9 + self.max_ncardsavail * CARD_FEATURES + self.max_ncardsavail + self.max_opponents * 8
        obs_dim = self.n_scalar
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(obs_dim,), dtype=np.float32
        )
        # Action: ncardslots integer indices into the ncardsavail-card hand,
        # in play order (index 0 plays first).  Produced by the autoregressive
        # pointer network.  MultiDiscrete so the rollout buffer stores them as
        # (ncardslots,) int — compatible with teacher-forcing evaluate_actions().
        self.action_space = spaces.MultiDiscrete(
            [self.max_ncardsavail] * self.ncardslots
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

    def _load_map(self, mapfile: str) -> None:
        """Load (from cache) and set all map-derived attributes."""
        raw = self._map_cache[mapfile]
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

    def _cp_xy(self, player) -> Tuple[float, float]:
        cp_idx = min(player.next_checkpoint, self._n_checkpoints)
        return self._checkpoints.get(cp_idx, (player.xpos, player.ypos))

    def _dist_to_cp(self, player) -> float:
        cx, cy = self._cp_xy(player)
        return math.sqrt((player.xpos - cx) ** 2 + (player.ypos - cy) ** 2)

    def _total_remaining_dist(self, player) -> float:
        """Sum of straight-line distances along the remaining checkpoint path.

        dist(pos → cp_k) + dist(cp_k → cp_{k+1}) + ... + dist(cp_{n-1} → cp_n)

        This removes the jump discontinuity in the distance-based reward: when a
        checkpoint is reached, curr_dist drops by exactly the distance covered to
        get there, so (prev_dist - curr_dist) is always a smooth progress signal.
        """
        cp_idx = player.next_checkpoint
        if cp_idx > self._n_checkpoints:
            return 0.0
        x, y = player.xpos, player.ypos
        total = 0.0
        for i in range(cp_idx, self._n_checkpoints + 1):
            cx, cy = self._checkpoints.get(i, (x, y))
            total += math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            x, y = cx, cy
        return total

    def _opp_obs_block(self) -> np.ndarray:
        block = np.zeros(self.max_opponents * 8, dtype=np.float32)
        max_h = self.max_ncardsavail + FREE_HEALTH_OFFSET  # fixed normaliser across variable nca
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

    def _card_preview(self, hand: list, cp_x: float, cp_y: float) -> np.ndarray:
        """Return (ncardslots,) distance-improvement per card played solo as slot-1.
        preview[i] = (dist_before - dist_after_card_i) / map_diag, normalised.
        Positive = card moves toward the current checkpoint.
        """
        p = self._player
        dist_before = math.sqrt((p.xpos - cp_x) ** 2 + (p.ypos - cp_y) ** 2)
        preview = np.zeros(len(hand), dtype=np.float32)
        for i, card in enumerate(hand):
            sim_p = types.SimpleNamespace(
                id=p.id, xpos=p.xpos, ypos=p.ypos,
                direction=p.direction, health=p.health,
                next_checkpoint=p.next_checkpoint,
                last_cp_x=p.last_cp_x, last_cp_y=p.last_cp_y,
                cannon_direction=p.cannon_direction, powered_down=False,
                color=p.color, name=p.name,
            )
            sim_cards = [p.id, card, BACKEND_USERID, ROUNDEND_CARDID]
            try:
                play_one_round({p.id: sim_p}, self._map_data, sim_cards, self.ncardsavail)
            except Exception:
                pass
            dist_after = math.sqrt((sim_p.xpos - cp_x) ** 2 + (sim_p.ypos - cp_y) ** 2)
            preview[i] = (dist_before - dist_after) / self._map_diag
        return preview

    def _build_obs(self) -> np.ndarray:
        p = self._player
        cx, cy = self._cp_xy(p)
        angle = p.direction * math.pi / 2
        max_health = self.max_ncardsavail + FREE_HEALTH_OFFSET  # fixed normaliser

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

        hand = self._deck[self._next_card : self._next_card + self.ncardsavail]
        cards = np.concatenate([encode_card(c) for c in hand])
        preview = self._card_preview(hand, cx, cy)

        # Zero-pad card features and preview to max_ncardsavail
        pad = self.max_ncardsavail - self.ncardsavail
        if pad > 0:
            cards = np.concatenate([cards, np.zeros(pad * CARD_FEATURES, dtype=np.float32)])
            preview = np.concatenate([preview, np.zeros(pad, dtype=np.float32)])

        return np.concatenate([state, cards, preview, self._opp_obs_block()])

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

        # Randomise map and hand size for this episode (curriculum / multi-map).
        if len(self._all_mapfiles) > 1:
            self._load_map(random.choice(self._all_mapfiles))
        if len(self._ncardsavail_options) > 1:
            self.ncardsavail = random.choice(self._ncardsavail_options)

        # Shuffle a copy so self._map_data is never mutated.
        positions = list(self._start_positions)
        random.shuffle(positions)

        def _pos(i):
            p = positions[i % len(positions)]
            return int(p["x"] / self._tile_w), int(p["y"] / self._tile_h)

        sx, sy = _pos(0)
        sd = random.randint(0, 3)
        self._player = self._make_player(-1, sx, sy, sd, "#4488CC", "rl")
        self._deck = _make_deck(self.pct_repair, self.pct_cannon)
        self._next_card = 0
        self._round = 0
        self._prev_dist = self._total_remaining_dist(self._player)

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
            self._opp_decks.append(_make_deck(self.pct_repair, self.pct_cannon))
            self._opp_next_cards.append(0)

        return self._build_obs(), {}

    def step(self, action: np.ndarray):
        from pigame.bots import pick_cards  # lazy import to avoid circular dep

        w = self.weights
        p = self._player
        pid = p.id

        # Decode action: (ncardslots,) integer indices into the ncardsavail-card
        # hand, in play order.  Produced by the pointer network (or converted
        # from float32 via rounding for legacy compat).
        hand = self._deck[self._next_card : self._next_card + self.ncardsavail]
        raw  = np.asarray(action, dtype=np.float64)[:self.ncardslots]
        indices = [int(round(float(v))) for v in raw]
        # Clamp to valid range and deduplicate (pointer network should not repeat,
        # but this guards against numerical noise at inference time).
        selected_idx = []
        used: set = set()
        for idx in indices:
            idx = max(0, min(idx, self.ncardsavail - 1))
            if idx not in used:
                selected_idx.append(idx)
                used.add(idx)
        # Fill any missing slots with the first unused card
        for i in range(self.ncardsavail):
            if len(selected_idx) >= self.ncardslots:
                break
            if i not in used:
                selected_idx.append(i)
                used.add(i)
        played = [hand[i] for i in selected_idx[:self.ncardslots]]

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
        opp_prev_health = {oid: o.health for oid, o in self._opponents.items()}
        opp_prev_dist  = {oid: self._dist_to_cp(o) for oid, o in self._opponents.items()}

        all_players = {pid: p, **self._opponents}
        game_over = play_one_round(all_players, self._map_data, round_cards, self.ncardsavail)

        selected_set = set(selected_idx[:self.ncardslots])
        remainder    = [hand[i] for i in range(self.ncardsavail) if i not in selected_set]
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
        curr_dist = self._total_remaining_dist(p)
        self._prev_dist = curr_dist

        # ── reward ────────────────────────────────────────────────────────────
        # prev_dist and curr_dist are total remaining path lengths (sum of all
        # remaining checkpoint distances), so (prev_dist - curr_dist) is always
        # a smooth progress signal with no jump when a checkpoint is reached.
        reward = 0.0
        reward += w.distance * (prev_dist - curr_dist)
        reward += w.time

        cps_gained = p.next_checkpoint - prev_cp
        if cps_gained > 0:
            reward += w.checkpoint * cps_gained

        health_lost = prev_health - p.health
        if health_lost > 0:
            reward += w.damage_taken * health_lost

        # Damage dealt and push opponent off course
        for oid, opp in self._opponents.items():
            dmg = opp_prev_health[oid] - opp.health
            if dmg > 0:
                reward += w.damage_dealt * dmg
            new_opp_dist = self._dist_to_cp(opp)
            push = new_opp_dist - opp_prev_dist[oid]
            if push > 0:
                reward += w.push_opp * push

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
