"""The research pages' figures. Read by site/research.py; a page shows one with {{chart <name>}} or
{{pipeline <name>}}.

Words are (English, Norwegian). A row's `keys` name its measurements, one per series (None: not
measured); site/research.py says what a key is. `{key}` in a title, caption or note prints that
measurement, so the words around it must stay true when it moves: `holds` lists what the title
asserts, and the build fails when one of them stops being true.
"""

B = "brass/"
F = "fretted/"
BASE = ("<code>eval/baselines.json</code>, ", "<code>eval/baselines.json</code>, ")
CHORALES_N = ("{p/chorales-transcription/pieces|int} chorales, {p/chorales-transcription/notes|int} notes",
              "{p/chorales-transcription/pieces|int} koraler, {p/chorales-transcription/notes|int} toner")
URMP_N = ("{p/urmp-transcription/pieces|int} pieces, {p/urmp-transcription/notes|int} notes",
          "{p/urmp-transcription/pieces|int} stykker, {p/urmp-transcription/notes|int} toner")
CHORALES = ("Brass quartets", "Brasskvartetter")
URMP = ("Chamber brass", "Kammerbrass")
CHORALES_NOTE = ("ChoraleBricks: four real players (trumpet, flugelhorn, baritone, tuba), recorded one at a time and mixed.",
                 "ChoraleBricks: fire ekte musikere (trompet, flygelhorn, baryton, tuba), tatt opp én om gangen og mikset.")
URMP_NOTE = ("URMP: real duos to quintets of trumpet, horn, trombone and tuba.",
             "URMP: ekte duoer til kvintetter med trompet, horn, trombone og tuba.")
RECORDINGS = ("Recordings", "Opptak")
F1_AXIS = ("Onset F1: 0 = nothing right, 1 = every played note found and no extra ones",
           "Onset-F1: 0 = ingenting riktig, 1 = alle spilte toner funnet og ingen ekstra")
SHARE_AXIS = ("Share of notes", "Andel av tonene")

INSTRUMENTS = (("trumpet", ("Trumpet", "Trompet")), ("flugelhorn", ("Flugelhorn", "Flygelhorn")), ("horn", ("French horn", "Valthorn")),
               ("baritone", ("Baritone", "Baryton")), ("trombone", ("Trombone", "Trombone")), ("tuba", ("Tuba", "Tuba")))
STEMS = ("{m/datasets/choralebricks_solo_stems|int} single-instrument recordings in all",
         "{m/datasets/choralebricks_solo_stems|int} opptak av ett instrument i alt")


def transcription(suite, rows):
    return [{"label": label, "keys": [f"{B}{suite}/{model}.onset100_f1" if "100" in has else None,
                                      f"{B}{suite}/{model}.onset_f1" if "50" in has else None]} for label, model, has in rows]


FIGURES = {
    # ------------------------------------------------------------------------------- brass
    "notes-found": {
        "title": ("The best model scores {brass/chorales-transcription/muscriptor-medium.onset100_f1} on brass quartets and "
                  "{brass/urmp-transcription/muscriptor-medium.onset100_f1} on chamber brass",
                  "Den beste modellen får {brass/chorales-transcription/muscriptor-medium.onset100_f1} på brasskvartetter og "
                  "{brass/urmp-transcription/muscriptor-medium.onset100_f1} på kammerbrass"),
        "holds": ["brass/chorales-transcription/muscriptor-medium.onset100_f1 > brass/chorales-transcription/basic-pitch.onset100_f1",
                  "brass/urmp-transcription/muscriptor-medium.onset100_f1 > brass/urmp-transcription/basic-pitch.onset100_f1",
                  "brass/slakh-transcription/pipeB-sw-muscriptor.onset100_f1 > brass/slakh-transcription/muscriptor-medium.onset100_f1"],
        "sub": ("Notes found in the whole recording, every part at once. A dot is one piece; the ringed dot is the mean.",
                "Toner funnet i hele opptaket, alle stemmer samtidig. En prikk er ett stykke; prikken med ring er snittet."),
        "axis": F1_AXIS,
        "series": [("Onset within 100 ms", "Ansats innen 100 ms"), ("Onset within 50 ms", "Ansats innen 50 ms")],
        "view_label": RECORDINGS,
        "views": [
            {"label": CHORALES, "note": CHORALES_NOTE, "n": CHORALES_N,
             "rows": transcription("chorales-transcription", [("MuScriptor medium", "muscriptor-medium", "100 50"), ("Basic Pitch", "basic-pitch", "100 50")])},
            {"label": URMP, "note": URMP_NOTE, "n": URMP_N,
             "rows": transcription("urmp-transcription", [("MuScriptor medium", "muscriptor-medium", "100 50"), ("Basic Pitch", "basic-pitch", "100 50")])},
            {"label": ("Trumpet over a band", "Trompet over et band"),
             "note": ("Slakh: synthesized songs with a trumpet lead. Only the 100 ms score is gated.",
                      "Slakh: syntetiske låter med trompet i front. Bare 100 ms-målet er låst."),
             "n": ("{m/datasets/slakh_trumpet_songs|int} songs", "{m/datasets/slakh_trumpet_songs|int} låter"),
             "rows": transcription("slakh-transcription", [
                 (("Separated first, then MuScriptor", "Separert først, så MuScriptor"), "pipeB-sw-muscriptor", "100"),
                 (("MuScriptor on the whole mix", "MuScriptor på hele miksen"), "muscriptor-medium", "100"),
                 (("Separated first, then Basic Pitch", "Separert først, så Basic Pitch"), "pipeB-sw-basicpitch", "100"),
                 (("Basic Pitch on the whole mix", "Basic Pitch på hele miksen"), "basic-pitch", "100")])},
        ],
        "caption": ("Onset F1 of the two transcribers on real brass, and of the two routes on a full band. A note counts as found when its "
                    "pitch is right and its start is within the tolerance.",
                    "Onset-F1 for de to transkripsjonsmodellene på ekte brass, og for de to veiene på et fullt band. En tone regnes som funnet "
                    "når tonehøyden er riktig og starten er innenfor toleransen."),
        "source": ("<code>eval/baselines.json</code>, suites chorales-transcription, urmp-transcription and slakh-transcription; "
                   "the pieces from <code>site/shared/research/measured/per-piece.json</code>.",
                   "<code>eval/baselines.json</code>, suitene chorales-transcription, urmp-transcription og slakh-transcription; "
                   "stykkene fra <code>site/shared/research/measured/per-piece.json</code>."),
    },
    "rhythm": {
        "title": ("With the score's beats nearly every note lands in its place; with tracked beats under half do",
                  "Med partiturets slag havner nesten alle toner på plass; med slag sporet fra opptaket under halvparten"),
        "holds": ["brass/quant-chorales/beat_this.position_acc < 0.5", "brass/quant-urmp/beat_this.position_acc < 0.5",
                  "brass/quant-chorales/reference_beats.position_acc >= 0.9", "brass/quant-urmp/reference_beats.position_acc >= 0.9"],
        "format": "pct",
        "sub": ("The correct notes are given to the quantizer, so only the beat grid differs. A dot is one piece: with tracked beats the "
                "pieces spread over almost the whole scale.",
                "Kvantiseringen får de riktige tonene, så bare slagrutenettet er ulikt. En prikk er ett stykke: med sporede slag sprer "
                "stykkene seg over nesten hele skalaen."),
        "axis": ("Share of the reference notes written as the score has them", "Andel av referansetonene skrevet slik partituret har dem"),
        "series": [("Beats given (from the score)", "Slag gitt (fra partituret)"), ("Beats tracked (Beat This!)", "Slag sporet (Beat This!)")],
        "view_label": RECORDINGS,
        "views": [{"label": label, "note": note, "n": n, "rows": [
            {"label": text, "keys": [f"{B}{suite}/reference_beats.{key}", f"{B}{suite}/beat_this.{key}"]} for text, key in (
                (("Right place in the bar", "Riktig plass i takten"), "position_acc"),
                (("Right place within the beat", "Riktig plass i slaget"), "subdivision_acc"),
                (("Right written length", "Riktig skrevet lengde"), "duration_acc"))]}
            for label, note, n, suite in ((CHORALES, CHORALES_NOTE, CHORALES_N, "quant-chorales"), (URMP, URMP_NOTE, URMP_N, "quant-urmp"))],
        "caption": ("Rhythm with the beats given and with the beats tracked. Position in the bar needs the bar lines to be right; "
                    "position within the beat does not.",
                    "Rytme med slagene gitt og med slagene sporet. Plass i takten krever at taktstrekene er riktige; plass i slaget gjør det ikke."),
        "source": ("<code>eval/baselines.json</code>, suites quant-chorales and quant-urmp; the pieces from <code>per-piece.json</code>.",
                   "<code>eval/baselines.json</code>, suitene quant-chorales og quant-urmp; stykkene fra <code>per-piece.json</code>."),
    },
    "solo-written": {
        "title": ("From one player's recording the notes are heard, but about one in four is written where the score has it",
                  "Fra opptak av én musiker blir tonene hørt, men omtrent én av fire blir skrevet der partituret har den"),
        "holds": ["brass/solo-beat-model/urmp.small0.written_f1 < 0.3", "brass/solo-beat-model/choralebricks.small0.written_f1 < 0.3",
                  "brass/solo-beat-model/urmp.final0.written_f1 < 0.3", "brass/solo-beat-model/choralebricks.final0.written_f1 < 0.3",
                  "brass/solo-beat-model/urmp.small0.written_f1 > 0.2", "brass/solo-beat-model/choralebricks.small0.written_f1 > 0.2",
                  "brass/solo-beat-model/urmp.small0.onset_f1 > 0.7", "brass/solo-beat-model/choralebricks.small0.onset_f1 > 0.7"],
        "sub": ("The whole solo path with the models a phone has, scored against the player's own part: the same notes, counted first by "
                "pitch and onset, then also by their place in the bar.",
                "Hele soloveien med modellene en telefon har, målt mot musikerens egen stemme: de samme tonene, først talt etter tonehøyde "
                "og ansats, så også etter plassen i takten."),
        "axis": ("F1, 0 to 1", "F1, 0 til 1"),
        "series": [("Heard: pitch and onset within 100 ms", "Hørt: tonehøyde og ansats innen 100 ms"),
                   ("Written in place: also in the right place in the bar", "Skrevet på plass: også på riktig plass i takten")],
        "view_label": ("Beat tracker", "Slagsporer"),
        "views": [{"label": label, "note": note, "rows": [
            {"label": text, "keys": [f"{B}solo-beat-model/{part}.{model}.onset_f1", f"{B}solo-beat-model/{part}.{model}.written_f1"],
             "n": (f"{{brass/solo-beat-model/{part}.parts|int}} parts", f"{{brass/solo-beat-model/{part}.parts|int}} stemmer")}
            for text, part in ((("Chamber brass, single parts (URMP)", "Kammerbrass, enkeltstemmer (URMP)"), "urmp"),
                               (("Chorales, single parts (ChoraleBricks)", "Koraler, enkeltstemmer (ChoraleBricks)"), "choralebricks"))]}
            for label, note, model in (
                (("Beat This! small0 (on phones)", "Beat This! small0 (på telefoner)"), ("The small beat tracker the apps carry.", "Den lille slagsporeren appene har med."), "small0"),
                (("Beat This! final0 (larger)", "Beat This! final0 (større)"), ("The larger beat tracker; the notes are the same.", "Den større slagsporeren; tonene er de samme."), "final0"))],
        "caption": ("The solo path end to end, on each part recorded alone. The gap between the two bars of a row is what the beat grid, the "
                    "metre and the bar lines cost.",
                    "Soloveien fra ende til ende, på hver stemme tatt opp alene. Avstanden mellom de to stolpene i en rad er det slagrutenettet, "
                    "taktarten og taktstrekene koster."),
        "source": ("<code>eval/baselines.json</code>, suite solo-beat-model (runs locally, not in CI).",
                   "<code>eval/baselines.json</code>, suiten solo-beat-model (kjøres lokalt, ikke i CI)."),
    },
    "solo-instruments": {
        "title": ("One instrument alone is found well, tuba included, once the app knows which instrument it is",
                  "Ett instrument alene blir funnet godt, også tuba, når appen vet hvilket instrument det er"),
        "holds": [f"brass/solo-instruments/{i}.seat_f1 >= 0.85" for i, _ in INSTRUMENTS] + ["brass/solo-instruments/tuba.today_f1 < 0.1"]
                 + [f"brass/solo-instruments/{i}.sw_f1 >= 0.85" for i, _ in INSTRUMENTS] + ["brass/solo-instruments/tuba.bp_f1 < 0.6"],
        "sub": ("Onset F1 at 100 ms of the written solo line, per instrument, with a fixed cornet range and with the player's own.",
                "Onset-F1 ved 100 ms for den skrevne sololinjen, per instrument, med et fast kornettomfang og med musikerens eget."),
        "axis": F1_AXIS,
        "series": [("Instrument chosen: its own range", "Instrument valgt: dets eget omfang"), ("No instrument chosen: fixed E3–E6", "Ikke valgt instrument: fast E3–E6")],
        "view_label": ("Compare", "Sammenlign"),
        "views": [{"label": ("The written line, with and without the instrument chosen", "Den skrevne linjen, med og uten valgt instrument"),
                   "rows": [{"label": label, "keys": [f"{B}solo-instruments/{i}.seat_f1", f"{B}solo-instruments/{i}.today_f1"],
                             "n": (f"{{m/solo_stems/{i}|int}} recordings", f"{{m/solo_stems/{i}|int}} opptak")} for i, label in INSTRUMENTS]},
                  {"label": ("The two models, each alone", "De to modellene, hver for seg"), "series": ["SwiftF0", "Basic Pitch"],
                   "rows": [{"label": label, "keys": [f"{B}solo-instruments/{i}.sw_f1", f"{B}solo-instruments/{i}.bp_f1"],
                             "n": (f"{{m/solo_stems/{i}|int}} recordings", f"{{m/solo_stems/{i}|int}} opptak")} for i, label in INSTRUMENTS]}],
        "caption": ("Each instrument recorded alone. Pitch and onset only: where the notes land in the bar is the figure before this one. The second "
                    "view is SwiftF0 measured on brass, beside Basic Pitch, the model that confirms its notes.",
                    "Hvert instrument tatt opp alene. Bare tonehøyde og ansats: hvor tonene havner i takten, står i forrige figur. Den andre visningen "
                    "er SwiftF0 målt på messing, ved siden av Basic Pitch, modellen som bekrefter tonene."),
        "source": ("<code>eval/baselines.json</code>, suite solo-instruments (runs in CI).", "<code>eval/baselines.json</code>, suiten solo-instruments (kjøres i CI)."),
    },
    "voices": {
        "title": ("From a quartet recording the top voice is found and the tenor is mostly lost",
                  "Fra et kvartettopptak blir overstemmen funnet, og tenoren for det meste borte"),
        "holds": ["brass/seat-voices/muscriptor-medium.S_f1 > 0.85", "brass/seat-voices/muscriptor-medium.T_f1 < 0.4",
                  "brass/seat-voices/basic-pitch.T_f1 < 0.4", "brass/seat-voices/consensus.T_f1 < 0.4",
                  "p/chorales-transcription/muscriptor-medium.recall_T < 0.55", "p/chorales-transcription/muscriptor-medium.recall_B < 0.55",
                  "p/chorales-transcription/muscriptor-medium.recall_S > 0.8"],
        "sub": ("One player's line picked out of the four-part mix by the range of their instrument, scored against that player's part.",
                "Én musikers linje plukket ut av den firstemte miksen etter omfanget til instrumentet, målt mot musikerens stemme."),
        "axis": F1_AXIS,
        "series": ["MuScriptor medium", "Basic Pitch", ("Notes both found", "Toner begge fant")],
        "view_label": ("Question", "Spørsmål"),
        "views": [{"label": ("One player's line taken out whole", "Én musikers linje hentet ut hel"), "n": CHORALES_N, "rows": [
            {"label": label, "keys": [f"{B}seat-voices/{m}.{v}_f1" for m in ("muscriptor-medium", "basic-pitch", "consensus")]} for v, label in (
                ("S", ("Soprano (trumpet)", "Sopran (trompet)")), ("A", ("Alto (flugelhorn)", "Alt (flygelhorn)")),
                ("T", ("Tenor (baritone)", "Tenor (baryton)")), ("B", ("Bass (tuba)", "Bass (tuba)")))]}] + [
            {"label": label, "n": CHORALES_N, "format": "pct", "series": ["MuScriptor medium", "Basic Pitch"],
                   "axis": ("Share of the voice's notes found (recall)", "Andel av stemmens toner funnet (recall)"),
                   "note": ("A note is credited to a voice when any written note matches it, so these are upper bounds.",
                            "En tone godskrives en stemme når en hvilken som helst skrevet tone treffer den, så dette er øvre grenser."),
                   "rows": [{"label": text, "keys": [f"p/chorales-transcription/{m}.{key}_{v}" for m in ("muscriptor-medium", "basic-pitch")]} for v, text in (
                       ("S", ("Soprano (trumpet)", "Sopran (trompet)")), ("A", ("Alto (flugelhorn)", "Alt (flygelhorn)")),
                       ("T", ("Tenor (baritone)", "Tenor (baryton)")), ("B", ("Bass (tuba)", "Bass (tuba)")))]}
                  for label, key in ((("Notes of each voice found, within 100 ms", "Toner funnet per stemme, innen 100 ms"), "recall100"), (("Within 50 ms", "Innen 50 ms"), "recall"))],
        "caption": ("First view: onset F1 at 100 ms of the line picked out for each player. Other views: the share of each player's notes that appear "
                    "anywhere in the transcription of the quartet (upper bounds: any written note may match). This is why Brasscribe writes only "
                    "the tune and the bass from what it heard in a band, and arranges the parts between them.",
                    "Første visning: onset-F1 ved 100 ms for linjen som er plukket ut for hver musiker. De andre visningene: andelen av hver musikers "
                    "toner som finnes et sted i transkripsjonen av kvartetten (øvre grenser: en hvilken som helst skrevet tone kan treffe). Derfor "
                    "skriver Brasscribe bare melodien og bassen fra det den hørte i et band, og arrangerer stemmene imellom."),
        "source": ("<code>eval/baselines.json</code>, suite seat-voices (runs in CI); the recall views from <code>per-piece.json</code>, computed with the gate's scorer but not gated.",
                   "<code>eval/baselines.json</code>, suiten seat-voices (kjøres i CI); recall-visningene fra <code>per-piece.json</code>, regnet ut med sperrens målekode, men ikke låst."),
    },
    "doubt": {
        "title": ("The ? marks are rarely false alarms, but they catch a third of the wrong notes at best",
                  "?-merkene er sjelden falsk alarm, men de fanger i beste fall en tredel av de gale tonene"),
        "holds": [f"brass/solo-instruments/{i}.q_hit < 0.34" for i, _ in INSTRUMENTS] + [f"brass/solo-instruments/{i}.q_false_alarm < 0.05" for i, _ in INSTRUMENTS],
        "format": "pct",
        "sub": ("Of a solo line's wrong notes, the share that carry a ?; and of its right notes, the share marked anyway. Each is a mean over "
                "the instrument's recordings.",
                "Av de gale tonene i en sololinje: andelen som har et ?; og av de riktige tonene: andelen som likevel er merket. Hver er et "
                "snitt over opptakene av instrumentet."),
        "axis": SHARE_AXIS,
        "series": [("Wrong notes that carry a ?", "Gale toner som har et ?"), ("Right notes marked ? anyway", "Riktige toner som likevel har ?")],
        "views": [{"label": ("ChoraleBricks", "ChoraleBricks"),
                   "note": ("Few notes are wrong to begin with: {m/solo_stems/wrong_notes_trumpet|int} on all the trumpet recordings together and "
                            "{m/solo_stems/wrong_notes_flugelhorn|int} on the flugelhorn's, so a share here can turn on one note. The confidence "
                            "model behind the marks was fitted on these same recordings.",
                            "Få toner er gale i utgangspunktet: {m/solo_stems/wrong_notes_trumpet|int} på alle trompetopptakene til sammen og "
                            "{m/solo_stems/wrong_notes_flugelhorn|int} på flygelhornets, så en andel her kan avhenge av én tone. Sikkerhetsmodellen "
                            "bak merkene er tilpasset de samme opptakene."),
                   "rows": [{"label": label, "keys": [f"{B}solo-instruments/{i}.q_hit", f"{B}solo-instruments/{i}.q_false_alarm"],
                             "n": (f"{{m/solo_stems/{i}|int}} recordings", f"{{m/solo_stems/{i}|int}} opptak")} for i, label in INSTRUMENTS]}],
        "caption": ("Doubt marks on solo lines. These recordings are fitting data for the marks, not a test of them, so a new recording "
                    "should be expected to do no better.",
                    "Tvilsmerker på sololinjer. Disse opptakene er data merkene er tilpasset, ikke en prøve av dem, så et nytt opptak kan "
                    "ikke ventes å gjøre det bedre."),
        "source": ("<code>eval/baselines.json</code>, suite solo-instruments, <code>q_hit</code> and <code>q_false_alarm</code>; counts from "
                   "<code>measured.toml</code>.",
                   "<code>eval/baselines.json</code>, suiten solo-instruments, <code>q_hit</code> og <code>q_false_alarm</code>; antall fra "
                   "<code>measured.toml</code>."),
    },
    "fast-notes": {
        "title": ("Fast figures: about six notes in ten are heard, and fewer survive being written down",
                  "Raske figurer: omtrent seks av ti toner blir hørt, og færre overlever å bli skrevet ned"),
        "holds": ["brass/fast-notes/small0.sw.fig_recall > 0.5", "brass/fast-notes/small0.sw.fig_recall < 0.7",
                  "brass/fast-notes/small0.written.fig_recall < brass/fast-notes/small0.line.fig_recall",
                  "brass/fast-notes/oracle.written.fig_recall < brass/fast-notes/oracle.line.fig_recall",
                  "m/fast_notes/oracle_fig_after > m/fast_notes/oracle_fig_before", "m/fast_notes/oracle_fig_after < 0.5",
                  "m/fast_notes/small0_fig_after > m/fast_notes/small0_fig_before", "m/fast_notes/small0_fig_after < 0.5"],
        "format": "pct",
        "sub": ("Share of the notes in a fast run, repeated-note figure or trill that are still there after each stage of the solo path.",
                "Andel av tonene i et raskt løp, en figur med gjentatte toner eller en trille som fortsatt er der etter hvert steg i soloveien."),
        "axis": ("Share of the figure's notes kept (recall)", "Andel av figurens toner beholdt (recall)"),
        "series": [("Beats given", "Slag gitt"), ("Beats tracked (Beat This! small0)", "Slag sporet (Beat This! small0)")],
        "view_label": ("Show", "Vis"),
        "views": [{"label": ("Stage by stage", "Steg for steg"),
                   "n": ("{m/datasets/fast_notes_frozen_clips|int} clips frozen in the repository: built from samples, dry and with a room; development data",
                         "{m/datasets/fast_notes_frozen_clips|int} klipp som er låst i repositoriet: satt sammen av samplinger, tørt og med rom; utviklingsdata"),
                   "rows": [{"label": label, "keys": [f"{B}fast-notes/oracle.{stage}.fig_recall", f"{B}fast-notes/small0.{stage}.fig_recall"]} for stage, label in (
                       ("sw", ("1. Heard by the pitch tracker (SwiftF0)", "1. Hørt av tonehøydesporeren (SwiftF0)")),
                       ("line", ("2. In the solo line after the vote", "2. I sololinjen etter avstemningen")),
                       ("quantized", ("3. After snapping to the beat grid", "3. Etter plassering på slagrutenettet")),
                       ("written", ("4. Written in the score", "4. Skrevet i notene")))]}] + [
            {"label": label, "series": [("Before the fast-note rules", "Før reglene for raske toner"), ("After", "Etter")],
                   "axis": ("Share or F1, 0 to 100 %", "Andel eller F1, 0 til 100 %"), "n": ("{m/fast_notes/clips|int} clips built from samples; the rules were developed on them", "{m/fast_notes/clips|int} klipp satt sammen av samplinger; reglene er utviklet på dem"),
                   "rows": [{"label": text, "keys": [f"m/fast_notes/{beats}_{key}_before", f"m/fast_notes/{beats}_{key}_after"]} for text, key in (
                       (("Notes of the fast figure written (recall)", "Toner i den raske figuren skrevet (recall)"), "fig"),
                       (("All notes of the clip (F1)", "Alle tonene i klippet (F1)"), "f1"),
                       (("Trills and alternations that keep four fifths of their notes", "Triller og vekslinger som beholder fire femdeler av tonene"), "alt"))]}
                  for label, beats in ((("Before and after, beats given", "Før og etter, slag gitt"), "oracle"), (("Before and after, beats tracked", "Før og etter, slag sporet"), "small0"))],
        "caption": ("Where fast notes are lost. The clips are rendered from real trumpet samples, dry and with a hall, with an exact reference; "
                    "they are development data, not held out. The before-and-after views are the full set of {m/fast_notes/clips|int} clips, so "
                    "their numbers differ a little from the frozen part the gate holds.",
                    "Hvor raske toner går tapt. Klippene er satt sammen av ekte trompetsamplinger, tørt og med romklang, med nøyaktig fasit; "
                    "de er utviklingsdata, ikke holdt utenfor. Visningene før og etter gjelder hele settet på {m/fast_notes/clips|int} klipp, så "
                    "tallene avviker litt fra den låste delen sperren holder."),
        "source": ("<code>eval/baselines.json</code>, suite fast-notes (runs in CI); before and after from <code>docs/brasscribe/plan/fast-notes.md</code>, section 7.2, via <code>measured.toml</code>.",
                   "<code>eval/baselines.json</code>, suiten fast-notes (kjøres i CI); før og etter fra <code>docs/brasscribe/plan/fast-notes.md</code>, avsnitt 7.2, via <code>measured.toml</code>."),
    },
    "agreement": {
        "title": ("A note heard by SwiftF0 and one more model is almost always right; without that pairing it is a coin toss or worse",
                  "En tone hørt av SwiftF0 og én modell til er nesten alltid riktig; uten den kombinasjonen er det myntkast eller verre"),
        "holds": ["brass/solo-vote/precision.bp+mus+sw > 0.9", "brass/solo-vote/precision.mus+sw > 0.9", "brass/solo-vote/precision.bp+sw > 0.85",
                  "brass/solo-vote/precision.sw < 0.6", "brass/solo-vote/precision.bp+mus < 0.5"],
        "format": "pct",
        "sub": ("Share of the notes that are right, by which of the three models found them, on solo lines separated from a mix.",
                "Andel av tonene som er riktige, etter hvilke av de tre modellene som fant dem, på sololinjer separert fra en miks."),
        "axis": ("Precision: share of the notes in the group that are right", "Presisjon: andel av tonene i gruppen som er riktige"),
        "series": [("Precision", "Presisjon")],
        "views": [{"label": ("Separated solo lines", "Separerte sololinjer"), "rows": [
            {"label": label, "keys": [f"{B}solo-vote/precision.{key}"], "n": (f"{{m/solo_vote/{n}|int}} notes", f"{{m/solo_vote/{n}|int}} toner")} for key, n, label in (
                ("mus+sw", "n_mus_sw", ("SwiftF0 and MuScriptor", "SwiftF0 og MuScriptor")),
                ("bp+mus+sw", "n_all", ("All three", "Alle tre")),
                ("bp+sw", "n_bp_sw", ("SwiftF0 and Basic Pitch", "SwiftF0 og Basic Pitch")),
                ("sw", "n_sw", ("SwiftF0 alone", "SwiftF0 alene")),
                ("bp+mus", "n_bp_mus", ("MuScriptor and Basic Pitch, not SwiftF0", "MuScriptor og Basic Pitch, ikke SwiftF0")))]}],
        "caption": ("Agreement between models is what the confidence of a note is built on. The trumpet lines were separated with Mega-53 from "
                    "the ten chorale mixes and two Slakh songs.",
                    "Enighet mellom modellene er det sikkerheten til en tone bygger på. Trompetlinjene ble separert med Mega-53 fra de ti "
                    "koralmiksene og to Slakh-låter."),
        "source": ("<code>eval/baselines.json</code>, suite solo-vote (runs locally); note counts from "
                   "<code>docs/shared/research/10-benchmark-results.md</code> via <code>measured.toml</code>.",
                   "<code>eval/baselines.json</code>, suiten solo-vote (kjøres lokalt); antall toner fra "
                   "<code>docs/shared/research/10-benchmark-results.md</code> via <code>measured.toml</code>."),
    },
    "models": {
        "title": ("The larger model was not better, and telling the model the instruments are brass made it worse",
                  "Den større modellen var ikke bedre, og å fortelle modellen at instrumentene er messing gjorde den dårligere"),
        "holds": ["brass/chorales-transcription/muscriptor-large.onset_f1 < brass/chorales-transcription/muscriptor-medium.onset_f1",
                  "brass/chorales-transcription/muscriptor-medium-brass.onset_f1 < brass/chorales-transcription/muscriptor-medium.onset_f1",
                  "brass/chorales-transcription/muscriptor-large-brass.onset_f1 < brass/chorales-transcription/muscriptor-large.onset_f1"],
        "spread": False,
        "sub": ("Every model and setting that was run on the ten brass quartets, at the strict 50 ms tolerance.",
                "Alle modeller og innstillinger som ble kjørt på de ti brasskvartettene, med den strenge toleransen på 50 ms."),
        "axis": F1_AXIS,
        "series": [("Onset within 50 ms", "Ansats innen 50 ms"), ("Onset and note end both right", "Ansats og toneslutt begge riktige")],
        "views": [{"label": CHORALES, "n": CHORALES_N, "rows": [
            {"label": label, "keys": [f"{B}chorales-transcription/{m}.onset_f1", f"{B}chorales-transcription/{m}.onoff_f1"]} for m, label in (
                ("muscriptor-medium", ("MuScriptor medium (used)", "MuScriptor medium (brukes)")),
                ("basic-pitch-retuned", ("Basic Pitch, recording retuned to A = 440 (used)", "Basic Pitch, opptaket stemt om til A = 440 (brukes)")),
                ("basic-pitch", ("Basic Pitch, as recorded", "Basic Pitch, slik det ble tatt opp")),
                ("muscriptor-large", ("MuScriptor large", "MuScriptor large")),
                ("muscriptor-medium-brass", ("MuScriptor medium, told it is brass", "MuScriptor medium, fortalt at det er messing")),
                ("muscriptor-large-brass", ("MuScriptor large, told it is brass", "MuScriptor large, fortalt at det er messing")))]}],
        "caption": ("Model comparison on the same recordings, as means over the pieces.",
                    "Modellsammenligning på de samme opptakene, som snitt over stykkene."),
        "source": ("<code>eval/baselines.json</code>, suite chorales-transcription (runs in CI).", "<code>eval/baselines.json</code>, suiten chorales-transcription (kjøres i CI)."),
    },
    "inner-parts": {
        "title": ("Arranged inner parts match the composer's about four notes in five from the right harmony, and about half from a recording",
                  "Arrangerte mellomstemmer treffer komponistens omtrent fire av fem toner fra riktig harmoni, og omtrent halvparten fra et opptak"),
        "holds": ["brass/arrange/quartet.alto_recall_pc > 0.75", "brass/arrange/quartet.tenor_recall_pc > 0.75",
                  "brass/quartet-audio/mus.alto_recall_pc < 0.6", "brass/quartet-audio/mus.tenor_recall_pc < 0.6",
                  "brass/quartet-audio/mus.tenor_recall_pc > 0.4"],
        "format": "pct",
        "sub": ("Share of the chorale's own alto and tenor notes that the quartet arranger also chose (same note name, any octave).",
                "Andel av koralens egne alt- og tenortoner som kvartettarrangøren også valgte (samme tonenavn, vilkårlig oktav)."),
        "axis": ("Share of the composer's notes matched (recall)", "Andel av komponistens toner truffet (recall)"),
        "series": [("From the score's harmony", "Fra partiturets harmoni"), ("From the recording (MuScriptor)", "Fra opptaket (MuScriptor)"),
                   ("From the recording (Basic Pitch only)", "Fra opptaket (bare Basic Pitch)")],
        "views": [{"label": CHORALES, "n": CHORALES_N, "rows": [
            {"label": label, "keys": [f"{B}arrange/quartet.{v}_recall_pc", f"{B}quartet-audio/mus.{v}_recall_pc", f"{B}quartet-audio/bp.{v}_recall_pc"]}
            for v, label in (("alto", ("Alto", "Alt")), ("tenor", ("Tenor", "Tenor")))]}],
        "caption": ("The quartet arranger sees a melody, a bass and the harmony, and writes the two parts between. Matching the composer is a "
                    "strict test: other inner parts can be equally good music. The two kinds of row are matched differently: from the score's harmony "
                    "note by note at the same onset; from a recording by the note name sounding 50 ms after each attack.",
                    "Kvartettarrangøren ser en melodi, en bass og harmonien, og skriver de to stemmene imellom. Å treffe komponisten er en streng "
                    "prøve: andre mellomstemmer kan være like god musikk. De to slagene rader sammenlignes ulikt: fra partiturets harmoni tone for tone "
                    "på samme ansats; fra et opptak etter tonenavnet som klinger 50 ms etter hver ansats."),
        "source": ("<code>eval/baselines.json</code>, suites arrange and quartet-audio (the chorale parts run in CI).",
                   "<code>eval/baselines.json</code>, suitene arrange og quartet-audio (koraldelene kjøres i CI)."),
    },
    "speed": {
        "title": ("The three small models take under a second per minute of music; the two separators take "
                  "{c/bs-roformer-sw/coreml-fp16-ALL.s_per_min|sec} and {c/mega53/coreml-fp16-ALL.s_per_min|sec}, and Mega-53 "
                  "{c/mega53/coreml-fp16-ALL.peak_gb|gb} of memory",
                  "De tre små modellene bruker under ett sekund per minutt musikk; de to separatorene bruker "
                  "{c/bs-roformer-sw/coreml-fp16-ALL.s_per_min|sec} og {c/mega53/coreml-fp16-ALL.s_per_min|sec}, og Mega-53 "
                  "{c/mega53/coreml-fp16-ALL.peak_gb|gb} minne"),
        "holds": ["c/swift-f0/coreml-fp32-ALL.s_per_min < 1", "c/basic-pitch/coreml-b1-fp32-ALL.s_per_min < 1", "c/beat-this/small0/coreml-fp16-ALL.s_per_min < 1",
                  "c/bs-roformer-sw/coreml-fp16-ALL.s_per_min > 1", "c/mega53/coreml-fp16-ALL.s_per_min > 1"],
        "sub": ("Each model alone, converted for Apple devices and in its reference framework, on one Apple M5 Pro laptop with 48 GB. "
                "No phone has been timed.",
                "Hver modell alene, konvertert for Apple-enheter og i referanserammeverket, på én bærbar Apple M5 Pro med 48 GB. "
                "Ingen telefon er målt."),
        "series": [("Converted (best conversion that passes)", "Konvertert (beste konvertering som er godkjent)"),
                   ("Reference framework on the processor", "Referanserammeverket på prosessoren")],
        "view_label": ("Measure", "Mål"),
        "views": [{"label": label, "format": how, "scale": "log", "log": span, "axis": axis, "note": note,
                   "n": ("30 s of audio (Beat This!: 60 s), median of 1 to 5 runs", "30 s lyd (Beat This!: 60 s), median av 1 til 5 kjøringer"),
                   "rows": [{"label": name, "keys": [f"c/{model}/{converted}.{field}", f"c/{model}/{reference}.{field}"]} for name, model, converted, reference in (
                       (("SwiftF0 (pitch of one line)", "SwiftF0 (tonehøyden til én linje)"), "swift-f0", "coreml-fp32-ALL", "ort-cpu-upstream"),
                       (("Basic Pitch (notes)", "Basic Pitch (toner)"), "basic-pitch", "coreml-b1-fp32-ALL", "tf-savedmodel"),
                       (("Beat This! small0 (beats)", "Beat This! small0 (slag)"), "beat-this", "small0/coreml-fp16-ALL", "small0/torch-cpu"),
                       (("BS-RoFormer SW (separation, 6 stems)", "BS-RoFormer SW (separasjon, 6 spor)"), "bs-roformer-sw", "coreml-fp16-ALL", "torch-cpu"),
                       (("Mega-53 (separation, 53 stems)", "Mega-53 (separasjon, 53 spor)"), "mega53", "coreml-fp16-ALL", "torch-cpu"),
                       (("MuScriptor medium (notes), on the processor only", "MuScriptor medium (toner), bare på prosessoren"), "muscriptor", "onnx-ort-cpu", "torch-cpu"))]}
                  for label, how, field, span, axis, note in (
                      (("Time", "Tid"), "sec", "s_per_min", (-2, 3),
                       ("Seconds of computing per minute of audio, each step ten times the last (60 s = as long as the music)",
                        "Sekunder regnetid per minutt lyd, hvert steg ti ganger det forrige (60 s = like lenge som musikken)"),
                       ("Lower is faster. The scale is logarithmic: the models differ by a factor of thousands.",
                        "Lavere er raskere. Skalaen er logaritmisk: modellene skiller seg med en faktor på flere tusen.")),
                      (("Memory", "Minne"), "gb", "peak_gb", (-1, 2),
                       ("Peak memory of the process in GB, each step ten times the last", "Høyeste minnebruk for prosessen i GB, hvert steg ti ganger det forrige"),
                       ("The whole process, with the framework loaded. Logarithmic scale.", "Hele prosessen, med rammeverket lastet. Logaritmisk skala.")))],
        "caption": ("Speed and memory per model. MuScriptor's only passing conversion runs on the processor and is slower than the original; "
                    "the engine runs the original on the graphics processor, which the next figure times.",
                    "Fart og minne per modell. Den eneste godkjente konverteringen av MuScriptor kjører på prosessoren og er tregere enn "
                    "originalen; motoren kjører originalen på grafikkprosessoren, som neste figur måler."),
        "source": ("<code>convert/reports/*.json</code> (made by the scripts in <code>convert/</code>; <code>python3 convert/summarize.py</code> prints them).",
                   "<code>convert/reports/*.json</code> (laget av skriptene i <code>convert/</code>; <code>python3 convert/summarize.py</code> skriver dem ut)."),
    },
    "conversions": {
        "title": ("Half precision on the Neural Engine broke two small models: SwiftF0 fell to {c/swift-f0/coreml-fp16-CPU_AND_NE.parity|f2} "
                  "and Basic Pitch to {c/basic-pitch/coreml-b1-fp16-CPU_AND_NE.parity|f2}",
                  "Halv presisjon på Neural Engine ødela to små modeller: SwiftF0 falt til {c/swift-f0/coreml-fp16-CPU_AND_NE.parity|f2} "
                  "og Basic Pitch til {c/basic-pitch/coreml-b1-fp16-CPU_AND_NE.parity|f2}"),
        "holds": ["c/swift-f0/coreml-fp16-CPU_AND_NE.parity < c/swift-f0/threshold_f1", "c/basic-pitch/coreml-b1-fp16-CPU_AND_NE.parity < c/swift-f0/threshold_f1",
                  "c/swift-f0/coreml-fp32-ALL.parity >= c/swift-f0/threshold_f1", "c/swift-f0/coreml-split-CPU_AND_NE.parity >= c/swift-f0/threshold_f1",
                  "c/basic-pitch/coreml-b1-fp32-ALL.parity >= c/swift-f0/threshold_f1", "c/beat-this/small0/coreml-fp16-ALL.parity >= c/swift-f0/threshold_f1",
                  "c/bs-roformer-sw/coreml-fp16-ALL.parity >= c/swift-f0/threshold_f1", "c/mega53/coreml-fp16-ALL.parity >= c/swift-f0/threshold_f1"],
        "format": "f3", "spread": False,
        "sub": ("How closely a converted model gives the original's result: F1 of its notes (or beats) against the original's own output.",
                "Hvor nær en konvertert modell kommer originalens resultat: F1 for tonene (eller slagene) mot originalens eget resultat."),
        "axis": ("F1 against the original model's output, 0 to 1", "F1 mot originalmodellens resultat, 0 til 1"),
        "mark": ("c/swift-f0/threshold_f1", ("must reach {c/swift-f0/threshold_f1|f2}", "må nå {c/swift-f0/threshold_f1|f2}")),
        "series": [("Parity with the original", "Samsvar med originalen")],
        "views": [{"label": ("Conversions", "Konverteringer"),
                   "n": ("the 10 chorale and 8 chamber mixes and their single parts; separators on four 30-second excerpts",
                         "de 10 koral- og 8 kammermiksene og enkeltstemmene deres; separatorene på fire utdrag på 30 sekunder"),
                   "rows": [{"label": label, "keys": [f"c/{key}.parity"]} for label, key in (
                       (("SwiftF0, full precision", "SwiftF0, full presisjon"), "swift-f0/coreml-fp32-ALL"),
                       (("SwiftF0, half precision on the Neural Engine: fails", "SwiftF0, halv presisjon på Neural Engine: underkjent"), "swift-f0/coreml-fp16-CPU_AND_NE"),
                       (("SwiftF0 split: only its middle on the Neural Engine", "SwiftF0 delt: bare midtdelen på Neural Engine"), "swift-f0/coreml-split-CPU_AND_NE"),
                       (("Basic Pitch, full precision", "Basic Pitch, full presisjon"), "basic-pitch/coreml-b1-fp32-ALL"),
                       (("Basic Pitch, half precision: fails", "Basic Pitch, halv presisjon: underkjent"), "basic-pitch/coreml-b1-fp16-CPU_AND_NE"),
                       (("Beat This! small0, half precision", "Beat This! small0, halv presisjon"), "beat-this/small0/coreml-fp16-ALL"),
                       (("BS-RoFormer SW, half precision", "BS-RoFormer SW, halv presisjon"), "bs-roformer-sw/coreml-fp16-ALL"),
                       (("Mega-53, half precision", "Mega-53, halv presisjon"), "mega53/coreml-fp16-ALL"),
                       (("MuScriptor, ONNX", "MuScriptor, ONNX"), "muscriptor/onnx-ort-cpu"),
                       (("MuScriptor, Core ML half precision: fails a stricter test", "MuScriptor, Core ML halv presisjon: underkjent i en strengere prøve"), "muscriptor/coreml-fp16-ALL"))]}],
        "caption": ("Conversions to Core ML and ONNX, against the gate. MuScriptor writes its notes one token after another, so it must also "
                    "produce the very same tokens as the original; its Core ML form does not, although its notes nearly match.",
                    "Konverteringer til Core ML og ONNX, mot sperren. MuScriptor skriver tonene symbol for symbol, så den må også gi nøyaktig de "
                    "samme symbolene som originalen; Core ML-utgaven gjør ikke det, selv om tonene nesten stemmer."),
        "source": ("<code>convert/reports/*.json</code>, <code>parity</code> (the lower score where a report has two).",
                   "<code>convert/reports/*.json</code>, <code>parity</code> (den laveste verdien der en rapport har to)."),
    },
    "solo-stages": {
        "title": ("A 30-second solo on the computer: MuScriptor is {m/solo_stages/muscriptor|sec} of the model time, the pitch tracker {m/solo_stages/swift_f0|sec}",
                  "En solo på 30 sekunder på datamaskinen: MuScriptor står for {m/solo_stages/muscriptor|sec} av modelltiden, tonehøydesporeren {m/solo_stages/swift_f0|sec}"),
        "holds": ["m/solo_stages/muscriptor > m/solo_stages/basic_pitch", "m/solo_stages/muscriptor > m/solo_stages/beats", "m/solo_stages/swift_f0 < 1"],
        "format": "sec", "max": "auto",
        "sub": ("Seconds each model call took in one solo job, as the engine runs them, each starting its own process.",
                "Sekunder hvert modellkall tok i én solojobb, slik motoren kjører dem, hvert i sin egen prosess."),
        "axis": ("Seconds for {m/jobs/solo_audio_s|int} s of audio", "Sekunder for {m/jobs/solo_audio_s|int} s lyd"),
        "series": [("Seconds", "Sekunder")],
        "views": [{"label": ("Solo job", "Solojobb"), "n": ("one job on one M-series Mac", "én jobb på én Mac med M-prosessor"),
                   "rows": [{"label": label, "keys": [f"m/solo_stages/{key}"]} for label, key in (
                       (("Beats (Beat This!)", "Slag (Beat This!)"), "beats"), (("Pitch of the line (SwiftF0)", "Linjens tonehøyde (SwiftF0)"), "swift_f0"),
                       (("Notes (Basic Pitch)", "Toner (Basic Pitch)"), "basic_pitch"), (("Notes (MuScriptor, graphics processor)", "Toner (MuScriptor, grafikkprosessor)"), "muscriptor"),
                       (("Pitch contour for note ends", "Tonehøydekurve for toneslutt"), "contour"))]}],
        "caption": ("One job, one machine: a single measurement, not a benchmark. The whole job took longer (the text below): arranging and "
                    "exporting come on top.",
                    "Én jobb, én maskin: en enkeltmåling, ikke en målesuite. Hele jobben tok lengre tid (teksten under): arrangering og eksport "
                    "kommer i tillegg."),
        "source": ("<code>docs/shared/research/13-performance-audit.md</code> via <code>measured.toml</code>.",
                   "<code>docs/shared/research/13-performance-audit.md</code> via <code>measured.toml</code>."),
    },
    "consensus": {
        "title": ("Keeping only what two models agree on does not find more notes, and on a full band it finds fewer",
                  "Å beholde bare det to modeller er enige om, finner ikke flere toner, og på et fullt band finner det færre"),
        "holds": ["brass/consensus-slakh/t0.8.onset100_f1 < brass/slakh-transcription/pipeB-sw-muscriptor.onset100_f1",
                  "brass/consensus-chorales/best.onset100_f1 < 0.78", "brass/consensus-urmp/t0.8.onset100_f1 < 0.9"],
        "sub": ("The best single route against the combined vote of the models, on each kind of recording. Onset F1 at 100 ms.",
                "Den beste enkeltveien mot modellenes samlede avstemning, for hvert slags opptak. Onset-F1 ved 100 ms."),
        "axis": F1_AXIS,
        "series": [("Best single route", "Beste enkeltvei"), ("Vote between the models", "Avstemning mellom modellene")],
        "views": [{"label": RECORDINGS, "rows": [
            {"label": CHORALES, "keys": [B + "chorales-transcription/muscriptor-medium.onset100_f1", B + "consensus-chorales/best.onset100_f1"], "n": CHORALES_N},
            {"label": URMP, "keys": [B + "urmp-transcription/muscriptor-medium.onset100_f1", B + "consensus-urmp/t0.8.onset100_f1"], "n": URMP_N},
            {"label": ("Trumpet over a band (separated first)", "Trompet over et band (separert først)"),
             "keys": [B + "slakh-transcription/pipeB-sw-muscriptor.onset100_f1", B + "consensus-slakh/t0.8.onset100_f1"],
             "n": ("{m/datasets/slakh_trumpet_songs|int} songs", "{m/datasets/slakh_trumpet_songs|int} låter")}]}],
        "caption": ("A negative result. The vote is therefore used to say how sure a note is, not to decide which notes are written.",
                    "Et negativt resultat. Avstemningen brukes derfor til å si hvor sikker en tone er, ikke til å avgjøre hvilke toner som skrives."),
        "source": ("<code>eval/baselines.json</code>, suites consensus-chorales, consensus-urmp, consensus-slakh and the transcription suites.",
                   "<code>eval/baselines.json</code>, suitene consensus-chorales, consensus-urmp, consensus-slakh og transkripsjonssuitene."),
    },
    "melody": {
        "title": ("For the melody, the top line of MuScriptor's notes beats the top line of everything both models found, on every set",
                  "For melodien slår den øverste linjen av tonene til MuScriptor den øverste linjen av alt begge modellene fant, i alle settene"),
        "holds": [f"brass/melody/muscriptor_supported.{k} > brass/melody/union.{k}" for k in ("slakh", "urmp", "chorales")],
        "sub": ("Three ways to choose which notes the melody may be drawn from, scored on the melody alone. Onset F1 at 100 ms.",
                "Tre måter å velge hvilke toner melodien kan hentes fra, målt på melodien alene. Onset-F1 ved 100 ms."),
        "axis": F1_AXIS,
        "series": [("Trumpet over a band (Slakh)", "Trompet over et band (Slakh)"), URMP, CHORALES],
        "views": [{"label": ("Melody", "Melodi"),
                   "n": ("{m/datasets/slakh_trumpet_songs|int} songs, {p/urmp-transcription/pieces|int} chamber pieces, {p/chorales-transcription/pieces|int} chorales",
                         "{m/datasets/slakh_trumpet_songs|int} låter, {p/urmp-transcription/pieces|int} kammerstykker, {p/chorales-transcription/pieces|int} koraler"),
                   "rows": [{"label": label, "keys": [f"{B}melody/{key}.{k}" for k in ("slakh", "urmp", "chorales")]} for label, key in (
                       (("Notes MuScriptor found (used)", "Toner MuScriptor fant (brukes)"), "muscriptor_supported"),
                       (("Only notes both models found", "Bare toner begge modellene fant"), "agreement"),
                       (("Everything either model found", "Alt en av modellene fant"), "union"))]}],
        "caption": ("Choosing the melody. Basic Pitch hears overtones as high notes, and they land above the tune when everything is kept.",
                    "Valg av melodi. Basic Pitch hører overtoner som høye toner, og de havner over melodien når alt beholdes."),
        "source": ("<code>eval/baselines.json</code>, suite melody (runs locally).", "<code>eval/baselines.json</code>, suiten melody (kjøres lokalt)."),
    },
    "solo-trackers": {
        "title": ("On a solo line lifted out of a mix, the pitch tracker leads and MuScriptor, the best model on mixes, trails",
                  "På en sololinje løftet ut av en miks leder tonehøydesporeren, og MuScriptor, den beste modellen på mikser, ligger bak"),
        "holds": ["brass/solo-vote/sw.onset100_f1 > brass/solo-vote/mus.onset100_f1", "brass/solo-vote/sw.onset100_f1 > brass/solo-vote/bp.onset100_f1",
                  "brass/solo-vote/sw.onset100_f1 >= brass/solo-vote/vote2.onset100_f1"],
        "sub": ("Each model alone on trumpet lines separated with Mega-53, and the line kept when two models agree. Onset F1 at 100 ms.",
                "Hver modell alene på trompetlinjer separert med Mega-53, og linjen som beholdes når to modeller er enige. Onset-F1 ved 100 ms."),
        "axis": F1_AXIS,
        "series": [("Onset F1", "Onset-F1")],
        "views": [{"label": ("Separated solo lines", "Separerte sololinjer"),
                   "n": ("the solo lines of {p/chorales-transcription/pieces|int} chorales and {m/datasets/slakh_trumpet_songs|int} songs",
                         "sololinjene fra {p/chorales-transcription/pieces|int} koraler og {m/datasets/slakh_trumpet_songs|int} låter"),
                   "rows": [{"label": label, "keys": [f"{B}solo-vote/{key}.onset100_f1"]} for label, key in (
                       (("SwiftF0", "SwiftF0"), "sw"), (("Notes at least two models found", "Toner minst to modeller fant"), "vote2"),
                       (("MuScriptor", "MuScriptor"), "mus"), (("Basic Pitch", "Basic Pitch"), "bp"))]}],
        "caption": ("Why a solo is built on the pitch tracker. The two-model line has precision {brass/solo-vote/vote2.onset100_p} and recall "
                    "{brass/solo-vote/vote2.onset100_r}.",
                    "Hvorfor en solo bygges på tonehøydesporeren. Linjen fra to modeller har presisjon {brass/solo-vote/vote2.onset100_p} og recall "
                    "{brass/solo-vote/vote2.onset100_r}."),
        "source": ("<code>eval/baselines.json</code>, suite solo-vote (runs locally).", "<code>eval/baselines.json</code>, suiten solo-vote (kjøres lokalt)."),
    },
    "durations": {
        "title": ("Written note lengths: right for about nine in ten chorale notes and about two in three in chamber music, whichever rule is used",
                  "Skrevne tonelengder: riktige for omtrent ni av ti koraltoner og omtrent to av tre i kammermusikk, uansett regel"),
        "holds": ["brass/durations/chorales.audio > 0.85", "brass/durations/urmp.audio < 0.7", "brass/durations/urmp.audio > 0.6",
                  "brass/durations/urmp.audio > brass/durations/urmp.performed", "brass/durations/chorales.audio > brass/durations/chorales.performed"],
        "format": "pct",
        "sub": ("Share of notes whose written length equals the score's, with the score's beats, under three rules for how long a note is.",
                "Andel toner der skrevet lengde er lik partiturets, med partiturets slag, under tre regler for hvor lang en tone er."),
        "axis": ("Share of notes with the score's written length", "Andel toner med partiturets skrevne lengde"),
        "series": [URMP, CHORALES],
        "views": [{"label": ("Note ends from the annotation", "Toneslutt fra annotasjonen"),
                   "n": ("{p/urmp-transcription/pieces|int} chamber pieces, {p/chorales-transcription/pieces|int} chorales",
                         "{p/urmp-transcription/pieces|int} kammerstykker, {p/chorales-transcription/pieces|int} koraler"),
                   "rows": [{"label": label, "keys": [f"{B}durations/urmp.{key}", f"{B}durations/chorales.{key}"]} for label, key in (
                       (("As long as it was played", "Så lang som den ble spilt"), "performed"),
                       (("Held to the next note when the gap is small", "Holdt til neste tone når avstanden er liten"), "fill8"),
                       (("From where the pitch leaves the note (used)", "Fra der tonehøyden forlater tonen (brukes)"), "audio"))]}],
        "caption": ("Three rules for written length. The rule in use gains two or three points. In chamber music the score often writes a short "
                    "note and a rest where the player holds on, and no rule here recovers that.",
                    "Tre regler for skrevet lengde. Regelen som brukes, vinner to–tre prosentpoeng. I kammermusikk skriver partituret ofte en kort "
                    "tone og en pause der musikeren holder ut, og ingen regel her henter det inn."),
        "source": ("<code>eval/baselines.json</code>, suite durations (the chorale part runs in CI).", "<code>eval/baselines.json</code>, suiten durations (koraldelen kjøres i CI)."),
    },
    "brass-pipeline": {
        "title": ("The Brasscribe pipeline", "Brasscribes arbeidsflyt"),
        "desc": ("Stages from recording to score. Learned models (outlined in the brand colour) only listen: they separate layers, find notes and "
                 "find beats. Everything after the vote is music rules that always give the same result. Dashed stages are where the musician decides.",
                 "Stegene fra opptak til noter. Lærte modeller (med ramme i merkefargen) bare lytter: de skiller lag, finner toner og finner slag. "
                 "Alt etter avstemningen er musikkregler som alltid gir samme resultat. Stiplede steg er der musikeren bestemmer."),
        "legend": [("Learned model", "Lært modell"), ("Music rule (same input, same output)", "Musikkregel (samme inn, samme ut)"), ("The musician decides", "Musikeren bestemmer")],
        "caption": ("From recording to score. The two columns run side by side, notes on the left and the beat grid on the right, and meet where "
                    "the notes are put on the grid.",
                    "Fra opptak til noter. De to kolonnene går side om side, toner til venstre og slagrutenettet til høyre, og møtes der tonene "
                    "settes på rutenettet."),
        "rows": [
            [("rule", ("Recording", "Opptak"), (["a file, the microphone, or sound on the computer"], ["en fil, mikrofonen eller lyd på datamaskinen"]))],
            [("human", ("What is this?", "Hva er dette?"), (["solo · brass band · soloist with orchestra · pop/rock"], ["solo · brassband · solist med orkester · pop/rock"]))],
            [("model", ("Separate", "Skill lagene"), (["a song or an orchestra only:", "BS-RoFormer SW, Mega-53"], ["bare låt eller orkester:", "BS-RoFormer SW, Mega-53"])),
             ("model", ("Beats", "Slag"), (["Beat This!", "on the whole mix"], ["Beat This!", "på hele miksen"]))],
            [("model", ("Notes per layer", "Toner per lag"), (["MuScriptor, Basic Pitch", "and SwiftF0"], ["MuScriptor, Basic Pitch", "og SwiftF0"])),
             ("rule", ("Metrical level", "Metrisk nivå"), (["the beat a player", "would count"], ["slaget en musiker", "ville telt"]))],
            [("rule", ("Vote and confidence", "Avstemning og sikkerhet"), (["agreement between models", "→ which notes get a ?"], ["enighet mellom modellene", "→ hvilke toner som får ?"])),
             ("rule", ("Bar lines, free time", "Taktstreker, fri rytme"), (["downbeat cleanup,", "ad lib. passages"], ["opprydding i enere,", "ad lib.-partier"]))],
            [("rule", ("Put the notes on the grid", "Sett tonene på rutenettet"), (["quantization, 24 ticks per beat"], ["kvantisering, 24 trinn per slag"]))],
            [("rule", ("Durations", "Lengder"), (["note ends from the pitch contour; staccato"], ["toneslutt fra tonehøydekurven; staccato"]))],
            [("rule", ("Spelling and key", "Tonenavn og toneart"), (["ps13 at concert pitch · Krumhansl–Kessler"], ["ps13 i klingende tonehøyde · Krumhansl–Kessler"]))],
            [("rule", ("Harmony", "Harmoni"), (["the chord tones of each beat"], ["akkordtonene i hvert slag"]))],
            [("rule", ("Arrange", "Arranger"), (["full band · small band · quartet"], ["fullt band · lite band · kvartett"]))],
            [("rule", ("Difficulty", "Vanskelighetsgrad"), (["as played · standard · easier"], ["som spilt · standard · enklere"]))],
            [("human", ("Check the notes marked ?", "Sjekk tonene merket ?"), (["grouped review, your part first"], ["gruppevis gjennomgang, din stemme først"]))],
            [("rule", ("Share or print", "Del eller skriv ut"), (["MusicXML · PDF · MIDI · MP3 · talking score"], ["MusicXML · PDF · MIDI · MP3 · talende noter"]))],
        ],
    },
}
