// Signal summaries for the audio inspector: waveform peaks, short-time
// spectra and frame energy. All work on mono Float32 samples.

export function mixdown(channels: Float32Array[]): Float32Array {
  if (channels.length === 1) return channels[0];
  const n = channels[0].length;
  const out = new Float32Array(n);
  for (const ch of channels) for (let i = 0; i < n; i++) out[i] += ch[i] / channels.length;
  return out;
}

/** Min/max pairs for `buckets` equal slices of [start, end). */
export function peaks(x: Float32Array, buckets: number, start = 0, end = x.length): Float32Array {
  const out = new Float32Array(buckets * 2);
  const span = (end - start) / buckets;
  for (let b = 0; b < buckets; b++) {
    const i0 = Math.floor(start + b * span);
    const i1 = Math.max(i0 + 1, Math.floor(start + (b + 1) * span));
    let lo = 0;
    let hi = 0;
    for (let i = i0; i < i1 && i < x.length; i++) {
      const v = x[i];
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
    out[2 * b] = lo;
    out[2 * b + 1] = hi;
  }
  return out;
}

/** In-place iterative radix-2 FFT. `re` and `im` have a power-of-two length. */
export function fft(re: Float64Array, im: Float64Array): void {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      [re[i], re[j]] = [re[j], re[i]];
      [im[i], im[j]] = [im[j], im[i]];
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len;
    const wr = Math.cos(ang);
    const wi = Math.sin(ang);
    for (let i = 0; i < n; i += len) {
      let cr = 1;
      let ci = 0;
      for (let k = 0; k < len / 2; k++) {
        const ar = re[i + k + len / 2] * cr - im[i + k + len / 2] * ci;
        const ai = re[i + k + len / 2] * ci + im[i + k + len / 2] * cr;
        re[i + k + len / 2] = re[i + k] - ar;
        im[i + k + len / 2] = im[i + k] - ai;
        re[i + k] += ar;
        im[i + k] += ai;
        const t = cr * wr - ci * wi;
        ci = cr * wi + ci * wr;
        cr = t;
      }
    }
  }
}

export interface Spectrogram {
  frames: number;
  bins: number;
  /** dB values, frame-major: data[f * bins + k]. */
  data: Float32Array;
  hop: number;
  size: number;
}

/** Magnitude spectrogram (Hann window) over samples [start, end), `frames` columns. */
export function spectrogram(x: Float32Array, frames: number, size = 2048, start = 0, end = x.length): Spectrogram {
  const bins = size / 2;
  const data = new Float32Array(frames * bins);
  const hop = Math.max(1, (end - start - size) / Math.max(1, frames - 1));
  const win = new Float64Array(size);
  for (let i = 0; i < size; i++) win[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / (size - 1));
  const re = new Float64Array(size);
  const im = new Float64Array(size);
  for (let f = 0; f < frames; f++) {
    const o = Math.floor(start + f * hop);
    for (let i = 0; i < size; i++) {
      re[i] = (x[o + i] ?? 0) * win[i];
      im[i] = 0;
    }
    fft(re, im);
    for (let k = 0; k < bins; k++) {
      const mag = Math.hypot(re[k], im[k]) / size;
      data[f * bins + k] = 20 * Math.log10(mag + 1e-10);
    }
  }
  return { frames, bins, data, hop, size };
}

/** RMS energy in dBFS for `frames` equal slices. */
export function energy(x: Float32Array, frames: number): Float32Array {
  const out = new Float32Array(frames);
  const span = x.length / frames;
  for (let f = 0; f < frames; f++) {
    const i0 = Math.floor(f * span);
    const i1 = Math.max(i0 + 1, Math.floor((f + 1) * span));
    let s = 0;
    // Stride keeps long files fast; energy is a smooth summary.
    const step = Math.max(1, Math.floor((i1 - i0) / 2048));
    let n = 0;
    for (let i = i0; i < i1; i += step) {
      s += x[i] * x[i];
      n++;
    }
    out[f] = 10 * Math.log10(s / Math.max(1, n) + 1e-12);
  }
  return out;
}
