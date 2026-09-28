// Largest and smallest value of a list without spreading it into Math.max/min.
// Spreading passes every element as a call argument, and a long list (a full-band
// score has hundreds of thousands of MIDI events) overflows the call stack.

export function maxOf<T>(items: readonly T[], value: (item: T) => number, empty = -Infinity): number {
  let best = empty;
  for (const item of items) {
    const v = value(item);
    if (v > best) best = v;
  }
  return best;
}

export function minOf<T>(items: readonly T[], value: (item: T) => number, empty = Infinity): number {
  let best = empty;
  for (const item of items) {
    const v = value(item);
    if (v < best) best = v;
  }
  return best;
}
