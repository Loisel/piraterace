"""
Autoregressive Pointer Network for PirateRace card selection.

Architecture (Vinyals et al. 2015, NeurIPS):
  Encoder  : MLP on scalar obs + per-card MLP on each card's 13-d features
             (including the path-preview value).  Output = initial decoder context.
  Decoder  : ncardslots sequential pointer steps.  At each step:
               scaled dot-product attention → categorical distribution over
               still-available cards → sample (or argmax for inference) →
               GRUCell updates context with the selected card's encoding.
  Log-prob : sum of ncardslots per-step categorical log-probs — the correct
             joint probability accounting for prior selections (no duplicates).

Why this beats flat MLP:
  - MLP scores each card independently (no conditioning on what's already picked)
  - Pointer network at step k knows which cards were picked at steps 0..k-1 via
    the GRU hidden state; this is the right inductive bias for permutation tasks.

Used by:
  train_v3.py — BC teacher forcing + PPO fine-tuning
  bots.py     — deterministic inference via ONNX export
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple

from stable_baselines3.common.policies import ActorCriticPolicy


CARD_FEATURES = 13   # per-card obs features (12 type one-hot + 1 rank)
N_STATE       = 9    # scalar state features at start of obs


class PointerDecoder(nn.Module):
    """
    Encoder + autoregressive pointer decoder.

    encode(obs)             → context, card_enc, card_keys, value
    forward_sample(obs)     → actions, log_probs, entropy, value   (for rollouts)
    evaluate_actions(obs, a)→ log_probs, entropy, value            (for PPO updates / BC)
    """

    def __init__(self, obs_dim: int, ncardsavail: int, ncardslots: int,
                 hidden_dim: int = 256, card_dim: int = 64):
        super().__init__()
        self.obs_dim     = obs_dim
        self.ncardsavail = ncardsavail
        self.ncardslots  = ncardslots
        self.hidden_dim  = hidden_dim
        self.card_dim    = card_dim

        # Scalar obs encoder: state(9) + preview(nca) + greedy_slot(nca) + opp(*8)
        # (raw per-card type vectors are encoded separately below)
        scalar_obs_dim = obs_dim - ncardsavail * CARD_FEATURES
        self.obs_encoder = nn.Sequential(
            nn.Linear(scalar_obs_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),     nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),     nn.ReLU(),
        )

        # Per-card encoder: CARD_FEATURES (13) + preview (1) + greedy_slot (1) → card_dim
        self.card_encoder = nn.Sequential(
            nn.Linear(CARD_FEATURES + 2, card_dim), nn.ReLU(),
            nn.Linear(card_dim, card_dim),           nn.ReLU(),
        )

        # Project card encodings to the attention key space
        self.key_proj = nn.Linear(card_dim, hidden_dim, bias=False)

        # Context update: MLP projection of (context ‖ selected_card_enc).
        # Avoids GRUCell whose internal chunk() op breaks TorchScript ONNX export.
        self.ctx_update = nn.Sequential(
            nn.Linear(hidden_dim + card_dim, hidden_dim), nn.ReLU(),
        )

        # Value head on initial context (separate from actor)
        self.value_head = nn.Sequential(
            nn.Linear(hidden_dim, 128), nn.ReLU(),
            nn.Linear(128, 1),
        )

    # ── internal helpers ─────────────────────────────────────────────────────

    def encode(self, obs: torch.Tensor
               ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Split obs into components and encode.

        obs layout: [state(9)] [cards(nca×13)] [preview(nca)] [greedy_slot(nca)] [opp(*8)]

        greedy_slot[i] = rank of card i when sorted by preview score, normalised
        to [0, 1] (0 = best card by solo preview, 1 = worst).  Gives the pointer
        network an explicit multi-step-quality signal per card without extra sims.

        Returns:
          context   (B, hidden_dim)      — initial decoder hidden state
          card_enc  (B, nca, card_dim)   — per-card encodings (for GRU input)
          card_keys (B, nca, hidden_dim) — attention keys
          value     (B,)                 — critic estimate
        """
        B   = obs.shape[0]
        nca = self.ncardsavail
        CF  = CARD_FEATURES

        state      = obs[:, :N_STATE]
        cards_flat = obs[:, N_STATE : N_STATE + nca * CF]
        preview    = obs[:, N_STATE + nca * CF : N_STATE + nca * CF + nca]
        greedy_sl  = obs[:, N_STATE + nca * CF + nca : N_STATE + nca * CF + 2 * nca]
        opp        = obs[:, N_STATE + nca * CF + 2 * nca:]

        # Scalar context: state + preview + greedy_slot + opp
        scalar  = torch.cat([state, preview, greedy_sl, opp], dim=1)
        context = self.obs_encoder(scalar)                      # (B, hidden)

        # Per-card: combine 13-d type/rank vector with preview and greedy_slot
        cards_2d  = cards_flat.view(B, nca, CF)                 # (B, nca, 13)
        prev_2d   = preview.unsqueeze(2)                        # (B, nca,  1)
        gslot_2d  = greedy_sl.unsqueeze(2)                     # (B, nca,  1)
        card_in   = torch.cat([cards_2d, prev_2d, gslot_2d], dim=2)  # (B, nca, 15)
        card_enc  = self.card_encoder(card_in)                  # (B, nca, card_dim)
        card_keys = self.key_proj(card_enc)                     # (B, nca, hidden)

        value = self.value_head(context).squeeze(-1)            # (B,)
        return context, card_enc, card_keys, value

    def _attend(self, context: torch.Tensor, card_keys: torch.Tensor,
                available: torch.Tensor) -> torch.Tensor:
        """Scaled dot-product attention. Unavailable cards → -inf logit."""
        scale  = math.sqrt(self.hidden_dim)
        scores = (card_keys * context.unsqueeze(1)).sum(-1) / scale  # (B, nca)
        return scores.masked_fill(~available, float('-inf'))

    def _select_and_update(self, context, card_enc, card_keys, available, sel):
        """Update mask and GRU context after selecting card index `sel` (B,)."""
        B   = context.shape[0]
        # Mask out the selected card
        sel_oh   = F.one_hot(sel, self.ncardsavail).bool()      # (B, nca)
        available = available & ~sel_oh
        # Gather selected card's encoding and update GRU context
        idx      = sel.view(B, 1, 1).expand(B, 1, self.card_dim)
        sel_enc  = card_enc.gather(1, idx).squeeze(1)           # (B, card_dim)
        context  = self.ctx_update(torch.cat([context, sel_enc], dim=1))
        return context, available

    # ── public forward methods ────────────────────────────────────────────────

    def _real_card_mask(self, obs: torch.Tensor) -> torch.Tensor:
        """
        Detect which card slots are real (non-padding) from the observation.

        Real cards have at least one non-zero feature (their type one-hot is 1.0).
        Padding slots are entirely zero.  Returns bool (B, ncardsavail).
        """
        B   = obs.shape[0]
        nca = self.ncardsavail
        cards_2d = obs[:, N_STATE : N_STATE + nca * CARD_FEATURES].view(B, nca, CARD_FEATURES)
        return cards_2d.abs().sum(dim=2) > 0   # True = real card

    def forward_sample(self, obs: torch.Tensor, deterministic: bool = False
                       ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Autoregressive rollout (used during PPO rollout collection).

        Returns:
          actions   (B, ncardslots) long  — selected card indices in play order
          log_probs (B,)                  — sum of per-step log P(a_k | prev)
          entropy   (B,)                  — sum of per-step entropies
          value     (B,)
        """
        B = obs.shape[0]
        context, card_enc, card_keys, value = self.encode(obs)
        available = self._real_card_mask(obs)   # only real (non-padding) cards
        actions_out   = torch.zeros(B, self.ncardslots, dtype=torch.long,  device=obs.device)
        log_probs_sum = torch.zeros(B, device=obs.device)
        entropy_sum   = torch.zeros(B, device=obs.device)

        for k in range(self.ncardslots):
            logits = self._attend(context, card_keys, available)
            dist   = torch.distributions.Categorical(logits=logits)
            sel    = logits.argmax(dim=-1) if deterministic else dist.sample()

            log_probs_sum = log_probs_sum + dist.log_prob(sel)
            entropy_sum   = entropy_sum   + dist.entropy()
            actions_out[:, k] = sel

            context, available = self._select_and_update(
                context, card_enc, card_keys, available, sel
            )

        return actions_out, log_probs_sum, entropy_sum, value

    def evaluate_actions(self, obs: torch.Tensor, actions: torch.Tensor
                         ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Teacher-forced evaluation (used by PPO train() and BC pretraining).

        actions : (B, ncardslots) long — expert/stored card indices.
        Returns : log_probs (B,), entropy (B,), value (B,)
        """
        B = obs.shape[0]
        context, card_enc, card_keys, value = self.encode(obs)
        available     = self._real_card_mask(obs)   # only real (non-padding) cards
        log_probs_sum = torch.zeros(B, device=obs.device)
        entropy_sum   = torch.zeros(B, device=obs.device)

        for k in range(self.ncardslots):
            logits = self._attend(context, card_keys, available)
            dist   = torch.distributions.Categorical(logits=logits)
            sel    = actions[:, k]

            log_probs_sum = log_probs_sum + dist.log_prob(sel)
            entropy_sum   = entropy_sum   + dist.entropy()

            context, available = self._select_and_update(
                context, card_enc, card_keys, available, sel
            )

        return log_probs_sum, entropy_sum, value


# ── ONNX-compatible deterministic wrapper ─────────────────────────────────────

class PointerOnnxWrapper(nn.Module):
    """
    Thin wrapper around PointerDecoder for ONNX export.

    Unrolls ncardslots pointer steps deterministically (argmax at each step).
    Uses only ONNX-compatible ops: gather, one_hot, boolean masking, Linear+ReLU.

    Input:  obs  (1, obs_dim) float32
    Output: card_indices  (1, ncardslots) float32  — indices into the hand
    """

    def __init__(self, pointer: PointerDecoder):
        super().__init__()
        self.pointer = pointer

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        B   = obs.shape[0]
        p   = self.pointer
        ctx, enc, keys, _ = p.encode(obs)
        avail = p._real_card_mask(obs)

        indices = []
        for _ in range(p.ncardslots):
            logits = p._attend(ctx, keys, avail)
            sel    = logits.argmax(dim=-1)                           # (B,)
            indices.append(sel.float())
            sel_oh = F.one_hot(sel, p.ncardsavail).bool()
            avail  = avail & ~sel_oh
            idx    = sel.view(B, 1, 1).expand(B, 1, p.card_dim)
            sel_enc = enc.gather(1, idx).squeeze(1)
            ctx    = p.ctx_update(torch.cat([ctx, sel_enc], dim=1))

        return torch.stack(indices, dim=1)                           # (B, ncardslots)


# ── SB3 policy wrapper ────────────────────────────────────────────────────────

class PointerActorCriticPolicy(ActorCriticPolicy):
    """
    SB3 ActorCriticPolicy that delegates all actor/critic work to PointerDecoder.

    Compatible with MultiDiscrete([ncardsavail] * ncardslots) action space.

    Override approach:
      _build()          — build PointerDecoder instead of MLP actor/critic
      forward()         — autoregressive sampling (for rollout collection)
      evaluate_actions()— teacher-forced evaluation (for PPO update step)
      predict_values()  — critic bootstrap at rollout end
      _predict()        — deterministic argmax (for model.predict() eval calls)
    """

    def __init__(self, observation_space, action_space, lr_schedule,
                 ncardsavail: int, ncardslots: int,
                 hidden_dim: int = 256, card_dim: int = 64, **kwargs):
        self._ptr_nca    = ncardsavail
        self._ptr_ncs    = ncardslots
        self._ptr_hidden = hidden_dim
        self._ptr_card   = card_dim
        kwargs.pop('net_arch',      None)
        kwargs.pop('activation_fn', None)
        super().__init__(
            observation_space, action_space, lr_schedule,
            net_arch=[], activation_fn=nn.Tanh,
            **kwargs,
        )

    def _build(self, lr_schedule) -> None:
        """Build PointerDecoder instead of the default MLP extractor + heads."""
        self.features_extractor = self.make_features_extractor()
        self.features_dim       = self.features_extractor.features_dim

        self.pointer = PointerDecoder(
            obs_dim     = self.features_dim,
            ncardsavail = self._ptr_nca,
            ncardslots  = self._ptr_ncs,
            hidden_dim  = self._ptr_hidden,
            card_dim    = self._ptr_card,
        )

        # Placeholders so that SB3 internals that inspect these attrs don't break.
        # None of the overridden forward methods actually call them.
        # log_std is intentionally NOT set — PPO.train() checks hasattr(policy, "log_std")
        # and tries to exp() it; leaving it absent skips that logging branch.
        self.mlp_extractor = nn.Identity()
        self.action_net    = nn.Identity()
        self.value_net     = nn.Identity()

        self.optimizer = self.optimizer_class(
            self.parameters(), lr=lr_schedule(1), **self.optimizer_kwargs
        )

    # ── mandatory SB3 interface ───────────────────────────────────────────────

    def forward(self, obs: torch.Tensor, deterministic: bool = False
                ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Rollout collection: returns (actions, values, log_probs)."""
        feats = self.extract_features(obs, self.features_extractor)
        actions, log_probs, _, values = self.pointer.forward_sample(feats, deterministic)
        return actions.float(), values.unsqueeze(-1), log_probs

    def evaluate_actions(self, obs: torch.Tensor, actions: torch.Tensor
                         ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """PPO update: returns (values, log_probs, entropy)."""
        feats = self.extract_features(obs, self.features_extractor)
        log_probs, entropy, values = self.pointer.evaluate_actions(
            feats, actions.long()
        )
        return values.unsqueeze(-1), log_probs, entropy.mean()

    def predict_values(self, obs: torch.Tensor) -> torch.Tensor:
        feats = self.extract_features(obs, self.features_extractor)
        _, _, _, values = self.pointer.forward_sample(feats, deterministic=True)
        return values.unsqueeze(-1)

    def _predict(self, observation: torch.Tensor, deterministic: bool = False
                 ) -> torch.Tensor:
        feats = self.extract_features(observation, self.features_extractor)
        actions, _, _, _ = self.pointer.forward_sample(feats, deterministic)
        return actions.float()

    def get_distribution(self, obs: torch.Tensor):
        raise NotImplementedError("PointerActorCriticPolicy uses forward() directly")
