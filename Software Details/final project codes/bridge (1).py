import http.server
import urllib.request
import urllib.error
import json
import os
import sys
import threading
import time

# ============================================================
#  CONFIGURATION
# ============================================================

# Floor ESP32 — WiFi access point, always at this IP
FLOOR_IP   = "192.168.4.1"
FLOOR_PORT = 80

# Ceiling ESP32 — connects to Floor AP, IP assigned by DHCP
# Typically 192.168.4.2, but we auto-discover to be safe
CEILING_IP   = None   # set by auto-discovery
CEILING_PORT = 80

# Bridge server port (your browser connects here)
BRIDGE_PORT = 8000

# Path to your HTML file
HTML_FILE = "finalwebcode.html"


# ============================================================
#  CEILING AUTO-DISCOVERY
# ============================================================
#
# The ceiling ESP32 gets a DHCP address from the floor AP.
# We scan the small subnet to find it.
#

def discover_ceiling(timeout=1.0):
    """Try common DHCP addresses to find the ceiling ESP32."""
    candidates = [
        "192.168.4.2",
        "192.168.4.3",
        "192.168.4.4",
        "192.168.4.5",
    ]
    for ip in candidates:
        try:
            url = "http://{}:{}/".format(ip, CEILING_PORT)
            req = urllib.request.Request(url)
            req.add_header('Connection', 'close')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode('utf-8', 'ignore')
                if 'CEILING' in body:
                    return ip
        except:
            pass
    return None


def discover_ceiling_loop():
    """Background thread: keep trying until ceiling is found."""
    global CEILING_IP
    while CEILING_IP is None:
        ip = discover_ceiling()
        if ip:
            CEILING_IP = ip
            print("[BRIDGE] Ceiling ESP32 found at {}".format(ip))
        else:
            time.sleep(2)


# ============================================================
#  CACHED CEILING IR STATE
# ============================================================
#
# The bridge polls the ceiling ESP32 for IR sensor triggers
# in a background thread so the main /state response is fast.
#

ceiling_ir = [0, 0]          # latest IR trigger flags
ceiling_lock = threading.Lock()
ceiling_alive = False


def ceiling_poll_loop():
    """Background thread: poll ceiling /ir_state every ~80ms."""
    global ceiling_ir, ceiling_alive
    while True:
        if CEILING_IP is None:
            time.sleep(0.5)
            continue
        try:
            url = "http://{}:{}/ir_state".format(CEILING_IP, CEILING_PORT)
            req = urllib.request.Request(url)
            req.add_header('Connection', 'close')
            with urllib.request.urlopen(req, timeout=1) as resp:
                data = json.loads(resp.read())
                with ceiling_lock:
                    # OR-merge: if either poll caught a trigger, keep it
                    # until the bridge's /state consumer clears it
                    for i in range(2):
                        if data['ir'][i]:
                            ceiling_ir[i] = 1
                    ceiling_alive = True
        except:
            ceiling_alive = False
        time.sleep(0.08)


def pop_ceiling_ir():
    """Read and clear the cached IR trigger flags."""
    with ceiling_lock:
        vals = list(ceiling_ir)
        ceiling_ir[0] = 0
        ceiling_ir[1] = 0
    return vals


# ============================================================
#  HTTP HANDLER
# ============================================================

class BridgeHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        path = self.path.split('?')[0]

        # ── Serve the HTML game ──────────────────────────────
        if path == '/' or path == '/index.html':
            self.serve_html()

        # ── Unified state: 9 floor buttons + 2 ceiling IR ───
        elif path == '/state':
            self.handle_state()

        # ── Floor NeoPixel commands → forward to floor ───────
        elif path in ('/set_tile', '/set_all_tiles', '/set_led',
                       '/clear', '/brightness'):
            self.forward_to_floor()

        # ── Ceiling commands → forward to ceiling ────────────
        elif path in ('/ceiling_state', '/ceiling_event',
                       '/ceiling_speed'):
            self.handle_ceiling_cmd()

        # ── Health / debug ───────────────────────────────────
        elif path == '/status':
            self.handle_status()

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.end_headers()

    # ── Serve HTML ────────────────────────────────────────────

    def serve_html(self):
        try:
            with open(HTML_FILE, 'r', encoding='utf-8') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        except FileNotFoundError:
            self.send_response(500)
            self.end_headers()
            msg = "ERROR: Cannot find '{}'\n".format(HTML_FILE)
            msg += "Make sure bridge.py and your HTML file are in the same folder!"
            self.wfile.write(msg.encode('utf-8'))

    # ── Unified /state ────────────────────────────────────────
    #
    # Returns {"b": [b0..b8, ir_left, ir_right]}
    #   - indices 0–8:  floor grid buttons
    #   - index 9:      ceiling left IR  (BONUS-L)
    #   - index 10:     ceiling right IR (BONUS-R)
    #
    # This keeps the same 11-element array the HTML already
    # expects, so the game code needs zero changes.
    #

    def handle_state(self):
        # 1. Get 9 floor buttons
        floor_buttons = [0] * 9
        try:
            url = "http://{}:{}/state".format(FLOOR_IP, FLOOR_PORT)
            req = urllib.request.Request(url)
            req.add_header('Connection', 'close')
            with urllib.request.urlopen(req, timeout=1) as resp:
                data = json.loads(resp.read())
                floor_buttons = data.get('b', [0]*9)
        except:
            pass

        # 2. Get 2 ceiling IR triggers (from background cache)
        ir = pop_ceiling_ir()

        # 3. Merge into single 11-element array
        merged = floor_buttons + ir
        payload = json.dumps({"b": merged})

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload.encode('utf-8'))

    # ── Forward to floor ESP32 ────────────────────────────────

    def forward_to_floor(self):
        url = "http://{}:{}{}".format(FLOOR_IP, FLOOR_PORT, self.path)
        try:
            req = urllib.request.Request(url)
            req.add_header('Connection', 'close')
            with urllib.request.urlopen(req, timeout=2) as resp:
                body = resp.read()
                ctype = resp.headers.get('Content-Type', 'text/plain')
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
        except urllib.error.URLError as e:
            self.send_error_json(502, "Floor ESP32 not reachable", str(e))
        except Exception as e:
            self.send_error_json(500, "Bridge error", str(e))

    # ── Forward to ceiling ESP32 ──────────────────────────────
    #
    #   /ceiling_state?state=game_ddr   →  ceiling /set_state?state=game_ddr
    #   /ceiling_event?type=wrong       →  ceiling /event?type=wrong
    #   /ceiling_speed?value=1.5        →  ceiling /speed?value=1.5
    #

    def handle_ceiling_cmd(self):
        if CEILING_IP is None:
            self.send_error_json(503, "Ceiling ESP32 not found yet",
                                 "Still scanning...")
            return

        path = self.path.split('?')[0]
        query = self.path.split('?')[1] if '?' in self.path else ''

        # Map bridge routes to ceiling routes
        route_map = {
            '/ceiling_state': '/set_state',
            '/ceiling_event': '/event',
            '/ceiling_speed': '/speed',
        }
        ceiling_path = route_map.get(path, path)
        ceiling_url = "http://{}:{}{}{}{}".format(
            CEILING_IP, CEILING_PORT,
            ceiling_path,
            '?' if query else '',
            query
        )

        try:
            req = urllib.request.Request(ceiling_url)
            req.add_header('Connection', 'close')
            with urllib.request.urlopen(req, timeout=2) as resp:
                body = resp.read()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
        except urllib.error.URLError as e:
            self.send_error_json(502, "Ceiling ESP32 not reachable", str(e))
        except Exception as e:
            self.send_error_json(500, "Bridge error", str(e))

    # ── Status / debug ────────────────────────────────────────

    def handle_status(self):
        status = {
            "floor":   {"ip": FLOOR_IP, "port": FLOOR_PORT},
            "ceiling": {
                "ip":    CEILING_IP or "scanning...",
                "port":  CEILING_PORT,
                "alive": ceiling_alive,
            },
            "bridge_port": BRIDGE_PORT,
        }
        payload = json.dumps(status, indent=2)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(payload.encode('utf-8'))

    # ── Helpers ───────────────────────────────────────────────

    def send_error_json(self, code, error, detail):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        msg = json.dumps({"error": error, "detail": detail})
        self.wfile.write(msg.encode('utf-8'))

    def log_message(self, format, *args):
        msg = format % args
        # Suppress noisy polling logs
        if '/state' not in msg and '/ir_state' not in msg:
            print("[BRIDGE]", msg)


# ============================================================
#  MAIN
# ============================================================

def main():
    if not os.path.exists(HTML_FILE):
        print("=" * 55)
        print("  ERROR: Cannot find '{}'".format(HTML_FILE))
        print()
        print("  Make sure bridge.py and your HTML file")
        print("  are in the SAME folder.")
        print("=" * 55)
        sys.exit(1)

    # Start background threads
    t1 = threading.Thread(target=discover_ceiling_loop, daemon=True)
    t1.start()

    t2 = threading.Thread(target=ceiling_poll_loop, daemon=True)
    t2.start()

    print("=" * 55)
    print("  ARCADE BRIDGE SERVER")
    print("=" * 55)
    print()
    print("  HTML file:       {}".format(HTML_FILE))
    print("  Floor ESP32:     {}:{}".format(FLOOR_IP, FLOOR_PORT))
    print("  Ceiling ESP32:   auto-discovering...")
    print("  Bridge:          http://localhost:{}".format(BRIDGE_PORT))
    print()
    print("  ARCHITECTURE:")
    print("    Browser ←→ Bridge ←→ Floor ESP32  (buttons + LEDs)")
    print("                    ↕")
    print("               Ceiling ESP32  (disco + IR + motors)")
    print()
    print("  STEPS:")
    print("    1. Power both ESP32s")
    print("    2. Connect laptop WiFi to: Shesheshe")
    print("    3. Open browser: http://localhost:{}".format(BRIDGE_PORT))
    print("    4. Play!")
    print()
    print("  Debug: http://localhost:{}/status".format(BRIDGE_PORT))
    print("  Press Ctrl+C to stop")
    print("=" * 55)

    server = http.server.HTTPServer(('0.0.0.0', BRIDGE_PORT), BridgeHandler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[BRIDGE] Shutting down...")
        server.server_close()


if __name__ == '__main__':
    main()
