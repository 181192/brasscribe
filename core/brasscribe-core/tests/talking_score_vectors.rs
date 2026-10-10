//! Talking-score conformance vectors (docs/accessibility/talking-score-vectors.json),
//! every case in both languages.

use brasscribe_core::talking_score::{announce, Bar, Context, Part, Settings};
use serde_json::{json, Value};

/// A case read the way every app's vector test reads it: B-flat cornet,
/// written key 2 sharps and 128 bars unless the case says otherwise.
fn vector_call(c: &Value, lang: &str) -> String {
    let st = |k: &str, d: &str| c["settings"].get(k).and_then(|v| v.as_str()).unwrap_or(d).to_string();
    let settings = Settings { lang: lang.into(), pitch_mode: st("pitch_mode", "written"), verbosity: st("verbosity", "standard"), ..Default::default() };
    let cx = &c["context"];
    let ctx = Context {
        part: cx.get("part").and_then(|v| v.as_str()).map(String::from),
        bar: cx.get("bar").and_then(|v| v.as_i64()),
        pitch_mode: cx.get("pitch_mode").and_then(|v| v.as_str()).map(String::from),
    };
    let pn = c.get("part");
    let ps = |k: &str| pn.and_then(|p| p.get(k)).and_then(|v| v.as_str()).map(String::from);
    let part = Part {
        name: ps("name").or(ctx.part.clone()).unwrap_or_else(|| "Solo Cornet".into()),
        name_nb: ps("name_nb"),
        instrument: ps("instrument").or(Some("Cornet in B♭".into())),
        instrument_nb: ps("instrument_nb").or(if pn.is_none() { Some("kornett i B".into()) } else { None }),
        transpose: Some(json!({"chromatic": -2, "diatonic": -1})),
    };
    let b = c.get("bar").cloned().unwrap_or(json!({}));
    let fr = b.get("free_region").filter(|r| r.is_object());
    let region = fr.map(|r| json!({"start_bar": r["start_bar"], "end_bar": r["end_bar"], "start_s": r["start_s"], "end_s": r["end_s"]}));
    let bar = Bar {
        number: b.get("number").and_then(|v| v.as_i64()).or(ctx.bar).unwrap_or(1),
        key_fifths: b.get("key_fifths").and_then(|v| v.as_i64()).unwrap_or(2),
        tempo_marked: b.get("tempo_bpm").and_then(|v| v.as_f64()),
        free_region: region,
        entering_region: fr.and_then(|r| r.get("entering")).and_then(|v| v.as_bool()).unwrap_or(false),
        a_tempo: b.get("a_tempo").and_then(|v| v.as_bool()).unwrap_or(false),
        total_bars: 128,
        ..Default::default()
    };
    announce(&part, &bar, &c["event"], &ctx, &settings, false)
}

#[test]
fn every_vector_in_both_languages() {
    let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../docs/accessibility/talking-score-vectors.json");
    let doc: Value = serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap();
    let cases = doc["cases"].as_array().unwrap();
    let mut failures = Vec::new();
    let mut n = 0;
    for c in cases {
        for lang in ["en", "nb"] {
            n += 1;
            let got = vector_call(c, lang);
            let want = c["expected"][lang].as_str().unwrap();
            if got != want {
                failures.push(format!("{} [{lang}]\n  got:  {got}\n  want: {want}", c["id"]));
            }
        }
    }
    assert!(failures.is_empty(), "{}/{n} vectors differ:\n{}", failures.len(), failures.join("\n"));
    assert_eq!(n, cases.len() * 2);
}

#[test]
fn navigation_walks_a_built_score() {
    use brasscribe_core::talking_score::{announce_at, build, navigate, part_lines, Cursor, Unit};
    let xml = r#"<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><work><work-title>T</work-title></work>
<part-list><score-part id="P1"><part-name>Solo Cornet</part-name><score-instrument id="I1"><instrument-name>Cornet in B♭</instrument-name></score-instrument></score-part></part-list>
<part id="P1">
<measure number="1"><attributes><divisions>2</divisions><key><fifths>2</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><transpose><diatonic>-1</diatonic><chromatic>-2</chromatic></transpose></attributes>
<note><pitch><step>B</step><alter>-1</alter><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>half</type></note>
<note><pitch><step>G</step><octave>5</octave></pitch><duration>4</duration><voice>1</voice><type>half</type><tie type="start"/></note></measure>
<measure number="2"><note><pitch><step>G</step><octave>5</octave></pitch><duration>8</duration><voice>1</voice><type>whole</type><tie type="stop"/></note></measure>
<measure number="3"><note><rest measure="yes"/><duration>8</duration><voice>1</voice></note></measure>
</part></score-partwise>"#;
    let doc = build(xml, None).unwrap();
    let s = Settings::default();
    let c0 = Cursor { part: 0, bar: 0, event: 0 };
    let c1 = navigate(&doc, c0, Unit::Note, true).unwrap();
    assert_eq!(c1, Cursor { part: 0, bar: 0, event: 1 });
    let c2 = navigate(&doc, c1, Unit::Note, true).unwrap();
    assert_eq!(c2, Cursor { part: 0, bar: 1, event: 0 });
    let ctx = Context { part: Some("Solo Cornet".into()), bar: Some(1), pitch_mode: Some("written".into()) };
    assert_eq!(announce_at(&doc, c2, &ctx, &s, false).unwrap(), "bar 2, beat 1: G 5 held, from bar 1 beat 3");
    let lines = part_lines(&doc, 0, &s);
    assert_eq!(lines[1].1, vec!["bar 2, beat 1: G 5 held, from bar 1 beat 3".to_string()]);
    assert_eq!(navigate(&doc, c2, Unit::Bar, true), Some(Cursor { part: 0, bar: 2, event: 0 }));
    assert_eq!(navigate(&doc, c0, Unit::Part, true), None);
    let ctx2 = Context { bar: Some(2), ..ctx };
    assert_eq!(announce_at(&doc, Cursor { part: 0, bar: 2, event: 0 }, &ctx2, &s, true).unwrap(), "bar 3: rest, whole bar");
}

#[test]
fn compound_time_names_eighths_not_triplets() {
    use brasscribe_core::talking_score::{build, part_lines};
    let xml = r#"<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><work><work-title>T</work-title></work>
<part-list><score-part id="P1"><part-name>Solo Cornet</part-name><score-instrument id="I1"><instrument-name>Cornet in B♭</instrument-name></score-instrument></score-part></part-list>
<part id="P1">
<measure number="1"><attributes><divisions>2</divisions><key><fifths>2</fifths></key><time><beats>6</beats><beat-type>8</beat-type></time><transpose><diatonic>-1</diatonic><chromatic>-2</chromatic></transpose></attributes>
<note><pitch><step>D</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>eighth</type></note>
<note><pitch><step>E</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>eighth</type></note>
<note><pitch><step>F</step><alter>1</alter><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>eighth</type></note>
<note><pitch><step>G</step><octave>5</octave></pitch><duration>2</duration><voice>1</voice><type>quarter</type></note>
<note><pitch><step>A</step><octave>5</octave></pitch><duration>1</duration><voice>1</voice><type>eighth</type><tie type="start"/></note></measure>
<measure number="2"><note><pitch><step>A</step><octave>5</octave></pitch><duration>6</duration><voice>1</voice><type>half</type><dot/><tie type="stop"/></note></measure>
</part></score-partwise>"#;
    let doc = build(xml, None).unwrap();
    assert_eq!(doc["parts"][0]["bars"][0]["events"][1]["pos"], json!({"beat": 1, "num": 1, "den": 3, "compound": true}));
    let lines = part_lines(&doc, 0, &Settings::default());
    assert_eq!(
        lines[0].1,
        [
            "bar 1, beat 1: D 5, eighth note",
            "beat 1, eighth 2: E 5, eighth note",
            "beat 1, eighth 3: F-sharp 5, eighth note",
            "beat 2: G 5, quarter note",
            "beat 2, eighth 3: A 5, eighth note, tied to dotted half note in bar 2",
        ]
    );
    assert_eq!(lines[1].1, ["bar 2, beat 1: A 5 held, from bar 1 beat 2, eighth 3"]);
    let nb = part_lines(&doc, 0, &Settings { lang: "nb".into(), ..Default::default() });
    assert_eq!(nb[0].1[1], "slag 1, 2. åttendedel: E 5, åttendedelsnote");
    assert_eq!(nb[1].1, ["takt 2, slag 1: A 5 holdes, fra takt 1 slag 2, 3. åttendedel"]);

    let rest = xml.replace(
        r#"<measure number="2"><note><pitch><step>A</step><octave>5</octave></pitch><duration>6</duration><voice>1</voice><type>half</type><dot/><tie type="stop"/></note></measure>"#,
        r#"<measure number="2"><note><rest measure="yes"/><duration>6</duration><voice>1</voice></note></measure>"#,
    );
    let doc = build(&rest, None).unwrap();
    let ev = &doc["parts"][0]["bars"][1]["events"][0];
    assert_eq!(ev["kind"], "bar-rest");
    assert_eq!(ev["pos"], json!({"beat": 1, "num": 0, "den": 1, "compound": true}));
}

#[test]
fn a_pickup_is_named_and_its_notes_sit_on_the_beats_of_the_bar_they_lead_into() {
    use brasscribe_core::talking_score::{build, part_lines, TICKS_PER_QUARTER};
    let xml = r#"<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><work><work-title>Pickup</work-title></work>
<part-list><score-part id="P1"><part-name>Solo Cornet</part-name></score-part><score-part id="P2"><part-name>2nd Horn</part-name></score-part></part-list>
<part id="P1">
<measure number="0" implicit="yes"><attributes><divisions>2</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>1</duration><voice>1</voice><type>eighth</type></note>
<note><pitch><step>A</step><octave>4</octave></pitch><duration>2</duration><voice>1</voice><type>quarter</type><tie type="start"/></note></measure>
<measure number="1"><note><pitch><step>A</step><octave>4</octave></pitch><duration>8</duration><voice>1</voice><type>whole</type><tie type="stop"/></note></measure>
<measure number="2"><note><pitch><step>C</step><octave>5</octave></pitch><duration>8</duration><voice>1</voice><type>whole</type></note></measure>
</part>
<part id="P2">
<measure number="0" implicit="yes"><attributes><divisions>2</divisions><key><fifths>0</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time></attributes>
<note><rest measure="yes"/><duration>3</duration><voice>1</voice></note></measure>
<measure number="1"><note><rest measure="yes"/><duration>8</duration><voice>1</voice></note></measure>
<measure number="2"><note><pitch><step>C</step><octave>4</octave></pitch><duration>8</duration><voice>1</voice><type>whole</type></note></measure>
</part></score-partwise>"#;
    let doc = build(xml, None).unwrap();
    assert_eq!(doc["total_bars"], 2, "the pickup is not one of the bars counted");
    let pickup = &doc["parts"][0]["bars"][0];
    assert_eq!(pickup["number"], 0);
    assert_eq!(pickup["events"][0]["tick"], 0);
    assert_eq!(pickup["events"][0]["pos"], json!({"beat": 3, "num": 1, "den": 2}));
    assert_eq!(pickup["events"][1]["tick"], TICKS_PER_QUARTER / 2);
    assert_eq!(pickup["events"][1]["pos"], json!({"beat": 4, "num": 0, "den": 1}));
    let en = part_lines(&doc, 0, &Settings::default());
    assert_eq!(en[0].0, "Pickup");
    assert_eq!(en[0].1, ["pickup, beat 3 and: G 4, eighth note", "beat 4: A 4, quarter note, tied to whole note in bar 1"]);
    assert_eq!(en[1], ("Bar 1".to_string(), vec!["bar 1, beat 1: A 4 held, from pickup beat 4".to_string()]));
    let nb_settings = Settings { lang: "nb".into(), ..Default::default() };
    let nb = part_lines(&doc, 0, &nb_settings);
    assert_eq!(nb[0].0, "Opptakt");
    assert_eq!(nb[0].1[0], "opptakt, slag 3-og: G 4, åttendedelsnote");
    assert_eq!(nb[1].1, ["takt 1, slag 1: A 4 holdes, fra opptakt slag 4"]);
    let full = part_lines(&doc, 0, &Settings { verbosity: "full".into(), ..Default::default() });
    assert!(full[0].1[0].starts_with("pickup, beat 3 and: "), "{}", full[0].1[0]);
    assert!(full[1].1[0].starts_with("bar 1 of 2, beat 1: "), "{}", full[1].1[0]);
    assert_eq!(part_lines(&doc, 1, &Settings::default())[0], ("Pickup and bar 1".to_string(), vec!["pickup and bar 1: rest".to_string()]));
    assert_eq!(part_lines(&doc, 1, &nb_settings)[0], ("Opptakt og takt 1".to_string(), vec!["opptakt og takt 1: pause".to_string()]));

    // A first measure left out of the numbering is the pickup too.
    let unnumbered = build(&xml.replace(r#"number="0" implicit="yes""#, r#"number="X1" implicit="yes""#), None).unwrap();
    assert_eq!(unnumbered["parts"][0]["bars"][0]["number"], 0);
    assert_eq!(unnumbered["parts"][0]["bars"][0]["events"][0]["pos"], json!({"beat": 3, "num": 1, "den": 2}));
}
