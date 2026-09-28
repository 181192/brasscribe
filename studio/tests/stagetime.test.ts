import { describe, expect, it } from "vitest";
import { setLang } from "../src/i18n";
import { reduce, type RunView } from "../src/lib/events";
import { stageTime, stageTimeTip } from "../src/lib/stagetime";

describe("stage time", () => {
  it("shows only the time when the stage did not wait for the GPU", () => {
    setLang("en");
    expect(stageTime({ seconds: 2.1, queue_wait_s: 0.01, run_s: 2.09 })).toBe("2.1 s");
    expect(stageTime({ seconds: 2.1 })).toBe("2.1 s");
    expect(stageTimeTip({ seconds: 2.1, queue_wait_s: 0 })).toBeNull();
  });

  it("splits waited from ran when another job held the GPU", () => {
    setLang("en");
    const s = { seconds: 375.9, queue_wait_s: 373.8, run_s: 2.1 };
    expect(stageTime(s)).toBe("ran 2.1 s · waited 6 min 14 s");
    expect(stageTimeTip(s)).toContain("Waited 6 min 14 s");
    setLang("nb");
    expect(stageTime(s)).toBe("kjørte 2,1 s · ventet 6 min 14 s");
    setLang("en");
  });

  it("keeps the wait and run time from stage events", () => {
    const start: RunView = { id: "r", status: "running", stages: [], lastEventId: -1, log: [] };
    const v = reduce(start, { id: 0, run: "r", type: "stage", time: 1, stage: "beats", status: "ran", seconds: 10, queue_wait_s: 8, run_s: 2 });
    expect(v.stages[0]).toMatchObject({ seconds: 10, queue_wait_s: 8, run_s: 2 });
  });
});
