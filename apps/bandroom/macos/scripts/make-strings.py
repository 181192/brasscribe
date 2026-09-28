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
    "%@ GB": "%@ GB",
    "%@ aren't downloaded yet.": "%@ er ikke lastet ned ennå.",
    "%@ is paired.": "%@ er koblet til.",
    "%@ keeps the recording and can send it again.": "%@ beholder opptaket og kan sende det på nytt.",
    "%@ of %@ GB": "%@ av %@ GB",
    "%@ wants to use this computer.": "%@ vil bruke denne datamaskinen.",
    "%@ · about %lld min left": "%@ · omtrent %lld min igjen",
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
    "A download arrived damaged": "En nedlasting kom fram skadet",
    "About Brasscribe Bandroom": "Om Brasscribe Bandroom",
    "Accept one licence": "Godta én lisens",
    "Accept the licence on Hugging Face, then try again": "Godta lisensen på Hugging Face, og prøv igjen",
    "Access key from Hugging Face": "Tilgangsnøkkel fra Hugging Face",
    "Add an access key": "Legg til en tilgangsnøkkel",
    "Add the key, then try again. The separators download without it.":
        "Legg til nøkkelen, og prøv igjen. Skillerne lastes ned uten den.",
    "Address": "Adresse",
    "Allow": "Godkjenn",
    "Allow %@?": "Godkjenne %@?",
    "Almost full": "Nesten fullt",
    "Also delete the downloads (%@ GB)": "Slett også nedlastingene (%@ GB)",
    "Another program on this computer is in the way.": "Et annet program på denne datamaskinen står i veien.",
    "Appearance": "Utseende",
    "Arranging for brass band": "Arrangerer for brassband",
    "Back": "Tilbake",
    "Back in about a minute. Phones reconnect by themselves.": "Tilbake om et minutt. Telefonene kobler seg til igjen selv.",
    "Band writer (MuScriptor)": "Bandskriver (MuScriptor)",
    "Brasscribe can't start": "Brasscribe kan ikke starte",
    "Brasscribe couldn't save the download": "Brasscribe fikk ikke lagret nedlastingen",
    "Brasscribe deleted it. Try again to fetch it afresh.": "Brasscribe har slettet den. Prøv igjen for å hente den på nytt.",
    "Brasscribe does the heavy work here, so your phones and tablets can make scores for the whole band. Recordings stay on your own devices.":
        "Brasscribe gjør det tunge arbeidet her, så telefoner og nettbrett kan lage partitur for hele bandet. Opptakene blir på dine egne enheter.",
    "Brasscribe is ready": "Brasscribe er klar",
    "Brasscribe is ready. Phones and tablets can make full-band scores now.":
        "Brasscribe er klar. Telefoner og nettbrett kan lage partitur for fullt band nå.",
    "Brasscribe isn't running. Start it from the menu bar, then pair.": "Brasscribe kjører ikke. Start den fra menylinjen, og koble til etterpå.",
    "Brasscribe needs attention: %@": "Brasscribe må sjekkes: %@",
    "Brasscribe on %@": "Brasscribe på %@",
    "Brasscribe on this Mac": "Brasscribe på denne Macen",
    "Brasscribe stopped unexpectedly": "Brasscribe stoppet uventet",
    "Brasscribe uses the key only to download the band writer from Hugging Face, and keeps it in your Keychain.":
        "Brasscribe bruker nøkkelen bare til å laste ned bandskriveren fra Hugging Face, og oppbevarer den i nøkkelringen din.",
    "Brasscribe's own tools aren't installed yet.": "Brasscribes egne verktøy er ikke installert ennå.",
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
    "Check the internet connection, then try again. It continues where it stopped.":
        "Sjekk internettforbindelsen, og prøv igjen. Nedlastingen fortsetter der den stoppet.",
    "Check this computer": "Sjekk datamaskinen",
    "Close window": "Lukk vinduet",
    "Code: %@ %@ %@, %@ %@ %@": "Kode: %@ %@ %@, %@ %@ %@",
    "Collapsed": "Lukket",
    "Connected now": "Tilkoblet nå",
    "Continue": "Fortsett",
    "Continue without it": "Fortsett uten",
    "Copy details for the tech person": "Kopier detaljer til den tekniske i bandet",
    "Copy diagnostics": "Kopier diagnose",
    "Dark": "Mørkt",
    "Data folder": "Datamappe",
    "Details for the band's tech person": "Detaljer for den tekniske i bandet",
    "Do this once for each phone or tablet. It stays paired.": "Gjør dette én gang per telefon eller nettbrett. Den forblir tilkoblet.",
    "Don't allow": "Ikke godkjenn",
    "Don't see it? On a MacBook it can hide behind the camera notch. Open Brasscribe from Launchpad any time.":
        "Ser du det ikke? På en MacBook kan det skjule seg bak kamerahakket. Du kan alltid åpne Brasscribe fra Launchpad.",
    "Done": "Ferdig",
    "Download": "Last ned",
    "Downloading": "Laster ned",
    "Downloading what Brasscribe needs": "Laster ned det Brasscribe trenger",
    "Engine from a checkout (folder with pixi.toml)": "Motor fra en utsjekk (mappe med pixi.toml)",
    "Expanded": "Åpnet",
    "Fast: uses the graphics chip": "Rask: bruker grafikkbrikken",
    "Finding the beat": "Finner pulsen",
    "Finish setting up": "Gjør ferdig oppsettet",
    "For when the Brasscribe mark is hidden in the menu bar, for example behind the camera notch.":
        "Til når Brasscribe-merket er skjult i menylinjen, for eksempel bak kamerahakket.",
    "Free space": "Ledig plass",
    "Free up space…": "Frigjør plass …",
    "Full-band scores need one more step": "Partitur for fullt band trenger ett steg til",
    "Get an access key on Hugging Face": "Hent en tilgangsnøkkel hos Hugging Face",
    "Getting full": "Begynner å bli fullt",
    "Getting the recording ready": "Gjør opptaket klart",
    "Got it": "OK",
    "Hugging Face access": "Tilgang til Hugging Face",
    "Hugging Face didn't accept the access key": "Hugging Face godtok ikke tilgangsnøkkelen",
    "Increase contrast is on, so Brasscribe uses its high-contrast colours.":
        "Øk kontrast er på, så Brasscribe bruker høykontrastfargene.",
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
    "Light": "Lyst",
    "Listening tools": "Lytteverktøy",
    "Make scores on this computer": "Lag partitur på denne datamaskinen",
    "Match system": "Følg systemet",
    "Memory": "Minne",
    "Missing %lld downloads": "Mangler %lld nedlastinger",
    "Missing one download": "Mangler én nedlasting",
    "More": "Mer",
    "Name shown to phones": "Navnet telefonene ser",
    "Needs about 15 GB · %lld GB free": "Trenger omtrent 15 GB · %lld GB ledig",
    "Needs attention": "Må sjekkes",
    "Next, your Mac asks whether Brasscribe may find devices on your network. Choose **Allow** so phones can connect.":
        "Nå spør Macen om Brasscribe får finne enheter på nettverket. Velg **Tillat** så telefonene kan koble seg til.",
    "No phones yet. Pair a phone to make full-band scores from it.":
        "Ingen telefoner ennå. Koble til en telefon for å lage partitur for fullt band fra den.",
    "None connected now · %lld paired": "Ingen tilkoblet nå · %lld sammenkoblet",
    "Not enough space": "Ikke nok plass",
    "Not enough space: needs about 15 GB, %lld GB free": "Ikke nok plass: trenger omtrent 15 GB, %lld GB ledig",
    "Now": "Nå",
    "OK": "OK",
    "On the phone, open Brasscribe › Settings › Your computer and choose **Brasscribe on %@**. Then allow it here.":
        "Åpne Brasscribe på telefonen › Innstillinger › Datamaskinen din, og velg **Brasscribe på %@**. Godkjenn den her etterpå.",
    "Open Menu Bar settings": "Åpne innstillingene for menylinjen",
    "Open Studio": "Åpne Studio",
    "Open the MuScriptor page": "Åpne MuScriptor-siden",
    "Or scan the QR code with the phone's camera.": "Eller skann QR-koden med kameraet på telefonen.",
    "Or type this address in Brasscribe on the phone: %@, port %@": "Eller skriv inn denne adressen i Brasscribe på telefonen: %@, port %@",
    "Or type this code on the phone:": "Eller skriv inn denne koden på telefonen:",
    "Pair a phone": "Koble til en telefon",
    "Pair another phone": "Koble til en telefon til",
    "Paired": "Sammenkoblet",
    "Paste": "Lim inn",
    "Paste a new key": "Lim inn en ny nøkkel",
    "Pause": "Pause",
    "Paused · %@": "På pause · %@",
    "Phone doesn't show this computer?": "Ser ikke telefonen denne datamaskinen?",
    "Phones and tablets": "Telefoner og nettbrett",
    "Phones can't make full-band scores here after this. Scores on your phones stay.": "Etterpå kan ikke telefonene lage partitur for fullt band her. Partitur på telefonene blir liggende.",
    "Phones can't send recordings until you start it.": "Telefonene kan ikke sende opptak før du starter den.",
    "Phones list this Mac as “Brasscribe on %@”.": "Telefonene viser denne Macen som «Brasscribe på %@».",
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
    "Remove Brasscribe from this Mac?": "Fjerne Brasscribe fra denne Macen?",
    "Remove Brasscribe from this Mac…": "Fjern Brasscribe fra denne Macen …",
    "Restart": "Start på nytt",
    "Restart now": "Start på nytt nå",
    "Restart when done": "Start på nytt når den er ferdig",
    "Restart when “%@” is done?": "Starte på nytt når «%@» er ferdig?",
    "Resume": "Fortsett",
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
    "Show in the Dock": "Vis i Dock",
    "Show logs": "Vis logger",
    "Sign in again…": "Logg inn på nytt …",
    "Signed in, but the licence isn't accepted yet. Choose **Agree** on the MuScriptor page.":
        "Du er logget inn, men lisensen er ikke godtatt ennå. Velg **Agree** på MuScriptor-siden.",
    "Skip for now": "Hopp over nå",
    "Soloist separator": "Solistskiller",
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
    "The Brasscribe mark may be hidden behind the camera notch. Open Brasscribe from Launchpad any time, or make room in System Settings › Menu Bar.":
        "Brasscribe-merket kan være skjult bak kamerahakket. Du kan alltid åpne Brasscribe fra Launchpad, eller gi plass i Systeminnstillinger › Menylinje.",
    "The band writer isn't downloaded yet.": "Bandskriveren er ikke lastet ned ennå.",
    "The band writer needs your Hugging Face access key": "Bandskriveren trenger tilgangsnøkkelen din fra Hugging Face",
    "The band writer, MuScriptor, is shared by its makers for non-commercial use (CC BY-NC 4.0). Each person accepts it with their own free Hugging Face account.":
        "Bandskriveren, MuScriptor, deles av dem som laget den, til ikke-kommersiell bruk (CC BY-NC 4.0). Hver person godtar lisensen med sin egen gratis Hugging Face-konto.",
    "The download stopped": "Nedlastingen stoppet",
    "The downloads need about %@ GB; %@ GB is free.": "Nedlastingene trenger omtrent %@ GB, og %@ GB er ledig.",
    "The downloads stay in %@, so installing again doesn't fetch them again.": "Nedlastingene blir liggende i %@, så en ny installasjon slipper å hente dem på nytt.",
    "The instrument separator isn't downloaded yet.": "Instrumentskilleren er ikke lastet ned ennå.",
    "The key is saved in your Keychain.": "Nøkkelen er lagret i nøkkelringen.",
    "The key may have been deleted or have expired.": "Nøkkelen kan være slettet eller utløpt.",
    "The phone keeps the recording and can send it again.": "Telefonen beholder opptaket og kan sende det på nytt.",
    "The phone shows the number:": "Telefonen viser tallet:",
    "The phone shows the number: %@": "Telefonen viser tallet: %@",
    "The separators have no stated licence, so Brasscribe doesn't pass them on: this Mac downloads them from where their makers publish them.":
        "Skillerne har ingen oppgitt lisens, så Brasscribe deler dem ikke videre. Macen laster dem ned der de som laget dem, publiserer dem.",
    "The soloist separator isn't downloaded yet.": "Solistskilleren er ikke lastet ned ennå.",
    "This code works while this window is open, and only once.": "Koden virker så lenge dette vinduet er åpent, og bare én gang.",
    "This computer": "Denne datamaskinen",
    "This request has expired. Choose this computer on the phone again.": "Forespørselen er utløpt. Velg denne datamaskinen på telefonen igjen.",
    "Too many wrong codes. Wait a moment, or allow the phone here.": "For mange feil koder. Vent litt, eller godkjenn telefonen her.",
    "Try again": "Prøv igjen",
    "Updating": "Oppdaterer",
    "Use this name": "Bruk dette navnet",
    "Uses the graphics chip": "Bruker grafikkbrikken",
    "Version": "Versjon",
    "Very busy": "Svært travel",
    "Waiting": "Venter",
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
    "the band writer": "bandskriveren",
    "the instrument separator": "instrumentskilleren",
    "the soloist separator": "solistskilleren",
    "this score": "dette partituret",
    "“%@”": "«%@»",
    "“%@” from %@": "«%@» fra %@",
}

# Keys built at run time that the compiler can't extract (none today).
EXTRA: list[str] = []

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
