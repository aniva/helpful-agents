import http.server
import socketserver
import json
import os
import sys
import urllib.parse
import webbrowser
import threading
import subprocess

from detector import detect_gopro, suggest_destination, to_local_path, is_windows
from extractor import scan_and_extract_timeline
from cutter import cut_attempts, sync_cuts_file
from stitcher import stitch_highlights

DEFAULT_PORT = 8765
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "web")

# Live progress state tracked across operations
progress_state = {
    "active": False,
    "percent": 0,
    "title": "",
    "message": "",
    "details": ""
}

def report_progress(percent, message=None, details=None, title=None, active=True):
    progress_state["active"] = active
    progress_state["percent"] = min(100, max(0, int(percent)))
    if title: progress_state["title"] = title
    if message: progress_state["message"] = message
    if details: progress_state["details"] = details

class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

class AppHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/api/progress":
            self.send_json(progress_state)
            return

        elif path == "/api/detect_sd":
            detected = detect_gopro()
            suggested_src = detected[0] if detected else ""
            suggested_dst = suggest_destination(suggested_src)
            self.send_json({
                "detectedSources": detected,
                "suggestedSource": suggested_src,
                "suggestedDestination": suggested_dst
            })
            return

        elif path == "/api/thumbnail":
            dest_dir = query.get("dest", [""])[0]
            rel_path = query.get("path", [""])[0]
            full_path = os.path.join(to_local_path(dest_dir), rel_path.replace("/", os.sep))

            if os.path.exists(full_path):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(full_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
            return

        elif path == "/api/load_state":
            dest_dir = to_local_path(query.get("dest", [""])[0])
            state_file = os.path.join(dest_dir, "session_state.json")
            if os.path.exists(state_file):
                with open(state_file, "r", encoding="utf-8") as f:
                    self.send_json(json.load(f))
            else:
                self.send_json({"cuts": []})
            return

        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        content_len = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_len) if content_len > 0 else b"{}"
        try:
            data = json.loads(body.decode('utf-8'))
        except Exception:
            data = {}

        if path == "/api/scan":
            src = to_local_path(data.get("sourceDir", ""))
            dst = to_local_path(data.get("destDir", ""))
            interval = float(data.get("interval", 4.0))

            if not os.path.exists(src):
                self.send_json({"error": f"Source directory not found: {src}"}, status=400)
                return

            report_progress(0, "Starting scan...", "Initializing thumbnail extraction...", title="Scanning GoPro Footage", active=True)
            manifest = scan_and_extract_timeline(
                src, dst, interval,
                progress_callback=lambda p, m, d: report_progress(p, m, d, title="Scanning GoPro Footage")
            )
            report_progress(100, "Done!", "Timeline ready.", active=False)
            
            state_file = os.path.join(dst, "session_state.json")
            existing_cuts = []
            if os.path.exists(state_file):
                try:
                    with open(state_file, "r", encoding="utf-8") as sf:
                        sdata = json.load(sf)
                        existing_cuts = sdata.get("cuts", [])
                except Exception:
                    pass
            manifest["savedCuts"] = existing_cuts

            self.send_json(manifest)
            return

        elif path == "/api/sync_cuts":
            dst = to_local_path(data.get("destDir", ""))
            cuts = data.get("cuts", [])
            state = {
                "sourceDir": data.get("sourceDir", ""),
                "destDir": dst,
                "interval": data.get("interval", 4.0),
                "cuts": cuts
            }
            os.makedirs(dst, exist_ok=True)
            with open(os.path.join(dst, "session_state.json"), "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            sync_cuts_file(dst, cuts)
            self.send_json({"status": "ok", "count": len(cuts)})
            return

        elif path == "/api/process":
            action = data.get("action", "cut")
            src = to_local_path(data.get("sourceDir", ""))
            dst = to_local_path(data.get("destDir", ""))
            cuts = data.get("cuts", [])

            sync_cuts_file(dst, cuts)

            cut_results = []
            stitch_result = None

            if action in ["cut", "cut_and_stitch"]:
                report_progress(0, "Starting cut...", "Preparing GPU NVENC...", title="Cutting Attempts", active=True)
                
                def cut_prog(idx, total, msg):
                    pct = int(((idx - 1) / max(1, total)) * (60 if action == "cut_and_stitch" else 100))
                    report_progress(pct, f"Cutting Attempt {idx}/{total}", msg)

                cut_results = cut_attempts(src, dst, cuts, progress_callback=cut_prog)

            if action in ["stitch", "cut_and_stitch"]:
                report_progress(60 if action == "cut_and_stitch" else 0, "Applying transitions...", "Dip-fades in progress...", title="Stitching Highlights", active=True)
                attempt_files = [r["path"] for r in cut_results if r.get("status") == "success"] if cut_results else None

                def stitch_prog(idx, total, msg):
                    base_pct = 60 if action == "cut_and_stitch" else 0
                    span = 35 if action == "cut_and_stitch" else 85
                    pct = base_pct + int((idx / max(1, total)) * span)
                    report_progress(pct, f"Transition {idx}/{total}", msg)

                stitch_result = stitch_highlights(dst, attempt_files=attempt_files, progress_callback=stitch_prog)

            report_progress(100, "Finished!", "All tasks completed.", active=False)

            self.send_json({
                "status": "ok",
                "action": action,
                "cutResults": cut_results,
                "stitchResult": stitch_result
            })
            return

        elif path == "/api/open_folder":
            folder = to_local_path(data.get("path", ""))
            if os.path.exists(folder):
                if is_windows():
                    os.startfile(folder)
                else:
                    subprocess.run(["explorer.exe", folder.replace("/mnt/c", "C:").replace("/mnt/e", "E:").replace("/", "\\")])
            self.send_json({"status": "ok"})
            return

        self.send_response(404)
        self.end_headers()

    def send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

def start_server(port=DEFAULT_PORT):
    actual_port = port
    while actual_port < port + 20:
        try:
            httpd = ThreadedHTTPServer(("", actual_port), AppHandler)
            break
        except OSError:
            actual_port += 1

    url = f"http://localhost:{actual_port}"
    print(f"\n[GoPro Pump Foil Attempts Extractor v1]")
    print(f"Threaded server started at: {url}")
    print(f"Press Ctrl+C to stop.\n")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")

if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    start_server(p)