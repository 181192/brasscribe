#!/usr/bin/env python3
"""Writes Strings/en-US/Resources.resw and Strings/nb-NO/Resources.resw of Brasscribe Bandroom for Windows.

The copy is design/server-app.md §10 (the Norwegian is written, not translated). Keys are the deck's keys
with "_" for "." and "-" (resw names can't hold "."); extra keys the deck doesn't list are marked (+).
Edit the table here and run: python3 tools/Strings/gen_resw.py
"""
from pathlib import Path
from xml.sax.saxutils import escape

ROWS = [
    # 10.1 Popover and flyout (the step names are Play's, word for word)
    ("Header", "Brasscribe on {0}", "Brasscribe på {0}"),
    ("WindowTitle", "Brasscribe on this PC", "Brasscribe på denne PC-en"),
    ("Status_Running", "Running", "Kjører"),
    ("Status_MakingScore", "Making a score", "Lager partitur"),  # (+) mac mockup status line
    ("Status_Running_Idle", "Ready. Phones and tablets can send recordings.", "Klar. Telefoner og nettbrett kan sende opptak."),
    ("Status_Starting", "Starting…", "Starter …"),
    ("Status_Attention", "Needs attention", "Må sjekkes"),
    ("Status_Stopped", "Stopped", "Stoppet"),
    ("Status_Stopped_Sub", "Phones can't send recordings until you start it.", "Telefonene kan ikke sende opptak før du starter den."),
    ("Status_Updating", "Updating", "Oppdaterer"),
    ("Status_Updating_Sub", "Back in about a minute. Phones reconnect by themselves.", "Tilbake om et minutt. Telefonene kobler seg til igjen selv."),
    ("Update_Progress", "Updating Brasscribe… {0}%.", "Oppdaterer Brasscribe … {0} %."),  # (+) the engine after an app update
    ("Update_Failed_Title", "Brasscribe couldn't finish updating", "Brasscribe fikk ikke fullført oppdateringen"),  # (+)
    ("Update_Failed_Why", "The previous version is still running, so phones can keep sending recordings.",
     "Den forrige versjonen kjører fortsatt, så telefonene kan sende opptak som før."),  # (+)
    ("Status_Setup", "Setting up", "Gjøres klar"),
    ("Status_Error", "Stopped unexpectedly", "Stoppet uventet"),
    ("Now_Heading", "Now", "Nå"),
    ("Now_Title", "“{0}”", "«{0}»"),  # (+) now.source when the job doesn't say which phone sent it
    ("Now_Source", "“{0}” from {1}", "«{0}» fra {1}"),
    ("Now_Progress", "{0}% · about {1} min left", "{0} % · omtrent {1} min igjen"),
    ("Now_Percent", "{0}%", "{0} %"),  # (+)
    ("Now_Queue", "{0} more waiting", "{0} til venter"),
    ("Step_Prepare", "Getting the recording ready", "Gjør opptaket klart"),
    ("Step_Beat", "Finding the beat", "Finner pulsen"),
    ("Step_Separate", "Separating the instruments", "Skiller instrumentene"),
    ("Step_Layers", "Separating the soloist from the band", "Skiller solisten fra bandet"),
    ("Step_Notes", "Writing down the notes", "Skriver ned tonene"),
    ("Step_Arrange", "Arranging for brass band", "Arrangerer for brassband"),
    ("Step_Layout", "Laying out the pages", "Setter opp sidene"),
    ("Primary_Pair", "Pair a phone", "Koble til en telefon"),
    ("Primary_Start", "Start Brasscribe", "Start Brasscribe"),
    ("Primary_FinishSetup", "Finish setting up", "Gjør ferdig oppsettet"),
    ("Primary_TryAgain", "Try again", "Prøv igjen"),
    ("Devices_Heading", "Phones and tablets", "Telefoner og nettbrett"),
    ("Devices_Summary", "{0} connected now · {1} paired", "{0} tilkoblet nå · {1} sammenkoblet"),
    ("Devices_Summary_None", "None connected now · {0} paired", "Ingen tilkoblet nå · {0} sammenkoblet"),
    ("Devices_Connected", "Connected now", "Tilkoblet nå"),
    ("Devices_Connected_Never", "Not used yet", "Ikke brukt ennå"),  # (+)
    ("Devices_LastUsed", "Last used {0}", "Sist brukt {0}"),
    ("Devices_When_Today", "today", "i dag"),  # (+)
    ("Devices_When_Yesterday", "yesterday", "i går"),  # (+)
    ("Devices_When_DaysAgo", "{0} days ago", "for {0} dager siden"),
    ("Devices_Remove", "Remove", "Fjern"),
    ("Devices_Remove_A11y", "Remove {0}", "Fjern {0}"),  # (+) the button's accessible name
    ("Devices_Removed", "{0} is removed.", "{0} er fjernet."),  # (+) announced
    ("Devices_Remove_Failed", "{0} couldn't be removed. Try again.", "{0} ble ikke fjernet. Prøv igjen."),  # (+)
    ("Devices_Empty", "No phones yet. Pair a phone to make full-band scores from it.", "Ingen telefoner ennå. Koble til en telefon for å lage partitur for fullt band fra den."),
    ("Back", "Back", "Tilbake"),
    ("Close", "Close", "Lukk"),  # (+)
    ("Computer_Heading", "This computer", "Denne datamaskinen"),
    ("Health_Load", "Work load", "Arbeidsmengde"),
    ("Health_Load_Calm", "Calm", "Rolig"),
    ("Health_Load_Busy", "Busy", "Travel"),
    ("Health_Load_VeryBusy", "Very busy", "Svært travel"),
    ("Health_Memory", "Memory", "Minne"),
    ("Health_Memory_Plenty", "Plenty free", "God plass"),
    ("Health_Memory_GettingFull", "Getting full", "Begynner å bli fullt"),
    ("Health_Memory_AlmostFull", "Almost full", "Nesten fullt"),
    ("Health_Disk", "Free space", "Ledig plass"),
    ("Health_Disk_Value", "{0} GB free", "{0} GB ledig"),
    ("Health_Ready", "Ready to make scores", "Klar til å lage partitur"),
    ("Health_Ready_Yes", "Ready", "Klar"),
    ("Health_Ready_Missing", "Missing one download", "Mangler én nedlasting"),
    ("Health_Ready_MissingMany", "Missing {0} downloads", "Mangler {0} nedlastinger"),
    ("Health_Speed_Gpu", "Uses the graphics chip", "Bruker grafikkbrikken"),
    ("Health_Speed_Nvidia", "Uses the graphics card (NVIDIA)", "Bruker grafikkortet (NVIDIA)"),
    ("Health_Speed_Cpu", "Processor only: slower", "Bare prosessoren: tregere"),
    ("Update_Row", "Version {0} is ready. It installs when nothing is being made.", "Versjon {0} er klar. Den installeres når ingenting lages."),
    ("Update_Now", "Update now", "Oppdater nå"),
    ("Action_Restart", "Restart", "Start på nytt"),
    ("Action_Stop", "Stop", "Stopp"),
    ("Action_OpenStudio", "Open Studio", "Åpne Studio"),
    ("More", "More", "Mer"),
    ("More_Settings", "Settings…", "Innstillinger …"),
    ("More_Updates", "Check for updates", "Se etter oppdateringer"),
    ("More_Login", "Start when I log in", "Start når jeg logger på"),
    ("More_About", "About Brasscribe Bandroom", "Om Brasscribe Bandroom"),
    ("More_Remove", "Remove Brasscribe from this PC…", "Fjern Brasscribe fra denne PC-en …"),
    ("More_Quit", "Quit Brasscribe Bandroom", "Avslutt Brasscribe Bandroom"),
    # Settings (the settings.* rows) and Appearance (design/system.md §10)
    ("Settings_Title", "Settings", "Innstillinger"),
    ("Settings_Login", "Start when I log in", "Start når jeg logger på"),
    ("Settings_Name", "Name shown to phones", "Navnet telefonene ser"),
    ("Settings_Name_Note", "Phones list this PC as “Brasscribe on {0}”.", "Telefonene viser denne PC-en som «Brasscribe på {0}»."),
    ("Settings_Name_Use", "Use this name", "Bruk dette navnet"),
    ("Settings_Hf", "Hugging Face access", "Tilgang til Hugging Face"),
    ("Settings_Hf_Note", "Brasscribe uses the key only to download the band writer from Hugging Face, and keeps it in Windows Credential Manager.", "Brasscribe bruker nøkkelen bare til å laste ned bandskriveren fra Hugging Face, og oppbevarer den i Legitimasjonsbehandling i Windows."),  # (+) the macOS copy, Keychain → Credential Manager
    ("Settings_Hf_Saved", "The key is saved in Credential Manager.", "Nøkkelen er lagret i Legitimasjonsbehandling."),  # (+)
    ("Settings_Hf_FromEnvironment", "Brasscribe uses the HF_TOKEN key set on this PC.", "Brasscribe bruker HF_TOKEN-nøkkelen som er satt på denne PC-en."),  # (+)
    ("Settings_Save", "Save", "Lagre"),  # (+)
    ("Appearance_Title", "Appearance", "Utseende"),  # (+) design/system.md §10
    ("Appearance_System", "Match system", "Følg systemet"),  # (+)
    ("Appearance_Light", "Light", "Lyst"),  # (+)
    ("Appearance_Dark", "Dark", "Mørkt"),  # (+)
    ("Appearance_Contrast", "Your contrast theme is on, so Windows chooses the colours.", "Kontrasttemaet ditt er på, så Windows velger fargene."),  # (+)
    ("Tray_Open", "Open", "Åpne"),
    ("Tray_PauseDownloads", "Pause the downloads", "Sett nedlastingene på pause"),  # (+) no setup window on Windows
    ("Tray_ResumeDownloads", "Resume the downloads", "Fortsett nedlastingene"),  # (+)
    ("Tech_Summary", "Details for the band's tech person", "Detaljer for den tekniske i bandet"),
    ("Tech_Address", "Address", "Adresse"),
    ("Tech_Port", "Port", "Port"),  # (+)
    ("Tech_Version", "Version", "Versjon"),
    ("Tech_Build", "Engine build", "Motorbygg"),  # (+)
    ("Tech_Workspace", "Workspace", "Arbeidsområde"),  # (+)
    ("Tech_Device", "Runs on", "Kjører på"),
    ("Tech_Server", "Server", "Server"),  # (+)
    ("Tech_Data", "Data folder", "Datamappe"),
    ("Tech_Logs", "Show logs", "Vis logger"),
    ("Tech_Copy", "Copy diagnostics", "Kopier diagnose"),
    ("Tech_Copied", "Diagnostics copied.", "Diagnosen er kopiert."),  # (+) announced
    ("Tooltip_Running", "Brasscribe: running · {0} phones connected", "Brasscribe: kjører · {0} telefoner tilkoblet"),
    ("Tooltip_Running_One", "Brasscribe: running · 1 phone connected", "Brasscribe: kjører · 1 telefon tilkoblet"),  # (+)
    ("Tooltip_Busy", "Brasscribe: making a score, {0}%", "Brasscribe: lager partitur, {0} %"),
    ("Tooltip_Attention", "Brasscribe needs attention: {0}", "Brasscribe må sjekkes: {0}"),
    ("Tooltip_Stopped", "Brasscribe: stopped", "Brasscribe: stoppet"),
    ("Tooltip_Starting", "Brasscribe: starting", "Brasscribe: starter"),
    ("Tooltip_Updating", "Brasscribe: updating", "Brasscribe: oppdaterer"),
    ("Tooltip_Setup", "Brasscribe: setting up, {0}%", "Brasscribe: gjøres klar, {0} %"),
    # 10.2 Confirmations
    ("Stop_Busy_Title", "Stop while “{0}” is being made?", "Stoppe mens «{0}» lages?"),
    ("Stop_Busy_Title_Untitled", "Stop while a score is being made?", "Stoppe mens et partitur lages?"),  # (+)
    ("Stop_Busy_Body", "{0} keeps the recording and can send it again.", "{0} beholder opptaket og kan sende det på nytt."),
    ("Stop_Busy_Body_Unknown", "The phone keeps the recording and can send it again.", "Telefonen beholder opptaket og kan sende det på nytt."),  # (+) no device on the job
    ("Stop_Busy_Keep", "Keep going", "Fortsett"),
    ("Stop_Busy_Stop", "Stop now", "Stopp nå"),
    ("Restart_Busy_Title", "Restart when “{0}” is done?", "Starte på nytt når «{0}» er ferdig?"),
    ("Restart_Busy_Title_Untitled", "Restart when the score is done?", "Starte på nytt når partituret er ferdig?"),  # (+)
    ("Restart_Busy_Now", "Restart now", "Start på nytt nå"),
    ("Restart_Busy_Later", "Restart when done", "Start på nytt når den er ferdig"),
    ("Cancel", "Cancel", "Avbryt"),
    ("RemoveDevice_Title", "Remove {0}?", "Fjerne {0}?"),
    ("RemoveDevice_Body", "It can't send recordings here until it is paired again. Scores already on it stay.", "Den kan ikke sende opptak hit før den kobles til igjen. Partitur som allerede ligger på den, blir liggende."),
    ("RemoveDevice_Ok", "Remove", "Fjern"),
    # 10.3 Pair a phone
    ("Pair_Title", "Pair a phone", "Koble til en telefon"),
    ("Pair_Lead", "Do this once for each phone or tablet. It stays paired.", "Gjør dette én gang per telefon eller nettbrett. Den forblir tilkoblet."),
    ("Pair_Way1", "On the phone, open Brasscribe › Settings › Your computer and choose {0}. Then allow it here.", "Åpne Brasscribe på telefonen › Innstillinger › Datamaskinen din, og velg {0}. Godkjenn den her etterpå."),
    ("Pair_Way2", "Or scan the QR code with the phone's camera.", "Eller skann QR-koden med kameraet på telefonen."),
    ("Pair_Qr_Caption", "Scan with the camera, or in Brasscribe on the phone.", "Skann med kameraet, eller i Brasscribe på telefonen."),
    ("Pair_Way3", "Or type this code on the phone:", "Eller skriv inn denne koden på telefonen:"),
    ("Pair_Code_A11y", "Code: {0} {1} {2}, {3} {4} {5}", "Kode: {0} {1} {2}, {3} {4} {5}"),
    ("Pair_Qr_A11y", "QR code for pairing with Brasscribe on {0}. It holds the same code: {1}.", "QR-kode for å koble til Brasscribe på {0}. Den inneholder den samme koden: {1}."),
    ("Pair_Limit", "This code works while this window is open, and only once.", "Koden virker så lenge dette vinduet er åpent, og bare én gang."),
    ("Pair_Waiting", "Waiting for a phone…", "Venter på en telefon …"),
    ("Pair_Waiting_A11y", "Waiting for a phone.", "Venter på en telefon."),
    ("Pair_Done", "{0} is paired.", "{0} er koblet til."),
    ("Pair_Another", "Pair another phone", "Koble til en telefon til"),
    ("Pair_Lockout", "Too many wrong codes. Wait a moment, or allow the phone here.", "For mange feil koder. Vent litt, eller godkjenn telefonen her."),
    ("Pair_Help_Summary", "Phone doesn't show this computer?", "Ser ikke telefonen denne datamaskinen?"),
    ("Pair_Help_Wifi", "Check that both are on the same Wi-Fi.", "Sjekk at begge er på samme wifi."),
    ("Pair_Help_Address", "Or type this address in Brasscribe on the phone: {0}, port {1}", "Eller skriv inn denne adressen i Brasscribe på telefonen: {0}, port {1}"),
    ("Pair_Close", "Done", "Ferdig"),
    ("Pair_Unavailable", "Brasscribe isn't running, so phones can't pair right now. Start it from the taskbar corner, then try again.", "Brasscribe kjører ikke, så telefoner kan ikke kobles til nå. Start den fra hjørnet av oppgavelinjen, og prøv igjen."),  # (+)
    ("Dot", "dot", "punktum"),  # (+) spoken addresses
    ("Allow_Title", "Allow {0}?", "Godkjenne {0}?"),
    ("Allow_Body", "It can send recordings to this computer and get scores back. You can remove it any time.", "Den kan sende opptak til denne datamaskinen og få partitur tilbake. Du kan fjerne den når som helst."),
    ("Allow_Match", "The phone shows the number:", "Telefonen viser tallet:"),
    ("Allow_Match_A11y", "The phone shows the number: {0}", "Telefonen viser tallet: {0}"),
    ("Allow_Expired", "This request has expired. Choose this computer on the phone again.", "Forespørselen er utløpt. Velg denne datamaskinen på telefonen igjen."),
    ("Allow_Failed", "That didn't go through. Try again.", "Det gikk ikke. Prøv igjen."),  # (+) the answer didn't get through
    ("Allow_Ok", "Allow", "Godkjenn"),
    ("Allow_No", "Don't allow", "Ikke godkjenn"),
    ("Notify_PairRequest", "{0} wants to use this computer.", "{0} vil bruke denne datamaskinen."),
    # 10.4 First run (the parts Bandroom for Windows shows today)
    ("Setup_3_Title", "Downloading what Brasscribe needs", "Laster ned det Brasscribe trenger"),
    ("Setup_3_Leave", "You can close this window. Brasscribe keeps downloading and tells you when it's ready.", "Du kan lukke dette vinduet. Brasscribe fortsetter å laste ned og sier fra når alt er klart."),
    ("Setup_Step", "{0} of {1}", "{0} av {1}"),  # (+) environments done while the size is unknown
    ("Setup_3_Progress", "{0} of {1} GB · about {2} min left", "{0} av {1} GB · omtrent {2} min igjen"),
    ("Setup_3_Amount", "{0} of {1} GB", "{0} av {1} GB"),  # (+) before the time left is known
    ("Setup_3_Paused", "Paused · {0} of {1} GB", "På pause · {0} av {1} GB"),
    ("Setup_3_NoKey_Title", "The band writer needs your Hugging Face access key", "Bandskriveren trenger tilgangsnøkkelen din fra Hugging Face"),
    ("Setup_3_NoKey_Why", "Add the key, then try again. The instrument separators download without it.", "Legg til nøkkelen, og prøv igjen. Instrumentskillerne lastes ned uten den."),
    ("Setup_3_NoKey_Fix", "Add an access key", "Legg til en tilgangsnøkkel"),
    ("Setup_3_Licence_Title", "Accept the licence on Hugging Face, then try again", "Godta lisensen på Hugging Face, og prøv igjen"),
    ("Setup_3_Licence_Why", "Signed in, but the licence isn't accepted yet. Choose Agree on the MuScriptor page.", "Du er logget inn, men lisensen er ikke godtatt ennå. Velg Agree på MuScriptor-siden."),
    ("Setup_3_Licence_Fix", "Open the MuScriptor page", "Åpne MuScriptor-siden"),
    ("Setup_3_Space_Title", "Not enough space", "Ikke nok plass"),
    ("Setup_3_Space_Why", "The downloads need about {0} GB; {1} GB is free.", "Nedlastingene trenger omtrent {0} GB, og {1} GB er ledig."),
    ("Setup_3_Damaged_Title", "A download arrived damaged", "En nedlasting kom fram skadet"),
    ("Setup_3_Damaged_Why", "Brasscribe deleted it. Try again to fetch it afresh.", "Brasscribe har slettet den. Prøv igjen for å hente den på nytt."),
    ("Setup_3_Network_Title", "The download stopped", "Nedlastingen stoppet"),
    ("Setup_3_Network_Why", "Check the internet connection, then try again. It continues where it stopped.", "Sjekk internettforbindelsen, og prøv igjen. Nedlastingen fortsetter der den stoppet."),
    ("Setup_3_Disk_Title", "Brasscribe couldn't save the download", "Brasscribe fikk ikke lagret nedlastingen"),  # (+) mac setup window
    ("Setup_2_Key_Label", "Access key from Hugging Face", "Tilgangsnøkkel fra Hugging Face"),
    ("Setup_Item_Listening", "Listening tools", "Lytteverktøy"),
    ("Setup_Item_Soloist", "Soloist separator", "Solistskiller"),
    ("Setup_Item_BandWriter", "Band writer (MuScriptor)", "Bandskriver (MuScriptor)"),
    ("Setup_Item_Separator", "Instrument separator", "Instrumentskiller"),
    ("Setup_Item_BeatFinder", "Beat finder", "Taktfinner"),
    ("Setup_Failed", "The download stopped. Check the internet connection, then try again.", "Nedlastingen stoppet. Sjekk internettforbindelsen, og prøv igjen."),  # (+)
    ("Setup_4_Where", "It runs quietly in the corner of the taskbar. If you don't see it, choose ^ (Show hidden icons).", "Den kjører i det stille i hjørnet av oppgavelinjen. Ser du den ikke, velger du ^ (Vis skjulte ikoner)."),
    ("Setup_Refuse", "Brasscribe needs a 64-bit Intel or AMD PC with Windows 10 (22H2) or Windows 11.", "Brasscribe trenger en 64-biters PC med Intel eller AMD og Windows 10 (22H2) eller Windows 11."),
    ("Notify_Ready", "Brasscribe is ready. Phones and tablets can make full-band scores now.", "Brasscribe er klar. Telefoner og nettbrett kan lage partitur for fullt band nå."),
    # 10.5 Needs attention and errors
    ("Lan_Title", "Phones can't find this computer", "Telefoner finner ikke denne datamaskinen"),
    ("Lan_Win_Why", "Windows Firewall is blocking Brasscribe on this network.", "Windows-brannmuren stopper Brasscribe på dette nettverket."),
    ("Lan_Win_Fix", "Allow on private networks", "Tillat på private nettverk"),
    ("Lan_Public_Why", "This network is set to Public, so Windows hides this PC. If it's your home or band-room Wi-Fi, set it to Private.", "Dette nettverket er satt til Offentlig, så Windows skjuler denne PC-en. Er det wifi hjemme eller i øvingslokalet, setter du det til Privat."),
    ("Lan_Public_Fix", "Open network settings", "Åpne nettverksinnstillingene"),
    ("Disk_Title", "Space is running low", "Lite ledig plass"),
    ("Disk_Why", "{0} GB free. Brasscribe needs 3 GB to make a score.", "{0} GB ledig. Brasscribe trenger 3 GB for å lage et partitur."),
    ("Disk_Fix", "Free up space…", "Frigjør plass …"),
    ("Download_Title", "Full-band scores need one more step", "Partitur for fullt band trenger ett steg til"),
    ("Download_Why", "The band writer isn't downloaded yet.", "Bandskriveren er ikke lastet ned ennå."),
    ("Download_Why_Soloist", "The soloist separator isn't downloaded yet.", "Solistskilleren er ikke lastet ned ennå."),
    ("Download_Why_Instrument", "The instrument separator isn't downloaded yet.", "Instrumentskilleren er ikke lastet ned ennå."),
    ("Download_Why_Many", "{0} aren't downloaded yet.", "{0} er ikke lastet ned ennå."),
    ("Download_Why_Tools", "Brasscribe's own tools aren't installed yet.", "Verktøyene til Brasscribe er ikke installert ennå."),
    ("Model_Soloist", "the soloist separator", "solistskilleren"),  # (+) download.why's list
    ("Model_Instrument", "the instrument separator", "instrumentskilleren"),  # (+)
    ("Model_BandWriter", "the band writer", "bandskriveren"),  # (+)
    ("List_And", "{0} and {1}", "{0} og {1}"),  # (+) "a, b and c"
    ("Key_Title", "Hugging Face didn't accept the access key", "Hugging Face godtok ikke tilgangsnøkkelen"),
    ("Key_Why", "The key may have been deleted or have expired.", "Nøkkelen kan være slettet eller utløpt."),
    ("Key_Paste", "Paste a new key", "Lim inn en ny nøkkel"),
    ("Port_Title", "Brasscribe can't start", "Brasscribe kan ikke starte"),
    ("Port_Why", "Another program on this computer is in the way.", "Et annet program på denne datamaskinen står i veien."),
    ("Error_Title", "Brasscribe stopped unexpectedly", "Brasscribe stoppet uventet"),
    ("Error_Why", "It tried to start three times. Recordings on your phones are safe.", "Den prøvde å starte tre ganger. Opptakene på telefonene er trygge."),
    ("Error_Copy", "Copy details for the tech person", "Kopier detaljer til den tekniske i bandet"),
]

HEAD = """<?xml version="1.0" encoding="utf-8"?>
<!-- Generated by tools/Strings/gen_resw.py from design/server-app.md §10. Edit the script, not this file. -->
<root>
  <resheader name="resmimetype"><value>text/microsoft-resx</value></resheader>
  <resheader name="version"><value>2.0</value></resheader>
  <resheader name="reader"><value>System.Resources.ResXResourceReader, System.Windows.Forms, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089</value></resheader>
  <resheader name="writer"><value>System.Resources.ResXResourceWriter, System.Windows.Forms, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089</value></resheader>
"""

root = Path(__file__).resolve().parents[2] / "src" / "Brasscribe.Bandroom" / "Strings"
keys = [k for k, _, _ in ROWS]
assert len(keys) == len(set(keys)), "duplicate keys"
for lang, col in (("en-US", 1), ("nb-NO", 2)):
    out = root / lang / "Resources.resw"
    out.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(
        f'  <data name="{k}" xml:space="preserve">\n    <value>{escape(row[col])}</value>\n  </data>\n'
        for row in ROWS for k in [row[0]])
    out.write_text(HEAD + body + "</root>\n", encoding="utf-8")
    print(f"wrote {out} ({len(ROWS)} strings)")
