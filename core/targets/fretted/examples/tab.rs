//! Tablature for a JSON request on standard input, as MusicXML on standard output:
//! `cargo run -p target-fretted --example tab < request.json > tab.musicxml`.

use std::io::Read;

fn main() {
    let mut request = String::new();
    if let Err(e) = std::io::stdin().read_to_string(&mut request) {
        eprintln!("cannot read the request: {e}");
        std::process::exit(1);
    }
    match target_fretted::json::tab_musicxml_json(&request) {
        Ok(xml) => print!("{xml}"),
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1);
        }
    }
}
