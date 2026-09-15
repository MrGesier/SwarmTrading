import type {Horizon,Term} from "./multiscale";
export type Candle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};
export type History = {
  time: number;
  mid: number;
  consensus: number;
  horizon_consensus?: Record<string, number>;
  market_entropy: number;
  swarm_entropy: number;
  slope: number;
  levels: number[][];
  horizon_metrics?:Record<string,{market_entropy:number;swarm_entropy:number;effective:number|null;ready:boolean}>;
};
export type Strategy = {
  id: string;
  family: string;
  horizon: number;
  threshold: number;
  gain: number;
  signal: number;
  weight: number;
};
export type Transition = {
  time: number;
  state: string;
  previous: string;
  score: number;
  reasons: string[];
};
export type State = {
  horizons?:Record<string,Horizon>;
  term_structure?:Term;
  timestamp: number;
  mode: string;
  symbol: string;
  venue: string;
  regime: string;
  health: {
    status: string;
    age_ms: number | null;
    sequence: number;
    message: string;
    recording: string;
  };
  features: {
    mid: number;
    spread: number;
    microprice: number;
    micro_delta: number;
    imbalance: number;
    weighted_imbalance: number;
    flow: number;
    volatility: number;
    returns: Record<string, number>;
    volume: number;
    intensity: number;
    bid_depth: number;
    ask_depth: number;
    ready: Record<string, boolean>;
    history_seconds: number;
    bid_concentration: number;
    ask_concentration: number;
    vacuum_up: number;
    vacuum_down: number;
  };
  candles: Candle[];
  history: History[];
  bids: number[][];
  asks: number[][];
  families: {
    name: string;
    short: number;
    neutral: number;
    long: number;
    consensus: number;
  }[];
  strategies: Strategy[];
  triggers: {
    bp: number;
    price: number;
    density: number;
    resistance: number;
  }[];
  cone: {
    horizon: number;
    consensus: number;
    ready: boolean;
    remaining: number;
  }[];
  entropy: {
    market: number;
    swarm: number;
    price: number;
    book: number;
    trade: number;
    slope: number;
  };
  swarm: {
    raw: number;
    active: number;
    effective: number | null;
    support: number[];
    consensus: number;
    velocity: number;
  };
  intent: {
    state: string;
    score: number;
    reasons: string[];
    calibrated: boolean;
  };
  timeline: Transition[];
};
