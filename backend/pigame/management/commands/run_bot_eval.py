"""
Django management command: run a bot evaluation tournament.

Examples:
    # 1v1: random vs greedy, 20 games, map1
    python manage.py run_bot_eval --bots random,greedy --games 20

    # Single-player: greedy alone, see if it can reach checkpoints
    python manage.py run_bot_eval --bots greedy --games 10 --rounds 80

    # 4-player free-for-all on a different map
    python manage.py run_bot_eval --bots random,random,greedy,greedy --map map2.json --games 30

    # JSON output (pipe to jq etc.)
    python manage.py run_bot_eval --bots random,greedy --games 50 --format json

    # Reproducible run
    python manage.py run_bot_eval --bots random,greedy --games 20 --seed 42
"""

import json
import sys
import time

from django.core.management.base import BaseCommand, CommandError

from pigame.bot_eval import run_tournament


class Command(BaseCommand):
    help = "Run a bot evaluation tournament and print statistics."

    def add_arguments(self, parser):
        parser.add_argument(
            "--bots",
            type=str,
            default="random,greedy",
            help="Comma-separated list of bot types, one per player. "
                 "Available: random, greedy. Example: random,greedy,random",
        )
        parser.add_argument(
            "--map",
            type=str,
            default="map1.json",
            dest="mapfile",
            help="Map filename (relative to MAPSDIR). Default: map1.json",
        )
        parser.add_argument(
            "--games",
            type=int,
            default=20,
            help="Number of games to play. Default: 20",
        )
        parser.add_argument(
            "--rounds",
            type=int,
            default=50,
            help="Maximum rounds per game. Default: 50",
        )
        parser.add_argument(
            "--ncardslots",
            type=int,
            default=5,
            help="Cards played per round per player. Default: 5",
        )
        parser.add_argument(
            "--ncardsavail",
            type=int,
            default=9,
            help="Cards visible in hand. Default: 9",
        )
        parser.add_argument(
            "--repair",
            type=int,
            default=0,
            dest="pct_repair",
            help="Percentage of repair cards in deck. Default: 0",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Random seed for reproducibility. Default: none (random)",
        )
        parser.add_argument(
            "--format",
            choices=["table", "json"],
            default="table",
            dest="output_format",
            help="Output format. Default: table",
        )

    def handle(self, *args, **options):
        bot_specs = [b.strip() for b in options["bots"].split(",")]
        mapfile = options["mapfile"]
        n_games = options["games"]
        max_rounds = options["rounds"]
        ncardslots = options["ncardslots"]
        ncardsavail = options["ncardsavail"]
        pct_repair = options["pct_repair"]
        seed = options["seed"]
        output_format = options["output_format"]

        if ncardslots > ncardsavail:
            raise CommandError("--ncardslots must be <= --ncardsavail")

        # ── progress indicator (table mode only) ─────────────────────────────
        game_counter = [0]

        def progress(g, total, result):
            game_counter[0] = g
            if output_format == "table":
                winner = result.players[result.winner_slot].bot_type if result.winner_slot is not None else "—"
                sys.stderr.write(f"\r  Game {g:>4}/{total}  last winner: {winner:<10}")
                sys.stderr.flush()

        # ── run ──────────────────────────────────────────────────────────────
        self.stderr.write(
            f"Running {n_games} games  ·  {len(bot_specs)} bots: {', '.join(bot_specs)}"
            f"  ·  map: {mapfile}  ·  {ncardslots}/{ncardsavail} cards"
            + (f"  ·  seed: {seed}" if seed is not None else "")
        )
        t0 = time.perf_counter()
        slot_stats, results = run_tournament(
            bot_specs,
            mapfile,
            n_games=n_games,
            max_rounds=max_rounds,
            ncardslots=ncardslots,
            ncardsavail=ncardsavail,
            pct_repair=pct_repair,
            seed=seed,
            progress_cb=progress,
        )
        elapsed = time.perf_counter() - t0
        if output_format == "table":
            sys.stderr.write("\n")

        # ── output ────────────────────────────────────────────────────────────
        if output_format == "json":
            self._output_json(slot_stats, results, elapsed)
        else:
            self._output_table(slot_stats, results, elapsed, n_games, max_rounds, mapfile, bot_specs)

    # ── table output ──────────────────────────────────────────────────────────

    def _output_table(self, slot_stats, results, elapsed, n_games, max_rounds, mapfile, bot_specs):
        out = self.stdout.write

        out("")
        out(f"{'='*70}")
        out(f"  Tournament: {n_games} games  ·  max {max_rounds} rounds/game  ·  map: {mapfile}")
        out(f"{'='*70}")

        # Per-slot stats
        hdr = f"  {'Slot':<6}{'Bot type':<12}{'Wins':>6}{'Win%':>7}{'Avg CPs':>9}{'Avg Rnds':>10}{'Avg Dist':>10}"
        out(hdr)
        out("  " + "-" * (len(hdr) - 2))
        for s in slot_stats:
            avg_rounds = f"{s.avg_rounds_to_win:.1f}" if s.avg_rounds_to_win is not None else "  —"
            avg_dist = f"{s.avg_min_dist:.2f}" if s.avg_min_dist < float("inf") else "  —"
            out(
                f"  {s.slot:<6}{s.bot_type:<12}{s.wins:>6}{s.win_rate*100:>6.1f}%"
                f"{s.avg_checkpoints:>9.2f}{avg_rounds:>10}{avg_dist:>10}"
            )

        # Game-level overview
        rounds_list = [r.rounds_played for r in results]
        won_games = [r for r in results if r.winner_slot is not None]
        out("")
        out(f"  Game stats:")
        out(f"    Games with a winner : {len(won_games)}/{n_games}")
        out(f"    Avg rounds/game     : {sum(rounds_list)/len(rounds_list):.1f}")
        if won_games:
            out(f"    Fastest win         : {min(r.rounds_played for r in won_games)} rounds")
            out(f"    Slowest win         : {max(r.rounds_played for r in won_games)} rounds")
        all_cps = [pr.checkpoints_reached for r in results for pr in r.players]
        out(f"    Max CPs in one game : {max(all_cps)}")
        out(f"    Elapsed             : {elapsed:.1f}s  ({elapsed*1000/n_games:.0f} ms/game)")
        out(f"{'='*70}")
        out("")

    # ── json output ───────────────────────────────────────────────────────────

    def _output_json(self, slot_stats, results, elapsed):
        data = {
            "slots": [
                {
                    "slot": s.slot,
                    "bot_type": s.bot_type,
                    "n_games": s.n_games,
                    "wins": s.wins,
                    "win_rate": round(s.win_rate, 4),
                    "avg_checkpoints": round(s.avg_checkpoints, 3),
                    "avg_rounds_to_win": round(s.avg_rounds_to_win, 1) if s.avg_rounds_to_win else None,
                    "avg_min_dist": round(s.avg_min_dist, 3) if s.avg_min_dist < float("inf") else None,
                }
                for s in slot_stats
            ],
            "games": [
                {
                    "rounds_played": r.rounds_played,
                    "winner_slot": r.winner_slot,
                    "players": [
                        {
                            "slot": pr.slot,
                            "bot_type": pr.bot_type,
                            "won": pr.won,
                            "rounds_to_win": pr.rounds_to_win,
                            "checkpoints_reached": pr.checkpoints_reached,
                            "min_dist_to_next_cp": round(pr.min_dist_to_next_cp, 3)
                            if pr.min_dist_to_next_cp < float("inf")
                            else None,
                        }
                        for pr in r.players
                    ],
                }
                for r in results
            ],
            "elapsed_seconds": round(elapsed, 2),
        }
        self.stdout.write(json.dumps(data, indent=2))
