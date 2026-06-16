"""
Pure-Python bot evaluation framework — no per-round DB or Redis writes.

Each EvalGame maintains a players dict across rounds and steps it forward with
play_one_round() — O(1) per round.  run_tournament() fans games out across
CPU cores with ProcessPoolExecutor for near-linear speedup.

Public API:
    EvalGame(bot_specs, mapfile, ...).run(max_rounds)  →  GameResult
    run_tournament(bot_specs, mapfile, n_games, ...)   →  (stats, results)
"""

import copy
import math
import os
import random
import types
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from pigame.bots import pick_cards
from pigame.game_logic import (
    BACKEND_USERID,
    ROUNDEND_CARDID,
    argsort,
    card_id_rank,
    determine_checkpoint_locations,
    determine_starting_locations,
    load_map,
    play_one_round,
)
from pigame.models import (
    CANNON_DIRECTION,
    COLORS,
    DEFAULT_DECK,
    FREE_HEALTH_OFFSET,
    NRANKINGS,
)


# ── deck helpers ──────────────────────────────────────────────────────────────

def _make_deck(pct_repair: int = 0, pct_cannon: int = 0) -> List[int]:
    deck = list(DEFAULT_DECK)
    n_repair = int(round(pct_repair * 1e-2 * len(deck)))
    deck.extend([100 * NRANKINGS] * n_repair)
    if pct_cannon > 0:
        n_cannon = int(round(pct_cannon * 1e-2 * len(deck)))
        cannon_ids = [-10, -11, -12, -13]
        for i in range(n_cannon):
            deck.append(cannon_ids[i % len(cannon_ids)])
    random.shuffle(deck)
    return deck


def _advance_deck(deck, next_card, ncardslots, ncardsavail):
    next_card += ncardslots
    if next_card + ncardsavail > len(deck):
        remaining = deck[next_card:]
        used = deck[:next_card]
        random.shuffle(used)
        deck = remaining + used
        next_card = 0
    return deck, next_card


# ── result data classes ───────────────────────────────────────────────────────

@dataclass
class PlayerResult:
    slot: int
    bot_type: str
    won: bool = False
    rounds_to_win: Optional[int] = None
    checkpoints_reached: int = 0
    min_dist_to_next_cp: float = float("inf")


@dataclass
class GameResult:
    rounds_played: int
    players: List[PlayerResult]
    winner_slot: Optional[int] = None


# ── single-game evaluator ─────────────────────────────────────────────────────

class EvalGame:
    """
    Simulates a complete game between bot players in memory.

    Lifecycle (convenience):
        result = EvalGame(["random", "greedy"], "map1.json").run(max_rounds=50)

    Lifecycle (RL / step-by-step):
        game = EvalGame(...)
        obs = game.reset()
        while True:
            obs, rewards, done, info = game.step()
            if done: break
    """

    def __init__(
        self,
        bot_specs: List[str],
        mapfile: str,
        ncardslots: int = 5,
        ncardsavail: int = 9,
        pct_repair: int = 0,
        pct_cannon: int = 0,
        _map_data=None,     # internal: skip Redis call when map is pre-loaded
    ):
        if ncardsavail < ncardslots:
            raise ValueError("ncardsavail must be >= ncardslots")
        self.bot_specs = bot_specs
        self.mapfile = mapfile
        self.ncardslots = ncardslots
        self.ncardsavail = ncardsavail
        self.pct_repair = pct_repair
        self.pct_cannon = pct_cannon
        self.n_players = len(bot_specs)

        # Deep-copy: determine_starting_locations mutates the map's startinglocs
        # layer in-place; the copy keeps the Redis-cached version clean.
        raw = _map_data if _map_data is not None else load_map(mapfile)
        self._map_data = copy.deepcopy(raw)
        self._checkpoints = determine_checkpoint_locations(self._map_data)
        self._n_checkpoints = len(self._checkpoints)

        self._player_ids: List[int] = [-(i + 1) for i in range(self.n_players)]

        self._players: Dict[int, object] = {}
        self._decks: List[List[int]] = []
        self._next_cards: List[int] = []
        self._start_x: List[int] = []
        self._start_y: List[int] = []
        self._start_dir: List[int] = []
        self._colors: List[str] = []
        self._names: List[str] = []
        self.round: int = 0
        self.done: bool = False

    # ── internal ──────────────────────────────────────────────────────────────

    def _init_players(self):
        color_list = list(COLORS.values())
        self._players = {}
        for i, pid in enumerate(self._player_ids):
            self._players[pid] = types.SimpleNamespace(
                id=pid,
                name=self._names[i],
                color=self._colors[i],
                xpos=self._start_x[i],
                ypos=self._start_y[i],
                last_cp_x=self._start_x[i],
                last_cp_y=self._start_y[i],
                direction=self._start_dir[i],
                cannon_direction=CANNON_DIRECTION.FORWARD,
                next_checkpoint=1,
                health=self.ncardsavail + FREE_HEALTH_OFFSET,
                powered_down=False,
            )

    def _observations(self) -> Dict[int, dict]:
        obs = {}
        for pid, st in self._players.items():
            next_cp = min(st.next_checkpoint, self._n_checkpoints)
            cp_x, cp_y = self._checkpoints.get(next_cp, (st.xpos, st.ypos))
            obs[pid] = {
                "xpos": st.xpos,
                "ypos": st.ypos,
                "direction": st.direction,
                "health": st.health,
                "next_checkpoint": st.next_checkpoint,
                "dist_to_next_cp": math.sqrt((st.xpos - cp_x) ** 2 + (st.ypos - cp_y) ** 2),
            }
        return obs

    # ── public API ────────────────────────────────────────────────────────────

    def reset(self) -> Dict[int, dict]:
        sx, sy, sd = determine_starting_locations(self._map_data)
        self._start_x = sx[: self.n_players]
        self._start_y = sy[: self.n_players]
        self._start_dir = sd[: self.n_players]

        color_list = list(COLORS.values())
        self._colors = [color_list[i % len(color_list)] for i in range(self.n_players)]
        self._names = [f"{bt}_{i}" for i, bt in enumerate(self.bot_specs)]

        self._decks = [_make_deck(self.pct_repair, self.pct_cannon) for _ in range(self.n_players)]
        self._next_cards = [0] * self.n_players
        self.round = 0
        self.done = False

        self._init_players()
        return self._observations()

    def step(self) -> Tuple[Dict[int, dict], Dict[int, float], bool, dict]:
        """
        Play one round.

        Returns:
            observations  — dict pid → obs dict
            rewards       — dict pid → float (distance improvement toward goal)
            done          — True when the game is over
            info          — {"round": int}
        """
        if self.done:
            raise RuntimeError("Game is over — call reset() first.")

        prev_obs = self._observations()

        # 1. Each bot picks its card order
        played_per_player: List[List[int]] = []
        for i, (pid, bot_type) in enumerate(zip(self._player_ids, self.bot_specs)):
            hand = list(self._decks[i][self._next_cards[i] : self._next_cards[i] + self.ncardsavail])
            playable = hand[: self.ncardslots]
            remainder = hand[self.ncardslots :]

            best = pick_cards(
                bot_type,
                playable,
                mapfile=self.mapfile,
                player_id=pid,
                current_state=self._players[pid],
                checkpoints=self._checkpoints,
                ncardsavail=self.ncardsavail,
                map_data=self._map_data,
            )
            played_per_player.append(best)
            self._decks[i][self._next_cards[i] : self._next_cards[i] + self.ncardsavail] = best + remainder

        # 2. Interleave cards by slot, sorted by rank (highest first)
        round_cards: List[int] = []
        for slot in range(self.ncardslots):
            slot_entries = [(self._player_ids[i], played_per_player[i][slot]) for i in range(self.n_players)]
            rankings = [card_id_rank(c)[1] for _, c in slot_entries]
            for j in argsort(rankings)[::-1]:
                pid, card = slot_entries[j]
                round_cards.extend([pid, card])
        round_cards.extend([BACKEND_USERID, ROUNDEND_CARDID])

        # 3. Advance one round — O(ncardslots), not O(full history)
        self.done = play_one_round(self._players, self._map_data, round_cards, self.ncardsavail)

        # 4. Advance deck pointers
        for i in range(self.n_players):
            self._decks[i], self._next_cards[i] = _advance_deck(
                self._decks[i], self._next_cards[i], self.ncardslots, self.ncardsavail
            )

        self.round += 1

        curr_obs = self._observations()
        rewards = {
            pid: prev_obs[pid]["dist_to_next_cp"] - curr_obs[pid]["dist_to_next_cp"]
            for pid in self._player_ids
        }

        return curr_obs, rewards, self.done, {"round": self.round}

    def run(self, max_rounds: int = 50) -> GameResult:
        self.reset()
        min_dists: Dict[int, float] = {pid: float("inf") for pid in self._player_ids}

        while not self.done and self.round < max_rounds:
            obs, _, _, _ = self.step()
            for pid, o in obs.items():
                min_dists[pid] = min(min_dists[pid], o["dist_to_next_cp"])

        winner_slot = None
        player_results = []
        for i, (pid, bot_type) in enumerate(zip(self._player_ids, self.bot_specs)):
            st = self._players[pid]
            cps = min(max(0, st.next_checkpoint - 1), self._n_checkpoints)
            won = cps >= self._n_checkpoints
            if won and winner_slot is None:
                winner_slot = i
            player_results.append(PlayerResult(
                slot=i,
                bot_type=bot_type,
                won=won,
                rounds_to_win=self.round if won else None,
                checkpoints_reached=cps,
                min_dist_to_next_cp=min_dists[pid],
            ))

        return GameResult(
            rounds_played=self.round,
            players=player_results,
            winner_slot=winner_slot,
        )


# ── parallel tournament ───────────────────────────────────────────────────────

def _run_game_worker(args):
    """
    Top-level worker function (must be picklable for multiprocessing).
    Runs a single game and returns its GameResult.
    """
    bot_specs, mapfile, map_data, max_rounds, ncardslots, ncardsavail, pct_repair, pct_cannon, game_seed = args
    random.seed(game_seed)
    game = EvalGame(bot_specs, mapfile, ncardslots, ncardsavail, pct_repair, pct_cannon, _map_data=map_data)
    return game.run(max_rounds)


@dataclass
class SlotStats:
    slot: int
    bot_type: str
    n_games: int
    wins: int = 0
    total_rounds_to_win: int = 0
    total_checkpoints: int = 0
    min_dist_samples: List[float] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.wins / self.n_games if self.n_games else 0.0

    @property
    def avg_checkpoints(self) -> float:
        return self.total_checkpoints / self.n_games if self.n_games else 0.0

    @property
    def avg_rounds_to_win(self) -> Optional[float]:
        return self.total_rounds_to_win / self.wins if self.wins else None

    @property
    def avg_min_dist(self) -> float:
        s = [d for d in self.min_dist_samples if d < float("inf")]
        return sum(s) / len(s) if s else float("inf")


def run_tournament(
    bot_specs: List[str],
    mapfile: str,
    n_games: int = 20,
    max_rounds: int = 50,
    ncardslots: int = 5,
    ncardsavail: int = 9,
    pct_repair: int = 0,
    pct_cannon: int = 0,
    seed: Optional[int] = None,
    n_workers: int = 1,
    progress_cb=None,
) -> Tuple[List[SlotStats], List[GameResult]]:
    """
    Run a tournament of n_games games between the given bots.

    Games run in parallel across n_workers processes.  n_workers=1 keeps
    execution sequential (useful for debugging and exact reproducibility).

    Each game gets a deterministic seed derived from `seed` (or a random one
    when seed=None) so results are reproducible regardless of worker count.
    """
    # Assign each game a unique seed up-front in the parent process.
    # When seed is None, draw from the parent's random state so different
    # tournament runs differ even without an explicit seed.
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()
    game_seeds = [rng.randint(0, 2**31) for _ in range(n_games)]

    # Load map once in parent; workers receive it as an argument (no Redis per worker).
    map_data = load_map(mapfile)

    worker_args = [
        (bot_specs, mapfile, map_data, max_rounds, ncardslots, ncardsavail, pct_repair, pct_cannon, gs)
        for gs in game_seeds
    ]

    slot_stats = [SlotStats(slot=i, bot_type=bt, n_games=n_games) for i, bt in enumerate(bot_specs)]
    results: List[GameResult] = []

    def _accumulate(result: GameResult):
        results.append(result)
        for pr in result.players:
            s = slot_stats[pr.slot]
            if pr.won:
                s.wins += 1
                s.total_rounds_to_win += result.rounds_played
            s.total_checkpoints += pr.checkpoints_reached
            if pr.min_dist_to_next_cp < float("inf"):
                s.min_dist_samples.append(pr.min_dist_to_next_cp)

    if n_workers <= 1:
        for g, args in enumerate(worker_args):
            result = _run_game_worker(args)
            _accumulate(result)
            if progress_cb:
                progress_cb(g + 1, n_games, result)
    else:
        completed = 0
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            future_to_idx = {pool.submit(_run_game_worker, args): g for g, args in enumerate(worker_args)}
            for future in as_completed(future_to_idx):
                result = future.result()
                _accumulate(result)
                completed += 1
                if progress_cb:
                    progress_cb(completed, n_games, result)

    return slot_stats, results
