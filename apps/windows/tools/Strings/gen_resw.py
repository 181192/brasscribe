#!/usr/bin/env python3
"""Writes the en-US and nb-NO Resources.resw of Brasscribe Play from one table (keeps keys in step).

Usage: python3 tools/Strings/gen_resw.py src/Brasscribe.Play/Strings
Edit the table here, not the .resw files; LocalizationTests checks the result."""
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


def icon_button(uid, en, nb, hen, hnb):
    name(uid, en, nb); tip(uid, en, nb); help_(uid, hen, hnb)


def text_button(uid, en, nb, hen, hnb):
    prop(uid, "Content", en, nb); help_(uid, hen, hnb)


# ---- window and title bar ----
add("AppWindowTitle", "Brasscribe Play", "Brasscribe Play")
icon_button("BackButton", "Back", "Tilbake", "Go back (Alt+Left)", "Gå tilbake (Alt+Venstre)")
name("ExportButton", "Share or print", "Del eller skriv ut"); help_("ExportButton", "Print your part, or save the score, parts, audio or MIDI (Ctrl+P)", "Skriv ut stemmen din, eller lagre partituret, stemmene, lyd eller MIDI (Ctrl+P)")
prop("ExportButtonLabel", "Text", "Share or print", "Del eller skriv ut")
icon_button("SettingsButton", "Settings", "Innstillinger", "Language, keyboard, reading aloud and Brasscribe on your computer (Ctrl+,)", "Språk, tastatur, opplesing og Brasscribe på datamaskinen (Ctrl+,)")
icon_button("HelpButton", "Help and keyboard shortcuts", "Hjelp og hurtigtaster", "Show every keyboard shortcut (F1)", "Vis alle hurtigtaster (F1)")
name("LibraryNav", "Your scores", "Partiturene dine")
text_button("NewScoreButton", "New score", "Nytt partitur", "Open or record a new recording", "Åpne eller ta opp et nytt opptak")
prop("NewScoreLabel", "Text", "New score", "Nytt partitur")
prop("LibraryHeading", "Text", "YOUR SCORES", "PARTITURENE DINE")

# ---- first run ----
prop("FirstRunHeadingLead", "Text", "Scores for your band, from ", "Partitur for bandet ditt, fra ")
prop("FirstRunHeadingBrass", "Text", "any recording.", "et hvilket som helst opptak.")
prop("FirstRunPoint1Title", "Text", "Record or open", "Ta opp eller åpne")
prop("FirstRunPoint1Body", "Text", "Play the piece, record a rehearsal, or open a file you have.", "Spill stykket, ta opp en øvelse eller åpne en fil du har.")
prop("FirstRunPoint2Title", "Text", "Check the marked notes", "Sjekk de merkede tonene")
prop("FirstRunPoint2Body", "Text", "Notes Brasscribe isn't sure about get a “?”. A boxed “?” means very unsure. You decide.",
     "Toner Brasscribe er usikker på, får et «?». Et «?» i en boks betyr svært usikker. Du bestemmer.")
prop("FirstRunPoint3Title", "Text", "Practise with the band", "Øv med bandet")
prop("FirstRunPoint3Body", "Text", "Mute your part, slow it down, repeat the hard bars.", "Slå av lyden på stemmen din, spill saktere, gjenta de vanskelige taktene.")
prop("FirstRunPrivacy", "Text", "Recordings stay on this PC and your own computer.", "Opptakene blir på denne PC-en og din egen datamaskin.")
text_button("GetStartedButton", "Get started", "Kom i gang", "Go to Home", "Gå til startsiden")

# ---- home ----
prop("HomeHeadingLead", "Text", "Turn a recording into ", "Gjør et opptak om til ")
prop("HomeHeadingBrass", "Text", "a score.", "et partitur.")
prop("HomeIntro", "Text", "Play it, record it, or open a file. Brasscribe writes the parts for your band.",
     "Spill det, ta det opp eller åpne en fil. Brasscribe skriver stemmene for bandet ditt.")
prop("HomeDropTitle", "Text", "Drop an audio or video file here", "Slipp en lyd- eller videofil her")
prop("HomeDropFormats", "Text", "MP3, WAV, M4A, MP4 and most other formats, or a MusicXML score", "MP3, WAV, M4A, MP4 og de fleste andre formater, eller et MusicXML-partitur")
name("ImportButton", "Open a recording", "Åpne et opptak"); help_("ImportButton", "Open an audio or video file, or a MusicXML score (Ctrl+O)", "Åpne en lyd- eller videofil, eller et MusicXML-partitur (Ctrl+O)")
prop("ImportButtonLabel", "Text", "Open a recording…", "Åpne et opptak …")
name("DecodingProgress", "Reading the file", "Leser filen")
name("RecordMicButton", "Record with the microphone", "Ta opp med mikrofonen"); help_("RecordMicButton", "Play your part in the room (Ctrl+Shift+R)", "Spill stemmen din i rommet (Ctrl+Shift+R)")
prop("RecordMicTitle", "Text", "Record with the microphone", "Ta opp med mikrofonen")
prop("RecordMicBody", "Text", "Play your part in the room", "Spill stemmen din i rommet")
name("RecordSystemButton", "Record what's playing", "Ta opp det som spilles"); help_("RecordSystemButton", "Record everything this PC plays", "Ta opp alt denne PC-en spiller")
prop("RecordSystemTitle", "Text", "Record what's playing", "Ta opp det som spilles")
prop("RecordSystemBody", "Text", "Sound from another app on this PC", "Lyd fra en annen app på denne PC-en")
name("RecordAppCard", "Record one app", "Ta opp én app"); help_("RecordAppCard", "Choose the app to record, and nothing else is recorded", "Velg appen som skal tas opp, og ingenting annet blir tatt opp")
prop("RecordAppTitle", "Text", "Record one app", "Ta opp én app")
prop("RecordAppBody", "Text", "Only the app you choose, not other sounds", "Bare appen du velger, ikke andre lyder")
prop("AppPicker", "Header", "App to record", "App som skal tas opp"); prop("AppPicker", "PlaceholderText", "Choose an app that is playing", "Velg en app som spiller")
help_("AppPicker", "Apps that play sound right now are listed first", "Apper som spiller lyd akkurat nå, står øverst")
icon_button("RefreshAppsButton", "Look for apps again", "Se etter apper på nytt", "Look again for apps that play sound", "Se etter apper som spiller lyd på nytt")
name("RecordAppButton", "Record this app", "Ta opp denne appen"); help_("RecordAppButton", "Record the chosen app and nothing else", "Ta opp den valgte appen og ingenting annet")
prop("RecordAppButtonLabel", "Text", "Record this app", "Ta opp denne appen")
prop("AppCaptureUnavailable", "Text", "Needs Windows 11. You can still record everything this PC plays.",
     "Krever Windows 11. Du kan fortsatt ta opp alt PC-en spiller.")
name("RecordingTime", "Recording time", "Opptakstid")
name("LevelMeter", "Input level", "Inngangsnivå")
prop("StopRecordingButton", "Content", "Stop recording", "Stopp opptaket"); help_("StopRecordingButton", "Stop and continue with the recording (Ctrl+Shift+R)", "Stopp og gå videre med opptaket (Ctrl+Shift+R)")
prop("CaptureNotice", "Title", "Nothing was heard", "Ingenting ble hørt")
prop("StartError", "Title", "That didn't work", "Det gikk ikke")
prop("LinkNote", "Text", "Links to streaming sites can't be downloaded. Play the music and record it instead.",
     "Lenker til strømmetjenester kan ikke lastes ned. Spill musikken og ta den opp i stedet.")
prop("HomeScoresHeading", "Text", "YOUR SCORES", "PARTITURENE DINE")
name("ScoreCards", "Your scores", "Partiturene dine")
prop("HomeEmpty", "Text", "Your scores will appear here.", "Partiturene dine vises her.")

# ---- what is this ----
prop("KindHeading", "Text", "What is this?", "Hva er dette?")
prop("KindIntro", "Text", "Your answer decides how Brasscribe listens. It never guesses.",
     "Svaret ditt avgjør hvordan Brasscribe lytter. Det gjettes aldri.")
name("KindOptions", "What is this recording?", "Hva er dette opptaket?")
prop("KindNotSure", "Text", "Not sure? Choose Brass band. You can change it later.", "Usikker? Velg Brassband. Du kan endre det senere.")
text_button("KindCancelButton", "Cancel", "Avbryt", "Back to Home, the recording is kept", "Tilbake til startsiden, opptaket beholdes")
prop("ContinueButton", "Content", "Continue", "Fortsett"); help_("ContinueButton", "Make the score. Choose what the recording is first.", "Lag partituret. Velg først hva opptaket er.")

# ---- making the score ----
name("TranscribeProgress", "Making the score", "Lager partituret")
prop("CancelTranscriptionButton", "Content", "Cancel", "Avbryt"); help_("CancelTranscriptionButton", "Stop making this score (asks first)", "Slutt å lage dette partituret (spør først)")
prop("TranscribeLeaveNote", "Text", "Brasscribe will tell you when the score is ready.", "Brasscribe sier fra når partituret er klart.")

# ---- check the notes ----
prop("LegendUncertain", "Text", "Uncertain", "Usikker")
prop("LegendVeryUncertain", "Text", "Very uncertain", "Svært usikker")
name("ReviewLegend", "“?” means uncertain. A boxed “?” means very uncertain.", "«?» betyr usikker. «?» i en boks betyr svært usikker.")
name("ReviewList", "Notes to check", "Toner å sjekke")
name("ReviewSnippet", "The bars around the note", "Taktene rundt tonen")
help_("ReviewListenButton", "Plays the bar once, from the recording when there is one. Press again to stop (Space)", "Spiller takten én gang, fra opptaket når det finnes. Trykk igjen for å stoppe (Mellomrom)")
prop("ReviewListenLabel", "Text", "Listen to this bar", "Lytt til denne takten")
prop("ReviewStopLabel", "Text", "Stop", "Stopp")
help_("ReviewKeepBarButton", "The other marked notes in this bar are right; their “?” go", "De andre merkede tonene i takten er riktige; «?» fjernes")
name("ReviewScope", "Which notes to check", "Hvilke toner som skal sjekkes")
name("ReviewChangeNoteButton", "Change note…", "Endre tonen …"); help_("ReviewChangeNoteButton", "Choose what the note should be; the whole score follows", "Velg hva tonen skal være; hele partituret følger med")
prop("ReviewChangeNoteLabel", "Text", "Change note…", "Endre tonen …")
prop("ReviewKeys", "Text", "Space listens · K keeps · arrows move", "Mellomrom lytter · K beholder · piltastene flytter")
text_button("ReviewSkipButton", "Skip", "Hopp over", "Leave this note marked and go to the next", "La tonen være merket og gå til neste")
name("ReviewKeepButton", "Keep, go to next", "Behold, gå til neste"); help_("ReviewKeepButton", "The note is right; its “?” goes (K)", "Tonen er riktig; «?» fjernes (K)")
prop("ReviewKeepLabel", "Text", "Keep, go to next", "Behold, gå til neste")

# ---- how should the score be ----
prop("OutputOverline", "Text", "LAST STEP", "SISTE STEG")
prop("OutputHeading", "Text", "How should the score be?", "Hvordan skal partituret bli?")
prop("OutputIntro", "Text", "You can change this later. Nothing is lost.", "Du kan endre dette senere. Ingenting går tapt.")
prop("OutputBandHeading", "Text", "Which band?", "Hvilket band?")
name("LineupChoices", "Which band?", "Hvilket band?")
name("LineupFullChoice", "Full brass band", "Fullt brassband")
prop("LineupFullTitle", "Text", "Full brass band", "Fullt brassband")
prop("LineupFullBody", "Text", "About 25 players", "Rundt 25 musikere")
name("LineupSmallChoice", "Small band", "Lite band")
prop("LineupSmallTitle", "Text", "Small band", "Lite band")
prop("LineupSmallBody", "Text", "10–15 players, parts doubled up", "10–15 musikere, stemmene slått sammen")
prop("OutputHardHeading", "Text", "How hard?", "Hvor vanskelig?")
prop("DifficultyFaithful", "Content", "As played", "Som spilt")
prop("DifficultyStandard", "Content", "A bit easier", "Litt enklere")
prop("DifficultyEasier", "Content", "Easier", "Enklere")
prop("OutputHardTip", "Text", "Easier keeps the tune but avoids high notes and fast runs.", "Enklere beholder melodien, men unngår høye toner og raske løp.")
prop("OutputKeyHeading", "Text", "Key", "Toneart")
name("KeyDownButton", "Lower", "Lavere"); tip("KeyDownButton", "A semitone lower", "Et halvtonetrinn lavere")
prop("KeyDownLabel", "Text", "Lower", "Lavere")
name("KeyUpButton", "Higher", "Høyere"); tip("KeyUpButton", "A semitone higher", "Et halvtonetrinn høyere")
prop("KeyUpLabel", "Text", "Higher", "Høyere")
text_button("OutputBackButton", "Back", "Tilbake", "Back to the score as it is", "Tilbake til partituret slik det er")
text_button("ShowScoreButton", "Show the score", "Vis partituret", "Arranges again only if you changed a choice", "Arrangerer på nytt bare hvis du endret et valg")

# ---- score ----
name("ScoreToolbar", "Score tools", "Verktøy for partituret")
add(f"ScoreToolbar.{AUTO}.LocalizedLandmarkType", "toolbar", "verktøylinje")
name("PartPicker", "Parts", "Stemmer"); help_("PartPicker", "All parts, or one part as a page (P)", "Alle stemmer, eller én stemme som side (P)")
name("PitchChoice", "Pitch", "Tonehøyde")
tip("WrittenChoice", "Written is what you read on your part.", "Notert er det du leser i stemmen din.")
prop("ConcertChoice", "Content", "Concert pitch", "Klingende"); tip("ConcertChoice", "Concert is how it sounds on a piano.", "Klingende er slik det låter på et piano.")
icon_button("ZoomOutButton", "Zoom out", "Zoom ut", "Smaller notation (Ctrl+-)", "Mindre noter (Ctrl+-)")
name("ZoomBox", "Zoom, percent", "Zoom, prosent"); help_("ZoomBox", "Notation size from 50 to 400 percent", "Notestørrelse fra 50 til 400 prosent")
icon_button("ZoomInButton", "Zoom in", "Zoom inn", "Larger notation (Ctrl+=)", "Større noter (Ctrl+=)")
name("ViewMenuButton", "View", "Vis"); help_("ViewMenuButton", "Read aloud, show video, how the score should be", "Les opp, vis video, hvordan partituret skal være")
prop("ViewMenuLabel", "Text", "View", "Vis")
prop("TalkingScoreToggle", "Text", "Read aloud", "Les opp"); help_("TalkingScoreToggle", "Describes the score in words for a screen reader (Ctrl+T)", "Beskriver partituret med ord for skjermleser (Ctrl+T)")
prop("VideoToggle", "Text", "Show video", "Vis video")
prop("PipItem", "Text", "Video in its own window", "Video i eget vindu")
prop("ChooseOutputItem", "Text", "How should the score be?…", "Hvordan skal partituret bli? …")
text_button("CheckThemButton", "Check them", "Sjekk dem", "Go through the notes marked ? one at a time", "Gå gjennom tonene merket ? én om gangen")
prop("PartPageNote", "Text", "Written down by Brasscribe. Check the notes marked ? before the rehearsal.",
     "Skrevet ned av Brasscribe. Sjekk tonene merket ? før øvelsen.")
name("ScoreNotation", "Notes", "Noter")
help_("ScoreNotation", "Arrows move by note, Ctrl+arrows by beat and bar, Ctrl+Shift+arrows by part. U finds notes marked ?. Tab leaves the score.",
      "Piltastene flytter én tone, Ctrl+piltaster ett slag eller én takt, Ctrl+Shift+piltaster én stemme. U finner toner merket ?. Tab går ut av partituret.")
prop("ListenToBarItem", "Text", "Listen to this bar", "Lytt til denne takten")
prop("MarkCheckedItem", "Text", "Keep this note", "Behold denne tonen")
prop("ReadBarItem", "Text", "Read the bar", "Les takten")
prop("GoToBarItem", "Text", "Go to bar…", "Gå til takt …")
prop("LoopStartItem", "Text", "Repeat from here", "Gjenta herfra")
prop("LoopEndItem", "Text", "Repeat to here", "Gjenta hit")
name("TalkingList", "Read aloud", "Les opp")
prop("MixerHeading", "Text", "PARTS", "STEMMER")
name("Mixer", "Parts: mute or hear alone", "Stemmer: lyd av eller hør alene")
prop("MixerYourPart", "Text", "your part", "stemmen din")
prop("MixerMuteLabel", "Text", "Mute", "Lyd av")
prop("MixerSoloLabel", "Text", "Only this", "Bare denne")
prop("MixerNote", "Text", "Your part is muted so you can play along. “Only this” plays one part alone.",
     "Stemmen din er uten lyd, så du kan spille med. «Bare denne» spiller én stemme alene.")
prop("AdLibNotice", "Text", "Some bars have no steady beat (ad lib.). Their rhythms are approximate.",
     "Noen takter har ingen fast puls (ad lib.). Rytmene der er omtrentlige.")
name("VideoView", "Original video", "Originalvideo")
name("PlayerBar", "Player", "Avspiller")
add(f"PlayerBar.{AUTO}.LocalizedLandmarkType", "player", "avspiller")
icon_button("PreviousBarButton", "Previous bar", "Forrige takt", "Go to the bar before", "Gå til takten før")
icon_button("PlayPauseButton", "Play or pause", "Spill av eller pause", "Space in the score, Ctrl+Shift+Space anywhere", "Mellomrom i partituret, Ctrl+Shift+Mellomrom hvor som helst")
icon_button("NextBarButton", "Next bar", "Neste takt", "Go to the bar after", "Gå til takten etter")
name("HearChoice", "Hear", "Hør")
prop("HearBand", "Content", "Hear the band", "Hør bandet"); help_("HearBand", "Play the score", "Spill av partituret")
prop("HearRecording", "Content", "Recording", "Opptaket"); help_("HearRecording", "Play the recording from the same place (O)", "Spill av opptaket fra samme sted (O)")
prop("SpeedLabel", "Text", "Speed", "Tempo")
name("SpeedSlider", "Speed", "Tempo"); help_("SpeedSlider", "25 to 150 percent, without changing the pitch", "25 til 150 prosent, uten å endre tonehøyden")
name("CountInToggle", "Count-in", "Inntelling"); tip("CountInToggle", "One bar of clicks before the music starts.", "Én takt med klikk før musikken starter.")
prop("CountInLabel", "Text", "Count-in", "Inntelling")
name("MetronomeToggle", "Metronome", "Metronom"); tip("MetronomeToggle", "A click on every beat.", "Et klikk på hvert slag.")
prop("MetronomeLabel", "Text", "Metronome", "Metronom")
name("MuteMyPartToggle", "Mute my part", "Lyd av min stemme"); tip("MuteMyPartToggle", "Your part is silent so you can play it.", "Stemmen din er stille, så du kan spille den selv.")
prop("MuteMyPartLabel", "Text", "Mute my part", "Lyd av min stemme")
prop("RepeatBarsLabel", "Text", "Repeat bars", "Gjenta takt")
name("LoopStartBox", "Repeat from bar", "Gjenta fra takt")
prop("RepeatToLabel", "Text", "to", "til")
name("LoopEndBox", "Repeat to bar", "Gjenta til takt")
text_button("SetLoopButton", "Repeat", "Gjenta", "Plays these bars over and over (L)", "Spiller disse taktene om og om igjen (L)")
text_button("ClearLoopButton", "Stop repeating", "Slutt å gjenta", "Play on without repeating (L)", "Spill videre uten å gjenta (L)")

# ---- dialogs ----
prop("ExportDialog", "Title", "Share or print", "Del eller skriv ut"); prop("ExportDialog", "PrimaryButtonText", "Print…", "Skriv ut …"); prop("ExportDialog", "CloseButtonText", "Cancel", "Avbryt")
prop("ExportDialog", "SecondaryButtonText", "Save…", "Lagre …")
prop("ExportWhatHeading", "Text", "WHAT", "HVA")
name("ExportScope", "What to share or print", "Hva som skal deles eller skrives ut")
prop("ExportEveryPart", "Content", "Every part", "Alle stemmer")
prop("ExportConductor", "Content", "Conductor's score", "Dirigentpartitur")
prop("ExportEveryPartTip", "Text", "Every part: one PDF per player.", "Alle stemmer: én PDF per musiker.")
prop("ExportAsHeading", "Text", "AS", "SOM")
prop("ExportMarksNote", "Text", "Notes Brasscribe wasn't sure about keep their “?” marks.", "Toner Brasscribe var usikker på, beholder «?»-merket.")
prop("GoToBarDialog", "Title", "Go to bar", "Gå til takt"); prop("GoToBarDialog", "PrimaryButtonText", "Go", "Gå"); prop("GoToBarDialog", "CloseButtonText", "Cancel", "Avbryt")
prop("GoToBarBox", "Header", "Bar number", "Taktnummer")
prop("ShortcutsDialog", "Title", "Keyboard shortcuts", "Hurtigtaster"); prop("ShortcutsDialog", "CloseButtonText", "Close", "Lukk")
prop("SettingsDialog", "Title", "Settings", "Innstillinger"); prop("SettingsDialog", "CloseButtonText", "Close", "Lukk")
prop("SettingsLanguageHeading", "Text", "Language", "Språk")
prop("LanguageBox", "Header", "App language", "Appspråk")
prop("LanguageSystem", "Content", "Same as Windows", "Samme som Windows")
prop("LanguageRestartNote", "Text", "A new language is used the next time you start the app.", "Nytt språk tas i bruk neste gang du starter appen.")
prop("SettingsAccessibilityHeading", "Text", "Display and keyboard", "Visning og tastatur")
prop("SingleKeySwitch", "Header", "Single-key shortcuts in the score", "Hurtigtaster med én tast i partituret")
help_("SingleKeySwitch", "Keys such as U, R and P. Arrows always work.", "Taster som U, R og P. Piltastene virker alltid.")
prop("ReduceMotionSwitch", "Header", "Reduce motion", "Mindre bevegelse")
help_("ReduceMotionSwitch", "The cursor jumps per beat and the score turns pages instead of scrolling", "Markøren hopper ett slag om gangen, og partituret blar i stedet for å rulle")
prop("VerbosityBox", "Header", "How much “Read aloud” says", "Hvor mye «Les opp» sier")
prop("VerbosityBrief", "Content", "Brief", "Kort")
prop("VerbosityStandard", "Content", "Standard", "Standard")
prop("VerbosityFull", "Content", "Everything", "Alt")
prop("SettingsEngineHeading", "Text", "Brasscribe on your computer", "Brasscribe på datamaskinen")
prop("EngineAddressBox", "Header", "Address", "Adresse")
prop("EngineDetails", "Header", "Details for the band's tech person", "Detaljer for den tekniske i bandet")
name("EngineDetails", "Details for the band's tech person", "Detaljer for den tekniske i bandet")
help_("ConnectionActionButton", "Connect this PC to Brasscribe on your computer", "Koble denne PC-en til Brasscribe på datamaskinen")
text_button("AskComputerButton", "Ask on the computer instead", "Spør på datamaskinen i stedet", "No code to type: choose Allow on the computer", "Ingen kode å skrive: velg Godkjenn på datamaskinen")
text_button("CancelAskButton", "Stop waiting", "Slutt å vente", "Stop waiting for the computer to allow this PC", "Slutt å vente på at datamaskinen godkjenner denne PC-en")
prop("MatchCodeLabel", "Text", "The computer shows the same number", "Datamaskinen viser det samme tallet")
text_button("UnpairButton", "Forget this computer", "Glem denne datamaskinen", "The computer forgets this PC, and this PC forgets the computer", "Datamaskinen glemmer denne PC-en, og denne PC-en glemmer datamaskinen")
prop("EngineAddressBox", "PlaceholderText", "http://127.0.0.1:8765", "http://127.0.0.1:8765")
prop("PairingCodeBox", "Header", "Code", "Kode")
prop("PairingCodeBox", "PlaceholderText", "The six digits your computer shows", "De seks sifrene datamaskinen viser")
text_button("ConnectButton", "Connect", "Koble til", "Open Brasscribe on your computer and choose Pair a device, then type the code here", "Åpne Brasscribe på datamaskinen og velg Koble til en enhet, og skriv inn koden her")
prop("SettingsAboutHeading", "Text", "About", "Om")
prop("AboutText", "Text",
     "Brasscribe Play is a non-commercial project. Notation and sound: alphaTab (MPL-2.0). The display face is Instrument Serif (SIL OFL 1.1).",
     "Brasscribe Play er et ikke-kommersielt prosjekt. Noter og lyd: alphaTab (MPL-2.0). Overskriftsskriften er Instrument Serif (SIL OFL 1.1).")
name("ErrorSteps", "What to do", "Hva du kan gjøre")

# ---- code strings ----
code = {
    "Duration_MinutesSeconds": ("{0} min {1} s", "{0} min {1} s"),
    "Duration_Seconds": ("{0} s", "{0} s"),
    "Screen_Start": ("Home", "Startside"),
    "Screen_FirstRun": ("Welcome", "Velkommen"),
    "Screen_SourceKind": ("What is this?", "Hva er dette?"),
    "Screen_Transcribing": ("Making the score", "Lager partituret"),
    "Screen_Review": ("Check the notes", "Sjekk tonene"),
    "Screen_ChooseOutput": ("How should the score be?", "Hvordan skal partituret bli?"),
    "Screen_Score": ("Score", "Partitur"),
    "Screen_Error": ("Something went wrong", "Noe gikk galt"),
    "Back_Home": ("Home", "Startside"),
    "Back_FullScore": ("Full score", "Hele partituret"),
    "Title_CheckNotes": ("{0} · Check the notes", "{0} · Sjekk tonene"),
    "Title_ScoreSubtitle": ("{0} · {1} bars", "{0} · {1} takter"),
    "Library_OnePart": ("One part", "Én stemme"),
    "Library_SmallBand": ("Small band", "Lite band"),
    "Library_FullBand": ("Full band", "Fullt band"),
    "Library_Today": ("Today", "I dag"),
    "Library_Subtitle": ("{0} · {1} bars · {2}", "{0} · {1} takter · {2}"),
    "Library_ToCheckOne": ("{0} to check", "{0} å sjekke"),
    "Library_ToCheck": ("{0} to check", "{0} å sjekke"),
    "Library_Yesterday": ("Yesterday", "I går"),
    "Library_RecordingTitle": ("Recording, {0}", "Opptak, {0}"),
    "Start_Imported": ("Opened {0}, {1}", "Åpnet {0}, {1}"),
    "Start_RecordingName": ("Recording", "Opptak"),
    "Start_RecordingStarted": ("Recording started", "Opptaket har startet"),
    "Start_RecordingStopped": ("Recording stopped, {0}", "Opptaket er stoppet, {0}"),
    "Start_Error_Link": ("Links to streaming sites can't be downloaded. Play the music and record it instead.", "Lenker til strømmetjenester kan ikke lastes ned. Spill musikken og ta den opp i stedet."),
    "Start_Error_Unsupported": ("{0} can't be opened. Try an MP3, WAV, M4A or MP4 file, or a MusicXML score.", "{0} kan ikke åpnes. Prøv en MP3-, WAV-, M4A- eller MP4-fil, eller et MusicXML-partitur."),
    "Start_Error_Decode": ("{0} can't be read. Try another file, or record it instead.", "{0} kan ikke leses. Prøv en annen fil, eller ta det opp i stedet."),
    "Start_Error_Score": ("{0} can't be opened as a score.", "{0} kan ikke åpnes som partitur."),
    "Start_Error_AppCaptureUnsupported": ("Recording one app needs Windows 11. Record everything this PC plays instead.", "Opptak av én app krever Windows 11. Ta opp alt PC-en spiller i stedet."),
    "Start_Error_ChooseApp": ("Choose the app to record first.", "Velg først appen som skal tas opp."),
    "Start_Error_MicrophonePermission": ("Brasscribe may not use the microphone. Allow it in Windows Settings, Privacy, Microphone.", "Brasscribe har ikke lov til å bruke mikrofonen. Gi tilgang i Windows-innstillinger, Personvern, Mikrofon."),
    "Start_Error_Capture": ("Recording couldn't start: {0}", "Opptaket kunne ikke starte: {0}"),
    "Start_Error_TooShort": ("The recording is shorter than a second. Try again.", "Opptaket er kortere enn ett sekund. Prøv igjen."),
    "Start_Level_Silent": ("Input level, silent", "Inngangsnivå, stille"),
    "Start_Level_Low": ("Input level, low", "Inngangsnivå, lavt"),
    "Start_Level_Good": ("Input level, good", "Inngangsnivå, bra"),
    "Start_Level_TooLoud": ("Input level, too loud", "Inngangsnivå, for høyt"),
    "Start_Notice_SilenceWhilePlaying": ("The app is playing, but Brasscribe hears only silence. Streaming apps usually block recording. Open a file instead, or record with the microphone.", "Appen spiller, men Brasscribe hører bare stillhet. Strømmeapper stopper som regel opptak. Åpne en fil i stedet, eller ta opp med mikrofonen."),
    "Start_Notice_NothingPlaying": ("Only silence is arriving. Check that something is playing. Streaming apps usually block recording.", "Det kommer bare stillhet. Sjekk at noe spiller. Strømmeapper stopper som regel opptak."),
    "Start_Notice_TooLoud": ("The sound is too loud and distorts. Turn the volume down a little.", "Lyden er for høy og blir forvrengt. Skru ned volumet litt."),
    "Kind_Solo_Label": ("One instrument", "Ett instrument"),
    "Kind_Solo_Description": ("One player on their own, like you practising the cornet.", "Én musiker alene, som når du øver på kornetten."),
    "Kind_BrassBand_Label": ("Brass band", "Brassband"),
    "Kind_BrassBand_Description": ("A whole band playing together, with no other instruments.", "Et helt band som spiller sammen, uten andre instrumenter."),
    "Kind_OrchestraWithSoloist_Label": ("Soloist with orchestra or band", "Solist med orkester eller band"),
    "Kind_OrchestraWithSoloist_Description": ("You get the solo part, plus the accompaniment arranged for brass band.", "Du får solostemmen, og akkompagnementet arrangert for brassband."),
    "Kind_PopRock_Label": ("Pop or rock", "Pop eller rock"),
    "Kind_PopRock_Description": ("Singing, guitars, keys, bass and drums.", "Sang, gitarer, tangenter, bass og trommer."),
    "Kind_SourceLine": ("{0} · {1}", "{0} · {1}"),
    "Kind_WhereThisPc": ("Made on this PC. Nothing goes online.", "Lages på denne PC-en. Ingenting sendes til nettet."),
    "Kind_WhereComputer": ("Made by Brasscribe on your computer. Nothing goes online.", "Lages av Brasscribe på datamaskinen din. Ingenting sendes til nettet."),
    "Transcribe_Started": ("Making a score of {0} as {1}", "Lager partitur av {0} som {1}"),
    "Transcribe_Stage_Upload": ("Getting the recording ready", "Gjør opptaket klart"),
    "Transcribe_Stage_Separate": ("Separating the instruments", "Skiller instrumentene"),
    "Transcribe_Stage_Beats": ("Finding the beat", "Finner pulsen"),
    "Transcribe_Stage_Notes": ("Writing down the notes", "Skriver ned tonene"),
    "Transcribe_Stage_Arrange": ("Arranging for brass band", "Arrangerer for brassband"),
    "Transcribe_Stage_Engrave": ("Laying out the pages", "Setter opp sidene"),
    "Transcribe_Stage_Working": ("Working", "Arbeider"),
    "Transcribe_Step_Ready": ("Getting the recording ready", "Gjør opptaket klart"),
    "Transcribe_Step_Beats": ("Finding the beat", "Finner pulsen"),
    "Transcribe_Step_Separate": ("Separating the instruments", "Skiller instrumentene"),
    "Transcribe_Step_SeparateSoloist": ("Separating the soloist from the band", "Skiller solisten fra bandet"),
    "Transcribe_Step_Notes": ("Writing down the notes", "Skriver ned tonene"),
    "Transcribe_Step_Arrange": ("Arranging for brass band", "Arrangerer for brassband"),
    "Transcribe_Step_Layout": ("Laying out the pages", "Setter opp sidene"),
    "Transcribe_StepDone": ("{0}, done", "{0}, ferdig"),
    "Transcribe_StepCurrent": ("{0}, now", "{0}, nå"),
    "Transcribe_StepPending": ("{0}, to come", "{0}, kommer"),
    "Transcribe_Overline": ("Step {0} of {1} · {2}", "Steg {0} av {1} · {2}"),
    "Transcribe_Eta_Unknown": ("Working out the time left", "Regner ut hvor lang tid som er igjen"),
    "Transcribe_Eta_UnderMinute": ("Less than a minute left", "Under ett minutt igjen"),
    "Transcribe_Eta_Minutes": ("About {0} minutes left", "Omtrent {0} minutter igjen"),
    "Transcribe_Eta_Hours": ("About {0} hours left", "Omtrent {0} timer igjen"),
    "Transcribe_ProgressAnnouncement": ("{0} percent. {1}. {2}", "{0} prosent. {1}. {2}"),
    "Transcribe_Device": ("Running on {0}", "Kjører på {0}"),
    "Transcribe_Done": ("The score is ready", "Partituret er klart"),
    "Transcribe_Cancelled": ("Stopped. The recording is kept.", "Stoppet. Opptaket beholdes."),
    "Transcribe_Failed": ("The score couldn't be made", "Partituret kunne ikke lages"),
    "Transcribe_Error": ("Stopped: {0}", "Stoppet: {0}"),
    "Transcribe_CancelConfirm": ("Stop making this score? The recording stays in Your scores.", "Slutte å lage dette partituret? Opptaket blir liggende i Partiturene dine."),
    "Transcribe_Rearranging": ("Arranging again with your choices", "Arrangerer på nytt med valgene dine"),
    "CancelDialog_Title": ("Stop making this score?", "Slutte å lage dette partituret?"),
    "CancelDialog_Content": ("The recording stays in Your scores, so you can start again.", "Opptaket blir liggende i Partiturene dine, så du kan starte på nytt."),
    "CancelDialog_Stop": ("Stop", "Stopp"),
    "CancelDialog_Keep": ("Keep going", "Fortsett"),
    "Review_CountOne": ("{0} note to check", "{0} tone å sjekke"),
    "Review_Count": ("{0} notes to check", "{0} toner å sjekke"),
    "Review_LeadMany": ("Most of these are probably right. Start with the {0} very unsure ones.", "De fleste av disse er nok riktige. Begynn med de {0} svært usikre."),
    "Review_LeadManyOne": ("Most of these are probably right. Start with the {0} very unsure one.", "De fleste av disse er nok riktige. Begynn med den {0} svært usikre."),
    "Review_LeadStart": ("Start with the {0} very unsure ones.", "Begynn med de {0} svært usikre."),
    "Review_LeadStartOne": ("Start with the {0} very unsure one.", "Begynn med den {0} svært usikre."),
    "Review_KeepBar": ("Keep the rest of this bar ({0})", "Behold resten av takten ({0})"),
    "Review_KeptBar": ("Kept {0} notes in bar {1}. {2} left", "Beholdt {0} toner i takt {1}. {2} igjen"),
    "Review_Triage": ("Check your part first: {0} notes in {1}, {2} very unsure", "Sjekk stemmen din først: {0} toner i {1}, {2} svært usikre"),
    "Review_ScopeMine": ("Your part ({0})", "Stemmen din ({0})"),
    "Review_ScopeAll": ("All parts ({0})", "Alle stemmer ({0})"),
    "Review_Accompaniment": ("Accompaniment", "Akkompagnement"),
    "Review_MyPartDone": ("Your part is checked. Now the other parts.", "Stemmen din er sjekket. Nå de andre stemmene."),
    "Review_Changed": ("Changed to {0}", "Endret til {0}"),
    "Review_ListItem": ("Bar {0} · {1}", "Takt {0} · {1}"),
    "Review_ListItemUncertain": ("Bar {0}, {1}, uncertain", "Takt {0}, {1}, usikker"),
    "Review_ListItemVeryUncertain": ("Bar {0}, {1}, very uncertain", "Takt {0}, {1}, svært usikker"),
    "Review_Overline": ("{0} of {1} · {2}", "{0} av {1} · {2}"),
    "Review_BarsHeading": ("Bars {0}–{1}", "Takt {0}–{1}"),
    "Review_GroupLine": ("{0} notes together, from: {1}", "{0} toner sammen, fra: {1}"),
    "Review_BarHeading": ("Bar {0}", "Takt {0}"),
    "Review_NoteWritten": ("Written {0}", "Notert {0}"),
    "Review_NoteConcert": ("Concert {0}", "Klingende {0}"),
    "Review_LevelUncertain": ("Uncertain: listen to the original and the score side by side.", "Usikker: lytt til opptaket og partituret side om side."),
    "Review_LevelVeryUncertain": ("Very uncertain: listen to the original and the score side by side.", "Svært usikker: lytt til opptaket og partituret side om side."),
    "Review_Kept": ("Kept bar {0}. {1} left", "Beholdt takt {0}. {1} igjen"),
    "Review_AllDone": ("Every note is checked", "Alle tonene er sjekket"),
    "Review_FinishLater": ("Finish later ({0} left)", "Fortsett senere ({0} igjen)"),
    "Review_FinishConfirmOne": ("{0} note keeps its ? mark. You can check it any time from the score with “Check them”.", "{0} tone beholder ?-merket. Du kan sjekke den når som helst fra partituret med «Sjekk dem»."),
    "Review_FinishConfirm": ("{0} notes keep their ? marks. You can check them any time from the score with “Check them”.", "{0} toner beholder ?-merket. Du kan sjekke dem når som helst fra partituret med «Sjekk dem»."),
    "FinishLater_Title": ("Finish checking later?", "Fortsette senere?"),
    "FinishLater_Confirm": ("Finish later", "Fortsett senere"),
    "FinishLater_Keep": ("Keep checking", "Sjekk videre"),
    "Error_TryAgain": ("Try again", "Prøv igjen"),
    "Error_ChooseAnother": ("Choose another recording", "Velg et annet opptak"),
    "Error_DetailsHeading": ("Details for the band's tech person", "Detaljer for den tekniske i bandet"),
    "Error_ComputerUnreachable_Title": ("Can't reach Brasscribe on your computer", "Får ikke kontakt med Brasscribe på datamaskinen"),
    "Error_ComputerUnreachable_Reason": ("Your recording is safe. Full-band scores are made on your computer, and it isn't answering.", "Opptaket ditt er trygt. Partitur for fullt band lages på datamaskinen, og den svarer ikke."),
    "Error_ComputerUnreachable_Step1": ("Check that the computer is on and on the same network.", "Sjekk at datamaskinen er på og på samme nettverk."),
    "Error_ComputerUnreachable_Step2": ("Open Brasscribe on the computer.", "Åpne Brasscribe på datamaskinen."),
    "Error_ComputerUnreachable_Step3": ("Choose Try again.", "Velg Prøv igjen."),
    "Error_ComputerUnreachable_Details": ("Start it with: brasscribe serve. Settings shows the address it uses. The message was: {0}", "Start den med: brasscribe serve. Innstillinger viser adressen den bruker. Meldingen var: {0}"),
    "Error_ScoreFailed_Title": ("The score couldn't be made", "Partituret kunne ikke lages"),
    "Error_ScoreFailed_Reason": ("Your recording is safe. Something stopped Brasscribe on your computer while it worked.", "Opptaket ditt er trygt. Noe stoppet Brasscribe på datamaskinen mens den arbeidet."),
    "Error_ScoreFailed_Step1": ("Choose Try again. It often works the second time.", "Velg Prøv igjen. Det går ofte andre gang."),
    "Error_ScoreFailed_Step2": ("If it stops again, try a shorter recording.", "Hvis det stopper igjen, prøv et kortere opptak."),
    "Score_ControlType": ("score", "partitur"),
    "Score_FullScore": ("All parts", "Alle stemmer"),
    "Score_PartShown": ("{0} part.", "{0}-stemmen."),
    "Score_Checked": ("Kept. {0} left", "Beholdt. {0} igjen"),
    "Score_UncertainLeftOne": ("{0} note marked ? (boxed ? = very unsure)", "{0} tone merket ? (? i boks = svært usikker)"),
    "Score_UncertainLeft": ("{0} notes marked ? (boxed ? = very unsure)", "{0} toner merket ? (? i boks = svært usikker)"),
    "Score_ListeningOriginal": ("Playing bar {0} from the recording", "Spiller takt {0} fra opptaket"),
    "Score_ListeningScore": ("Playing bar {0}", "Spiller takt {0}"),
    "Score_ListenStopped": ("Stopped", "Stoppet"),
    "Score_ListenEnded": ("End of bar {0}", "Slutt på takt {0}"),
    "Review_Listen": ("Listen to this bar", "Lytt til denne takten"),
    "Review_Stop": ("Stop", "Stopp"),
    "Connection_Connected": ("Connected to Brasscribe on {0}", "Koblet til Brasscribe på {0}"),
    "Connection_Reconnecting": ("Looking for Brasscribe on {0} …", "Leter etter Brasscribe på {0} …"),
    "Connection_Offline": ("Not connected. You can still make scores on this PC.", "Ikke tilkoblet. Du kan fortsatt lage partitur på denne PC-en."),
    "Connection_NeedsPairing": ("The computer no longer recognises this PC.", "Datamaskinen kjenner ikke igjen denne PC-en lenger."),
    "Connection_Connect": ("Connect", "Koble til"),
    "Connection_PairAgain": ("Pair this PC again", "Koble til PC-en på nytt"),
    "Connection_YourComputer": ("your computer", "datamaskinen"),
    "Connection_DetailsAddress": ("Address: {0}", "Adresse: {0}"),
    "Connection_DetailsServerId": ("Server id: {0}", "Server-ID: {0}"),
    "Connection_DetailsLastSeen": ("Last answered: {0}", "Svarte sist: {0}"),
    "Settings_Engine_ChosenPaired": ("Using Brasscribe on {0}. This PC is already paired with it.", "Bruker Brasscribe på {0}. Denne PC-en er allerede koblet til den."),
    "Settings_Engine_Forgotten": ("The computer no longer recognises this PC. Type the six digits it shows, or ask on the computer instead.", "Datamaskinen kjenner ikke igjen denne PC-en lenger. Skriv inn de seks sifrene den viser, eller spør på datamaskinen i stedet."),
    "Settings_Engine_CodeWrong": ("That code didn't work. Check the six digits on the computer and try again.", "Den koden virket ikke. Sjekk de seks sifrene på datamaskinen, og prøv igjen."),
    "Settings_Engine_Locked": ("Too many wrong codes. Wait a moment, or ask on the computer instead.", "For mange feil koder. Vent litt, eller spør på datamaskinen i stedet."),
    "Settings_Engine_Unreachable": ("Couldn't reach your computer. Check that Brasscribe is running there and that both are on the same network.", "Fikk ikke kontakt med datamaskinen. Sjekk at Brasscribe kjører der, og at begge er på samme nettverk."),
    "Settings_Engine_Failed": ("Something went wrong talking to your computer. Try again.", "Noe gikk galt i kontakten med datamaskinen. Prøv igjen."),
    "Settings_Engine_AskWaiting": ("On the computer, choose Allow when it shows this number: {0}", "Velg Godkjenn på datamaskinen når den viser dette tallet: {0}"),
    "Settings_Engine_AskDenied": ("The computer didn't allow this PC. You can ask again.", "Datamaskinen godkjente ikke denne PC-en. Du kan spørre på nytt."),
    "Settings_Engine_AskExpired": ("The computer didn't answer in time. You can ask again.", "Datamaskinen svarte ikke i tide. Du kan spørre på nytt."),
    "Settings_Engine_AskBusy": ("Other devices are waiting on the computer. Try again in a couple of minutes.", "Andre enheter venter på datamaskinen. Prøv igjen om et par minutter."),
    "Settings_Engine_Unpaired": ("This PC is no longer paired with Brasscribe on {0}.", "Denne PC-en er ikke lenger koblet til Brasscribe på {0}."),
    "Settings_Link_Invalid": ("That link isn't a Brasscribe pairing link.", "Den lenken er ikke en tilkoblingslenke fra Brasscribe."),
    "Settings_Link_Newer": ("That link is from a newer Brasscribe. Update this app, then try again.", "Lenken er fra en nyere Brasscribe. Oppdater appen, og prøv igjen."),
    "Settings_Link_Looking": ("Looking for Brasscribe on {0} …", "Leter etter Brasscribe på {0} …"),
    "Settings_Link_NotFound": ("Couldn't find Brasscribe on {0}. Check that this PC is on the same network as the computer.", "Fant ikke Brasscribe på {0}. Sjekk at denne PC-en er på samme nettverk som datamaskinen."),
    "Score_Zoom": ("Zoom {0} percent", "Zoom {0} prosent"),
    "Score_NoOriginal": ("There's no recording to hear: this score was opened without one.", "Det finnes ikke noe opptak å høre: partituret ble åpnet uten."),
    "Score_SwitchedToOriginal": ("Playing the recording from bar {0}", "Spiller opptaket fra takt {0}"),
    "Score_SwitchedToScore": ("Playing the band", "Spiller bandet"),
    "Score_LoopLabel": ("Repeat {0}–{1}", "Gjenta {0}–{1}"),
    "Score_AsWritten": ("As written", "Notert"),
    "Score_AsWrittenFor": ("As written for {0}", "Notert for {0}"),
    "Pip_Title": ("Original video", "Originalvideo"),
    "Shortcut_SwitchSource": ("Hear the band or the recording", "Hør bandet eller opptaket"),
    "Player_Position": ("Bar {0} of {1}", "Takt {0} av {1}"),
    "Player_BarBeat": ("Bar {0}, beat {1}", "Takt {0}, slag {1}"),
    "Player_Of": ("of {0}", "av {0}"),
    "Player_Tempo": ("♩ = {0}", "♩ = {0}"),
    "Player_TempoSlowed": ("♩ = {0} (slowed from {1})", "♩ = {0} (ned fra {1})"),
    "Player_TempoFaster": ("♩ = {0} (faster than {1})", "♩ = {0} (opp fra {1})"),
    "Player_LoopOff": ("Not repeating", "Gjentar ikke"),
    "Player_LoopSet": ("Repeating bars {0} to {1}", "Gjentar takt {0} til {1}"),
    "Player_LoopStartAt": ("Repeat starts at bar {0}", "Gjentakelsen starter i takt {0}"),
    "Player_NotReady": ("The sound isn't ready yet: no instrument sounds are loaded.", "Lyden er ikke klar ennå: ingen instrumentlyder er lastet."),
    "Player_PlayAlongOn": ("{0} muted so you can play along", "{0} er uten lyd, så du kan spille med"),
    "Player_PlayAlongOff": ("Your part plays again", "Stemmen din spiller igjen"),
    "Player_Speed": ("Speed {0} percent", "Tempo {0} prosent"),
    "Player_Muted": ("{0} muted", "{0} uten lyd"),
    "Player_Unmuted": ("{0} on", "{0} på"),
    "Player_Soloed": ("Only {0}", "Bare {0}"),
    "Player_Unsoloed": ("All parts again", "Alle stemmer igjen"),
    "Player_CountInOn": ("Count-in on", "Inntelling på"),
    "Player_CountInOff": ("Count-in off", "Inntelling av"),
    "Player_MetronomeOn": ("Metronome on", "Metronom på"),
    "Player_MetronomeOff": ("Metronome off", "Metronom av"),
    "Mixer_Mute": ("Mute {0}", "Lyd av {0}"),
    "Mixer_Solo": ("Only this: {0}", "Bare denne: {0}"),
    "Export_Format_MusicXmlScore": ("MusicXML, conductor's score", "MusicXML, dirigentpartitur"),
    "Export_Format_MusicXmlPart": ("MusicXML, one part", "MusicXML, én stemme"),
    "Export_Format_Pdf": ("PDF", "PDF"),
    "Export_Format_PdfPart": ("PDF, one part", "PDF, én stemme"),
    "Export_Format_Midi": ("MIDI", "MIDI"),
    "Export_Format_Audio": ("Audio (MP3)", "Lyd (MP3)"),
    "Export_Format_TalkingScoreHtml": ("Talking score, web page", "Talende partitur, nettside"),
    "Export_Format_TalkingScoreText": ("Talking score, plain text", "Talende partitur, ren tekst"),
    "Export_Format_Braille": ("Braille music (BRF)", "Punktskrift for noter (BRF)"),
    "Export_Pdf": ("PDF", "PDF"),
    "Export_Pdf_For": ("For printing and the music stand", "For utskrift og notestativet"),
    "Export_MusicXml": ("MusicXML", "MusicXML"),
    "Export_MusicXml_For": ("Edit in MuseScore, Sibelius or Dorico", "Rediger i MuseScore, Sibelius eller Dorico"),
    "Export_Audio": ("Audio", "Lyd"),
    "Export_Audio_For": ("MP3 of the score, to practise with", "MP3 av partituret, til å øve med"),
    "Export_Midi": ("MIDI", "MIDI"),
    "Export_Midi_For": ("For other music apps", "For andre musikkapper"),
    "Export_TalkingScore": ("Talking score", "Talende partitur"),
    "Export_TalkingScore_For": ("Text a screen reader can read aloud", "Tekst en skjermleser kan lese opp"),
    "Export_Braille": ("Braille music", "Punktskrift for noter"),
    "Export_Braille_For": ("BRF file for a braille display or embosser", "BRF-fil for leselist eller punktskriver"),
    "Export_Scope_MyPart": ("{0} (you)", "{0} (deg)"),
    "Export_Scope_Conductor": ("Conductor's score", "Dirigentpartitur"),
    "Export_SaveOne": ("Save…", "Lagre …"),
    "Export_SaveMany": ("Save {0} files…", "Lagre {0} filer …"),
    "Export_SummaryOne": ("{0} file", "{0} fil"),
    "Export_SummaryMany": ("{0} files", "{0} filer"),
    "Export_Printing": ("Sent to the printer", "Sendt til skriveren"),
    "Export_Reason_NeedsEngine": ("Needs Brasscribe on your computer, which made this score.", "Krever Brasscribe på datamaskinen, som laget dette partituret."),
    "Export_Reason_NoScore": ("Open or make a score first.", "Åpne eller lag et partitur først."),
    "Export_Done": ("Saved {0}", "Lagret {0}"),
    "Export_DoneMany": ("Saved {0} files in {1}", "Lagret {0} filer i {1}"),
    "Export_Failed": ("Couldn't save: {0}", "Kunne ikke lagre: {0}"),
    "Output_NeedsEngine": ("How hard and the key are set by Brasscribe on your computer. Open a score it made to change them.", "Vanskegrad og toneart settes av Brasscribe på datamaskinen. Åpne et partitur den har laget for å endre dem."),
    "Output_Rearranging": ("Arranging again with your choices", "Arrangerer på nytt med valgene dine"),
    "Output_KeyAsRecordedDetail": ("As recorded · concert pitch", "Som i opptaket · klingende"),
    "Output_KeyConcert": ("{0} (concert)", "{0} (klingende)"),
    "Output_KeyWritten": ("{0} for {1} instruments", "{0} for {1}-instrumenter"),
    "Output_KeyConcertDetail": ("Concert pitch", "Klingende"),
    "Key_AsRecorded": ("As recorded", "Som i opptaket"),
    "Output_NeedsCore": ("Arranging on this PC needs Brasscribe's arranger, which isn't installed.", "Arrangering på denne PC-en krever arrangøren i Brasscribe, som ikke er installert."),
    "Output_Ready": ("The score is ready", "Partituret er klart"),
    "Output_Failed": ("Couldn't arrange it: {0}", "Kunne ikke arrangere: {0}"),
    "Settings_Engine_NeedsCode": ("Your computer asks for a code. Type the six digits it shows, or ask on the computer instead.", "Datamaskinen ber om en kode. Skriv inn de seks sifrene den viser, eller spør på datamaskinen i stedet."),
    "Settings_Engine_Connected": ("Connected to Brasscribe on {0}.", "Koblet til Brasscribe på {0}."),
    "Settings_CoreVersion": ("Arranger on this PC: {0}", "Arrangør på denne PC-en: {0}"),
    "Settings_CoreManaged": ("built in (the full arranger isn't installed)", "innebygd (den fulle arrangøren er ikke installert)"),
    "Shortcuts_Global": ("Everywhere", "Overalt"),
    "Shortcuts_Score": ("In the score", "I partituret"),
    "Shortcut_Import": ("Open a recording", "Åpne et opptak"),
    "Shortcut_Record": ("Start or stop recording", "Start eller stopp opptak"),
    "Shortcut_PlayPauseGlobal": ("Play or pause", "Spill av eller pause"),
    "Shortcut_Export": ("Share or print", "Del eller skriv ut"),
    "Shortcut_GoToBar": ("Go to bar", "Gå til takt"),
    "Shortcut_TalkingScore": ("Read aloud, or back to the notes", "Les opp, eller tilbake til notene"),
    "Shortcut_Settings": ("Settings", "Innstillinger"),
    "Shortcut_Help": ("Keyboard shortcuts", "Hurtigtaster"),
    "Shortcut_Close": ("Close a dialog or leave the score", "Lukk en dialog eller gå ut av partituret"),
    "Shortcut_PlayPause": ("Play or pause", "Spill av eller pause"),
    "Shortcut_Note": ("Next or previous note", "Neste eller forrige tone"),
    "Shortcut_Beat": ("Next or previous beat", "Neste eller forrige slag"),
    "Shortcut_Bar": ("Next or previous bar", "Neste eller forrige takt"),
    "Shortcut_Part": ("Next or previous part", "Neste eller forrige stemme"),
    "Shortcut_FirstLast": ("First or last bar", "Første eller siste takt"),
    "Shortcut_Uncertain": ("Next or previous note marked ?", "Neste eller forrige tone merket ?"),
    "Shortcut_Checked": ("Keep the note", "Behold tonen"),
    "Shortcut_ReadBar": ("Read the bar", "Les takten"),
    "Shortcut_PlayBar": ("Play this bar, or play from here", "Spill denne takten, eller spill herfra"),
    "Shortcut_WhereAmI": ("Where am I (everything)", "Hvor er jeg (alt)"),
    "Shortcut_Loop": ("Repeat from, repeat to, repeat on or off", "Gjenta fra, gjenta til, gjenta av eller på"),
    "Shortcut_Speed": ("Slower, faster, normal speed", "Saktere, raskere, normalt tempo"),
    "Shortcut_MuteSolo": ("Mute the part, or only this part", "Lyd av stemmen, eller bare denne stemmen"),
    "Shortcut_CountInMetronome": ("Count-in, metronome", "Inntelling, metronom"),
    "Shortcut_Zoom": ("Zoom out, zoom in, reset zoom", "Zoom ut, zoom inn, tilbakestill zoom"),
    "Shortcut_Leave": ("Leave the score", "Gå ut av partituret"),
}
for k, (en, nb) in code.items():
    add(k, en, nb)


# ---- added with the evidence review and score editing (kept in step with the .resw) ----
add('ChangeNote_Down', 'Down a semitone', 'En halvtone ned')
add('ChangeNote_Heard', 'What each transcriber heard', 'Hva hver transkriberer hørte')
add('ChangeNote_Save', 'Save', 'Lagre')
add('ChangeNote_Title', 'Change note', 'Endre tone')
add('ChangeNote_Up', 'Up a semitone', 'En halvtone opp')
add('DiscoveredEnginesList.[using:Microsoft.UI.Xaml.Automation]AutomationProperties.Name', 'Computers running Brasscribe on this network', 'Datamaskiner som kjører Brasscribe på dette nettverket')
add('EditTitleItem.Text', 'Edit score title', 'Endre partiturnavn')
add('FindEnginesButton.Content', 'Find on this network', 'Finn på dette nettverket')
add('FindEnginesButton.[using:Microsoft.UI.Xaml.Automation]AutomationProperties.HelpText', 'Look for computers running Brasscribe on the same network', 'Se etter datamaskiner som kjører Brasscribe på samme nettverk')
add('Library_DeleteFailed', "Couldn't delete {0}. Is your computer on?", 'Kunne ikke slette {0}. Er datamaskinen på?')
add('Library_Deleted', 'Deleted {0}', 'Slettet {0}')
add('Library_OnComputer', '{0} · On your computer', '{0} · På datamaskinen din')
add('ReviewConfidence.[using:Microsoft.UI.Xaml.Automation]AutomationProperties.Name', 'How sure Brasscribe is', 'Hvor sikker Brasscribe er')
add('ReviewHeardHeading.Text', 'What each transcriber heard', 'Hva hver transkriberer hørte')
add('ReviewHowSure.Text', 'How sure Brasscribe is', 'Hvor sikker Brasscribe er')
add('Review_HeardNothing', 'No note', 'Ingen tone')
add('Review_HeardSame', 'Same, {0}', 'Samme, {0}')
add('Review_LevelAlternative', '{0}: it could also be {1}.', '{0}: det kan også være {1}.')
add('Review_WordUncertain', 'Uncertain', 'Usikker')
add('Review_WordVeryUncertain', 'Very uncertain', 'Svært usikker')
add('ScoreOptionsButton.[using:Microsoft.UI.Xaml.Automation]AutomationProperties.Name', 'Score options', 'Valg for partituret')
add('ScoreOptions_CheckNotes', 'Check the notes', 'Sjekk tonene')
add('ScoreOptions_Delete', 'Delete', 'Slett')
add('ScoreOptions_DeleteComputer', 'The score is removed from your computer.', 'Partituret fjernes fra datamaskinen din.')
add('ScoreOptions_DeleteThisPc', 'The score is removed from this PC.', 'Partituret fjernes fra denne PC-en.')
add('ScoreOptions_DeleteTitle', 'Delete “{0}”?', 'Slette «{0}»?')
add('ScoreOptions_EditTitle', 'Edit title', 'Endre navn')
add('Score_CancelTitle', 'Cancel', 'Avbryt')
add('Score_EditTitle', 'Edit score title', 'Endre partiturnavn')
add('Score_RenameFailed', "Couldn't rename {0}", 'Kunne ikke endre navn på {0}')
add('Score_SaveTitle', 'Save', 'Lagre')
add('Settings_Engine_Chosen', 'Using Brasscribe on {0}. Type the six-digit code it shows, then choose Connect.', 'Bruker Brasscribe på {0}. Skriv inn den sekssifrede koden den viser, og velg Koble til.')
add('Settings_Engine_FoundMany', 'Found {0} computers running Brasscribe. Choose one.', 'Fant {0} datamaskiner som kjører Brasscribe. Velg én.')
add('Settings_Engine_FoundOne', 'Found Brasscribe on {0}. Choose it to use it.', 'Fant Brasscribe på {0}. Velg den for å bruke den.')
add('Settings_Engine_NoneFound', 'No computer running Brasscribe was found on this network. Check that Brasscribe on the computer says Running, and that both are on the same Wi-Fi.', 'Fant ingen datamaskin som kjører Brasscribe på dette nettverket. Sjekk at Brasscribe på datamaskinen sier at den kjører, og at begge er på samme wifi.')
add('Settings_Engine_Searching', 'Looking for Brasscribe on your network…', 'Ser etter Brasscribe på nettverket …')

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
