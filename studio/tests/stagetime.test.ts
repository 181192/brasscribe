import { describe, expect, it } from "vitest";
import { setLang } from "../src/i18n";
import { StageGraph } from "../src/components/stagegraph";
import { reduce, type RunView } from "../src/lib/events";
import { stageTime, stageTimeTip, waitNote, WAIT_NOTE_ID } from "../src/lib/stagetime";

describe("stage time", () => {
  it("shows only the time when the stage did not wait for the GPU", () => {
    setLang("en");
    expect(stageTime({ seconds: 2.1, queue_wait_s: 0.01, run_s: 2.09 })).toBe("2.1 s");
    expect(stageTime({ seconds: 2.1 })).toBe("2.1 s");
    expect(stageTimeTip({ seconds: 2.1, queue_wait_s: 0 })).toBeNull();
    expect(waitNote({ seconds: 2.1, queue_wait_s: 0 })).toBeNull();
  });

  it("splits waited from ran, in the order they happened, when another job held the GPU", () => {
    setLang("en");
    const s = { seconds: 375.9, queue_wait_s: 373.8, run_s: 2.1 };
    expect(stageTime(s)).toBe("waited 6 min 14 s · ran 2.1 s");
    expect(stageTimeTip(s)).toContain("Waited 6 min 14 s");
    setLang("nb");
    expect(stageTime(s)).toBe("ventet 6 min 14 s · kjørte 2,1 s");
    expect(waitNote(s)!.textContent).toBe("Ventet 6 min 14 s på at en annen jobb skulle slippe GPU-en, og kjørte så 2,1 s.");
    setLang("en");
  });

  it("explains a wait in the stage panel, which the selected node is described by, not in a hover title", () => {
    setLang("en");
    const view: RunView = {
      id: "r", status: "succeeded", lastEventId: 3, log: [],
      stages: [
        { name: "transcribe.solo.muscriptor", kind: "transcribe", status: "ran", cacheHit: false, seconds: 375.9, queue_wait_s: 373.8, run_s: 2.1 },
        { name: "beats", kind: "beats", status: "ran", cacheHit: false, seconds: 1.2 },
      ],
    };
    const graph = new StageGraph();
    document.body.append(graph);
    graph.update(view);
    const node = (name: string) => graph.querySelector<HTMLButtonElement>(`[data-stage="${name}"]`)!;
    const waited = "transcribe.solo.muscriptor";
    expect(node(waited).hasAttribute("title")).toBe(false);
    expect(node(waited).hasAttribute("aria-describedby")).toBe(false);
    expect(node(waited).textContent).toContain("waited 6 min 14 s · ran 2.1 s");

    graph.select(waited);
    const panel = waitNote(view.stages[0])!;
    document.body.append(panel);
    expect(node(waited).getAttribute("aria-describedby")).toBe(WAIT_NOTE_ID);
    expect(document.getElementById(WAIT_NOTE_ID)!.textContent).toBe("Waited 6 min 14 s for another job to free the GPU, then ran 2.1 s.");

    graph.select("beats"); // no wait: nothing to describe
    expect(node("beats").hasAttribute("aria-describedby")).toBe(false);
    graph.remove();
    panel.remove();
  });

  it("keeps the wait and run time from stage events", () => {
    const start: RunView = { id: "r", status: "running", stages: [], lastEventId: -1, log: [] };
    const v = reduce(start, { id: 0, run: "r", type: "stage", time: 1, stage: "beats", status: "ran", seconds: 10, queue_wait_s: 8, run_s: 2 });
    expect(v.stages[0]).toMatchObject({ seconds: 10, queue_wait_s: 8, run_s: 2 });
  });
});
