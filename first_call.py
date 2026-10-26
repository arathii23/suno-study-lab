"""Make one small Sarvam TTS request; reruns reuse the saved audio."""

import base64
import io
import json
import os
from pathlib import Path
import wave

import httpx
from sarvamai import SarvamAI

ROOT = Path(__file__).resolve().parent
TEXT = "प्रकाश संश्लेषण में पौधे सूर्य के प्रकाश से अपना भोजन बनाते हैं। इस प्रक्रिया में जल और कार्बन डाइऑक्साइड का उपयोग होता है।"
MODEL = "bulbul:v4-flash"
SPEAKER = "anand_hi_documentary"
OUTPUT = ROOT / "audio" / "hindi_sample.wav"
RECORD = ROOT / ".cache" / "first_call.json"


def main():
    if OUTPUT.exists() and RECORD.exists():
        print("Reusing the saved first-call audio. No API request sent.")
        print(OUTPUT)
        return
    for line in (ROOT / ".env").read_text().splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "SARVAM_API_KEY":
            os.environ.setdefault(name.strip(), value.strip().strip("\"'"))
    if not os.environ.get("SARVAM_API_KEY"):
        raise SystemExit("Missing SARVAM_API_KEY in the environment or .env.")
    assert 0 < len(TEXT) <= 200
    RECORD.parent.mkdir(exist_ok=True)
    attempt_file = RECORD.parent / "first_call_attempts.json"
    attempts = json.loads(attempt_file.read_text()) if attempt_file.exists() else 0
    requests = RECORD.parent / "requests.jsonl"
    server_attempts = sum(bool(json.loads(line).get("development")) for line in requests.read_text().splitlines()) if requests.exists() else 0
    if attempts + server_attempts >= 3:
        raise SystemExit("Development request limit reached. No request sent.")
    attempt_file.write_text(json.dumps(attempts + 1))
    try:
        with httpx.Client(timeout=60, follow_redirects=False) as transport:
            client = SarvamAI(api_subscription_key=os.environ["SARVAM_API_KEY"], timeout=60, httpx_client=transport)
            response = client.text_to_speech.convert(
                text=TEXT, language_code="hi-IN", model=MODEL, speaker=SPEAKER,
                pace=1.0, speech_sample_rate=24000, output_audio_codec="wav",
                request_options={"max_retries": 0},
            )
    except Exception as error:
        status = getattr(error, "status_code", None)
        raise SystemExit(f"Sarvam request failed ({status or type(error).__name__}). No automatic retry.") from None
    audio = base64.b64decode(response.audios[0], validate=True)
    with wave.open(io.BytesIO(audio), "rb") as wav:
        frames, rate = wav.getnframes(), wav.getframerate()
        if frames <= 0 or not wav.readframes(frames):
            raise SystemExit("Sarvam returned empty audio.")
    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_bytes(audio)
    result = {"model": MODEL, "speaker": SPEAKER, "language": "hi-IN", "pace": 1.0,
              "text": TEXT, "characters": len(TEXT), "seconds": round(frames / rate, 2),
              "bytes": len(audio), "estimated_cost_inr": len(TEXT) / 1000,
              "request_id": response.request_id}
    RECORD.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({key: value for key, value in result.items() if key != "text"}, indent=2))
    print(f"Saved valid WAV: {OUTPUT}")
    print("Cost is an estimate before GST; account usage/balance has not been queried.")


if __name__ == "__main__":
    main()
