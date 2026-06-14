"""
Train a PPO reinforcement-learning bot for PirateRace.

Requirements (not in main requirements.txt — install separately):
    pip install gymnasium stable-baselines3

Examples:
    # Solo agent on map1, 500k steps, save to pigame/rl_models/
    python manage.py train_rl_bot

    # Longer run on the_hammer
    python manage.py train_rl_bot --map the_hammer.json --steps 2000000

    # Resume from checkpoint
    python manage.py train_rl_bot --resume pigame/rl_models/solo_map1

    # Evaluate an existing model (no training)
    python manage.py train_rl_bot --eval-only pigame/rl_models/solo_map1 --games 50
"""

import os
import sys
import time

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Train a PPO RL bot for PirateRace (requires gymnasium + stable-baselines3)."

    def add_arguments(self, parser):
        parser.add_argument("--map", default="map1.json", dest="mapfile",
                            help="Map to train on. Default: map1.json")
        parser.add_argument("--steps", type=int, default=500_000,
                            help="Total env steps for training. Default: 500000")
        parser.add_argument("--envs", type=int, default=8,
                            help="Parallel env copies for rollout. Default: 8")
        parser.add_argument("--out", default=None, dest="out_path",
                            help="Model save path (no .zip). Default: pigame/rl_models/solo_<map>")
        parser.add_argument("--resume", default=None,
                            help="Path to existing model to resume training.")
        parser.add_argument("--eval-only", default=None, dest="eval_only",
                            help="Skip training; evaluate model at this path.")
        parser.add_argument("--games", type=int, default=100,
                            help="Evaluation games after training. Default: 100")
        parser.add_argument("--max-rounds", type=int, default=60, dest="max_rounds",
                            help="Max rounds per episode. Default: 60")

    def handle(self, *args, **options):
        try:
            from stable_baselines3 import PPO
            from stable_baselines3.common.env_util import make_vec_env
            from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv
        except ImportError as e:
            raise CommandError(
                f"Missing RL dependency: {e}\n"
                "Install with: pip install gymnasium stable-baselines3"
            )

        from pigame.rl_env import PirateEnv, SOLO_WEIGHTS

        mapfile = options["mapfile"]
        total_steps = options["steps"]
        n_envs = options["envs"]
        max_rounds = options["max_rounds"]
        n_eval_games = options["games"]

        # Resolve output path
        base_dir = os.path.join(os.path.dirname(__file__), "..", "..", "rl_models")
        os.makedirs(base_dir, exist_ok=True)
        map_stem = mapfile.replace(".json", "")
        default_out = os.path.join(base_dir, f"solo_{map_stem}")
        out_path = options["out_path"] or default_out

        # ── eval-only mode ────────────────────────────────────────────────────
        if options["eval_only"]:
            model_path = options["eval_only"]
            self.stdout.write(f"Loading model from {model_path} ...")
            env = PirateEnv(mapfile=mapfile, max_rounds=max_rounds, weights=SOLO_WEIGHTS)
            model = PPO.load(model_path)
            self._evaluate(model, env, n_eval_games, self.stdout.write)
            return

        # ── build vectorised env ──────────────────────────────────────────────
        self.stdout.write(
            f"Training PPO · map={mapfile} · steps={total_steps:,} · {n_envs} envs"
        )

        def make_env():
            return PirateEnv(mapfile=mapfile, max_rounds=max_rounds, weights=SOLO_WEIGHTS)

        # DummyVecEnv runs envs in-process (safe when Django is already configured).
        # SubprocVecEnv is faster for CPU-heavy envs but requires each subprocess
        # to re-initialise Django — set n_envs=1 or use DummyVecEnv if it hangs.
        vec_cls = SubprocVecEnv if n_envs > 1 else DummyVecEnv
        vec_env = make_vec_env(make_env, n_envs=n_envs, vec_env_cls=vec_cls)

        # ── create or resume model ─────────────────────────────────────────────
        if options["resume"]:
            self.stdout.write(f"Resuming from {options['resume']}")
            model = PPO.load(options["resume"], env=vec_env)
        else:
            model = PPO(
                "MlpPolicy",
                vec_env,
                verbose=1,
                n_steps=2048,
                batch_size=256,
                n_epochs=10,
                learning_rate=3e-4,
                gamma=0.99,
                gae_lambda=0.95,
                clip_range=0.2,
                ent_coef=0.01,       # entropy bonus encourages exploration
                tensorboard_log=os.path.join(base_dir, "tb_logs"),
            )

        # ── train ─────────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        model.learn(total_timesteps=total_steps, progress_bar=True)
        elapsed = time.perf_counter() - t0
        self.stdout.write(f"\nTraining done in {elapsed:.0f}s")

        # ── save ──────────────────────────────────────────────────────────────
        model.save(out_path)
        self.stdout.write(f"Model saved to {out_path}.zip")

        vec_env.close()

        # ── quick eval after training ──────────────────────────────────────────
        eval_env = PirateEnv(mapfile=mapfile, max_rounds=max_rounds, weights=SOLO_WEIGHTS)
        self._evaluate(model, eval_env, n_eval_games, self.stdout.write)

    # ── evaluation helper ─────────────────────────────────────────────────────

    @staticmethod
    def _evaluate(model, env, n_games: int, write):
        import numpy as np

        wins = 0
        total_rounds = 0
        total_cps = []

        for g in range(n_games):
            obs, _ = env.reset(seed=g)
            done = False
            while not done:
                action, _ = model.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, info = env.step(action)
                done = terminated or truncated
            total_rounds += info["round"]
            cps = info["checkpoints"]
            total_cps.append(cps)
            if terminated:
                wins += 1

        write("")
        write(f"  Eval over {n_games} games:")
        write(f"    Win rate       : {wins}/{n_games}  ({wins/n_games*100:.1f}%)")
        write(f"    Avg rounds     : {total_rounds/n_games:.1f}")
        write(f"    Avg checkpoints: {sum(total_cps)/n_games:.2f}")
        write(f"    Max checkpoints: {max(total_cps)}")
