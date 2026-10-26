"""Offline integration checks. No Sarvam API requests are made by this suite."""

import base64
from concurrent.futures import ThreadPoolExecutor
import http.client
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import wave

from reader import Reader, ReaderError, SAMPLES, audio_info, validate
from server import make_server


def wav_bytes():
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(b"\x00\x01\x00\xff" * 2400)
    return output.getvalue()


class ReaderTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.audio = wav_bytes()
        self.convert = Mock(return_value=SimpleNamespace(audios=[base64.b64encode(self.audio).decode()], request_id="offline-test"))
        self.client = SimpleNamespace(text_to_speech=SimpleNamespace(convert=self.convert))
        self.factory = Mock(return_value=self.client)
        self.reader = Reader(self.root, client_factory=self.factory)
        self.options = {"text": SAMPLES["hi-IN"], "language": "hi-IN", "speaker": "anand_hi_documentary", "pace": 1}

    def tearDown(self):
        self.directory.cleanup()

    def test_cache_survives_restart_and_does_not_repeat_charge(self):
        first = self.reader.generate(self.options, development=True)
        restarted = Reader(self.root, client_factory=self.factory)
        second = restarted.generate({**self.options, "text": "  " + self.options["text"] + "  "}, development=True)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(second["generation_estimate_inr"], 0)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(self.convert.call_count, 1)
        self.assertEqual(restarted.usage()["live_requests"], 1)
        self.assertEqual(self.convert.call_args.kwargs["request_options"], {"max_retries": 0})

    def test_concurrent_duplicates_call_provider_once(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.reader.generate(self.options), range(6)))
        self.assertEqual(self.convert.call_count, 1)
        self.assertEqual(sum(not item["cached"] for item in results), 1)

    def test_voice_and_speed_changes_make_distinct_recordings(self):
        first = self.reader.generate(self.options)
        second = self.reader.generate({**self.options, "pace": 0.75})
        third = self.reader.generate({**self.options, "speaker": "ishita_hi_edtech"})
        self.assertEqual(len({item["id"] for item in (first, second, third)}), 3)
        self.assertEqual(self.convert.call_count, 3)

    def test_invalid_inputs_never_reach_provider(self):
        invalid = [None, [], {"text": "   "}, {"text": "a" * 2001},
                   {**self.options, "language": []}, {**self.options, "speaker": "aparna_en_edtech"},
                   {**self.options, "pace": True}, {**self.options, "pace": float("nan")},
                   {**self.options, "pace": float("inf")}, {**self.options, "pace": 2.1},
                   {**self.options, "text": "hello\x00world"}]
        for payload in invalid:
            with self.subTest(payload=type(payload).__name__):
                with self.assertRaises(ReaderError):
                    self.reader.generate(payload)
        self.factory.assert_not_called()

    def test_unicode_character_boundary_and_minimum_speed(self):
        result = validate({**self.options, "text": "अ" * 2000, "pace": 0.5})
        self.assertEqual(len(result["text"]), 2000)
        self.assertEqual(result["pace"], 0.5)

    def test_development_limits_count_first_call_and_allow_cache(self):
        (self.root / ".cache" / "first_call_attempts.json").write_text("1")
        self.reader.generate(self.options, development=True)
        self.reader.generate({**self.options, "text": "A second short test."}, development=True)
        with self.assertRaises(ReaderError):
            self.reader.generate({**self.options, "text": "A third new test."}, development=True)
        with self.assertRaises(ReaderError):
            self.reader.generate({**self.options, "text": "a" * 201}, development=True)
        self.assertTrue(self.reader.generate(self.options, development=True)["cached"])
        self.assertEqual(self.convert.call_count, 2)

    def test_auth_failure_pauses_further_requests_and_hides_provider_body(self):
        class AuthError(Exception):
            status_code = 403
        self.convert.side_effect = AuthError("PRIVATE_PROVIDER_RESPONSE")
        for _ in range(2):
            with self.assertRaises(ReaderError) as caught:
                self.reader.generate(self.options)
            self.assertNotIn("PRIVATE_PROVIDER_RESPONSE", str(caught.exception))
        self.assertEqual(self.convert.call_count, 1)

    def test_invalid_audio_is_not_cached_or_presented_as_success(self):
        self.convert.return_value.audios = [base64.b64encode(b"not-a-wav").decode()]
        with self.assertRaises(ReaderError):
            self.reader.generate(self.options)
        self.assertEqual(self.reader.recent(), [])
        self.assertFalse(list((self.root / "audio").glob("*.wav")))

    def test_truncated_wav_is_rejected(self):
        with self.assertRaises(ReaderError):
            audio_info(self.audio[:-100])

    def test_import_first_call_without_another_provider_request(self):
        (self.root / "audio" / "hindi_sample.wav").write_bytes(self.audio)
        (self.root / ".cache" / "first_call.json").write_text(json.dumps({**self.options, "model": "bulbul:v4-flash"}))
        restarted = Reader(self.root, client_factory=self.factory)
        self.assertTrue(restarted.generate(self.options, development=True)["cached"])
        self.convert.assert_not_called()


class HTTPTests(unittest.TestCase):
    def setUp(self):
        ReaderTests.setUp(self)
        self.recording = self.reader.generate(self.options)
        self.app = make_server(0, reader=self.reader)
        self.thread = threading.Thread(target=self.app.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.app.shutdown()
        self.app.server_close()
        self.thread.join()
        ReaderTests.tearDown(self)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.app.server_port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_only_public_files_are_served(self):
        for path in ("/.env", "/reader.py", "/.cache/first_call.json", "/requirements.txt", "/../.env"):
            self.assertEqual(self.request("GET", path)[0], 404)
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Suno", body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_audio_download_and_seek_ranges(self):
        url = self.recording["audio_url"]
        status, headers, body = self.request("GET", url, headers={"Range": "bytes=0-43"})
        self.assertEqual(status, 206)
        self.assertEqual(body, self.audio[:44])
        self.assertEqual(headers["Content-Range"], f"bytes 0-43/{len(self.audio)}")
        self.assertEqual(self.request("GET", url, headers={"Range": "bytes=999999-"})[0], 416)
        self.assertEqual(self.request("GET", url, headers={"Range": "bytes=-0"})[0], 416)
        status, headers, body = self.request("GET", self.recording["download_url"])
        self.assertEqual(status, 200)
        self.assertTrue(headers["Content-Disposition"].startswith("attachment;"))
        self.assertEqual(body, self.audio)

    def test_other_websites_cannot_trigger_generation(self):
        calls = self.convert.call_count
        body = json.dumps(self.options)
        status, _, _ = self.request("POST", "/api/generate", body, {"Content-Type": "application/json", "Origin": "https://other-site.example"})
        self.assertEqual(status, 403)
        self.assertEqual(self.request("GET", "/api/config", headers={"Host": "other-site.example"})[0], 403)
        self.assertEqual(self.convert.call_count, calls)

    def test_cached_request_works_through_the_real_http_server(self):
        status, _, body = self.request("POST", "/api/generate", json.dumps(self.options), {"Content-Type": "application/json"})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["recording"]["cached"])
        self.assertEqual(self.convert.call_count, 1)

    def test_bad_json_and_large_requests_fail_without_generation(self):
        calls = self.convert.call_count
        self.assertEqual(self.request("POST", "/api/generate", "{", {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.request("POST", "/api/generate", "x" * 16001, {"Content-Type": "application/json"})[0], 413)
        self.assertEqual(self.request("POST", "/api/generate", "{}", {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.convert.call_count, calls)


if __name__ == "__main__":
    unittest.main()
