//! The band's own soloist: faithful placement as played inside the solo range, and its range check.

use brasscribe_core::arranger::{in_register, place_soloist};
use brasscribe_core::instruments::{brass_band, lead_lineup, minimal_band, quartet, seat_lineup, RangeCheck, CORNET};
use brasscribe_core::model::Note;

fn line(pitches: &[i32]) -> Vec<Note> {
    pitches.iter().enumerate().map(|(i, &p)| Note::new(p, 12 * i as i64, 12, 1.0, vec![])).collect()
}

fn pitches(notes: &[Note]) -> Vec<i32> {
    notes.iter().map(|n| n.pitch).collect()
}

#[test]
fn the_cornet_soloist_reaches_written_d6() {
    assert_eq!(CORNET.solo_range(), (52, 84));
    assert_eq!(CORNET.pro, (52, 82));
    assert_eq!(CORNET.placement_limit(), (52, 82), "section cornets keep the playable top");
}

#[test]
fn a_phrase_inside_the_range_is_written_as_played() {
    let lead = brass_band().lead_part().clone();
    let mut w = Vec::new();
    let solo = line(&[69, 72, 76, 81, 83, 84, 81, 79, 74]);
    assert_eq!(pitches(&place_soloist(&solo, &lead, &mut w)), pitches(&solo));
    assert!(w.is_empty(), "{w:?}");
}

#[test]
fn one_outlier_moves_alone_and_the_run_keeps_its_direction() {
    let lead = brass_band().lead_part().clone();
    let mut w = Vec::new();
    // A rising run with one tracker octave error (78 heard as 90).
    let placed = place_soloist(&line(&[72, 74, 76, 90, 79, 81]), &lead, &mut w);
    assert_eq!(pitches(&placed), vec![72, 74, 76, 78, 79, 81]);
    assert!(pitches(&placed).windows(2).all(|p| p[1] > p[0]), "the run still rises");
    assert_eq!(w, vec!["Solo Cornet: moved 90 to 78 at tick 36 (outside the range)"]);
}

#[test]
fn a_phrase_mostly_outside_takes_the_fewest_octaves() {
    let lead = brass_band().lead_part().clone();
    let mut w = Vec::new();
    let placed = place_soloist(&line(&[40, 43, 47, 50, 52]), &lead, &mut w);
    assert_eq!(pitches(&placed), vec![52, 55, 59, 62, 64]);
    assert!(w.is_empty(), "{w:?}");
}

#[test]
fn the_register_gate_needs_95_percent_inside() {
    let range = CORNET.solo_range();
    let mut ps: Vec<i32> = vec![60; 19];
    ps.push(40);
    assert!(in_register(&line(&ps), range), "19 of 20 inside");
    ps.push(41);
    assert!(!in_register(&line(&ps), range), "19 of 21 inside");
    assert!(!in_register(&[], range));
}

#[test]
fn the_soloist_lead_is_checked_against_the_solo_range() {
    for lineup in [brass_band(), minimal_band()] {
        assert!(lineup.soloist_lead());
        assert_eq!(lineup.check("Solo Cornet", 84), RangeCheck::Uncomfortable, "{}", lineup.name);
        assert_eq!(lineup.check("Solo Cornet", 85), RangeCheck::Impossible);
        assert_eq!(lineup.check("Solo Cornet", 79), RangeCheck::Ok);
        assert_eq!(lineup.check("2nd Cornet", 83), RangeCheck::Impossible, "section cornets keep 82");
    }
    assert_eq!(brass_band().check("Repiano Cornet", 83), RangeCheck::Impossible);
}

#[test]
fn not_a_soloist_lead_quartet_solo_take_or_moved_tune() {
    let q = quartet();
    assert!(!q.soloist_lead());
    assert_eq!(q.check("1st Cornet", 83), RangeCheck::Impossible);
    let take = seat_lineup("solo-cornet", None).unwrap();
    assert!(!take.soloist_lead());
    let euph = lead_lineup(brass_band(), "euphonium").unwrap();
    assert!(euph.lead_moved && !euph.soloist_lead());
    assert_eq!(euph.check("Solo Cornet", 83), RangeCheck::Impossible);
    // The tune already on the seat's part does not move it.
    let own = lead_lineup(brass_band(), "solo-cornet").unwrap();
    assert!(!own.lead_moved && own.soloist_lead());
}

fn direction(ps: &[i32]) -> Vec<i32> {
    ps.windows(2).map(|w| (w[1] - w[0]).signum()).collect()
}

#[test]
fn a_phrase_past_the_solo_range_keeps_its_direction() {
    let lead = brass_band().lead_part().clone();
    let (lo, hi) = lead.instrument.solo_range();
    for ps in [
        vec![76, 79, 81, 84, 86, 88, 86, 84, 81, 79], // an arch that peaks two tones above the range
        vec![72, 74, 76, 77, 79, 81, 83, 84, 86, 87], // a run that ends above it
        vec![84, 86, 84, 86, 84, 86, 84],             // a trill across the top
    ] {
        let placed = pitches(&place_soloist(&line(&ps), &lead, &mut Vec::new()));
        assert!(placed.iter().all(|&p| lo <= p && p <= hi), "{placed:?}");
        assert_eq!(direction(&placed), direction(&ps), "{ps:?} -> {placed:?}");
    }
}
