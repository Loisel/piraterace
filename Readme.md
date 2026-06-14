# PirateRace

PirateRace is a turn based multiplayer 2D tile game with a nasty random fate component. You compete with other pirates for the gold treasure your great great grand-father has hidden on a remote island. Plan your next moves and trash your opponents. But beware, fate might strike any time to ruin your carefully planned treasure hunt.

## Technologies

- Backend: Python, Django
- Frontend: Ionic + Angular + Phaser
- Hosting: Nginx
- Deployment: Terraform, Ansible, docker-compose

## Developer Setup

### Initialize Containers

```
docker-compose pull
docker-compose build
```

### Start all components

```
docker-compose down
maint/backend_collectstatic.sh
maint/backend_migrate.sh
maint/frontend_npm_install.sh
docker-compose up -d
```

### Open the game

The game is running under the nginx which forwards all calls to the correct backends.

http://localhost:1337

## RL Bot

PirateRace ships an AI bot trained with Proximal Policy Optimisation (PPO) that navigates toward checkpoints and competes against human players. This section explains how it works and how to train or retrain it.

### How it works

Each game round the bot receives an **observation** and outputs an **action**:

| Observation segment | Size | Content |
|---|---|---|
| Agent state | 9 | Position (normalised), heading (sin/cos), health, checkpoint progress, vector to next checkpoint, round fraction |
| Hand of cards | `ncardslots × 9` | One-hot card type (8 bits) + normalised rank |
| Map layout | `W × H × 9` | Per-tile: collision, void, current x/y, vortex, damage, turret x/y, fast-current |
| Opponent state | `max_opponents × 8` | Per opponent: position, heading, health, checkpoint progress, vector to their next checkpoint |

The **action** is a vector of 8 floats — one preference score per card type (fwd1/2/3, back1, rotL/R/180, repair). The hand is sorted so the most-preferred card type plays first, with ties broken by rank. This gives the policy a consistent semantic that transfers across different hands — "prefer fwd3 here" means the same thing regardless of which specific cards were dealt.

At inference time the policy is an ONNX file (`pigame/rl_models/solo_map1.onnx`) loaded by `onnxruntime` — no PyTorch required in the container.

### Curriculum training

Training in three stages significantly outperforms training against the final opponent directly:

```
Stage 1 — Solo navigation
  The bot learns to reach checkpoints without any competition.
  No distracting collision dynamics; reward signal is clean.

Stage 2 — vs Random bot
  Introduces a second player. The bot learns that another ship
  exists, can block it, and that speed matters.

Stage 3 — vs Greedy bot
  The greedy bot plays near-optimally for its own navigation.
  The RL bot learns to race under pressure.
```

All three stages use `max_opponents=1` so the observation shape (386 for map1) stays constant and stage 2 can resume stage 1's weights rather than starting from scratch.

### Training setup (runs on host, not inside Docker)

Install the RL dependencies — these are heavy and kept off the main `requirements.txt`:

```bash
# Install PyTorch, gymnasium, stable-baselines3 on the host
pip install gymnasium stable-baselines3 torch onnxruntime onnxscript
```

The training scripts read map files directly from `backend/static/maps/` and use a local in-memory cache instead of Redis.

### Running the curriculum

Run all three stages with the management command:

```bash
cd backend

# Stage 1 — 2M solo steps (~30 min on 8-core CPU)
python manage.py train_rl_bot \
    --steps 2000000 \
    --out pigame/rl_models/curriculum_stage1

# Stage 2 — 1M steps vs random, resuming from stage 1
python manage.py train_rl_bot \
    --steps 1000000 --opponents random \
    --resume pigame/rl_models/curriculum_stage1 \
    --out pigame/rl_models/curriculum_stage2

# Stage 3 — 1M steps vs greedy, resuming from stage 2
python manage.py train_rl_bot \
    --steps 1000000 --opponents greedy \
    --resume pigame/rl_models/curriculum_stage2 \
    --out pigame/rl_models/curriculum_stage3
```

Each stage automatically exports an ONNX file alongside the `.zip`. After all three stages, deploy the final model:

```bash
cp pigame/rl_models/curriculum_stage3.onnx      pigame/rl_models/solo_map1.onnx
cp pigame/rl_models/curriculum_stage3.onnx.data pigame/rl_models/solo_map1.onnx.data
docker compose restart backend
```

Or run all three stages in one shot (runs overnight):

```bash
python /tmp/train_curriculum.py   # see the script for the full pipeline
```

### Training on a different map

```bash
python manage.py train_rl_bot \
    --map the_hammer.json \
    --steps 2000000 \
    --out pigame/rl_models/hammer_stage1
```

The model will be deployed automatically as `solo_<mapfile-stem>` unless `--out` is given. To use it in-game, select "RL Bot" in the game config — it loads the ONNX model matching the game's map.

### Evaluation

```bash
python manage.py train_rl_bot \
    --eval-only pigame/rl_models/solo_map1 \
    --games 200
```

To compare bots head-to-head, use the `run_bot_eval` command:

```bash
python manage.py run_bot_eval \
    --bots rl greedy random \
    --map map1.json \
    --games 200
```

### Key files

| File | Purpose |
|---|---|
| `pigame/rl_env.py` | Gymnasium environment — observation, action space, reward |
| `pigame/bots.py` | `_rl_pick()` — loads ONNX, builds obs, returns sorted hand |
| `pigame/management/commands/train_rl_bot.py` | Django management command for training |
| `pigame/rl_models/solo_map1.onnx` | Trained policy (gitignored — generate locally) |
| `requirements-rl.txt` | Extra deps for training (not needed at runtime) |

### Reward weights

Two presets in `rl_env.py` control bot personality:

| Weight | Solo | Race | Effect |
|---|---|---|---|
| `distance` | 1.0 | 1.0 | reward per tile closer to next checkpoint |
| `checkpoint` | 5.0 | 5.0 | flat reward per checkpoint reached |
| `win` | 20.0 | 20.0 | reward for clearing all checkpoints |
| `damage_taken` | −0.5 | −0.5 | penalty per HP lost |
| `time` | −0.01 | −0.01 | encourages speed |
| `win_race` | 0 | **10.0** | bonus for finishing before opponents |
| `lose_race` | 0 | **−5.0** | penalty when an opponent finishes first |
| `lead_bonus` | 0 | **0.3** | per checkpoint ahead of each opponent |

Use `SOLO_WEIGHTS` for stage 1, `RACE_WEIGHTS` for stages 2 and 3. Swap in `IMPULSIVE_WEIGHTS` to train a bot that values shooting and pushing opponents over winning — more fun to play against.

## Cloud Deployment

The game is hosted on hetzner cloud ( https://www.hetzner.com/cloud ) with the following environments:

- (WORK IN PROGRESS) dev.piraterace.com : Development Environment
- (TODO LATER) piraterace.com : Production Environment

It consists of 1 vserver per environment which contains the full stack (database, backend, frontend, etc.). If this setup does not satisfy the requirements any more we can always scale out.

### Overview

#### Technologies

* Terraform ( https://www.terraform.io/ ) is an infrastructure as code tool that lets you create cloud servers and other resources via a configuration language.
* Ansible ( https://www.ansible.com/ ) Ansible is a configuration management software which works with yaml-files to setup a certain server state.

#### Infrastructure as code

* `deployment/terraform` : contains the terraform modules (currently just 1 module, called piraterace) and the terraform_wrapper.sh (automatically downloads the correct terraform version if nonexistant)
* `deployment/ansible` : contains ansible playbooks, configuration and hosts files

### Terraform

Check out the repository which contains this README here on any machine with internet access (e.g. your laptop) and run the following commands. The commands are all idempotent, you can run them as often as you want to ensure the cloud state matches the configuration. The terraform_wrapper.sh script will download the correct terraform version, if it has not been downloaded already (works on Linux x86_64). Otherwise you can install terraform yourself and use it directly.

```
# Switch to the correct terraform module
cd deployment/terraform/piraterace

# Initialize terraform plugins, etc. -> it is safe to run this command everytime, but it is only needed to be run once or if plugins change, terraform will prompt you if the command needs to be run 
../terraform_wrapper.sh init

# Check what changes need to be performed and then apply those changes. If no changes need to be performed the configuration already matches the state in the cloud.
../terraform_wrapper.sh apply
```

### Ansible

Ansible configures servers to match a certain desired state. The commands are idempotent, you can run them as often as you like to ensure the state matches the configuration of the yaml files. Run them from a machine with internet access (e.g. your laptop).

The playbook will install docker and docker-compose, setup let's encrypt and will start piraterace.

(currently only the installation of docker + docker-compose is implemented)

```
# Install the ansible binary
sudo apt install ansible

cd deployment/ansible
ansible-playbook -i hosts playbooks/piraterace-dev.yaml
```
