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
if "quiz_results" not in st.session_state:
    st.session_state.quiz_results = {}

def pack_identity(text, language, goal):
    return hashlib.sha256(json.dumps([text.strip(), language, goal, 2]).encode()).hexdigest()

def load_demo():
    example = json.loads((Path(__file__).parent / "demo/study_pack.json").read_text())
    st.session_state.notes = example["notes"]
    st.session_state.language = "English"
    st.session_state.goal = "Understand the concept"
    st.session_state.packs[pack_identity(example["notes"], "English", "Understand the concept")] = example["pack"]
    st.session_state.demo_notes = example["notes"]

def load_sample(language):
    st.session_state.language = language
    st.session_state.notes = SAMPLES["hi-IN" if language == "Hindi" else "en-IN"]

with st.sidebar:
    st.title("Suno.")
    st.caption("READ → LISTEN → RECALL")
    st.divider()
    st.markdown("**A quieter way to learn.**")
    st.write("For students who understand more when they can hear, revisit, and test an idea in their own language.")
    st.caption("Hindi + English · explicit generation · private session")
    st.divider()
    st.button("✦ Explore the instant demo", on_click=load_demo, use_container_width=True)
    st.caption("Real, previously generated audio and questions. No new credits needed.")
    spending_display = st.empty()
    st.caption("Before GST. Not your verified account balance. Replays and quiz checks cost nothing.")
    st.caption("Powered by Sarvam-105B + Bulbul v4 Flash")
    st.caption("Aaditya Rathi & Priyanshi Agarwal · IIT Kanpur")
    st.link_button("View project on GitHub", "https://github.com/arathii23/suno-study-lab")
st.caption("YOUR STUDY SPACE")
st.title("Your notes, out loud.")
st.write("Listen to a concept. Make it simpler. Find out what you remember.")
intro, demo = st.columns([2, 1])
with intro:
    st.caption("FOR COMMUTES, SCREEN BREAKS & EXAM REVISION")
    st.write("**One set of notes. Three ways to learn:** natural narration, source-grounded flashcards, and a quiz that shows what to revisit.")
with demo:
    st.button("Try the free 60-second demo", on_click=load_demo, type="primary", use_container_width=True)
    st.caption("No sign-up. No generation charge. Start with Listen, then open Understand & recall.")
with st.expander("Why Suno? · A student-first learning loop"):
    st.write("**Listen:** choose Hindi or English voices and your pace. **Recall:** answer before revealing explanations. **Revisit:** focus on missed concepts instead of rereading everything.")
    st.caption("Designed to support students who prefer audio and revision on the move. Learning outcomes have not been measured. Notes are sent to Sarvam only when you request generation; session data is temporary, not a permanent notebook.")
left, right = st.columns([1.65, 1], gap="large")
with right:
    language = st.radio("Reading language", ["Hindi", "English"], horizontal=True, key="language")
    code = "hi-IN" if language == "Hindi" else "en-IN"
    speaker = st.selectbox("Your narrator", [v["id"] for v in VOICES[code]], format_func=lambda x: next(v["name"] + " · " + v["style"] for v in VOICES[code] if v["id"] == x))
    pace = st.slider("Reading speed", 0.5, 2.0, 1.0, 0.05)
    goal = st.selectbox("Your study goal", ["Understand the concept", "Revise for an exam", "Explain it to a beginner"], key="goal")
    st.caption("Language selection does not translate notes. The study pack can explain them in your selected language.")
with left:
    if "notes" not in st.session_state:
        st.session_state.notes = SAMPLES["hi-IN"]
    a, b = st.columns(2)
    a.button("Load Hindi sample", on_click=load_sample, args=("Hindi",), use_container_width=True)
    b.button("Load English sample", on_click=load_sample, args=("English",), use_container_width=True)
    notes = st.text_area("Your study notes", key="notes", height=230, max_chars=2000)
    st.caption(f"{len(notes.strip())} / 2,000 characters · Estimated narration ₹{len(notes.strip()) / 1000:.3f} before GST")
listen, recall = st.tabs(["🎧 Listen & revisit", "✦ Understand & recall"])
with listen:
    st.subheader("Make room for listening.")
    if notes.strip() == st.session_state.get("demo_notes") and language == "English":
        st.info("Previously generated example · Aparna at 1× · free to replay")
        demo_audio = (Path(__file__).parent / "demo/narration.wav").read_bytes()
        st.audio(demo_audio, format="audio/wav")
        st.download_button("Download example audio", demo_audio, "suno-example.wav", "audio/wav")
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
    pack_id = pack_identity(notes, language, goal)
    if st.button("Create my study pack", type="primary", disabled=len(notes.strip()) < 20):
        try:
            if pack_id not in st.session_state.packs:
                with st.spinner("Making your revision pack with Sarvam-105B…"):
                    pack = build_pack(notes, language, goal)
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
        reviewed = 0
        for index, card in enumerate(pack["flashcards"]):
            with st.expander(f"{index + 1}. {card['question']}"):
                st.write(card["answer"])
                if card.get("evidence"):
                    st.caption("From your notes: “" + card["evidence"] + "”")
                reviewed += st.checkbox("Mark as reviewed", key=f"reviewed-{pack_id}-{index}")
        st.progress(reviewed / max(1, len(pack["flashcards"])), text=f"{reviewed} / {len(pack['flashcards'])} flashcards reviewed")
        if pack["quiz"]:
            st.markdown("#### What stuck? Take a quick check.")
            with st.form(f"quiz-{pack_id}"):
                answers = [st.radio(q["question"], range(3), format_func=lambda i, q=q: q["options"][i], index=None, key=f"{pack_id}-{i}") for i, q in enumerate(pack["quiz"])]
                if st.form_submit_button("Check my understanding"):
                    if any(answer is None for answer in answers):
                        st.warning("Answer every question before checking your understanding.")
                    else:
                        st.session_state.quiz_results[pack_id] = answers
            submitted = st.session_state.quiz_results.get(pack_id)
            if submitted is not None:
                score = sum(answer == q["answer_index"] for answer, q in zip(submitted, pack["quiz"]))
                st.success(f"You recalled {score} of {len(pack['quiz'])} concepts.")
                missed = [q for answer, q in zip(submitted, pack["quiz"]) if answer != q["answer_index"]]
                st.markdown("#### Your next revision step")
                if missed:
                    st.info(f"Focus on {len(missed)} concept(s), then try the quiz again. This revision plan costs no extra credits.")
                    for number, q in enumerate(missed, 1):
                        st.markdown(f"**{number}. {q['question']}**")
                        st.write(q["explanation"])
                    revision = "# My focused revision plan\n\n" + "\n\n".join(f"## {q['question']}\n{q['explanation']}" for q in missed)
                    st.download_button("Download my revision checklist", revision, "suno-revision-checklist.md", "text/markdown")
                else:
                    st.success("All concepts recalled! Explain the big idea aloud without looking, then revisit it tomorrow.")
                for q in pack["quiz"]:
                    with st.expander("Answer: " + q["options"][q["answer_index"]]):
                        st.write(q["explanation"])
                        if q.get("evidence"):
                            st.caption("From your notes: “" + q["evidence"] + "”")
        guide = "# Suno study guide\n\n" + pack["summary"] + "\n\n## Flashcards\n\n" + "\n\n".join(f"### {c['question']}\n{c['answer']}" for c in pack["flashcards"])
        guide += "\n\n## Quiz answers\n\n" + "\n\n".join(f"### {q['question']}\n{q['options'][q['answer_index']]}\n\n{q['explanation']}" for q in pack["quiz"])
        st.download_button("Download your study guide", guide, "suno-study-guide.md", "text/markdown")
    else:
        st.info("Try ‘Explore the instant demo’ in the sidebar to see flashcards and a quiz without spending credits.")
spending_display.metric("Estimated use this session", f"₹{st.session_state.spending:.3f}")
st.divider()
st.caption("Made for multilingual learning and accessible revision. No model training has been performed. Each generation requires your click; automatic retries are disabled.")
