import { describe, expect, it } from "vitest";
import { madeLineup, seatName, seatRows } from "../src/views/run";

describe("seat options in the run summary", () => {
  it("names seats as their band parts", () => {
    expect(seatName("1st-baritone")).toBe("1st Baritone");
    expect(seatName("eb-bass")).toBe("E♭ Bass");
    expect(seatName("solo-horn")).toBe("Solo Horn");
  });
  it("shows only the options a job has", () => {
    expect(seatRows(undefined)).toEqual([]);
    expect(seatRows({ lead: "lineup", seat: null })).toEqual([]);
    const rows = seatRows({ seat: "euphonium", reads: "bass", lead: "seat" }).map((e) => e.textContent);
    expect(rows).toEqual(["Written for", "Euphonium", "Reads", "Bass clef, as it sounds", "Tune on", "The seat's part"]);
  });
  it("names an empty part in both languages", async () => {
    const { messages: STRINGS } = await import("../src/i18n");
    expect(STRINGS.en["score.source.empty"]).toBe("Nothing to play in this arrangement");
    expect(STRINGS.nb["score.source.empty"]).toBe("Tom i dette arrangementet");
  });
  it("names the band the score is made for, not the one asked for", () => {
    expect(madeLineup("brass-band", { lineup: "full" })).toBe("minimal");
    expect(madeLineup("pop-rock", undefined)).toBe("minimal");
    expect(madeLineup("brass-band", { lineup: "quartet" })).toBe("quartet");
    expect(madeLineup("orchestra-with-soloist", { lineup: "full" })).toBe("full");
    expect(madeLineup("orchestra-with-soloist", undefined)).toBe("full");
    expect(madeLineup("solo", { seat: "euphonium" })).toBe("one");
    expect(madeLineup("solo", {})).toBe("minimal");
  });
});
