//! What the band's parts and instruments are called in Norwegian.
//!
//! The shared core reads a score aloud without knowing what plays it (`scribe_core::talking_score`).
//! The names it says in a language other than the score's own are the target's, handed over through
//! [`Names`]. The tables are the reference's (`talking_score.py`: `NB_PART_NAMES`, `instrument_nb`).

use scribe_core::talking_score::Names;

/// A part's name in Norwegian; a name the band does not have comes back unchanged.
pub fn nb_part_name(name: &str) -> &str {
    match name {
        "Soprano Cornet" => "Sopran-kornett",
        "Solo Cornet" => "Solokornett",
        "1st Cornet" => "1. kornett",
        "Tenor Horn" => "Althorn",
        "Repiano Cornet" => "Repiano-kornett",
        "2nd Cornet" => "2. kornett",
        "3rd Cornet" => "3. kornett",
        "Flugelhorn" => "Flygelhorn",
        "Solo Horn" => "Solo althorn",
        "1st Horn" => "1. althorn",
        "2nd Horn" => "2. althorn",
        "1st Baritone" => "1. baryton",
        "2nd Baritone" => "2. baryton",
        "1st Trombone" => "1. trombone",
        "2nd Trombone" => "2. trombone",
        "Bass Trombone" => "Basstrombone",
        "Euphonium" => "Eufonium",
        "E♭ Bass" => "Ess-bass",
        "B♭ Bass" => "B-bass",
        "Percussion" => "Slagverk",
        "Trumpet" => "Trompet",
        other => other,
    }
}

/// An instrument's name in Norwegian as it is said inside a sentence ("Cornet in B♭" -> «kornett i B»).
pub fn instrument_nb(en: &str) -> String {
    let mut s = en.to_string();
    for (a, b) in [
        ("Soprano Cornet", "sopran-kornett"),
        ("Cornet", "kornett"),
        ("Trumpet", "trompet"),
        ("Flugelhorn", "flygelhorn"),
        ("Tenor Horn", "althorn"),
        ("Horn", "althorn"),
        ("Baritone", "baryton"),
        ("Euphonium", "eufonium"),
        ("Bass Trombone", "basstrombone"),
        ("Drum Kit", "trommesett"),
        (" in B♭", " i B"),
        (" in E♭", " i Ess"),
        (" in C", " i C"),
    ] {
        s = s.replace(a, b);
    }
    let mut c = s.chars();
    match c.next() {
        None => String::new(),
        Some(f) => f.to_lowercase().collect::<String>() + c.as_str(),
    }
}

/// The band's names for the talking score. Norwegian is the one language it has them in beside English.
pub struct BandNames;

impl Names for BandNames {
    fn part(&self, name: &str, lang: &str) -> Option<String> {
        (lang == "nb").then(|| nb_part_name(name).to_string())
    }

    fn instrument(&self, name: &str, lang: &str) -> Option<String> {
        (lang == "nb").then(|| instrument_nb(name))
    }
}
