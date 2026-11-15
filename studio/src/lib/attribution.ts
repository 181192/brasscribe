// alphaTab 1.9 draws a small "♪ alphaTab.net" mark at the end of the first system of a score of more than 10 bars
// or more than 2 tracks, and asks that it stays visible: nothing of ours is drawn over it. The mark is right-aligned to
// the last bar of that system and rests above everything alphaTab placed over the top staff, at a height alphaTab does
// not report, so the zone kept clear takes in the whole band above that staff.
export interface Zone { x: number; y: number; w: number; h: number }

/** The mark's width in alphaTab's layout units at scale 1, with a margin. */
export const ATTRIBUTION_WIDTH = 78;

interface Bounds { x: number; y: number; w: number; h: number }
interface SystemBounds { visualBounds: Bounds; bars: { realBounds: Bounds; bars: { realBounds: Bounds }[] }[] }

/** Where the mark can be, in the units of alphaTab's bounds, or null when the score carries none. */
export function attributionZone(systems: SystemBounds[], masterBars: number, tracksShown: number, scale: number): Zone | null {
  if (masterBars <= 10 && tracksShown <= 2) return null;
  const system = systems[0];
  const last = system?.bars[system.bars.length - 1];
  if (!system || !last) return null;
  const top = system.visualBounds.y;
  const staffTop = last.bars[0]?.realBounds.y ?? top;
  const w = ATTRIBUTION_WIDTH * scale;
  return { x: last.realBounds.x + last.realBounds.w - w, y: top, w, h: Math.max(0, staffTop - top) };
}

export const overlaps = (a: Zone, b: Zone): boolean => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

/** The top a box of [box] size must take to clear [zone]: unchanged when it does not touch it, else just above it. */
export function clearOf(box: Zone, zone: Zone | null): number {
  return zone && overlaps(box, zone) ? zone.y - box.h - 2 : box.y;
}
