# Media-Type Classification

Phase 4 (WS-D) guesses what kind of media you selected and suggests sensible
defaults. It is designed to be instant and never block the job.

## Tier 1 (instant, always)

Deterministic signals only — filename keywords, track layout (video/audio),
duration and the presence of a speaker VTT file. It runs on selection, takes
well under a second, and shows a suggestion in the pinned action area:

```
Media type: meeting (70%)
```

Types: `meeting`, `lecture`, `interview`, `tutorial`, `webinar`, `podcast`,
`presentation`, `other`. Each guess carries a `confidence`. **Low confidence
falls back to the defaults** (`other`, no suggestion) — the app never acts on a
weak guess.

The guess (type, confidence, tier, signals, suggested frame mode/preset) is
stored in `job_state.json` under `media_type` and shown in
`Summary_Report.md` as **Media type**.

Suggested frame mode: screen-style media (`tutorial`, `presentation`,
`lecture`) → `scene`; talking media (`meeting`, `webinar`, `interview`,
`podcast`) → `interval`.

## Tier 3 (optional AI pass)

`parse_classification_output` / `merge_tier3` turn an LLM reply (via the
`media_type_classification` prompt) into a refined guess that overrides the
Tier-1 type when confident. The AI pass is optional and always degrades to the
Tier-1 result; it must never gate job start.

## Soft budget

Tier 1 is effectively free. Heavier probes (tiny Whisper snippet, audio
loudness, frame classifier) are intended to run under a ~10s **soft** budget:
they run asynchronously, are cancelled if they exceed it, and the job can start
before they finish. Tier 1 always stands as the fallback.

## Not yet wired

The asynchronous Tier-2 probes and the live AI refinement loop (updating the
suggestion only if the user has not overridden it) are the remaining WS-D work;
the pure classification and parsing logic they build on is implemented and
tested.

In the current release, the classification runs from the Tier-1 signals only
(duration, container/codec and extension). The heavier probes described above
are designed but not scheduled, so the media type can be less specific than
the design intends — for example an interview is reported from its container
and duration rather than from a spoken-word probe. The tier-1 fallback always
stands, so a job never blocks on this.
