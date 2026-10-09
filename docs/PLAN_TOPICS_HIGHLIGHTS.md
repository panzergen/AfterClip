# Plan: Topics & Highlights refinements

Decisions made with the user; carry forward in later chats. Status markers at the
end of each section.

## 1. Topic segmentation — DONE

**Problem:** `Topics.md` produced a near-fixed ~2 min cadence and then one giant
topic for everything after ~01:01:30 (a 2 h meeting → last section was ~61 min).

**Root cause:**
- `topic_max_sections` was capped at **20**, so the algorithm stopped splitting
  after 20 sections and lumped the rest into the final one.
- `topic_min_seconds` defaulted to **120**, forcing boundaries ≥ 2 min apart.

**Fix (implemented):**
- `DEFAULT_TOPIC_MIN_SECONDS` 120 → **60**.
- `DEFAULT_TOPIC_MAX_SECTIONS` 20 → **0**, where `0 = auto`.
- New `topics.auto_max_sections(duration_seconds)` → `max(4, min(120, duration/60))`
  (about one section per minute, bounded).
- `segment_topics_cohesion(..., max_sections=None)` derives the cap from duration
  when `None`; the service passes `request.topic_max_sections or None`.
- `TranscriptionRequest.topic_max_sections` default 20 → 0; `topic_min_seconds`
  default 120 → 60.

Settings keys (unchanged names): `topic_method`, `topic_min_seconds`,
`topic_max_sections`. CLI: `--topics off|cohesion|ai`, `--topic-min-seconds`,
`--topic-max-sections`.

Status: **implemented and tested** (295 + 58).

## 2. Highlights — rework (PLANNED)

**Problem:** highlights are extracted *per transcription chunk* (85 chunks for a
2 h meeting) and concatenated, so they are numerous and scoped to each chunk,
not the overall video.

**Decisions (from user):**
1. At most **1 highlight per 5 minutes** of video.
2. Keep the existing headline/format; the complaint was the *number*, not content.
3. At most **3 highlights** total in the report.
4. Score cut-off **≥ 7** (0–10 scale).
5. **Single LLM call** — no second ranking call; global ranking done in code.
6. Do the topic fix now (done above).

**Approach (single call):**
- Change the `highlights` prompt so each chunk returns a compact JSON array of
  *scored candidates* instead of a bullet list:
  `[{"start":"HH:MM:SS","end":"HH:MM:00","title":"…","score":8,"reason":"…"}]`.
- In code (`extract_highlights` + a new aggregator):
  1. Parse every chunk's candidates.
  2. Drop `score < 7`.
  3. Deduplicate near-duplicate titles.
  4. Enforce max **1 per 5 minutes** (keep the highest score in each 5-min window).
  5. Sort by score desc, keep the top **3**.
  6. Render the final short list (existing bullet/timestamp format).

**Draft prompt (Stage 1 criteria — same call):**
> Score each candidate 0–10 as a meeting highlight.
> **High score when:** the speaker emphasizes importance/commitment ("this is
> important", "we definitely do this", "we must…"); a decision **changes**
> ("we said X before, now we change to Y"); an action is assigned ("I'll add this
> to my list", "<person> will do it", "we will open a task/ticket"); a follow-up
> is scheduled ("let's talk about this next meeting", "we'll revisit this").
> **Low score when:** the item is optional, a "nice to have", or for the distant
> future.
> Return compact JSON only, no prose.

**Implementation notes / open items:**
- Add/update `highlight` prompt in `domain/prompts.py` and the prompt store
  (placeholder `{lang}`, `{srt_content}` — already exists; just change the text).
- The scoring/cap/spacing logic lives in `application/service.py` or a new
  `application/highlights.py`; update `clean_highlights_output` or replace its
  use in `extract_highlights`.
- `clean_highlights_output` currently keeps only timestamped lines; will be
  replaced by the JSON-candidate parser + aggregator.
- Ensure the topic/highlight tests are updated (`tests/application/test_service.py`,
  `tests/application/test_topics.py`, plus a new aggregator unit test).

Status: **NOT implemented** — do this next chat per the decisions above.
