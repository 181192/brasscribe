//! seats, seat_part, part_sources and the seat options over UniFFI and the C ABI.

use std::ffi::{CStr, CString};
use std::os::raw::c_char;

use brasscribe_ffi::{arrange_musicxml_with, part_name_nb, part_sources, seat_part, seats, ArrangeOptions, SeatPart};

/// A solo take: only the solo layer has notes (a baritone line, some of it below E3).
const SOLO: &str = r#"{"title": "S", "voices": [
  {"id": "solo", "role": "melody", "layer": "solo", "notes": [{"pitch": 43, "start": 0, "dur": 48}, {"pitch": 50, "start": 48, "dur": 48}]},
  {"id": "bass", "role": "bass", "layer": "bass", "notes": []}],
 "meters": [{"tick": 0, "beats": 4}], "keys": [{"tick": 0, "fifths": 0}],
 "arrangement": {"lineup": "minimal", "difficulty": "faithful", "transpose_semitones": 0, "seat": "1st-baritone", "lead": "seat"}}"#;

fn parts(xml: &str) -> Vec<String> {
    xml.split("<part-name>").skip(1).map(|s| s.split('<').next().unwrap().to_string()).collect()
}

fn c_call(f: impl FnOnce(*mut *mut c_char, *mut *mut c_char) -> i32) -> Result<String, String> {
    let (mut out, mut err): (*mut c_char, *mut c_char) = (std::ptr::null_mut(), std::ptr::null_mut());
    let code = f(&mut out, &mut err);
    let take = |p: *mut c_char| {
        let s = unsafe { CStr::from_ptr(p) }.to_string_lossy().into_owned();
        unsafe { brasscribe_ffi::c_api::bc_string_free(p) };
        s
    };
    if code == 0 {
        Ok(take(out))
    } else {
        Err(take(err))
    }
}

#[test]
fn seats_carry_the_core_names() {
    let s = seats();
    assert_eq!(s.len(), 19);
    let tpt = s.iter().find(|x| x.id == "trumpet").unwrap();
    assert_eq!((tpt.name.as_str(), tpt.nb_name.as_str(), tpt.instrument.as_str()), ("Trumpet", "Trompet", "bb-trumpet"));
    assert!(tpt.tune);
    let horn = s.iter().find(|x| x.id == "solo-horn").unwrap();
    assert_eq!((horn.name.as_str(), horn.nb_name.as_str(), horn.clef.as_str()), ("Solo Horn", "Solo althorn", "treble"));
    assert_eq!(s.iter().find(|x| x.id == "bass-trombone").unwrap().reads, vec!["bass"]);
    let json = c_call(|o, e| unsafe { brasscribe_ffi::c_api::bc_seats(o, e) }).unwrap();
    assert!(json.contains(r#""nb_name":"Sopran-kornett""#));
    // tune: the core's roles, over UniFFI and the C ABI alike
    let core = target_brass::instruments::SEATS.iter().map(|x| (x.id.to_string(), x.tune())).collect::<Vec<_>>();
    assert_eq!(s.iter().map(|x| (x.id.clone(), x.tune)).collect::<Vec<_>>(), core);
    assert!(horn.tune && !s.iter().find(|x| x.id == "eb-bass").unwrap().tune);
    let rows: serde_json::Value = serde_json::from_str(&json).unwrap();
    let c: Vec<(String, bool)> = rows.as_array().unwrap().iter().map(|r| (r["id"].as_str().unwrap().into(), r["tune"].as_bool().unwrap())).collect();
    assert_eq!(c, core);
}

#[test]
fn seat_part_spot_checks() {
    assert_eq!(seat_part("minimal".into(), "1st-baritone".into()).unwrap(), SeatPart { part: Some("Euphonium".into()), exact: false, same_key: true, takes: None });
    assert_eq!(seat_part("quartet".into(), "eb-bass".into()).unwrap(), SeatPart { part: Some("Euphonium".into()), exact: false, same_key: false, takes: None });
    assert_eq!(seat_part("band".into(), "2nd-cornet".into()).unwrap(), SeatPart { part: Some("2nd Cornet".into()), exact: true, same_key: true, takes: None });
    assert_eq!(
        seat_part("band".into(), "trumpet".into()).unwrap(),
        SeatPart { part: Some("Trumpet".into()), exact: false, same_key: true, takes: Some("Solo Cornet".into()) }
    );
    assert_eq!(seat_part("quartet".into(), "trumpet".into()).unwrap().part.as_deref(), Some("1st Cornet"));
    assert!(seat_part("band".into(), "tuba".into()).is_err());
    let (l, s) = (CString::new("quartet").unwrap(), CString::new("percussion").unwrap());
    let json = c_call(|o, e| unsafe { brasscribe_ffi::c_api::bc_seat_part(l.as_ptr(), s.as_ptr(), o, e) }).unwrap();
    assert_eq!(json, r#"{"part":null,"exact":false,"same_key":false,"takes":null}"#);
    let (l, s) = (CString::new("band").unwrap(), CString::new("trumpet").unwrap());
    let json = c_call(|o, e| unsafe { brasscribe_ffi::c_api::bc_seat_part(l.as_ptr(), s.as_ptr(), o, e) }).unwrap();
    assert_eq!(json, r#"{"part":"Trumpet","exact":false,"same_key":true,"takes":"Solo Cornet"}"#);
}

#[test]
fn a_solo_take_for_a_seat_is_one_part() {
    let src = part_sources(SOLO.into()).unwrap();
    assert_eq!(src.len(), 1);
    assert_eq!((src[0].part.as_str(), src[0].source.as_str()), ("1st Baritone", "your-recording"));
    let o = ArrangeOptions { lineup: "minimal".into(), seat: Some("1st-baritone".into()), reads: Some("bass".into()), ..Default::default() };
    let xml = arrange_musicxml_with(SOLO.into(), o).unwrap();
    assert_eq!(parts(&xml), ["1st Baritone"]);
    assert!(xml.contains("<sign>F</sign>") && !xml.contains("<transpose>"));
    let json = CString::new(SOLO).unwrap();
    let rows = c_call(|o, e| unsafe { brasscribe_ffi::c_api::bc_part_sources(json.as_ptr(), o, e) }).unwrap();
    assert_eq!(rows, r#"[{"part":"1st Baritone","source":"your-recording"}]"#);
}

#[test]
fn seat_options_are_checked() {
    let bad = |o: ArrangeOptions| arrange_musicxml_with(SOLO.into(), o).is_err();
    // A drummer's solo take is no drum part: refused, not drawn as hits.
    let e = arrange_musicxml_with(SOLO.into(), ArrangeOptions { lineup: "minimal".into(), seat: Some("percussion".into()), ..Default::default() });
    assert!(e.unwrap_err().to_string().contains(target_brass::instruments::PERCUSSION_SOLO));
    assert!(bad(ArrangeOptions { seat: Some("tuba".into()), ..Default::default() }));
    assert!(bad(ArrangeOptions { reads: Some("bass".into()), ..Default::default() }));
    assert!(bad(ArrangeOptions { lead: Some("seat".into()), ..Default::default() }));
    assert!(bad(ArrangeOptions { seat: Some("solo-cornet".into()), reads: Some("bass".into()), ..Default::default() }));
}

#[test]
fn part_names_in_norwegian() {
    assert_eq!(part_name_nb("Solo Horn".into()), "Solo althorn");
    assert_eq!(part_name_nb("1st Cornet".into()), "1. kornett");
    assert_eq!(part_name_nb("Tenor Horn".into()), "Althorn");
    assert_eq!(part_name_nb("Strings".into()), "Strings");
    // every seat's nb name is the same table
    for s in seats() {
        assert_eq!(part_name_nb(s.name.clone()), s.nb_name);
    }
    let n = CString::new("E♭ Bass").unwrap();
    assert_eq!(c_call(|o, e| unsafe { brasscribe_ffi::c_api::bc_part_name_nb(n.as_ptr(), o, e) }).unwrap(), "Ess-bass");
}
