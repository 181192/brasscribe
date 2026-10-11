//! The band draft the apps make on the device: Basic Pitch on the whole mix in every slot of the
//! song arranger (arrange_song_with), on the committed ChoraleBricks transcriptions.

use std::path::PathBuf;

use scribe_ffi::{arrange_song, arrange_song_with, CoreError, SongArrangeOptions};

fn chorales() -> Vec<PathBuf> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../eval/fixtures/choralebricks-brass4");
    let mut dirs: Vec<PathBuf> = std::fs::read_dir(&root).unwrap().map(|e| e.unwrap().path()).filter(|p| p.join("basic-pitch.mid").is_file()).collect();
    dirs.sort();
    assert!(dirs.len() >= 10, "chorale fixtures missing under {}", root.display());
    dirs
}

/// Basic Pitch fills the melody, bass and harmony slots, with no melody support.
fn draft(dir: &PathBuf, options: SongArrangeOptions) -> Result<scribe_ffi::SongOutput, CoreError> {
    let bp = std::fs::read(dir.join("basic-pitch.mid")).unwrap();
    let beats = std::fs::read_to_string(dir.join("beat-this.beats")).unwrap();
    arrange_song_with(bp.clone(), None, bp.clone(), vec![bp], beats, "Draft".into(), options)
}

fn parts(xml: &str) -> Vec<String> {
    xml.split("<part-name>").skip(1).map(|s| s.split('<').next().unwrap().to_string()).collect()
}

/// Bars per part, from the MusicXML (`<measure` per `<part id=`).
fn bars_per_part(xml: &str) -> Vec<usize> {
    xml.split("<part id=").skip(1).map(|p| p.matches("<measure ").count()).collect()
}

#[test]
fn every_chorale_gives_a_band_with_every_part_the_same_length() {
    for dir in chorales() {
        for (lineup, n) in [("minimal", 8), ("quartet", 4)] {
            let out = draft(&dir, SongArrangeOptions { lineup: lineup.into(), ..Default::default() }).unwrap();
            let names = parts(&out.musicxml);
            assert_eq!(names.len(), n, "{} {lineup}: {names:?}", dir.display());
            let bars = bars_per_part(&out.musicxml);
            assert_eq!(bars.len(), n);
            assert!(bars.iter().all(|&b| b == bars[0] && b >= 4), "{} {lineup}: bars per part {bars:?}", dir.display());
            let comp: serde_json::Value = serde_json::from_str(&out.composition_json).unwrap();
            for id in ["melody", "bass", "harmony"] {
                let v = comp["voices"].as_array().unwrap().iter().find(|v| v["id"] == id).unwrap();
                assert!(!v["notes"].as_array().unwrap().is_empty(), "{} {lineup}: no {id} notes", dir.display());
            }
            // A quartet is recorded in the composition, so arranging it again keeps the lineup.
            assert_eq!(comp["arrangement"]["lineup"].as_str(), (lineup == "quartet").then_some("quartet"));
        }
    }
}

#[test]
fn the_default_options_are_arrange_song() {
    let dir = &chorales()[0];
    let bp = std::fs::read(dir.join("basic-pitch.mid")).unwrap();
    let beats = std::fs::read_to_string(dir.join("beat-this.beats")).unwrap();
    let plain = arrange_song(bp.clone(), None, bp.clone(), vec![bp], beats, "Draft".into()).unwrap();
    let with = draft(dir, SongArrangeOptions::default()).unwrap();
    assert_eq!(plain.musicxml, with.musicxml);
    assert_eq!(plain.composition_json, with.composition_json);
}

#[test]
fn a_seat_is_recorded_and_can_carry_the_tune() {
    let dir = &chorales()[0];
    let o = SongArrangeOptions { seat: Some("euphonium".into()), lead: Some("seat".into()), ..Default::default() };
    let comp: serde_json::Value = serde_json::from_str(&draft(dir, o).unwrap().composition_json).unwrap();
    assert_eq!(comp["arrangement"]["seat"], "euphonium");
    assert_eq!(comp["arrangement"]["lead"], "seat");
}

#[test]
fn options_that_do_not_fit_are_invalid_input() {
    let dir = &chorales()[0];
    let bad = [
        SongArrangeOptions { lineup: "band".into(), ..Default::default() },
        SongArrangeOptions { lead: Some("seat".into()), ..Default::default() },
        SongArrangeOptions { seat: Some("nope".into()), ..Default::default() },
        SongArrangeOptions { lead: Some("x".into()), ..Default::default() },
        SongArrangeOptions { seat: Some("euphonium".into()), reads: Some("alto".into()), ..Default::default() },
    ];
    for o in bad {
        let desc = format!("{o:?}");
        // the core's own check refuses it too: the binding asks that check, it has no rules of its own
        let core = target_brass::pipeline::SongOptions {
            lineup: o.lineup.clone(),
            seat: o.seat.clone(),
            reads: o.reads.clone(),
            lead: o.lead.clone().unwrap_or_default(),
            kit: String::new(),
        };
        assert!(target_brass::pipeline::check_song_options(&core).is_err(), "{desc}");
        assert!(matches!(draft(dir, o), Err(CoreError::Invalid { .. })), "{desc}");
    }
}
