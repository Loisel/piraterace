export interface GameInfo {
  game_id: number;
  time_started: string;
  cardslots: number;
  cards_played: number[];
  map: any;
  mapfile: string;
  checkpoints: any;
  me: number;
  countdown_duration: number;
  time_per_action: number;
  countdown: number;
  initial_health: number;
  CARDS: any;
  CANNON_DIRECTION_DESCR2ID: any;
  path_highlighting: boolean;
  actionstack: any[];
  Ngameround: number;
  state: string;
  players: any;
  stats: any;
}
