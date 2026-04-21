# main floor 
import network
import socket
from machine import Pin
from neopixel import NeoPixel
import time

STRIP_PINS = [5, 19, 22, 23, 13, 26, 33, 32]

strips = [NeoPixel(Pin(p), 18) for p in STRIP_PINS]

COLORS = {'off':    (0, 0, 0),
    'yellow': (255, 230, 0),
    'blue':   (0, 170, 255),
    'green':  (57, 255, 20),
    'red':    (255, 34, 68),
    'orange': (255, 119, 0),
    'pink':   (255, 45, 122),
    'purple': (192, 64, 255),
    'white':  (255, 255, 255),
    'cyan':   (0, 229, 255)}

def get_color(name):
    return COLORS.get(name, (0, 0, 0))

def set_tile(tile_index, color_name):
    if tile_index < 0 or tile_index > 8:
        return
    color = get_color(color_name)
    s = strips[tile_index]
    for i in range(18):
        s[i] = color
    s.write()

def set_tile_led(tile_index, led_index, color_name):
    if tile_index < 0 or tile_index > 8:
        return
    if led_index < 0 or led_index >= 18:
        return
    color = get_color(color_name)
    s = strips[tile_index]
    s[led_index] = color
    s.write()

def set_all_tiles(colors_list):
    """Set all 9 tiles from a list of 9 color names."""
    if len(colors_list) != 9:
        return
    for tile_idx, cname in enumerate(colors_list):
        color = get_color(cname)
        s = strips[tile_idx]
        for i in range(18):
            s[i] = color
    for s in strips:
        s.write()

def clear_all():
    """Turn off all LEDs on all strips."""
    off = (0, 0, 0)
    for s in strips:
        for i in range(18):
            s[i] = off
        s.write()

BUTTON_PINS = [18, 25, 12, 27, 14, 4, 21, 23, 15]
BUTTON_NAMES = ['TOP-LEFT', 'UP', 'TOP-RIGHT',
    'LEFT', 'CENTER', 'RIGHT',
    'BOT-LEFT', 'DOWN', 'BOT-RIGHT']

NUM_BUTTONS = 9
buttons = [Pin(p, Pin.IN, Pin.PULL_UP) for p in BUTTON_PINS]
prev_states = [1] * NUM_BUTTONS
button_pressed = [0] * NUM_BUTTONS
last_press_time = [0] * NUM_BUTTONS
DEBOUNCE_MS = 50

# ── WIFI AP ──────────────────────────────────────
ap = network.WLAN(network.AP_IF)
ap.active(True)
ap.config(essid='Shesheshe', password='12345678')

while not ap.active():
    time.sleep(0.1)

print("WiFi AP started")
print("IP:", ap.ifconfig()[0])

# ── STARTUP ANIMATION ────────────────────────────
def startup_animation():
    test_colors = ['red', 'orange', 'yellow', 'green', 'cyan', 'blue', 'purple', 'pink', 'white']
    for color in test_colors:
        set_all_tiles([color] * 9)
        time.sleep(0.15)
    clear_all()

startup_animation()

# ── HTTP HELPERS ─────────────────────────────────
def send_response(conn, status, ctype, body):
    conn.send("HTTP/1.1 {} OK\r\n".format(status))
    conn.send("Content-Type: {}\r\n".format(ctype))
    conn.send("Access-Control-Allow-Origin: *\r\n")
    conn.send("Cache-Control: no-store\r\n")
    conn.send("Connection: close\r\n\r\n")
    conn.sendall(body)

def parse_params(url):
    if '?' not in url:
        return {}
    qs = url.split('?')[1].split(' ')[0]
    params = {}
    for pair in qs.split('&'):
        if '=' in pair:
            k, v = pair.split('=', 1)
            params[k] = v
    return params

# ── SERVER ───────────────────────────────────────
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(addr)
server.listen(5)

print("Server running on :80")

while True:
    now = time.ticks_ms()
    for i in range(NUM_BUTTONS):
        current = buttons[i].value()
        if current != prev_states[i]:
            if time.ticks_diff(now, last_press_time[i]) > DEBOUNCE_MS:
                prev_states[i] = current
                last_press_time[i] = now
                if current == 0:
                    button_pressed[i] = 1
                    print("[PRESS]", BUTTON_NAMES[i])

    try:
        server.setblocking(False)
        conn, _ = server.accept()
        server.setblocking(True)
    except OSError:
        time.sleep_ms(1)
        continue

    try:
        request = conn.recv(1024).decode('utf-8', 'ignore')
        first_line = request.split('\r\n')[0] if request else ''
        url_path = first_line.split(' ')[1] if ' ' in first_line else ''

        if 'GET /state' in first_line:
            payload = '{{"b":[{},{},{},{},{},{},{},{},{}]}}'.format(*button_pressed)
            send_response(conn, 200, 'application/json', payload)
            for i in range(NUM_BUTTONS):
                button_pressed[i] = 0

        elif 'GET /set_tile' in first_line:
            p = parse_params(url_path)
            idx = int(p.get('index', -1))
            col = p.get('color', 'off')
            if 0 <= idx <= 8:
                set_tile(idx, col)
                send_response(conn, 200, 'text/plain', 'OK')
            else:
                send_response(conn, 400, 'text/plain', 'BAD_INDEX')

        elif 'GET /set_all_tiles' in first_line:
            p = parse_params(url_path)
            colors = p.get('colors', '').split(',')
            if len(colors) == 9:
                set_all_tiles(colors)
                send_response(conn, 200, 'text/plain', 'OK')
            else:
                send_response(conn, 400, 'text/plain', 'NEED_9')

        elif 'GET /set_led' in first_line:
            p = parse_params(url_path)
            tile = int(p.get('tile', -1))
            led = int(p.get('led', -1))
            col = p.get('color', 'off')
            if 0 <= tile <= 8 and 0 <= led < 18:
                set_tile_led(tile, led, col)
                send_response(conn, 200, 'text/plain', 'OK')
            else:
                send_response(conn, 400, 'text/plain', 'BAD_INDEX')

        elif 'GET /clear' in first_line:
            clear_all()
            send_response(conn, 200, 'text/plain', 'OK')

        else:
            send_response(conn, 200, 'text/plain', 'FLOOR ESP32 OK')

    except Exception as e:
        print("[ERR]", e)
    finally:
        conn.close()
