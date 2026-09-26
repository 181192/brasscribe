// Example music for the mockups (invented, in the style of a brass-band solo). Compact event syntax:
//   q4  quarter on staff step 4 (0 = bottom line)   e5[ / e4]  eighths beamed from [ to ]
//   h6  half   w3 whole   rq re rh rw  rests
//   suffix u = uncertain, v = very uncertain, # b n = accidental
(function () {
  function parse(str) {
    return str.trim().split(/\s+/).map((t) => {
      if (t[0] === "r") return { r: t[1] };
      const m = t.match(/^([whqe])(-?\d+)(.*)$/);
      const e = { d: m[1], s: +m[2] };
      const f = m[3];
      if (f.includes("u")) e.u = 1;
      if (f.includes("v")) e.u = 2;
      if (f.includes("#")) e.acc = "#";
      if (f.includes("b")) e.acc = "b";
      if (f.includes("n")) e.acc = "n";
      if (f.includes("[")) e.beam = "start";
      else if (f.includes("]")) e.beam = "end";
      else if (e.d === "e" && f.includes("-")) e.beam = "mid";
      return e;
    });
  }
  const bars = (arr) => arr.map(parse);

  const solo = bars([
    "h7 q6 q5",
    "e4[ e5] q6u q7 q8",
    "h9 q8 rq",
    "e7[ e6] e5[ e4] h3",
    "q4 q5 e6[ e7u] q8",
    "h9v q8 q7",
    "q6 q5u h4",
    "w2",
  ]);
  const flugel = bars(["w4", "h3 h4", "h5 q4 rq", "w3", "h2 h3", "h4 q5 q4", "h3 h2", "w0"]);
  const horn = bars(["h2 h1", "h0 h1", "h2 rh", "h1 h0", "q1 q2 h3", "h2 h1", "h1 h0u", "w-1"]);
  const bari = bars(["w-2", "h-1 h0", "h1 rh", "h0 h-1", "h-2 h-1", "h0 q1 q0", "h-1 h-2", "w-3"]);
  const euph = bars(["q0 q1 h2", "e3[ e2] q1 h0", "h1 q2 q3", "w2", "q1 q2 q3 q4", "h5u h4", "q3 q2 h1", "w0"]);
  const bass = bars(["w-3", "h-4 h-3", "h-2 rh", "h-3 h-4", "w-3", "h-2 h-3", "h-4 h-5", "w-6"]);

  const barsMeta = (from, n, adlib = []) => Array.from({ length: n }, (_, i) => ({ n: from + i, adlib: adlib.includes(i) }));

  window.SCORES = {
    // Full score, desktop: six staves, loop set on bars 12-13, cursor in bar 13.
    full: {
      sp: 8, key: 2, time: [4, 4], nameWidth: 128, staffGap: 52, top: 64,
      bars: barsMeta(9, 8),
      staves: [
        { name: "Solo Cornet", bars: solo }, { name: "Flugelhorn", bars: flugel }, { name: "Solo Horn", bars: horn },
        { name: "Baritone", bars: bari }, { name: "Euphonium", bars: euph }, { name: "E♭ Bass", bars: bass },
      ],
      loop: { from: 3, to: 4, label: "Loop 12–13" }, cursor: { bar: 4, frac: 0.42 },
      label: "Score, bars 9 to 16. Loop set, bars 12 to 13.",
    },
    // Phone score view: three staves, four bars.
    phone: {
      sp: 6, key: 2, time: [4, 4], nameWidth: 50, staffGap: 30, top: 46,
      bars: barsMeta(9, 3),
      staves: [
        { name: "Solo", bars: solo.slice(0, 3) }, { name: "Flug.", bars: flugel.slice(0, 3) },
        { name: "Euph.", bars: euph.slice(0, 3) }, { name: "Bass", bars: bass.slice(0, 3) },
      ],
      cursor: { bar: 1, frac: 0.55 },
      label: "Score, bars 9 to 11",
    },
    phone2: {
      sp: 6, key: 2, time: false, nameWidth: 50, staffGap: 30, top: 46,
      bars: barsMeta(12, 3),
      staves: [
        { name: "Solo", bars: solo.slice(3, 6) }, { name: "Flug.", bars: flugel.slice(3, 6) },
        { name: "Euph.", bars: euph.slice(3, 6) }, { name: "Bass", bars: bass.slice(3, 6) },
      ],
      label: "Score, bars 12 to 14",
    },
    // Single part, large: Solo Cornet with ad lib opening, uncertain marks, focus on one note.
    part1: {
      sp: 11, key: 2, time: [4, 4], names: false, top: 78,
      bars: [{ n: 1, adlib: true }, { n: 2, adlib: true }, { n: 3 }],
      staves: [{ name: "Solo Cornet", bars: bars(["w5", "h6 q7u q8", "h9 q8 q7"]) }],
      label: "Solo Cornet, bars 1 to 3",
    },
    part2: {
      sp: 11, key: 2, time: false, clef: true, names: false, top: 78,
      bars: barsMeta(4, 3),
      staves: [{ name: "Solo Cornet", bars: solo.slice(1, 4) }],
      cursor: { bar: 0, frac: 0.6 },
      label: "Solo Cornet, bars 4 to 6",
    },
    part3: {
      sp: 11, key: 2, time: false, names: false, top: 78,
      bars: barsMeta(7, 3),
      staves: [{ name: "Solo Cornet", bars: solo.slice(4, 7) }],
      label: "Solo Cornet, bars 7 to 9",
    },
    partPhone1: {
      sp: 9, key: 2, time: [4, 4], names: false, top: 64,
      bars: [{ n: 1, adlib: true }, { n: 2 }],
      staves: [{ name: "Solo Cornet", bars: bars(["w5", "h6 q7u q8"]) }],
    },
    partPhone2: {
      sp: 9, key: 2, time: false, names: false, top: 64,
      bars: barsMeta(3, 2),
      staves: [{ name: "Solo Cornet", bars: bars(["h9 q8 q7", "e4[ e5] q6u q7 q8"]) }],
      cursor: { bar: 1, frac: 0.35 },
    },
    partPhone3: {
      sp: 9, key: 2, time: false, names: false, top: 64,
      bars: barsMeta(5, 2),
      staves: [{ name: "Solo Cornet", bars: bars(["h9v q8 q7", "q6 q5u h4"]) }],
    },
    // Review: one bar at a time, with the note in focus.
    reviewBar: {
      sp: 10, key: 2, time: false, names: false, top: 70,
      bars: barsMeta(14, 2),
      staves: [{ name: "Solo Cornet", bars: bars(["h9v q8 q7", "q6 q5u h4"]) }],
      focus: { staff: 0, bar: 0, ev: 0 }, focusGap: 3,
      label: "Bars 14 and 15. Bar 14, beat 1: A5, half note, very uncertain.",
    },
    reviewBarPhone: {
      sp: 8.5, key: 2, time: false, names: false, top: 62,
      bars: barsMeta(14, 2),
      staves: [{ name: "Solo Cornet", bars: bars(["h9v q8 q7", "q6 q5u h4"]) }],
      focus: { staff: 0, bar: 0, ev: 0 }, focusGap: 3,
    },
    mini1: { sp: 6, key: 2, time: false, clef: true, names: false, top: 34, barNumbers: false, bars: barsMeta(10, 1), staves: [{ name: "", bars: bars(["e4[ e5] q6u q7 q8"]) }] },
    mini2: { sp: 6, key: 2, time: false, clef: true, names: false, top: 34, barNumbers: false, bars: barsMeta(13, 1), staves: [{ name: "", bars: bars(["q4 q5 e6[ e7u] q8"]) }] },
    mini3: { sp: 6, key: 2, time: false, clef: true, names: false, top: 34, barNumbers: false, bars: barsMeta(14, 1), staves: [{ name: "", bars: bars(["h9v q8 q7"]) }] },
    mini4: { sp: 6, key: 2, time: false, clef: true, names: false, top: 34, barNumbers: false, bars: barsMeta(15, 1), staves: [{ name: "", bars: bars(["q6 q5u h4"]) }] },
    // Studio: denser score strip.
    studio: {
      sp: 6, key: 2, time: [4, 4], nameWidth: 96, staffGap: 30, top: 44,
      bars: barsMeta(1, 8, [0, 1]),
      staves: [
        { name: "Solo Cornet", bars: bars(["w5", "h6 q7u q8", ...["h9 q8 rq", "e7[ e6] e5[ e4] h3", "q4 q5 e6[ e7u] q8", "h9v q8 q7", "q6 q5u h4", "w2"]]) },
        { name: "Euphonium", bars: euph }, { name: "E♭ Bass", bars: bass },
      ],
      cursor: { bar: 3, frac: 0.3 },
    },
  };
})();
