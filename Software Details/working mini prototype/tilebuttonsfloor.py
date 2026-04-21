import network
import socket
from machine import Pin
import time

BUTTON_PINS = [18, 25, 33, 27, 14, 4, 21, 23, 15]
BUTTON_NAMES = [
    'TOP-LEFT', 'UP', 'TOP-RIGHT',
    'LEFT', 'CENTER', 'RIGHT',
    'BOT-LEFT', 'DOWN', 'BOT-RIGHT',
    'BONUS-L', 'BONUS-R']

buttons = [Pin(p, Pin.IN, Pin.PULL_UP) for p in BUTTON_PINS]

prev_states = [1] * 11
button_state = [0] * 11     
button_pressed = [0] * 11    
last_press_time = [0] * 11
DEBOUNCE_MS = 50

# ---------- ACCESS POINT ----------
ap = network.WLAN(network.AP_IF)
ap.active(True)
ap.config(essid='Shesheshe', password='12345678')

while not ap.active():
    time.sleep(0.1)

print("WiFi AP started")
print("IP:", ap.ifconfig()[0])

# ---------- HTTP SERVER ----------
def send_response(conn, status, content_type, body):
    conn.send("HTTP/1.1 {} OK\r\n".format(status))
    conn.send("Content-Type: {}\r\n".format(content_type))
    conn.send("Access-Control-Allow-Origin: *\r\n")
    conn.send("Cache-Control: no-store\r\n")
    conn.send("Connection: close\r\n\r\n")
    conn.sendall(body)

addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(addr)
server.listen(5)

print("Server running...")

while True:
    # ── Poll buttons with debounce ────────────────────────────
    now = time.ticks_ms()
    for i in range(9):
        current = buttons[i].value()
        if current != prev_states[i]:
            if time.ticks_diff(now, last_press_time[i]) > DEBOUNCE_MS:
                prev_states[i] = current
                last_press_time[i] = now
                if current == 0:
                    button_state[i] = 1
                    button_pressed[i] = 1  # STICKY: stays 1
                    print("[PRESS]", BUTTON_NAMES[i])
                else:
                    button_state[i] = 0

    # ── Handle HTTP ───────────────────────────────────────────
    try:
        server.setblocking(False)
        conn, addr2 = server.accept()
        server.setblocking(True)
    except OSError:
        time.sleep_ms(1)
        continue

    try:
        request = conn.recv(1024).decode('utf-8', 'ignore')
        first_line = request.split('\r\n')[0] if request else ''

        if 'GET /state' in first_line:
            # Send sticky presses to browser
            payload = '{{"b":[{},{},{},{},{},{},{},{},{},{},{}]}}'.format(*button_pressed)
            send_response(conn, 200, 'application/json', payload)
            
            # CLEAR sticky presses after browser reads them
            for i in range(11):
                button_pressed[i] = 0
        else:
            send_response(conn, 200, 'text/plain', 'ARCADE ESP32 OK')
 
    except Exception as e:
        print("[ERR]", e)
    finally:
        conn.close()



