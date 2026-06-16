"""
Custom SB3 features extractors for PirateRace.

Observation layout (set by PirateEnv):
    obs = [scalar_prefix | ego_crop_suffix]

scalar_prefix  = state(9) + cards(ncardslots×9) + opp(max_opponents×8)
ego_crop_suffix = CROP_SIZE × CROP_SIZE × N_TILE_PROPS  (flattened, row-major)

Two extractors are provided:

PirateCNNExtractor:
    CNN crop + scalar MLP → combined features_dim vector.
    Used with action space (N_CARD_TYPES,) — type preference scoring.

PirateAttentionExtractor:
    Per-card self-attention + CNN cross-attention → flat features vector.
    Used with action space (ncardslots,) — direct per-card priority scoring.
    Recommended: policy_kwargs net_arch=dict(pi=[], vf=[256,128]) so the
    policy head directly scores cards while the value head uses an MLP.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor

from pigame.rl_env import CROP_SIZE, N_TILE_PROPS, N_CROP_FEATS


class PirateCNNExtractor(BaseFeaturesExtractor):
    """
    Splits flat obs into scalar features and the ego-centric spatial crop.

    CNN processes the CROP_SIZE×CROP_SIZE×N_TILE_PROPS spatial crop.
    Three conv layers with stride-2 downsampling compress 21×21 → 4×4.
    A linear head processes the scalar prefix.
    Both representations are concatenated and projected to features_dim.

    Constructor kwargs (pass via policy_kwargs["features_extractor_kwargs"]):
        n_scalar   (int) : length of the scalar prefix in the obs vector
        features_dim (int) : output dimension (default 256)
    """

    def __init__(self, observation_space, n_scalar: int, features_dim: int = 256):
        super().__init__(observation_space, features_dim=features_dim)

        self.n_scalar = n_scalar

        # CNN: 21×21 → 10×10 → 4×4
        self.cnn = nn.Sequential(
            nn.Conv2d(N_TILE_PROPS, 32, kernel_size=3, padding=1),   # (32, 21, 21)
            nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=3, stride=2),              # (64, 10, 10)
            nn.ReLU(),
            nn.Conv2d(64, 64, kernel_size=3, stride=2),              # (64,  4,  4)
            nn.ReLU(),
            nn.Flatten(),                                             # 64*4*4 = 1024
        )
        with torch.no_grad():
            dummy = torch.zeros(1, N_TILE_PROPS, CROP_SIZE, CROP_SIZE)
            cnn_out_dim = self.cnn(dummy).shape[1]

        # Scalar head
        self.scalar_net = nn.Sequential(
            nn.Linear(n_scalar, 128),
            nn.ReLU(),
        )

        # Combine CNN + scalar → features_dim
        self.combine = nn.Sequential(
            nn.Linear(cnn_out_dim + 128, features_dim),
            nn.ReLU(),
        )

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        scalar = obs[:, :self.n_scalar]
        crop_flat = obs[:, self.n_scalar:]  # shape (B, N_CROP_FEATS)

        B = crop_flat.shape[0]
        # Reshape to (B, H, W, C) → permute to (B, C, H, W) for Conv2d
        crop_2d = crop_flat.view(B, CROP_SIZE, CROP_SIZE, N_TILE_PROPS)
        crop_2d = crop_2d.permute(0, 3, 1, 2).contiguous()

        cnn_feat    = self.cnn(crop_2d)
        scalar_feat = self.scalar_net(scalar)

        return self.combine(torch.cat([cnn_feat, scalar_feat], dim=1))


class PirateAttentionExtractor(BaseFeaturesExtractor):
    """
    Attention-based features extractor for per-card priority scoring.

    Each card in the hand attends to every other card (self-attention) and
    receives injected spatial + global-state context.  The output is:

        [spatial_ctx(CNN_DIM) | global_ctx(GLOBAL_DIM) | card0..cardN(CARD_HIDDEN each)]

    Flatten shape = CNN_DIM + GLOBAL_DIM + n_cards × CARD_HIDDEN = 640 (for 5 cards).

    Recommended policy_kwargs:
        net_arch=dict(pi=[], vf=[256, 128])

    This gives the policy head a direct Linear(640 → ncardslots) — one score
    per card — while the value head uses a deeper MLP for global state estimation.

    Constructor kwargs (pass via policy_kwargs["features_extractor_kwargs"]):
        n_scalar  (int) : length of scalar prefix (state + cards + opp)
        n_cards   (int) : number of cards in the hand (= ncardslots)
    """

    CARD_DIM    = 9    # features per card in obs
    CNN_DIM     = 256  # spatial context output
    GLOBAL_DIM  = 64   # state + opp context
    CARD_HIDDEN = 64   # per-card hidden dim
    STATE_DIM   = 9    # state features before the card block

    def __init__(self, observation_space, n_scalar: int, n_cards: int,
                 n_attn_heads: int = 4):
        features_dim = self.CNN_DIM + self.GLOBAL_DIM + n_cards * self.CARD_HIDDEN
        super().__init__(observation_space, features_dim=features_dim)

        self.n_scalar  = n_scalar
        self.n_cards   = n_cards
        self.card_end  = self.STATE_DIM + n_cards * self.CARD_DIM

        # CNN for ego-centric crop: 21×21 → 10×10 → 4×4 → 1024 → CNN_DIM
        self.cnn = nn.Sequential(
            nn.Conv2d(N_TILE_PROPS, 32, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv2d(32, 64, kernel_size=3, stride=2),
            nn.ReLU(),
            nn.Conv2d(64, 64, kernel_size=3, stride=2),
            nn.ReLU(),
            nn.Flatten(),
        )
        with torch.no_grad():
            cnn_raw = self.cnn(torch.zeros(1, N_TILE_PROPS, CROP_SIZE, CROP_SIZE)).shape[1]
        self.cnn_proj = nn.Sequential(nn.Linear(cnn_raw, self.CNN_DIM), nn.ReLU())

        # Global context: state(9) + opp block
        n_state_opp = n_scalar - n_cards * self.CARD_DIM
        self.global_net = nn.Sequential(nn.Linear(n_state_opp, self.GLOBAL_DIM), nn.ReLU())

        # Per-card encoder (weights shared across all card positions)
        self.card_enc = nn.Sequential(nn.Linear(self.CARD_DIM, self.CARD_HIDDEN), nn.ReLU())

        # Context injection: project [spatial, global] into card space
        self.ctx_proj = nn.Linear(self.CNN_DIM + self.GLOBAL_DIM, self.CARD_HIDDEN)

        # Self-attention: cards attend to each other
        self.self_attn = nn.MultiheadAttention(
            embed_dim=self.CARD_HIDDEN, num_heads=n_attn_heads,
            batch_first=True, dropout=0.0,
        )
        self.attn_norm = nn.LayerNorm(self.CARD_HIDDEN)

    def forward(self, obs: torch.Tensor) -> torch.Tensor:
        B = obs.shape[0]

        scalar   = obs[:, :self.n_scalar]
        crop_flat = obs[:, self.n_scalar:]

        # ── spatial path ──────────────────────────────────────────────────────
        crop_2d = crop_flat.view(B, CROP_SIZE, CROP_SIZE, N_TILE_PROPS)
        crop_2d = crop_2d.permute(0, 3, 1, 2).contiguous()
        spatial = self.cnn_proj(self.cnn(crop_2d))          # (B, CNN_DIM)

        # ── global state/opp path ─────────────────────────────────────────────
        state_vec  = scalar[:, :self.STATE_DIM]
        opp_vec    = scalar[:, self.card_end:]
        global_ctx = self.global_net(torch.cat([state_vec, opp_vec], dim=-1))  # (B, GLOBAL_DIM)

        # ── per-card path ─────────────────────────────────────────────────────
        card_block = scalar[:, self.STATE_DIM:self.card_end]
        cards      = card_block.view(B, self.n_cards, self.CARD_DIM)
        card_feats = self.card_enc(cards)                    # (B, n_cards, CARD_HIDDEN)

        # Inject context: each card sees where we are and the board state
        ctx     = torch.cat([spatial, global_ctx], dim=-1)  # (B, CNN_DIM + GLOBAL_DIM)
        ctx_inj = F.relu(self.ctx_proj(ctx)).unsqueeze(1)   # (B, 1, CARD_HIDDEN)
        card_feats = card_feats + ctx_inj                   # broadcast over n_cards

        # Self-attention: cards reason about each other
        attn_out, _ = self.self_attn(card_feats, card_feats, card_feats)
        card_feats  = self.attn_norm(card_feats + attn_out) # (B, n_cards, CARD_HIDDEN)

        # ── combine ───────────────────────────────────────────────────────────
        card_flat = card_feats.reshape(B, -1)               # (B, n_cards * CARD_HIDDEN)
        return torch.cat([spatial, global_ctx, card_flat], dim=-1)
        # (B, CNN_DIM + GLOBAL_DIM + n_cards*CARD_HIDDEN)
