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
        "sub": ("The correct notes are given to the quantizer, so only the beat grid differs. A dot is one piece: with tracked beats a "
                "piece is either nearly all right or nearly all wrong.",
                "Kvantiseringen får de riktige tonene, så bare slagrutenettet er ulikt. En prikk er ett stykke: med sporede slag er et "
                "stykke enten nesten helt riktig eller nesten helt feil."),
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
                  "brass/solo-beat-model/urmp.small0.written_f1 > 0.2", "brass/solo-beat-model/choralebricks.small0.written_f1 > 0.2"],
        "sub": ("The whole solo path as the phone runs it, scored against the player's own part. The two series are two sizes of the beat "
                "tracker.",
                "Hele soloveien slik telefonen kjører den, målt mot musikerens egen stemme. De to seriene er to størrelser av slagsporeren."),
        "axis": ("F1 or share, 0 to 1", "F1 eller andel, 0 til 1"),
        "series": [("Beat This! small0 (the one on phones)", "Beat This! small0 (den på telefoner)"), ("Beat This! final0 (larger)", "Beat This! final0 (større)")],
        "view_label": RECORDINGS,
        "views": [{"label": label, "note": note, "n": n, "rows": [
            {"label": text, "keys": [f"{B}solo-beat-model/{part}.small0.{key}", f"{B}solo-beat-model/{part}.final0.{key}"]} for text, key in (
                (("Notes heard: pitch and onset within 100 ms (F1)", "Toner hørt: tonehøyde og ansats innen 100 ms (F1)"), "onset_f1"),
                (("Notes written right: also in the right place in the bar (F1)", "Toner skrevet riktig: også på riktig plass i takten (F1)"), "written_f1"),
                (("Of the notes heard, share in the right place in the bar", "Av de hørte tonene: andel på riktig plass i takten"), "bar_position_acc"),
                (("Parts with the right bar length", "Stemmer med riktig taktlengde"), "meter_match"))]}
            for label, note, n, part in (
                (("Chamber brass, single parts", "Kammerbrass, enkeltstemmer"), ("Every single part of the URMP pieces, each from its own recording.", "Hver enkeltstemme i URMP-stykkene, fra sitt eget opptak."),
                 ("{brass/solo-beat-model/urmp.parts|int} parts", "{brass/solo-beat-model/urmp.parts|int} stemmer"), "urmp"),
                (("Chorales, single parts", "Koraler, enkeltstemmer"), ("Single brass parts of the ChoraleBricks chorales.", "Enkeltstemmer for messing fra ChoraleBricks-koralene."),
                 ("{brass/solo-beat-model/choralebricks.parts|int} parts", "{brass/solo-beat-model/choralebricks.parts|int} stemmer"), "choralebricks"))],
        "caption": ("The solo path end to end. The four rows measure different things on the same 0 to 1 scale: read each row across its "
                    "two series, and the first two rows against each other.",
                    "Soloveien fra ende til ende. De fire radene måler ulike ting på samme skala fra 0 til 1: les hver rad på tvers av de to "
                    "seriene, og de to første radene mot hverandre."),
        "source": ("<code>eval/baselines.json</code>, suite solo-beat-model (runs locally, not in CI).",
                   "<code>eval/baselines.json</code>, suiten solo-beat-model (kjøres lokalt, ikke i CI)."),
    },
    "solo-instruments": {
        "title": ("One instrument alone is found well, tuba included, once the app knows which instrument it is",
                  "Ett instrument alene blir funnet godt, også tuba, når appen vet hvilket instrument det er"),
        "holds": [f"brass/solo-instruments/{i}.seat_f1 >= 0.85" for i, _ in INSTRUMENTS] + ["brass/solo-instruments/tuba.today_f1 < 0.1"],
        "sub": ("Onset F1 at 100 ms of the written solo line, per instrument, with a fixed cornet range and with the player's own.",
                "Onset-F1 ved 100 ms for den skrevne sololinjen, per instrument, med et fast kornettomfang og med musikerens eget."),
        "axis": F1_AXIS,
        "series": [("Instrument chosen: its own range", "Instrument valgt: dets eget omfang"), ("No instrument chosen: fixed E3–E6", "Ikke valgt instrument: fast E3–E6")],
        "views": [{"label": ("ChoraleBricks", "ChoraleBricks"), "n": STEMS,
                   "rows": [{"label": label, "keys": [f"{B}solo-instruments/{i}.seat_f1", f"{B}solo-instruments/{i}.today_f1"]} for i, label in INSTRUMENTS]}],
        "caption": ("Each instrument recorded alone in a dry room. Pitch and onset only: where the notes land in the bar is the figure above.",
                    "Hvert instrument tatt opp alene i et tørt rom. Bare tonehøyde og ansats: hvor tonene havner i takten, står i figuren over."),
        "source": ("<code>eval/baselines.json</code>, suite solo-instruments (runs in CI).", "<code>eval/baselines.json</code>, suiten solo-instruments (kjøres i CI)."),
    },
    "voices": {
        "title": ("From a quartet recording the top voice is found and the tenor is mostly lost",
                  "Fra et kvartettopptak blir overstemmen funnet, og tenoren for det meste borte"),
        "holds": ["brass/seat-voices/muscriptor-medium.S_f1 > 0.85", "brass/seat-voices/muscriptor-medium.T_f1 < 0.4",
                  "brass/seat-voices/basic-pitch.T_f1 < 0.4", "brass/seat-voices/consensus.T_f1 < 0.4"],
        "sub": ("One player's line picked out of the four-part mix by the range of their instrument, scored against that player's part.",
                "Én musikers linje plukket ut av den firstemte miksen etter omfanget til instrumentet, målt mot musikerens stemme."),
        "axis": F1_AXIS,
        "series": ["MuScriptor medium", "Basic Pitch", ("Notes both found", "Toner begge fant")],
        "views": [{"label": CHORALES, "n": CHORALES_N, "rows": [
            {"label": label, "keys": [f"{B}seat-voices/{m}.{v}_f1" for m in ("muscriptor-medium", "basic-pitch", "consensus")]} for v, label in (
                ("S", ("Soprano (trumpet)", "Sopran (trompet)")), ("A", ("Alto (flugelhorn)", "Alt (flygelhorn)")),
                ("T", ("Tenor (baritone)", "Tenor (baryton)")), ("B", ("Bass (tuba)", "Bass (tuba)")))]}],
        "caption": ("Onset F1 at 100 ms per voice. This is why Brasscribe writes only the tune and the bass from what it heard in a band, and "
                    "arranges the parts between them.",
                    "Onset-F1 ved 100 ms per stemme. Derfor skriver Brasscribe bare melodien og bassen fra det den hørte i et band, og "
                    "arrangerer stemmene imellom."),
        "source": ("<code>eval/baselines.json</code>, suite seat-voices (runs in CI).", "<code>eval/baselines.json</code>, suiten seat-voices (kjøres i CI)."),
    },
    "doubt": {
        "title": ("The ? marks are rarely false alarms, but they catch a third of the wrong notes at best",
                  "?-merkene er sjelden falsk alarm, men de fanger i beste fall en tredel av de gale tonene"),
        "holds": [f"brass/solo-instruments/{i}.q_hit < 0.34" for i, _ in INSTRUMENTS] + [f"brass/solo-instruments/{i}.q_false_alarm < 0.05" for i, _ in INSTRUMENTS],
        "format": "pct",
        "sub": ("Of a solo line's wrong notes, the share that carry a ?; and of its right notes, the share marked anyway.",
                "Av de gale tonene i en sololinje: andelen som har et ?; og av de riktige tonene: andelen som likevel er merket."),
        "axis": SHARE_AXIS,
        "series": [("Wrong notes that carry a ?", "Gale toner som har et ?"), ("Right notes marked ? anyway", "Riktige toner som likevel har ?")],
        "views": [{"label": ("ChoraleBricks", "ChoraleBricks"), "n": STEMS,
                   "rows": [{"label": label, "keys": [f"{B}solo-instruments/{i}.q_hit", f"{B}solo-instruments/{i}.q_false_alarm"]} for i, label in INSTRUMENTS]}],
        "caption": ("Doubt marks on solo lines. The lines have few wrong notes to begin with (the figure above), so each share is of a small number.",
                    "Tvilsmerker på sololinjer. Linjene har få gale toner i utgangspunktet (figuren over), så hver andel er av et lite antall."),
        "source": ("<code>eval/baselines.json</code>, suite solo-instruments, <code>q_hit</code> and <code>q_false_alarm</code>.",
                   "<code>eval/baselines.json</code>, suiten solo-instruments, <code>q_hit</code> og <code>q_false_alarm</code>."),
    },
    "fast-notes": {
        "title": ("Fast figures: about six notes in ten are heard, and fewer survive being written down",
                  "Raske figurer: omtrent seks av ti toner blir hørt, og færre overlever å bli skrevet ned"),
        "holds": ["brass/fast-notes/small0.sw.fig_recall > 0.5", "brass/fast-notes/small0.sw.fig_recall < 0.7",
                  "brass/fast-notes/small0.written.fig_recall < brass/fast-notes/small0.line.fig_recall",
                  "brass/fast-notes/oracle.written.fig_recall < brass/fast-notes/oracle.line.fig_recall"],
        "format": "pct",
        "sub": ("Share of the notes in a fast run, repeated-note figure or trill that are still there after each stage of the solo path.",
                "Andel av tonene i et raskt løp, en figur med gjentatte toner eller en trille som fortsatt er der etter hvert steg i soloveien."),
        "axis": ("Share of the figure's notes kept (recall)", "Andel av figurens toner beholdt (recall)"),
        "series": [("Beats given", "Slag gitt"), ("Beats tracked (Beat This! small0)", "Slag sporet (Beat This! small0)")],
        "views": [{"label": ("Fast-note clips", "Klipp med raske toner"),
                   "n": ("the frozen fast-notes clips", "de låste klippene med raske toner"),
                   "rows": [{"label": label, "keys": [f"{B}fast-notes/oracle.{stage}.fig_recall", f"{B}fast-notes/small0.{stage}.fig_recall"]} for stage, label in (
                       ("sw", ("1. Heard by the pitch tracker (SwiftF0)", "1. Hørt av tonehøydesporeren (SwiftF0)")),
                       ("line", ("2. In the solo line after the vote", "2. I sololinjen etter avstemningen")),
                       ("quantized", ("3. After snapping to the beat grid", "3. Etter plassering på slagrutenettet")),
                       ("written", ("4. Written in the score", "4. Skrevet i notene")))]}],
        "caption": ("Where fast notes are lost. The clips are rendered from real trumpet samples, dry and with a hall, with an exact reference; "
                    "they are development data, not held out.",
                    "Hvor raske toner går tapt. Klippene er satt sammen av ekte trompetsamplinger, tørt og med romklang, med nøyaktig fasit; "
                    "de er utviklingsdata, ikke holdt utenfor."),
        "source": ("<code>eval/baselines.json</code>, suite fast-notes (runs in CI).", "<code>eval/baselines.json</code>, suiten fast-notes (kjøres i CI)."),
    },
    "agreement": {
        "title": ("A note that two models heard is almost always right; a note only one heard is a coin toss or worse",
                  "En tone som to modeller hørte, er nesten alltid riktig; en tone bare én hørte, er som myntkast eller verre"),
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
        "caption": ("Model comparison on the same recordings. The pieces behind the first rows spread widely; the transcription figure shows them.",
                    "Modellsammenligning på de samme opptakene. Stykkene bak de første radene spriker mye; transkripsjonsfiguren viser dem."),
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
                    "strict test: other inner parts can be equally good music.",
                    "Kvartettarrangøren ser en melodi, en bass og harmonien, og skriver de to stemmene imellom. Å treffe komponisten er en streng "
                    "prøve: andre mellomstemmer kan være like god musikk."),
        "source": ("<code>eval/baselines.json</code>, suites arrange and quartet-audio (the chorale parts run in CI).",
                   "<code>eval/baselines.json</code>, suitene arrange og quartet-audio (koraldelene kjøres i CI)."),
    },
    "speed": {
        "title": ("The models a phone runs take under a second per minute of music; the separators and MuScriptor take from "
                  "{c/bs-roformer-sw/coreml-fp16-ALL.s_per_min|sec} to over a minute, and gigabytes of memory",
                  "Modellene en telefon kjører, bruker under ett sekund per minutt musikk; separatorene og MuScriptor bruker fra "
                  "{c/bs-roformer-sw/coreml-fp16-ALL.s_per_min|sec} til over et minutt, og gigabyte med minne"),
        "holds": ["c/swift-f0/coreml-fp32-ALL.s_per_min < 1", "c/basic-pitch/coreml-b1-fp32-ALL.s_per_min < 1", "c/beat-this/small0/coreml-fp16-ALL.s_per_min < 1",
                  "c/muscriptor/onnx-ort-cpu.s_per_min > 60", "c/mega53/coreml-fp16-ALL.peak_gb > 8", "c/bs-roformer-sw/coreml-fp16-ALL.peak_gb > 2"],
        "sub": ("Each model alone on one Apple M5 Pro laptop with 48 GB. No phone has been timed.",
                "Hver modell alene på én bærbar Apple M5 Pro med 48 GB. Ingen telefon er målt."),
        "series": [("Converted for devices (best passing conversion)", "Konvertert for enheter (beste godkjente konvertering)"),
                   ("Reference framework on the processor", "Referanserammeverket på prosessoren")],
        "view_label": ("Measure", "Mål"),
        "views": [{"label": label, "format": how, "max": "auto", "axis": axis, "note": note,
                   "n": ("30 s of audio (Beat This!: 60 s), median of 1 to 5 runs", "30 s lyd (Beat This!: 60 s), median av 1 til 5 kjøringer"),
                   "rows": [{"label": name, "keys": [f"c/{model}/{converted}.{field}", f"c/{model}/{reference}.{field}"]} for name, model, converted, reference in (
                       ("SwiftF0 (pitch of one line)", "swift-f0", "coreml-fp32-ALL", "ort-cpu-upstream"),
                       ("Basic Pitch (notes)", "basic-pitch", "coreml-b1-fp32-ALL", "tf-savedmodel"),
                       ("Beat This! small0 (beats)", "beat-this", "small0/coreml-fp16-ALL", "small0/torch-cpu"),
                       ("HT-Demucs (separation, 4 stems)", "htdemucs", "coreml-fp32-ALL", "torch-cpu"),
                       ("BS-RoFormer SW (separation, 6 stems)", "bs-roformer-sw", "coreml-fp16-ALL", "torch-cpu"),
                       ("Mega-53 (separation, 53 stems)", "mega53", "coreml-fp16-ALL", "torch-cpu"),
                       ("MuScriptor medium (notes)", "muscriptor", "onnx-ort-cpu", "torch-cpu"))]}
                  for label, how, field, axis, note in (
                      (("Time", "Tid"), "sec", "s_per_min", ("Seconds of computing per minute of audio (60 s = as long as the music)", "Sekunder regnetid per minutt lyd (60 s = like lenge som musikken)"),
                       ("Lower is faster. The three small models are not zero: their numbers are beside the axis.", "Lavere er raskere. De tre små modellene er ikke null: tallene står ved aksen.")),
                      (("Memory", "Minne"), "gb", "peak_gb", ("Peak memory of the process, GB", "Høyeste minnebruk for prosessen, GB"),
                       ("The whole process, with the framework loaded.", "Hele prosessen, med rammeverket lastet.")))],
        "caption": ("Speed and memory per model. A whole job adds loading, the music rules and the export: the text below gives two measured jobs.",
                    "Fart og minne per modell. En hel jobb legger til lasting, musikkreglene og eksporten: teksten under gir to målte jobber."),
        "source": ("<code>convert/reports/*.json</code> (made by the scripts in <code>convert/</code>; <code>python3 convert/summarize.py</code> prints them).",
                   "<code>convert/reports/*.json</code> (laget av skriptene i <code>convert/</code>; <code>python3 convert/summarize.py</code> skriver dem ut)."),
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
            [("model", ("Separate", "Skill lagene"), (["full band only:", "BS-RoFormer SW, Mega-53"], ["bare fullt band:", "BS-RoFormer SW, Mega-53"])),
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
            [("rule", ("Share or print", "Del eller skriv ut"), (["MusicXML · PDF · MIDI · MP3 · braille · talking score"], ["MusicXML · PDF · MIDI · MP3 · punktskrift · talende noter"]))],
        ],
    },
}
