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
  percentage_repaircards: number;
  player_color_choices: string[];
  player_colors: string[];
  player_ids: number[];
  player_names: string[];
  player_ready: boolean[];
  request_id: number;
}
