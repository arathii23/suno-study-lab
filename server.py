"""Local-only web server. Only explicit public files and generated WAVs are served."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from reader import ROOT, Reader, ReaderError

PUBLIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/styles.css": ("styles.css", "text/css; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/favicon.svg": ("favicon.svg", "image/svg+xml")}


class Handler(BaseHTTPRequestHandler):
    server_version = "Suno"

    def log_message(self, format, *args):
        pass  # Do not log request bodies, study notes, or credentials.

    def _trusted(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        return self.headers.get("Host", "") in hosts

    def _headers(self, status, mime, length, extra=None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def _json(self, status, result):
        data = json.dumps(result, ensure_ascii=False).encode()
        self._headers(status, "application/json; charset=utf-8", len(data))
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._trusted():
            return self._json(403, {"error": "Open the reader using its localhost address."})
        url = urlsplit(self.path)
        if url.path == "/api/config":
            return self._json(200, self.server.reader.config())
        if url.path in PUBLIC:
            filename, mime = PUBLIC[url.path]
            return self._file(ROOT / "static" / filename, mime)
        match = re.fullmatch(r"/audio/([a-f0-9]{64})\.wav", url.path)
        if match:
            disposition = "attachment" if url.query == "download=1" else "inline"
            return self._file(self.server.reader.audio / f"{match[1]}.wav", "audio/wav",
                              {"Content-Disposition": f'{disposition}; filename="suno-notes-{match[1][:8]}.wav"'}, ranges=True)
        return self._json(404, {"error": "This page or recording was not found."})

    def _file(self, path, mime, extra=None, ranges=False):
        if not path.is_file():
            return self._json(404, {"error": "This file was not found."})
        total = path.stat().st_size
        start, end, status = 0, total - 1, 200
        extra = dict(extra or {})
        if ranges:
            extra["Accept-Ranges"] = "bytes"
            request_range = self.headers.get("Range")
            if request_range:
                match = re.fullmatch(r"bytes=(\d*)-(\d*)", request_range)
                if not match or not any(match.groups()):
                    self._headers(416, mime, 0, {"Content-Range": f"bytes */{total}"})
                    return
                first, last = match.groups()
                if first:
                    start = int(first)
                    end = min(int(last), total - 1) if last else total - 1
                else:
                    start = max(0, total - int(last))
                if start > end or start >= total:
                    self._headers(416, mime, 0, {"Content-Range": f"bytes */{total}"})
                    return
                extra["Content-Range"] = f"bytes {start}-{end}/{total}"
                status = 206
        self._headers(status, mime, end - start + 1, extra)
        if self.command != "HEAD":
            with path.open("rb") as file:
                file.seek(start)
                self.wfile.write(file.read(end - start + 1))

    def do_POST(self):
        if not self._trusted():
            return self._json(403, {"error": "Unrecognized local address."})
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers['Host']}":
            return self._json(403, {"error": "Requests must come from this reader."})
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            return self._json(403, {"error": "Requests must come from this reader."})
        if self.path != "/api/generate":
            return self._json(404, {"error": "This action was not found."})
        if self.headers.get_content_type() != "application/json":
            return self._json(415, {"error": "Send notes as JSON."})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16000:
                raise ReaderError("The request is empty or too large.", 413)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            result = self.server.reader.generate(payload, development=self.server.development)
            return self._json(200, {"recording": result, "usage": self.server.reader.usage()})
        except (ValueError, UnicodeDecodeError):
            return self._json(400, {"error": "The notes could not be read. Please try again."})
        except ReaderError as error:
            return self._json(error.status, {"error": str(error)})
        except Exception:
            return self._json(500, {"error": "The recording could not be saved. Check available disk space and try again."})


def make_server(port=8000, reader=None, development=False):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.reader = reader or Reader()
    server.development = development
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Suno: turn study notes into audio.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--development", action="store_true", help="Enforce 200 characters and three development API calls; cached audio is unrestricted.")
    args = parser.parse_args()
    app = make_server(args.port, development=args.development)
    print(f"Suno is ready at http://127.0.0.1:{app.server_port}", flush=True)
    print("Development limits enabled." if args.development else "Generate sends notes to Sarvam; replay uses saved audio.", flush=True)
    try:
        app.serve_forever()
    except KeyboardInterrupt:
        print("\nReader stopped.")
    finally:
        app.server_close()
