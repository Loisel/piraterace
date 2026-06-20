export class GameAudio {
  private ctx: AudioContext | null = null;
  private sfxGain: GainNode | null = null;
  private musicGain: GainNode | null = null;
  private bgScheduled = false;
  private bgTimeout: any = null;
  // Separate time/index pointers so melody, bass and percussion advance independently
  private bgMelTime = 0; private bgMelIdx = 0;
  private bgBasTime = 0; private bgBasIdx = 0;
  private bgPercTime = 0; private bgPercBeat = 0;

  sfxVolume = 0.55;
  musicVolume = 0.18;
  sfxOn = localStorage.getItem('audio_sfx') !== 'off';
  musicOn = localStorage.getItem('audio_music') !== 'off';

  setMusicOn(val: boolean) {
    this.musicOn = val;
    localStorage.setItem('audio_music', val ? 'on' : 'off');
    if (this.musicGain && this.ctx)
      this.musicGain.gain.setTargetAtTime(val ? this.musicVolume : 0, this.ctx.currentTime, 0.15);
    if (val && !this.bgScheduled && this.ctx) this.startBackgroundMusic();
    else if (!val) { this.bgScheduled = false; clearTimeout(this.bgTimeout); this.bgTimeout = null; }
  }

  setSfxOn(val: boolean) {
    this.sfxOn = val;
    localStorage.setItem('audio_sfx', val ? 'on' : 'off');
    if (this.sfxGain && this.ctx)
      this.sfxGain.gain.setTargetAtTime(val ? this.sfxVolume : 0, this.ctx.currentTime, 0.05);
  }

  private ensure(): AudioContext {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      const master = this.ctx.createGain();
      master.gain.value = 1.0;
      master.connect(this.ctx.destination);
      this.sfxGain = this.ctx.createGain();
      this.sfxGain.gain.value = this.sfxOn ? this.sfxVolume : 0;
      this.sfxGain.connect(master);
      this.musicGain = this.ctx.createGain();
      this.musicGain.gain.value = this.musicOn ? this.musicVolume : 0;
      this.musicGain.connect(master);
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx;
  }

  // Basic oscillator with linear ADSR envelope
  private tone(out: GainNode, freq: number, type: OscillatorType, t0: number, t1: number, vol: number, freqEnd?: number) {
    const ctx = this.ctx!;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(vol, t0 + 0.008);
    g.gain.setValueAtTime(vol, Math.max(t0 + 0.008, t1 - 0.04));
    g.gain.linearRampToValueAtTime(0, t1);
    g.connect(out);
    const o = ctx.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(freq, t0);
    if (freqEnd !== undefined) o.frequency.exponentialRampToValueAtTime(freqEnd, t1);
    o.connect(g);
    o.start(t0); o.stop(t1 + 0.05);
  }

  // Bandpass-filtered white noise burst
  private noise(out: GainNode, t0: number, t1: number, vol: number, loHz = 200, hiHz = 4000) {
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
    src.connect(flt);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(vol, t0 + 0.01);
    g.gain.linearRampToValueAtTime(0, t1);
    flt.connect(g); g.connect(out);
    src.start(t0); src.stop(t1 + 0.05);
  }

  // Formant-filtered sawtooth voice (simulates a shouting human voice).
  // fund: fundamental Hz (~150-250 for a male shout)
  // f1, f2: first and second formant peaks that define the vowel
  //   "AH": f1=800  f2=1200   "OH/NO": f1=500  f2=900
  //   "EH": f1=600  f2=1700   "EE/scream": f1=300  f2=2300
  //   "HO": f1=500  f2=800
  private vocal(out: GainNode, fund: number, t0: number, t1: number, vol: number,
                f1: number, f2: number, fundEnd?: number) {
    const ctx = this.ctx!;
    const atk = 0.04;
    const rel = Math.min(0.12, (t1 - t0) * 0.25);
    // 3 slightly-detuned voices for a "crowd" feel
    for (let v = 0; v < 3; v++) {
      const det = (v - 1) * 0.009;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, t0);
      g.gain.linearRampToValueAtTime(vol / 2.5, t0 + atk);
      g.gain.setValueAtTime(vol / 2.5, Math.max(t0 + atk, t1 - rel));
      g.gain.linearRampToValueAtTime(0, t1);

      const o = ctx.createOscillator();
      o.type = 'sawtooth';
      o.frequency.setValueAtTime(fund * (1 + det), t0);
      if (fundEnd !== undefined) o.frequency.exponentialRampToValueAtTime(fundEnd * (1 + det), t1);

      // Two bandpass formant filters in parallel
      const bp1 = ctx.createBiquadFilter();
      bp1.type = 'bandpass'; bp1.frequency.value = f1; bp1.Q.value = f1 / 120;
      const bp2 = ctx.createBiquadFilter();
      bp2.type = 'bandpass'; bp2.frequency.value = f2; bp2.Q.value = f2 / 180;

      o.connect(bp1); bp1.connect(g);
      o.connect(bp2); bp2.connect(g);
      g.connect(out);
      o.start(t0); o.stop(t1 + 0.05);
    }
  }

  // ── Sound effects ──────────────────────────────────────────────────────────

  playCardReorder() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.noise(this.sfxGain!, t, t + 0.05, 0.5, 1500, 6000);
  }

  playTreasurePickup() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    [523, 659, 784, 1047].forEach((f, i) =>
      this.tone(this.sfxGain!, f, 'sine', t + i * 0.07, t + i * 0.07 + 0.18, 0.4));
  }

  // Crew: brief "AY!" cheer at a checkpoint
  playCheckpoint() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    const s = this.sfxGain!;
    this.vocal(s, 160, t, t + 0.48, 0.85, 600, 1700, 190);  // "AY/EH" vowel
    this.vocal(s, 205, t + 0.04, t + 0.48, 0.45, 650, 1600, 225);
    this.tone(s, 1047, 'sine', t, t + 0.28, 0.22);           // bell accent
  }

  // Crew: full victory roar "HOORAY!"
  playFinalCheckpoint() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    const s = this.sfxGain!;
    // First wave — "AH" open vowel (F1=800, F2=1200)
    this.vocal(s, 140, t,        t + 1.0,  0.9,  800, 1200, 175);
    this.vocal(s, 172, t + 0.05, t + 1.0,  0.65, 780, 1100, 200);
    this.vocal(s, 118, t + 0.08, t + 0.9,  0.5,  720, 1000, 148);
    // Second louder wave
    this.vocal(s, 180, t + 0.65, t + 1.65, 0.95, 800, 1200, 215);
    this.vocal(s, 155, t + 0.70, t + 1.65, 0.65, 760, 1100, 185);
    this.vocal(s, 215, t + 0.75, t + 1.65, 0.4,  880, 1400, 235);
    // Triumphant brass-like stabs
    [523, 659, 784, 1047].forEach((f, i) =>
      this.tone(s, f, 'sawtooth', t + 0.5 + i * 0.11, t + 0.5 + i * 0.11 + 0.32, 0.22));
  }

  // Cannon blast — concussion boom + crack + echo
  playHit() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    const s = this.sfxGain!;
    // Low-end BOOM (pitch sweep 90→28 Hz)
    const o = ctx.createOscillator(); const g = ctx.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(90, t);
    o.frequency.exponentialRampToValueAtTime(28, t + 0.45);
    g.gain.setValueAtTime(0, t); g.gain.linearRampToValueAtTime(1.0, t + 0.006);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.6);
    o.connect(g); g.connect(s); o.start(t); o.stop(t + 0.65);
    // Initial crack — ultra-short broadband noise
    this.noise(s, t, t + 0.03, 1.0, 800, 14000);
    // Body rumble
    this.noise(s, t, t + 0.32, 0.65, 60, 450);
    // Echo boom ~230 ms later
    this.tone(s, 55, 'sine', t + 0.23, t + 0.58, 0.32, 24);
    this.noise(s, t + 0.23, t + 0.44, 0.22, 50, 280);
    // Sizzle / hot metal hiss
    this.noise(s, t + 0.02, t + 0.42, 0.28, 3000, 14000);
  }

  playBurnDamage() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.noise(this.sfxGain!, t, t + 0.18, 0.3, 600, 3000);
    this.tone(this.sfxGain!, 200, 'sawtooth', t, t + 0.12, 0.2, 120);
  }

  // Pirates wailing "NOOO!" as ship descends
  playSink() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    const s = this.sfxGain!;
    // "OH/OO" vowel (F1=500, F2=900), pitch diving from ~220 → 110 Hz
    this.vocal(s, 220, t,        t + 1.35, 0.85, 500, 900, 112);
    this.vocal(s, 200, t + 0.08, t + 1.25, 0.65, 470, 830, 102);
    this.vocal(s, 248, t + 0.13, t + 1.40, 0.45, 545, 960, 122);
    // Water gurgle / bubbles
    for (let i = 0; i < 6; i++)
      this.noise(s, t + i * 0.19, t + i * 0.19 + 0.13, 0.22, 220, 1600);
    // Structural groan of breaking hull
    this.tone(s, 80, 'sawtooth', t + 0.45, t + 1.1, 0.3, 38);
  }

  // Pirate terror-scream "AAAH!" before being eaten
  playOctopus() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    const s = this.sfxGain!;
    // Screaming "EEE" vowel (F1=300, F2=2300), pitch rising rapidly from panic
    this.vocal(s, 215, t,        t + 0.78, 0.9,  310, 2200, 465);
    this.vocal(s, 228, t + 0.04, t + 0.72, 0.65, 290, 2050, 442);
    // Abrupt cutoff: deep tentacle rumble
    this.tone(s, 65, 'sawtooth', t + 0.58, t + 1.05, 0.55, 28);
    this.noise(s, t + 0.52, t + 0.98, 0.42, 80, 600);
  }

  playRockHit() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.tone(this.sfxGain!, 190, 'sine', t, t + 0.18, 0.55, 60);
    this.noise(this.sfxGain!, t, t + 0.1, 0.5, 300, 2500);
  }

  // Crew chanting "Heave! Heave! HO!" while hammering
  playRepair() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    const s = this.sfxGain!;
    // "Heave!" — "EH" vowel (F1=600, F2=1700) × 2 grunts
    this.vocal(s, 145, t,        t + 0.17, 0.65, 600, 1700);
    this.vocal(s, 145, t + 0.24, t + 0.41, 0.65, 600, 1700);
    // "HO!" — "OH" vowel (F1=500, F2=800), louder, slightly higher
    this.vocal(s, 168, t + 0.48, t + 0.74, 0.92, 500, 800);
    // Hammer metallic taps
    this.tone(s, 660, 'square', t + 0.04, t + 0.09, 0.22);
    this.tone(s, 660, 'square', t + 0.28, t + 0.33, 0.22);
  }

  // Ship's bell — start of a new round
  playRoundStart() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.tone(this.sfxGain!, 110, 'sine', t,       t + 2.2,  0.5);
    this.tone(this.sfxGain!, 220, 'sine', t,       t + 1.6,  0.22);
    this.tone(this.sfxGain!, 330, 'sine', t + 0.03, t + 1.3, 0.12);
  }

  // Crew shouts "Set SAILS!" — countdown begins
  playSailsSet() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    const s = this.sfxGain!;
    // Quick "HEY!" attack — "EH" vowel
    this.vocal(s, 172, t,        t + 0.18, 0.7,  600, 1700);
    // "SAILS!" — open "AH" vowel, rising pitch
    this.vocal(s, 182, t + 0.13, t + 0.58, 0.95, 800, 1200, 218);
    this.vocal(s, 158, t + 0.15, t + 0.55, 0.58, 760, 1100, 192);
    this.noise(s, t, t + 0.08, 0.15, 2000, 8000);  // breath
  }

  // Drum + quick "Hey!" as sails unfurl
  playAnimationStart() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    const s = this.sfxGain!;
    this.noise(s, t, t + 0.12, 0.55, 60, 280);
    this.tone(s, 90, 'sine', t, t + 0.18, 0.45, 34);
    this.vocal(s, 178, t + 0.04, t + 0.26, 0.5, 700, 1200);
  }

  playShieldAbsorb() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.tone(this.sfxGain!, 880, 'sine', t, t + 0.22, 0.35);
    this.noise(this.sfxGain!, t, t + 0.15, 0.2, 2000, 6000);
  }

  // ── Background music — Sea Shanty ──────────────────────────────────────────
  // D Dorian (D E F G A B C D) — 4/4 at 108 BPM, 8-bar loop = 32 beats ≈ 17.8 s
  private static readonly BPM = 108;

  // [freq Hz, duration in quarter beats]  — total: 32 beats across 8 bars
  private static readonly MELODY: [number, number][] = [
    // bar 1
    [293.66, 1], [293.66, 0.5], [349.23, 0.5], [440.00, 2],
    // bar 2
    [391.99, 1], [349.23, 0.5], [329.63, 0.5], [293.66, 2],
    // bar 3
    [440.00, 1], [440.00, 0.5], [523.25, 0.5], [587.33, 2],
    // bar 4
    [523.25, 1], [440.00, 0.5], [391.99, 0.5], [440.00, 2],
    // bar 5
    [349.23, 1], [391.99, 0.5], [440.00, 0.5], [391.99, 1], [349.23, 0.5], [329.63, 0.5],
    // bar 6
    [293.66, 1], [329.63, 0.5], [349.23, 0.5], [391.99, 2],
    // bar 7
    [440.00, 1], [391.99, 0.5], [349.23, 0.5], [329.63, 1], [293.66, 0.5], [329.63, 0.5],
    // bar 8
    [293.66, 4],
  ];

  // Bass — half-note (2-beat) steps, 15 entries = 32 beats
  private static readonly BASS: [number, number][] = [
    [146.83, 2], [220.00, 2],  // D3 A3
    [196.00, 2], [261.63, 2],  // G3 C4
    [174.61, 2], [261.63, 2],  // F3 C4
    [196.00, 2], [146.83, 2],  // G3 D3
    [174.61, 2], [196.00, 2],  // F3 G3
    [146.83, 2], [220.00, 2],  // D3 A3
    [220.00, 2], [196.00, 2],  // A3 G3
    [146.83, 4],               // D3 (whole)
  ];

  startBackgroundMusic() {
    if (!this.musicOn) return;
    const ctx = this.ensure();
    if (this.bgScheduled) return;
    this.bgScheduled = true;
    const start = ctx.currentTime + 0.15;
    this.bgMelTime = start; this.bgMelIdx = 0;
    this.bgBasTime = start; this.bgBasIdx = 0;
    this.bgPercTime = start; this.bgPercBeat = 0;
    this.scheduleBGM();
  }

  private scheduleBGM() {
    if (!this.bgScheduled || !this.ctx || !this.musicGain) return;
    const ctx = this.ctx;
    const beat = 60 / GameAudio.BPM;
    const ahead = 0.45;
    const mel = GameAudio.MELODY;
    const bas = GameAudio.BASS;

    // Tin-whistle melody
    while (this.bgMelTime < ctx.currentTime + ahead) {
      const [freq, beats] = mel[this.bgMelIdx % mel.length];
      const dur = beats * beat;
      this.bgWhistle(freq, this.bgMelTime, this.bgMelTime + dur * 0.82);
      this.bgMelTime += dur;
      this.bgMelIdx++;
    }

    // Bass
    while (this.bgBasTime < ctx.currentTime + ahead) {
      const [freq, beats] = bas[this.bgBasIdx % bas.length];
      const dur = beats * beat;
      this.bgBass(freq, this.bgBasTime, this.bgBasTime + dur * 0.68);
      this.bgBasTime += dur;
      this.bgBasIdx++;
    }

    // Percussion — quarter-note grid: kick on 1 & 3, wood-block on 2 & 4
    while (this.bgPercTime < ctx.currentTime + ahead) {
      const beatInBar = this.bgPercBeat % 4;
      if (beatInBar === 0 || beatInBar === 2) this.bgKick(this.bgPercTime);
      else this.bgWoodblock(this.bgPercTime);
      this.bgPercTime += beat;
      this.bgPercBeat++;
    }

    this.bgTimeout = setTimeout(() => this.scheduleBGM(), 150);
  }

  // Penny-whistle / tin-flute note with slight vibrato
  private bgWhistle(freq: number, t0: number, t1: number) {
    const ctx = this.ctx!;
    // Square wave → low-pass for a pipe-like timbre
    const o = ctx.createOscillator();
    o.type = 'square';
    o.frequency.setValueAtTime(freq, t0);

    // Vibrato LFO (~5.5 Hz, ±1.1% depth)
    const lfo = ctx.createOscillator();
    lfo.type = 'sine'; lfo.frequency.value = 5.5;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = freq * 0.011;
    lfo.connect(lfoGain); lfoGain.connect(o.frequency);

    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass'; lp.frequency.value = Math.min(freq * 3.8, 4200); lp.Q.value = 0.5;

    const g = ctx.createGain();
    const atk = 0.026; const rel = Math.min(0.055, (t1 - t0) * 0.22);
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(0.26, t0 + atk);
    g.gain.setValueAtTime(0.26, Math.max(t0 + atk, t1 - rel));
    g.gain.linearRampToValueAtTime(0, t1);

    o.connect(lp); lp.connect(g); g.connect(this.musicGain!);
    lfo.start(t0); lfo.stop(t1 + 0.05);
    o.start(t0); o.stop(t1 + 0.05);
  }

  // Soft sine bass note
  private bgBass(freq: number, t0: number, t1: number) {
    const ctx = this.ctx!;
    const o = ctx.createOscillator();
    o.type = 'sine'; o.frequency.value = freq;
    const g = ctx.createGain();
    const atk = 0.03; const rel = Math.min(0.09, (t1 - t0) * 0.2);
    g.gain.setValueAtTime(0, t0);
    g.gain.linearRampToValueAtTime(0.24, t0 + atk);
    g.gain.setValueAtTime(0.24, Math.max(t0 + atk, t1 - rel));
    g.gain.linearRampToValueAtTime(0, t1);
    o.connect(g); g.connect(this.musicGain!);
    o.start(t0); o.stop(t1 + 0.05);
  }

  // Kick drum on beats 1 & 3
  private bgKick(t: number) {
    const ctx = this.ctx!;
    const o = ctx.createOscillator();
    o.type = 'sine';
    o.frequency.setValueAtTime(105, t);
    o.frequency.exponentialRampToValueAtTime(36, t + 0.15);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.72, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.22);
    o.connect(g); g.connect(this.musicGain!);
    o.start(t); o.stop(t + 0.25);
    // body thump
    this.noise(this.musicGain!, t, t + 0.04, 0.22, 45, 170);
  }

  // Wood-block accent on beats 2 & 4
  private bgWoodblock(t: number) {
    this.noise(this.musicGain!, t, t + 0.07, 0.2, 900, 3800);
    const ctx = this.ctx!;
    const o = ctx.createOscillator();
    o.type = 'sine'; o.frequency.value = 480;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.12, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.055);
    o.connect(g); g.connect(this.musicGain!);
    o.start(t); o.stop(t + 0.07);
  }

  stopBackgroundMusic() {
    this.bgScheduled = false;
    clearTimeout(this.bgTimeout); this.bgTimeout = null;
    if (this.ctx && this.musicGain) {
      const now = this.ctx.currentTime;
      this.musicGain.gain.setValueAtTime(this.musicGain.gain.value, now);
      this.musicGain.gain.linearRampToValueAtTime(0, now + 0.8);
      setTimeout(() => { if (this.musicGain) this.musicGain.gain.value = this.musicOn ? this.musicVolume : 0; }, 900);
    }
  }

  destroy() {
    this.stopBackgroundMusic();
    this.ctx?.close();
    this.ctx = null; this.sfxGain = null; this.musicGain = null;
  }
}
