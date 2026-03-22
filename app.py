import os
import re
import tempfile
import streamlit as st
import assemblyai as aai
from pathlib import Path

st.set_page_config(page_title="Podcast Transcriber", page_icon="🎙️", layout="centered")

SPEAKER_NAMES = {
    "A": "Allie",
    "B": "Aaron",
}

TIMECODE_INTERVAL_MS = 20_000  # 20 seconds


def format_time(ms: int) -> str:
    seconds = ms // 1000
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def build_transcript(utterances) -> str:
    lines = []
    last_timecode_at = -TIMECODE_INTERVAL_MS
    current_speaker = None

    for utt in utterances:
        start = utt.start
        speaker = SPEAKER_NAMES.get(utt.speaker, f"Speaker {utt.speaker}")
        text = utt.text.strip()

        if not text:
            continue

        if start >= last_timecode_at + TIMECODE_INTERVAL_MS:
            while last_timecode_at + TIMECODE_INTERVAL_MS <= start:
                last_timecode_at += TIMECODE_INTERVAL_MS
            lines.append(f"\n[{format_time(last_timecode_at)}]")
            current_speaker = None

        if speaker != current_speaker:
            lines.append(f"\n{speaker}:")
            current_speaker = speaker

        lines.append(f"  {text}")

    return "\n".join(lines).strip()


def search_transcript(transcript: str, keyword: str):
    blocks = re.split(r'(?=\n\[[\d:]+\])', transcript)
    matches = []
    for block in blocks:
        if re.search(re.escape(keyword), block, re.IGNORECASE):
            highlighted = re.sub(
                f'({re.escape(keyword)})',
                r'**\1**',
                block,
                flags=re.IGNORECASE
            )
            matches.append(highlighted.strip())
    return matches


# ── API key ──────────────────────────────────────────────────────────────────
api_key = st.secrets.get("ASSEMBLYAI_API_KEY", os.environ.get("ASSEMBLYAI_API_KEY", ""))
if not api_key:
    st.error("AssemblyAI API key not set. Add it to your Streamlit secrets as ASSEMBLYAI_API_KEY.")
    st.stop()

aai.settings.api_key = api_key

# ── Header ───────────────────────────────────────────────────────────────────
st.title("Podcast Transcriber")
st.caption("Upload an episode · get a transcript with timecodes and speaker labels · search it.")

tab_transcribe, tab_search = st.tabs(["Transcribe", "Search"])

# ── Transcribe tab ────────────────────────────────────────────────────────────
with tab_transcribe:
    uploaded = st.file_uploader(
        "Upload your episode",
        type=["mp3", "m4a", "wav", "flac", "ogg"],
    )

    if uploaded:
        st.audio(uploaded)

        if st.button("Transcribe", type="primary"):
            with st.spinner("Transcribing… this usually takes 1–3 minutes."):
                suffix = Path(uploaded.name).suffix
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
                    f.write(uploaded.read())
                    tmp_path = f.name

                try:
                    config = aai.TranscriptionConfig(speaker_labels=True)
                    result = aai.Transcriber().transcribe(tmp_path, config=config)

                    if result.status == aai.TranscriptStatus.error:
                        st.error(f"Transcription failed: {result.error}")
                    else:
                        transcript = build_transcript(result.utterances)
                        st.session_state["transcript"] = transcript
                        st.session_state["episode_name"] = Path(uploaded.name).stem
                        st.success("Done!")
                finally:
                    os.unlink(tmp_path)

    if "transcript" in st.session_state:
        st.text_area("Transcript", st.session_state["transcript"], height=450)
        st.download_button(
            "Download transcript (.txt)",
            data=st.session_state["transcript"],
            file_name=f"{st.session_state['episode_name']}_transcript.txt",
            mime="text/plain",
        )

# ── Search tab ────────────────────────────────────────────────────────────────
with tab_search:
    if "transcript" not in st.session_state:
        st.info("Transcribe an episode first, then come back here to search it.")
    else:
        keyword = st.text_input("Search keyword or phrase", placeholder="e.g. anxiety")

        if keyword:
            matches = search_transcript(st.session_state["transcript"], keyword)

            if not matches:
                st.write(f'No results found for **"{keyword}"**')
            else:
                st.write(f'**{len(matches)} section(s)** containing "{keyword}":')
                st.divider()
                for i, block in enumerate(matches):
                    st.markdown(f"```\n{block}\n```")
                    if i < len(matches) - 1:
                        st.divider()
