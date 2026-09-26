"""Build App/Localizable.xcstrings (English source, Norwegian bokmål) from the keys Xcode
extracted into *.stringsdata during the last build, plus the bokmål table below.

Usage: python3 scripts/make-string-catalog.py build/DerivedData/Build/Intermediates.noindex
Keys without a translation are listed on stderr and left for review in Xcode.
"""

import glob
import json
import sys

NB = {
    "%lld": "%lld",
    "%lld %%": "%lld %%",
    "%lld percent": "%lld prosent",
    "%lld uncertain notes": "%lld usikre noter",
    "A brass band playing together.": "Et brassband som spiller sammen.",
    "A single player, for example you practising.": "Én utøver, for eksempel deg når du øver.",
    "A soloist in front of an orchestra or band.": "En solist foran et orkester eller korps.",
    "About": "Om",
    "About %lld min left": "Omtrent %lld min igjen",
    "Address": "Adresse",
    "All parts": "Alle stemmer",
    "Arranging for brass band": "Arrangerer for brassband",
    "Audio of the score": "Lyd av partituret",
    "Back": "Tilbake",
    "Bar %lld, beat %lld": "Takt %lld, slag %lld",
    "Bars": "Takter",
    "Bars %lld–%lld: ad lib (free time)": "Takt %lld–%lld: ad lib (fritt tempo)",
    "Bars with uncertain notes": "Takter med usikre noter",
    "Baseline sounds: MuseScore General SoundFont (MIT), downloaded separately.": "Grunnlyder: MuseScore General SoundFont (MIT), lastes ned separat.",
    "Braille music (BRF)": "Punktskriftnoter (BRF)",
    "Brass band": "Brassband",
    "Brasscribe Play": "Brasscribe Play",
    "Cancel": "Avbryt",
    "Cancelled.": "Avbrutt.",
    "Check connection": "Sjekk tilkoblingen",
    "Concert": "Klingende",
    "Concert hall and seating": "Konsertsal og plassering",
    "Connected to Brasscribe %@ (%@).": "Koblet til Brasscribe %@ (%@).",
    "Couldn't open the score": "Kunne ikke åpne partituret",
    "Couldn't open this file.": "Kunne ikke åpne filen.",
    "Count-in": "Inntelling",
    "Count-in %lld": "Inntelling %lld",
    "Count-in: C · Metronome: M · Play along: A": "Inntelling: C · Metronom: M · Spill med: A",
    "Delete": "Slett",
    "Difficulty": "Vanskelighetsgrad",
    "Done": "Ferdig",
    "Double-tap to move playback here.": "Dobbelttrykk for å flytte avspillingen hit.",
    "Easier": "Enklere",
    "Engraving the score": "Setter partituret",
    "Engraving the score…": "Setter partituret …",
    "Estimating time…": "Beregner tid …",
    "Everything playing on this Mac": "All lyd som spilles på denne Macen",
    "Export": "Eksporter",
    "Faithful": "Tro mot opptaket",
    "Faster": "Raskere",
    "Finding the beat": "Finner pulsen",
    "Free time": "Fritt tempo",
    "Full brass band": "Fullt brassband",
    "Getting the recording ready": "Gjør opptaket klart",
    "Import audio or video": "Importer lyd eller video",
    "Input level": "Inngangsnivå",
    "Keep the original key": "Behold originaltonearten",
    "Key (concert)": "Toneart (klingende)",
    "Less than a minute left": "Under ett minutt igjen",
    "Lineup": "Besetning",
    "Lineup, difficulty and key are sent to your computer; older versions of Brasscribe may ignore them.": "Besetning, vanskelighetsgrad og toneart sendes til datamaskinen din. Eldre versjoner av Brasscribe kan overse dem.",
    "Links to streaming sites can't be downloaded. Play the music and record it, or import a file you have.": "Lenker til strømmetjenester kan ikke lastes ned. Spill av musikken og ta den opp, eller importer en fil du har.",
    "Listen to the original": "Hør originalen",
    "Listen to uncertain bars": "Hør på usikre takter",
    "Loop": "Gjenta",
    "Loop current bar: L": "Gjenta denne takten: L",
    "Loop from bar": "Gjenta fra takt",
    "Loop this bar": "Gjenta denne takten",
    "Loop to bar": "Gjenta til takt",
    "MIDI": "MIDI",
    "Making the audio": "Lager lyden",
    "Metronome": "Metronom",
    "Microphone access is off. Turn it on in Settings to record.": "Mikrofontilgang er slått av. Slå den på i Innstillinger for å ta opp.",
    "MusicXML (score and parts)": "MusicXML (partitur og stemmer)",
    "Mute": "Demp",
    "Mute %@": "Demp %@",
    "Mutes your part so you can play it.": "Demper stemmen din så du kan spille den selv.",
    "My part": "Min stemme",
    "New score": "Nytt partitur",
    "Next bar": "Neste takt",
    "Notation engraved with Verovio (LGPL-3.0), included as an unmodified dynamic framework.": "Notene settes med Verovio (LGPL-3.0), som følger med som et uendret dynamisk rammeverk.",
    "Nothing was heard. Either nothing was playing, recording permission was refused, or the app plays protected (DRM) audio, which the system does not let anyone record.": "Ingenting ble hørt. Enten ble ingenting spilt av, tillatelsen til opptak ble avslått, eller appen spiller beskyttet lyd (DRM), som systemet ikke lar noen ta opp.",
    "OK": "OK",
    "One instrument": "Ett instrument",
    "Only silence was recorded": "Bare stillhet ble tatt opp",
    "Open score": "Åpne partituret",
    "Orchestra or band with a soloist": "Orkester eller korps med solist",
    "Original": "Original",
    "Original / score: O": "Original / partitur: O",
    "Original recording": "Originalopptak",
    "PDF": "PDF",
    "Pair": "Koble til",
    "Paired.": "Tilkoblet.",
    "Pairing code": "Tilkoblingskode",
    "Part": "Stemme",
    "Parts": "Stemmer",
    "Parts and sound": "Stemmer og lyd",
    "Pause": "Pause",
    "Pitch": "Tonehøyde",
    "Play": "Spill",
    "Play %@": "Spill %@",
    "Play along": "Spill med",
    "Play along (mute my part)": "Spill med (demp min stemme)",
    "Play or pause: Space": "Spill eller pause: mellomrom",
    "Play this bar": "Spill denne takten",
    "Play when you're ready.": "Spill når du er klar.",
    "Playback": "Avspilling",
    "Playback problem": "Problem med avspillingen",
    "Pop or rock": "Pop eller rock",
    "Previous / next bar: ← / →": "Forrige / neste takt: ← / →",
    "Previous bar": "Forrige takt",
    "Protected (DRM) music and video can't be recorded or imported. Play the piece yourself, or use a file you own without copy protection.": "Beskyttet musikk og video (DRM) kan ikke tas opp eller importeres. Spill stykket selv, eller bruk en fil du eier uten kopibeskyttelse.",
    "Protected (DRM) playback, as in some streaming apps, can't be recorded; you'll hear it but the recording stays silent.": "Beskyttet avspilling (DRM), som i noen strømmeapper, kan ikke tas opp. Du hører lyden, men opptaket blir stille.",
    "Record": "Ta opp",
    "Record from": "Ta opp fra",
    "Record sound playing on this Mac": "Ta opp lyd som spilles på denne Macen",
    "Record this Mac": "Ta opp fra denne Macen",
    "Record with the microphone": "Ta opp med mikrofonen",
    "Recorded": "Tatt opp",
    "Recorded %lld seconds": "%lld sekunder tatt opp",
    "Recording %@": "Opptak %@",
    "Recording…": "Tar opp …",
    "Review": "Gjennomgang",
    "Score": "Partitur",
    "Score pages": "Partitursider",
    "Scores": "Partiturer",
    "Sending the recording": "Sender opptaket",
    "Separating the instruments": "Skiller instrumentene fra hverandre",
    "Settings": "Innstillinger",
    "Show": "Vis",
    "Slower": "Saktere",
    "Slower / faster: [ / ]": "Saktere / raskere: [ / ]",
    "Small band": "Lite korps",
    "Solo": "Solo",
    "Solo %@": "Solo %@",
    "Sound": "Lyd",
    "Sounds": "Lyder",
    "Speed": "Tempo",
    "Standard": "Standard",
    "Start Brasscribe on your computer with “brasscribe serve --host 0.0.0.0” and type the six-digit code it shows.": "Start Brasscribe på datamaskinen med «brasscribe serve --host 0.0.0.0» og skriv inn den sekssifrede koden som vises.",
    "Start recording": "Start opptak",
    "Stop": "Stopp",
    "Switch between the score and the original recording at the same place.": "Bytt mellom partituret og originalopptaket på samme sted.",
    "Talking score": "Talende partitur",
    "Talking score (text)": "Talende partitur (tekst)",
    "The demo recording is not available.": "Demo-opptaket er ikke tilgjengelig.",
    "The notation engine could not start.": "Notesettingen kunne ikke starte.",
    "The performer did not keep a steady beat here, so rhythms are approximate.": "Utøveren holdt ikke jevn puls her, så rytmene er omtrentlige.",
    "This decides how the music is taken apart. Brasscribe never guesses.": "Dette avgjør hvordan musikken tas fra hverandre. Brasscribe gjetter aldri.",
    "This is not a score Brasscribe can read.": "Dette er ikke et partitur Brasscribe kan lese.",
    "This recording is copy-protected": "Dette opptaket er kopibeskyttet",
    "Transcribe": "Transkriber",
    "Transcribing on %@": "Transkriberer på %@",
    "Transpose %@%lld semitones": "Transponer %@%lld halvtoner",
    "Try the demo (Mikkel)": "Prøv demoen (Mikkel)",
    "Uncertain notes": "Usikre noter",
    "Uncertain notes are marked with an open diamond and an orange colour.": "Usikre noter er merket med en åpen rute og oransje farge.",
    "Use the demo instead of a computer": "Bruk demoen i stedet for en datamaskin",
    "Video of the performance, synced to the score": "Video av framføringen, synkronisert med partituret",
    "Vocals or lead with bass, drums and keys.": "Sang eller melodi med bass, trommer og tangenter.",
    "What is this?": "Hva er dette?",
    "Working": "Jobber",
    "Writing down the notes": "Skriver ned notene",
    "Written": "Skrevet",
    "Your computer": "Datamaskinen din",
    "Your scores appear here.": "Partiturene dine vises her.",
    "Zoom %lld percent": "Zoom %lld prosent",
    "Zoom in": "Zoom inn",
    "Arrange again on this device": "Arranger på nytt på denne enheten",
    "Couldn't arrange on this device.": "Kunne ikke arrangere på denne enheten.",
    "Zoom out": "Zoom ut",
    "from %lld": "fra %lld",
    "to %lld": "til %lld",
}

INFO_NB = {
    "CFBundleDisplayName": "Brasscribe Play",
    "NSMicrophoneUsageDescription": "Brasscribe Play tar opp spillingen din for å gjøre den om til noter.",
    "NSAudioCaptureUsageDescription": "Brasscribe Play tar opp lyden som spilles på denne Macen for å gjøre den om til noter.",
    "NSLocalNetworkUsageDescription": "Brasscribe Play snakker med Brasscribe på din egen datamaskin for å transkribere opptak.",
}


def entry(nb: str) -> dict:
    return {"localizations": {"nb": {"stringUnit": {"state": "translated", "value": nb}}}}


def main(root: str) -> None:
    keys = set()
    for f in glob.glob(root + "/**/*.stringsdata", recursive=True):
        if "BrasscribePlay_" not in f or "Tests" in f:
            continue
        for table in json.load(open(f)).get("tables", {}).values():
            keys.update(e["key"] for e in table)
    keys.discard("")
    strings = {}
    missing = []
    for k in sorted(keys):
        if k in NB:
            strings[k] = entry(NB[k])
        else:
            strings[k] = {}
            missing.append(k)
    catalog = {"sourceLanguage": "en", "strings": strings, "version": "1.0"}
    with open("App/Localizable.xcstrings", "w") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False, sort_keys=True)
    info = {"sourceLanguage": "en", "version": "1.0",
            "strings": {k: entry(v) for k, v in INFO_NB.items()}}
    with open("App/InfoPlist.xcstrings", "w") as f:
        json.dump(info, f, indent=2, ensure_ascii=False, sort_keys=True)
    print(f"{len(strings)} strings, {len(missing)} without Norwegian", file=sys.stderr)
    for k in missing:
        print("  missing:", k, file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1])
