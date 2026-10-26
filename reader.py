"""Sarvam narration, input validation, and a local file cache."""

import array
import base64
from contextlib import contextmanager
import hashlib
import io
import json
import math
import os
from pathlib import Path
import shutil
import sys
import threading
from datetime import datetime, timezone
import wave

import httpx
from sarvamai import SarvamAI

ROOT = Path(__file__).resolve().parent
MODEL = "bulbul:v4-flash"
MAX_CHARACTERS = 2000
RATE_PER_1000 = 1.0  # INR, pay-as-you-go, before GST; checked 2026-10-26.
SAMPLE_RATE = 24000
VOICES = {
    "hi-IN": [
        {"id": "anand_hi_documentary", "name": "Anand", "style": "Clear, unhurried narration"},
        {"id": "ishita_hi_edtech", "name": "Ishita", "style": "For lessons and study notes"},
        {"id": "roopa_hi_narration", "name": "Roopa", "style": "Natural Hindi narration"},
    ],
    "en-IN": [
        {"id": "aparna_en_edtech", "name": "Aparna", "style": "Engaging, measured learning voice"},
        {"id": "shubh_en_narration_gentle", "name": "Shubh", "style": "Gentle, relaxed narration"},
        {"id": "simran_en_narration", "name": "Simran", "style": "Natural English narration"},
    ],
}
SAMPLES = {
    "hi-IN": "प्रकाश संश्लेषण में पौधे सूर्य के प्रकाश से अपना भोजन बनाते हैं। इस प्रक्रिया में जल और कार्बन डाइऑक्साइड का उपयोग होता है।",
    "en-IN": "Photosynthesis is how plants turn sunlight into food. They use water and carbon dioxide to make glucose, releasing oxygen into the air.",
}


class ReaderError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def load_environment():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, separator, value = line.partition("=")
            if separator and name.strip() == "SARVAM_API_KEY":
                os.environ.setdefault("SARVAM_API_KEY", value.strip().strip("\"'"))


def validate(payload):
    if not isinstance(payload, dict):
        raise ReaderError("Send an object containing your notes and reading options.")
    text = payload.get("text", "")
    if not isinstance(text, str) or not text.strip():
        raise ReaderError("Add some notes before generating audio.")
    text = text.strip()
    if len(text) > MAX_CHARACTERS:
        raise ReaderError("Keep your notes within 2,000 characters for one recording.")
    if any(ord(char) < 32 and char not in "\n\r\t" for char in text):
        raise ReaderError("Your notes contain unsupported control characters.")
    language = payload.get("language", "hi-IN")
    if not isinstance(language, str) or language not in VOICES:
        raise ReaderError("Choose Hindi or English.")
    speaker = payload.get("speaker", VOICES[language][0]["id"])
    if speaker not in [voice["id"] for voice in VOICES[language]]:
        raise ReaderError("Choose a narrator available for the selected language.")
    pace = payload.get("pace", 1.0)
    if isinstance(pace, bool) or not isinstance(pace, (float, int)) or not math.isfinite(pace) or not 0.5 <= pace <= 2.0:
        raise ReaderError("Reading speed must be between 0.5× and 2×.")
    return {"text": text, "language": language, "speaker": speaker, "pace": round(float(pace), 2)}


def cache_key(options):
    identity = {**options, "model": MODEL, "codec": "wav", "sample_rate": SAMPLE_RATE}
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def audio_info(data):
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            frames, rate, width = wav.getnframes(), wav.getframerate(), wav.getsampwidth()
            channels = wav.getnchannels()
            pcm = wav.readframes(frames)
            if frames <= 0 or rate <= 0 or len(pcm) != frames * width * channels:
                raise ValueError("Empty or truncated WAV")
            peaks = []
            if width == 2:
                samples = array.array("h", pcm)
                if sys.byteorder != "little":
                    samples.byteswap()
                window = max(1, len(samples) // 80)
                for index in range(80):
                    section = samples[index * window:(index + 1) * window]
                    peaks.append(max((abs(value) for value in section), default=0))
                maximum = max(peaks) or 1
                peaks = [round(value / maximum, 3) for value in peaks]
            return {"seconds": round(frames / rate, 3), "bytes": len(data), "peaks": peaks}
    except (wave.Error, EOFError, ValueError, ZeroDivisionError):
        raise ReaderError("The audio was incomplete. No recording was saved. Try again when ready.", 502) from None


class Reader:
    def __init__(self, root=ROOT, client_factory=None):
        self.root = Path(root)
        self.cache = self.root / ".cache"
        self.audio = self.root / "audio"
        self.cache.mkdir(exist_ok=True)
        self.audio.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.client_factory = client_factory
        self.blocked = None
        self._import_first_call()

    @contextmanager
    def _client(self):
        if self.client_factory:
            yield self.client_factory()
            return
        load_environment()
        key = os.environ.get("SARVAM_API_KEY")
        if not key:
            raise ReaderError("Add your Sarvam API key to .env, then restart the reader.", 503)
        with httpx.Client(timeout=60, follow_redirects=False) as transport:
            yield SarvamAI(api_subscription_key=key, timeout=60, httpx_client=transport)

    def _import_first_call(self):
        source = self.audio / "hindi_sample.wav"
        record = self.cache / "first_call.json"
        if not source.exists() or not record.exists():
            return
        try:
            first = json.loads(record.read_text())
            if first["model"] != MODEL:
                return
            options = validate({key: first[key] for key in ("text", "language", "speaker", "pace")})
            identity = cache_key(options)
            destination = self.audio / f"{identity}.wav"
            if (self.cache / f"{identity}.json").exists() and destination.exists():
                return
            info = audio_info(source.read_bytes())
            shutil.copyfile(source, destination)
            self._write_record(identity, options, info, first.get("request_id"))
        except (ValueError, KeyError, OSError, ReaderError):
            return

    def _write_record(self, identity, options, info, request_id):
        record = {**options, **info, "id": identity, "model": MODEL, "request_id": request_id,
                  "created_at": datetime.now(timezone.utc).isoformat(),
                  "characters": len(options["text"]),
                  "estimated_cost_inr": round(len(options["text"]) / 1000 * RATE_PER_1000, 4)}
        path = self.cache / f"{identity}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
        return record

    def _cached(self, identity):
        path = self.cache / f"{identity}.json"
        audio = self.audio / f"{identity}.wav"
        if not path.exists() or not audio.exists():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if record["bytes"] != audio.stat().st_size:
                return None
            return record
        except (ValueError, KeyError, OSError):
            return None

    @staticmethod
    def public(record, cached):
        return {**record, "cached": cached, "audio_url": f"/audio/{record['id']}.wav",
                "download_url": f"/audio/{record['id']}.wav?download=1",
                "generation_estimate_inr": 0 if cached else record["estimated_cost_inr"]}

    def recent(self):
        items = []
        for path in self.cache.glob("*.json"):
            if len(path.stem) != 64:
                continue
            record = self._cached(path.stem)
            if record:
                items.append(self.public(record, True))
        return sorted(items, key=lambda item: item["created_at"], reverse=True)[:10]

    def usage(self):
        attempts = self.cache / "requests.jsonl"
        events = []
        if attempts.exists():
            for line in attempts.read_text().splitlines():
                try:
                    events.append(json.loads(line))
                except ValueError:
                    continue
        first = self.cache / "first_call_attempts.json"
        count = int(json.loads(first.read_text())) if first.exists() else 0
        first_record = self.cache / "first_call.json"
        first_cost = json.loads(first_record.read_text()).get("estimated_cost_inr", 0) if first_record.exists() else 0
        return {"live_requests": count + len(events),
                "development_requests": count + sum(event["development"] for event in events),
                "estimated_submitted_cost_inr": round(first_cost + sum(event["estimated_cost_inr"] for event in events), 4),
                "balance_verified": False}

    def config(self):
        return {"model": MODEL, "max_characters": MAX_CHARACTERS, "voices": VOICES,
                "samples": SAMPLES, "rate_per_1000_inr": RATE_PER_1000,
                "pricing_checked": "2026-10-26", "recent": self.recent(), "usage": self.usage()}

    def generate(self, payload, development=False):
        options = validate(payload)
        identity = cache_key(options)
        # Serialize cache misses: concurrent duplicate requests pay only once.
        with self.lock:
            existing = self._cached(identity)
            if existing:
                return self.public(existing, True)
            if self.blocked:
                raise ReaderError(self.blocked, 503)
            if development and (len(options["text"]) > 200 or self.usage()["development_requests"] >= 3):
                raise ReaderError("Development limit reached. No request sent.", 409)
            with self._client() as client:
                event = {"characters": len(options["text"]), "development": development,
                         "estimated_cost_inr": round(len(options["text"]) / 1000 * RATE_PER_1000, 4),
                         "time": datetime.now(timezone.utc).isoformat()}
                with (self.cache / "requests.jsonl").open("a", encoding="utf-8") as file:
                    file.write(json.dumps(event) + "\n")
                try:
                    response = client.text_to_speech.convert(
                        text=options["text"], language_code=options["language"], speaker=options["speaker"],
                        pace=options["pace"], model=MODEL, speech_sample_rate=SAMPLE_RATE,
                        output_audio_codec="wav", request_options={"max_retries": 0},
                    )
                except Exception as error:
                    status = getattr(error, "status_code", None)
                    if status in (402, 403, 404):
                        self.blocked = "Generation is paused. Check your Sarvam key, credits, and model access, then restart the reader."
                        raise ReaderError(self.blocked, 503) from None
                    if status == 429:
                        self.blocked = "Generation is paused after a rate or credit limit. Check your Sarvam dashboard, then restart when ready. No retry was sent."
                        raise ReaderError(self.blocked, 429) from None
                    if status in (400, 422):
                        raise ReaderError("Sarvam could not accept these reading options. Check the language and narrator. No retry was sent.", 502) from None
                    raise ReaderError("Sarvam could not finish this request. Check your connection and try again when ready. No retry was sent.", 502) from None
            try:
                data = base64.b64decode(response.audios[0], validate=True)
            except (ValueError, IndexError, TypeError):
                raise ReaderError("Sarvam returned unreadable audio. No recording was saved.", 502) from None
            info = audio_info(data)
            path = self.audio / f"{identity}.wav"
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(data)
            temporary.replace(path)
            record = self._write_record(identity, options, info, getattr(response, "request_id", None))
            return self.public(record, False)
