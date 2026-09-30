// A cache of loads by key that keeps the most recently used values within a size budget.
// Values are kept as promises, so a load asked for twice runs once; a value's size is known only
// once it has loaded, and only loaded values are ever dropped.

interface Entry<V> {
  value: Promise<V>;
  size: number | null;
}

export class SizedLru<K, V> {
  private readonly entries = new Map<K, Entry<V>>();

  constructor(private readonly budget: number, private readonly sizeOf: (v: V) => number) {}

  /** The value for `key`, loading it with `load` when it is not cached. A failed load is not kept. */
  get(key: K, load: () => Promise<V>): Promise<V> {
    const hit = this.entries.get(key);
    if (hit) {
      // Most recently used last.
      this.entries.delete(key);
      this.entries.set(key, hit);
      return hit.value;
    }
    const entry: Entry<V> = { value: load(), size: null };
    this.entries.set(key, entry);
    entry.value.then((v) => {
      if (this.entries.get(key) !== entry) return;
      entry.size = this.sizeOf(v);
      this.evict(key);
    }, () => {
      if (this.entries.get(key) === entry) this.entries.delete(key);
    });
    return entry.value;
  }

  /** Total size of the loaded values held. */
  get size(): number {
    let n = 0;
    for (const e of this.entries.values()) n += e.size ?? 0;
    return n;
  }

  has(key: K): boolean {
    return this.entries.has(key);
  }

  clear(): void {
    this.entries.clear();
  }

  /** Drop the least recently used loaded values until the rest fit; `keep` (just loaded) stays. */
  private evict(keep: K): void {
    let total = this.size;
    for (const [k, e] of this.entries) {
      if (total <= this.budget) break;
      if (k === keep || e.size === null) continue;
      this.entries.delete(k);
      total -= e.size;
    }
  }
}
