"""
Custom SB3 features extractor for PirateRace.

Observation layout (set by PirateEnv):
    obs = [scalar_prefix | ego_crop_suffix]

scalar_prefix  = state(9) + cards(ncardslots×9) + opp(max_opponents×8)
ego_crop_suffix = CROP_SIZE × CROP_SIZE × N_TILE_PROPS  (flattened, row-major)

The extractor processes the spatial crop with a small CNN and the scalar
features with a linear layer, then combines them into a fixed features_dim
vector that SB3's actor-critic head sees.
"""

import torch
import torch.nn as nn
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
