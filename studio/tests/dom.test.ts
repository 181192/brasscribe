import { afterEach, describe, expect, it } from "vitest";
import { clear, h, more, onPanelHidden, rebuild, tabs } from "../src/ui/dom";

describe("tabs", () => {
  it("tells what sits in a panel when another tab is chosen", () => {
    const players: Record<string, HTMLElement> = {};
    const hidden: string[] = [];
    const el = tabs("Views", ["score", "audio"].map((id) => ({ id, label: id, render: (p: HTMLElement) => {
      players[id] = h("div", {});
      p.append(players[id]);
    } })), "score");
    document.body.append(el);
    const off = onPanelHidden(players.score, () => hidden.push("score"));
    el.querySelector<HTMLButtonElement>("[data-id=audio]")!.click();
    expect(hidden).toEqual(["score"]);
    onPanelHidden(players.audio, () => hidden.push("audio"));
    el.querySelector<HTMLButtonElement>("[data-id=score]")!.click();
    el.querySelector<HTMLButtonElement>("[data-id=score]")!.click();
    expect(hidden).toEqual(["score", "audio"]);
    off();
    el.querySelector<HTMLButtonElement>("[data-id=audio]")!.click();
    expect(hidden).toEqual(["score", "audio"]);
  });

  it("does nothing for an element outside a tab panel", () => {
    expect(() => onPanelHidden(h("div", {}), () => undefined)()).not.toThrow();
  });
});

afterEach(() => document.body.replaceChildren());

describe("rebuilding part of a page", () => {
  const draw = (box: HTMLElement, label = "Run") => clear(box,
    more("Run details", h("p", {}, "id")),
    more("Files", h("p", {}, "a.txt")),
    h("button", { type: "button", "data-key": "run:cpu" }, label),
    h("button", { type: "button" }, "Compare"));

  it("keeps open disclosures open and gives focus back to the same control", () => {
    const box = h("div", {});
    document.body.append(box);
    draw(box);
    box.querySelectorAll("details")[1].open = true;
    box.querySelector<HTMLButtonElement>("[data-key='run:cpu']")!.focus();
    const before = document.activeElement;
    rebuild([box], () => draw(box, "Running…"));
    expect(Array.from(box.querySelectorAll("details")).map((d) => d.open)).toEqual([false, true]);
    expect(document.activeElement).not.toBe(before);
    expect((document.activeElement as HTMLElement).dataset.key).toBe("run:cpu");
  });

  it("matches controls without a key by their text", () => {
    const box = h("div", {});
    document.body.append(box);
    draw(box);
    box.querySelectorAll("button")[1].focus();
    rebuild([box], () => draw(box));
    expect(document.activeElement?.textContent).toBe("Compare");
  });

  it("leaves focus alone when it was elsewhere", () => {
    const box = h("div", {});
    const outside = h("input", {});
    document.body.append(box, outside);
    draw(box);
    outside.focus();
    rebuild([box], () => draw(box));
    expect(document.activeElement).toBe(outside);
  });
});
