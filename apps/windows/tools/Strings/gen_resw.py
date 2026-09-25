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


# ---- window and header ----
add("AppWindowTitle", "Brasscribe Play", "Brasscribe Play")
prop("AppTitle", "Text", "Brasscribe Play", "Brasscribe Play")
icon_button("BackButton", "Back", "Tilbake", "Go back to the previous screen (Alt+Left)", "Gå tilbake til forrige skjermbilde (Alt+Venstre)")
name("ExportButton", "Export", "Eksporter"); help_("ExportButton", "Save the score, a part, MIDI, audio or the talking score (Ctrl+E)", "Lagre partituret, en stemme, MIDI, lyd eller den talende noten (Ctrl+E)")
prop("ExportButtonLabel", "Text", "Export", "Eksporter")
icon_button("SettingsButton", "Settings", "Innstillinger", "Language, keyboard, talking score and engine (Ctrl+,)", "Språk, tastatur, talende note og motor (Ctrl+,)")
icon_button("HelpButton", "Keyboard shortcuts", "Hurtigtaster", "Show every keyboard shortcut (F1)", "Vis alle hurtigtaster (F1)")

# ---- start ----
prop("StartHeading", "Text", "Make a brass-band score", "Lag et korpspartitur")
prop("StartIntro", "Text", "Import a recording or a video, or record what you hear. Brasscribe writes it out for brass band.",
     "Importer et opptak eller en video, eller ta opp det du hører. Brasscribe skriver det ut for brassband.")
name("ImportButton", "Import audio or video", "Importer lyd eller video"); help_("ImportButton", "Open an audio file, a video file or a MusicXML score (Ctrl+O)", "Åpne en lydfil, en videofil eller et MusicXML-partitur (Ctrl+O)")
prop("ImportButtonLabel", "Text", "Import audio or video", "Importer lyd eller video")
name("DecodingProgress", "Reading the file", "Leser filen")
prop("RecordHeading", "Text", "Record", "Ta opp")
name("RecordMicButton", "Record with the microphone", "Ta opp med mikrofonen"); help_("RecordMicButton", "Record yourself or the room (Ctrl+Shift+R)", "Ta opp deg selv eller rommet (Ctrl+Shift+R)")
prop("RecordMicButtonLabel", "Text", "Record with the microphone", "Ta opp med mikrofonen")
name("RecordSystemButton", "Record what this PC plays", "Ta opp det PC-en spiller"); help_("RecordSystemButton", "Record everything the speakers play", "Ta opp alt som spilles i høyttalerne")
prop("RecordSystemButtonLabel", "Text", "Record what this PC plays", "Ta opp det PC-en spiller")
prop("AppPicker", "Header", "App to record", "App som skal tas opp"); prop("AppPicker", "PlaceholderText", "Choose an app that is playing", "Velg en app som spiller")
help_("AppPicker", "Apps that play sound right now are listed first", "Apper som spiller lyd akkurat nå, står øverst")
icon_button("RefreshAppsButton", "Refresh the app list", "Oppdater applisten", "Look again for apps that play sound", "Se etter apper som spiller lyd på nytt")
name("RecordAppButton", "Record only this app", "Ta opp bare denne appen"); help_("RecordAppButton", "Record the chosen app and nothing else", "Ta opp den valgte appen og ingenting annet")
prop("RecordAppButtonLabel", "Text", "Record only this app", "Ta opp bare denne appen")
prop("AppCaptureUnavailable", "Text", "Recording a single app needs Windows 11. You can still record everything this PC plays.",
     "Opptak av én app krever Windows 11. Du kan fortsatt ta opp alt PC-en spiller.")
name("RecordingTime", "Recording time", "Opptakstid")
name("LevelMeter", "Input level", "Inngangsnivå")
prop("StopRecordingButton", "Content", "Stop recording", "Stopp opptaket"); help_("StopRecordingButton", "Stop and continue with the recording (Ctrl+Shift+R)", "Stopp og gå videre med opptaket (Ctrl+Shift+R)")
prop("CaptureNotice", "Title", "Nothing is being recorded", "Ingenting blir tatt opp")
prop("StartError", "Title", "That did not work", "Det gikk ikke")
prop("DrmNote", "Text", "Windows does not let apps record protected (DRM) playback, such as some streaming services. Brasscribe tells you when that happens instead of recording silence.",
     "Windows lar ikke apper ta opp beskyttet avspilling (DRM), for eksempel fra noen strømmetjenester. Brasscribe sier fra når det skjer, i stedet for å ta opp stillhet.")
prop("LinkNote", "Text", "Links such as YouTube are not downloaded. Play the video and record it, or import a file you have.",
     "Lenker, for eksempel til YouTube, lastes ikke ned. Spill av videoen og ta den opp, eller importer en fil du har.")

# ---- what is this ----
prop("KindHeading", "Text", "What is this?", "Hva er dette?")
prop("KindIntro", "Text", "Choose what the recording is. The answer decides how it is transcribed.",
     "Velg hva opptaket er. Svaret avgjør hvordan det blir transkribert.")
prop("KindOptions", "Header", "Recording type", "Type opptak")
prop("ContinueButton", "Content", "Continue", "Fortsett"); help_("ContinueButton", "Start the transcription. Choose what the recording is first.", "Start transkripsjonen. Velg først hva opptaket er.")

# ---- transcription ----
prop("TranscribeHeading", "Text", "Transcribing", "Transkriberer")
name("TranscribeProgress", "Transcription progress", "Framdrift for transkripsjonen")
prop("TranscribeErrorBar", "Title", "Transcription stopped", "Transkripsjonen stoppet")
text_button("TranscribeBackButton", "Back to the choices", "Tilbake til valgene", "Choose again or check the engine settings, the recording is kept", "Velg på nytt eller sjekk innstillingene for motoren, opptaket beholdes")
prop("CancelTranscriptionButton", "Content", "Cancel", "Avbryt"); help_("CancelTranscriptionButton", "Stop the transcription", "Stopp transkripsjonen")

# ---- score ----
prop("AdLibNotice", "Text", "Some passages are in free time (ad lib.). They are written by feel, not on a strict beat.",
     "Noen partier er i fritt tempo (ad lib.). De er notert etter gehør, ikke på et fast slag.")
prop("PartPicker", "Header", "Show", "Vis"); help_("PartPicker", "The full score or one part in written pitch", "Hele partituret eller én stemme i skrevet tone")
prop("ConcertPitchSwitch", "Header", "Concert pitch", "Klingende tone"); help_("ConcertPitchSwitch", "Show sounding pitch instead of written pitch", "Vis klingende tone i stedet for skrevet tone")
icon_button("ZoomOutButton", "Zoom out", "Zoom ut", "Smaller notation (Ctrl+-)", "Mindre noter (Ctrl+-)")
prop("ZoomBox", "Header", "Zoom, percent", "Zoom, prosent"); help_("ZoomBox", "Notation size from 50 to 400 percent", "Notestørrelse fra 50 til 400 prosent")
icon_button("ZoomInButton", "Zoom in", "Zoom inn", "Larger notation (Ctrl+=)", "Større noter (Ctrl+=)")
text_button("TalkingScoreToggle", "Talking score", "Talende note", "Show the score as text, one line per note (Ctrl+T)", "Vis noten som tekst, én linje per note (Ctrl+T)")
text_button("OutputOptionsButton", "Output", "Utgave", "Lineup, difficulty and key", "Besetning, vanskegrad og toneart")
prop("OutputHeading", "Text", "Choose output", "Velg utgave")
prop("LineupBox", "Header", "Lineup", "Besetning")
prop("LineupFull", "Content", "Full band", "Fullt korps")
prop("LineupMinimal", "Content", "Minimal band", "Lite korps")
prop("DifficultyBox", "Header", "Difficulty", "Vanskegrad")
prop("DifficultyFaithful", "Content", "Faithful", "Tro mot opptaket")
prop("DifficultyStandard", "Content", "Standard", "Standard")
prop("DifficultyEasier", "Content", "Easier", "Enklere")
prop("KeyBox", "Header", "Key", "Toneart")
prop("KeyOriginal", "Content", "As recorded", "Som i opptaket")
text_button("ApplyOutputButton", "Apply", "Bruk", "Arrange again with these choices", "Arranger på nytt med disse valgene")
name("ScoreNotation", "Score", "Partitur")
help_("ScoreNotation", "Arrows move by note, Ctrl+arrows by beat and bar, Ctrl+Shift+arrows by part. U finds uncertain notes. Tab leaves the score.",
      "Piltaster flytter én note, Ctrl+piltaster ett slag eller én takt, Ctrl+Shift+piltaster én stemme. U finner usikre noter. Tab går ut av noten.")
prop("ListenToBarItem", "Text", "Listen to this bar", "Lytt til denne takten")
prop("MarkCheckedItem", "Text", "Mark as checked", "Merk som kontrollert")
prop("ReadBarItem", "Text", "Read bar", "Les takten")
prop("GoToBarItem", "Text", "Go to bar…", "Gå til takt …")
prop("LoopStartItem", "Text", "Loop starts here", "Løkken starter her")
prop("LoopEndItem", "Text", "Loop ends here", "Løkken slutter her")
name("TalkingList", "Talking score", "Talende note")
prop("MixerHeading", "Text", "Parts", "Stemmer")
name("Mixer", "Mixer", "Mikser")
name("PlayerBar", "Player", "Avspiller")
icon_button("PlayPauseButton", "Play or pause", "Spill av eller pause", "Space in the score, Ctrl+Shift+Space anywhere", "Mellomrom i noten, Ctrl+Shift+Mellomrom hvor som helst")
icon_button("StopButton", "Stop", "Stopp", "Stop playback", "Stopp avspillingen")
text_button("ListenBarButton", "Listen to bar", "Lytt til takt", "Play the current bar, looped (P)", "Spill den gjeldende takten i løkke (P)")
text_button("MarkCheckedButton", "Mark as checked", "Merk som kontrollert", "The note is right; stop marking it uncertain (C)", "Noten er riktig; slutt å merke den som usikker (C)")
name("SlowerButton", "Slower", "Saktere"); help_("SlowerButton", "5 percent slower (-)", "5 prosent saktere (-)")
prop("SpeedSlider", "Header", "Speed", "Tempo"); help_("SpeedSlider", "25 to 150 percent, without changing pitch", "25 til 150 prosent, uten å endre tonehøyden")
name("FasterButton", "Faster", "Raskere"); help_("FasterButton", "5 percent faster (=)", "5 prosent raskere (=)")
prop("LoopStartBox", "Header", "Loop from bar", "Løkke fra takt")
prop("LoopEndBox", "Header", "to bar", "til takt")
text_button("SetLoopButton", "Set loop", "Lag løkke", "Loop the bars you typed (L)", "Spill taktene du skrev inn i løkke (L)")
text_button("ClearLoopButton", "Clear loop", "Fjern løkke", "Play without a loop", "Spill uten løkke")
text_button("CountInToggle", "Count-in", "Innslag", "Count one bar before playing (K)", "Slå inn én takt før avspilling (K)")
text_button("MetronomeToggle", "Metronome", "Metronom", "Click on every beat (T)", "Klikk på hvert slag (T)")
prop("TransposeBox", "Header", "Transpose, semitones", "Transponer, halvtoner")
text_button("PlayAlongToggle", "Play along", "Spill med", "Mute your part and play it yourself, with a count-in", "Demp stemmen din og spill den selv, med innslag")

# ---- dialogs ----
prop("ExportDialog", "Title", "Export", "Eksporter"); prop("ExportDialog", "PrimaryButtonText", "Save…", "Lagre …"); prop("ExportDialog", "CloseButtonText", "Close", "Lukk")
name("ExportFormatList", "Format", "Format")
prop("ExportPartBox", "Header", "Part", "Stemme")
prop("GoToBarDialog", "Title", "Go to bar", "Gå til takt"); prop("GoToBarDialog", "PrimaryButtonText", "Go", "Gå"); prop("GoToBarDialog", "CloseButtonText", "Cancel", "Avbryt")
prop("GoToBarBox", "Header", "Bar number", "Taktnummer")
prop("ShortcutsDialog", "Title", "Keyboard shortcuts", "Hurtigtaster"); prop("ShortcutsDialog", "CloseButtonText", "Close", "Lukk")
prop("SettingsDialog", "Title", "Settings", "Innstillinger"); prop("SettingsDialog", "CloseButtonText", "Close", "Lukk")
prop("SettingsLanguageHeading", "Text", "Language", "Språk")
prop("LanguageBox", "Header", "App language", "Appspråk")
prop("LanguageSystem", "Content", "Same as Windows", "Samme som Windows")
prop("LanguageRestartNote", "Text", "A new language is used the next time you start the app.", "Nytt språk tas i bruk neste gang du starter appen.")
prop("SettingsAccessibilityHeading", "Text", "Accessibility", "Tilgjengelighet")
prop("SingleKeySwitch", "Header", "Single-key shortcuts in the score", "Hurtigtaster med én tast i noten")
help_("SingleKeySwitch", "Keys such as U, R and P. Arrows always work.", "Taster som U, R og P. Piltastene virker alltid.")
prop("ReduceMotionSwitch", "Header", "Reduce motion", "Mindre bevegelse")
help_("ReduceMotionSwitch", "The cursor jumps per beat and the score turns pages instead of scrolling", "Markøren hopper ett slag om gangen, og noten blar i stedet for å rulle")
prop("VerbosityBox", "Header", "Talking score detail", "Detaljer i talende note")
prop("VerbosityBrief", "Content", "Brief", "Kort")
prop("VerbosityStandard", "Content", "Standard", "Standard")
prop("VerbosityFull", "Content", "Full", "Full")
prop("SettingsEngineHeading", "Text", "Transcription engine", "Transkripsjonsmotor")
prop("EngineAddressBox", "Header", "Engine address", "Adresse til motoren")
prop("EngineAddressBox", "PlaceholderText", "http://127.0.0.1:8765", "http://127.0.0.1:8765")
prop("PairingCodeBox", "Header", "Pairing code", "Paringskode")
prop("PairingCodeBox", "PlaceholderText", "Shown by the engine on the other computer", "Vises av motoren på den andre datamaskinen")
text_button("ConnectButton", "Connect", "Koble til", "Check the engine and pair with the code if it asks for one", "Sjekk motoren og par med koden hvis den ber om det")
prop("SettingsAboutHeading", "Text", "About", "Om")
prop("AboutText", "Text",
     "Brasscribe Play is a non-commercial project. Notation and synth: alphaTab (MPL-2.0). Transcription models run in the Brasscribe engine; MuScriptor weights are CC BY-NC 4.0 and are downloaded by you.",
     "Brasscribe Play er et ikke-kommersielt prosjekt. Noter og synth: alphaTab (MPL-2.0). Transkripsjonsmodellene kjører i Brasscribe-motoren; MuScriptor-vektene er CC BY-NC 4.0 og lastes ned av deg.")

# ---- code strings ----
code = {
    "Duration_MinutesSeconds": ("{0} min {1} s", "{0} min {1} s"),
    "Duration_Seconds": ("{0} s", "{0} s"),
    "Screen_Start": ("Start", "Start"),
    "Screen_SourceKind": ("What is this?", "Hva er dette?"),
    "Screen_Transcribing": ("Transcribing", "Transkriberer"),
    "Screen_Score": ("Score", "Partitur"),
    "Start_Imported": ("Imported {0}, {1}", "Importerte {0}, {1}"),
    "Start_RecordingName": ("Recording", "Opptak"),
    "Start_RecordingStarted": ("Recording started", "Opptaket har startet"),
    "Start_RecordingStopped": ("Recording stopped, {0}", "Opptaket er stoppet, {0}"),
    "Start_Error_Link": ("Links are not downloaded. Play the video and record it, or import a file.", "Lenker lastes ikke ned. Spill av videoen og ta den opp, eller importer en fil."),
    "Start_Error_Unsupported": ("{0} is not an audio, video or MusicXML file.", "{0} er ikke en lyd-, video- eller MusicXML-fil."),
    "Start_Error_Decode": ("{0} could not be read. Try another file.", "{0} kunne ikke leses. Prøv en annen fil."),
    "Start_Error_Score": ("{0} could not be opened as a score.", "{0} kunne ikke åpnes som partitur."),
    "Start_Error_AppCaptureUnsupported": ("Recording a single app needs Windows 11.", "Opptak av én app krever Windows 11."),
    "Start_Error_ChooseApp": ("Choose the app to record first.", "Velg først appen som skal tas opp."),
    "Start_Error_MicrophonePermission": ("Brasscribe may not use the microphone. Allow it in Windows Settings, Privacy, Microphone.", "Brasscribe har ikke lov til å bruke mikrofonen. Gi tilgang i Windows-innstillinger, Personvern, Mikrofon."),
    "Start_Error_Capture": ("Recording could not start: {0}", "Opptaket kunne ikke starte: {0}"),
    "Start_Error_TooShort": ("The recording is shorter than a second. Try again.", "Opptaket er kortere enn ett sekund. Prøv igjen."),
    "Start_Level_Silent": ("Input level, silent", "Inngangsnivå, stille"),
    "Start_Level_Low": ("Input level, low", "Inngangsnivå, lavt"),
    "Start_Level_Good": ("Input level, good", "Inngangsnivå, bra"),
    "Start_Level_TooLoud": ("Input level, too loud", "Inngangsnivå, for høyt"),
    "Start_Notice_SilenceWhilePlaying": ("The app is playing, but Windows gives Brasscribe only silence. This happens with protected (DRM) playback, which cannot be recorded.", "Appen spiller, men Windows gir Brasscribe bare stillhet. Det skjer med beskyttet avspilling (DRM), som ikke kan tas opp."),
    "Start_Notice_NothingPlaying": ("Only silence is arriving. Check that something is playing. Protected (DRM) playback cannot be recorded.", "Det kommer bare stillhet. Sjekk at noe spiller. Beskyttet avspilling (DRM) kan ikke tas opp."),
    "Start_Notice_TooLoud": ("The input is too loud and distorts. Turn the volume down a little.", "Inngangen er for høy og forvrenges. Skru ned volumet litt."),
    "Kind_Solo_Label": ("Solo instrument", "Soloinstrument"),
    "Kind_Solo_Description": ("One brass player, alone.", "Én messingblåser alene."),
    "Kind_BrassBand_Label": ("Brass band", "Brassband"),
    "Kind_BrassBand_Description": ("A brass band or brass ensemble.", "Et brassband eller et messingensemble."),
    "Kind_OrchestraWithSoloist_Label": ("Orchestra with soloist", "Orkester med solist"),
    "Kind_OrchestraWithSoloist_Description": ("A soloist in front of an orchestra or backing track.", "En solist foran et orkester eller et komp."),
    "Kind_PopRock_Label": ("Pop or rock", "Pop eller rock"),
    "Kind_PopRock_Description": ("A band with vocals, guitar, bass and drums.", "Et band med sang, gitar, bass og trommer."),
    "Transcribe_Started": ("Transcribing {0} as {1}", "Transkriberer {0} som {1}"),
    "Transcribe_Stage_Upload": ("Sending the recording to the engine", "Sender opptaket til motoren"),
    "Transcribe_Stage_Separate": ("Separating the instruments", "Skiller instrumentene"),
    "Transcribe_Stage_Beats": ("Finding the beat", "Finner slagene"),
    "Transcribe_Stage_Notes": ("Writing down the notes", "Skriver ned notene"),
    "Transcribe_Stage_Arrange": ("Arranging for brass band", "Arrangerer for brassband"),
    "Transcribe_Stage_Engrave": ("Engraving the score", "Setter partituret"),
    "Transcribe_Stage_Working": ("Working", "Arbeider"),
    "Transcribe_Eta_Unknown": ("Estimating the time left", "Beregner tiden som gjenstår"),
    "Transcribe_Eta_UnderMinute": ("Less than a minute left (estimate)", "Under ett minutt igjen (anslag)"),
    "Transcribe_Eta_Minutes": ("About {0} minutes left (estimate)", "Omtrent {0} minutter igjen (anslag)"),
    "Transcribe_Eta_Hours": ("About {0} hours left (estimate)", "Omtrent {0} timer igjen (anslag)"),
    "Transcribe_ProgressAnnouncement": ("{0} percent. {1}. {2}", "{0} prosent. {1}. {2}"),
    "Transcribe_Device": ("Running on {0}", "Kjører på {0}"),
    "Transcribe_Done": ("The score is ready", "Partituret er klart"),
    "Transcribe_Cancelled": ("Transcription cancelled", "Transkripsjonen er avbrutt"),
    "Transcribe_Failed": ("The transcription failed", "Transkripsjonen mislyktes"),
    "Transcribe_Error": ("Transcription stopped: {0}", "Transkripsjonen stoppet: {0}"),
    "CancelDialog_Title": ("Stop the transcription?", "Stoppe transkripsjonen?"),
    "CancelDialog_Content": ("The work done so far is kept by the engine, so starting again is quicker.", "Motoren tar vare på arbeidet så langt, så det går raskere å starte på nytt."),
    "CancelDialog_Stop": ("Stop", "Stopp"),
    "CancelDialog_Keep": ("Keep going", "Fortsett"),
    "Score_ControlType": ("score", "partitur"),
    "Score_FullScore": ("Full score", "Hele partituret"),
    "Score_PartShown": ("{0} part.", "{0}-stemmen."),
    "Score_Checked": ("Checked. {0} left", "Kontrollert. {0} igjen"),
    "Score_UncertainLeft": ("{0} uncertain notes to check", "{0} usikre noter å kontrollere"),
    "Score_ListeningOriginal": ("Playing bar {0} from the recording", "Spiller takt {0} fra opptaket"),
    "Score_ListeningScore": ("Playing bar {0}", "Spiller takt {0}"),
    "Score_Zoom": ("Zoom {0} percent", "Zoom {0} prosent"),
    "Player_Position": ("Bar {0} of {1}", "Takt {0} av {1}"),
    "Player_LoopOff": ("No loop", "Ingen løkke"),
    "Player_LoopSet": ("Loop set, bars {0} to {1}", "Løkke satt, takt {0} til {1}"),
    "Player_LoopStartAt": ("Loop starts at bar {0}", "Løkken starter i takt {0}"),
    "Player_NotReady": ("Playback is not ready: no sound set is loaded.", "Avspillingen er ikke klar: ingen lyder er lastet."),
    "Player_PlayAlongOn": ("Play along: {0} muted", "Spill med: {0} er dempet"),
    "Player_PlayAlongOff": ("Play along off", "Spill med er av"),
    "Player_Speed": ("Speed {0} percent", "Tempo {0} prosent"),
    "Player_Muted": ("{0} muted", "{0} dempet"),
    "Player_Unmuted": ("{0} on", "{0} på"),
    "Player_Soloed": ("{0} solo", "{0} solo"),
    "Player_Unsoloed": ("{0} solo off", "{0} solo av"),
    "Player_CountInOn": ("Count-in on", "Innslag på"),
    "Player_CountInOff": ("Count-in off", "Innslag av"),
    "Player_MetronomeOn": ("Metronome on", "Metronom på"),
    "Player_MetronomeOff": ("Metronome off", "Metronom av"),
    "Mixer_Mute": ("Mute {0}", "Demp {0}"),
    "Mixer_Solo": ("Solo {0}", "Solo {0}"),
    "Export_Format_MusicXmlScore": ("MusicXML, full score", "MusicXML, hele partituret"),
    "Export_Format_MusicXmlPart": ("MusicXML, one part", "MusicXML, én stemme"),
    "Export_Format_Pdf": ("PDF", "PDF"),
    "Export_Format_Midi": ("MIDI", "MIDI"),
    "Export_Format_Audio": ("Audio (MP3)", "Lyd (MP3)"),
    "Export_Format_TalkingScoreHtml": ("Talking score, web page", "Talende note, nettside"),
    "Export_Format_TalkingScoreText": ("Talking score, plain text", "Talende note, ren tekst"),
    "Export_Format_Braille": ("Braille music (BRF)", "Punktskrift for noter (BRF)"),
    "Export_Reason_NeedsEngine": ("Needs the engine that made this score.", "Krever motoren som laget dette partituret."),
    "Export_Reason_NoScore": ("Open or make a score first.", "Åpne eller lag et partitur først."),
    "Export_Reason_BrailleMissing": ("Braille export is not available yet: the engine does not write BRF files.", "Eksport til punktskrift finnes ikke ennå: motoren lager ikke BRF-filer."),
    "Export_Done": ("Saved {0} as {1}", "Lagret {0} som {1}"),
    "Export_Failed": ("Could not save: {0}", "Kunne ikke lagre: {0}"),
    "Output_NotYet": ("Difficulty and key choices are not available yet.", "Valg av vanskegrad og toneart finnes ikke ennå."),
    "Output_NeedsCore": ("Arranging on this PC needs the Brasscribe core library, which is not installed.", "Arrangering på denne PC-en krever Brasscribe-kjernebiblioteket, som ikke er installert."),
    "Output_Ready": ("Arrangement ready", "Arrangementet er klart"),
    "Output_Failed": ("Could not arrange: {0}", "Kunne ikke arrangere: {0}"),
    "Settings_Engine_NeedsCode": ("The engine asks for a pairing code. Type the code it shows.", "Motoren ber om en paringskode. Skriv inn koden den viser."),
    "Settings_Engine_Connected": ("Connected to engine {0}, running on {1}", "Koblet til motor {0}, kjører på {1}"),
    "Settings_CoreVersion": ("Core library: {0}", "Kjernebibliotek: {0}"),
    "Settings_CoreManaged": ("built-in (the native core is not installed)", "innebygd (det native kjernebiblioteket er ikke installert)"),
    "Shortcuts_Global": ("Everywhere", "Overalt"),
    "Shortcuts_Score": ("In the score", "I noten"),
    "Shortcut_Import": ("Import a file", "Importer en fil"),
    "Shortcut_Record": ("Start or stop recording", "Start eller stopp opptak"),
    "Shortcut_PlayPauseGlobal": ("Play or pause", "Spill av eller pause"),
    "Shortcut_Export": ("Export", "Eksporter"),
    "Shortcut_GoToBar": ("Go to bar", "Gå til takt"),
    "Shortcut_TalkingScore": ("Switch between notation and talking score", "Bytt mellom noter og talende note"),
    "Shortcut_Settings": ("Settings", "Innstillinger"),
    "Shortcut_Help": ("Keyboard shortcuts", "Hurtigtaster"),
    "Shortcut_Close": ("Close a dialog or leave the score", "Lukk en dialog eller gå ut av noten"),
    "Shortcut_PlayPause": ("Play or pause", "Spill av eller pause"),
    "Shortcut_Note": ("Next or previous note", "Neste eller forrige note"),
    "Shortcut_Beat": ("Next or previous beat", "Neste eller forrige slag"),
    "Shortcut_Bar": ("Next or previous bar", "Neste eller forrige takt"),
    "Shortcut_Part": ("Next or previous part", "Neste eller forrige stemme"),
    "Shortcut_FirstLast": ("First or last bar", "Første eller siste takt"),
    "Shortcut_Uncertain": ("Next or previous uncertain note", "Neste eller forrige usikre note"),
    "Shortcut_Checked": ("Mark as checked", "Merk som kontrollert"),
    "Shortcut_ReadBar": ("Read the bar", "Les takten"),
    "Shortcut_PlayBar": ("Play this bar, or play from here", "Spill denne takten, eller spill herfra"),
    "Shortcut_WhereAmI": ("Where am I (full detail)", "Hvor er jeg (alle detaljer)"),
    "Shortcut_Loop": ("Loop start, loop end, loop on or off", "Løkkestart, løkkeslutt, løkke av eller på"),
    "Shortcut_Speed": ("Slower, faster, normal speed", "Saktere, raskere, normalt tempo"),
    "Shortcut_MuteSolo": ("Mute or solo the current part", "Demp eller solo gjeldende stemme"),
    "Shortcut_CountInMetronome": ("Count-in, metronome", "Innslag, metronom"),
    "Shortcut_Zoom": ("Zoom out, zoom in, reset zoom", "Zoom ut, zoom inn, tilbakestill zoom"),
    "Shortcut_Leave": ("Leave the score", "Gå ut av noten"),
}
for k, (en, nb) in code.items():
    add(k, en, nb)

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
