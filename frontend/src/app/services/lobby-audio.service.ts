import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

// Original "swashbuckler" adventure theme for the lobby/menu screens — a
// full ~20-bar arrangement (intro -> theme -> bridge -> climax -> repeat)
// in the spirit of pirate-adventure film scores, NOT a reproduction of any
// copyrighted melody. Shares the `audio_music` on/off preference with the
// in-game GameAudio (frontend/src/app/game/game-audio.ts) via musicOn$, so
// the single header "Music" toggle controls both.
//
// D natural minor throughout. All four melodic/harmonic tracks (strings,
// bass, lead, brass) share one 80-beat master cycle so their section
// changes land together; percussion follows the same cycle for dynamics
// (quiet intro, driving theme, sparse bridge, full climax).
const D2 = 73.42,
  F2 = 87.31,
  G2 = 98.0,
  A2 = 110.0,
  Bb2 = 116.54,
  C3 = 130.81,
  D3 = 146.83,
  A3 = 220.0,
  Bb3 = 233.08,
  C4 = 261.63,
  D4 = 293.66,
  E4 = 329.63,
  F4 = 349.23,
  G4 = 392.0,
  A4 = 440.0,
  Bb4 = 466.16,
  C5 = 523.25,
  D5 = 587.33,
  F5 = 698.46,
  G5 = 783.99;
const R = 0; // rest marker

@Injectable({ providedIn: 'root' })
export class LobbyAudioService {
  private ctx: AudioContext | null = null;
  private musicGain: GainNode | null = null;
  private scheduled = false;
  private timeout: any = null;

  private stringTime = 0;
  private stringIdx = 0;
  private bassTime = 0;
  private bassIdx = 0;
  private leadTime = 0;
  private leadIdx = 0;
  private brassTime = 0;
  private brassIdx = 0;
  private percTime = 0;
  private percBeat = 0;

  musicVolume = 0.15;
  musicOn = localStorage.getItem('audio_music') !== 'off';
  // Single source of truth for the shared "Music" preference (the header
  // toggle) so any currently-playing GameAudio instance can stay in sync
  // live, not just on its own next construction.
  musicOn$ = new BehaviorSubject<boolean>(this.musicOn);

  private static readonly BPM = 132;

  // Section boundaries within the shared 80-beat master cycle.
  private static readonly INTRO_END = 16;
  private static readonly THEME_END = 48;
  private static readonly BRIDGE_END = 64;
  private static readonly CYCLE_BEATS = 80;

  // ── Strings: eighth-note ostinato, one long arc through the whole cycle ──
  // Intro (16 beats): sparse quarter-note arpeggio, i-i-VI-VII
  private static readonly STR_INTRO: number[] = [
    D4, R, F4, R, A4, R, F4, R, D4, R, F4, R, A4, R, F4, R, Bb3, R, D4, R, F4, R, D4, R, C4, R, E4, R, G4, R, E4, R,
  ];
  // Theme A (64 beats / 8 bars): full driving ostinato, i-i-VI-VII x2,
  // matching BASS's 8-bar theme progression below.
  private static readonly STR_THEME: number[] = [
    D4, F4, A4, F4, D4, F4, A4, F4,
    D4, F4, A4, F4, D4, F4, A4, F4,
    Bb3, D4, F4, D4, Bb3, D4, F4, D4,
    C4, E4, G4, E4, C4, E4, G4, E4,
    D4, F4, A4, F4, D4, F4, A4, F4,
    D4, F4, A4, F4, D4, F4, A4, F4,
    Bb3, D4, F4, D4, Bb3, D4, F4, D4,
    C4, E4, G4, E4, C4, E4, G4, E4,
  ];
  // Bridge (16 beats): thinner, brighter relative-major color, III-VII-VI-v
  private static readonly STR_BRIDGE: number[] = [
    F4, R, A4, R, C5, R, A4, R, C4, R, E4, R, G4, R, E4, R, Bb3, R, D4, R, F4, R, D4, R, A3, R, C4, R, E4, R, C4, R,
  ];
  // Climax (16 beats): loud, full, octave lift on the final bar
  private static readonly STR_CLIMAX: number[] = [
    D4, F4, A4, F4, D4, F4, A4, F4,
    Bb3, D4, F4, D4, Bb3, D4, F4, D4,
    C4, E4, G4, E4, C4, E4, G4, E4,
    D5, A4, F4, A4, D5, A4, F4, A4,
  ];
  private static readonly STRINGS: number[] = [
    ...LobbyAudioService.STR_INTRO,
    ...LobbyAudioService.STR_THEME,
    ...LobbyAudioService.STR_BRIDGE,
    ...LobbyAudioService.STR_CLIMAX,
  ];

  // ── Bass: one sustained root per bar, tracking the same chords ──
  private static readonly BASS: [number, number][] = [
    // intro — i i VI VII
    [D2, 4], [D2, 4], [Bb2, 4], [C3, 4],
    // theme — i i VI VII i i VI VII
    [D2, 4], [D2, 4], [Bb2, 4], [C3, 4], [D2, 4], [D2, 4], [Bb2, 4], [C3, 4],
    // bridge — III VII VI v
    [F2, 4], [C3, 4], [Bb2, 4], [A2, 4],
    // climax — i VI VII i(up)
    [D2, 4], [Bb2, 4], [C3, 4], [D3, 4],
  ];

  // ── Lead: the actual melodic hook — silent in the intro, then develops ──
  private static readonly LEAD_THEME: [number, number][] = [
    [A4, 2], [C5, 2], [D5, 2], [C5, 2],
    [Bb4, 2], [A4, 2], [F4, 2], [A4, 2],
    [C5, 2], [Bb4, 2], [A4, 2], [G4, 2],
    [A4, 1], [Bb4, 1], [C5, 2], [D5, 4],
  ];
  private static readonly LEAD_BRIDGE: [number, number][] = [
    [F4, 2], [A4, 2], [C5, 2], [Bb4, 2],
    [A4, 2], [G4, 2], [E4, 2], [F4, 2],
  ];
  private static readonly LEAD_CLIMAX: [number, number][] = [
    [D5, 1], [D5, 1], [F5, 1], [A4, 1], [D5, 1], [F5, 1], [G5, 2],
    [F5, 1], [D5, 1], [C5, 1], [Bb4, 1], [A4, 1], [G4, 1], [F4, 2],
  ];
  private static readonly LEAD: [number, number][] = [
    [R, 16],
    ...LobbyAudioService.LEAD_THEME,
    ...LobbyAudioService.LEAD_BRIDGE,
    ...LobbyAudioService.LEAD_CLIMAX,
  ];

  // ── Brass: punctuation only — silent in intro/bridge, accents in theme,
  // full fanfare in the climax ──
  private static readonly BRASS: [number, number][] = [
    [R, 16],
    [A4, 1], [R, 3], [A4, 1], [R, 3], [D5, 1], [R, 3], [G4, 1], [R, 3],
    [A4, 1], [R, 3], [A4, 1], [R, 3], [D5, 1], [R, 3], [G4, 1], [R, 3],
    [R, 16],
    [D5, 2], [F5, 2], [A4, 2], [D5, 2], [G5, 2], [F5, 2], [D5, 2], [A4, 2],
  ];

  private static readonly STRINGS_LEN = LobbyAudioService.STRINGS.length; // eighth-note slots

  // ── Persistent preference toggle ─────────────────────────────────────
  // Only updates the shared preference/gain — does NOT start or stop
  // scheduling itself, since that depends on whether the current route is
  // actually the lobby (the caller decides that, see app.component.ts).
  setMusicOn(val: boolean) {
    this.musicOn = val;
    localStorage.setItem('audio_music', val ? 'on' : 'off');
    if (this.musicGain && this.ctx) this.musicGain.gain.setTargetAtTime(val ? this.musicVolume : 0, this.ctx.currentTime, 0.15);
    this.musicOn$.next(val);
  }

  private ensure(): AudioContext {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.musicGain = this.ctx.createGain();
      this.musicGain.gain.value = this.musicOn ? this.musicVolume : 0;
      this.musicGain.connect(this.ctx.destination);
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx;
  }

  start() {
    // re-sync with the shared preference in case it was changed elsewhere
    // (e.g. the in-game sound settings modal) since this service was created
    this.musicOn = localStorage.getItem('audio_music') !== 'off';
    if (!this.musicOn || this.scheduled) return;
    const ctx = this.ensure();
    this.scheduled = true;
    const t0 = ctx.currentTime + 0.15;
    this.stringTime = t0;
    this.stringIdx = 0;
    this.bassTime = t0;
    this.bassIdx = 0;
    this.leadTime = t0;
    this.leadIdx = 0;
    this.brassTime = t0;
    this.brassIdx = 0;
    this.percTime = t0;
    this.percBeat = 0;
    this.schedule();
  }

  stop() {
    this.scheduled = false;
    clearTimeout(this.timeout);
    this.timeout = null;
    if (this.ctx && this.musicGain) {
      const now = this.ctx.currentTime;
      this.musicGain.gain.setValueAtTime(this.musicGain.gain.value, now);
      this.musicGain.gain.linearRampToValueAtTime(0, now + 0.6);
      setTimeout(() => {
        if (this.musicGain) this.musicGain.gain.value = this.musicOn ? this.musicVolume : 0;
      }, 700);
    }
  }

  private schedule() {
    if (!this.scheduled || !this.ctx || !this.musicGain) return;
    const ctx = this.ctx;
    const beat = 60 / LobbyAudioService.BPM;
    const ahead = 0.5;

    while (this.stringTime < ctx.currentTime + ahead) {
      const freq = LobbyAudioService.STRINGS[this.stringIdx % LobbyAudioService.STRINGS_LEN];
      if (freq > 0) this.string(freq, this.stringTime, this.stringTime + beat * 0.46);
      this.stringTime += beat * 0.5;
      this.stringIdx++;
    }

    while (this.bassTime < ctx.currentTime + ahead) {
      const [freq, beats] = LobbyAudioService.BASS[this.bassIdx % LobbyAudioService.BASS.length];
      if (freq > 0) this.bass(freq, this.bassTime, this.bassTime + beats * beat * 0.92);
      this.bassTime += beats * beat;
      this.bassIdx++;
    }

    while (this.leadTime < ctx.currentTime + ahead) {
      const [freq, beats] = LobbyAudioService.LEAD[this.leadIdx % LobbyAudioService.LEAD.length];
      const dur = beats * beat;
      if (freq > 0) this.lead(freq, this.leadTime, this.leadTime + dur * 0.85);
      this.leadTime += dur;
      this.leadIdx++;
    }

    while (this.brassTime < ctx.currentTime + ahead) {
      const [freq, slotBeats] = LobbyAudioService.BRASS[this.brassIdx % LobbyAudioService.BRASS.length];
      const slotDur = slotBeats * beat;
      if (freq > 0) {
        const noteDur = slotDur * (slotBeats >= 2 ? 0.75 : 0.55);
        this.brass(freq, this.brassTime, this.brassTime + noteDur);
      }
      this.brassTime += slotDur;
      this.brassIdx++;
    }

    while (this.percTime < ctx.currentTime + ahead) {
      const cyclePos = this.percBeat % LobbyAudioService.CYCLE_BEATS;
      const beatInBar = this.percBeat % 4;
      if (cyclePos < LobbyAudioService.INTRO_END) {
        // intro — soft downbeat only
        if (beatInBar === 0) this.kick(this.percTime, 0.28);
      } else if (cyclePos < LobbyAudioService.THEME_END) {
        // theme — driving kick/tick
        if (beatInBar === 0 || beatInBar === 2) this.kick(this.percTime, 0.5);
        else this.tick(this.percTime);
      } else if (cyclePos < LobbyAudioService.BRIDGE_END) {
        // bridge — sparse, tick only
        if (beatInBar === 0 || beatInBar === 2) this.tick(this.percTime);
      } else {
        // climax — full kick/tick plus shaker on every eighth
        if (beatInBar === 0 || beatInBar === 2) this.kick(this.percTime, 0.6);
        else this.tick(this.percTime);
        this.shaker(this.percTime + beat * 0.5);
      }
      this.percTime += beat;
      this.percBeat++;
    }

    this.timeout = setTimeout(() => this.schedule(), 150);
  }

  // Sawtooth string section, low-passed for a bowed-ensemble feel
  private string(freq: number, t0: number, t1: number) {
    const ctx = this.ctx!;
    const o = ctx.createOscillator();
    o.type = 'sawtooth';
    o.frequency.value = freq;
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 2200;
    lp.Q.value = 0.7;
    const g = ctx.createGain();
    const atk = 0.012;
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(0.22, t0 + atk);
    g.gain.linearRampToValueAtTime(0, t1);
    o.connect(lp);
    lp.connect(g);
    g.connect(this.musicGain!);
    o.start(t0);
    o.stop(t1 + 0.05);
  }

  // Warm sine/triangle bass foundation, slow attack, sustained under the bar
  private bass(freq: number, t0: number, t1: number) {
    const ctx = this.ctx!;
    const o = ctx.createOscillator();
    o.type = 'triangle';
    o.frequency.value = freq;
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 500;
    const g = ctx.createGain();
    const atk = 0.05;
    const rel = Math.min(0.2, (t1 - t0) * 0.15);
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(0.3, t0 + atk);
    g.gain.setValueAtTime(0.3, Math.max(t0 + atk, t1 - rel));
    g.gain.linearRampToValueAtTime(0, t1);
    o.connect(lp);
    lp.connect(g);
    g.connect(this.musicGain!);
    o.start(t0);
    o.stop(t1 + 0.05);
  }

  // Solo horn-like lead voice — the memorable melodic hook, legato with vibrato
  private lead(freq: number, t0: number, t1: number) {
    const ctx = this.ctx!;
    const o = ctx.createOscillator();
    o.type = 'sawtooth';
    o.frequency.setValueAtTime(freq, t0);
    const lfo = ctx.createOscillator();
    lfo.type = 'sine';
    lfo.frequency.value = 5;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = freq * 0.01;
    lfo.connect(lfoGain);
    lfoGain.connect(o.frequency);
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = freq * 2.0;
    bp.Q.value = 1.1;
    const g = ctx.createGain();
    const atk = 0.03;
    const rel = Math.min(0.15, (t1 - t0) * 0.25);
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(0.3, t0 + atk);
    g.gain.setValueAtTime(0.3, Math.max(t0 + atk, t1 - rel));
    g.gain.linearRampToValueAtTime(0, t1);
    o.connect(bp);
    bp.connect(g);
    g.connect(this.musicGain!);
    lfo.start(t0);
    lfo.stop(t1 + 0.05);
    o.start(t0);
    o.stop(t1 + 0.05);
  }

  // Sawtooth brass stab through a bandpass formant for a horn-like edge
  private brass(freq: number, t0: number, t1: number) {
    const ctx = this.ctx!;
    for (const det of [0, 0.006, -0.006]) {
      const o = ctx.createOscillator();
      o.type = 'sawtooth';
      o.frequency.value = freq * (1 + det);
      const bp = ctx.createBiquadFilter();
      bp.type = 'bandpass';
      bp.frequency.value = freq * 1.8;
      bp.Q.value = 1.4;
      const g = ctx.createGain();
      const atk = 0.02;
      const rel = Math.min(0.12, (t1 - t0) * 0.3);
      g.gain.setValueAtTime(0, t0);
      g.gain.linearRampToValueAtTime(0.26, t0 + atk);
      g.gain.setValueAtTime(0.26, Math.max(t0 + atk, t1 - rel));
      g.gain.linearRampToValueAtTime(0, t1);
      o.connect(bp);
      bp.connect(g);
      g.connect(this.musicGain!);
      o.start(t0);
      o.stop(t1 + 0.05);
    }
  }

  private noise(t0: number, t1: number, vol: number, loHz: number, hiHz: number) {
    const ctx = this.ctx!;
    const len = Math.ceil(ctx.sampleRate * (t1 - t0 + 0.1));
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const flt = ctx.createBiquadFilter();
    flt.type = 'bandpass';
    flt.frequency.value = (loHz + hiHz) / 2;
    flt.Q.value = (loHz + hiHz) / (hiHz - loHz);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(vol, t0 + 0.008);
    g.gain.linearRampToValueAtTime(0, t1);
    src.connect(flt);
    flt.connect(g);
    g.connect(this.musicGain!);
    src.start(t0);
    src.stop(t1 + 0.05);
  }

  private kick(t: number, vol = 0.5) {
    const ctx = this.ctx!;
    const o = ctx.createOscillator();
    o.type = 'sine';
    o.frequency.setValueAtTime(100, t);
    o.frequency.exponentialRampToValueAtTime(34, t + 0.13);
    const g = ctx.createGain();
    g.gain.setValueAtTime(vol, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.18);
    o.connect(g);
    g.connect(this.musicGain!);
    o.start(t);
    o.stop(t + 0.2);
  }

  private tick(t: number) {
    this.noise(t, t + 0.045, 0.13, 2500, 8000);
  }

  private shaker(t: number) {
    this.noise(t, t + 0.03, 0.06, 4000, 11000);
  }

  destroy() {
    this.stop();
    this.ctx?.close();
    this.ctx = null;
    this.musicGain = null;
  }
}
