"""Build App/Localizable.xcstrings (English source, Norwegian bokmål) from the keys Xcode extracted into
*.stringsdata during the last build, plus the bokmål below (design/server-app.md §10, written, not
translated).

Usage: python3 scripts/make-strings.py build/DerivedData/Build/Intermediates.noindex
Keys without Norwegian are listed on stderr, and the script exits 1 so a gap can't slip through.
"""

import glob
import json
import sys

NB = {
    " dot ": " punktum ",
    "%@ is paired.": "%@ er koblet til.",
    "%@ keeps the recording and can send it again.": "%@ beholder opptaket og kan sende det på nytt.",
    "%@ wants to use this computer.": "%@ vil bruke denne datamaskinen.",
    "%@: %@ · %@ · paired %@": "%@: %@ · %@ · sammenkoblet %@",
    "%lld": "%lld",
    "%lld GB free": "%lld GB ledig",
    "%lld GB free. Brasscribe needs 3 GB to make a score.": "%lld GB ledig. Brasscribe trenger 3 GB for å lage et partitur.",
    "%lld connected now · %lld paired": "%lld tilkoblet nå · %lld sammenkoblet",
    "%lld more waiting": "%lld til venter",
    "%lld%%": "%lld %%",
    "%lld%% · about %lld min left": "%lld %% · omtrent %lld min igjen",
    "1. Sign in and choose **Agree** on the MuScriptor page.": "1. Logg inn og velg **Agree** på MuScriptor-siden.",
    "2. Come back here. Brasscribe downloads it for you.": "2. Kom tilbake hit. Brasscribe laster den ned for deg.",
    "About Brasscribe Bandroom": "Om Brasscribe Bandroom",
    "Accept one licence": "Godta én lisens",
    "Access key from Hugging Face": "Tilgangsnøkkel fra Hugging Face",
    "Address": "Adresse",
    "Allow": "Godkjenn",
    "Allow %@?": "Godkjenne %@?",
    "Almost full": "Nesten fullt",
    "Another program on this computer is in the way.": "Et annet program på denne datamaskinen står i veien.",
    "Arranging for brass band": "Arrangerer for brassband",
    "Back": "Tilbake",
    "Back in about a minute. Phones reconnect by themselves.": "Tilbake om et minutt. Telefonene kobler seg til igjen selv.",
    "Band writer (MuScriptor)": "Bandskriver (MuScriptor)",
    "Beat finder": "Taktfinner",
    "Brasscribe can't start": "Brasscribe kan ikke starte",
    "Brasscribe does the heavy work here, so your phones and tablets can make scores for the whole band. Recordings stay on your own devices.":
        "Brasscribe gjør det tunge arbeidet her, så telefoner og nettbrett kan lage partitur for hele bandet. Opptakene blir på dine egne enheter.",
    "Brasscribe is ready": "Brasscribe er klar",
    "Brasscribe isn't running. Start it from the menu bar, then pair.": "Brasscribe kjører ikke. Start den fra menylinjen, og koble til etterpå.",
    "Brasscribe needs attention: %@": "Brasscribe må sjekkes: %@",
    "Brasscribe on %@": "Brasscribe på %@",
    "Brasscribe on this Mac": "Brasscribe på denne Macen",
    "Brasscribe stopped unexpectedly": "Brasscribe stoppet uventet",
    "Brasscribe: making a score, %lld%%": "Brasscribe: lager partitur, %lld %%",
    "Brasscribe: running · %lld phones connected": "Brasscribe: kjører · %lld telefoner tilkoblet",
    "Brasscribe: running · 1 phone connected": "Brasscribe: kjører · 1 telefon tilkoblet",
    "Brasscribe: setting up, %lld%%": "Brasscribe: gjøres klar, %lld %%",
    "Brasscribe: starting": "Brasscribe: starter",
    "Brasscribe: stopped": "Brasscribe: stoppet",
    "Brasscribe: updating": "Brasscribe: oppdaterer",
    "Busy": "Travel",
    "Calm": "Rolig",
    "Cancel": "Avbryt",
    "Check that both are on the same Wi-Fi.": "Sjekk at begge er på samme wifi.",
    "Check this computer": "Sjekk datamaskinen",
    "Close window": "Lukk vinduet",
    "Code: %@ %@ %@, %@ %@ %@": "Kode: %@ %@ %@, %@ %@ %@",
    "Collapsed": "Lukket",
    "Connected now": "Tilkoblet nå",
    "Continue": "Fortsett",
    "Copy details for the tech person": "Kopier detaljer til den tekniske i bandet",
    "Copy diagnostics": "Kopier diagnose",
    "Data folder": "Datamappe",
    "Details for the band's tech person": "Detaljer for den tekniske i bandet",
    "Do this once for each phone or tablet. It stays paired.": "Gjør dette én gang per telefon eller nettbrett. Den forblir tilkoblet.",
    "Don't allow": "Ikke godkjenn",
    "Done": "Ferdig",
    "Download": "Last ned",
    "Downloading what Brasscribe needs": "Laster ned det Brasscribe trenger",
    "Engine from a checkout (folder with pixi.toml)": "Motor fra en utsjekk (mappe med pixi.toml)",
    "Expanded": "Åpnet",
    "Fast: uses the graphics chip": "Rask: bruker grafikkbrikken",
    "Finding the beat": "Finner pulsen",
    "Finish setting up": "Gjør ferdig oppsettet",
    "Free space": "Ledig plass",
    "Free up space…": "Frigjør plass …",
    "Full-band scores need one more step": "Partitur for fullt band trenger ett steg til",
    "Get an access key on Hugging Face": "Hent en tilgangsnøkkel hos Hugging Face",
    "Getting full": "Begynner å bli fullt",
    "Getting the recording ready": "Gjør opptaket klart",
    "Hugging Face access": "Tilgang til Hugging Face",
    "Instrument separator": "Instrumentskiller",
    "Internet: needed once, for the downloads": "Internett: trengs én gang, til nedlastingene",
    "It can send recordings to this computer and get scores back. You can remove it any time.":
        "Den kan sende opptak til denne datamaskinen og få partitur tilbake. Du kan fjerne den når som helst.",
    "It can't send recordings here until it is paired again. Scores already on it stay.":
        "Den kan ikke sende opptak hit før den kobles til igjen. Partitur som allerede ligger på den, blir liggende.",
    "It runs quietly in the menu bar. Look for the Brasscribe mark at the top of the screen.":
        "Den kjører i det stille i menylinjen. Se etter Brasscribe-merket øverst på skjermen.",
    "It tried to start three times. Recordings on your phones are safe.": "Den prøvde å starte tre ganger. Opptakene på telefonene er trygge.",
    "Keep going": "Fortsett",
    "Large": "Stor",
    "Larger": "Større",
    "Last used %@": "Sist brukt %@",
    "Laying out the pages": "Setter opp sidene",
    "Listening tools": "Lytteverktøy",
    "Make scores on this computer": "Lag partitur på denne datamaskinen",
    "Memory": "Minne",
    "Missing one download": "Mangler én nedlasting",
    "More": "Mer",
    "Needs about 15 GB · %lld GB free": "Trenger omtrent 15 GB · %lld GB ledig",
    "Needs attention": "Må sjekkes",
    "Next, your Mac asks whether Brasscribe may find devices on your network. Choose **Allow** so phones can connect.":
        "Nå spør Macen om Brasscribe får finne enheter på nettverket. Velg **Tillat** så telefonene kan koble seg til.",
    "No phones yet. Pair a phone to make full-band scores from it.":
        "Ingen telefoner ennå. Koble til en telefon for å lage partitur for fullt band fra den.",
    "None connected now · %lld paired": "Ingen tilkoblet nå · %lld sammenkoblet",
    "Not enough space: needs about 15 GB, %lld GB free": "Ikke nok plass: trenger omtrent 15 GB, %lld GB ledig",
    "Now": "Nå",
    "OK": "OK",
    "On the phone, open Brasscribe › Settings › Your computer and choose **Brasscribe on %@**. Then allow it here.":
        "Åpne Brasscribe på telefonen › Innstillinger › Datamaskinen din, og velg **Brasscribe på %@**. Godkjenn den her etterpå.",
    "Open Studio": "Åpne Studio",
    "Or scan the QR code with the phone's camera.": "Eller skann QR-koden med kameraet på telefonen.",
    "Or type this address in Brasscribe on the phone: %@, port %@": "Eller skriv inn denne adressen i Brasscribe på telefonen: %@, port %@",
    "Or type this code on the phone:": "Eller skriv inn denne koden på telefonen:",
    "Pair a phone": "Koble til en telefon",
    "Pair another phone": "Koble til en telefon til",
    "Paired": "Sammenkoblet",
    "Paste": "Lim inn",
    "Phone doesn't show this computer?": "Ser ikke telefonen denne datamaskinen?",
    "Phones and tablets": "Telefoner og nettbrett",
    "Phones can't send recordings until you start it.": "Telefonene kan ikke sende opptak før du starter den.",
    "Plenty free": "God plass",
    "Port": "Port",
    "Processor only: slower": "Bare prosessoren: tregere",
    "QR code for pairing with Brasscribe on %@. It holds the same code: %@.":
        "QR-kode for å koble til Brasscribe på %@. Den inneholder den samme koden: %@.",
    "Quit Brasscribe Bandroom": "Avslutt Brasscribe Bandroom",
    "Read the licence": "Les lisensen",
    "Ready": "Klar",
    "Ready to make scores": "Klar til å lage partitur",
    "Ready. Phones and tablets can send recordings.": "Klar. Telefoner og nettbrett kan sende opptak.",
    "Remove": "Fjern",
    "Remove %@": "Fjern %@",
    "Remove %@?": "Fjerne %@?",
    "Restart": "Start på nytt",
    "Restart now": "Start på nytt nå",
    "Restart when done": "Start på nytt når den er ferdig",
    "Restart when “%@” is done?": "Starte på nytt når «%@» er ferdig?",
    "Running": "Kjører",
    "Running · Making a score": "Kjører · Lager partitur",
    "Runs on": "Kjører på",
    "Scan with the camera, or in Brasscribe on the phone.": "Skann med kameraet, eller i Brasscribe på telefonen.",
    "Separating the instruments": "Skiller instrumentene",
    "Separating the soloist from the band": "Skiller solisten fra bandet",
    "Server": "Server",
    "Set up Brasscribe": "Gjør Brasscribe klar",
    "Setting up": "Gjøres klar",
    "Settings…": "Innstillinger …",
    "Show logs": "Vis logger",
    "Sign in again…": "Logg inn på nytt …",
    "Skip for now": "Hopp over nå",
    "Space is running low": "Lite ledig plass",
    "Standard": "Standard",
    "Start Brasscribe": "Start Brasscribe",
    "Start when I log in": "Start når jeg logger på",
    "Starting…": "Starter …",
    "Stop": "Stopp",
    "Stop now": "Stopp nå",
    "Stop while “%@” is being made?": "Stoppe mens «%@» lages?",
    "Stopped": "Stoppet",
    "Stopped unexpectedly": "Stoppet uventet",
    "Takes effect the next time Brasscribe starts.": "Gjelder fra neste gang Brasscribe starter.",
    "Text size": "Tekststørrelse",
    "The band writer isn't downloaded yet.": "Bandskriveren er ikke lastet ned ennå.",
    "The band writer, MuScriptor, is shared by its makers for non-commercial use (CC BY-NC 4.0). Each person accepts it with their own free Hugging Face account.":
        "Bandskriveren, MuScriptor, deles av dem som laget den, til ikke-kommersiell bruk (CC BY-NC 4.0). Hver person godtar lisensen med sin egen gratis Hugging Face-konto.",
    "The download stopped": "Nedlastingen stoppet",
    "The key is saved in your Keychain.": "Nøkkelen er lagret i nøkkelringen.",
    "The phone keeps the recording and can send it again.": "Telefonen beholder opptaket og kan sende det på nytt.",
    "The phone shows the number:": "Telefonen viser tallet:",
    "The phone shows the number: %@": "Telefonen viser tallet: %@",
    "This code works while this window is open, and only once.": "Koden virker så lenge dette vinduet er åpent, og bare én gang.",
    "This computer": "Denne datamaskinen",
    "This request has expired. Choose this computer on the phone again.": "Forespørselen er utløpt. Velg denne datamaskinen på telefonen igjen.",
    "Too many wrong codes. Wait a moment, or allow the phone here.": "For mange feil koder. Vent litt, eller godkjenn telefonen her.",
    "Try again": "Prøv igjen",
    "Updating": "Oppdaterer",
    "Uses the graphics chip": "Bruker grafikkbrikken",
    "Version": "Versjon",
    "Very busy": "Svært travel",
    "Waiting for a phone…": "Venter på en telefon …",
    "Where downloads are kept": "Hvor nedlastingene lagres",
    "Without it, Brasscribe can't write down a full band. You can add it later.":
        "Uten den kan ikke Brasscribe skrive ned et fullt band. Du kan legge den til senere.",
    "Work load": "Arbeidsmengde",
    "Writing down the notes": "Skriver ned tonene",
    "You can close this window. Brasscribe keeps downloading and tells you when it's ready.":
        "Du kan lukke dette vinduet. Brasscribe fortsetter å laste ned og sier fra når alt er klart.",
    "full-band scores need one more step": "partitur for fullt band trenger ett steg til",
    "space is running low": "lite ledig plass",
    "this score": "dette partituret",
    "“%@”": "«%@»",
    "“%@” from %@": "«%@» fra %@",
}

# Keys built at run time (LocalizedStringKey(item)) that the compiler can't extract.
EXTRA = ["Listening tools", "Band writer (MuScriptor)", "Instrument separator", "Beat finder"]

INFO_NB = {
    "CFBundleDisplayName": "Brasscribe Bandroom",
    "CFBundleName": "Brasscribe Bandroom",
    "NSLocalNetworkUsageDescription": "Telefoner og nettbrett i bandet finner denne Macen på nettverket og sender opptakene sine hit.",
}


def entry(nb: str) -> dict:
    return {"localizations": {"nb": {"stringUnit": {"state": "translated", "value": nb}}}}


def main(root: str) -> int:
    keys = set(EXTRA)
    for f in glob.glob(root + "/**/*.stringsdata", recursive=True):
        if "BrasscribeBandroom.build" not in f:
            continue
        for table in json.load(open(f)).get("tables", {}).values():
            keys.update(e["key"] for e in table)
    keys.discard("")
    strings, missing = {}, []
    for k in sorted(keys):
        if k in NB:
            strings[k] = entry(NB[k])
        else:
            strings[k] = {}
            missing.append(k)
    with open("App/Localizable.xcstrings", "w") as f:
        json.dump({"sourceLanguage": "en", "strings": strings, "version": "1.0"}, f, indent=2, ensure_ascii=False, sort_keys=True)
    with open("App/InfoPlist.xcstrings", "w") as f:
        json.dump({"sourceLanguage": "en", "version": "1.0", "strings": {k: entry(v) for k, v in INFO_NB.items()}},
                  f, indent=2, ensure_ascii=False, sort_keys=True)
    unused = sorted(set(NB) - keys)
    print(f"{len(strings)} strings, {len(missing)} without Norwegian, {len(unused)} unused", file=sys.stderr)
    for k in missing:
        print("  missing:", k, file=sys.stderr)
    for k in unused:
        print("  unused:", k, file=sys.stderr)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
