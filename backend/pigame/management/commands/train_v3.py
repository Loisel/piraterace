"""
v3 training: Pointer Network with BC teacher-forcing + PPO fine-tuning.

Architecture change (from flat MLP):
  PointerDecoder — autoregressive selection:  ncardslots sequential pointer
  steps, each a softmax over remaining cards conditioned on prior picks via a
  GRUCell.  This is the architecturally correct approach for "select k from n
  in order" (Vinyals et al. 2015, Hearthstone AI paper, IJCAI 2019 Select-MDP).

BC pretraining:
  Teacher-forcing log-likelihood: L = -E[Σ_k log P(a_k | obs, a_0..k-1)]
  where a_k is the greedy expert's k-th card choice.  This gives dense gradient
  signal at every pointer step, including the first (most important) choice.

PPO fine-tuning:
  Log-prob = sum of ncardslots per-step log-probs → correct policy gradient.
  ent_coef acts on the sum-entropy (~5× a single Categorical entropy).

Stages:
  BC   : 8k episodes → teacher-forcing, 60 epochs
  PPO-1: 5M solo steps (learn navigation)
  PPO-2: 3M vs greedy (learn to race)

Output: rl_models/v3_vs_greedy.{zip,onnx}
"""

import multiprocessing
multiprocessing.set_start_method("fork", force=True)

import os, sys, time, random
import numpy as np

REPO = "/home/fabian/work/piraterace/backend"
sys.path.insert(0, REPO)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "piraterace.settings")

import django
from django.conf import settings as _dj
_dj.CACHES["default"]["LOCATION"] = "redis://172.19.0.4:6379"
django.setup()

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv, VecNormalize
from stable_baselines3.common.callbacks import BaseCallback

from pigame.rl_env import PirateEnv, SOLO_WEIGHTS, RACE_WEIGHTS
from pigame.rl_pointer import PointerDecoder, PointerActorCriticPolicy, PointerOnnxWrapper
from pigame.bots import _greedy_pick, _simulate_end_pos_fast

MODEL_DIR = os.path.join(REPO, "pigame", "rl_models")
os.makedirs(MODEL_DIR, exist_ok=True)

MAPFILE         = "map1.json"           # kept for BC eval / WinRateCallback baseline
MAPS            = ["map1.json", "map2.json", "rennstreck.json", "the_hammer.json", "the_maelstrom.json"]
MAX_ROUNDS      = 60
N_ENVS          = 16
NCARDSLOTS      = 5                    # cards played per round (always 5)
NCARDSAVAIL_OPTIONS = [5, 9, 12, 15]  # randomly chosen per episode during training
MAX_NCARDSAVAIL = 15                   # fixed obs/action size; covers all options above
NCARDSAVAIL     = 12                   # default for single-map eval

# ── BC config ──────────────────────────────────────────────────────────────────
BC_EPISODES   = 8_000
BC_EPOCHS     = 60
BC_BATCH_SIZE = 512
BC_LR         = 3e-4

# ── PPO config ─────────────────────────────────────────────────────────────────
PPO_STEPS_SOLO   = 5_000_000  # needs longer for large maps; runs fast with 16 parallel envs
PPO_STEPS_SOLO_RESUME = 10_000_000  # when resuming from v3_solo: much longer for multi-map
PPO_STEPS_GREEDY = 3_000_000
WIN_RATE_FREQ    = 500_000

# Pass --resume to skip BC and load v3_solo checkpoint for extended PPO-1 solo.
RESUME = "--resume" in sys.argv

PPO_KWARGS = dict(
    verbose=1,
    n_steps=2048,
    batch_size=512,   # larger rollouts from 16 envs → bigger batch stays efficient
    n_epochs=5,       # fewer passes per rollout to match update frequency
    learning_rate=3e-4,
    gamma=0.99,
    gae_lambda=0.95,
    clip_range=0.2,
    ent_coef=0.01,   # per-step value; pointer sums 5 steps so effective ~0.05
    policy_kwargs=dict(
        ncardsavail=MAX_NCARDSAVAIL,
        ncardslots=NCARDSLOTS,
        hidden_dim=256,
        card_dim=64,
    ),
)


# ── win-rate callback ──────────────────────────────────────────────────────────

class WinRateCallback(BaseCallback):
    def __init__(self, opponent_types=None, n_eval=100, eval_freq=WIN_RATE_FREQ):
        super().__init__(verbose=0)
        self.opponent_types = opponent_types or []
        self.n_eval         = n_eval
        self.eval_freq      = eval_freq
        self._next_eval     = eval_freq
        self._initialised   = False

    def _on_step(self) -> bool:
        # On first call, push _next_eval past the current step so we don't fire
        # N_ENVS× immediately when resuming from a checkpoint mid-training.
        if not self._initialised:
            self._initialised = True
            import math
            self._next_eval = self.eval_freq * (math.floor(self.num_timesteps / self.eval_freq) + 1)
        if self.num_timesteps < self._next_eval:
            return True
        self._next_eval += self.eval_freq
        # PPO-1 solo: use the_hammer (4 CPs, genuinely hard — greedy only 87–97%).
        # Rennstreck is trivially easy (60-round budget vs 18 needed) and was
        # already 100% before any extra training — useless as a progress signal.
        # PPO-2 vs greedy: use map1 (standard greedy benchmark).
        eval_map = "the_hammer.json" if not self.opponent_types else MAPFILE
        env = PirateEnv(
            mapfile=eval_map, max_rounds=MAX_ROUNDS,
            weights=RACE_WEIGHTS if self.opponent_types else SOLO_WEIGHTS,
            opponent_types=self.opponent_types, max_opponents=1,
            ncardsavail=NCARDSAVAIL, ncardslots=NCARDSLOTS,
            max_ncardsavail=MAX_NCARDSAVAIL,
        )
        wins, cps = 0, []
        for g in range(self.n_eval):
            obs, _ = env.reset(seed=g)
            done = False
            while not done:
                action, _ = self.model.predict(obs, deterministic=True)
                obs, _, term, trunc, info = env.step(action)
                done = term or trunc
            cps.append(info["checkpoints"])
            if info.get("won", False):
                wins += 1
        label   = f"vs {self.opponent_types}" if self.opponent_types else "solo"
        avg_cps = sum(cps) / self.n_eval
        print(f"  [step {self.num_timesteps:,}] {label}: "
              f"{wins}/{self.n_eval} wins ({100*wins/self.n_eval:.0f}%)  avg_cps={avg_cps:.2f}")
        return True


# ── ONNX export ────────────────────────────────────────────────────────────────

def export_onnx(model, out_path: str):
    """Export pointer network to ONNX (deterministic, unrolled 5 steps)."""
    policy = model.policy
    policy.eval()
    obs_dim = model.observation_space.shape[0]

    wrapper = PointerOnnxWrapper(policy.pointer)
    wrapper.eval()
    dummy = torch.zeros(1, obs_dim)

    onnx_path = out_path + ".onnx"
    torch.onnx.export(
        wrapper, dummy, onnx_path,
        input_names=["obs"],
        output_names=["card_indices"],   # bots.py detects by this name
        dynamic_axes={"obs": {0: "batch"}},
        opset_version=13,
        dynamo=False,                    # use stable TorchScript path (ort compat)
    )
    size_kb = os.path.getsize(onnx_path) / 1024
    print(f"  ONNX → {onnx_path}  ({size_kb:.0f} KB)")
    policy.set_training_mode(False)


# ── evaluation ─────────────────────────────────────────────────────────────────

def evaluate(model, opponent_types, n_games=200):
    """Evaluate across all training maps and nca values."""
    results = []
    n_per_combo = max(10, n_games // (len(MAPS) * len(NCARDSAVAIL_OPTIONS)))
    for mapfile in MAPS:
        for nca in NCARDSAVAIL_OPTIONS:
            env = PirateEnv(mapfile=mapfile, max_rounds=MAX_ROUNDS,
                            weights=RACE_WEIGHTS, opponent_types=opponent_types,
                            max_opponents=1, ncardsavail=nca, ncardslots=NCARDSLOTS,
                            max_ncardsavail=MAX_NCARDSAVAIL)
            wins, cps = 0, []
            for g in range(n_per_combo):
                obs, _ = env.reset(seed=g)
                done = False
                while not done:
                    action, _ = model.predict(obs, deterministic=True)
                    obs, _, term, trunc, info = env.step(action)
                    done = term or trunc
                cps.append(info["checkpoints"])
                if info.get("won", term):
                    wins += 1
            pct = 100 * wins / n_per_combo
            avg = sum(cps) / n_per_combo
            results.append((mapfile, nca, pct, avg))
            print(f"    {mapfile} nca={nca}: {wins}/{n_per_combo} ({pct:.0f}%)  avg_cps={avg:.2f}")
    opp = opponent_types or ["solo"]
    overall = sum(r[2] for r in results) / len(results)
    print(f"    → overall {opp}: {overall:.0f}% win rate")


# ── BC data collection ─────────────────────────────────────────────────────────

def _best_combo_from_hand(hand, ncardslots, ncardsavail, player, checkpoints, map_data):
    """
    Preview-select top ncardslots cards, greedy-order them.

    Returns (top_indices as tuple, ordered_cards as list).
    ~(ncardsavail + 100) simulations per call.
    """
    import math as _math
    cp_idx = min(player.next_checkpoint, max(checkpoints.keys()))
    cp_x, cp_y = checkpoints[cp_idx]
    dist_before = _math.sqrt((player.xpos - cp_x) ** 2 + (player.ypos - cp_y) ** 2)

    previews = []
    for card in hand:
        ex, ey = _simulate_end_pos_fast(map_data, player.id, player, [card], ncardsavail)
        previews.append(dist_before - _math.sqrt((ex - cp_x) ** 2 + (ey - cp_y) ** 2))

    ranked       = sorted(range(ncardsavail), key=lambda i: -previews[i])
    top_indices  = tuple(sorted(ranked[:ncardslots]))
    selected     = [hand[i] for i in ranked[:ncardslots]]
    ordered      = _greedy_pick(selected, MAPFILE, player.id, player,
                                checkpoints, ncardsavail, map_data)
    return top_indices, ordered


def collect_bc_data(n_episodes: int):
    """
    Run greedy (solo) games across all training maps with variable ncardsavail.
    At each step record obs + expert card indices for teacher-forcing.
    """
    env = PirateEnv(mapfile=MAPS[0], max_rounds=MAX_ROUNDS,
                    weights=SOLO_WEIGHTS, opponent_types=[], max_opponents=1,
                    ncardsavail_options=NCARDSAVAIL_OPTIONS, ncardslots=NCARDSLOTS,
                    max_ncardsavail=MAX_NCARDSAVAIL,
                    mapfiles=MAPS)
    ncs      = env.ncardslots
    obs_list = []
    act_list = []   # (ncardslots,) int per step

    t0 = time.perf_counter()
    total_steps = 0
    t_last, steps_last = t0, 0

    print(f"  maps: {MAPS}")
    print(f"  ncardsavail options: {NCARDSAVAIL_OPTIONS}")

    for ep in range(n_episodes):
        obs, _ = env.reset(seed=ep)
        done = False
        while not done:
            nca  = env.ncardsavail                         # may vary each episode
            hand = list(env._deck[env._next_card : env._next_card + nca])

            top_indices, best_ordered = _best_combo_from_hand(
                hand, ncs, nca,
                env._player, env._checkpoints, env._map_data,
            )

            # Convert best_ordered (card VALUES) → indices into hand
            remaining_top = list(top_indices)
            action_indices = []
            for card_val in best_ordered:
                matched = False
                for j, idx in enumerate(remaining_top):
                    if hand[idx] == card_val:
                        action_indices.append(idx)
                        remaining_top.pop(j)
                        matched = True
                        break
                if not matched:
                    # Fallback (shouldn't happen): take next available top index
                    if remaining_top:
                        action_indices.append(remaining_top.pop(0))

            action = np.array(action_indices, dtype=np.int32)
            obs_list.append(obs.copy())
            act_list.append(action)
            total_steps += 1

            obs, _, term, trunc, _ = env.step(action)
            done = term or trunc

        if (ep + 1) % 200 == 0:
            now   = time.perf_counter()
            elapsed   = now - t0
            interval  = now - t_last
            steps_int = total_steps - steps_last
            sps       = steps_int / interval if interval > 0 else 0
            eps_done  = ep + 1
            spe       = total_steps / eps_done
            eta       = (n_episodes - eps_done) * spe / sps if sps > 0 else float("inf")
            print(f"    ep {eps_done}/{n_episodes}  steps={total_steps}  "
                  f"{sps:.0f} steps/s  elapsed={elapsed:.0f}s  eta={eta:.0f}s")
            t_last, steps_last = now, total_steps

    elapsed = time.perf_counter() - t0
    print(f"  BC data: {total_steps} steps from {n_episodes} episodes in {elapsed:.0f}s")
    return (np.array(obs_list, dtype=np.float32),
            np.array(act_list,  dtype=np.int64))


# ── BC training ────────────────────────────────────────────────────────────────

def bc_pretrain(model, obs_arr: np.ndarray, action_arr: np.ndarray):
    """
    Teacher-forcing BC: maximise log P(expert action sequence | obs).

    Loss = -mean_batch [ Σ_k log P(a_k | obs, a_0..k-1) ]

    The pointer network is teacher-forced: at step k it receives the *actual*
    expert action a_{k-1} to update its context, so each per-step loss gets
    clean gradient signal even before the model is accurate on step k-1.
    """
    pointer = model.policy.pointer
    pointer.train()
    optimizer = torch.optim.Adam(pointer.parameters(), lr=BC_LR)

    obs_t = torch.FloatTensor(obs_arr)
    act_t = torch.LongTensor(action_arr)    # (N, ncardslots)
    loader = DataLoader(
        TensorDataset(obs_t, act_t),
        batch_size=BC_BATCH_SIZE, shuffle=True,
    )

    t0 = time.perf_counter()
    for epoch in range(BC_EPOCHS):
        total_loss = 0.0
        for obs_b, acts_b in loader:
            log_probs, _, _ = pointer.evaluate_actions(obs_b, acts_b)
            loss = -log_probs.mean()          # maximise log-likelihood
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        if (epoch + 1) % 10 == 0:
            avg   = total_loss / len(loader)
            # Perplexity per step: exp(-avg / ncardslots) — 1.0 = perfect
            ppx   = float(np.exp(-avg / NCARDSLOTS)) if avg < 50 else float("inf")
            print(f"    epoch {epoch+1}/{BC_EPOCHS}  bc_loss={avg:.4f}  "
                  f"per-step perplexity={ppx:.3f}")

    print(f"  BC done in {time.perf_counter()-t0:.0f}s")
    pointer.eval()
    model.policy.set_training_mode(False)


# ── main ───────────────────────────────────────────────────────────────────────

print("=" * 60)
print("v3 training: Pointer Network BC + PPO")
if RESUME:
    print("  MODE: resume from v3_solo (skip BC, extended PPO-1)")
print("=" * 60)

def make_env_solo():
    return PirateEnv(mapfile=MAPS[0], max_rounds=MAX_ROUNDS,
                     weights=SOLO_WEIGHTS, max_opponents=1,
                     ncardsavail_options=NCARDSAVAIL_OPTIONS, ncardslots=NCARDSLOTS,
                     max_ncardsavail=MAX_NCARDSAVAIL, mapfiles=MAPS)

if RESUME:
    # ── Resume: skip BC, load existing solo checkpoint ─────────────────────────
    solo_path = os.path.join(MODEL_DIR, "v3_solo")
    print(f"\n[RESUME] Loading {solo_path} ...")
    vec_env = make_vec_env(make_env_solo, n_envs=N_ENVS, vec_env_cls=SubprocVecEnv, vec_env_kwargs={"start_method": "fork"})
    vec_env = VecNormalize.load(solo_path + "_vecnorm.pkl", venv=vec_env)
    vec_env.training = True
    model = PPO.load(solo_path, env=vec_env, **{k: v for k, v in PPO_KWARGS.items()
                                                  if k not in ("policy_kwargs",)})
    print(f"  Loaded. Continuing PPO-1 solo for {PPO_STEPS_SOLO_RESUME:,} more steps ...")
    ppo1_steps = PPO_STEPS_SOLO_RESUME
else:
    # ── Step 1: BC pretraining ─────────────────────────────────────────────────
    print("\n[BC] Collecting greedy game data ...")
    obs_arr, action_arr = collect_bc_data(BC_EPISODES)
    print(f"  Dataset: {obs_arr.shape[0]} steps, obs_dim={obs_arr.shape[1]}, "
          f"action shape={action_arr.shape}")

    print("\n[BC] Building initial model ...")
    vec_env = make_vec_env(make_env_solo, n_envs=N_ENVS, vec_env_cls=SubprocVecEnv, vec_env_kwargs={"start_method": "fork"})
    vec_env = VecNormalize(vec_env, norm_obs=False, norm_reward=True, gamma=0.99)
    model = PPO(PointerActorCriticPolicy, vec_env, **PPO_KWARGS)
    print(f"  obs_dim={model.observation_space.shape[0]}")
    print(f"  action_space={model.action_space}")
    total_params = sum(p.numel() for p in model.policy.parameters())
    print(f"  model params: {total_params:,}")

    print("\n[BC] Training pointer network with teacher-forcing ...")
    bc_pretrain(model, obs_arr, action_arr)

    bc_path = os.path.join(MODEL_DIR, "v3_bc")
    model.save(bc_path)
    vec_env.save(bc_path + "_vecnorm.pkl")
    export_onnx(model, bc_path)

    print("\n[BC] Evaluating BC policy ...")
    evaluate(model, [])
    ppo1_steps = PPO_STEPS_SOLO

# ── Step 2: PPO solo ───────────────────────────────────────────────────────────

print("\n[PPO-1] Solo fine-tuning ...")
t0 = time.perf_counter()
model.learn(total_timesteps=ppo1_steps, progress_bar=False,
            reset_num_timesteps=not RESUME,
            callback=WinRateCallback(opponent_types=[], n_eval=100))
print(f"  Done in {time.perf_counter()-t0:.0f}s")

solo_path = os.path.join(MODEL_DIR, "v3_solo")
model.save(solo_path)
vec_env.save(solo_path + "_vecnorm.pkl")
export_onnx(model, solo_path)
if not RESUME:
    vec_env.close()

print("\n[PPO-1] Evaluating ...")
evaluate(model, [])

# ── Step 3: PPO vs greedy ──────────────────────────────────────────────────────

if RESUME:
    vec_env.close()

print("\n[PPO-2] Fine-tuning vs greedy ...")

# Mix greedy and solo envs 50/50 to prevent catastrophic forgetting:
# greedy envs push the model to race; solo envs anchor navigation ability.
# Lower LR (1e-4 vs 3e-4) also reduces forgetting.
N_GREEDY = N_ENVS // 2
N_SOLO2  = N_ENVS - N_GREEDY

def make_env_greedy():
    return PirateEnv(mapfile=MAPS[0], max_rounds=MAX_ROUNDS,
                     weights=RACE_WEIGHTS, opponent_types=["greedy"],
                     max_opponents=1, ncardsavail_options=NCARDSAVAIL_OPTIONS,
                     ncardslots=NCARDSLOTS, max_ncardsavail=MAX_NCARDSAVAIL,
                     mapfiles=MAPS)

def make_env_solo2():
    return PirateEnv(mapfile=MAPS[0], max_rounds=MAX_ROUNDS,
                     weights=SOLO_WEIGHTS, max_opponents=1,
                     ncardsavail_options=NCARDSAVAIL_OPTIONS, ncardslots=NCARDSLOTS,
                     max_ncardsavail=MAX_NCARDSAVAIL, mapfiles=MAPS)

vec_env2 = SubprocVecEnv([make_env_greedy] * N_GREEDY + [make_env_solo2] * N_SOLO2, start_method="fork")
vec_env2 = VecNormalize.load(solo_path + "_vecnorm.pkl", venv=vec_env2)
vec_env2.training = True
model.set_env(vec_env2)
# Lower LR prevents large weight updates that overwrite navigation skills.
model.learning_rate = 1e-4
model.policy.optimizer.param_groups[0]["lr"] = 1e-4

t0 = time.perf_counter()
model.learn(total_timesteps=PPO_STEPS_GREEDY, progress_bar=False,
            reset_num_timesteps=False,
            callback=WinRateCallback(opponent_types=["greedy"], n_eval=100))
print(f"  Done in {time.perf_counter()-t0:.0f}s")

final_path = os.path.join(MODEL_DIR, "v3_vs_greedy")
model.save(final_path)
vec_env2.save(final_path + "_vecnorm.pkl")
export_onnx(model, final_path)
vec_env2.close()

print("\n[PPO-2] Final evaluation ...")
evaluate(model, [])
evaluate(model, ["greedy"])

print("\n=== Training complete ===")
print(f"Deploy: cp {final_path}.onnx {MODEL_DIR}/solo_map1.onnx")
