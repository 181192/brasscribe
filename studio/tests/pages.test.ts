import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, assumeEngineInterface } from "../src/api/client";
import type { Job, ProfileInfo } from "../src/api/types";
import { messages, setLang } from "../src/i18n";
import { looksLikePage, MAX_PAGES, MAX_PAGE_BYTES, moved, pageFormat, pagesProblem, profilesFor, readFailure, readsPages } from "../src/lib/pages";
import { errorNotice, refusalWords } from "../src/ui/dom";
import { doubtfulBars, readRows } from "../src/views/run";
import { runsView } from "../src/views/runs";

const here = dirname(fileURLToPath(import.meta.url));
const engine = (name: string) => readFileSync(join(here, "..", "..", "engine", "src", "scribe_engine", name), "utf8");
const answers = JSON.parse(readFileSync(join(here, "..", "e2e", "fixtures", "api", "responses.json"), "utf8"));
const profiles = answers["/v1/profiles"].body as ProfileInfo[];

const PNG = Uint8Array.of(0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52, 1, 2, 3);
const bytes = (s: string) => Uint8Array.from(s, (c) => c.charCodeAt(0));
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => {
  vi.unstubAllGlobals();
  setLang("en");
  document.body.replaceChildren();
});
beforeEach(() => assumeEngineInterface("match"));

describe("pages", () => {
  it("offers a profile for what it reads; one that does not say listens", () => {
    expect(profilesFor(profiles, "pages").map((p) => p.name)).toEqual(["sheet", "sheet-tab"]);
    expect(profilesFor(profiles, "audio").map((p) => p.name)).not.toContain("sheet");
    const silent = { ...profiles[0], input: undefined } as unknown as ProfileInfo;
    expect(profilesFor([silent], "audio")).toEqual([silent]);
    expect(profilesFor([silent], "pages")).toEqual([]);
  });

  it("moves a page one place, and leaves the order alone at either end", () => {
    expect(moved(["a", "b", "c"], 2, -1)).toEqual(["a", "c", "b"]);
    expect(moved(["a", "b", "c"], 0, 1)).toEqual(["b", "a", "c"]);
    expect(moved(["a", "b", "c"], 0, -1)).toEqual(["a", "b", "c"]);
    expect(moved(["a", "b", "c"], 2, 1)).toEqual(["a", "b", "c"]);
  });

  it("has the engine's limits, and says before sending what they rule out", () => {
    expect(Number(/^MAX_PAGES = (\d+)/m.exec(engine("pages.py"))?.[1])).toBe(MAX_PAGES);
    expect(engine("pages.py")).toContain("MAX_PAGE_BYTES = 50 * 1024 * 1024");
    expect(MAX_PAGE_BYTES).toBe(50 * 1024 * 1024);
    const page = { size: 1000 };
    expect(pagesProblem([])).toBe("none");
    expect(pagesProblem(Array(MAX_PAGES).fill(page))).toBeNull();
    expect(pagesProblem(Array(MAX_PAGES + 1).fill(page))).toBe("too_many");
    expect(pagesProblem([page, { size: MAX_PAGE_BYTES + 1 }])).toBe("too_large");
  });

  it("knows a picture or a PDF from a recording by its type or its name", () => {
    for (const f of [{ name: "march.png", type: "image/png" }, { name: "IMG_0001.HEIC", type: "" }, { name: "parts.PDF" }, { name: "scan", type: "application/pdf" }]) {
      expect(looksLikePage(f), f.name).toBe(true);
    }
    for (const f of [{ name: "take.wav", type: "audio/wav" }, { name: "concert.mp4", type: "video/mp4" }, { name: "take" }]) expect(looksLikePage(f), f.name).toBe(false);
  });

  it("tells a job's input by its first bytes, as the engine does", () => {
    expect(pageFormat(PNG)).toBe("image/png");
    expect(pageFormat(Uint8Array.of(0xff, 0xd8, 0xff, 0xe0))).toBe("image/jpeg");
    expect(pageFormat(bytes("RIFF\0\0\0\0WEBPVP8 "))).toBe("image/webp");
    expect(pageFormat(bytes("%PDF-1.7"))).toBe("application/pdf");
    expect(pageFormat(bytes("PK\x03\x04page-001.png"))).toBe("application/zip");
    expect(pageFormat(bytes("RIFF\0\0\0\0WAVEfmt "))).toBeNull();
    expect(pageFormat(new Uint8Array(0))).toBeNull();
  });

  it("knows a run that read pages by its profile, and by its first stage once the profile is no longer listed", () => {
    const jobs = answers["/v1/jobs"].body as Job[];
    expect(jobs.filter((j) => readsPages(j, profiles)).map((j) => j.id).sort()).toEqual(["old-hundredth-sheet", "old-hundredth-unread"]);
    const withoutReader = profilesFor(profiles, "audio");
    expect(jobs.filter((j) => readsPages(j, withoutReader)).map((j) => j.id).sort()).toEqual(["old-hundredth-sheet", "old-hundredth-unread"]);
  });

  it("has words in both languages for every way the engine says pages could not be read", () => {
    const sheet = engine("sheet.py");
    const said = [...sheet.matchAll(/^(?:NO_MUSIC|NOT_READ|ONLY_TAB) = "([^"]+)"|^ {4}"\w+": f?"([^"]+)",$/gm)].map((m) => (m[1] ?? m[2]).replace("{pages.MAX_PAGES}", String(MAX_PAGES)));
    expect(said).toHaveLength(6);
    const names = said.map((words) => readFailure(`read: StageFailed: read: ${words}`));
    expect(new Set(names).size).toBe(6);
    for (const name of names) {
      expect(name, "a failure Studio has no words for").not.toBeNull();
      for (const l of ["en", "nb"] as const) expect(messages[l]).toHaveProperty([`run.unread.${name}`]);
    }
    expect(readFailure("read: StageFailed: read: no notes were found on the page\nTraceback (most recent call last):\n  File")).toBe("no_music");
    expect(readFailure("beats: ValueError: the beat grid has no downbeat in the first 8 bars")).toBeNull();
  });

  it("has words in both languages for every refusal the engine names", () => {
    const codes = [...(engine("pages.py") + engine("sheet.py")).matchAll(/^(?:NOT_A_PAGE|WRONG_INPUT|PAGE_TOO_LARGE|READER_MISSING) = "(\w+)"$/gm)].map((m) => m[1]);
    expect(codes.sort()).toEqual(["not_a_page", "page_too_large", "reader_missing", "wrong_input"]);
    for (const code of codes) {
      for (const l of ["en", "nb"] as const) expect(messages[l]).toHaveProperty([`refusal.${code}`]);
    }
  });

  it("says a named refusal in Studio's words, with the engine's own under Details; others as before", () => {
    const missing = new ApiError(503, "this computer has no reader of printed music installed: install it in Bandroom", "reader_missing");
    expect(refusalWords(missing)).toMatch(/Bandroom, under Settings, Sheet music from pictures/);
    const notice = errorNotice(missing);
    expect(notice.querySelector(".notice-title")?.textContent).toBe("Brasscribe on this computer turned this down.");
    expect(notice.querySelector("details")?.textContent).toContain("no reader of printed music installed");
    setLang("nb");
    expect(refusalWords(new ApiError(415, "IMG_0001.HEIC is a HEIC or AVIF picture", "not_a_page"))).toMatch(/HEIC-bilde fra en iPhone/);
    expect(refusalWords(new ApiError(422, "unknown profile", "something_new"))).toBeNull();
    expect(refusalWords(new ApiError(500, "boom"))).toBeNull();
  });

  it("lists the bars in doubt with their staff only when the page has more than one", () => {
    expect(doubtfulBars({ staves: 1, bars: 12, notes: 32, doubtful_bars: [{ staff: 1, bar: 6 }, { staff: 1, bar: 9 }] })).toBe("6, 9");
    expect(doubtfulBars({ staves: 2, bars: 12, notes: 64, doubtful_bars: [{ staff: 1, bar: 6 }, { staff: 2, bar: 7 }] })).toBe("6 (staff 1), 7 (staff 2)");
    const text = (rows: HTMLElement[]) => rows.map((r) => r.textContent).join("|");
    expect(text(readRows({ staves: 1, bars: 12, notes: 32, doubtful_bars: [] }))).toBe("Read from|Pages (pictures or a PDF)|Staves|1|Bars|12|Notes|32|Bars in doubt|None");
    expect(text(readRows(null))).toBe("Read from|Pages (pictures or a PDF)");
  });
});

describe("the client, for pages", () => {
  it("sends the pages in order with the job's options, and leaves out what is not set", async () => {
    let sent: { url: string; init: RequestInit } | undefined;
    vi.stubGlobal("fetch", (url: string, init: RequestInit) => {
      sent = { url, init };
      return Promise.resolve(json({ id: "r1" }, 202));
    });
    const page = (name: string) => new File([PNG], name, { type: "image/png" });
    const job = await api.createJobFromPages([page("b.png"), page("a.png")], { profile: "sheet-tab", title: null, render_audio: false, instrument: "ukulele", capo: 0 });
    expect(job.id).toBe("r1");
    expect(sent?.url).toBe("/v1/jobs/pages");
    expect(sent?.init.method).toBe("POST");
    const form = sent?.init.body as FormData;
    expect((form.getAll("files") as File[]).map((f) => f.name)).toEqual(["b.png", "a.png"]);
    expect([...form.keys()].filter((k) => k !== "files").sort()).toEqual(["capo", "instrument", "profile", "render_audio"]);
    expect([form.get("profile"), form.get("render_audio"), form.get("instrument"), form.get("capo")]).toEqual(["sheet-tab", "false", "ukulele", "0"]);
  });

  it("keeps the code the engine names a refusal by", async () => {
    vi.stubGlobal("fetch", () => Promise.resolve(json(answers["POST /v1/jobs/pages"].body, 415)));
    const e = await api.createJobFromPages([], { profile: "sheet" }).catch((x) => x);
    expect(e).toBeInstanceOf(ApiError);
    expect([(e as ApiError).status, (e as ApiError).code]).toEqual([415, "not_a_page"]);
    expect((e as ApiError).message).toContain("IMG_0001.HEIC");
    vi.stubGlobal("fetch", () => Promise.resolve(json({ detail: "unknown profile nope" }, 422)));
    expect(((await api.createJobFromPages([], { profile: "nope" }).catch((x) => x)) as ApiError).code).toBeUndefined();
  });

  it("fetches a picture whole to show it, and of a PDF or an archive only enough to know what it is", async () => {
    /** A body in two pieces, which counts how many were asked for and whether the rest was let go. */
    const answer = (first: Uint8Array, rest: Uint8Array) => {
      const seen = { pulled: 0, cancelled: false };
      const pieces = [first, rest];
      const body = new ReadableStream<Uint8Array>({
        pull(c) {
          const piece = pieces[seen.pulled++];
          if (piece) c.enqueue(piece);
          else c.close();
        },
        cancel() {
          seen.cancelled = true;
        },
      }, { highWaterMark: 0 });
      vi.stubGlobal("fetch", () => Promise.resolve({ ok: true, status: 200, body } as unknown as Response));
      return seen;
    };
    answer(PNG.subarray(0, 5), PNG.subarray(5));
    const picture = await api.pagesInput("r1");
    expect(picture.kind).toBe("picture");
    if (picture.kind === "picture") expect([picture.picture.type, picture.picture.size]).toEqual(["image/png", PNG.length]);
    for (const [head, kind] of [[bytes("%PDF-1.7\n1 0 obj"), "pdf"], [bytes("PK\x03\x04page-001.png"), "archive"], [bytes("RIFF\0\0\0\0WAVEfmt "), "other"]] as const) {
      const seen = answer(head, new Uint8Array(1000));
      expect((await api.pagesInput("r1")).kind).toBe(kind);
      expect(seen).toEqual({ pulled: 1, cancelled: true });
    }
    vi.stubGlobal("fetch", () => Promise.resolve(json({ detail: "input audio no longer exists" }, 404)));
    expect(((await api.pagesInput("r1").catch((x) => x)) as ApiError).status).toBe(404);
  });
});

describe("the new-run form", () => {
  /** The runs view with an engine that lists `listed` profiles; `post` answers what the form sends. */
  async function form(listed: ProfileInfo[], post: (url: string, init: RequestInit) => Response = () => json({ id: "r1" }, 202)) {
    const sent: { url: string; init: RequestInit }[] = [];
    vi.stubGlobal("fetch", (url: string, init: RequestInit = {}) => {
      if (init.method === "POST") {
        sent.push({ url, init });
        return Promise.resolve(post(url, init));
      }
      return Promise.resolve(json(url === "/v1/profiles" ? listed : []));
    });
    const root = document.createElement("div");
    document.body.append(root);
    runsView(root);
    await vi.waitFor(() => expect(root.querySelector("form")).not.toBeNull());
    const el = root.querySelector("form")!;
    const choose = (kind: string) => {
      const radio = el.querySelector<HTMLInputElement>(`input[name=source-kind][value=${kind}]`)!;
      radio.checked = true;
      radio.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const pick = (input: string, ...names: string[]) => {
      const field = el.querySelector<HTMLInputElement>(input)!;
      Object.defineProperty(field, "files", { configurable: true, value: names.map((n) => new File([PNG], n, { type: /\.png$/.test(n) ? "image/png" : "" })) });
      field.dispatchEvent(new Event("change", { bubbles: true }));
    };
    const offered = () => Array.from(el.querySelectorAll<HTMLOptionElement>("#run-profile option")).map((o) => o.value);
    const listedPages = () => Array.from(el.querySelectorAll(".page-list .page-name")).map((x) => x.textContent);
    const press = (name: string) => Array.from(el.querySelectorAll<HTMLButtonElement>(".page-list button")).find((b) => b.getAttribute("aria-label") === name)!.click();
    const submit = async () => {
      el.dispatchEvent(new Event("submit", { cancelable: true }));
      await vi.waitFor(() => expect(sent.length || el.querySelector("#run-error")!.childElementCount).toBeTruthy());
      await vi.waitFor(() => expect(location.hash === "#/runs/r1" || el.querySelector("#run-error")!.childElementCount).toBeTruthy());
    };
    return { el, sent, choose, pick, offered, listedPages, press, submit };
  }

  beforeEach(() => {
    location.hash = "";
  });

  it("offers a recording the profiles that listen, and pages the ones that read", async () => {
    const f = await form(profiles);
    expect(f.offered()).toEqual(profilesFor(profiles, "audio").map((p) => p.name));
    expect(f.el.querySelector<HTMLSelectElement>("#run-profile")!.value).toBe("orchestra-with-soloist");
    expect(f.el.querySelector<HTMLElement>(".pages")!.hidden).toBe(true);
    f.choose("pages");
    expect(f.offered()).toEqual(["sheet", "sheet-tab"]);
    expect(f.el.querySelector("#run-profile-desc")!.textContent).toMatch(/Nothing is arranged/);
    expect(f.el.querySelector<HTMLElement>(".pages")!.hidden).toBe(false);
    // Nothing listens to a page: the large models are not offered for it.
    expect(f.el.querySelector<HTMLElement>("#run-heavy")!.closest<HTMLElement>("div")!.hidden).toBe(true);
    f.choose("source");
    expect(f.offered()).not.toContain("sheet");
    expect(f.el.querySelector<HTMLElement>("#run-heavy")!.closest<HTMLElement>("div")!.hidden).toBe(false);
  });

  it("keeps the profile chosen while what is read stays the same", async () => {
    const f = await form(profiles);
    f.choose("pages");
    const profile = f.el.querySelector<HTMLSelectElement>("#run-profile")!;
    profile.value = "sheet-tab";
    profile.dispatchEvent(new Event("change", { bubbles: true }));
    f.pick("#run-pages", "1.png");
    expect(profile.value).toBe("sheet-tab");
  });

  it("does not offer pages where the engine lists no profile that reads them, and says where the reader is installed", async () => {
    const f = await form(profilesFor(profiles, "audio"));
    expect(f.el.querySelector("input[name=source-kind][value=pages]")).toBeNull();
    expect(f.el.querySelector("fieldset.source")!.textContent).toMatch(/installed in Bandroom, under Settings, Sheet music from pictures/);
    // A picture chosen as a recording is not uploaded: the same line says why.
    f.pick("#run-file", "march.png");
    await f.submit();
    expect(f.sent).toEqual([]);
    expect(f.el.querySelector("#run-error")!.textContent).toMatch(/needs the reader/);
  });

  it("keeps the pages in the order chosen, adds to them, moves and removes them, and sends them in that order", async () => {
    const f = await form(profiles);
    f.choose("pages");
    f.pick("#run-pages", "2.png", "1.png");
    f.pick("#run-pages", "3.pdf");
    expect(f.listedPages()).toEqual(["2.png", "1.png", "3.pdf"]);
    const buttons = () => Array.from(f.el.querySelectorAll<HTMLButtonElement>(".page-list li:first-child button")).map((b) => [b.textContent, b.disabled]);
    expect(buttons()).toEqual([["Move up", true], ["Move down", false], ["Remove", false]]);
    f.press("Move up: 1.png");
    expect(f.listedPages()).toEqual(["1.png", "2.png", "3.pdf"]);
    // Focus stays with the page that moved: at the top it cannot go further up, so on its other button.
    expect(document.activeElement?.getAttribute("aria-label")).toBe("Move down: 1.png");
    f.press("Remove: 3.pdf");
    expect(f.listedPages()).toEqual(["1.png", "2.png"]);
    expect(document.activeElement?.getAttribute("aria-label")).toBe("Remove: 2.png");
    (f.el.querySelector("#run-title") as HTMLInputElement).value = "Old Hundredth";
    await f.submit();
    expect(f.sent.map((s) => s.url)).toEqual(["/v1/jobs/pages"]);
    const body = f.sent[0].init.body as FormData;
    expect((body.getAll("files") as File[]).map((x) => x.name)).toEqual(["1.png", "2.png"]);
    expect([body.get("profile"), body.get("title"), body.get("render_audio"), body.get("allow_heavy")]).toEqual(["sheet", "Old Hundredth", "true", null]);
    expect(location.hash).toBe("#/runs/r1");
  });

  it("asks for pages before sending none, and for fewer when there are too many", async () => {
    const f = await form(profiles);
    f.choose("pages");
    await f.submit();
    expect(f.el.querySelector("#run-error")!.textContent).toBe("Choose the pages first.");
    f.pick("#run-pages", ...Array.from({ length: MAX_PAGES + 1 }, (_, i) => `${i}.png`));
    await f.submit();
    expect(f.el.querySelector("#run-error")!.textContent).toMatch(/more than 40 pages/);
    expect(f.sent).toEqual([]);
  });

  it("says a refused upload in Studio's words, in the page's language, and keeps the pages", async () => {
    setLang("nb");
    const f = await form(profiles, () => json(answers["POST /v1/jobs/pages"].body, 415));
    f.choose("pages");
    f.pick("#run-pages", "1.png", "IMG_0001.HEIC");
    await f.submit();
    const notice = f.el.querySelector("#run-error .notice-error")!;
    expect(notice.querySelector("p")!.textContent).toMatch(/^En av filene er ikke et bilde eller en PDF/);
    expect(notice.querySelector("details")!.textContent).toContain("IMG_0001.HEIC is a HEIC or AVIF picture");
    expect(f.listedPages()).toEqual(["1.png", "IMG_0001.HEIC"]);
    expect(f.el.querySelector<HTMLButtonElement>("#run-submit")!.disabled).toBe(false);
  });

  it("does not upload a picture as a recording, and says where sheet music is chosen", async () => {
    const f = await form(profiles);
    f.pick("#run-file", "march.png");
    await f.submit();
    expect(f.sent).toEqual([]);
    expect(f.el.querySelector("#run-error")!.textContent).toMatch(/choose “Sheet music: pictures or a PDF” under Source/);
  });
});
