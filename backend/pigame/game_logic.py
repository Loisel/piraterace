import json
import os
import random
import types
from django.core.cache import cache

from piraterace.settings import MAPSDIR
from piplayer.models import Account
from pigame.models import (
    add_repair_cards,
    card_id_rank,
    CARDS,
    DEFAULT_DECK,
    DIRID2MOVE,
    DIRID2NAME,
    FREE_HEALTH_OFFSET,
    CANNON_DIRECTION,
    CANNON_DIRECTION_CARDS,
)

BACKEND_USERID = -1
ROUNDEND_CARDID = -1
POWER_DOWN_CARDID = -2
BOARD_CANNON_PLAYERID = -1
SKIP_CARDID = -999          # Odysseus Curse: slot played but has no effect

ODYSSEUS_CURSE_LEAD = 2     # checkpoints ahead of every other player to trigger curse
ODYSSEUS_CURSE_SLOTS = 2    # number of card slots removed by the curse

TILE_DEFAULTS = {
    "collision": False,
    "current_x": 0,
    "current_y": 0,
    "damage": 0,
    "void": False,
    "vortex": 0,
    "turret_x": 0,
    "turret_y": 0,
    "fast_current": False,
}

UPGRADE_TYPES = {
    "burning_cannons": {"name": "Burning Cannons"},
    "shield": {"name": "Shield", "charges": 3},
    "checkpoint_rush": {"name": "Checkpoint Rush"},
    "ghost_ship": {"name": "Ghost Ship"},
    "solid_rock": {"name": "Solid as a Rock"},
    "carpenter": {"name": "Carpenter"},
    "shipwright": {"name": "Shipwright"},
    "rose_cannons": {"name": "Rose Cannons"},
}
TREASURES_PER_ROUND_DEFAULT = 2.0


def argsort(seq):
    return sorted(range(len(seq)), key=seq.__getitem__)


def is_player_cursed(player_id, player_states):
    """True if player is ODYSSEUS_CURSE_LEAD+ checkpoints ahead of every other player."""
    if len(player_states) < 2:
        return False
    me = player_states[player_id]
    others = [p.next_checkpoint for pid, p in player_states.items() if pid != player_id]
    return bool(others) and me.next_checkpoint >= max(others) + ODYSSEUS_CURSE_LEAD


def flatten_list_of_tuples(lot):
    return [i for j in lot for i in j]


def is_plain_water(tile_props):
    return (
        not tile_props.get("collision", False)
        and not tile_props.get("void", False)
        and tile_props.get("vortex", 0) == 0
        and tile_props.get("turret_x", 0) == 0
        and tile_props.get("turret_y", 0) == 0
        and tile_props.get("damage", 0) == 0
        and tile_props.get("current_x", 0) == 0
        and tile_props.get("current_y", 0) == 0
    )


def compute_round_treasures(game_id, round_num, gmap, occupied_positions, rate=None):
    if rate is None:
        rate = TREASURES_PER_ROUND_DEFAULT
    # Fractional rates: 0.5 means one chest every 2 rounds, etc.
    if rate <= 0:
        return []
    if rate < 1:
        period = round(1.0 / rate)
        if round_num % period != 0:
            return []
        n_chests = 1
    else:
        n_chests = int(rate)
    rng = random.Random(game_id * 10000 + round_num)
    w, h = gmap["bg_width"], gmap["bg_height"]
    valid_tiles = [
        (x, y)
        for y in range(h)
        for x in range(w)
        if (x, y) not in occupied_positions and is_plain_water(gmap["tile_prop_cache"][y * w + x])
    ]
    if not valid_tiles:
        return []
    n = min(n_chests, len(valid_tiles))
    positions = rng.sample(valid_tiles, n)
    upgrade_keys = list(UPGRADE_TYPES.keys())
    return [
        {"x": x, "y": y, "upgrade": rng.choice(upgrade_keys), "id": f"r{round_num}_{x}_{y}"}
        for x, y in positions
    ]


def set_player_deck(gamecfg, playerid, deck):
    cachestr = f"player_deck_{gamecfg.pk}_{playerid}"
    cache.set(cachestr, deck, None)


def get_player_deck(gamecfg, playerid):
    cachestr = f"player_deck_{gamecfg.pk}_{playerid}"
    deck = cache.get(cachestr)
    if deck is None:
        deck = add_repair_cards(Account.objects.get(pk=playerid).deck, gamecfg.percentage_repaircards)
        random.shuffle(deck)
        cache.set(cachestr, deck, None)
    return deck


def get_cards_on_hand(gamecfg, playeridx, ncards):
    """
    get next ncards that a player can draw from his deck
        return list of tuples of (playerid, card)
    """
    next_card = gamecfg.player_next_card[playeridx]
    deck = get_player_deck(gamecfg, gamecfg.player_ids[playeridx])

    if next_card + ncards > len(deck):
        remaining_cards = deck[next_card:]
        old_cards = deck[:next_card]
        random.shuffle(old_cards)
        deck = remaining_cards + old_cards
        set_player_deck(gamecfg, gamecfg.player_ids[playeridx], deck)
        gamecfg.player_next_card[playeridx] = 0
        gamecfg.save(update_fields=["player_next_card"])
        next_card = gamecfg.player_next_card[playeridx]

    res = []
    for i in range(0, ncards):
        res.append((gamecfg.player_ids[playeridx], deck[next_card + i]))
    return res


def determine_next_cards_played(gamecfg):
    """
    returns the cards in order that they will be played in a game by participating players.
    ncardslots will be returned for each player
    returns list of (playerid, card) tuples
    """

    cards_per_player = [get_cards_on_hand(gamecfg, i, gamecfg.ncardslots) for i in range(len(gamecfg.player_ids))]

    # sort by ranking...
    ret = []
    for i in range(gamecfg.ncardslots):
        nth_cards = [pcards[i] for pcards in cards_per_player]  # i.e. for each player one card
        rankings = [card_id_rank(c)[1] for pid, c in nth_cards]
        for j in argsort(rankings)[::-1]:
            ret.append(nth_cards[j])

    return ret


def determine_starting_locations(initmap):
    for layer in initmap["layers"]:
        if layer["name"] == "startinglocs":
            positions = layer["objects"]
            break

    random.shuffle(positions)
    theight = initmap["tileheight"]
    twidth = initmap["tilewidth"]
    start_pos_x = []
    start_pos_y = []
    start_direction = []
    for p in positions:
        start_pos_x.append(int(p["x"] / twidth))
        start_pos_y.append(int(p["y"] / theight))
        start_direction.append(random.choice(list(DIRID2NAME.keys())))
    return start_pos_x, start_pos_y, start_direction


def startinglocs_pixels(initmap):
    """Get the starting coordinates in terms of pixels, boats centered."""
    locx, locy, direction = determine_starting_locations(initmap)
    pos = [((x + 0.5) * initmap["tilewidth"], (y + 0.5) * initmap["tileheight"]) for x, y in zip(locx, locy)]
    return pos


def determine_checkpoint_locations(initmap):
    for layer in initmap["layers"]:
        if layer["name"] == "checkpoints":
            positions = layer["objects"]
            break

    theight = initmap["tileheight"]
    twidth = initmap["tilewidth"]
    checkpoints = {}
    for pos in positions:
        checkpoints[int(pos["name"])] = (int(pos["x"] / twidth), int(pos["y"] / theight))
    return checkpoints


def play_stack(game, initial_upgrades=None):
    initial_map = load_map(game.config.mapfile)
    stack = game.cards_played

    players = {}
    for pid, x, y, direction, color, name in zip(
        game.config.player_ids,
        game.config.player_start_x,
        game.config.player_start_y,
        game.config.player_start_directions,
        game.config.player_colors,
        game.config.player_names,
    ):
        p = types.SimpleNamespace()
        p.id = pid
        p.name = name
        p.last_cp_x = x
        p.last_cp_y = y
        p.xpos = x
        p.ypos = y
        p.start_pos_x = x
        p.start_pos_y = y
        p.direction = direction
        p.start_direction = direction
        p.cannon_direction = CANNON_DIRECTION.FORWARD
        p.next_checkpoint = 1
        p.color = color
        p.health = game.config.ncardsavail + FREE_HEALTH_OFFSET
        p.powered_down = False
        players[pid] = p

    cardstack = list(zip(stack[::2], stack[1::2]))
    checkpoints = determine_checkpoint_locations(initial_map)

    actionstack = []
    player_upgrades = {pid: {} for pid in players}
    if initial_upgrades:
        for pid, upgrades in initial_upgrades.items():
            if pid in player_upgrades:
                player_upgrades[pid] = dict(upgrades)
    on_fire_pids = set()
    active_treasures = []
    current_round = 0

    Nplayercardsplayedthisround = 0
    powerdowncards = []
    activeCardSlot = 0
    for playerid, card in cardstack:
        if card == ROUNDEND_CARDID:
            current_round += 1
            activeCardSlot = 0

            # checkpoint detection
            for player in players.values():
                if (
                    (player.xpos == checkpoints[player.next_checkpoint][0])
                    and (player.ypos == checkpoints[player.next_checkpoint][1])
                    and (player.health > 0)
                ):
                    if player.next_checkpoint == len(checkpoints):
                        game.state = "end"
                        game.save(update_fields=["state"])
                        actionstack.append([dict(key="win", target=player.id)])
                    player.next_checkpoint += 1
                    player.last_cp_x = player.xpos
                    player.last_cp_y = player.ypos

            # treasure collection: players standing on a treasure tile collect it
            collection_actions = []
            collected_ids = set()
            for treasure in list(active_treasures):
                for player in players.values():
                    if player.health <= 0:
                        continue
                    if player.xpos == treasure["x"] and player.ypos == treasure["y"]:
                        collected_ids.add(treasure["id"])
                        upgrade = treasure["upgrade"]
                        collection_actions.append(
                            dict(key="treasure_collected", target=player.id, upgrade=upgrade,
                                 posx=treasure["x"], posy=treasure["y"], treasure_id=treasure["id"])
                        )
                        if upgrade == "shield":
                            player_upgrades[player.id]["shield"] = {"charges": UPGRADE_TYPES["shield"]["charges"]}
                        elif upgrade == "checkpoint_rush":
                            player.next_checkpoint += 1
                            if player.next_checkpoint > len(checkpoints):
                                game.state = "end"
                                game.save(update_fields=["state"])
                                collection_actions.append(dict(key="win", target=player.id))
                            else:
                                collection_actions.append(
                                    dict(key="upgrade_gained", target=player.id, upgrade=upgrade)
                                )
                        else:
                            player_upgrades[player.id][upgrade] = True
                            collection_actions.append(
                                dict(key="upgrade_gained", target=player.id, upgrade=upgrade)
                            )
                        break
            active_treasures = [t for t in active_treasures if t["id"] not in collected_ids]
            if collection_actions:
                actionstack.append(collection_actions)

            # burn damage from burning_cannons hits this round
            burn_actions = []
            for pid in list(on_fire_pids):
                p = players[pid]
                if p.health <= 0:
                    continue
                p.health -= 1
                burn_actions.append(dict(key="burn_damage", target=pid, health=p.health))
                if p.health <= 0:
                    lost = kill_player(p, player_upgrades)
                    burn_actions.append(dict(key="death", target=pid, type="burn"))
                    for upg in lost:
                        burn_actions.append(dict(key="upgrade_lost", target=pid, upgrade=upg))
            on_fire_pids.clear()
            if burn_actions:
                actionstack.append(burn_actions)

            # carpenter / shipwright passive repair
            carpenter_repair_actions = []
            maxhealth = game.config.ncardsavail + FREE_HEALTH_OFFSET
            for p in players.values():
                if p.health <= 0:
                    continue
                upgrades = player_upgrades.get(p.id, {})
                amount = (1 if "carpenter" in upgrades else 0) + (2 if "shipwright" in upgrades else 0)
                if amount > 0 and p.health < maxhealth:
                    p.health = min(p.health + amount, maxhealth)
                    carpenter_repair_actions.append(
                        dict(key="repair", target=p.id, health=p.health, health_repair=amount, posx=p.xpos, posy=p.ypos)
                    )
            if carpenter_repair_actions:
                actionstack.append(carpenter_repair_actions)

            # powerdown repair
            for player in players.values():
                player.powered_down = False
            powerdownrepair_actions = []
            for pid in powerdowncards:
                if players[pid].health <= 0:
                    continue
                players[pid].health = game.config.ncardsavail + FREE_HEALTH_OFFSET
                players[pid].powered_down = True
                powerdownrepair_actions.append(dict(key="powerdownrepair", target=pid, health=players[pid].health))
            actionstack.append(powerdownrepair_actions)
            powerdowncards = []

            # respawns
            respawn_actions = []
            for p in players.values():
                if p.health <= 0:
                    p.health = game.config.ncardsavail
                    p.xpos = p.last_cp_x
                    p.ypos = p.last_cp_y
                    respawn_actions.append(
                        dict(key="respawn", target=p.id, health=p.health, posx=p.xpos, posy=p.ypos, direction=p.direction)
                    )
            actionstack.append(respawn_actions)

            # spawn new treasures for next round, avoiding current player & treasure positions
            occupied = {(p.xpos, p.ypos) for p in players.values() if p.health > 0}
            occupied |= {(t["x"], t["y"]) for t in active_treasures}
            new_treasures = compute_round_treasures(game.pk, current_round + 1, initial_map, occupied, rate=game.config.treasures_per_round)
            if new_treasures:
                active_treasures.extend(new_treasures)
                actionstack.append([dict(key="treasure_spawn", **t) for t in new_treasures])

        elif card == POWER_DOWN_CARDID:
            powerdowncards.append(playerid)

        elif card in CANNON_DIRECTION_CARDS:
            players[playerid].cannon_direction = CANNON_DIRECTION_CARDS[card]["direction"]

        else:  # obviously a player card
            Nplayercardsplayedthisround += 1
            actions = get_actions_for_card(game, initial_map, players, players[playerid], card, player_upgrades=player_upgrades)
            if len(actions) > 0:
                cardid, cardrank = card_id_rank(card)
                actionstack.append(
                    [
                        dict(
                            key="card_is_played",
                            target=playerid,
                            cardslot=activeCardSlot,
                            card=CARDS[cardid],
                        )
                    ]
                )
                actionstack.extend(actions)

        if Nplayercardsplayedthisround == len(players):  # all players played a card
            activeCardSlot += 1
            Nplayercardsplayedthisround = 0

            # board moves
            board_moves_actions = board_moves(game, initial_map, players, player_upgrades=player_upgrades)
            actionstack.append(board_moves_actions)

            board_turret_actions = board_turrets(game, initial_map, players, player_upgrades=player_upgrades)
            actionstack.append(board_turret_actions)

            board_repair_actions = board_repair(game, initial_map, players)
            actionstack.append(board_repair_actions)

            # cannons
            cannon_actions = []
            for p in players.values():
                if p.health > 0 and not p.powered_down:
                    cannon_actions.extend(
                        shoot_player_cannon(game, initial_map, players, p,
                                            player_upgrades=player_upgrades, on_fire_set=on_fire_pids)
                    )
            actionstack.append(cannon_actions)

    return players, actionstack, player_upgrades, active_treasures


def play_one_round(players, initial_map, round_cards, ncardsavail, player_upgrades=None, active_treasures=None):
    """
    Process one round for an already-initialised players dict.

    This is the O(1)-per-round path used by the bot evaluator. Unlike
    play_stack (which replays the full card history from scratch each call),
    this function starts from whatever state is already in `players` and
    applies exactly one round of cards, mutating `players` in place.

    Args:
        players:          {pid: SimpleNamespace} — mutated in place.
        initial_map:      pre-loaded map data dict.
        round_cards:      flat list [pid, card, pid, card, …, BACKEND_USERID, ROUNDEND_CARDID]
        ncardsavail:      hand size; used for max-health calculations.
        player_upgrades:  optional {pid: {upgrade_type: state}} — mutated in place.
        active_treasures: optional list of active treasure dicts — mutated in place.

    Returns:
        game_over (bool): True if any player reached their final checkpoint.
    """
    checkpoints = determine_checkpoint_locations(initial_map)
    cardstack = list(zip(round_cards[::2], round_cards[1::2]))

    _game = types.SimpleNamespace(config=types.SimpleNamespace(ncardsavail=ncardsavail))

    if player_upgrades is None:
        player_upgrades = {pid: {} for pid in players}
    if active_treasures is None:
        active_treasures = []

    on_fire_pids = set()
    game_over = False
    n_players = len(players)
    Nplayercardsplayedthisround = 0
    powerdowncards = []

    for playerid, card in cardstack:
        if card == ROUNDEND_CARDID:
            for player in players.values():
                if (
                    player.health > 0
                    and player.xpos == checkpoints[player.next_checkpoint][0]
                    and player.ypos == checkpoints[player.next_checkpoint][1]
                ):
                    if player.next_checkpoint == len(checkpoints):
                        game_over = True
                    player.next_checkpoint += 1
                    player.last_cp_x = player.xpos
                    player.last_cp_y = player.ypos

            # treasure collection
            collected_ids = set()
            for treasure in list(active_treasures):
                for player in players.values():
                    if player.health <= 0:
                        continue
                    if player.xpos == treasure["x"] and player.ypos == treasure["y"]:
                        collected_ids.add(treasure["id"])
                        upgrade = treasure["upgrade"]
                        if upgrade == "shield":
                            player_upgrades[player.id]["shield"] = {"charges": UPGRADE_TYPES["shield"]["charges"]}
                        elif upgrade == "checkpoint_rush":
                            player.next_checkpoint += 1
                            if player.next_checkpoint > len(checkpoints):
                                game_over = True
                        else:
                            player_upgrades[player.id][upgrade] = True
                        break
            for i in range(len(active_treasures) - 1, -1, -1):
                if active_treasures[i]["id"] in collected_ids:
                    active_treasures.pop(i)

            # burn damage
            for pid in list(on_fire_pids):
                p = players[pid]
                if p.health <= 0:
                    continue
                p.health -= 1
                if p.health <= 0:
                    kill_player(p, player_upgrades)
            on_fire_pids.clear()

            # carpenter / shipwright passive repair
            maxhealth_one = ncardsavail + FREE_HEALTH_OFFSET
            for p in players.values():
                if p.health <= 0:
                    continue
                upgrades = player_upgrades.get(p.id, {})
                amount = (1 if "carpenter" in upgrades else 0) + (2 if "shipwright" in upgrades else 0)
                if amount > 0:
                    p.health = min(p.health + amount, maxhealth_one)

            for player in players.values():
                player.powered_down = False
            for pid in powerdowncards:
                if players[pid].health <= 0:
                    continue
                players[pid].health = ncardsavail + FREE_HEALTH_OFFSET
                players[pid].powered_down = True
            powerdowncards = []

            for p in players.values():
                if p.health <= 0:
                    p.health = ncardsavail
                    p.xpos = p.last_cp_x
                    p.ypos = p.last_cp_y

        elif card == POWER_DOWN_CARDID:
            powerdowncards.append(playerid)

        elif card in CANNON_DIRECTION_CARDS:
            players[playerid].cannon_direction = CANNON_DIRECTION_CARDS[card]["direction"]

        else:
            Nplayercardsplayedthisround += 1
            get_actions_for_card(_game, initial_map, players, players[playerid], card, player_upgrades=player_upgrades)

            if Nplayercardsplayedthisround == n_players:
                Nplayercardsplayedthisround = 0
                board_moves(_game, initial_map, players, player_upgrades=player_upgrades)
                board_turrets(_game, initial_map, players, player_upgrades=player_upgrades)
                board_repair(_game, initial_map, players)
                for p in players.values():
                    if p.health > 0 and not p.powered_down:
                        shoot_player_cannon(_game, initial_map, players, p,
                                            player_upgrades=player_upgrades, on_fire_set=on_fire_pids)

    return game_over


def kill_player(p, player_upgrades=None):
    p.health = 0
    p.xpos = p.ypos = -99
    if player_upgrades is not None:
        lost = list(player_upgrades.get(p.id, {}).keys())
        player_upgrades[p.id] = {}
        return lost
    return []


def board_turrets(game, gmap, players, player_upgrades=None):
    actions = []
    turret_pos = gmap.get("turret_positions")
    tile_pairs = turret_pos if turret_pos is not None else (
        (x, y) for x in range(gmap["width"]) for y in range(gmap["height"])
    )
    for x, y in tile_pairs:
        tile_prop = get_tile_properties(gmap, x, y)
        if tile_prop["turret_x"] != 0:
            actions.extend(
                shoot_cannon_ball(
                    gmap,
                    xstart=x,
                    ystart=y,
                    xinc=tile_prop["turret_x"],
                    yinc=0,
                    source_player=BOARD_CANNON_PLAYERID,
                    players=players,
                    cannon_damage=1,
                    collide_terrain=True,
                    collide_players=True,
                    player_upgrades=player_upgrades,
                )
            )
        if tile_prop["turret_y"] != 0:
            actions.extend(
                shoot_cannon_ball(
                    gmap,
                    xstart=x,
                    ystart=y,
                    xinc=0,
                    yinc=tile_prop["turret_y"],
                    source_player=BOARD_CANNON_PLAYERID,
                    players=players,
                    cannon_damage=1,
                    collide_terrain=True,
                    collide_players=True,
                    player_upgrades=player_upgrades,
                )
            )
    return actions


def board_repair(game, gmap, players):
    actions = []
    maxhealth = game.config.ncardsavail + FREE_HEALTH_OFFSET

    for pid, p in players.items():
        if (p.health <= 0) or (p.health >= maxhealth):
            continue
        tile_prop = get_tile_properties(gmap, p.xpos, p.ypos)
        if tile_prop["damage"] < 0:
            p.health -= tile_prop["damage"]
            if p.health >= maxhealth:
                p.health = maxhealth
            actions.append(
                dict(key="repair", target=p.id, health_repair=-tile_prop["damage"], health=p.health, posx=p.xpos, posy=p.ypos)
            )

    return actions


def board_moves(game, gmap, players, fast_current=True, player_upgrades=None):
    # TODO: disable collisions for board_moves
    actions = []
    for pid, p in players.items():
        if p.health <= 0:
            break
        tile_prop = get_tile_properties(gmap, p.xpos, p.ypos)
        if (tile_prop["vortex"] != 0) and (tile_prop["current_x"] == 0) and (tile_prop["current_y"] == 0):
            if player_upgrades and "ghost_ship" in player_upgrades.get(pid, {}):
                continue
            actions.append({"key": "rotate", "target": pid, "from": p.direction, "to": (p.direction + tile_prop["vortex"]) % 4})
            p.direction = (p.direction + tile_prop["vortex"]) % 4

    player_moved = {pid: False for pid in players.keys()}
    # we have to do this nplayer times to resolve blocking situation on the currents
    for n in range(len(players)):
        for pid, p in players.items():
            if (not player_moved[pid]) and (p.health > 0):
                tile_prop = get_tile_properties(gmap, p.xpos, p.ypos)
                if tile_prop["current_x"] != 0:
                    old_xpos = p.xpos
                    actions.extend(move_player_x(game, gmap, players, p, tile_prop["current_x"], push_players=False, player_upgrades=player_upgrades))
                    if p.xpos != old_xpos:
                        player_moved[pid] = True
                        next_tile_prop = get_tile_properties(gmap, p.xpos, p.ypos)
                        if next_tile_prop["vortex"] != 0:
                            if not (player_upgrades and "ghost_ship" in player_upgrades.get(pid, {})):
                                actions.append(
                                    {
                                        "key": "rotate",
                                        "target": pid,
                                        "from": p.direction,
                                        "to": (p.direction + next_tile_prop["vortex"]) % 4,
                                    }
                                )
                                p.direction = (p.direction + next_tile_prop["vortex"]) % 4

                if tile_prop["current_y"] != 0:
                    old_ypos = p.ypos
                    actions.extend(move_player_y(game, gmap, players, p, tile_prop["current_y"], push_players=False, player_upgrades=player_upgrades))
                    if p.ypos != old_ypos:
                        player_moved[pid] = True
                        next_tile_prop = get_tile_properties(gmap, p.xpos, p.ypos)
                        if next_tile_prop["vortex"] != 0:
                            if not (player_upgrades and "ghost_ship" in player_upgrades.get(pid, {})):
                                actions.append(
                                    {
                                        "key": "rotate",
                                        "target": pid,
                                        "from": p.direction,
                                        "to": (p.direction + next_tile_prop["vortex"]) % 4,
                                    }
                                )
                                p.direction = (p.direction + next_tile_prop["vortex"]) % 4
    if fast_current:
        fb_players = {}
        # call board moves again for players on fast belt
        for pid, p in players.items():
            tile_prop = get_tile_properties(gmap, p.xpos, p.ypos)
            if tile_prop.get("fast_current", False) == True:
                fb_players[pid] = p
        if len(fb_players) > 0:
            actions.extend(board_moves(game, gmap, fb_players, fast_current=False, player_upgrades=player_upgrades))
    return actions


def shoot_player_cannon(game, gmap, players, player, player_upgrades=None, on_fire_set=None):
    has_compass_rose = player_upgrades is not None and "rose_cannons" in player_upgrades.get(player.id, {})
    directions = list(range(4)) if has_compass_rose else [(player.direction + player.cannon_direction) % 4]
    actions = []
    for d in directions:
        actions.extend(shoot_cannon_ball(
            gmap,
            xstart=player.xpos,
            ystart=player.ypos,
            xinc=DIRID2MOVE[d][0],
            yinc=DIRID2MOVE[d][1],
            source_player=player.id,
            players=players,
            cannon_damage=1,
            collide_terrain=True,
            collide_players=True,
            player_upgrades=player_upgrades,
            on_fire_set=on_fire_set,
        ))
    return actions


def shoot_cannon_ball(
    gmap, xstart, ystart, xinc, yinc, source_player, players, cannon_damage=1,
    collide_terrain=True, collide_players=True, player_upgrades=None, on_fire_set=None
):
    actions = []
    x, y = xstart, ystart
    while (x >= 0 and x < gmap["width"]) and (y >= 0 and y < gmap["height"]):
        x += xinc
        y += yinc

        # hit a player?
        for other_player in players.values():
            if (x == other_player.xpos) and (y == other_player.ypos):
                # burning cannons: set target on fire
                if (
                    on_fire_set is not None
                    and player_upgrades is not None
                    and source_player in player_upgrades
                    and "burning_cannons" in player_upgrades[source_player]
                ):
                    on_fire_set.add(other_player.id)

                # shield absorption
                actual_damage = cannon_damage
                if player_upgrades is not None and "shield" in player_upgrades.get(other_player.id, {}):
                    shield = player_upgrades[other_player.id]["shield"]
                    absorbed = min(cannon_damage, shield["charges"])
                    shield["charges"] -= absorbed
                    actual_damage = cannon_damage - absorbed
                    actions.append(dict(key="shield_absorb", target=other_player.id, absorbed=absorbed, charges=shield["charges"]))
                    if shield["charges"] <= 0:
                        del player_upgrades[other_player.id]["shield"]
                        actions.append(dict(key="upgrade_lost", target=other_player.id, upgrade="shield"))

                other_player.health -= actual_damage
                is_fire_shot = on_fire_set is not None and other_player.id in on_fire_set
                actions.append(
                    dict(
                        key="shot",
                        src_x=xstart,
                        src_y=ystart,
                        source_player=source_player,
                        cannon_damage=actual_damage,
                        other_player=other_player.id,
                        other_player_health=other_player.health,
                        collided_at=(x, y),
                        on_fire=is_fire_shot,
                    )
                )
                if is_fire_shot and other_player.health > 0:
                    actions.append(dict(key="set_on_fire", target=other_player.id))
                if other_player.health <= 0:
                    lost = kill_player(other_player, player_upgrades)
                    actions.append(dict(key="death", source_player=source_player, target=other_player.id, type="cannon"))
                    for upg in lost:
                        actions.append(dict(key="upgrade_lost", target=other_player.id, upgrade=upg))

                if collide_players:
                    return actions
        # hit a colliding map tile?
        if get_tile_properties(gmap, x, y)["collision"]:
            actions.append(dict(key="shot", src_x=xstart, src_y=ystart, collided_at=(x, y)))
            if collide_terrain:
                return actions

    actions.append(dict(key="shot", src_x=xstart, src_y=ystart, collided_at=(x, y)))
    return actions


def calc_stats(game):
    players, actionstack, *_ = play_stack(game)
    ids = [(p.id, p.next_checkpoint) for p in players.values()]
    ids.append((BOARD_CANNON_PLAYERID, 0))
    ids.sort(key=lambda x: x[1], reverse=True)
    stats = {
        "move_count": {pid: 0 for pid, _ in ids},
        "rotation_count": {pid: 0 for pid, _ in ids},
        "death_count": {pid: 0 for pid, _ in ids},
        "void_count": {pid: 0 for pid, _ in ids},
        "cannondeath_count": {pid: 0 for pid, _ in ids},
        "damage_dealt": {pid: {other_pid: 0 for other_pid, _ in ids} for pid, _ in ids},
        "damage_taken": {pid: {other_pid: 0 for other_pid, _ in ids} for pid, _ in ids},
        "repair_count": {pid: 0 for pid, _ in ids},
        "powerdown_count": {pid: 0 for pid, _ in ids},
        "checkpoints": {pid: cp - 1 for pid, cp in ids},  # in frontend we count checkpoints reached
        "kills": {pid: {other_pid: 0 for other_pid, _ in ids} for pid, _ in ids},
    }
    for actiongrp in actionstack:
        for action in actiongrp:
            if "move" in action["key"]:
                stats["move_count"][action["target"]] += 1
            elif "rotate" in action["key"]:
                stats["rotation_count"][action["target"]] += 1
            elif "death" in action["key"]:
                stats["death_count"][action["target"]] += 1
                if "void" == action["type"]:
                    stats["void_count"][action["target"]] += 1
                if "cannon" == action["type"]:
                    stats["cannondeath_count"][action["target"]] += 1
                    source_player = action.get("source_player")
                    stats["kills"][source_player][action["target"]] += 1
            elif "shot" == action["key"]:
                other_player = action.get("other_player")
                if other_player:
                    source_player = action.get("source_player")
                    stats["damage_taken"][other_player][source_player] += action["cannon_damage"]
                    stats["damage_dealt"][source_player][other_player] += action["cannon_damage"]
            elif "repair" == action["key"]:
                stats["repair_count"][action["target"]] += action["health_repair"]
            elif "powerdownrepair" == action["key"]:
                stats["powerdown_count"][action["target"]] += 1

    liststats = {}
    for field in stats:
        liststats[field] = [stats[field][pid] for pid, _ in ids]
        for n in range(len(liststats[field])):
            val = liststats[field][n]
            if type(val) == dict:
                liststats[field][n] = [val[other_pid] for other_pid, _ in ids]

    liststats["names"] = [players[pid].name for pid, _ in ids[:-1]]
    liststats["names"].append("Board Cannons")
    return liststats


def get_actions_for_card(game, gmap, players, player, card, player_upgrades=None):
    actions = []
    if player.powered_down or player.health <= 0:
        return actions

    cardid, cardrank = card_id_rank(card)
    rot = CARDS[cardid]["rot"]
    if rot != 0:
        actions.append([{"key": "rotate", "target": player.id, "from": player.direction, "to": (player.direction + rot) % 4}])
        player.direction = (player.direction + rot) % 4

    for mov in range(abs(CARDS[cardid]["move"])):
        if player.health <= 0:
            break
        inc = int(CARDS[cardid]["move"] / abs(CARDS[cardid]["move"]))

        xinc = DIRID2MOVE[player.direction][0] * inc
        yinc = DIRID2MOVE[player.direction][1] * inc

        if xinc != 0:
            actions.append(move_player_x(game, gmap, players, player, xinc, player_upgrades=player_upgrades))
        if yinc != 0:
            actions.append(move_player_y(game, gmap, players, player, yinc, player_upgrades=player_upgrades))

    if CARDS[cardid]["repair"] != 0:
        maxhealth = game.config.ncardsavail + FREE_HEALTH_OFFSET
        if player.health + CARDS[cardid]["repair"] <= maxhealth:
            player.health += CARDS[cardid]["repair"]
            actions.append(
                [
                    dict(
                        key="repair",
                        target=player.id,
                        health=player.health,
                        health_repair=CARDS[cardid]["repair"],
                        posx=player.xpos,
                        posy=player.ypos,
                    )
                ]
            )

    return actions


def move_player_x(game, gmap, players, player, inc, push_players=True, player_upgrades=None):
    actions = []
    tile_prop = get_tile_properties(gmap, player.xpos + inc, player.ypos)
    if tile_prop["collision"]:
        damage = tile_prop["damage"]
        player.health -= damage
        actions.append(dict(key="collision_x", target=player.id, val=inc, health=player.health))
        if player.health <= 0:
            lost = kill_player(player, player_upgrades)
            actions.append(dict(key="death", target=player.id, type="collision"))
            for upg in lost:
                actions.append(dict(key="upgrade_lost", target=player.id, upgrade=upg))
        return actions

    ghost = player_upgrades and "ghost_ship" in player_upgrades.get(player.id, {})

    if tile_prop["void"] and not ghost:
        player.health = 0
        actions.append(
            {
                "key": "move_x",
                "target": player.id,
                "from": player.xpos,
                "to": player.xpos + inc,
                "target_pos": (player.xpos + inc, player.ypos),
            }
        )
        lost = kill_player(player, player_upgrades)
        actions.append(dict(key="death", target=player.id, type="void"))
        for upg in lost:
            actions.append(dict(key="upgrade_lost", target=player.id, upgrade=upg))
        return actions

    if (player.xpos + inc < 0) or (player.xpos + inc >= gmap["width"]):
        player.health = 0
        actions.append(
            {
                "key": "move_x",
                "target": player.id,
                "from": player.xpos,
                "to": player.xpos + inc,
                "target_pos": (player.xpos + inc, player.ypos),
            }
        )
        lost = kill_player(player, player_upgrades)
        actions.append(dict(key="death", target=player.id, type="void"))
        for upg in lost:
            actions.append(dict(key="upgrade_lost", target=player.id, upgrade=upg))
        return actions

    for pid, p2 in players.items():
        if (p2.xpos == player.xpos + inc) and (p2.ypos == player.ypos):
            if push_players:
                if player_upgrades and "solid_rock" in player_upgrades.get(p2.id, {}):
                    return actions  # rock ship blocks the pusher
                actions.extend(move_player_x(game, gmap, players, p2, inc, player_upgrades=player_upgrades))
                if (p2.xpos == player.xpos + inc) and (p2.ypos == player.ypos):
                    return actions
                break
            else:
                return actions
    actions.append(
        {
            "key": "move_x",
            "target": player.id,
            "from": player.xpos,
            "to": player.xpos + inc,
            "target_pos": (player.xpos + inc, player.ypos),
        }
    )
    player.xpos += inc
    return actions


def move_player_y(game, gmap, players, player, inc, push_players=True, player_upgrades=None):
    actions = []
    tile_prop = get_tile_properties(gmap, player.xpos, player.ypos + inc)
    if tile_prop["collision"]:
        damage = tile_prop["damage"]
        player.health -= damage
        actions.append(dict(key="collision_y", target=player.id, val=inc, health=player.health))
        if player.health <= 0:
            lost = kill_player(player, player_upgrades)
            actions.append(dict(key="death", target=player.id, type="collision"))
            for upg in lost:
                actions.append(dict(key="upgrade_lost", target=player.id, upgrade=upg))
        return actions

    ghost = player_upgrades and "ghost_ship" in player_upgrades.get(player.id, {})

    if tile_prop["void"] and not ghost:
        player.health = 0
        actions.append(
            {
                "key": "move_y",
                "target": player.id,
                "from": player.ypos,
                "to": player.ypos + inc,
                "target_pos": (player.xpos, player.ypos + inc),
            }
        )
        lost = kill_player(player, player_upgrades)
        actions.append(dict(key="death", target=player.id, type="void"))
        for upg in lost:
            actions.append(dict(key="upgrade_lost", target=player.id, upgrade=upg))
        return actions

    if (player.ypos + inc < 0) or (player.ypos + inc >= gmap["height"]):
        player.health = 0
        actions.append(
            {
                "key": "move_y",
                "target": player.id,
                "from": player.ypos,
                "to": player.ypos + inc,
                "target_pos": (player.xpos, player.ypos + inc),
            }
        )
        lost = kill_player(player, player_upgrades)
        actions.append(dict(key="death", target=player.id, type="void"))
        for upg in lost:
            actions.append(dict(key="upgrade_lost", target=player.id, upgrade=upg))
        return actions

    for pid, p2 in players.items():
        if (p2.xpos == player.xpos) and (p2.ypos == player.ypos + inc):
            if push_players:
                if player_upgrades and "solid_rock" in player_upgrades.get(p2.id, {}):
                    return actions  # rock ship blocks the pusher
                actions.extend(move_player_y(game, gmap, players, p2, inc, player_upgrades=player_upgrades))
                if (p2.xpos == player.xpos) and (p2.ypos == player.ypos + inc):
                    return actions
                break
            else:
                return actions
    actions.append(
        {
            "key": "move_y",
            "target": player.id,
            "from": player.ypos,
            "to": player.ypos + inc,
            "target_pos": (player.xpos, player.ypos + inc),
        }
    )
    player.ypos += inc
    return actions


def get_tile_properties(gmap, x, y):
    tile_cache = gmap.get("tile_prop_cache")
    if tile_cache is not None:
        w, h = gmap["bg_width"], gmap["bg_height"]
        if (x < 0) or (x >= w) or (y < 0) or (y >= h):
            return TILE_DEFAULTS
        return tile_cache[y * w + x]
    bg = list(filter(lambda l: l["name"] == "background", gmap["layers"]))[0]
    if (x < 0) or (x >= bg["width"]) or (y < 0) or (y >= bg["height"]):
        return TILE_DEFAULTS
    tile_id = bg["data"][y * bg["width"] + x]
    for tileset in gmap["tilesets"][::-1]:
        if tile_id >= tileset["firstgid"]:
            tileset_id = tile_id - tileset["firstgid"]
            tile_props = tileset["tiles"]
            tile_prop = next(filter(lambda p: p["id"] == tileset_id, tile_props))
            return {item["name"]: item["value"] for item in tile_prop["properties"]}
    raise ValueError(f"could not find tile_id {tile_id} in map")


_LOAD_MAP_CACHE_VERSION = 2  # bump when cached structure changes


def load_map(fname):
    cachename = f"map_v{_LOAD_MAP_CACHE_VERSION}_{fname}"

    gmap = cache.get(cachename)
    if gmap is not None:
        return gmap

    with open(os.path.join(MAPSDIR, fname)) as fh:
        gmap = json.load(fh)

    bg = list(filter(lambda l: l["name"] == "background", gmap["layers"]))[0]
    w, h = bg["width"], bg["height"]
    tile_prop_cache = [None] * (w * h)
    property_locations = {}
    for x in range(w):
        for y in range(h):
            prop = get_tile_properties(gmap, x, y)
            tile_prop_cache[y * w + x] = prop
            for p, v in prop.items():
                if v:
                    property_locations.setdefault(p, []).append((x, y))
    gmap["tile_prop_cache"] = tile_prop_cache
    gmap["bg_width"] = w
    gmap["bg_height"] = h
    gmap["property_locations"] = property_locations
    # Pre-sorted turret positions (x-outer, y-inner order, matching original scan)
    gmap["turret_positions"] = sorted(
        set(property_locations.get("turret_x", [])) | set(property_locations.get("turret_y", []))
    )
    gmap["filename"] = os.path.basename(fname)
    gmap["mapname"] = fname.replace(".json", "")
    properties = gmap.get("properties", {})
    for prop in properties:
        if prop["name"] == "mapname":
            gmap["mapname"] = prop["value"]

    cache.set(cachename, gmap, None)
    return gmap


def verify_map(mapobj):
    layer_names = [l["name"] for l in mapobj["layers"]]
    err_msg = []
    if not "background" in layer_names:
        err_msg.append("No background layer in map.")
    if not "startinglocs" in layer_names:
        err_msg.append("No startinglocs layer in map.")
    else:
        slayer = list(filter(lambda l: l["name"] == "startinglocs", mapobj["layers"]))[0]
        if len(slayer["objects"]) < 1:
            err_msg.append(f"startinglocs layer has only {len(slayer['objects'])} entries.")
    tilesets = mapobj["tilesets"]
    if len(tilesets) != 1:
        err_msg.append(f"{len(tilesets)} tilesets found. Only supporting 1 tileset.")

    req_props = set(TILE_DEFAULTS.keys())
    for ts in tilesets:
        for tile in ts["tiles"]:
            props = set([prop["name"] for prop in tile["properties"]])
            if props != req_props:
                err_msg.append(f"Found tile {tile['id']} without required properties, have {props}, required {req_props}")

    if "checkpoints" in layer_names:
        clayer = list(filter(lambda l: l["name"] == "checkpoints", mapobj["layers"]))[0]
        if len(clayer["objects"]) < 1:
            err_msg.append(f"checkpoints layer has only {len(clayer['objects'])} entries.")
        names = set()
        for o in clayer["objects"]:
            try:
                names.add(int(o["name"]))
            except:
                err_msg.append(f"Failed to convert checkpoint name {o['name']}, needs to be integer")
        expected_names = set(range(1, len(clayer["objects"]) + 1))
        diff = expected_names.difference(names)
        if len(diff) > 0:
            err_msg.append(f"Missing named checkpoints {diff}")
    return err_msg
