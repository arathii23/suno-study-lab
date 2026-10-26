# Suno — your notes, out loud

**Live app: https://suno-study-lab.streamlit.app/**  
**Aaditya Rathi and Priyanshi Agarwal · IIT Kanpur**

## One-minute demo

Click **Explore the instant demo**, play the saved real Sarvam narration, then open **Understand & recall**. Expand the flashcards, mark them reviewed, take the quiz, and download a readable study guide. This example uses no new API credits.

Three study goals tailor new packs for conceptual understanding, exam revision, or a beginner. Exact evidence quotes are shown only when found in the source notes. Flashcard review progress and quiz feedback persist during the session. Language selection supports Hindi and English. Model output is a revision aid, not independently verified educational material.

## Streamlit Study Lab

Run `.venv/bin/python -m streamlit run streamlit_app.py` and open http://localhost:8501.
The Streamlit edition adds Sarvam-105B explanations, flashcards, an interactive scored quiz, and downloadable revision packs. Both AI generation actions require a click. Reopening a study pack, flipping cards, checking quiz answers, and replaying audio do not call an AI model. Study content is isolated by browser session. This is prompt-based product refinement, not model-weight fine-tuning.

Deployment source: https://github.com/arathii23/suno-study-lab (public).
Streamlit Community Cloud deploys repository `arathii23/suno-study-lab`, branch `main`, entrypoint `streamlit_app.py` with Python 3.13. The API key is configured in private Streamlit Secrets and excluded from GitHub. Source changes on main update the live app automatically. The prepared public example in `demo/` contains only sample notes and previously generated outputs.

A local study reader with Hindi and Indian English narration, a choice of three documented voices per language, generation speeds from 0.5× to 2×, audio playback/seeking, WAV download, and a persistent audio cache. Paste up to 2,000 characters. The text is narrated as written; language selection does not translate it.

## Run

From this project directory:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python server.py
```

Open **http://127.0.0.1:8000**. If the environment is already installed, only the last command is necessary. To choose another port: `.venv/bin/python server.py --port 8001`. Stop with Ctrl+C.

The latest supplied API key is already in the local `.env`. For a fresh checkout, create `.env` with `SARVAM_API_KEY=your-key` or export that environment variable. An existing environment variable takes precedence. The backend reads it; the browser never receives it. `.env` is ignored and has owner-only file permissions. There is no dotenv dependency.

## First working call

```sh
.venv/bin/python first_call.py
```

The script sends a 123-character Hindi sample using `bulbul:v4-flash`, `anand_hi_documentary`, 1× pace, and 24 kHz WAV. Its result is saved to `audio/hindi_sample.wav`. Subsequent runs reuse this file without another API request. The reader imports the same sample into its cache automatically.

Initial verified result: **8.56 seconds, 410,924 bytes, estimated ₹0.123 before GST**. An additional **135-character English sample** was generated successfully through the browser with `aparna_en_edtech`. Development used **two live requests**, with total submitted text of **258 characters** and estimated cost of **₹0.258 before GST**. These are local estimates, not verified Sarvam billed usage or account balance. The supplied starting balance was 95 credits.

## Credit-conscious behavior

- Generation happens only after pressing Generate. Typing, changing settings, loading samples, opening the page, and replaying never call Sarvam.
- An identical normalized text, language, model, voice, pace, output format, and sample rate reuse the saved WAV. Concurrent duplicate requests are serialized and pay only once within a running server.
- All Sarvam calls set `max_retries=0`; HTTP transport retries are not enabled. Authentication, credit, model-access, and rate-limit errors pause further generation in that running server. Fix the underlying issue and restart deliberately.
- Cost previews use the published pay-as-you-go rate of ₹1 per 1,000 characters, excluding GST, checked 26 October 2026. They do not query billing or claim a remaining balance. Failed requests are included conservatively in the local submitted-cost estimate.
- Development mode: `.venv/bin/python server.py --development`. It enforces at most three development requests across the recorded first call and server calls, with at most 200 characters per new request. Cache hits still work. Use normal mode for your own longer study notes.

## Local storage and privacy

Only `static/index.html`, `static/styles.css`, `static/app.js`, `static/favicon.svg`, public API responses, and explicitly addressed generated WAVs are served. The server binds only to 127.0.0.1, checks the request host/origin, and does not log notes or request bodies. It is a local development app, not a publicly deployed service.

The current draft is saved in this browser's local storage. Recordings and their note text are stored under ignored `audio/` and `.cache/` directories on this computer. Only text explicitly generated is sent to Sarvam. Other people using this computer/browser profile may be able to access these local drafts and files.

There are no accounts, payments, database, OCR, translation, cloning, or hosting services. Fine-tuning is deferred; no training jobs or training-related charges have been created.

## Offline checks

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The suite uses mocked Sarvam responses, temporary directories, and a temporary loopback HTTP server. It spends no API credits. It covers caching across restarts, concurrent duplicates, parameter changes, invalid input, development limits, provider failures, WAV validity, first-call reuse, file access restrictions, cross-origin protection, audio seeking/downloads, and actual local HTTP routing.

## API references

- [Welcome and quickstart](https://docs.sarvam.ai/api/getting-started/welcome)
- [TTS endpoint, model, and parameter contract](https://docs.sarvam.ai/api-reference/text-to-speech/convert)
- [Compatible voice catalog](https://docs.sarvam.ai/api/api-guides-tutorials/text-to-speech/voices)
- [Pricing](https://docs.sarvam.ai/api/getting-started/pricing)

The direct dependencies are `sarvamai` and `streamlit`. The SDK's HTTPX dependency closes each request's connection cleanly. The original custom frontend has no packages or build step; Streamlit supplies the deployable Study Lab interface and its own dependencies.
