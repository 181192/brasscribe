#!/usr/bin/env python3
"""Writes the en-US and nb-NO Resources.resw of Fretscribe from one table (keeps keys in step).

Usage: python3 products/fretscribe/tools/gen_resw.py products/fretscribe/Kalli.Fretscribe/Strings
Edit the table here, not the .resw files; LocalizationTests checks the result. The program on the computer is
Bandroom (design/brands/fretscribe/brand/brand.md)."""
import sys
from pathlib import Path
from xml.sax.saxutils import escape

AUTO = "[using:Microsoft.UI.Xaml.Automation]AutomationProperties"
TIP = "[using:Microsoft.UI.Xaml.Controls]ToolTipService.ToolTip"

S = {}  # key -> (en, nb)


def add(key, en, nb):
    assert key not in S, key
    S[key] = (en, nb)


def name(uid, en, nb): add(f"{uid}.{AUTO}.Name", en, nb)
def help_(uid, en, nb): add(f"{uid}.{AUTO}.HelpText", en, nb)
def tip(uid, en, nb): add(f"{uid}.{TIP}", en, nb)
def prop(uid, p, en, nb): add(f"{uid}.{p}", en, nb)


def switch(uid):
    """A ToggleSwitch's On and Off: WinUI's own words follow Windows' language, not the app's."""
    prop(uid, "OnContent", "On", "På"); prop(uid, "OffContent", "Off", "Av")


def icon_button(uid, en, nb, hen, hnb):
    name(uid, en, nb); tip(uid, en, nb); help_(uid, hen, hnb)


def text_button(uid, en, nb, hen, hnb):
    prop(uid, "Content", en, nb); help_(uid, hen, hnb)


# ---- window and title bar ----
add("AppWindowTitle", "Fretscribe", "Fretscribe")
icon_button("BackButton", "Back", "Tilbake", "Go back (Alt+Left)", "Gå tilbake (Alt+Venstre)")
icon_button("SettingsButton", "Settings", "Innstillinger", "Your instrument, language, appearance and Bandroom on your computer (Ctrl+,)",
            "Instrumentet ditt, språk, utseende og Bandroom på datamaskinen (Ctrl+,)")
add("Back", "Back", "Tilbake")
add("Back_Home", "Home", "Hjem")
add("Back_CheckTheSong", "Check the song", "Sjekk sangen")
add("Notice_Problem", "Something went wrong, but your songs are safe. If it happens again, restart Fretscribe.",
    "Noe gikk galt, men sangene dine er trygge. Hvis det skjer igjen, start Fretscribe på nytt.")

# ---- Your songs (the pane and Home) ----
name("LibraryNav", "Your songs", "Sangene dine")
prop("LibraryHeading", "Text", "YOUR SONGS", "SANGENE DINE")
name("NewSongButton", "New song", "Ny sang"); help_("NewSongButton", "Record or open a recording", "Spill inn eller åpne et opptak")
prop("NewSongLabel", "Text", "New song", "Ny sang")
icon_button("SongOptionsButton", "More", "Mer", "Edit title or delete", "Endre tittel eller slett")
add("SongOptions_EditTitle", "Edit title", "Endre tittel")
add("SongOptions_Delete", "Delete", "Slett")
add("SongOptions_DeleteTitle", "Delete {0}?", "Slette {0}?")
add("SongOptions_DeleteThisPc", "The tab is deleted from this PC. Bandroom on your computer keeps its copy.",
    "Tabben slettes fra denne PC-en. Bandroom på datamaskinen beholder sin kopi.")
add("SongOptions_DeleteComputer", "The tab and its recording are deleted from your computer.",
    "Tabben og opptaket slettes fra datamaskinen.")
add("Song_EditTitle", "Edit title", "Endre tittel")
add("Song_SaveTitle", "Save", "Lagre")
add("Song_Cancel", "Cancel", "Avbryt")
add("Score_RenameFailed", "{0} couldn't be saved as the title. Try again.", "{0} kunne ikke lagres som tittel. Prøv igjen.")
add("Library_DeleteFailed", "Couldn't delete {0}. Is your computer on?", "Kunne ikke slette {0}. Er datamaskinen på?")
add("Library_Deleted", "Deleted {0}", "Slettet {0}")
add("Library_OnComputer", "{0} · On your computer", "{0} · På datamaskinen din")
add("Library_RecordingTitle", "Recording, {0}", "Opptak, {0}")
add("Library_SaveFailed", "Your change couldn't be saved on this PC. Check that the disk isn't full, then try again.",
    "Endringen kunne ikke lagres på denne PC-en. Sjekk at disken ikke er full, og prøv igjen.")
add("Library_Today", "Today", "I dag")
add("Library_Yesterday", "Yesterday", "I går")
add("Library_Unavailable", "Not found. Connect the drive it's on to open it.", "Finnes ikke. Koble til disken den ligger på, for å åpne den.")
add("Tab_Song", "Tab", "Tab")
add("Tab_ToCheck", "{0} notes to check", "{0} toner å sjekke")
add("Tab_ToCheck_One", "{0} note to check", "{0} tone å sjekke")

# ---- screens, as they are announced ----
for screen, en, nb in [("FirstRun", "Welcome", "Velkommen"), ("YourInstrument", "Your instrument", "Instrumentet ditt"),
                       ("Home", "Home", "Hjem"), ("WhatIsThis", "What is this?", "Hva er dette?"),
                       ("Transcribing", "Writing down the notes", "Skriver ned tonene"), ("CheckTheSong", "Check the song", "Sjekk sangen"),
                       ("Tab", "Tab", "Tab"), ("Error", "Something went wrong", "Noe gikk galt")]:
    add(f"Screen_{screen}", en, nb)

# ---- first run ----
prop("FirstRunHeading", "Text", "Tab from any recording.", "Tab fra et hvilket som helst opptak.")
prop("FirstRunPoint1Title", "Text", "Record or open a recording", "Spill inn eller åpne et opptak")
prop("FirstRunPoint1Body", "Text", "Play it, or open a song you have.", "Spill det, eller åpne en sang du har.")
prop("FirstRunPoint2Title", "Text", "Bandroom on your computer writes it down", "Bandroom på datamaskinen skriver det ned")
prop("FirstRunPoint2Body", "Text", "The notes are written down on your own computer. Nothing goes online.",
     "Tonene skrives ned på din egen datamaskin. Ingenting sendes til nettet.")
prop("FirstRunPoint3Title", "Text", "Check the notes marked ?", "Sjekk tonene merket ?")
prop("FirstRunPoint3Body", "Text", "Notes Fretscribe isn't sure about get a “?”. Listen to the bar and decide.",
     "Toner Fretscribe er usikker på, får et «?». Lytt til takten og bestem deg.")
prop("FirstRunPrivacy", "Text", "Your recordings stay on this PC and your own computer. Free, with nothing locked.",
     "Opptakene dine blir på denne PC-en og på din egen datamaskin. Gratis, og ingenting er låst.")
text_button("GetStartedButton", "Get started", "Kom i gang", "Choose your instrument, then go to Home", "Velg instrumentet ditt, og gå så til Hjem")

# ---- Your instrument ----
prop("InstrumentHeading", "Text", "Your instrument", "Instrumentet ditt")
prop("InstrumentLead", "Text", "Fretscribe remembers this for your tabs. You can change it in Settings.",
     "Fretscribe husker dette til tabbene dine. Du kan endre det i Innstillinger.")
prop("InstrumentBox", "Header", "Instrument", "Instrument")
prop("TuningBox", "Header", "Usual tuning", "Vanlig stemming")
prop("HandBox", "Header", "Which hand is on the neck?", "Hvilken hånd er på halsen?")
prop("ReadsBox", "Header", "You read", "Du leser")
text_button("InstrumentSaveButton", "Save", "Lagre", "Keep these answers for new tabs", "Bruk disse svarene til nye tabber")
text_button("InstrumentNotNowButton", "Not now", "Ikke nå", "Keep what you had: a six-string guitar in standard tuning until you answer",
            "Behold det du hadde: en seksstrengs gitar i standardstemming til du svarer")
add("Tab_Strings", "Strings", "Strenger")
add("Tab_Size", "Size", "Størrelse")
add("Tab_StringsCount", "{0} strings", "{0} strenger")
add("Tab_Hand_Note", "Tab looks the same either way.", "Tabben ser lik ut uansett.")
for i, en, nb in [("Guitar", "Guitar", "Gitar"), ("Bass", "Bass", "Bass"), ("Ukulele", "Ukulele", "Ukulele"), ("Mandolin", "Mandolin", "Mandolin")]:
    add(f"Tab_Instrument_{i}", en, nb)
for k, en, nb in [("Ukulele", "Soprano, concert or tenor", "Sopran, konsert eller tenor"), ("UkuleleBaritone", "Baritone", "Baryton"),
                  ("Mandolin", "Mandolin", "Mandolin"), ("Unknown", "Instrument", "Instrument")]:
    add(f"Tab_Kind_{k}", en, nb)
add("Tab_KindWithStrings_Guitar", "{0}-string guitar", "{0}-strengs gitar")
add("Tab_KindWithStrings_Bass", "{0}-string bass", "{0}-strengs bass")
add("Tab_KindWithStrings_Ukulele", "Ukulele", "Ukulele")
add("Tab_KindWithStrings_Mandolin", "Mandolin", "Mandolin")
for t, en, nb in [("Standard", "Standard", "Standard"), ("EbStandard", "E-flat standard (half a step down)", "Ess-standard (et halvt trinn ned)"),
                  ("DStandard", "D standard (a whole step down)", "D-standard (et helt trinn ned)"),
                  ("CStandard", "C standard (two whole steps down)", "C-standard (to hele trinn ned)"),
                  ("DropD", "Drop D", "Drop D"), ("DropC", "Drop C", "Drop C"), ("DropB", "Drop B", "Drop B"), ("DropA", "Drop A", "Drop A"),
                  ("Dadgad", "DADGAD", "DADGAD"), ("OpenG", "Open G", "Åpen G"), ("OpenD", "Open D", "Åpen D"), ("OpenE", "Open E", "Åpen E"),
                  ("Bead", "BEAD", "BEAD"), ("HighG", "High G", "Høy G"), ("LowG", "Low G", "Lav G")]:
    add(f"Tab_Tuning_{t}", en, nb)
for h, en, nb in [("Left", "Left hand on the neck (most players)", "Venstre hånd på halsen (de fleste)"),
                  ("Right", "Right hand on the neck (left-handed instrument)", "Høyre hånd på halsen (venstrehåndsinstrument)"),
                  ("RightUpsideDown", "Right hand on the neck (instrument upside down)", "Høyre hånd på halsen (instrumentet opp ned)")]:
    add(f"Tab_Hand_{h}", en, nb)
for r, en, nb in [("Tab", "Tab", "Tab"), ("TabAndNotation", "Tab and notation", "Tab og noter"), ("Notation", "Notation", "Noter")]:
    add(f"Tab_Reads_{r}", en, nb)
add("Tab_InstrumentWithStrings", "{0}, {1} strings", "{0}, {1} strenger")
add("Tab_InstrumentValue", "{0} · {1}", "{0} · {1}")

# ---- Home ----
prop("HomeHeading", "Text", "Turn a recording into tab.", "Gjør et opptak om til tab.")
prop("HomeIntro", "Text", "Play it, record it, or open a file. Bandroom on your computer writes down the notes.",
     "Spill det, ta det opp, eller åpne en fil. Bandroom på datamaskinen skriver ned tonene.")
prop("RecordMicTitle", "Text", "Record", "Spill inn")
prop("RecordMicBody", "Text", "Play it in the room, with the microphone", "Spill det i rommet, med mikrofonen")
text_button("RecordMicButton", "Record", "Spill inn", "Record with the microphone (Ctrl+Shift+R)", "Ta opp med mikrofonen (Ctrl+Shift+R)")
name("ImportButton", "Open a recording", "Åpne et opptak"); help_("ImportButton", "Open an audio or video file (Ctrl+O)", "Åpne en lyd- eller videofil (Ctrl+O)")
prop("ImportTitle", "Text", "Open a recording", "Åpne et opptak")
prop("ImportBody", "Text", "MP3, WAV, M4A, FLAC or a video", "MP3, WAV, M4A, FLAC eller en video")
name("RecordSystemButton", "Record what's playing", "Ta opp det som spilles"); help_("RecordSystemButton", "Record everything this PC plays", "Ta opp alt denne PC-en spiller")
prop("RecordSystemTitle", "Text", "Record what's playing", "Ta opp det som spilles")
prop("RecordSystemBody", "Text", "Sound from another app on this PC", "Lyd fra en annen app på denne PC-en")
name("DecodingProgress", "Reading the file", "Leser filen")
name("RecordingTime", "Recording time", "Opptakstid")
name("LevelMeter", "Input level", "Inngangsnivå")
text_button("StopRecordingButton", "Stop recording", "Stopp opptaket", "Stop and continue with the recording (Ctrl+Shift+R)", "Stopp og gå videre med opptaket (Ctrl+Shift+R)")
prop("CaptureNotice", "Title", "Nothing was heard", "Ingenting ble hørt")
prop("StartError", "Title", "That didn't work", "Det gikk ikke")
prop("HomeSongsHeading", "Text", "YOUR SONGS", "SANGENE DINE")
name("SongCards", "Your songs", "Sangene dine")
prop("HomeEmpty", "Text", "Nothing written down yet. Record a riff or open a recording.", "Ingenting er skrevet ned ennå. Spill inn et riff eller åpne et opptak.")
add("Tab_Error_ScoreFile", "{0} is sheet music, not a recording. Fretscribe writes tab from what it hears: open a recording, or record it.",
    "{0} er noter, ikke et opptak. Fretscribe skriver tab fra det den hører: åpne et opptak, eller spill det inn.")

# ---- What is this? ----
prop("WhatHeading", "Text", "What is this?", "Hva er dette?")
prop("WhatIntro", "Text", "Your answer decides how Fretscribe listens.", "Svaret ditt bestemmer hvordan Fretscribe lytter.")
name("WhatOptions", "What is this?", "Hva er dette?")
prop("WhatWhere", "Text", "Bandroom on your computer writes down the notes. The recording is not sent online.",
     "Bandroom på datamaskinen skriver ned tonene. Opptaket sendes ikke til nettet.")
prop("WhatWhereNeeded", "Text", "Bandroom on your computer writes down the notes.", "Bandroom på datamaskinen skriver ned tonene.")
text_button("WhatCancelButton", "Cancel", "Avbryt", "Back to Home; the recording is kept", "Tilbake til Hjem; opptaket beholdes")
text_button("ContinueButton", "Continue", "Fortsett", "Write down the notes", "Skriv ned tonene")
add("Tab_What_Instrument", "Just my instrument", "Bare instrumentet mitt")
add("Tab_What_Instrument_Desc", "One instrument playing, with nothing else.", "Ett instrument som spiller, uten noe annet.")
add("Tab_What_Song", "A full song", "En hel sang")
add("Tab_What_Song_Desc_Guitar", "A band or a record. Fretscribe picks out the guitar.", "Et band eller en plate. Fretscribe plukker ut gitaren.")
add("Tab_What_Song_Desc_Bass", "A band or a record. Fretscribe picks out the bass.", "Et band eller en plate. Fretscribe plukker ut bassen.")
add("Tab_What_Song_Desc_Ukulele", "A band or a record. This only works when no guitar is playing: in a song, Fretscribe can't tell a ukulele from a guitar.",
    "Et band eller en plate. Dette virker bare når ingen gitar spiller: i en sang kan ikke Fretscribe skille en ukulele fra en gitar.")
add("Tab_What_Song_Desc_Mandolin", "A band or a record. This only works when no guitar is playing: in a song, Fretscribe can't tell a mandolin from a guitar.",
    "Et band eller en plate. Dette virker bare når ingen gitar spiller: i en sang kan ikke Fretscribe skille en mandolin fra en gitar.")
add("Tab_What_NoRecording", "This recording is no longer on this PC. Open it again from Home.", "Dette opptaket er ikke lenger på denne PC-en. Åpne det på nytt fra Hjem.")
add("Tab_What_ConnectFirst", "Connect your computer to continue.", "Koble til datamaskinen for å fortsette.")
add("Tab_What_Asking", "Asking your computer…", "Spør datamaskinen …")
add("Tab_What_ChooseOne", "Choose what the recording is.", "Velg hva opptaket er.")
add("Tab_TooOld_Guitar", "Bandroom on your computer is too old to write guitar tabs. Update it there.",
    "Bandroom på datamaskinen er for gammel til å skrive gitartab. Oppdater den der.")
add("Tab_TooOld_Bass", "Bandroom on your computer is too old to write this tab. Update it there.",
    "Bandroom på datamaskinen er for gammel til å skrive denne tabben. Oppdater den der.")
add("Tab_TooOld_Ukulele", "Bandroom on your computer is too old to write ukulele tabs. Update it there.",
    "Bandroom på datamaskinen er for gammel til å skrive ukuleletab. Oppdater den der.")
add("Tab_TooOld_Mandolin", "Bandroom on your computer is too old to write mandolin tabs. Update it there.",
    "Bandroom på datamaskinen er for gammel til å skrive mandolintab. Oppdater den der.")

# ---- writing down the notes ----
name("TranscribeProgress", "Writing down the notes", "Skriver ned tonene")
prop("TranscribeWhere", "Text", "On your computer", "På datamaskinen")
text_button("CancelTranscriptionButton", "Cancel", "Avbryt", "Stop writing it down (asks first)", "Slutt å skrive det ned (spør først)")
prop("TranscribeLeaveNote", "Text", "The tab is in Your songs when it is ready.", "Tabben ligger i Sangene dine når den er klar.")
add("CancelDialog_Title", "Stop writing it down?", "Slutte å skrive det ned?")
add("CancelDialog_Content", "The recording stays on this PC, so you can start again.", "Opptaket blir liggende på denne PC-en, så du kan starte på nytt.")
add("CancelDialog_Keep", "Keep going", "Fortsett")
add("CancelDialog_Stop", "Stop", "Stopp")
add("Transcribe_CancelConfirm", "Stop writing it down? The recording stays on this PC.", "Slutte å skrive det ned? Opptaket blir liggende på denne PC-en.")
add("Transcribe_Cancelled", "Stopped. The recording is kept.", "Stoppet. Opptaket beholdes.")
add("Transcribe_Device", "Running on {0}", "Kjører på {0}")
add("Transcribe_Done", "The tab is ready", "Tabben er klar")
add("Transcribe_Error", "Stopped: {0}", "Stoppet: {0}")
add("Transcribe_Eta_Hours", "About {0} hours left", "Omtrent {0} timer igjen")
add("Transcribe_Eta_Minutes", "About {0} minutes left", "Omtrent {0} minutter igjen")
add("Transcribe_Eta_UnderMinute", "Less than a minute left", "Under ett minutt igjen")
add("Transcribe_Eta_Unknown", "Working out the time left", "Regner ut hvor lang tid som er igjen")
add("Transcribe_Failed", "The tab couldn't be written", "Tabben kunne ikke skrives")
add("Transcribe_Overline", "Step {0} of {1} · {2}", "Steg {0} av {1} · {2}")
add("Transcribe_ProgressAnnouncement", "{0} percent. {1}. {2}", "{0} prosent. {1}. {2}")
add("Transcribe_Rearranging", "Writing it down again with your change", "Skriver det ned på nytt med endringen din")
add("Transcribe_Started", "Writing down {0} as {1}", "Skriver ned {0} som {1}")
add("Transcribe_StepCurrent", "{0}, now", "{0}, nå")
add("Transcribe_StepDone", "{0}, done", "{0}, ferdig")
add("Transcribe_StepPending", "{0}, to come", "{0}, kommer")
for key, en, nb in [("Ready", "Getting the recording ready", "Gjør opptaket klart"), ("Beats", "Finding the beat", "Finner pulsen"),
                    ("Separate", "Picking out your instrument", "Plukker ut instrumentet ditt"), ("SeparateSoloist", "Picking out your instrument", "Plukker ut instrumentet ditt"),
                    ("Notes", "Writing down the notes", "Skriver ned tonene"), ("Arrange", "Placing the notes on the strings", "Legger tonene på strengene"),
                    ("Layout", "Laying out the tab", "Setter opp tabben")]:
    add(f"Transcribe_Step_{key}", en, nb)
for key, en, nb in [("Upload", "Getting the recording ready", "Gjør opptaket klart"), ("Beats", "Finding the beat", "Finner pulsen"),
                    ("Separate", "Picking out your instrument", "Plukker ut instrumentet ditt"), ("Notes", "Writing down the notes", "Skriver ned tonene"),
                    ("Arrange", "Placing the notes on the strings", "Legger tonene på strengene"), ("Engrave", "Laying out the tab", "Setter opp tabben"),
                    ("Working", "Working", "Arbeider")]:
    add(f"Transcribe_Stage_{key}", en, nb)

# ---- Check the song ----
prop("CheckHeading", "Text", "Check the song", "Sjekk sangen")
prop("CheckReading", "Text", "Reading what Fretscribe heard…", "Leser det Fretscribe hørte …")
name("CheckReadingProgress", "Reading what Fretscribe heard", "Leser det Fretscribe hørte")
prop("CheckLead", "Text", "This is what Fretscribe heard. If something here is wrong, the frets are wrong too.",
     "Dette er det Fretscribe hørte. Er noe feil her, blir båndene feil også.")
prop("CheckLater", "Text", "You can change this later.", "Du kan endre dette senere.")
text_button("ShowTabButton", "Show the tab", "Vis tabben", "Open the tab to read and practise it", "Åpne tabben for å lese og øve på den")
add("Tab_Check_Missing", "What Fretscribe heard can't be shown right now. {0}", "Det Fretscribe hørte kan ikke vises akkurat nå. {0}")
add("Tab_Check_NoComputer", "It was written on your computer, which isn't connected.", "Den ble skrevet på datamaskinen, som ikke er tilkoblet.")
add("Tab_Check_Connect", "To change these, connect your computer.", "Koble til datamaskinen for å endre dette.")
add("Tab_Check_Tuning", "Tuning", "Stemming")
add("Tab_Check_SoundsLike", "Sounds like {0}. Written for {1}.", "Høres ut som {0}. Skrevet for {1}.")
add("Tab_Check_Use", "Use {0}", "Bruk {0}")
add("Tab_Check_Capo", "Capo", "Capo")
add("Tab_Check_Capo_Change", "Change the capo", "Endre capo")
add("Tab_Check_Capo_Keeps", "Changing the capo changes the frets. The notes stay the same.", "Endrer du capo, endres båndene. Tonene er de samme.")
add("Tab_Check_Capo_None", "No capo", "Ingen capo")
add("Tab_Check_Capo_On", "Capo on fret {0}", "Capo på bånd {0}")
add("Tab_Check_Octave", "Octave", "Oktav")
add("Tab_Check_Octave_Down", "Written one octave lower than it was heard.", "Skrevet én oktav lavere enn det ble hørt.")
add("Tab_Check_Octave_TwoDown", "Written two octaves lower than it was heard.", "Skrevet to oktaver lavere enn det ble hørt.")
add("Tab_Check_Octave_Up", "Written one octave higher than it was heard.", "Skrevet én oktav høyere enn det ble hørt.")
add("Tab_Check_Octave_AsHeard", "Written as it was heard, as you chose.", "Skrevet slik det ble hørt, slik du valgte.")
add("Tab_Check_Octave_ChosenDown", "Written one octave lower, as you chose.", "Skrevet én oktav lavere, slik du valgte.")
add("Tab_Check_Octave_ChosenUp", "Written one octave higher, as you chose.", "Skrevet én oktav høyere, slik du valgte.")
add("Tab_Check_Octave_Notes", "{0} notes are written an octave lower than they were heard.", "{0} toner er skrevet en oktav lavere enn de ble hørt.")
add("Tab_Check_Octave_Notes_One", "{0} note is written an octave lower than it was heard.", "{0} tone er skrevet en oktav lavere enn den ble hørt.")
add("Tab_Check_AsHeard", "Write it as it was heard", "Skriv det slik det ble hørt")
add("Tab_Check_Octave_Auto", "Let Fretscribe choose", "La Fretscribe velge")
add("Tab_Check_Reference", "Reference pitch", "Kammertone")
add("Tab_Check_Reference_Sharp", "A little sharp of concert pitch (A = 440): {0} cents.", "Litt høyere enn kammertonen (A = 440): {0} cent.")
add("Tab_Check_Reference_Flat", "A little flat of concert pitch (A = 440): {0} cents.", "Litt lavere enn kammertonen (A = 440): {0} cent.")
add("Tab_Check_Reference_Allowed", "Fretscribe allowed for it.", "Fretscribe tok hensyn til det.")
add("Tab_Check_KeyTempo", "Key and tempo", "Toneart og tempo")
add("Tab_Check_KeyTempo_Value", "{0} · ♩ = {1} · {2}/{3}", "{0} · ♩ = {1} · {2}/{3}")
add("Tab_Check_KeyTempo_Spoken", "{0}, {1} beats a minute, {2} beats in a bar", "{0}, {1} slag i minuttet, {2} slag i takten")
add("Tab_Check_Notes", "Notes to check", "Toner å sjekke")
add("Tab_Check_Marked", "{0} notes marked ?", "{0} toner merket ?")
add("Tab_Check_Marked_One", "{0} note marked ?", "{0} tone merket ?")
add("Tab_Check_NoPlace_Title", "Notes with no place", "Toner uten plass")
add("Tab_Check_NoPlace", "{0} notes with no place on your instrument. Is the tuning right?", "{0} toner uten plass på instrumentet ditt. Er stemmingen riktig?")
add("Tab_Check_NoPlace_One", "{0} note with no place on your instrument. Is the tuning right?", "{0} tone uten plass på instrumentet ditt. Er stemmingen riktig?")
add("Tab_Check_LeftOut_Title", "Notes left out", "Utelatte toner")
add("Tab_Check_LeftOut", "{0} notes left out. They can't be played together with the rest.", "{0} toner er utelatt. De kan ikke spilles sammen med resten.")
add("Tab_Check_LeftOut_One", "{0} note left out. It can't be played together with the rest.", "{0} tone er utelatt. Den kan ikke spilles sammen med resten.")
add("Tab_Check_Added_Title", "Notes added", "Toner lagt til")
add("Tab_Check_Added", "{0} notes added to complete a chord. They are marked ?.", "{0} toner lagt til for å fullføre en akkord. De er merket ?.")
add("Tab_Check_Added_One", "{0} note added to complete a chord. It is marked ?.", "{0} tone lagt til for å fullføre en akkord. Den er merket ?.")

# ---- the tab ----
name("TabPage", "Tab", "Tab")
prop("TabReading", "Text", "Opening the tab…", "Åpner tabben …")
name("TabReadingProgress", "Opening the tab", "Åpner tabben")
add("Tab_Failed", "This tab can't be shown. Go back and open it again.", "Denne tabben kan ikke vises. Gå tilbake og åpne den på nytt.")
add("Tab_Chip", "{0} · {1}", "{0} · {1}")
add("Tab_NoCapo", "no capo", "uten capo")
add("Tab_Capo", "capo {0}", "capo {0}")
add("Tab_Marked", "{0} notes marked ?", "{0} toner merket ?")
add("Tab_Marked_One", "{0} note marked ?", "{0} tone merket ?")
add("Tab_NoPlaceCount", "{0} notes with no place", "{0} toner uten plass")
add("Tab_NoPlaceCount_One", "{0} note with no place", "{0} tone uten plass")
add("Tab_Zoom", "{0}%", "{0} %")
add("Tab_BarBeat", "Bar {0}, beat {1}", "Takt {0}, slag {1}")
add("Tab_PickupBeat", "The pickup bar, beat {0}", "Opptakten, slag {0}")
add("Tab_Mark_NotSure", "Bar {0}, beat {1}: Fretscribe isn't sure about this one. Play the bar slowly.",
    "Takt {0}, slag {1}: Fretscribe er ikke sikker på denne. Spill takten sakte.")
add("Tab_Mark_NoPlace", "Bar {0}, beat {1}: a note here has no place on your instrument. Is the tuning right?",
    "Takt {0}, slag {1}: en tone her har ingen plass på instrumentet ditt. Er stemmingen riktig?")
text_button("NextMarkButton", "Next ?", "Neste ?", "Go to the next note marked ? or !", "Gå til neste tone merket ? eller !")
icon_button("ZoomOutButton", "Smaller", "Mindre", "Make the tab smaller", "Gjør tabben mindre")
icon_button("ZoomInButton", "Larger", "Større", "Make the tab larger", "Gjør tabben større")
icon_button("FullScreenButton", "Full screen", "Fullskjerm", "The tab takes the whole screen (F11; Esc leaves)", "Tabben fyller hele skjermen (F11; Esc går ut)")
icon_button("LeaveFullScreenButton", "Leave full screen", "Gå ut av fullskjerm", "The header and the player come back (Esc or F11)", "Toppen og spilleren kommer tilbake (Esc eller F11)")
icon_button("ToStartButton", "To the start", "Til starten", "Back to the start of the repeat, or of the song", "Tilbake til starten av gjentakelsen, eller av sangen")
icon_button("PreviousBarButton", "Previous bar", "Forrige takt", "A bar back (Left)", "En takt tilbake (Venstre)")
icon_button("NextBarButton", "Next bar", "Neste takt", "A bar on (Right)", "En takt fram (Høyre)")
icon_button("SlowerButton", "Slower", "Saktere", "Play the recording slower; the pitch stays", "Spill opptaket saktere; tonehøyden er den samme")
icon_button("FasterButton", "Faster", "Raskere", "Play the recording faster; the pitch stays", "Spill opptaket raskere; tonehøyden er den samme")
text_button("FetchRecordingButton", "Get it from your computer", "Hent det fra datamaskinen", "Copy the recording from Bandroom to practise with it",
            "Kopier opptaket fra Bandroom for å øve med det")
add("Tab_Practice_Play", "Play", "Spill")
add("Tab_Practice_Pause", "Pause", "Pause")
add("Tab_Practice_Speed", "{0}%", "{0} %")
add("Tab_Practice_Repeat", "Repeat bars", "Gjenta takter")
add("Tab_Practice_RepeatOn", "Repeating {0}–{1}", "Gjentar {0}–{1}")
add("Tab_Practice_RepeatOn_One", "Repeating {0}", "Gjentar {0}")
add("Tab_Practice_RepeatTitle", "Repeat bars", "Gjenta takter")
add("Tab_Practice_From", "From bar", "Fra takt")
add("Tab_Practice_To", "To bar", "Til takt")
add("Tab_Practice_RepeatSet", "Repeat", "Gjenta")
add("Tab_Practice_RepeatStop", "Stop repeating", "Slutt å gjenta")
add("Tab_Practice_NoBeats", "Fretscribe can't follow the recording in this tab. You can still read it.",
    "Fretscribe kan ikke følge opptaket i denne tabben. Du kan fortsatt lese den.")
for state, en, nb in [("Looking", "Looking for the recording…", "Ser etter opptaket …"),
                      ("NotHere", "The recording is not on this PC.", "Opptaket er ikke på denne PC-en."),
                      ("Getting", "Getting the recording from your computer…", "Henter opptaket fra datamaskinen …"),
                      ("Gone", "Your computer doesn't have the recording any more. You can still read the tab.",
                       "Datamaskinen har ikke opptaket lenger. Du kan fortsatt lese tabben."),
                      ("NoAnswer", "The recording didn't come. Is your computer on?", "Opptaket kom ikke. Er datamaskinen på?"),
                      ("UpdateApp", "Update Fretscribe to get the recording from your computer.", "Oppdater Fretscribe for å hente opptaket fra datamaskinen."),
                      ("UpdateComputer", "Update Bandroom on your computer to get the recording from it.", "Oppdater Bandroom på datamaskinen for å hente opptaket derfra."),
                      ("NoRoom", "There is no room on this PC for the recording. You can still read the tab.",
                       "Det er ikke plass til opptaket på denne PC-en. Du kan fortsatt lese tabben."),
                      ("TooLarge", "The recording is too large to keep on this PC. You can still read the tab.",
                       "Opptaket er for stort til å ligge på denne PC-en. Du kan fortsatt lese tabben."),
                      ("Unplayable", "This PC can't play the recording. You can still read the tab.",
                       "Denne PC-en kan ikke spille av opptaket. Du kan fortsatt lese tabben.")]:
    add(f"Tab_Practice_{state}", en, nb)

# ---- errors ----
add("Error_ChooseAnother", "Choose another recording", "Velg et annet opptak")
add("Error_TryAgain", "Try again", "Prøv igjen")
add("Error_DetailsHeading", "Details for whoever set up the computer", "Detaljer for den som satte opp datamaskinen")
name("ErrorSteps", "What to do", "Hva du kan gjøre")
add("Error_GetUpdate", "Get the update", "Hent oppdateringen")
add("Error_GetUpdate_Help", "Opens the page with the newest Fretscribe and the newest Bandroom for your computer",
    "Åpner siden med nyeste Fretscribe og nyeste Bandroom for datamaskinen")
add("Error_ComputerUnreachable_Title", "Can't reach Bandroom on your computer", "Får ikke kontakt med Bandroom på datamaskinen")
add("Error_ComputerUnreachable_Reason", "Your recording is safe. Tabs are written on your computer, and it isn't answering.",
    "Opptaket ditt er trygt. Tabber skrives på datamaskinen, og den svarer ikke.")
add("Error_ComputerUnreachable_Step1", "Check that the computer is on and on the same network.", "Sjekk at datamaskinen er på og på samme nettverk.")
add("Error_ComputerUnreachable_Step2", "Open Bandroom on the computer.", "Åpne Bandroom på datamaskinen.")
add("Error_ComputerUnreachable_Step3", "Choose Try again.", "Velg Prøv igjen.")
add("Error_ComputerUnreachable_Details", "Start it with: scribe serve. Settings shows the address it uses. The message was: {0}",
    "Start den med: scribe serve. Innstillinger viser adressen den bruker. Meldingen var: {0}")
add("Error_ScoreFailed_Title", "The tab couldn't be written", "Tabben kunne ikke skrives")
add("Error_ScoreFailed_Reason", "Your recording is safe. Something stopped Bandroom on your computer while it worked.",
    "Opptaket ditt er trygt. Noe stoppet Bandroom på datamaskinen mens den arbeidet.")
add("Error_ScoreFailed_Step1", "Choose Try again. It often works the second time.", "Velg Prøv igjen. Det går ofte andre gang.")
add("Error_ScoreFailed_Step2", "If it stops again, try a shorter recording.", "Hvis det stopper igjen, prøv et kortere opptak.")
add("Error_RecordingUnreadable_Title", "The recording can't be read", "Opptaket kan ikke leses")
add("Error_RecordingUnreadable_Reason", "Fretscribe couldn't open the recording on this PC. It may have been moved or deleted, or another app is using it.",
    "Fretscribe fikk ikke åpnet opptaket på denne PC-en. Det kan være flyttet eller slettet, eller en annen app bruker det.")
add("Error_RecordingUnreadable_Step1", "Close other apps that use the file, then choose Try again.", "Lukk andre apper som bruker filen, og velg Prøv igjen.")
add("Error_RecordingUnreadable_Step2", "Or choose another recording.", "Eller velg et annet opptak.")
add("Error_UpdateApp_Title", "Update Fretscribe", "Oppdater Fretscribe")
add("Error_UpdateApp_Reason", "Your recording is safe. Bandroom on your computer is newer than this app, and they only work together when both are up to date.",
    "Opptaket ditt er trygt. Bandroom på datamaskinen er nyere enn denne appen, og de virker bare sammen når begge er oppdatert.")
add("Error_UpdateApp_Step1", "Update Fretscribe on this PC.", "Oppdater Fretscribe på denne PC-en.")
add("Error_UpdateApp_Step2", "Choose Try again.", "Velg Prøv igjen.")
add("Error_UpdateBandroom_Title", "Update Bandroom on your computer", "Oppdater Bandroom på datamaskinen")
add("Error_UpdateBandroom_Reason", "Your recording is safe. This app is newer than Bandroom on your computer, and they only work together when both are up to date.",
    "Opptaket ditt er trygt. Denne appen er nyere enn Bandroom på datamaskinen, og de virker bare sammen når begge er oppdatert.")
add("Error_UpdateBandroom_Step1", "Update Bandroom on the computer.", "Oppdater Bandroom på datamaskinen.")
add("Error_UpdateBandroom_Step2", "Choose Try again.", "Velg Prøv igjen.")
# What the computer answered, in the app's words (EngineErrors).
add("Error_Unreachable", "Can't reach Bandroom on your computer. Check that it is on and on the same network.",
    "Får ikke kontakt med Bandroom på datamaskinen. Sjekk at den er på og på samme nettverk.")
add("Error_Engine", "Bandroom on your computer ran into a problem. Try again.", "Bandroom på datamaskinen fikk et problem. Prøv igjen.")
add("Error_NeedsPairing", "Your computer needs pairing again. Enter the code it shows in Settings.",
    "Datamaskinen må kobles til på nytt. Skriv inn koden den viser, i Innstillinger.")
add("Error_NotFound", "Bandroom on your computer no longer has this recording. Open it again.", "Bandroom på datamaskinen har ikke dette opptaket lenger. Åpne det på nytt.")
add("Error_Options", "Bandroom on your computer couldn't use these choices. Try other choices, or update Bandroom on your computer.",
    "Bandroom på datamaskinen kunne ikke bruke disse valgene. Prøv andre valg, eller oppdater Bandroom på datamaskinen.")
add("Error_Timeout", "Your computer took too long to answer. Check that it is on and awake, then try again.",
    "Datamaskinen brukte for lang tid på å svare. Sjekk at den er på og våken, og prøv igjen.")
add("Error_TooLarge", "The recording is too large to send. Try a shorter recording.", "Opptaket er for stort til å sendes. Prøv et kortere opptak.")

# ---- starting a recording ----
add("Duration_MinutesSeconds", "{0} min {1} s", "{0} min {1} s")
add("Duration_Seconds", "{0} s", "{0} s")
add("Start_Error_Capture", "Recording couldn't start: {0}", "Opptaket kunne ikke starte: {0}")
add("Start_Error_ChooseApp", "Choose the app to record first.", "Velg først appen som skal tas opp.")
add("Start_Error_Decode", "{0} can't be read. Try another file, or record it instead.", "{0} kan ikke leses. Prøv en annen fil, eller ta det opp i stedet.")
add("Start_Error_Link", "Links to streaming sites can't be downloaded. Play the music and record it instead.",
    "Lenker til strømmetjenester kan ikke lastes ned. Spill musikken og ta den opp i stedet.")
add("Start_Error_MicrophonePermission", "Fretscribe may not use the microphone. Allow it in Windows Settings, Privacy, Microphone.",
    "Fretscribe har ikke lov til å bruke mikrofonen. Gi tilgang i Windows-innstillinger, Personvern, Mikrofon.")
add("Start_Error_NeedsCodec", "Windows couldn't read {0}. Files like this may need Web Media Extensions from the Microsoft Store. Try an MP3, WAV or MP4 file, or record it instead.",
    "Windows kunne ikke lese {0}. Slike filer kan trenge Webmedieutvidelser fra Microsoft Store. Prøv en MP3-, WAV- eller MP4-fil, eller ta det opp i stedet.")
add("Start_Error_Score", "{0} can't be opened as a tab.", "{0} kan ikke åpnes som tab.")
add("Start_Error_TooShort", "The recording is shorter than a second. Try again.", "Opptaket er kortere enn ett sekund. Prøv igjen.")
add("Start_Error_Unsupported", "{0} can't be opened. Try an MP3, WAV, M4A or MP4 file.", "{0} kan ikke åpnes. Prøv en MP3-, WAV-, M4A- eller MP4-fil.")
add("Start_Imported", "Opened {0}, {1}", "Åpnet {0}, {1}")
add("Start_Level_Good", "Input level, good", "Inngangsnivå, bra")
add("Start_Level_Low", "Input level, low", "Inngangsnivå, lavt")
add("Start_Level_Silent", "Input level, silent", "Inngangsnivå, stille")
add("Start_Level_TooLoud", "Input level, too loud", "Inngangsnivå, for høyt")
add("Start_Notice_Interrupted", "Recording stopped by itself: the device was disconnected, or the disk is full. Choose Stop to keep what was recorded.",
    "Opptaket stoppet av seg selv: enheten ble koblet fra, eller disken er full. Velg Stopp for å beholde det som ble tatt opp.")
add("Start_Notice_NothingPlaying", "Only silence is arriving. Check that something is playing. Streaming apps usually block recording.",
    "Det kommer bare stillhet. Sjekk at noe spiller. Strømmeapper stopper som regel opptak.")
add("Start_Notice_SilenceWhilePlaying", "The app is playing, but Fretscribe hears only silence. Streaming apps usually block recording. Open a file instead, or record with the microphone.",
    "Appen spiller, men Fretscribe hører bare stillhet. Strømmeapper stopper som regel opptak. Åpne en fil i stedet, eller ta opp med mikrofonen.")
add("Start_Notice_TooLoud", "The sound is too loud and distorts. Turn the volume down a little.", "Lyden er for høy og blir forvrengt. Skru ned volumet litt.")
add("Start_RecordingName", "Recording", "Opptak")
add("Start_RecordingStarted", "Recording started", "Opptaket har startet")
add("Start_RecordingStopped", "Recording stopped, {0}", "Opptaket er stoppet, {0}")

# ---- Settings ----
prop("SettingsDialog", "Title", "Settings", "Innstillinger")
prop("SettingsDialog", "CloseButtonText", "Close", "Lukk")
prop("SettingsYouHeading", "Text", "Your instrument", "Instrumentet ditt")
prop("InstrumentRowLabel", "Text", "New tabs are written for", "Nye tabber skrives for")
text_button("InstrumentChangeButton", "Change", "Endre", "Change your instrument, its tuning and what you read", "Endre instrumentet, stemmingen og hva du leser")
prop("SettingsLanguageHeading", "Text", "Language", "Språk")
prop("LanguageBox", "Header", "App language", "Appspråk")
prop("LanguageSystem", "Content", "Same as Windows", "Samme som Windows")
prop("LanguageRestartNote", "Text", "A new language is used the next time you start the app.", "Nytt språk tas i bruk neste gang du starter appen.")
prop("SettingsAccessibilityHeading", "Text", "Display", "Visning")
prop("AppearanceBox", "Header", "Appearance", "Utseende")
prop("AppearanceSystem", "Content", "Match system", "Følg systemet")
prop("AppearanceLight", "Content", "Light", "Lyst")
prop("AppearanceDark", "Content", "Dark", "Mørkt")
prop("AppearanceContrastNote", "Text", "Your contrast theme is on, so Windows chooses the colours.", "Kontrasttemaet ditt er på, så Windows velger fargene.")
prop("ReduceMotionSwitch", "Header", "Reduce motion", "Mindre bevegelse"); switch("ReduceMotionSwitch")
help_("ReduceMotionSwitch", "Pages change without sliding", "Sidene skifter uten å gli")
prop("SettingsEngineHeading", "Text", "Bandroom on your computer", "Bandroom på datamaskinen")
text_button("FindEnginesButton", "Find on this network", "Finn på dette nettverket", "Look for computers running Bandroom on the same network",
            "Se etter datamaskiner som kjører Bandroom på samme nettverk")
name("DiscoveredEnginesList", "Computers running Bandroom on this network", "Datamaskiner som kjører Bandroom på dette nettverket")
prop("PairingCodeBox", "Header", "Code", "Kode")
prop("PairingCodeBox", "PlaceholderText", "The six digits your computer shows", "De seks sifrene datamaskinen viser")
text_button("ConnectButton", "Connect", "Koble til", "Open Bandroom on your computer and choose Pair a device, then type the code here",
            "Åpne Bandroom på datamaskinen og velg Koble til en enhet, og skriv inn koden her")
text_button("AskComputerButton", "Ask on the computer instead", "Spør på datamaskinen i stedet", "No code to type: choose Allow on the computer",
            "Ingen kode å skrive: velg Godkjenn på datamaskinen")
prop("MatchCodeLabel", "Text", "The computer shows the same number", "Datamaskinen viser det samme tallet")
text_button("CancelAskButton", "Stop waiting", "Slutt å vente", "Stop waiting for the computer to allow this PC", "Slutt å vente på at datamaskinen godkjenner denne PC-en")
text_button("UnpairButton", "Forget this computer", "Glem denne datamaskinen", "The computer forgets this PC, and this PC forgets the computer",
            "Datamaskinen glemmer denne PC-en, og denne PC-en glemmer datamaskinen")
prop("EngineDetails", "Header", "Details for whoever set up the computer", "Detaljer for den som satte opp datamaskinen")
name("EngineDetails", "Details for whoever set up the computer", "Detaljer for den som satte opp datamaskinen")
prop("EngineAddressBox", "Header", "Address", "Adresse")
prop("EngineAddressBox", "PlaceholderText", "http://127.0.0.1:8765", "http://127.0.0.1:8765")
prop("SettingsAboutHeading", "Text", "About", "Om")
prop("AboutText", "Text", "Fretscribe is a non-commercial project. Tab and notation: alphaTab (MPL-2.0). The faces are Atkinson Hyperlegible Next (SIL OFL 1.1) and Fretscribe Tab (SIL OFL 1.1).",
     "Fretscribe er et ikke-kommersielt prosjekt. Tab og noter: alphaTab (MPL-2.0). Skriftene er Atkinson Hyperlegible Next (SIL OFL 1.1) og Fretscribe Tab (SIL OFL 1.1).")
add("Settings_AppVersion", "Version {0}", "Versjon {0}")
add("Settings_Engine_AskBusy", "Other devices are waiting on the computer. Try again in a couple of minutes.", "Andre enheter venter på datamaskinen. Prøv igjen om et par minutter.")
add("Settings_Engine_AskDenied", "The computer didn't allow this PC. You can ask again.", "Datamaskinen godkjente ikke denne PC-en. Du kan spørre på nytt.")
add("Settings_Engine_AskExpired", "The computer didn't answer in time. You can ask again.", "Datamaskinen svarte ikke i tide. Du kan spørre på nytt.")
add("Settings_Engine_AskWaiting", "On the computer, choose Allow when it shows this number: {0}", "Velg Godkjenn på datamaskinen når den viser dette tallet: {0}")
add("Settings_Engine_Chosen", "Using Bandroom on {0}. Type the six-digit code it shows, then choose Connect.",
    "Bruker Bandroom på {0}. Skriv inn den sekssifrede koden den viser, og velg Koble til.")
add("Settings_Engine_ChosenPaired", "Using Bandroom on {0}. This PC is already paired with it.", "Bruker Bandroom på {0}. Denne PC-en er allerede koblet til den.")
add("Settings_Engine_CodeWrong", "That code didn't work. Check the six digits on the computer and try again.",
    "Den koden virket ikke. Sjekk de seks sifrene på datamaskinen, og prøv igjen.")
add("Settings_Engine_Connected", "Connected to Bandroom on {0}.", "Koblet til Bandroom på {0}.")
add("Settings_Engine_Failed", "Something went wrong talking to your computer. Try again.", "Noe gikk galt i kontakten med datamaskinen. Prøv igjen.")
add("Settings_Engine_Forgotten", "The computer no longer recognises this PC. Type the six digits it shows, or ask on the computer instead.",
    "Datamaskinen kjenner ikke igjen denne PC-en lenger. Skriv inn de seks sifrene den viser, eller spør på datamaskinen i stedet.")
add("Settings_Engine_FoundMany", "Found {0} computers running Bandroom. Choose one.", "Fant {0} datamaskiner som kjører Bandroom. Velg én.")
add("Settings_Engine_FoundOne", "Found Bandroom on {0}. Choose it to use it.", "Fant Bandroom på {0}. Velg den for å bruke den.")
add("Settings_Engine_Locked", "Too many wrong codes. Wait a moment, or ask on the computer instead.", "For mange feil koder. Vent litt, eller spør på datamaskinen i stedet.")
add("Settings_Engine_NeedsCode", "Your computer asks for a code. Type the six digits it shows, or ask on the computer instead.",
    "Datamaskinen ber om en kode. Skriv inn de seks sifrene den viser, eller spør på datamaskinen i stedet.")
add("Settings_Engine_NoneFound", "No computer running Bandroom was found on this network. Check that Bandroom on the computer says Running, and that both are on the same Wi-Fi.",
    "Fant ingen datamaskin som kjører Bandroom på dette nettverket. Sjekk at Bandroom på datamaskinen sier at den kjører, og at begge er på samme wifi.")
add("Settings_Engine_Searching", "Looking for Bandroom on your network…", "Ser etter Bandroom på nettverket …")
add("Settings_Engine_Unpaired", "This PC is no longer paired with Bandroom on {0}.", "Denne PC-en er ikke lenger koblet til Bandroom på {0}.")
add("Settings_Engine_Unreachable", "Couldn't reach your computer. Check that Bandroom is running there and that both are on the same network.",
    "Fikk ikke kontakt med datamaskinen. Sjekk at Bandroom kjører der, og at begge er på samme nettverk.")
add("Settings_Link_Invalid", "That link isn't a Bandroom pairing link.", "Den lenken er ikke en tilkoblingslenke fra Bandroom.")
add("Settings_Link_Looking", "Looking for Bandroom on {0} …", "Leter etter Bandroom på {0} …")
add("Settings_Link_Newer", "That link is from a newer Bandroom. Update this app, then try again.", "Lenken er fra en nyere Bandroom. Oppdater appen, og prøv igjen.")
add("Settings_Link_NotFound", "Couldn't find Bandroom on {0}. Check that this PC is on the same network as the computer.",
    "Fant ikke Bandroom på {0}. Sjekk at denne PC-en er på samme nettverk som datamaskinen.")

# ---- the connection row ----
add("Connection_Connect", "Connect", "Koble til")
add("Connection_ConnectHelp", "Connect this PC to Bandroom on your computer", "Koble denne PC-en til Bandroom på datamaskinen")
add("Connection_Connected", "Connected to Bandroom on {0}", "Koblet til Bandroom på {0}")
add("Connection_DetailsAddress", "Address: {0}", "Adresse: {0}")
add("Connection_DetailsLastSeen", "Last answered: {0}", "Svarte sist: {0}")
add("Connection_DetailsServerId", "Server id: {0}", "Server-ID: {0}")
add("Connection_GetUpdate", "Get the update", "Hent oppdateringen")
add("Connection_GetUpdateHelp", "Opens the page with the newest Fretscribe and the newest Bandroom for your computer",
    "Åpner siden med nyeste Fretscribe og nyeste Bandroom for datamaskinen")
add("Connection_NeedsPairing", "The computer no longer recognises this PC.", "Datamaskinen kjenner ikke igjen denne PC-en lenger.")
add("Connection_Offline", "Not connected. Tabs are written on your computer: connect it to write a new one.",
    "Ikke tilkoblet. Tabber skrives på datamaskinen: koble den til for å skrive en ny.")
add("Connection_PairAgain", "Pair this PC again", "Koble til PC-en på nytt")
add("Connection_Reconnecting", "Looking for Bandroom on {0} …", "Leter etter Bandroom på {0} …")
add("Connection_ThisPc", "this PC", "denne PC-en")
add("Connection_UpdateApp", "Update Fretscribe. Bandroom on {0} is newer than this app, and they only work together when both are up to date.",
    "Oppdater Fretscribe. Bandroom på {0} er nyere enn denne appen, og de virker bare sammen når begge er oppdatert.")
add("Connection_UpdateBandroom", "Update Bandroom on {0}. This app is newer than Bandroom there, and they only work together when both are up to date.",
    "Oppdater Bandroom på {0}. Denne appen er nyere enn Bandroom der, og de virker bare sammen når begge er oppdatert.")
add("Connection_UpdateBandroomHere", "Update Bandroom on this PC. It is older than this app, and they only work together when both are up to date.",
    "Oppdater Bandroom på denne PC-en. Den er eldre enn denne appen, og de virker bare sammen når begge er oppdatert.")
add("Connection_YourComputer", "your computer", "datamaskinen")


HEADER = """<?xml version="1.0" encoding="utf-8"?>
<root>
  <xsd:schema id="root" xmlns="" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:msdata="urn:schemas-microsoft-com:xml-msdata">
    <xsd:import namespace="http://www.w3.org/XML/1998/namespace" />
    <xsd:element name="root" msdata:IsDataSet="true">
      <xsd:complexType>
        <xsd:choice maxOccurs="unbounded">
          <xsd:element name="data">
            <xsd:complexType>
              <xsd:sequence>
                <xsd:element name="value" type="xsd:string" minOccurs="0" msdata:Ordinal="1" />
                <xsd:element name="comment" type="xsd:string" minOccurs="0" msdata:Ordinal="2" />
              </xsd:sequence>
              <xsd:attribute name="name" type="xsd:string" use="required" msdata:Ordinal="1" />
              <xsd:attribute ref="xml:space" />
            </xsd:complexType>
          </xsd:element>
          <xsd:element name="resheader">
            <xsd:complexType>
              <xsd:sequence>
                <xsd:element name="value" type="xsd:string" minOccurs="0" msdata:Ordinal="1" />
              </xsd:sequence>
              <xsd:attribute name="name" type="xsd:string" use="required" />
            </xsd:complexType>
          </xsd:element>
        </xsd:choice>
      </xsd:complexType>
    </xsd:element>
  </xsd:schema>
  <resheader name="resmimetype">
    <value>text/microsoft-resx</value>
  </resheader>
  <resheader name="version">
    <value>2.0</value>
  </resheader>
  <resheader name="reader">
    <value>System.Resources.ResXResourceReader, System.Windows.Forms, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089</value>
  </resheader>
  <resheader name="writer">
    <value>System.Resources.ResXResourceWriter, System.Windows.Forms, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089</value>
  </resheader>
"""

out = Path(sys.argv[1])
for idx, lang in ((0, "en-US"), (1, "nb-NO")):
    lines = [HEADER]
    for k in sorted(S):
        lines.append(f'  <data name="{escape(k, {chr(34): "&quot;"})}" xml:space="preserve">\n    <value>{escape(S[k][idx])}</value>\n  </data>\n')
    lines.append("</root>\n")
    d = out / lang
    d.mkdir(parents=True, exist_ok=True)
    (d / "Resources.resw").write_text("".join(lines), encoding="utf-8")
print(len(S), "keys")
