// Canvas plumbing shared by the inspector plots: HiDPI sizing, redraw on
// resize, and a text alternative (role="img" with a label).
import { h } from "../ui/dom";

export interface Plot {
  box: HTMLElement;
  canvas: HTMLCanvasElement;
  /** Width and height in CSS pixels. */
  size(): { w: number; h: number };
  redraw(): void;
  setLabel(label: string): void;
}

export function plot(label: string, height: number, draw: (ctx: CanvasRenderingContext2D, w: number, h: number) => void): Plot {
  const canvas = h("canvas", { role: "img", "aria-label": label, height });
  canvas.style.height = `${height}px`;
  const box = h("div", { class: "canvas-box" }, canvas);
  let w = 0;
  const redraw = () => {
    const rect = canvas.getBoundingClientRect();
    w = Math.max(100, Math.round(rect.width || box.clientWidth || 800));
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, height);
    draw(ctx, w, height);
  };
  let pending = 0;
  const schedule = () => {
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(redraw);
  };
  new ResizeObserver(schedule).observe(box);
  return { box, canvas, size: () => ({ w, h: height }), redraw: schedule, setLabel: (l) => canvas.setAttribute("aria-label", l) };
}

/** Diagonal hatching as a fill pattern, so a colour is repeated by texture. */
export function hatch(ctx: CanvasRenderingContext2D, colour: string, spacing = 5): CanvasPattern | string {
  const c = document.createElement("canvas");
  c.width = c.height = spacing * 2;
  const g = c.getContext("2d");
  if (!g) return colour;
  g.strokeStyle = colour;
  g.lineWidth = 1.5;
  g.beginPath();
  g.moveTo(0, spacing * 2);
  g.lineTo(spacing * 2, 0);
  g.stroke();
  return ctx.createPattern(c, "repeat") ?? colour;
}

export function timeAxis(ctx: CanvasRenderingContext2D, w: number, y: number, t0: number, t1: number, colour: string): void {
  const span = t1 - t0;
  const steps = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
  const step = steps.find((s) => (w / span) * s > 70) ?? 600;
  ctx.fillStyle = colour;
  ctx.strokeStyle = colour;
  ctx.font = "11px system-ui, sans-serif";
  ctx.textBaseline = "top";
  for (let t = Math.ceil(t0 / step) * step; t <= t1; t += step) {
    const x = ((t - t0) / span) * w;
    ctx.beginPath();
    ctx.moveTo(x + 0.5, y);
    ctx.lineTo(x + 0.5, y + 4);
    ctx.stroke();
    const m = Math.floor(t / 60);
    const s = t - m * 60;
    ctx.fillText(`${m}:${s.toFixed(step < 1 ? 1 : 0).padStart(step < 1 ? 4 : 2, "0")}`, x + 2, y + 5);
  }
}
