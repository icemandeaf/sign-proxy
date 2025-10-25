# Vercel Python serverless function: POST /api/embed
# Body: {"pose": ["<base64 .pose>"], "model_name": "default"}
# Returns: upstream response from UZH (JSON with "embeddings" on success)

from http.server import BaseHTTPRequestHandler
import json, http.client

UP_HOST = "pub.cl.uzh.ch"
UP_PATH = "/demo/sign_clip/pose"

def _cors(h):
    h["Access-Control-Allow-Origin"] = "*"
    h["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    h["Access-Control-Allow-Headers"] = "Content-Type"

def _send(self, code, body_bytes, extra_headers=None, content_type="application/json"):
    self.send_response(code)
    hdrs = {
        "Content-Type": content_type,
        "Content-Length": str(len(body_bytes)),
    }
    if extra_headers:
        hdrs.update(extra_headers)
    _cors(hdrs)
    for k, v in hdrs.items():
        self.send_header(k, v)
    self.end_headers()
    self.wfile.write(body_bytes)

def _bad(self, code, msg):
    _send(self, code, json.dumps({"error": msg}).encode("utf-8"))

def _call_upstream(payload: dict):
    """Try GET-with-body (what UZH demo expects). If 405, retry POST."""
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}

    # 1) GET with body
    conn = http.client.HTTPSConnection(UP_HOST, timeout=60)
    conn.request("GET", UP_PATH, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    ct = resp.getheader("Content-Type") or "application/json"
    status = resp.status
    conn.close()

    if status == 405:
        # 2) Fallback to POST
        conn = http.client.HTTPSConnection(UP_HOST, timeout=60)
        conn.request("POST", UP_PATH, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        ct = resp.getheader("Content-Type") or "application/json"
        status = resp.status
        conn.close()

    return status, ct, data

class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        h = {}
        _cors(h)
        for k, v in h.items(): self.send_header(k, v)
        self.end_headers()

    def do_POST(self):
        if not self.path.endswith("/api/embed"):
            return _bad(self, 404, "Use POST /api/embed")

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            return _bad(self, 400, "Invalid JSON body")

        pose = body.get("pose")
        if not isinstance(pose, list) or not pose or not isinstance(pose[0], str):
            return _bad(self, 400, "Expected { pose:[<base64>], model_name? }")

        payload = {
            "pose": pose,
            "model_name": body.get("model_name", "default"),
        }

        try:
            status, ct, out = _call_upstream(payload)
            # Relay upstream status/body so you see errors from UZH too (e.g., 4xx/5xx for bad input)
            _send(self, status, out, content_type=ct)
        except Exception as e:
            _bad(self, 502, f"Upstream fetch failed: {e}")
