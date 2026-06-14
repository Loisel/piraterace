"""
Train a PPO reinforcement-learning bot for PirateRace.

Requirements (install separately — not in main requirements.txt):
    pip install gymnasium stable-baselines3 onnxruntime

────────────────────────────────────────────────────────────────
QUICK START — solo bot on map1 (500k steps)
────────────────────────────────────────────────────────────────
    python manage.py train_rl_bot

CURRICULUM TRAINING (recommended — 3-stage pipeline)
────────────────────────────────────────────────────────────────
Stage 1 — teach navigation (solo):
    python manage.py train_rl_bot \\
        --steps 2000000 --out pigame/rl_models/stage1_solo

Stage 2 — introduce competition (vs random):
    python manage.py train_rl_bot \\
        --steps 1000000 --opponents random \\
        --resume pigame/rl_models/stage1_solo \\
        --out pigame/rl_models/stage2_vs_random

Stage 3 — harden against greedy:
    python manage.py train_rl_bot \\
        --steps 1000000 --opponents greedy \\
        --resume pigame/rl_models/stage2_vs_random \\
        --out pigame/rl_models/stage3_vs_greedy

After stage 3, deploy the ONNX model:
    cp pigame/rl_models/stage3_vs_greedy.onnx pigame/rl_models/solo_map1.onnx
    cp pigame/rl_models/stage3_vs_greedy.onnx.data pigame/rl_models/solo_map1.onnx.data

EVALUATION ONLY
────────────────────────────────────────────────────────────────
    python manage.py train_rl_bot \\
        --eval-only pigame/rl_models/solo_map1 --games 100

OTHER OPTIONS
────────────────────────────────────────────────────────────────
    --map the_hammer.json   Train on a different map
    --envs 8                Parallel rollout environments
    --max-rounds 60         Episode length cap
"""

import os
import sys
import time

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Train a PPO RL bot for PirateRace (requires gymnasium + stable-baselines3)."

    def add_arguments(self, parser):
        parser.add_argument("--map", default="map1.json", dest="mapfile",
                            help="Map file to train on (default: map1.json)")
        parser.add_argument("--steps", type=int, default=500_000,
                            help="Total environment steps (default: 500000)")
        parser.add_argument("--envs", type=int, default=8,
                            help="Parallel rollout environments (default: 8)")
        parser.add_argument("--out", default=None, dest="out_path",
                            help="Model save path without extension (default: rl_models/solo_<map>)")
        parser.add_argument("--resume", default=None,
                            help="Existing model path to resume from")
        parser.add_argument("--eval-only", default=None, dest="eval_only",
                            help="Skip training; evaluate model at this path")
        parser.add_argument("--games", type=int, default=100,
                            help="Number of evaluation games (default: 100)")
        parser.add_argument("--max-rounds", type=int, default=60, dest="max_rounds",
                            help="Max rounds per episode (default: 60)")
        parser.add_argument("--opponents", nargs="*", default=[],
                            help="Bot types to play against, e.g. --opponents random greedy")
        parser.add_argument("--max-opponents", type=int, default=1, dest="max_opponents",
                            help="Observation slots reserved for opponents (default: 1). "
                                 "Keep this constant across curriculum stages so obs shape "
                                 "stays fixed and --resume works.")

    def handle(self, *args, **options):
        try:
            from stable_baselines3 import PPO
            from stable_baselines3.common.env_util import make_vec_env
            from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv, VecNormalize
        except ImportError as e:
            raise CommandError(
                f"Missing RL dependency: {e}\n"
                "Install with: pip install gymnasium stable-baselines3"
            )

        from pigame.rl_env import PirateEnv, SOLO_WEIGHTS, RACE_WEIGHTS
        from pigame.rl_policy import PirateCNNExtractor

        mapfile = options["mapfile"]
        total_steps = options["steps"]
        n_envs = options["envs"]
        max_rounds = options["max_rounds"]
        n_eval_games = options["games"]
        opponent_types = options["opponents"]
        max_opponents = options["max_opponents"]

        weights = RACE_WEIGHTS if opponent_types else SOLO_WEIGHTS

        base_dir = os.path.join(os.path.dirname(__file__), "..", "..", "rl_models")
        os.makedirs(base_dir, exist_ok=True)
        map_stem = mapfile.replace(".json", "")
        default_out = os.path.join(base_dir, f"solo_{map_stem}")
        out_path = options["out_path"] or default_out

        # ── eval-only mode ─────────────────────────────────────────────────────
        if options["eval_only"]:
            model_path = options["eval_only"]
            self.stdout.write(f"Loading model from {model_path} ...")
            env = PirateEnv(mapfile=mapfile, max_rounds=max_rounds,
                            weights=weights, opponent_types=opponent_types,
                            max_opponents=max_opponents)
            model = PPO.load(model_path)
            self._evaluate(model, env, n_eval_games, opponent_types, self.stdout.write)
            return

        # ── build vectorised env ───────────────────────────────────────────────
        opp_desc = f"vs [{', '.join(opponent_types)}]" if opponent_types else "solo"
        self.stdout.write(
            f"Training PPO · map={mapfile} · {opp_desc} · "
            f"steps={total_steps:,} · {n_envs} envs · max_opponents={max_opponents}"
        )

        def make_env():
            return PirateEnv(
                mapfile=mapfile, max_rounds=max_rounds,
                weights=weights, opponent_types=opponent_types,
                max_opponents=max_opponents,
            )

        vec_cls = SubprocVecEnv if n_envs > 1 else DummyVecEnv
        vec_env = make_vec_env(make_env, n_envs=n_envs, vec_env_cls=vec_cls)
        vec_env = VecNormalize(vec_env, norm_obs=False, norm_reward=True, gamma=0.99)

        # ── create or resume model ─────────────────────────────────────────────
        if options["resume"]:
            self.stdout.write(f"Resuming from {options['resume']}")
            stats_path = options["resume"] + "_vecnorm.pkl"
            if os.path.exists(stats_path):
                vec_env = VecNormalize.load(stats_path, venv=vec_env)
                vec_env.training = True
                self.stdout.write(f"  Loaded VecNormalize stats from {stats_path}")
            model = PPO.load(options["resume"], env=vec_env)
        else:
            # Compute n_scalar to pass to the CNN extractor so it knows
            # where the scalar prefix ends and the spatial crop begins.
            _tmp_env = make_env()
            n_scalar = _tmp_env.n_scalar
            del _tmp_env

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
                ent_coef=0.01,
                policy_kwargs=dict(
                    features_extractor_class=PirateCNNExtractor,
                    features_extractor_kwargs=dict(
                        n_scalar=n_scalar,
                        features_dim=256,
                    ),
                    net_arch=[128, 128],   # smaller head — CNN does heavy lifting
                ),
                tensorboard_log=os.path.join(base_dir, "tb_logs"),
            )

        # ── train ─────────────────────────────────────────────────────────────
        t0 = time.perf_counter()
        model.learn(total_timesteps=total_steps, progress_bar=True)
        elapsed = time.perf_counter() - t0
        self.stdout.write(f"\nTraining done in {elapsed:.0f}s")

        # ── save ──────────────────────────────────────────────────────────────
        model.save(out_path)
        vec_env.save(out_path + "_vecnorm.pkl")
        self.stdout.write(f"Model saved → {out_path}.zip")

        vec_env.close()

        # ── export ONNX ────────────────────────────────────────────────────────
        self.stdout.write("Exporting to ONNX ...")
        try:
            self._export_onnx(model, out_path)
        except Exception as e:
            self.stdout.write(f"  ONNX export failed: {e}")

        # ── eval ───────────────────────────────────────────────────────────────
        eval_env = PirateEnv(mapfile=mapfile, max_rounds=max_rounds,
                             weights=weights, opponent_types=opponent_types,
                             max_opponents=max_opponents)
        self._evaluate(model, eval_env, n_eval_games, opponent_types, self.stdout.write)

    # ── ONNX export ───────────────────────────────────────────────────────────

    @staticmethod
    def _export_onnx(model, out_path: str):
        import torch

        policy = model.policy
        policy.eval()
        obs_dim = model.observation_space.shape[0]

        class DetActionNet(torch.nn.Module):
            def __init__(self, p):
                super().__init__()
                self.policy = p
            def forward(self, obs):
                features = self.policy.extract_features(obs, self.policy.features_extractor)
                latent_pi, _ = self.policy.mlp_extractor(features)
                return self.policy.action_net(latent_pi)

        net = DetActionNet(policy)
        dummy = torch.zeros(1, obs_dim)
        onnx_path = out_path + ".onnx"
        torch.onnx.export(
            net, dummy, onnx_path,
            input_names=["obs"], output_names=["action_mean"],
            dynamic_axes={"obs": {0: "batch"}},
            opset_version=17,
        )
        size_kb = os.path.getsize(onnx_path) / 1024
        print(f"  ONNX exported → {onnx_path}  ({size_kb:.0f} KB)")

    # ── evaluation helper ─────────────────────────────────────────────────────

    @staticmethod
    def _evaluate(model, env, n_games: int, opponent_types: list, write):
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
            if info.get("won", terminated):
                wins += 1

        opp_desc = f" vs {opponent_types}" if opponent_types else " (solo)"
        write("")
        write(f"  Eval over {n_games} games{opp_desc}:")
        write(f"    Win rate       : {wins}/{n_games}  ({wins/n_games*100:.1f}%)")
        write(f"    Avg rounds     : {total_rounds/n_games:.1f}")
        write(f"    Avg checkpoints: {sum(total_cps)/n_games:.2f}")
        write(f"    Max checkpoints: {max(total_cps)}")
