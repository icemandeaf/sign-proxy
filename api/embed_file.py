# Vercel serverless function: POST /api/embed_file
# Form fields:
#   - file:       the uploaded .pose file (pose-format, MediaPipe layout)
#   - model_name: optional (default "default")
#
# Returns: upstream JSON from UZH (typically includes "embeddings")

from http.server import BaseHTTPRequestHandler
import json, http.client, base64, cgi

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
    """Try GET-with-body first (mirrors UZH demo). If 405, retry POST."""
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
        # 2) fallback: POST
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
        for k, v in h.items():
            self.send_header(k, v)
        self.end_headers()

    def do_POST(self):
        # This file maps to /api/embed_file; keep a guard just in case
        if not self.path.endswith("/api/embed_file"):
            return _bad(self, 404, "Use POST /api/embed_file")

        ctype = self.headers.get("Content-Type") or ""
        if "multipart/form-data" not in ctype:
            return _bad(self, 400, "Content-Type must be multipart/form-data")

        # Parse multipart form (standard library)
        try:
            fs = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": ctype,
                    "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                },
                keep_blank_values=True,
            )
        except Exception:
            return _bad(self, 400, "Failed to parse multipart form")

        if "file" not in fs:
            return _bad(self, 400, "Missing 'file' field (upload a .pose file)")

        file_item = fs["file"]
        try:
            pose_bytes = file_item.file.read()
        except Exception:
            return _bad(self, 400, "Could not read uploaded file")

        model_name = fs.getvalue("model_name") or "default"

        # Base64-encode the .pose, call upstream
        try:
            b64 = base64.b64encode(pose_bytes).decode("ascii")
            payload = {"pose": [b64], "model_name": model_name}
            status, ct, out = _call_upstream(payload)
            _send(self, status, out, content_type=ct)
        except Exception as e:
            _bad(self, 502, f"Upstream fetch failed: {e}")
