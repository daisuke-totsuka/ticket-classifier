import os, json
from http.server import BaseHTTPRequestHandler
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-1.5-flash")

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            n = int(self.headers.get("content-length", 0))
            body = self.rfile.read(n) if n > 0 else b"{}"
            data = json.loads(body)
            prompt = (data.get("prompt") or "").strip()
            if not prompt:
                self.send_response(400); self.end_headers(); return
            resp = model.generate_content(prompt)
            text = resp.text or ""
            out = json.dumps({"text": text}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())
