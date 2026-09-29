//! Seats: the seat -> part table as the plan writes it, walked for every seat and lineup.

use brasscribe_core::instruments::{brass_band, check_reads, lineup_by_name, part_banks, seat_part, SEATS};
use brasscribe_core::talking_score::nb_part_name;

/// (seat, full band, small band, quartet); None = no part.
const TABLE: [(&str, Option<&str>, Option<&str>, Option<&str>); 18] = [
    ("soprano-cornet", Some("Soprano Cornet"), Some("Solo Cornet"), Some("1st Cornet")),
    ("solo-cornet", Some("Solo Cornet"), Some("Solo Cornet"), Some("1st Cornet")),
    ("repiano-cornet", Some("Repiano Cornet"), Some("2nd Cornet"), Some("2nd Cornet")),
    ("2nd-cornet", Some("2nd Cornet"), Some("2nd Cornet"), Some("2nd Cornet")),
    ("3rd-cornet", Some("3rd Cornet"), Some("2nd Cornet"), Some("2nd Cornet")),
    ("flugelhorn", Some("Flugelhorn"), Some("Flugelhorn"), Some("2nd Cornet")),
    ("solo-horn", Some("Solo Horn"), Some("Solo Horn"), Some("Tenor Horn")),
    ("1st-horn", Some("1st Horn"), Some("Solo Horn"), Some("Tenor Horn")),
    ("2nd-horn", Some("2nd Horn"), Some("Solo Horn"), Some("Tenor Horn")),
    ("1st-baritone", Some("1st Baritone"), Some("Euphonium"), Some("Euphonium")),
    ("2nd-baritone", Some("2nd Baritone"), Some("Euphonium"), Some("Euphonium")),
    ("1st-trombone", Some("1st Trombone"), Some("1st Trombone"), Some("Euphonium")),
    ("2nd-trombone", Some("2nd Trombone"), Some("1st Trombone"), Some("Euphonium")),
    ("bass-trombone", Some("Bass Trombone"), Some("E♭ Bass"), Some("Euphonium")),
    ("euphonium", Some("Euphonium"), Some("Euphonium"), Some("Euphonium")),
    ("eb-bass", Some("E♭ Bass"), Some("E♭ Bass"), Some("Euphonium")),
    ("bb-bass", Some("B♭ Bass"), Some("B♭ Bass"), Some("Euphonium")),
    ("percussion", Some("Percussion"), None, None),
];

/// (seat, lineup) in a different key as the player reads by default. The bass trombone reads bass clef
/// at concert pitch, and so do its mapped parts.
const OTHER_KEY: [(&str, &str); 3] = [("soprano-cornet", "minimal"), ("soprano-cornet", "quartet"), ("eb-bass", "quartet")];

#[test]
fn seats_are_the_contest_band_then_the_trumpet() {
    let names: Vec<&str> = SEATS.iter().map(|s| s.part).collect();
    let band: Vec<&str> = brass_band().parts.iter().map(|p| p.name).collect();
    assert_eq!(names[..band.len()], band[..]);
    assert_eq!(names[band.len()..], ["Trumpet"]);
}

/// A trumpet player takes the lead part in the bands (written for trumpet), and 1st Cornet in the quartet.
#[test]
fn the_trumpet_takes_the_lead() {
    use brasscribe_core::instruments::{lead_lineup, seat_by_id, seat_lineup, with_seat, SeatPart};
    for lineup in ["band", "minimal"] {
        let sp = seat_part(lineup, "trumpet").unwrap();
        assert_eq!(sp, SeatPart { part: Some("Trumpet"), exact: false, same_key: true, takes: Some("Solo Cornet") }, "{lineup}");
        let base = lineup_by_name(lineup).unwrap();
        let l = with_seat(base.clone(), lineup, "trumpet");
        assert_eq!(l.lead, "Trumpet");
        assert!(!l.has("Solo Cornet") && l.soloist_lead() && !l.lead_moved);
        assert_eq!(l.parts.len(), base.parts.len());
        let (t, sc) = (l.by_name("Trumpet"), base.by_name("Solo Cornet"));
        assert_eq!((t.instrument.id, t.players, t.midi_bank.or(Some(1))), ("bb-trumpet", sc.players, sc.midi_bank.or(Some(1))));
        assert_eq!(l.parts.iter().position(|p| p.name == "Trumpet"), base.parts.iter().position(|p| p.name == "Solo Cornet"));
        // lead=seat: the tune is on the trumpet already.
        assert_eq!(lead_lineup(base, "trumpet").unwrap(), l);
    }
    let q = seat_part("quartet", "trumpet").unwrap();
    assert_eq!((q.part, q.exact, q.same_key, q.takes), (Some("1st Cornet"), false, true, None));
    assert_eq!(with_seat(lineup_by_name("quartet").unwrap(), "quartet", "trumpet"), lineup_by_name("quartet").unwrap());
    let take = seat_lineup("trumpet", None).unwrap();
    assert_eq!((take.lead, take.parts[0].instrument.pro), ("Trumpet", (52, 85)));
    assert!(seat_by_id("trumpet").unwrap().tune());
    assert_eq!(nb_part_name("Trumpet"), "Trompet");
    assert!(part_banks().contains(&("Trumpet", 1)));
    // Only a seat that is no band part takes the lead: the soprano cornet maps to Solo Cornet as before.
    assert_eq!(seat_part("minimal", "soprano-cornet").unwrap().takes, None);
}

#[test]
fn seat_part_table() {
    let banks = part_banks();
    for (seat, band, minimal, quartet) in TABLE {
        let own = SEATS.iter().find(|s| s.id == seat).unwrap().part;
        for (lineup, want) in [("band", band), ("minimal", minimal), ("quartet", quartet)] {
            let sp = seat_part(lineup, seat).unwrap();
            assert_eq!(sp.part, want, "{seat} in {lineup}");
            match want {
                None => assert!(!sp.exact && !sp.same_key),
                Some(name) => {
                    assert!(lineup_by_name(lineup).unwrap().has(name));
                    assert_eq!(sp.exact, name == own, "{seat} in {lineup}");
                    assert_eq!(sp.same_key, !OTHER_KEY.contains(&(seat, lineup)), "{seat} in {lineup}");
                    // Every resolved part has a Norwegian name and (but percussion) a SoundFont bank.
                    assert_ne!(nb_part_name(name), name, "{name}");
                    assert!(name == "Percussion" || banks.iter().any(|(n, _)| *n == name), "{name}");
                }
            }
        }
        assert_eq!(seat_part("full", seat), seat_part("band", seat));
        assert_eq!(seat_part("", seat), seat_part("band", seat));
    }
    assert!(seat_part("band", "tuba").is_err());
    assert!(seat_part("orchestra", "euphonium").is_err());
}

/// With no `reads`, the seat's part in every lineup is written in the seat's own first clef, and a
/// bass-clef part at concert pitch: the bass trombonist gets E♭ Bass and Euphonium in bass clef.
#[test]
fn default_reading_in_every_lineup() {
    use brasscribe_core::instruments::{seat_by_id, with_reading, Clef};
    for s in &SEATS {
        for lineup in ["band", "minimal", "quartet"] {
            let Some(part) = seat_part(lineup, s.id).unwrap().part else { continue };
            let base = brasscribe_core::instruments::with_seat(lineup_by_name(lineup).unwrap(), lineup, s.id);
            let l = with_reading(base.clone(), seat_by_id(s.id).unwrap(), Some(part), None);
            let inst = l.by_name(part).instrument;
            match s.default_reading() {
                Some("bass") => assert!(inst.clef == Clef::Bass && inst.chromatic == 0, "{} in {lineup}: {part}", s.id),
                Some("treble") => assert_eq!(inst.clef, Clef::Treble, "{} in {lineup}: {part}", s.id),
                other => assert_eq!(other, None, "{}", s.id),
            }
            // An explicit reading still wins.
            if s.reads.contains(&"bass") {
                let l = with_reading(base, seat_by_id(s.id).unwrap(), Some(part), Some("bass"));
                assert_eq!((l.by_name(part).instrument.clef, l.by_name(part).instrument.chromatic), (Clef::Bass, 0));
            }
        }
    }
    let bt = seat_by_id("bass-trombone").unwrap();
    for (lineup, part) in [("minimal", "E♭ Bass"), ("quartet", "Euphonium")] {
        let l = with_reading(lineup_by_name(lineup).unwrap(), bt, Some(part), None);
        assert_eq!((l.by_name(part).instrument.clef, l.by_name(part).instrument.chromatic), (Clef::Bass, 0), "{lineup}");
        // The other parts keep their own clef and key.
        assert_eq!(l.parts.iter().filter(|p| p.name != part).map(|p| p.instrument).collect::<Vec<_>>(),
                   lineup_by_name(lineup).unwrap().parts.iter().filter(|p| p.name != part).map(|p| p.instrument).collect::<Vec<_>>());
    }
}

#[test]
fn percussion_has_no_solo_take() {
    use brasscribe_core::instruments::{seat_lineup, PERCUSSION_SOLO};
    assert_eq!(seat_lineup("percussion", None).unwrap_err(), PERCUSSION_SOLO);
    assert!(SEATS.iter().filter(|s| !s.reads.is_empty()).all(|s| seat_lineup(s.id, None).is_ok()));
}

#[test]
fn clef_readings() {
    assert!(check_reads(Some("euphonium"), Some("bass")).is_ok());
    assert!(check_reads(None, None).is_ok());
    assert!(check_reads(Some("solo-cornet"), Some("bass")).is_err());
    assert!(check_reads(Some("bass-trombone"), Some("treble")).is_err());
    assert!(check_reads(None, Some("bass")).is_err());
}

/// The seats whose part can carry the tune: Role Melody or Solo in instruments.rs, not the bass line.
#[test]
fn tune_follows_the_roles() {
    use brasscribe_core::instruments::{lead_lineup, Role};
    let tune: Vec<&str> = SEATS.iter().filter(|s| s.tune()).map(|s| s.id).collect();
    assert_eq!(
        tune,
        [
            "soprano-cornet", "solo-cornet", "repiano-cornet", "2nd-cornet", "3rd-cornet", "flugelhorn", "solo-horn", "1st-horn",
            "2nd-horn", "1st-trombone", "2nd-trombone", "euphonium", "trumpet",
        ]
    );
    let band = brass_band();
    for s in &SEATS {
        let roles = s.own_part().instrument.roles;
        let melodic = roles.iter().any(|r| matches!(r, Role::Melody | Role::Solo));
        assert_eq!(s.tune(), melodic && s.part != band.bass && Some(s.part) != band.second_bass, "{}", s.id);
        // the same seats lead_lineup takes the tune for
        assert_eq!(s.tune(), lead_lineup(brass_band(), s.id).is_ok(), "{}", s.id);
    }
}
