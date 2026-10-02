#!/usr/bin/env python3
"""Ask the engine's own option check about every tab job the Fretscribe app can send.

    pixi run python apps/android/scripts/check-tab-options.py <jobs.jsonl>

Each line of the file is {"body": <the body of POST /v1/jobs as the app encodes it>, "expect": {...}}:
`expect` names what the app means the job to be (instrument, tuning, capo, layout, recording). The body goes
the way the API takes it: validated as the API's JobCreate, turned into the job's parameters as createJob
does, and checked by profiles.job_options. A job passes when the engine accepts it and reads it as the app
meant it.

The app's unit test `TabJobOptionsTest` writes the file and runs this; it skips itself where the engine is
not set up. Exit code 0: every job passed; 1: some did not (each is printed); 3: the engine cannot check
(the core's command line is missing).
"""
import json
import sys
from pathlib import Path

from brasscribe_engine import bass_tab, profiles, schemas, tab


def params_of(body: schemas.JobCreate) -> dict:
    """The job's parameters, as the API's createJob builds them."""
    params = {"audio": body.render_audio, "lineup": body.lineup, "difficulty": body.difficulty,
              "key": body.key, "transpose": body.transpose, "seat": body.seat, "reads": body.reads, "lead": body.lead}
    if not body.muscriptor:
        params["muscriptor"] = False
    params.update(tab.given(instrument=body.instrument, tuning=body.tuning, capo=body.capo, style=body.style,
                            recording=body.recording, octave=body.octave, layout=body.layout, chords=body.chords))
    return params


def main() -> int:
    try:
        bass_tab.core_cli()
    except bass_tab.CoreCliMissing as e:
        print(e, file=sys.stderr)
        return 3
    wrong = []
    jobs = [json.loads(line) for line in Path(sys.argv[1]).read_text().splitlines() if line.strip()]
    for job in jobs:
        try:
            body = schemas.JobCreate.model_validate(job["body"])
            if body.profile not in profiles.PROFILES:
                raise ValueError(f"unknown profile {body.profile}")
            opts = profiles.job_options(body.profile, params_of(body))
        except ValueError as e:  # pydantic's ValidationError is one
            wrong.append(f"refused: {json.dumps(job['body'])}: {str(e).splitlines()[0]}")
            continue
        differs = {k: (v, opts.get(k)) for k, v in job["expect"].items() if opts.get(k) != v}
        if differs:
            wrong.append(f"read otherwise: {json.dumps(job['body'])}: {differs}")
    for line in wrong:
        print(line)
    print(f"{len(jobs) - len(wrong)} of {len(jobs)} jobs accepted and read as meant")
    return 1 if wrong or not jobs else 0


if __name__ == "__main__":
    sys.exit(main())
