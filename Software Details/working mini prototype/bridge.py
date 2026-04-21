import http.server
import urllib.request
import urllib.error
import json
import os
import sys

# ESP32 IP address (default for AP mode)
ESP32_IP = "192.168.4.1"
ESP32_PORT = 80

# Bridge server port
BRIDGE_PORT = 8000

# Path to your HTML file
HTML_FILE = "finalwebcode.html"  # CHANGE THIS to your actual HTML filename


class BridgeHandler(http.server.BaseHTTPRequestHandler):
    
    def do_GET(self):
        path = self.path.split('?')[0]
        query = self.path.split('?')[1] if '?' in self.path else ''
        
        # ── Serve the HTML game ──────────────────────────────────
        if path == '/' or path == '/index.html':
            self.serve_html()
        
        # ── Forward to ESP32 ─────────────────────────────────────
        elif path in ['/state', '/set_tile', '/set_all_tiles', '/on', '/off']:
            self.forward_to_esp32()
        
        # ── Unknown route ────────────────────────────────────────
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not Found')
    
    def serve_html(self):
        """Serve the local HTML file"""
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
            print("[BRIDGE] ERROR: {} not found!".format(HTML_FILE))
    
    def forward_to_esp32(self):
        """Forward request to ESP32 and return response"""
        url = "http://{}:{}{}".format(ESP32_IP, ESP32_PORT, self.path)
        
        try:
            req = urllib.request.Request(url)
            req.add_header('Connection', 'close')
            
            with urllib.request.urlopen(req, timeout=2) as response:
                body = response.read()
                content_type = response.headers.get('Content-Type', 'text/plain')
            
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
        
        except urllib.error.URLError as e:
            self.send_response(502)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            error_msg = json.dumps({"error": "ESP32 not reachable", "detail": str(e)})
            self.wfile.write(error_msg.encode('utf-8'))
            print("[BRIDGE] ESP32 connection failed:", e)
        
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode('utf-8'))
            print("[BRIDGE] Error:", e)
    
    # Suppress default logging (cleaner output)
    def log_message(self, format, *args):
        # Only log errors and forwards, not every request
        msg = format % args
        if '/state' not in msg:  # Don't log polling (too noisy)
            print("[BRIDGE]", msg)


def main():
    # Check HTML file exists
    if not os.path.exists(HTML_FILE):
        print("=" * 50)
        print("ERROR: Cannot find '{}'".format(HTML_FILE))
        print("")
        print("Make sure:")
        print("  1. bridge.py is in the SAME folder as your HTML file")
        print("  2. The HTML filename matches: {}".format(HTML_FILE))
        print("")
        print("Your folder should look like:")
        print("  my_folder/")
        print("    bridge.py")
        print("    {}".format(HTML_FILE))
        print("=" * 50)
        sys.exit(1)
    
    print("=" * 50)
    print("  ARCADE BRIDGE SERVER")
    print("=" * 50)
    print("")
    print("  HTML file:  {}".format(HTML_FILE))
    print("  ESP32 IP:   {}:{}".format(ESP32_IP, ESP32_PORT))
    print("  Bridge:     http://localhost:{}".format(BRIDGE_PORT))
    print("")
    print("  STEPS:")
    print("  1. Connect laptop to WiFi: Shesheshe")
    print("  2. Open browser: http://localhost:{}".format(BRIDGE_PORT))
    print("  3. Play!")
    print("")
    print("  Press Ctrl+C to stop")
    print("=" * 50)
    
    server = http.server.HTTPServer(('0.0.0.0', BRIDGE_PORT), BridgeHandler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[BRIDGE] Shutting down...")
        server.server_close()


if __name__ == '__main__':
    main()
