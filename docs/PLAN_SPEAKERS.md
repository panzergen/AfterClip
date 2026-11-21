# Plan: Speakers section and transcript filtering

Target release: **0.6.0** (after the current output/HTML work).

## Goal

Make speakers a first-class navigation surface instead of only a label on
timeline entries.

## 1. Speakers section at the top of the HTML report

Add a compact **Speakers** section before the summary:

| Field | Meaning |
|---|---|
| Name | VTT name, voiceprint name, or `Speaker N` |
| Source | `VTT`, `voiceprint`, `mixed` or `unknown` |
| Speaking time | Sum of that speaker's labeled intervals |
| Segments | Number of transcript blocks attributed to the speaker |
| First / last | First and last timestamp where the speaker appears |

Interaction:

- Click a speaker to filter the timeline to that speaker.
- Click **All speakers** to reset.
- The active filter should be visible in the section.
- Filtering is view-only; the source transcript and JSONL stay unchanged.

## 2. Transcript speaker filter

In the transcript/timeline view, add a speaker selector:

- **All speakers** by default.
- Selecting one speaker shows only their transcript blocks.
- Show the filtered segment count and total speaking time.
- Preserve the original transcript files; this is a view filter, not a
  destructive edit.
- The same filter should apply to the HTML report where practical.
- Optionally persist the selected speaker per job, not globally.

## 3. Data and provenance

- Build speaker statistics from the existing `SpeakerInterval` data.
- Record `speaker_source` per label where possible:
  - VTT is authoritative for supplied names.
  - Voiceprints are probabilistic and may produce `Speaker N`.
  - VTT takes precedence; voiceprints fill gaps.
- Add `speaker`, `speaker_source` and `speaker_id` to the JSONL timeline and
  the metadata sidecar.
- Keep the Markdown timeline readable; speaker labels remain inline.

## 4. Acceptance

- Speaker totals match the labels in `Master_Timeline.md`.
- Filtering to one speaker never changes the source files.
- A job without VTT/voiceprints still shows the section as unavailable/empty.
- HTML filtering works on lean, thumbnail and full report modes.
- A speaker with no transcript blocks is either omitted or clearly marked.
