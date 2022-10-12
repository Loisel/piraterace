import json
import os
import random
import types

from piraterace.settings import MAPSDIR
from piplayer.models import Account
from pigame.models import card_id_rank, CARDS, DEFAULT_DECK, DIRID2MOVE, DIRID2NAME, FREE_HEALTH_OFFSET


def argsort(seq):
    return sorted(range(len(seq)), key=seq.__getitem__)


def flatten_list_of_tuples(lot):
    return [i for j in lot for i in j]


def get_cards_on_hand(player, ncards):
    """
    get next ncards that a player can draw from his deck
        return list of tuples of (playerid, card)
    """
    if player.next_card + ncards - 1 > len(player.deck):
        remaining_cards = player.deck[player.next_card :]
        old_cards = player.deck[: player.next_card]
        random.shuffle(old_cards)
        player.deck = remaining_cards + old_cards
        player.next_card = 0
        player.save(update_fields=["next_card", "deck"])

    res = []
    for i in range(0, ncards):
        res.append((player.pk, player.deck[(player.next_card + i)]))
    return res


def determine_next_cards_played(players_in_game, player_ids, ncardslots):
    """
    returns the cards in order that they will be played in a game by participating players.
    ncardslots will be returned for each player
    returns list of (playerid, card) tuples
    """

    # print(f"player_ids {player_ids}, player_in_game {players_in_game}")
    cards_per_player = []
    for i in player_ids:
        if i in players_in_game:
            cards_per_player.append(get_cards_on_hand(Account.objects.get(pk=i), ncardslots))
        else:  # play random cards from default deck for zombie players
            random_cards = [(i, random.choice(DEFAULT_DECK)) for _ in range(ncardslots)]
            cards_per_player.append(random_cards)

    # sort by ranking...
    ret = []
    for i in range(ncardslots):
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
        p.start_loc_x = x
        p.start_loc_y = y
        p.start_direction = direction
        p.xpos = x
        p.ypos = y
        p.direction = direction
        p.next_checkpoint = 1
        p.color = color
        p.team = team
        p.health = game.config.ncardsavail + FREE_HEALTH_OFFSET
        players[pid] = p

    cardstack = list(zip(stack[::2], stack[1::2]))
    checkpoints = determine_checkpoint_locations(initial_map)

    # print(f"full cardstack {cardstack}")

    actionstack = []
    # determine the rounds dynamically to avoid a race condition with respect to the
    # round counter
    Nrounds = int(len(cardstack) / (len(players) * game.config.ncardslots))
    # we do not generate the actions for the *current* round `Nround`!
    for rnd in range(Nrounds):

        stack_start = rnd * game.config.ncardslots * len(players)
        stack_end = (rnd + 1) * game.config.ncardslots * len(players)
        this_round_cards = cardstack[stack_start:stack_end]
        # print(f"this_round_cards: {this_round_cards}")

        for icard in range(game.config.ncardslots):
            for iplayer in range(len(players)):
                playerid, card = this_round_cards[icard * len(players) + iplayer]
                if players[playerid].health > 0:
                    actions = get_actions_for_card(game, initial_map, players, players[playerid], card)
                    actionstack.extend(actions)

            # board moves
            board_moves_actions = board_moves(game, initial_map, players)
            actionstack.append(board_moves_actions)

            # cannons
            cannon_actions = []
            for p in players.values():
                if p.health > 0:
                    cannon_actions.extend(shoot_cannon(game, initial_map, players, p))
            actionstack.append(cannon_actions)

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

        # respawns
        respawn_actions = []
        for p in players.values():
            if p.health <= 0:
                p.health = game.config.ncardsavail
                p.xpos = p.start_loc_x
                p.ypos = p.start_loc_y
                respawn_actions.append(dict(key="respawn", target=p.id))
        actionstack.append(respawn_actions)

        # [print(i, a) for i, a in enumerate(actionstack)]

    return players, actionstack


def kill_player(p):
    p.health = 0
    p.xpos = p.ypos = -99


def board_moves(game, gmap, players):
    # TODO: disable collisions for board_moves
    actions = []
    for pid, p in players.items():
        if p.health <= 0:
            break
        tile_prop = get_tile_properties(gmap, p.xpos, p.ypos)
        if tile_prop["vortex"] != 0:
            actions.append(dict(key="rotate", target=pid, val=tile_prop["vortex"]))
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


def shoot_cannon(game, gmap, players, player):
    actions = []
    CB_DAMAGE = 1

    xinc = DIRID2MOVE[player.direction][0]
    yinc = DIRID2MOVE[player.direction][1]

    cb_x = player.xpos
    cb_y = player.ypos

    while (cb_x >= 0 and cb_x < gmap["width"]) and (cb_y >= 0 and cb_y < gmap["height"]):
        cb_x += xinc
        cb_y += yinc
        # hit a player ?
        for other_player in players.values():
            if (cb_x == other_player.xpos) and (cb_y == other_player.ypos):
                other_player.health -= CB_DAMAGE
                actions.append(
                    dict(key="shot", target=player.id, other_player=other_player.id, damage=CB_DAMAGE, collided_at=(cb_x, cb_y))
                )
                if other_player.health <= 0:
                    actions.append(dict(key="death", target=other_player.id, type="cannon"))
                    kill_player(other_player)

                return actions
        # hit a colliding map tile?
        if get_tile_properties(gmap, cb_x, cb_y)["collision"]:
            actions.append(dict(key="shot", target=player.id, collided_at=(cb_x, cb_y)))
            return actions

    actions.append(dict(key="shot", target=player.id, collided_at=(cb_x, cb_y)))
    return actions


def get_actions_for_card(game, gmap, players, player, card):

    actions = []
    cardid, cardrank = card_id_rank(card)
    rot = CARDS[cardid]["rot"]
    if rot != 0:
        actions.append([dict(key="rotate", target=player.id, val=rot)])
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
        actions.append(dict(key="move_x", target=player.id, val=inc))
        actions.append(dict(key="death", target=player.id, type="void"))
        kill_player(player)
        return actions

    if (player.xpos + inc < 0) or (player.xpos + inc >= gmap["width"]):
        player.health = 0
        actions.append(dict(key="move_x", target=player.id, val=inc))
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
    player.xpos += inc
    actions.append(dict(key="move_x", target=player.id, val=inc))
    return actions


def move_player_y(game, gmap, players, player, inc, push_players=True):
    actions = []
    tile_prop = get_tile_properties(gmap, player.xpos, player.ypos + inc)
    print("tp", tile_prop)
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
        actions.append(dict(key="move_y", target=player.id, val=inc))
        actions.append(dict(key="death", target=player.id, type="void"))
        kill_player(player)
        return actions

    if (player.ypos + inc < 0) or (player.ypos + inc >= gmap["height"]):
        player.health = 0
        actions.append(dict(key="move_y", target=player.id, val=inc))
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
    player.ypos += inc
    actions.append(dict(key="move_y", target=player.id, val=inc))
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

    req_props = set(["collision", "current_x", "current_y", "damage", "void", "vortex"])
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
