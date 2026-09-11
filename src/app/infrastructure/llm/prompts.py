PROMPT_SUMMARY = (
    "Below is an audio transcript section from a recording. "
    "Please provide a concise, structured executive summary of what is discussed.\n"
    "CRITICAL REQUIREMENT: Do NOT output any thinking, reasoning steps, or internal monologue. Output ONLY the final summary.\n"
    "CRITICAL REQUIREMENT: You MUST write your response entirely in the language corresponding to language code '{lang}'.\n\n"
    "Transcript:\n{transcript}"
)

PROMPT_SUMMARY_COMBINE = (
    "Below are partial summaries from consecutive sections of one recording. "
    "Combine them into one concise, structured executive summary covering all sections. "
    "Preserve important decisions, action items, names, dates, and technical details.\n"
    "CRITICAL REQUIREMENT: Do NOT output any thinking, reasoning steps, or internal monologue. Output ONLY the final summary.\n"
    "CRITICAL REQUIREMENT: You MUST write your response entirely in the language corresponding to language code '{lang}'.\n\n"
    "Partial summaries:\n{summaries}"
)

PROMPT_HIGHLIGHTS = (
    "Analyze the following SRT subtitles (which include exact timestamps). "
    "Identify key highlights where the speaker says something important (e.g. 'it is important', key conclusions, "
    "or phrases indicating showing/referring to something on screen like 'look at this', 'here on the screen', 'as you can see').\n"
    "Format the output strictly as a bulleted list with exact timestamp (seconds / timestamp) and description.\n"
    "CRITICAL REQUIREMENT: Do NOT output any thinking, reasoning steps, or internal monologue. Output ONLY the final bulleted list.\n"
    "CRITICAL REQUIREMENT: You MUST write your response entirely in the language corresponding to language code '{lang}'.\n\n"
    "SRT Subtitles:\n{srt_content}"
)

PROMPT_VISION_FRAME = (
    "This frame belongs to a video recording described as: '{user_desc}'. "
    "At this timestamp, the speaker said: '{audio_context}'. "
    "If the frame shows a browser screen try to capture the whole URL. "
    "Analyze this frame and extract active URLs, UI elements, and screen interactions relevant to what was spoken, "
    "and pinpoint where the mouse pointer / cursor is located on the screen if visible.\n"
    "CRITICAL REQUIREMENT: Do NOT output any thinking or reasoning steps. Output ONLY the final frame description.\n"
    "CRITICAL REQUIREMENT: You MUST write your response entirely in the language corresponding to language code '{lang}'.\n"
)
