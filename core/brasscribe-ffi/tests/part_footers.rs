//! The source footer on printed parts, in en and nb, on Mikkel's layers. Skips when
//! data/mikkel/repro is not in the checkout.

use std::path::{Path, PathBuf};

use brasscribe_ffi::{arrange_layers_band, part_sources, LayerMidi, LayerStems, LayersSongOptions};

fn repro() -> Option<PathBuf> {
    let root = std::env::var_os("BRASSCRIBE_REPO").map(PathBuf::from).unwrap_or_else(|| Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."));
    let d = root.join("data/mikkel/repro");
    d.join("mix.beats").exists().then_some(d)
}

#[test]
fn arranged_parts_say_so_in_the_chosen_language() {
    let Some(d) = repro() else { return };
    let m = |n: &str| std::fs::read(d.join("layers").join(n)).unwrap();
    let layers = || LayerMidi {
        solo_swiftf0: m("solo-sw.mid"),
        solo_muscriptor: m("solo-mus.mid"),
        solo_basic_pitch: m("solo-bp.mid"),
        bass: m("bass-mus.mid"),
        orchestra: m("orchestra-mus.mid"),
        drums: m("drums-mus.mid"),
    };
    let beats = std::fs::read_to_string(d.join("mix.beats")).unwrap();
    for (lang, text) in [(None, "Arranged by Brasscribe from the band&apos;s harmony."), (Some("nb"), "Arrangert av Brasscribe ut fra harmoniene i bandet.")] {
        let o = LayersSongOptions { lang: lang.map(String::from), ..Default::default() };
        let r = arrange_layers_band(layers(), LayerStems::default(), beats.clone(), "Mikkel".into(), o).unwrap();
        let sources = part_sources(r.composition_json.clone()).unwrap();
        assert_eq!(sources.len(), r.parts.len());
        for (p, s) in r.parts.iter().zip(&sources) {
            let has = p.musicxml.contains(text) || p.musicxml.contains(&text.replace("&apos;", "'"));
            assert_eq!(has, s.source == "arranged", "{} ({})", p.file_name, s.source);
        }
        assert!(sources.iter().any(|s| s.source == "arranged") && sources.iter().any(|s| s.source == "recording"));
        assert!(!r.musicxml.contains("<credit"), "the full score has no footer");
    }
    let bad = LayersSongOptions { lang: Some("de".into()), ..Default::default() };
    assert!(arrange_layers_band(layers(), LayerStems::default(), beats, "Mikkel".into(), bad).is_err());
}
