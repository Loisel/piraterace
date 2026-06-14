"""
PirateRace gymnasium environment for RL training.

Single-player (solo) mode: one agent navigates all checkpoints.
Multiplayer will reuse the same class with n_opponents > 0.

Observation (flat float32, shape = (9 + ncardslots * 9,)):
    player_state  [x_norm, y_norm, sin(dir), cos(dir), health_norm,
                   cp_progress, dx_to_cp, dy_to_cp, round_norm]
    per card      [one-hot card type (8), rank_norm]

Action (float32, shape = (ncardslots,)):
    Logit per card slot. argsort(action) descending gives the play order
    of the cards the agent was dealt. The card with the highest logit
    is played in slot 0, lowest in slot ncardslots-1.

Install deps before use:
    pip install gymnasium stable-baselines3
"""

import copy
import math
import random
import types
from dataclasses import dataclass
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
    determine_checkpoint_locations,
    determine_starting_locations,
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

# Fixed mapping from card_id to one-hot index.
# Covers all card types in DEFAULT_DECK: fwd1/2/3, back1, rotL/R/180, repair.
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


# ── reward weights ─────────────────────────────────────────────────────────────

@dataclass
class RewardWeights:
    """
    Swap these to shape bot personality without touching the env code.

    Solo-racing weights (default) → bot focuses purely on winning fast.

    Impulsive/aggressive weights → bot values causing damage to opponents
    (push/shoot) almost as much as advancing toward checkpoints, producing
    a riskier, more entertaining playstyle even when it doesn't win.
    """
    distance: float = 1.0      # reward per tile moved closer to next CP
    checkpoint: float = 5.0    # flat reward per checkpoint reached
    win: float = 20.0          # flat reward for clearing all checkpoints
    damage_taken: float = -0.5 # per health-point lost (self-damage)
    time: float = -0.01        # per round (encourages speed)
    # Multiplayer only — ignored in solo:
    damage_dealt: float = 0.0  # per health-point dealt to any opponent
    push_opp: float = 0.0      # per tile an opponent was pushed off-course


SOLO_WEIGHTS = RewardWeights()

IMPULSIVE_WEIGHTS = RewardWeights(
    distance=0.4,
    checkpoint=3.0,
    win=10.0,
    damage_taken=-0.3,
    time=-0.005,
    damage_dealt=3.0,
    push_opp=1.5,
)


# ── environment ────────────────────────────────────────────────────────────────

class PirateEnv(gym.Env if HAS_GYM else object):
    """
    Gymnasium-compatible PirateRace environment (single-player for now).

    Usage:
        env = PirateEnv("map1.json")
        obs, info = env.reset(seed=42)
        for _ in range(1000):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                obs, info = env.reset()

    Plugs into stable-baselines3 make_vec_env:
        from stable_baselines3.common.env_util import make_vec_env
        vec_env = make_vec_env(lambda: PirateEnv("map1.json"), n_envs=8)
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

        # Load map once; reuse across all episodes (play_one_round reads, not writes).
        # deep-copy protects Redis-cached version from determine_starting_locations
        # which shuffles the startinglocs objects list in-place.
        raw = _map_data if _map_data is not None else load_map(mapfile)
        self._map_data = copy.deepcopy(raw)
        self._checkpoints = determine_checkpoint_locations(self._map_data)
        self._n_checkpoints = len(self._checkpoints)
        self._map_w = self._map_data["width"]
        self._map_h = self._map_data["height"]
        self._map_diag = math.sqrt(self._map_w ** 2 + self._map_h ** 2)
        # Store starting positions separately so reset() can shuffle a copy
        # without mutating self._map_data (which would break seed determinism).
        self._start_positions = [
            layer["objects"]
            for layer in self._map_data["layers"]
            if layer["name"] == "startinglocs"
        ][0]
        self._tile_w = self._map_data["tilewidth"]
        self._tile_h = self._map_data["tileheight"]

        # obs: 9 state floats + ncardslots card vectors
        obs_dim = 9 + ncardslots * CARD_FEATURES
        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(obs_dim,), dtype=np.float32
        )
        # action: one logit per card slot; argsort gives play order
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(ncardslots,), dtype=np.float32
        )

        # Runtime state — populated by reset()
        self._player: Optional[object] = None
        self._deck: List[int] = []
        self._next_card: int = 0
        self._round: int = 0
        self._prev_dist: float = 0.0

    # ── helpers ────────────────────────────────────────────────────────────────

    def _cp_xy(self) -> Tuple[float, float]:
        p = self._player
        cp_idx = min(p.next_checkpoint, self._n_checkpoints)
        return self._checkpoints.get(cp_idx, (p.xpos, p.ypos))

    def _dist_to_cp(self) -> float:
        p = self._player
        cx, cy = self._cp_xy()
        return math.sqrt((p.xpos - cx) ** 2 + (p.ypos - cy) ** 2)

    def _build_obs(self) -> np.ndarray:
        p = self._player
        cx, cy = self._cp_xy()
        angle = p.direction * math.pi / 2
        max_health = self.ncardsavail + FREE_HEALTH_OFFSET

        state = np.array([
            p.xpos / self._map_w * 2.0 - 1.0,                   # x ∈ [-1, 1]
            p.ypos / self._map_h * 2.0 - 1.0,                   # y
            math.sin(angle),                                      # direction (circular)
            math.cos(angle),
            p.health / max_health * 2.0 - 1.0,                  # health
            (p.next_checkpoint - 1) / max(1, self._n_checkpoints),  # cp progress [0,1]
            (cx - p.xpos) / self._map_diag,                      # dx toward cp
            (cy - p.ypos) / self._map_diag,                      # dy toward cp
            self._round / self.max_rounds,                       # time fraction [0,1]
        ], dtype=np.float32)

        hand = self._deck[self._next_card : self._next_card + self.ncardslots]
        cards = np.concatenate([encode_card(c) for c in hand])

        return np.concatenate([state, cards])

    # ── gymnasium API ──────────────────────────────────────────────────────────

    def reset(self, *, seed: Optional[int] = None, options=None):
        super().reset(seed=seed)   # sets self.np_random (required by gymnasium)
        if seed is not None:
            random.seed(seed)

        # Shuffle a copy so self._map_data is never mutated (determinism).
        positions = list(self._start_positions)
        random.shuffle(positions)
        sx = int(positions[0]["x"] / self._tile_w)
        sy = int(positions[0]["y"] / self._tile_h)
        sd = random.randint(0, 3)  # random starting direction

        pid = -1
        max_health = self.ncardsavail + FREE_HEALTH_OFFSET
        self._player = types.SimpleNamespace(
            id=pid,
            xpos=sx, ypos=sy,
            last_cp_x=sx, last_cp_y=sy,
            direction=sd,
            cannon_direction=CANNON_DIRECTION.FORWARD,
            next_checkpoint=1,
            health=max_health,
            powered_down=False,
            color="#4488CC",
            name="rl",
        )
        self._deck = _make_deck(self.pct_repair)
        self._next_card = 0
        self._round = 0
        self._prev_dist = self._dist_to_cp()

        return self._build_obs(), {}

    def step(self, action: np.ndarray):
        w = self.weights
        p = self._player
        pid = p.id

        # Decode action: argsort descending → play order for the dealt cards
        hand = self._deck[self._next_card : self._next_card + self.ncardslots]
        order = list(np.argsort(-np.asarray(action, dtype=np.float32)))
        played = [hand[i] for i in order]

        # Build flat round_cards list expected by play_one_round
        round_cards: List[int] = []
        for card in played:
            round_cards.extend([pid, card])
        round_cards.extend([BACKEND_USERID, ROUNDEND_CARDID])

        prev_cp = p.next_checkpoint
        prev_health = p.health
        prev_dist = self._prev_dist

        game_over = play_one_round(
            {pid: p}, self._map_data, round_cards, self.ncardsavail
        )

        # Write played order back into deck slot, then advance deck pointer
        remainder = self._deck[self._next_card + self.ncardslots : self._next_card + self.ncardsavail]
        self._deck[self._next_card : self._next_card + self.ncardsavail] = played + remainder
        self._deck, self._next_card = _advance_deck(
            self._deck, self._next_card, self.ncardslots, self.ncardsavail
        )

        self._round += 1
        curr_dist = self._dist_to_cp()
        self._prev_dist = curr_dist

        # Reward
        reward = 0.0
        reward += w.distance * (prev_dist - curr_dist)
        reward += w.time
        cps_gained = p.next_checkpoint - prev_cp
        if cps_gained > 0:
            reward += w.checkpoint * cps_gained
        health_lost = prev_health - p.health
        if health_lost > 0:
            reward += w.damage_taken * health_lost

        terminated = False
        if game_over:
            reward += w.win
            terminated = True

        truncated = self._round >= self.max_rounds

        info = {
            "round": self._round,
            "checkpoints": p.next_checkpoint - 1,
            "health": p.health,
            "dist_to_cp": curr_dist,
        }
        return self._build_obs(), float(reward), terminated, truncated, info
