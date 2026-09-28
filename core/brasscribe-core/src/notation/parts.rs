//! Individual parts from a written score: one MusicXML document per part.
//!
//! Per part: only that part's <score-part> and <part>; tempo marks and
//! rehearsal letters copied from the top part; runs of two or more empty bars
//! marked as one multi-bar rest; a part with no notes titled "(Tacet)".

use super::xml::El;

pub const MIN_MULTI_REST: usize = 2;

fn find<'a>(el: &'a El, name: &str) -> Option<&'a El> {
    el.children.iter().find(|c| c.name == name)
}

fn find_path<'a>(el: &'a El, path: &[&str]) -> Option<&'a El> {
    match path.split_first() {
        None => Some(el),
        Some((first, rest)) => el.children.iter().filter(|c| c.name == *first).find_map(|c| find_path(c, rest)),
    }
}

fn iter_named<'a>(el: &'a El, name: &str, out: &mut Vec<&'a El>) {
    for c in &el.children {
        if c.name == name {
            out.push(c);
        }
        iter_named(c, name, out);
    }
}

/// No note that is not a rest.
fn empty(measure: &El) -> bool {
    let mut notes = Vec::new();
    iter_named(measure, "note", &mut notes);
    !notes.iter().any(|n| find(n, "rest").is_none())
}

fn is_tempo_or_letter(d: &El) -> bool {
    find_path(d, &["direction-type", "metronome"]).is_some()
        || find_path(d, &["direction-type", "rehearsal"]).is_some()
        || find(d, "sound").is_some_and(|s| s.attrs.iter().any(|(k, v)| k == "tempo" && !v.is_empty()))
}

/// A multi-bar rest must not swallow a rehearsal letter, tempo or key change.
fn breaks_rest(m: &El) -> bool {
    find_path(m, &["direction", "direction-type", "rehearsal"]).is_some()
        || find_path(m, &["direction", "direction-type", "metronome"]).is_some()
        || find_path(m, &["attributes", "key"]).is_some()
}

fn mark_multi_rests(part: &mut El) {
    let n = part.children.len();
    let is_measure: Vec<bool> = part.children.iter().map(|c| c.name == "measure").collect();
    let idx: Vec<usize> = (0..n).filter(|&i| is_measure[i]).collect();
    let mut i = 0;
    while i < idx.len() {
        if !empty(&part.children[idx[i]]) {
            i += 1;
            continue;
        }
        let mut j = i;
        while j + 1 < idx.len() {
            let m = &part.children[idx[j + 1]];
            if empty(m) && find_path(m, &["attributes", "time"]).is_none() && !breaks_rest(m) {
                j += 1;
            } else {
                break;
            }
        }
        let count = j - i + 1;
        if count >= MIN_MULTI_REST {
            let m = &mut part.children[idx[i]];
            let style = El::new("measure-style").child(El::text("multiple-rest", count.to_string()));
            match m.children.iter().position(|c| c.name == "attributes") {
                Some(a) => m.children[a].push(style),
                None => m.children.insert(0, El::new("attributes").child(style)),
            }
        }
        i = j + 1;
    }
}

fn slug(name: &str) -> String {
    let s = name.replace('♭', "b").replace('♯', "#");
    let mut out = String::new();
    let mut dash = false;
    for c in s.chars() {
        if c.is_ascii_alphanumeric() {
            out.push(c);
            dash = false;
        } else if !dash {
            out.push('-');
            dash = true;
        }
    }
    out.trim_matches('-').to_string()
}

/// (file name, document) per part, in score order: "<nn>-<part name>.musicxml".
pub fn split_parts(root: &El) -> Vec<(String, El)> {
    split_parts_with_footers(root, &[])
}

/// A page-one footer credit (MusicXML `rights`, which MuseScore prints at the foot of the page),
/// placed before the part list.
fn add_footer(doc: &mut El, text: &str) {
    let credit = El::new("credit")
        .attr("page", "1")
        .child(El::text("credit-type", "rights"))
        .child(El::text("credit-words", text).attr("justify", "center").attr("valign", "bottom").attr("font-size", "8"));
    let at = doc.children.iter().position(|c| c.name == "part-list").unwrap_or(doc.children.len());
    doc.children.insert(at, credit);
}

/// [`split_parts`], with a footer on each part named in `footers` ((part name, text)).
pub fn split_parts_with_footers(root: &El, footers: &[(String, String)]) -> Vec<(String, El)> {
    let parts: Vec<&El> = root.children.iter().filter(|c| c.name == "part").collect();
    let score_parts: Vec<&El> = find(root, "part-list").map(|pl| pl.children.iter().filter(|c| c.name == "score-part").collect()).unwrap_or_default();
    let id_of = |e: &El| e.attrs.iter().find(|(k, _)| k == "id").map(|(_, v)| v.clone()).unwrap_or_default();
    // tempo marks and letters of the top part, per measure number
    let mut tempos: Vec<(String, Vec<El>)> = Vec::new();
    if let Some(top) = parts.first() {
        let mut measures = Vec::new();
        iter_named(top, "measure", &mut measures);
        for m in measures {
            let num = m.attrs.iter().find(|(k, _)| k == "number").map(|(_, v)| v.clone()).unwrap_or_default();
            for d in m.children.iter().filter(|c| c.name == "direction") {
                if is_tempo_or_letter(d) {
                    match tempos.iter_mut().find(|(n, _)| *n == num) {
                        Some(e) => e.1.push(d.clone()),
                        None => tempos.push((num.clone(), vec![d.clone()])),
                    }
                }
            }
        }
    }
    let mut out = Vec::new();
    for (k, part) in parts.iter().enumerate() {
        let k = k + 1;
        let pid = id_of(part);
        let name = score_parts
            .iter()
            .find(|sp| id_of(sp) == pid)
            .and_then(|sp| find(sp, "part-name"))
            .and_then(|n| n.text.clone())
            .map(|t| t.trim().to_string())
            .unwrap_or_else(|| pid.clone());
        let mut doc = root.clone();
        doc.children.retain(|c| c.name != "part" || id_of(c) == pid);
        if let Some(pl) = doc.children.iter_mut().find(|c| c.name == "part-list") {
            pl.children.retain(|c| c.name == "score-part" && id_of(c) == pid);
        }
        let mine_idx = doc.children.iter().position(|c| c.name == "part").unwrap();
        if k > 1 {
            let mine = &mut doc.children[mine_idx];
            for m in mine.children.iter_mut().filter(|c| c.name == "measure") {
                let num = m.attrs.iter().find(|(k, _)| k == "number").map(|(_, v)| v.clone()).unwrap_or_default();
                if let Some((_, ds)) = tempos.iter().find(|(n, _)| *n == num) {
                    for d in ds {
                        let at = if m.children.iter().any(|c| c.name == "attributes") { 1 } else { 0 };
                        let at = at.min(m.children.len());
                        m.children.insert(at, d.clone());
                    }
                }
            }
        }
        let tacet = doc.children[mine_idx].children.iter().filter(|c| c.name == "measure").all(empty);
        let label = if tacet { format!("{name} (Tacet)") } else { name.clone() };
        for (parent, child) in [(Some("work"), "work-title"), (None, "movement-title")] {
            let target = match parent {
                Some(p) => doc.children.iter_mut().find(|c| c.name == p).and_then(|w| w.children.iter_mut().find(|c| c.name == child)),
                None => doc.children.iter_mut().find(|c| c.name == child),
            };
            if let Some(el) = target {
                el.text = Some(match &el.text {
                    Some(t) if !t.is_empty() => format!("{t} — {label}"),
                    _ => label.clone(),
                });
            }
        }
        mark_multi_rests(&mut doc.children[mine_idx]);
        if let Some((_, text)) = footers.iter().find(|(p, _)| *p == name) {
            add_footer(&mut doc, text);
        }
        out.push((format!("{k:02}-{}.musicxml", slug(&name)), doc));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn score() -> El {
        let part = |id: &str| El::new("part").attr("id", id).child(El::new("measure").attr("number", "1"));
        let sp = |id: &str, name: &str| El::new("score-part").attr("id", id).child(El::text("part-name", name));
        El::new("score-partwise")
            .child(El::new("work").child(El::text("work-title", "T")))
            .child(El::new("part-list").child(sp("P1", "Solo Cornet")).child(sp("P2", "2nd Cornet")))
            .child(part("P1"))
            .child(part("P2"))
    }

    #[test]
    fn footer_only_on_the_parts_named() {
        let footers = [("2nd Cornet".to_string(), "Arranged.".to_string())];
        let parts = split_parts_with_footers(&score(), &footers);
        let credits = |d: &El| d.children.iter().filter(|c| c.name == "credit").cloned().collect::<Vec<_>>();
        assert!(credits(&parts[0].1).is_empty());
        let c = credits(&parts[1].1);
        assert_eq!(c.len(), 1);
        assert_eq!(find(&c[0], "credit-type").and_then(|e| e.text.as_deref()), Some("rights"));
        assert_eq!(find(&c[0], "credit-words").and_then(|e| e.text.as_deref()), Some("Arranged."));
        let names: Vec<&str> = parts[1].1.children.iter().map(|c| c.name.as_str()).collect();
        assert_eq!(names, ["work", "credit", "part-list", "part"]);
        // no footers: the parts as split_parts writes them
        assert!(split_parts(&score()).iter().all(|(_, d)| credits(d).is_empty()));
    }
}
