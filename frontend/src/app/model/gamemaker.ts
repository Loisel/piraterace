export interface GameMaker {
  id: number;
  mode: string;
  mapfile: string;
  player_ids: number[];
  player_names: string[];
  player_colors: string[];
  player_teams: number[];
  player_ready: boolean[];
  caller_idx: number;
  player_color_choices: string[];
}
