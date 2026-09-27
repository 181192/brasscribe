//! Lineups: roles, option names and the part tables every lineup must resolve in.

use brasscribe_core::instruments::{lineup_by_name, lineup_key, part_banks, Clef, LINEUP_KEYS};

#[test]
fn option_names_and_aliases() {
    assert_eq!(lineup_key("").unwrap(), "band");
    assert_eq!(lineup_key("full").unwrap(), "band");
    assert_eq!(lineup_by_name("minimal").unwrap().name, "Minimal brass");
    assert!(lineup_by_name("nonet").is_err());
}

#[test]
fn every_lineup_has_its_roles() {
    for key in LINEUP_KEYS {
        let l = lineup_by_name(key).unwrap();
        assert!(l.has(l.lead) && l.has(l.bass), "{key}");
        assert!(l.second_bass.is_none_or(|b| l.has(b)), "{key}");
    }
}

#[test]
fn a_part_name_means_one_bank_in_every_lineup() {
    let banks = part_banks();
    for key in LINEUP_KEYS {
        for p in lineup_by_name(key).unwrap().parts {
            let bank = banks.iter().find(|(n, _)| *n == p.name).map(|(_, b)| *b);
            match p.midi_bank {
                Some(b) => assert_eq!(bank, Some(b), "{key} {}", p.name),
                None if p.instrument.clef != Clef::Percussion => assert!(bank.is_some(), "{key} {}", p.name),
                None => {}
            }
        }
    }
}
