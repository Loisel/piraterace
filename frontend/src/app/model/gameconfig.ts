export interface GameConfig {
  all_ready: boolean;
  caller_id: number;
  caller_idx: number;
  CANNON_DIRECTION_DESCR2ID: any;
  countdown: number;
  creator_userid: number;
  gamename: string;
  id: number;
  mapfile: string;
  mapinfo: any;
  mode: string;
  ncardsavail: number;
  ncardslots: number;
  path_highlighting: boolean;
  treasure_preview: boolean;
  treasures_per_round: number;
  percentage_repaircards: number;
  player_color_choices: string[];
  player_colors: string[];
  player_ids: number[];
  player_names: string[];
  player_ready: boolean[];
  player_is_bot: boolean[];
  player_bot_type: string[];
  nmaxplayers: number;
  request_id: number;
}
