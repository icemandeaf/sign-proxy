# Vercel Python serverless function: POST /api/embed
# Body: {"pose": ["<base64 .pose>"], "model_name": "default"}
# Returns: upstream JSON (usually includes "embeddings")
from http.server import BaseHTTPRequestHandler
import json, requests

UPSTREAM_URL = "https://pub.cl.uzh.ch/demo/sign_clip/pose"

def _cors(h):
    h["Access-Control-Allow-Origin"] = "*"
    h["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    h["Access-Control-Allow-Headers"] = "Content-Type"

def _bad(self, code, msg):
    body = json.dumps({"error": msg}).encode("utf-8")
    self.send_response(code)
    hdrs = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body)),
    }
    _cors(hdrs)
    for k,v in hdrs.items(): self.send_header(k,v)
    self.end_headers()
    self.wfile.write(body)

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        hdrs = {}
        _cors(hdrs)
        for k,v in hdrs.items(): self.send_header(k,v)
        self.end_headers()

    def do_POST(self):
        # Route is /api/embed by file name; but we guard anyway
        if not self.path.endswith("/api/embed"):
            return _bad(self, 404, "Use POST /api/embed")

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return _bad(self, 400, "Invalid JSON body")

        pose = (body.get("pose") or [])
        if not isinstance(pose, list) or not pose or not isinstance(pose[0], str):
            return _bad(self, 400, "Expected { pose:[<base64>], model_name? }")

        payload = {
            "pose": pose,
            "model_name": body.get("model_name", "default")
        }

        # Try GET-with-body first (matches their demo); fallback to POST on 405
        headers = {"Content-Type": "application/json"}
        data = json.dumps(payload)
        try:
            r = requests.request("GET", UPSTREAM_URL, headers=headers, data=data, timeout=60)
            if r.status_code == 405:
                r = requests.request("POST", UPSTREAM_URL, headers=headers, data=data, timeout=60)
        except Exception as e:
            return _bad(self, 502, f"Upstream fetch failed: {e}")

        # Relay upstream response (status + content-type + body) + CORS
        content_type = r.headers.get("content-type", "application/json")
        out = r.content
        self.send_response(r.status_code)
        hdrs = {"Content-Type": content_type, "Content-Length": str(len(out))}
        _cors(hdrs)
        for k,v in hdrs.items(): self.send_header(k,v)
        self.end_headers()
        self.wfile.write(out)
