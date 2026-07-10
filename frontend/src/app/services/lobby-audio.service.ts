import { Injectable } from '@angular/core';

// Original "swashbuckler" adventure theme for the lobby/menu screens —
// driving minor-key string ostinato + brass stabs, in the spirit of
// pirate-adventure film scores (not a reproduction of any copyrighted
// melody). Shares the `audio_music` on/off preference with the in-game
// GameAudio (frontend/src/app/game/game-audio.ts) so the single "Music"
// toggle in the sound settings modal controls both.
@Injectable({ providedIn: 'root' })
export class LobbyAudioService {
  private ctx: AudioContext | null = null;
  private musicGain: GainNode | null = null;
  private scheduled = false;
  private timeout: any = null;

  private stringTime = 0;
  private stringIdx = 0;
  private brassTime = 0;
  private brassIdx = 0;
  private percTime = 0;
  private percBeat = 0;

  musicVolume = 0.15;
  musicOn = localStorage.getItem('audio_music') !== 'off';

  private static readonly BPM = 138;

  // Driving eighth-note string ostinato — D natural minor
  private static readonly STRINGS: number[] = [
    293.66, 349.23, 440.0, 349.23, // D4 F4 A4 F4
    293.66, 349.23, 440.0, 349.23,
    261.63, 349.23, 415.3, 349.23, // C4 F4 Ab4 F4
    293.66, 349.23, 440.0, 523.25, // ...climb to D5
  ];

  // Brass fanfare stabs — sequential [freq, slot-beats] pairs, freq 0 = rest.
  // Each note is played short/punchy within its slot, mirroring how
  // GameAudio's MELODY/BASS patterns are scheduled.
  private static readonly BRASS: [number, number][] = [
    [440.0, 1], [523.25, 1], [587.33, 2], [0, 4],
    [440.0, 1], [523.25, 1], [659.25, 2], [0, 4],
    [493.88, 1], [440.0, 1], [392.0, 2], [0, 4],
  ];

  // Only updates the shared preference/gain — does NOT start or stop
  // scheduling itself, since that depends on whether the current route is
  // actually the lobby (the caller decides that, see app.component.ts).
  setMusicOn(val: boolean) {
    this.musicOn = val;
    localStorage.setItem('audio_music', val ? 'on' : 'off');
    if (this.musicGain && this.ctx) this.musicGain.gain.setTargetAtTime(val ? this.musicVolume : 0, this.ctx.currentTime, 0.15);
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
      const freq = LobbyAudioService.STRINGS[this.stringIdx % LobbyAudioService.STRINGS.length];
      this.string(freq, this.stringTime, this.stringTime + beat * 0.46);
      this.stringTime += beat * 0.5;
      this.stringIdx++;
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
      const b = this.percBeat % 4;
      if (b === 0) this.kick(this.percTime);
      else this.tick(this.percTime);
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

  private kick(t: number) {
    const ctx = this.ctx!;
    const o = ctx.createOscillator();
    o.type = 'sine';
    o.frequency.setValueAtTime(100, t);
    o.frequency.exponentialRampToValueAtTime(34, t + 0.13);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.5, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.18);
    o.connect(g);
    g.connect(this.musicGain!);
    o.start(t);
    o.stop(t + 0.2);
  }

  private tick(t: number) {
    this.noise(t, t + 0.045, 0.13, 2500, 8000);
  }

  destroy() {
    this.stop();
    this.ctx?.close();
    this.ctx = null;
    this.musicGain = null;
  }
}
