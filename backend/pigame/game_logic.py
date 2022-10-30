import json
import os
import random
import types

from piraterace.settings import MAPSDIR
from piplayer.models import Account
from pigame.models import card_id_rank, CARDS, DEFAULT_DECK, DIRID2MOVE, DIRID2NAME, FREE_HEALTH_OFFSET

BACKEND_USERID = -1
ROUNDEND_CARDID = -1
POWER_DOWN_CARDID = -2


def argsort(seq):
    return sorted(range(len(seq)), key=seq.__getitem__)


def flatten_list_of_tuples(lot):
    return [i for j in lot for i in j]


def get_cards_on_hand(gamecfg, playeridx, ncards):
    """
    get next ncards that a player can draw from his deck
        return list of tuples of (playerid, card)
    """
    next_card = gamecfg.player_next_card[playeridx]
    deck = gamecfg.player_decks[playeridx]

    if next_card + ncards - 1 > len(deck):
        remaining_cards = deck[next_card:]
        old_cards = deck[:next_card]
        random.shuffle(old_cards)
        gamecfg.player_decks[playeridx] = remaining_cards + old_cards
        gamecfg.player_next_card[playeridx] = 0
        gamecfg.save(update_fields=["player_next_card", "player_decks"])
        next_card = gamecfg.player_next_card[playeridx]
        deck = gamecfg.player_decks[playeridx]

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
    for pid, x, y, direction, color, team in zip(
        game.config.player_ids,
        game.config.player_start_x,
        game.config.player_start_y,
        game.config.player_start_directions,
        game.config.player_colors,
        game.config.player_teams,
    ):
        p = types.SimpleNamespace()
        p.id = pid
        p.last_cp_x = x
        p.last_cp_y = y
        p.xpos = x
        p.ypos = y
        p.direction = direction
        p.next_checkpoint = 1
        p.color = color
        p.team = team
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
                        print("You win")
                    player.next_checkpoint += 1
                    player.last_cp_x = player.xpos
                    player.last_cp_y = player.ypos

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

            for player in players.values():
                player.powered_down = False
            for pid in powerdowncards:
                players[pid].health = game.config.ncardsavail + FREE_HEALTH_OFFSET
                players[pid].powered_down = True
            powerdowncards = []

        elif card == POWER_DOWN_CARDID:
            powerdowncards.append(playerid)

        else:  # obviously a player card
            actionstack.append([dict(key="card_is_played", target=p.id, cardslot=activeCardSlot)])
            Nplayercardsplayedthisround += 1
            actions = get_actions_for_card(game, initial_map, players, players[playerid], card)
            actionstack.extend(actions)

        if Nplayercardsplayedthisround == len(players):  # all players played a card
            activeCardSlot += 1
            Nplayercardsplayedthisround = 0

            # board moves
            board_moves_actions = board_moves(game, initial_map, players)
            actionstack.append(board_moves_actions)

            board_turret_actions = board_turrets(game, initial_map, players)
            actionstack.append(board_turret_actions)

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
                        players=players,
                        cannon_damage=1,
                        collide_terrain=True,
                        collide_players=True,
                    )
                )

    return actions


def board_moves(game, gmap, players):
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
    return actions


def shoot_player_cannon(game, gmap, players, player):
    return shoot_cannon_ball(
        gmap,
        xstart=player.xpos,
        ystart=player.ypos,
        xinc=DIRID2MOVE[player.direction][0],
        yinc=DIRID2MOVE[player.direction][1],
        players=players,
        cannon_damage=1,
        collide_terrain=True,
        collide_players=True,
    )


def shoot_cannon_ball(gmap, xstart, ystart, xinc, yinc, players, cannon_damage=1, collide_terrain=True, collide_players=True):
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
                        other_player=other_player.id,
                        damage=cannon_damage,
                        collided_at=(x, y),
                    )
                )
                if other_player.health <= 0:
                    actions.append(dict(key="death", target=other_player.id, type="cannon"))
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
            actions.append([dict(key="repair", target=player.id, val=CARDS[cardid]["repair"], posx=player.xpos, posy=player.ypos)])

    return actions


def move_player_x(game, gmap, players, player, inc, push_players=True):
    actions = []
    tile_prop = get_tile_properties(gmap, player.xpos + inc, player.ypos)
    if tile_prop["collision"]:
        damage = tile_prop["damage"]
        player.health -= damage
        actions.append(dict(key="collision_x", target=player.id, val=inc, damage=damage))
        if player.health <= 0:
            actions.append(dict(key="death", target=player.id, type="collision"))
            kill_player(player)
        return actions

    if tile_prop["void"]:
        player.health = 0
        actions.append({"key": "move_x", "target": player.id, "from": player.xpos, "to": player.xpos + inc})
        actions.append(dict(key="death", target=player.id, type="void"))
        kill_player(player)
        return actions

    if (player.xpos + inc < 0) or (player.xpos + inc >= gmap["width"]):
        player.health = 0
        actions.append({"key": "move_x", "target": player.id, "from": player.xpos, "to": player.xpos + inc})
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
    actions.append({"key": "move_x", "target": player.id, "from": player.xpos, "to": player.xpos + inc})
    player.xpos += inc
    return actions


def move_player_y(game, gmap, players, player, inc, push_players=True):
    actions = []
    tile_prop = get_tile_properties(gmap, player.xpos, player.ypos + inc)
    # print("tp", tile_prop)
    if tile_prop["collision"]:
        damage = tile_prop["damage"]
        player.health -= damage
        actions.append(dict(key="collision_y", target=player.id, val=inc, damage=damage))
        if player.health <= 0:
            actions.append(dict(key="death", target=player.id, type="collision"))
            kill_player(player)
        return actions

    if tile_prop["void"]:
        player.health = 0
        actions.append({"key": "move_y", "target": player.id, "from": player.ypos, "to": player.ypos + inc})
        actions.append(dict(key="death", target=player.id, type="void"))
        kill_player(player)
        return actions

    if (player.ypos + inc < 0) or (player.ypos + inc >= gmap["height"]):
        player.health = 0
        actions.append({"key": "move_y", "target": player.id, "from": player.ypos, "to": player.ypos + inc})
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
    actions.append({"key": "move_y", "target": player.id, "from": player.ypos, "to": player.ypos + inc})
    player.ypos += inc
    return actions


def get_tile_properties(gmap, x, y):
    bg = list(filter(lambda l: l["name"] == "background", gmap["layers"]))[0]
    # for j in range(bg["height"]):
    #    print(f'bg', bg["data"][j * bg["width"]:(j+1)*bg["width"]])
    if (x < 0) or (x >= bg["width"]) or (y < 0) or (y >= bg["height"]):
        return dict(void=True, collision=False, damage=0)
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
    with open(os.path.join(MAPSDIR, fname)) as fh:
        dt = json.load(fh)
    # tl = dt.layers[0].data
    # colliding = []
    return dt


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

    req_props = set(["collision", "current_x", "current_y", "damage", "void", "vortex", "turret_x", "turret_y"])
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
