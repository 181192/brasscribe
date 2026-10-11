//! The talking score says the band's Norwegian names because the band hands them to the core.

use scribe_core::talking_score::{build, part_lines, to_text, Names, ScoreNames, Settings};
use target_brass::instruments::brass_band;
use target_brass::names::{instrument_nb, nb_part_name, BandNames};

const SCORE: &str = r#"<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><work><work-title>T</work-title></work>
<part-list><score-part id="P1"><part-name>Solo Horn</part-name><score-instrument id="I1"><instrument-name>Tenor Horn in E♭</instrument-name></score-instrument></score-part></part-list>
<part id="P1">
<measure number="1"><attributes><divisions>2</divisions><key><fifths>3</fifths></key><time><beats>4</beats><beat-type>4</beat-type></time><transpose><diatonic>-5</diatonic><chromatic>-9</chromatic></transpose></attributes>
<note><pitch><step>G</step><octave>4</octave></pitch><duration>8</duration><voice>1</voice><type>whole</type></note></measure>
</part></score-partwise>"#;

#[test]
fn the_band_names_its_parts_and_instruments_in_the_document() {
    let doc = build(SCORE, None, &BandNames).unwrap();
    let part = &doc["parts"][0];
    assert_eq!((part["name"].as_str(), part["name_nb"].as_str()), (Some("Solo Horn"), Some("Solo althorn")));
    assert_eq!((part["instrument"].as_str(), part["instrument_nb"].as_str()), (Some("Tenor Horn in E♭"), Some("althorn i Ess")));
    let nb = Settings { lang: "nb".into(), ..Default::default() };
    assert!(to_text(&doc, &nb, None).contains("Solo althorn"));
    assert!(!to_text(&doc, &Settings::default(), None).contains("althorn"));
}

#[test]
fn without_a_target_the_score_s_own_names_are_read() {
    let doc = build(SCORE, None, &ScoreNames).unwrap();
    let part = &doc["parts"][0];
    assert_eq!(part["name_nb"], part["name"]);
    assert_eq!(part["instrument_nb"], part["instrument"]);
    // The notes are read the same, whoever names the parts.
    let nb = Settings { lang: "nb".into(), ..Default::default() };
    assert_eq!(part_lines(&doc, 0, &nb), part_lines(&build(SCORE, None, &BandNames).unwrap(), 0, &nb));
}

#[test]
fn every_part_and_instrument_of_the_band_has_a_norwegian_name() {
    for part in &brass_band().parts {
        assert_ne!(nb_part_name(part.name), part.name, "{}", part.name);
        assert_eq!(BandNames.part(part.name, "nb").as_deref(), Some(nb_part_name(part.name)));
        assert_eq!(BandNames.instrument(part.instrument.name, "nb"), Some(instrument_nb(part.instrument.name)));
        assert_ne!(instrument_nb(part.instrument.name), part.instrument.name, "{}", part.instrument.name);
    }
    // The band has no names in a language it does not speak: the score's own are used.
    assert_eq!(BandNames.part("Solo Cornet", "sv"), None);
    assert_eq!(BandNames.instrument("Cornet in B♭", "sv"), None);
}
