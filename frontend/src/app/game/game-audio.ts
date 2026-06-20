export class GameAudio {
  private ctx: AudioContext | null = null;
  private sfxGain: GainNode | null = null;
  private musicGain: GainNode | null = null;
  private bgScheduled = false;
  private bgTimeout: any = null;
  private bgNextTime = 0;
  private bgBeat = 0;

  sfxVolume = 0.55;
  musicVolume = 0.13;

  private ensure(): AudioContext {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      const master = this.ctx.createGain();
      master.gain.value = 1.0;
      master.connect(this.ctx.destination);
      this.sfxGain = this.ctx.createGain();
      this.sfxGain.gain.value = this.sfxVolume;
      this.sfxGain.connect(master);
      this.musicGain = this.ctx.createGain();
      this.musicGain.gain.value = this.musicVolume;
      this.musicGain.connect(master);
    }
    if (this.ctx.state === 'suspended') this.ctx.resume();
    return this.ctx;
  }

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
    o.start(t0);
    o.stop(t1 + 0.05);
  }

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
    flt.connect(g);
    g.connect(out);
    src.start(t0);
    src.stop(t1 + 0.05);
  }

  // Card drag/reorder
  playCardReorder() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.noise(this.sfxGain!, t, t + 0.05, 0.5, 1500, 6000);
  }

  // Treasure chest collected
  playTreasurePickup() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    [523, 659, 784, 1047].forEach((f, i) => {
      this.tone(this.sfxGain!, f, 'sine', t + i * 0.07, t + i * 0.07 + 0.18, 0.4);
    });
  }

  // Non-final checkpoint
  playCheckpoint() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.tone(this.sfxGain!, 880, 'sine', t, t + 0.18, 0.45);
    this.tone(this.sfxGain!, 1174, 'sine', t + 0.14, t + 0.38, 0.35);
  }

  // Final checkpoint / win
  playFinalCheckpoint() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    [523, 659, 784, 1047, 1319, 1568].forEach((f, i) => {
      this.tone(this.sfxGain!, f, 'triangle', t + i * 0.09, t + i * 0.09 + 0.45, 0.5);
    });
    this.tone(this.sfxGain!, 523, 'sine', t + 0.8, t + 2.0, 0.3);
  }

  // Cannon hit received
  playHit() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.tone(this.sfxGain!, 120, 'sine', t, t + 0.35, 0.6, 40);
    this.noise(this.sfxGain!, t, t + 0.12, 0.45, 150, 900);
  }

  // Burn damage tick
  playBurnDamage() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.noise(this.sfxGain!, t, t + 0.18, 0.3, 600, 3000);
    this.tone(this.sfxGain!, 200, 'sawtooth', t, t + 0.12, 0.2, 120);
  }

  // Ship sinks
  playSink() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.tone(this.sfxGain!, 220, 'sawtooth', t, t + 1.2, 0.45, 55);
    for (let i = 0; i < 6; i++) {
      this.noise(this.sfxGain!, t + i * 0.17, t + i * 0.17 + 0.12, 0.25, 250, 1800);
    }
  }

  // Void / octopus eaten
  playOctopus() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.tone(this.sfxGain!, 65, 'sawtooth', t, t + 0.9, 0.55, 28);
    this.noise(this.sfxGain!, t, t + 0.6, 0.4, 80, 500);
    this.tone(this.sfxGain!, 180, 'sine', t + 0.1, t + 0.5, 0.25, 80);
  }

  // Collision with rock/wall
  playRockHit() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.tone(this.sfxGain!, 190, 'sine', t, t + 0.18, 0.55, 60);
    this.noise(this.sfxGain!, t, t + 0.1, 0.5, 300, 2500);
  }

  // Repair (carpenter/powerdown)
  playRepair() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.tone(this.sfxGain!, 660, 'square', t, t + 0.07, 0.3);
    this.tone(this.sfxGain!, 880, 'square', t + 0.1, t + 0.18, 0.25);
    this.tone(this.sfxGain!, 1100, 'sine', t + 0.2, t + 0.35, 0.2);
  }

  // New round begins (select phase after animation)
  playRoundStart() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.tone(this.sfxGain!, 110, 'sine', t, t + 2.0, 0.5);
    this.tone(this.sfxGain!, 220, 'sine', t, t + 1.5, 0.25);
    this.tone(this.sfxGain!, 330, 'sine', t + 0.04, t + 1.2, 0.15);
  }

  // A player submits cards / countdown begins
  playSailsSet() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.noise(this.sfxGain!, t, t + 0.35, 0.3, 700, 4000);
    this.tone(this.sfxGain!, 698, 'sine', t + 0.08, t + 0.45, 0.35);
  }

  // Animation phase kicks off
  playAnimationStart() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.noise(this.sfxGain!, t, t + 0.12, 0.55, 60, 280);
    this.tone(this.sfxGain!, 440, 'sine', t + 0.05, t + 0.28, 0.25);
  }

  // Shield absorbs a hit
  playShieldAbsorb() {
    const ctx = this.ensure(); const t = ctx.currentTime;
    this.tone(this.sfxGain!, 880, 'sine', t, t + 0.22, 0.35);
    this.noise(this.sfxGain!, t, t + 0.15, 0.2, 2000, 6000);
  }

  // ── Background music ─────────────────────────────────────────────────────────
  // D minor pentatonic: D F G A C
  // Phrase A then phrase B, looping forever
  private static readonly MELODY: [number, number][] = [
    // phrase A
    [293.66, 1.0], [391.99, 0.5], [440.00, 0.5], [349.23, 0.75], [293.66, 0.25],
    [523.25, 1.0], [440.00, 0.5], [391.99, 1.5],
    // phrase B
    [349.23, 1.0], [440.00, 0.5], [523.25, 0.5], [587.33, 0.75], [440.00, 0.25],
    [391.99, 1.0], [349.23, 0.5], [293.66, 2.0],
  ];
  private static readonly BASS: [number, number][] = [
    [146.83, 2.0], [195.99, 2.0], [174.61, 2.0], [195.99, 2.0],
    [174.61, 2.0], [195.99, 2.0], [130.81, 2.0], [195.99, 2.0],
  ];
  private readonly BPM = 58;

  startBackgroundMusic() {
    const ctx = this.ensure();
    if (this.bgScheduled) return;
    this.bgScheduled = true;
    this.bgNextTime = ctx.currentTime + 0.2;
    this.bgBeat = 0;
    this.scheduleBGM();
  }

  private scheduleBGM() {
    if (!this.bgScheduled || !this.ctx || !this.musicGain) return;
    const ctx = this.ctx;
    const beat = 60 / this.BPM;
    const ahead = 0.4;
    const mel = GameAudio.MELODY;
    const bas = GameAudio.BASS;

    while (this.bgNextTime < ctx.currentTime + ahead) {
      const mi = this.bgBeat % mel.length;
      const bi = this.bgBeat % bas.length;
      const [mf, md] = mel[mi];
      const [bf, bd] = bas[bi];
      const dur = md * beat;
      const bdur = bd * beat;

      // melody — soft sine with a gentle tremolo via a second slight detune
      this.tone(this.musicGain!, mf, 'sine', this.bgNextTime, this.bgNextTime + dur * 0.88, 0.32);
      this.tone(this.musicGain!, mf * 1.003, 'sine', this.bgNextTime, this.bgNextTime + dur * 0.88, 0.08);

      // bass only on phrase downbeats
      if (mi === 0 || mi === 8) {
        this.tone(this.musicGain!, bf, 'sine', this.bgNextTime, this.bgNextTime + bdur * 0.75, 0.22);
      }

      this.bgNextTime += dur;
      this.bgBeat++;
    }

    this.bgTimeout = setTimeout(() => this.scheduleBGM(), 150);
  }

  stopBackgroundMusic() {
    this.bgScheduled = false;
    clearTimeout(this.bgTimeout);
    this.bgTimeout = null;
    if (this.ctx && this.musicGain) {
      const now = this.ctx.currentTime;
      this.musicGain.gain.setValueAtTime(this.musicGain.gain.value, now);
      this.musicGain.gain.linearRampToValueAtTime(0, now + 0.8);
      setTimeout(() => { if (this.musicGain) this.musicGain.gain.value = this.musicVolume; }, 900);
    }
  }

  destroy() {
    this.stopBackgroundMusic();
    this.ctx?.close();
    this.ctx = null;
    this.sfxGain = null;
    this.musicGain = null;
  }
}
