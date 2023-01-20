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


def argsort(seq):
    return sorted(range(len(seq)), key=seq.__getitem__)


def flatten_list_of_tuples(lot):
    return [i for j in lot for i in j]


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

    # print(f"player_ids {player_ids}, player_in_game {players_in_game}")
    cards_per_player = [get_cards_on_hand(gamecfg, i, gamecfg.ncardslots) for i in range(len(gamecfg.player_ids))]
    # for i in enumerate(gamecfg.player_ids):
    #    cards_per_player.append(get_cards_on_hand(gamecfg, i, gamecfg.ncardslots))

    # sort by ranking...
    ret = []
    for i in range(gamecfg.ncardslots):
        nth_cards = [pcards[i] for pcards in cards_per_player]  # i.e. for each player one card
        rankings = [card_id_rank(c)[1] for pid, c in nth_cards]
        # print(f"{i} :: cards this segment {nth_cards} rankings {rankings}")
        # if rankings collide, i.e. are the same we could compare submitted timestamps here
        for j in argsort(rankings)[::-1]:
            ret.append(nth_cards[j])

    # print(f"cards sorted: {ret}")
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


def play_stack(game):
    initial_map = load_inital_map(game.config.mapfile)
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

    # print(f"full cardstack {cardstack}")

    actionstack = []

    Nplayercardsplayedthisround = 0
    powerdowncards = []
    activeCardSlot = 0  # denotes current card slot that is to be played by each player, i.e. 0 if players are to play first card, 1 if players are playing second card
    for playerid, card in cardstack:

        if card == ROUNDEND_CARDID:
            activeCardSlot = 0
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

        elif card == POWER_DOWN_CARDID:
            powerdowncards.append(playerid)

        elif card in CANNON_DIRECTION_CARDS:
            players[playerid].cannon_direction = CANNON_DIRECTION_CARDS[card]["direction"]

        else:  # obviously a player card
            Nplayercardsplayedthisround += 1
            actions = get_actions_for_card(game, initial_map, players, players[playerid], card)
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
            board_moves_actions = board_moves(game, initial_map, players)
            actionstack.append(board_moves_actions)

            board_turret_actions = board_turrets(game, initial_map, players)
            actionstack.append(board_turret_actions)

            board_repair_actions = board_repair(game, initial_map, players)
            actionstack.append(board_repair_actions)

            # cannons
            cannon_actions = []
            for p in players.values():
                if p.health > 0 and not p.powered_down:
                    cannon_actions.extend(shoot_player_cannon(game, initial_map, players, p))
            actionstack.append(cannon_actions)

    # [print(i, a) for i, a in enumerate(actionstack)]

    return players, actionstack


def kill_player(p):
    p.health = 0
    p.xpos = p.ypos = -99


def board_turrets(game, gmap, players):
    actions = []

    for x in range(gmap["width"]):
        for y in range(gmap["height"]):
            tile_prop = get_tile_properties(gmap, x, y)
            if tile_prop["turret_x"] != 0:
                # print(f"turret_x at ({x},{y}) {tile_prop['turret_x']}")
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
                    )
                )
            if tile_prop["turret_y"] != 0:
                # print(f"turret_y at ({x},{y}) {tile_prop['turret_y']}")
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


def board_moves(game, gmap, players, fast_current=True):
    # TODO: disable collisions for board_moves
    actions = []
    for pid, p in players.items():
        if p.health <= 0:
            break
        tile_prop = get_tile_properties(gmap, p.xpos, p.ypos)
        if tile_prop["vortex"] != 0:
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
                    actions.extend(move_player_x(game, gmap, players, p, tile_prop["current_x"], push_players=False))
                    if p.xpos != old_xpos:
                        player_moved[pid] = True
                if tile_prop["current_y"] != 0:
                    old_ypos = p.ypos
                    actions.extend(move_player_y(game, gmap, players, p, tile_prop["current_y"], push_players=False))
                    if p.ypos != old_ypos:
                        player_moved[pid] = True
    if fast_current:
        fb_players = {}
        # call board moves again for players on fast belt
        for pid, p in players.items():
            tile_prop = get_tile_properties(gmap, p.xpos, p.ypos)
            if tile_prop.get("fast_current", False) == True:
                fb_players[pid] = p
        if len(fb_players) > 0:
            actions.extend(board_moves(game, gmap, fb_players, fast_current=False))
    return actions


def shoot_player_cannon(game, gmap, players, player):
    cannon_direction = (player.direction + player.cannon_direction) % 4
    return shoot_cannon_ball(
        gmap,
        xstart=player.xpos,
        ystart=player.ypos,
        xinc=DIRID2MOVE[cannon_direction][0],
        yinc=DIRID2MOVE[cannon_direction][1],
        source_player=player.id,
        players=players,
        cannon_damage=1,
        collide_terrain=True,
        collide_players=True,
    )


def shoot_cannon_ball(
    gmap, xstart, ystart, xinc, yinc, source_player, players, cannon_damage=1, collide_terrain=True, collide_players=True
):
    actions = []
    x, y = xstart, ystart
    while (x >= 0 and x < gmap["width"]) and (y >= 0 and y < gmap["height"]):
        x += xinc
        y += yinc

        # hit a player ?
        for other_player in players.values():
            if (x == other_player.xpos) and (y == other_player.ypos):
                other_player.health -= cannon_damage
                actions.append(
                    dict(
                        key="shot",
                        src_x=xstart,
                        src_y=ystart,
                        source_player=source_player,
                        cannon_damage=cannon_damage,
                        other_player=other_player.id,
                        other_player_health=other_player.health,
                        collided_at=(x, y),
                    )
                )
                if other_player.health <= 0:
                    actions.append(dict(key="death", source_player=source_player, target=other_player.id, type="cannon"))
                    kill_player(other_player)

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
    players, actionstack = play_stack(game)
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


def get_actions_for_card(game, gmap, players, player, card):

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
            actions.append(move_player_x(game, gmap, players, player, xinc))
        if yinc != 0:
            actions.append(move_player_y(game, gmap, players, player, yinc))

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


def move_player_x(game, gmap, players, player, inc, push_players=True):
    actions = []
    tile_prop = get_tile_properties(gmap, player.xpos + inc, player.ypos)
    if tile_prop["collision"]:
        damage = tile_prop["damage"]
        player.health -= damage
        actions.append(dict(key="collision_x", target=player.id, val=inc, health=player.health))
        if player.health <= 0:
            actions.append(dict(key="death", target=player.id, type="collision"))
            kill_player(player)
        return actions

    if tile_prop["void"]:
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
        actions.append(dict(key="death", target=player.id, type="void"))
        kill_player(player)
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
        actions.append(dict(key="death", target=player.id, type="void"))
        kill_player(player)
        return actions

    for pid, p2 in players.items():
        if (p2.xpos == player.xpos + inc) and (p2.ypos == player.ypos):
            if push_players:
                actions.extend(move_player_x(game, gmap, players, p2, inc))
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


def move_player_y(game, gmap, players, player, inc, push_players=True):
    actions = []
    tile_prop = get_tile_properties(gmap, player.xpos, player.ypos + inc)
    # print("tp", tile_prop)
    if tile_prop["collision"]:
        damage = tile_prop["damage"]
        player.health -= damage
        actions.append(dict(key="collision_y", target=player.id, val=inc, health=player.health))
        if player.health <= 0:
            actions.append(dict(key="death", target=player.id, type="collision"))
            kill_player(player)
        return actions

    if tile_prop["void"]:
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
        actions.append(dict(key="death", target=player.id, type="void"))
        kill_player(player)
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
        actions.append(dict(key="death", target=player.id, type="void"))
        kill_player(player)
        return actions

    for pid, p2 in players.items():
        if (p2.xpos == player.xpos) and (p2.ypos == player.ypos + inc):
            if push_players:
                actions.extend(move_player_y(game, gmap, players, p2, inc))
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
    bg = list(filter(lambda l: l["name"] == "background", gmap["layers"]))[0]
    # for j in range(bg["height"]):
    #    print(f'bg', bg["data"][j * bg["width"]:(j+1)*bg["width"]])
    if (x < 0) or (x >= bg["width"]) or (y < 0) or (y >= bg["height"]):
        return TILE_DEFAULTS
    tile_id = bg["data"][y * bg["width"] + x]
    for tileset in gmap["tilesets"][::-1]:
        if tile_id >= tileset["firstgid"]:
            tileset_id = tile_id - tileset["firstgid"]
            tile_props = tileset["tiles"]
            tile_prop = next(filter(lambda p: p["id"] == tileset_id, tile_props))
            # print("bg", x, y, tile_id, tileset_id, "prop", tile_prop)
            return {item["name"]: item["value"] for item in tile_prop["properties"]}
    raise ValueError(f"could not find tile_id {tile_id} in map")


def load_inital_map(fname):
    cachename = f"map_{fname}"

    gmap = cache.get(cachename)
    if gmap is not None:
        return gmap

    with open(os.path.join(MAPSDIR, fname)) as fh:
        gmap = json.load(fh)

    bg = list(filter(lambda l: l["name"] == "background", gmap["layers"]))[0]
    property_locations = {}
    for x in range(bg["width"]):
        for y in range(bg["height"]):
            prop = get_tile_properties(gmap, x, y)
            for p, v in prop.items():
                if v:
                    property_locations.setdefault(p, []).append((x, y))
    gmap["property_locations"] = property_locations

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
