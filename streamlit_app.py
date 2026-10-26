"""Cloud-ready Suno Study Lab: listen, understand, and recall."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import streamlit as st
from reader import Reader, ReaderError, SAMPLES, VOICES
from study import build_pack

st.set_page_config(page_title="Suno Study Lab", page_icon="🎧", layout="wide")
try:
    if "SARVAM_API_KEY" in st.secrets:
        os.environ["SARVAM_API_KEY"] = st.secrets["SARVAM_API_KEY"]
except FileNotFoundError:
    pass

st.markdown("<style>h1{font-family:Georgia,serif!important;letter-spacing:-2px} .stMainBlockContainer{max-width:1100px;padding-top:2rem} div.stButton>button[kind=primary]{border-radius:9px} footer{display:none}</style>", unsafe_allow_html=True)
if "workspace" not in st.session_state:
    st.session_state.workspace = tempfile.mkdtemp(prefix="suno-session-")
    st.session_state.packs = {}
    st.session_state.spending = 0.0
reader = Reader(Path(st.session_state.workspace))
with st.sidebar:
    st.title("Suno.")
    st.caption("READ → LISTEN → RECALL")
    st.divider()
    st.markdown("**A quieter way to learn.**")
    st.write("For students who understand more when they can hear, revisit, and test an idea in their own language.")
    st.caption("Hindi + English · explicit generation · private session")
    st.divider()
    st.metric("Estimated use this session", f"₹{st.session_state.spending:.3f}")
    st.caption("Before GST. Not your verified account balance. Replays and quiz checks cost nothing.")
    st.caption("Powered by Sarvam-105B + Bulbul v4 Flash")
st.caption("YOUR STUDY SPACE")
st.title("Your notes, out loud.")
st.write("Listen to a concept. Make it simpler. Find out what you remember.")
left, right = st.columns([1.65, 1], gap="large")
with right:
    language = st.radio("Reading language", ["Hindi", "English"], horizontal=True)
    code = "hi-IN" if language == "Hindi" else "en-IN"
    speaker = st.selectbox("Your narrator", [v["id"] for v in VOICES[code]], format_func=lambda x: next(v["name"] + " · " + v["style"] for v in VOICES[code] if v["id"] == x))
    pace = st.slider("Reading speed", 0.5, 2.0, 1.0, 0.05)
    st.caption("Language selection does not translate notes. The study pack can explain them in your selected language.")
with left:
    if "notes" not in st.session_state:
        st.session_state.notes = SAMPLES["hi-IN"]
    a, b = st.columns(2)
    if a.button("Load Hindi sample", use_container_width=True):
        st.session_state.notes = SAMPLES["hi-IN"]
    if b.button("Load English sample", use_container_width=True):
        st.session_state.notes = SAMPLES["en-IN"]
    notes = st.text_area("Your study notes", key="notes", height=230, max_chars=2000)
    st.caption(f"{len(notes.strip())} / 2,000 characters · Estimated narration ₹{len(notes.strip()) / 1000:.3f} before GST")
listen, recall = st.tabs(["🎧 Listen & revisit", "✦ Understand & recall"])
with listen:
    st.subheader("Make room for listening.")
    if st.button("Generate narration", type="primary", disabled=not notes.strip()):
        try:
            with st.spinner("Finding the rhythm in your notes…"):
                result = reader.generate({"text": notes, "language": code, "speaker": speaker, "pace": pace})
            st.session_state.recording = result
            st.session_state.spending += result["generation_estimate_inr"]
            st.success("Saved audio reused — no new charge." if result["cached"] else "Your narration is ready.")
        except ReaderError as error:
            st.error(str(error))
    if "recording" in st.session_state:
        result = st.session_state.recording
        path = reader.audio / f"{result['id']}.wav"
        st.audio(path.read_bytes(), format="audio/wav")
        st.download_button("Download narration", path.read_bytes(), "suno-study-notes.wav", "audio/wav")
        st.caption(f"{result['characters']} characters · {result['seconds']:.1f} seconds · Saved in this session")
with recall:
    st.subheader("Don't just listen. Remember.")
    st.write("Turn your notes into a short explanation, three flashcards, and a self-check quiz. AI uses the notes you provide; review the results against your source.")
    pack_id = hashlib.sha256((notes.strip() + language).encode()).hexdigest()
    if st.button("Create my study pack", type="primary", disabled=len(notes.strip()) < 20):
        try:
            if pack_id not in st.session_state.packs:
                with st.spinner("Making your revision pack with Sarvam-105B…"):
                    pack = build_pack(notes, language)
                st.session_state.packs[pack_id] = pack
                st.session_state.spending += pack["estimated_cost_inr"]
            st.success("Your study pack is ready. Reopening it and checking answers are free.")
        except ReaderError as error:
            st.error(str(error))
    pack = st.session_state.packs.get(pack_id)
    if pack:
        st.markdown("#### The big idea")
        st.write(pack["summary"])
        st.markdown("#### Flip through your flashcards")
        for index, card in enumerate(pack["flashcards"]):
            with st.expander(f"{index + 1}. {card['question']}"):
                st.write(card["answer"])
        if pack["quiz"]:
            st.markdown("#### What stuck? Take a quick check.")
            with st.form(f"quiz-{pack_id}"):
                answers = [st.radio(q["question"], range(3), format_func=lambda i, q=q: q["options"][i], index=None, key=f"{pack_id}-{i}") for i, q in enumerate(pack["quiz"])]
                if st.form_submit_button("Check my understanding"):
                    score = sum(answer == q["answer_index"] for answer, q in zip(answers, pack["quiz"]))
                    st.success(f"You recalled {score} of {len(pack['quiz'])} concepts.")
                    for q in pack["quiz"]:
                        st.write(f"**{q['options'][q['answer_index']]}** — {q['explanation']}")
        st.download_button("Download revision pack", json.dumps(pack, ensure_ascii=False, indent=2), "suno-revision.json", "application/json")
st.divider()
st.caption("Made for multilingual learning and accessible revision. No model training has been performed. Each generation requires your click; automatic retries are disabled.")
