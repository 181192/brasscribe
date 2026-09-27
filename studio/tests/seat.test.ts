import { describe, expect, it } from "vitest";
import { seatName, seatRows } from "../src/views/run";

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
});
