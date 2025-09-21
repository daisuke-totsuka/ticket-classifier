from http.server import BaseHTTPRequestHandler
import json, os

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # ここがランタイムログに出る
        print("health hit; has_key=", "GEMINI_API_KEY" in os.environ)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status":"ok"}).encode())
