import { describe, expect, it } from "vitest";
import { PianoRoll } from "../src/components/pianoroll";
import { t } from "../src/i18n";

describe("the piano roll", () => {
  it("shows a layer with more notes than a call can take as arguments", () => {
    // Math.max(...ends) throws RangeError at this size.
    const notes = Array.from({ length: 1_000_000 }, (_, i) => ({ pitch: 60 + (i % 12), start: i * 0.01, end: i * 0.01 + 0.5 }));
    const roll = new PianoRoll();
    document.body.append(roll);
    expect(() => { roll.data = [{ id: "m", label: "Model", colour: "bc-model-1", style: "line", notes }]; }).not.toThrow();
    // "Whole piece" measures the piece's length over every note.
    const whole = Array.from(roll.querySelectorAll("button")).find((b) => b.textContent === t("roll.whole"))!;
    expect(() => whole.click()).not.toThrow();
    roll.remove();
  });
});
