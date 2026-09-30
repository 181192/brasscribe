import { afterEach, describe, expect, it } from "vitest";
import { clear, h, more, rebuild } from "../src/ui/dom";

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
