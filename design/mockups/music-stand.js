// Music stand mockups (design/music-stand.md): example part, stand icons and the ?state= switch.
// Loaded after scores.js and before mockup.js renders, so the specs and icons are in place.
(function () {
  const params = new URLSearchParams(location.search);
  document.documentElement.dataset.state = params.get("state") || "shown";

  // Icons the stand needs that are not in design/tokens/icons.json yet (Material Symbols Rounded paths).
  Object.assign(globalThis.BrasscribeIcons || (globalThis.BrasscribeIcons = {}), {
    "music-stand": "M120-120v-200h80v120h120v80H120Zm520 0v-80h120v-120h80v200H640ZM120-640v-200h200v80H200v120h-80Zm640 0v-120H640v-80h200v200h-80Z",
    "rotation-lock": "M280-80q-33 0-56.5-23.5T200-160v-320q0-33 23.5-56.5T280-560h40v-80q0-66 47-113t113-47q66 0 113 47t47 113v80h40q33 0 56.5 23.5T760-480v320q0 33-23.5 56.5T680-80H280Zm0-80h400v-320H280v320Zm200-100q25 0 42.5-17.5T540-320q0-25-17.5-42.5T480-380q-25 0-42.5 17.5T420-320q0 25 17.5 42.5T480-260ZM400-560h160v-80q0-33-23.5-56.5T480-720q-33 0-56.5 23.5T400-640v80Z",
    "rotate": "M482-160q-134 0-228-93t-94-227v-7l-64 64-56-56 160-160 160 160-56 56-64-64v7q0 100 70.5 170T482-240q26 0 51-6t49-18l60 60q-38 22-78 33t-82 11Zm278-161L600-481l56-56 64 64v-7q0-100-70.5-170T478-720q-26 0-51 6t-49 18l-60-60q38-22 78-33t82-11q134 0 228 93t94 227v7l64-64 56 56-160 160Z",
    "page-prev": "M560-240 320-480l240-240 56 56-184 184 184 184-56 56Z",
    "page-next": "M504-480 320-664l56-56 240 240-240 240-56-56 184-184Z",
    "minus": "M200-440v-80h560v80H200Z",
    "plus": "M440-440H200v-80h240v-240h80v240h240v80H520v240h-80v-240Z",
  });

  function parse(str) {
    return str.trim().split(/\s+/).map((t) => {
      if (t[0] === "r") return { r: t[1] };
      const m = t.match(/^([whqe])(-?\d+)(.*)$/);
      const e = { d: m[1], s: +m[2] };
      const f = m[3];
      if (f.includes("u")) e.u = 1;
      if (f.includes("v")) e.u = 2;
      if (f.includes("#")) e.acc = "#";
      if (f.includes("[")) e.beam = "start";
      else if (f.includes("]")) e.beam = "end";
      return e;
    });
  }
  // A Solo Cornet line (invented): 20 bars, repeated to 60.
  const PHRASES = [
    "h7 q6 q5", "e4[ e5] q6u q7 q8", "h9 q8 rq", "e7[ e6] e5[ e4] h3",
    "q4 q5 e6[ e7u] q8", "h9v q8 q7", "q6 q5u h4", "w2",
    "q2 q4 q6 q7", "h8 q7 q6", "e5[ e6] e7[ e8] q9 rq", "h7 h5",
    "q6 q7 h8", "e9[ e8] q7 h6u", "q5 q4 q3 q4", "w5",
    "h7 q8 q9", "h10 q9u q8", "e7[ e6] e5[ e6] q7 rq", "w4",
  ];
  const ALL = [...PHRASES, ...PHRASES, ...PHRASES].map(parse);
  const system = (from, n, extra = {}) => ({
    key: 2, time: from === 1 ? [4, 4] : false, names: false, barNumbers: true,
    bars: Array.from({ length: n }, (_, i) => ({ n: from + i, adlib: from + i <= 2 })),
    staves: [{ name: "Solo Cornet", bars: ALL.slice(from - 1, from - 1 + n) }],
    label: `Solo Cornet, bars ${from} to ${from + n - 1}`,
    ...extra,
  });

  const S = window.SCORES;
  // Phone portrait: three bars a system, seven systems a page; the cursor is in bar 13 (system 5).
  for (let k = 0; k < 7; k++) {
    const from = 1 + k * 3;
    S[`standPhone${k}`] = system(from, 3, { sp: 6.4, top: 40, ...(from === 13 ? { cursor: { bar: 0, frac: 0.35 } } : {}) });
  }
  // Phone landscape: four bars a system, two systems a page (bars 13-20); the cursor is in bar 13.
  S.standLand0 = system(13, 4, { sp: 7.4, top: 46, cursor: { bar: 0, frac: 0.35 } });
  S.standLand1 = system(17, 4, { sp: 7.4, top: 46 });
  S.standLand0Loop = system(13, 4, { sp: 7.4, top: 46, cursor: { bar: 0, frac: 0.35 }, loop: { from: 0, to: 1, label: "Repeat 13–14" } });
  // Tablet landscape: two pages side by side, four bars a system, six systems a page (bars 1-48).
  for (let k = 0; k < 12; k++) {
    const from = 1 + k * 4;
    S[`standTab${k}`] = system(from, 4, { sp: 6.2, top: 40, ...(from === 13 ? { cursor: { bar: 1, frac: 0.3 } } : {}) });
  }
  // Entry: the normal score view on a phone, one part.
  S.entryPhone0 = system(9, 3, { sp: 7, top: 44, cursor: { bar: 1, frac: 0.5 } });
  S.entryPhone1 = system(12, 3, { sp: 7, top: 44 });
  S.entryPhone2 = system(15, 3, { sp: 7, top: 44 });
})();
