import { describe, expect, it } from "vitest";
import type { ParityReport } from "../src/api/types";
import { parityReport, variantLabel } from "../src/views/parity";

const report = {
  model: "swift-f0",
  device: "Apple M5 Pro",
  threshold_f1: 0.98,
  parity: {
    "coreml-fp32-CPU_AND_GPU": { note_f1: { f1: 1, p: 1, r: 1, min_f1: 0.995, n_clips: 10 }, note_f1_mixes: { f1: 1, p: 1, r: 1, min_f1: 0.99, n_clips: 4 } },
    "coreml-fp16-ALL": { note_f1: { f1: 0.97, p: 0.97, r: 0.97, min_f1: 0.71, min_clip: "urmp/03", n_clips: 10 }, note_f1_mixes: { f1: 1, p: 1, r: 1, min_f1: 0.99, n_clips: 4 } },
    "ort-coreml-static": { note_f1: { f1: 0.9, p: 0.9, r: 0.9, min_f1: 0.8, n_clips: 10 } },
  },
} as unknown as ParityReport;

describe("conversion parity", () => {
  it("names formats in words", () => {
    expect(variantLabel("coreml-b1-fp32-CPU_AND_GPU")).toBe("Core ML batch 1 fp32 (GPU)");
    expect(variantLabel("small0/onnx-ort-cpu")).toBe("small0: ONNX Runtime (CPU)");
    expect(variantLabel("ort-coreml-static")).toBe("ONNX Runtime static (Core ML)");
    expect(variantLabel("tflite-litert-cpu")).toBe("TFLite LiteRT (CPU)");
    expect(variantLabel("onnx-b1-ort-coreml")).toBe("batch 1 ONNX Runtime (Core ML)");
  });

  it("is ready when any format meets the threshold, and says on which", () => {
    const { el, notReady } = parityReport(report);
    expect(notReady).toBe(false);
    expect(el.querySelector(".ready-on")?.textContent).toContain("Core ML fp32 (GPU)");
    expect(el.querySelector(".ready-on")?.textContent).not.toContain("fp16");
  });

  it("names the variant and the threshold on every row below the threshold", () => {
    const { el } = parityReport(report);
    const rows = [...el.querySelectorAll(".parity-below tbody tr")];
    expect(rows).toHaveLength(2);
    for (const tr of rows) {
      const cells = [...tr.querySelectorAll("td")];
      expect(cells[0].textContent?.trim(), "variant").not.toBe("");
      expect(cells[cells.length - 1].textContent).toContain("below 0.98");
    }
    expect(rows[0].querySelector("td")?.textContent).toContain("Core ML fp16 (all units)");
    // The full table still has every row filled in, too (cells are not shared between tables).
    for (const tr of el.querySelectorAll("table:not(.x) tbody tr")) expect(tr.querySelector("td")?.textContent?.trim()).not.toBe("");
  });

  it("is not ready when no format meets the threshold", () => {
    const bad = { ...report, parity: { "coreml-fp16-ALL": (report.parity as Record<string, unknown>)["coreml-fp16-ALL"] } } as unknown as ParityReport;
    expect(parityReport(bad).notReady).toBe(true);
  });
});
