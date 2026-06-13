import random

from pigame.game_logic import get_player_deck, set_player_deck


def bot_submit_cards(gamecfg, player_idx, bot_type):
    player_id = gamecfg.player_ids[player_idx]
    deck = get_player_deck(gamecfg, player_id)
    next_card = gamecfg.player_next_card[player_idx]
    ncardsavail = gamecfg.ncardsavail
    hand = deck[next_card : next_card + ncardsavail]
    random.shuffle(hand)
    deck[next_card : next_card + ncardsavail] = hand
    set_player_deck(gamecfg, player_id, deck)
