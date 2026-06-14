"""
Pure-Python bot evaluation framework — no per-round DB or Redis writes.

Designed to be fast enough for RL training loops. Each EvalGame exposes a
reset() / step() interface (gym.Env style) as well as a convenience run().

Example:
    from pigame.bot_eval import EvalGame, run_tournament
    stats, results = run_tournament(["random", "greedy"], "map1.json", n_games=20)
"""

import copy
import math
import random
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
    play_stack,
)
from pigame.models import COLORS, DEFAULT_DECK, FREE_HEALTH_OFFSET, NRANKINGS


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_deck(pct_repair: int = 0) -> List[int]:
    """Fresh shuffled deck (no console output unlike models.add_repair_cards)."""
    deck = list(DEFAULT_DECK)
    n_repair = int(round(pct_repair * 1e-2 * len(deck)))
    deck.extend([100 * NRANKINGS] * n_repair)
    random.shuffle(deck)
    return deck


def _draw_hand(deck: List[int], next_card: int, ncardsavail: int) -> List[int]:
    """Slice ncardsavail cards starting at next_card (no deck mutation)."""
    return list(deck[next_card : next_card + ncardsavail])


def _advance_deck(deck: List[int], next_card: int, ncardslots: int, ncardsavail: int):
    """
    Advance deck pointer by ncardslots.
    If the deck would run short for the next draw, cycle used cards to the end
    (shuffled). Returns (new_deck, new_next_card).
    """
    next_card += ncardslots
    if next_card + ncardsavail > len(deck):
        remaining = deck[next_card:]
        used = deck[:next_card]
        random.shuffle(used)
        deck = remaining + used
        next_card = 0
    return deck, next_card


class _SimObj:
    """Stub that silently ignores any .save() calls from play_stack."""
    def save(self, **kwargs):
        pass


# ── result data classes ───────────────────────────────────────────────────────

@dataclass
class PlayerResult:
    slot: int
    bot_type: str
    won: bool = False
    rounds_to_win: Optional[int] = None
    checkpoints_reached: int = 0
    min_dist_to_next_cp: float = float("inf")  # closest the bot ever got to its next goal


@dataclass
class GameResult:
    rounds_played: int
    players: List[PlayerResult]
    winner_slot: Optional[int] = None  # None = no winner within max_rounds


# ── single-game evaluator ─────────────────────────────────────────────────────

class EvalGame:
    """
    Simulates a game between bot players entirely in memory.

    Lifecycle (convenience):
        result = EvalGame(["random", "greedy"], "map1.json").run(max_rounds=50)

    Lifecycle (RL):
        game = EvalGame(...)
        obs = game.reset()
        while True:
            obs, rewards, done, info = game.step()
            if done:
                break
    """

    def __init__(
        self,
        bot_specs: List[str],
        mapfile: str,
        ncardslots: int = 5,
        ncardsavail: int = 9,
        pct_repair: int = 0,
    ):
        if ncardsavail < ncardslots:
            raise ValueError("ncardsavail must be >= ncardslots")
        self.bot_specs = bot_specs
        self.mapfile = mapfile
        self.ncardslots = ncardslots
        self.ncardsavail = ncardsavail
        self.pct_repair = pct_repair
        self.n_players = len(bot_specs)

        # Load map once; take a deep copy so determine_starting_locations can
        # shuffle the object list in-place without corrupting the Redis cache.
        self._map_data = copy.deepcopy(load_map(mapfile))
        self._checkpoints = determine_checkpoint_locations(self._map_data)
        self._n_checkpoints = len(self._checkpoints)

        # Fake player IDs — negative so they never collide with real DB users
        self._player_ids: List[int] = [-(i + 1) for i in range(self.n_players)]

        # Filled by reset()
        self._decks: List[List[int]] = []
        self._next_cards: List[int] = []
        self._player_states: Dict[int, object] = {}
        self._cards_played: List[int] = []
        self._start_x: List[int] = []
        self._start_y: List[int] = []
        self._start_dir: List[int] = []
        self._colors: List[str] = []
        self._names: List[str] = []
        self.round: int = 0
        self.done: bool = False

    # ── internal ──────────────────────────────────────────────────────────────

    def _make_sim_game(self):
        cfg = _SimObj()
        cfg.mapfile = self.mapfile
        cfg.player_ids = list(self._player_ids)
        cfg.player_start_x = list(self._start_x)
        cfg.player_start_y = list(self._start_y)
        cfg.player_start_directions = list(self._start_dir)
        cfg.player_colors = list(self._colors)
        cfg.player_names = list(self._names)
        cfg.ncardsavail = self.ncardsavail

        game = _SimObj()
        game.config = cfg
        game.cards_played = list(self._cards_played)
        game.state = "select"
        return game

    def _observations(self) -> Dict[int, dict]:
        obs = {}
        for pid, st in self._player_states.items():
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
        """Initialise a fresh game. Returns initial observations keyed by player_id."""
        # Pick random starting positions from the map
        # (determine_starting_locations mutates the map layer in-place, so we
        #  must use our local deep-copy, not the Redis-cached version)
        sx, sy, sd = determine_starting_locations(self._map_data)
        self._start_x = sx[: self.n_players]
        self._start_y = sy[: self.n_players]
        self._start_dir = sd[: self.n_players]

        color_list = list(COLORS.values())
        self._colors = [color_list[i % len(color_list)] for i in range(self.n_players)]
        self._names = [f"{bt}_{i}" for i, bt in enumerate(self.bot_specs)]

        self._decks = [_make_deck(self.pct_repair) for _ in range(self.n_players)]
        self._next_cards = [0] * self.n_players
        self._cards_played = []
        self.round = 0
        self.done = False

        # Initialise player_states with empty history (starting positions)
        sim_game = self._make_sim_game()
        self._player_states, _ = play_stack(sim_game)

        return self._observations()

    def step(self) -> Tuple[Dict[int, dict], Dict[int, float], bool, dict]:
        """
        Play one round.

        Returns:
            observations  — dict pid → obs dict (same as reset())
            rewards       — dict pid → float  (distance improvement toward checkpoint)
            done          — True when the game is over (someone won)
            info          — extra debug info
        """
        if self.done:
            raise RuntimeError("Game is over — call reset() first.")

        prev_obs = self._observations()

        # ── 1. Each bot picks its card order ────────────────────────────────
        played_per_player: List[List[int]] = []
        for i, (pid, bot_type) in enumerate(zip(self._player_ids, self.bot_specs)):
            state = self._player_states.get(pid)
            hand = _draw_hand(self._decks[i], self._next_cards[i], self.ncardsavail)
            playable = hand[: self.ncardslots]
            remainder = hand[self.ncardslots :]

            best = pick_cards(
                bot_type,
                playable,
                mapfile=self.mapfile,
                player_id=pid,
                current_state=state,
                checkpoints=self._checkpoints,
                ncardsavail=self.ncardsavail,
            )
            played_per_player.append(best)

            # Write reordered hand back into deck
            self._decks[i][self._next_cards[i] : self._next_cards[i] + self.ncardsavail] = best + remainder

        # ── 2. Interleave cards by slot, sorted by rank (highest first) ─────
        # Replicates determine_next_cards_played without touching Redis.
        round_cards: List[int] = []
        for slot in range(self.ncardslots):
            slot_entries = [(self._player_ids[i], played_per_player[i][slot]) for i in range(self.n_players)]
            rankings = [card_id_rank(c)[1] for _, c in slot_entries]
            for j in argsort(rankings)[::-1]:
                pid, card = slot_entries[j]
                round_cards.extend([pid, card])
        round_cards.extend([BACKEND_USERID, ROUNDEND_CARDID])

        # ── 3. Append to full history and re-run play_stack from scratch ────
        # Running from scratch with the full history is how the real game works;
        # it ensures checkpoint tracking is always correct.
        self._cards_played.extend(round_cards)
        sim_game = self._make_sim_game()
        new_states, _ = play_stack(sim_game)
        self._player_states = new_states

        # ── 4. Advance deck pointers ────────────────────────────────────────
        for i in range(self.n_players):
            self._decks[i], self._next_cards[i] = _advance_deck(
                self._decks[i], self._next_cards[i], self.ncardslots, self.ncardsavail
            )

        self.round += 1
        self.done = (sim_game.state == "end")

        # ── 5. Compute per-player rewards (distance improvement) ─────────────
        curr_obs = self._observations()
        rewards = {}
        for pid in self._player_ids:
            prev_d = prev_obs[pid]["dist_to_next_cp"]
            curr_d = curr_obs[pid]["dist_to_next_cp"]
            rewards[pid] = prev_d - curr_d  # positive = moved closer

        return curr_obs, rewards, self.done, {"round": self.round}

    def run(self, max_rounds: int = 50) -> GameResult:
        """Play to completion or max_rounds. Returns GameResult with per-player stats."""
        self.reset()
        min_dists: Dict[int, float] = {pid: float("inf") for pid in self._player_ids}

        while not self.done and self.round < max_rounds:
            obs, _, done, _ = self.step()
            for pid, o in obs.items():
                min_dists[pid] = min(min_dists[pid], o["dist_to_next_cp"])

        winner_slot = None
        player_results = []
        for i, (pid, bot_type) in enumerate(zip(self._player_ids, self.bot_specs)):
            st = self._player_states.get(pid)
            # next_checkpoint starts at 1 and increments on each cp hit
            cps_reached = max(0, (st.next_checkpoint if st else 1) - 1)
            cps_reached = min(cps_reached, self._n_checkpoints)
            won = cps_reached >= self._n_checkpoints
            if won and winner_slot is None:
                winner_slot = i
            player_results.append(PlayerResult(
                slot=i,
                bot_type=bot_type,
                won=won,
                rounds_to_win=self.round if won else None,
                checkpoints_reached=cps_reached,
                min_dist_to_next_cp=min_dists[pid],
            ))

        return GameResult(
            rounds_played=self.round,
            players=player_results,
            winner_slot=winner_slot,
        )


# ── tournament ────────────────────────────────────────────────────────────────

@dataclass
class SlotStats:
    """Aggregate statistics for one player slot across N games."""
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
    seed: Optional[int] = None,
    progress_cb=None,
) -> Tuple[List[SlotStats], List[GameResult]]:
    """
    Run a tournament of N games between the given bots.

    Args:
        bot_specs:   e.g. ["random", "greedy", "random"]
        mapfile:     filename relative to MAPSDIR, e.g. "map1.json"
        n_games:     number of games to play
        max_rounds:  maximum rounds per game before declaring no winner
        seed:        optional RNG seed for reproducibility
        progress_cb: optional callable(game_idx, n_games, GameResult)

    Returns:
        (stats_per_slot, all_game_results)
    """
    if seed is not None:
        random.seed(seed)

    game = EvalGame(bot_specs, mapfile, ncardslots, ncardsavail, pct_repair)
    slot_stats = [SlotStats(slot=i, bot_type=bt, n_games=n_games) for i, bt in enumerate(bot_specs)]

    results: List[GameResult] = []
    for g in range(n_games):
        result = game.run(max_rounds)
        results.append(result)
        for pr in result.players:
            s = slot_stats[pr.slot]
            if pr.won:
                s.wins += 1
                s.total_rounds_to_win += result.rounds_played
            s.total_checkpoints += pr.checkpoints_reached
            if pr.min_dist_to_next_cp < float("inf"):
                s.min_dist_samples.append(pr.min_dist_to_next_cp)
        if progress_cb:
            progress_cb(g + 1, n_games, result)

    return slot_stats, results
