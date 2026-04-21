#main ceiling
from machine import Pin
from neopixel import NeoPixel
from time import sleep_ms, sleep_us, ticks_ms, ticks_us, ticks_diff, ticks_add
import network
import socket
import time
import _thread

LEFT_STEP_PINS  = [15, 4, 5, 18]
RIGHT_STEP_PINS = [19, 21, 22, 23]

C = {'off':          (0, 0, 0),
    'white':        (255, 255, 255),
    'red':          (255, 0, 0),
    'red_dark':     (100, 0, 0),
    'pink':         (255, 45, 122),
    'pink_light':   (255, 150, 180),
    'pink_hot':     (255, 80, 150),
    'pink_deep':    (200, 30, 90),
    'pink_soft':    (255, 120, 180),
    'pink_rose':    (255, 60, 130),
    'magenta':      (255, 0, 200),
    'purple':       (192, 64, 255),
    'purple_dark':  (140, 40, 200),
    'purple_deep':  (100, 20, 160),
    'purple_mid':   (160, 50, 220),
    'purple_light': (220, 80, 255),
    'purple_plum':  (120, 30, 180),
    'blue_dark':    (0, 0, 139),
    'blue_light':   (100, 180, 255),
    'blue_mid':     (0, 0, 140),
    'cyan':         (0, 255, 255),
    'green_light':  (100, 255, 100),
    'green_dark':   (0, 80, 10),
    'green_bright': (80, 255, 120),
    'green_lime':   (57, 255, 20),
    'orange':       (255, 165, 0),
    'orange_warm':  (200, 120, 0),
    'orange_bright':(255, 140, 0),
    'yellow':       (255, 230, 0),
    'warm':         (255, 180, 80),
    'warm_dim':     (180, 120, 50)}

disco = NeoPixel(Pin(DISCO_PIN), 78)

left_ir = Pin(3, Pin.IN, Pin.PULL_UP)
right_ir = Pin(16, Pin.IN, Pin.PULL_UP)

for i in range(DISCO_COUNT):
    disco[i] = C['off']
disco.write()

STEP_SEQ = [[1, 0, 0, 1], [1, 0, 0, 0], [1, 1, 0, 0], [0, 1, 0, 0],[0, 1, 1, 0], [0, 0, 1, 0], [0, 0, 1, 1], [0, 0, 0, 1]]
STEPS_PER_REV = 4096

left_pins  = [Pin(p, Pin.OUT) for p in LEFT_STEP_PINS]
right_pins = [Pin(p, Pin.OUT) for p in RIGHT_STEP_PINS]

left_pos = 0
left_target = 0
left_delay_us = 1200
left_step_idx = 0

right_pos = 0
right_target = 0
right_delay_us = 1200
right_step_idx = 0

def spin_cw(motor, revs, duration):
    global left_target, left_delay_us, right_target, right_delay_us
    steps = int(revs * STEPS_PER_REV)
    if steps == 0:
        return
    delay = max(800, int((duration * 1_000_000) / abs(steps)))
    if motor == 'left':
        left_target = left_pos + steps
        left_delay_us = delay
    else:
        right_target = right_pos + steps
        right_delay_us = delay

def spin_ccw(motor, revs, duration):
    global left_target, left_delay_us, right_target, right_delay_us
    steps = int(revs * STEPS_PER_REV)
    if steps == 0:
        return
    delay = max(800, int((duration * 1_000_000) / abs(steps)))
    if motor == 'left':
        left_target = left_pos - steps
        left_delay_us = delay
    else:
        right_target = right_pos - steps
        right_delay_us = delay

def stop_motor(motor):
    global left_target, right_target
    if motor == 'left':
        left_target = left_pos
        for p in left_pins: p.value(0)
    else:
        right_target = right_pos
        for p in right_pins: p.value(0)

def stop_all_motors():
    stop_motor('left')
    stop_motor('right')

def stepper_thread():
    global left_pos, left_step_idx, right_pos, right_step_idx
    left_next = ticks_us()
    right_next = ticks_us()
    
    while True:
        now = ticks_us()
        if left_pos != left_target:
            if ticks_diff(now, left_next) >= 0:
                d = 1 if left_target > left_pos else -1
                left_pos += d
                left_step_idx = (left_step_idx + d) % 8
                seq = STEP_SEQ[left_step_idx]
                for i in range(4): left_pins[i].value(seq[i])
                left_next = ticks_add(now, left_delay_us)
        else:
            for p in left_pins: p.value(0)

        if right_pos != right_target:
            if ticks_diff(now, right_next) >= 0:
                d = 1 if right_target > right_pos else -1
                right_pos += d
                right_step_idx = (right_step_idx + d) % 8
                seq = STEP_SEQ[right_step_idx]
                for i in range(4): right_pins[i].value(seq[i])
                right_next = ticks_add(now, right_delay_us)
        else:
            for p in right_pins: p.value(0)

        sleep_us(200)

_thread.start_new_thread(stepper_thread, ())
print("Stepper thread running")

seq_cmds = []
seq_idx = 0
seq_start = 0
seq_dur = 0
seq_loop = False
seq_on = False

def set_sequence(cmds, loop=False):
    global seq_cmds, seq_idx, seq_start, seq_loop, seq_on
    seq_cmds = cmds
    seq_idx = 0
    seq_loop = loop
    seq_on = True
    seq_start = ticks_ms()
    _run_seq_step()

def stop_sequence():
    global seq_on
    seq_on = False
    stop_all_motors()

def _run_seq_step():
    global seq_dur
    if seq_idx >= len(seq_cmds):
        return
    cmd = seq_cmds[seq_idx]

    if cmd[0] == 'cw':
        spin_cw(cmd[1], cmd[2], cmd[3])
        seq_dur = int(cmd[3] * 1000)
    elif cmd[0] == 'ccw':
        spin_ccw(cmd[1], cmd[2], cmd[3])
        seq_dur = int(cmd[3] * 1000)
    elif cmd[0] == 'both':
        fn_l = spin_cw if cmd[1] == 'cw' else spin_ccw
        fn_r = spin_cw if cmd[3] == 'cw' else spin_ccw
        fn_l('left', cmd[2], cmd[5])
        fn_r('right', cmd[4], cmd[5])
        seq_dur = int(cmd[5] * 1000)
    elif cmd[0] == 'wait':
        seq_dur = int(cmd[1] * 1000)
    elif cmd[0] == 'stop':
        stop_all_motors()
        seq_dur = 0

def update_sequence():
    global seq_idx, seq_start, seq_on
    if not seq_on or not seq_cmds:
        return
    if ticks_diff(ticks_ms(), seq_start) >= seq_dur:
        seq_idx += 1
        if seq_idx >= len(seq_cmds):
            if seq_loop:
                seq_idx = 0
            else:
                seq_on = False
                return
        seq_start = ticks_ms()
        _run_seq_step()

sta = network.WLAN(network.STA_IF)
sta.active(True)
sta.disconnect()

WIFI_SSID = 'Shesheshe'
WIFI_PASS = '12345678'

print("Connecting to WiFi:", WIFI_SSID)
sta.connect(WIFI_SSID, WIFI_PASS)

for _ in range(30):
    if sta.isconnected():
        break
    time.sleep(0.5)

if sta.isconnected():
    print("WiFi connected!")
    print("Ceiling IP:", sta.ifconfig()[0])
else:
    print("WiFi FAILED — rebooting in 5s")
    time.sleep(5)
    import machine
    machine.reset()

ir_left_last = 0
ir_right_last = 0
IR_DEBOUNCE = 500
ir_active = False

ir_left_triggered = 0
ir_right_triggered = 0

def check_ir_sensors():
    global ir_left_last, ir_right_last
    global ir_left_triggered, ir_right_triggered
    if not ir_active:
        return
    now = ticks_ms()

    if left_ir.value() == 0 and ticks_diff(now, ir_left_last) > IR_DEBOUNCE:
        ir_left_last = now
        ir_left_triggered = 1
        spin_cw('left', 1, 1.0)
        print("Left IR — bonus!")

    if right_ir.value() == 0 and ticks_diff(now, ir_right_last) > IR_DEBOUNCE:
        ir_right_last = now
        ir_right_triggered = 1
        spin_cw('right', 1, 1.0)
        print("Right IR — bonus!")

ATTRACT_PAT  = [C['pink'], C['pink'], C['purple'], C['purple'], C['blue_dark'], C['blue_dark']]
MENU_DDR_PAT = [C['cyan'], C['blue_dark']]
MENU_MEM_PAT = [C['orange'], C['orange_warm']]
MENU_MOLE_PAT= [C['green_light'], C['green_dark']]
MENU_TTT_PAT = [C['magenta'], C['pink_light']]
DDR_PAT      = [C['pink'], C['pink'], C['orange_bright'], C['orange_bright'], C['yellow'], C['yellow']]
MEM_PLAY_PAT = [C['blue_light'], C['blue_light'], C['blue_light'], C['blue_mid'], C['blue_mid'], C['blue_mid'], C['green_bright'], C['green_bright'], C['green_bright']]
MOLE_PAT     = [C['green_lime'], C['cyan'], C['orange'], C['pink'], C['purple'], C['yellow']]
TTT_PINK_PAT = [C['pink'], C['pink_hot'], C['pink_soft'], C['pink_deep'], C['pink_rose'], C['pink_light']]
TTT_PURP_PAT = [C['purple'], C['purple_dark'], C['purple_deep'], C['purple_mid'], C['purple_light'], C['purple_plum']]
WIN_PAT      = [C['pink'], C['cyan'], C['yellow'], C['green_lime'], C['purple'], C['orange']]

def disco_off():
    for i in range(DISCO_COUNT):
        disco[i] = C['off']
    disco.write()

def _scroll(t, speed_ms, pat):
    offset = (t // speed_ms) % DISCO_COUNT
    n = len(pat)
    for i in range(DISCO_COUNT):
        disco[i] = pat[(i + offset) % n]
    disco.write()

def _swap(t, interval_ms, c1, c2):
    swap = (t // interval_ms) % 2
    for i in range(DISCO_COUNT):
        disco[i] = c1 if ((i % 2) == swap) else c2
    disco.write()

def pattern_attract(t):
    _scroll(t, 40, ATTRACT_PAT)

def pattern_menu_ddr(t):
    _swap(t, 500, C['cyan'], C['blue_dark'])

def pattern_menu_memory(t):
    _swap(t, 500, C['orange'], C['orange_warm'])

def pattern_menu_mole(t):
    _swap(t, 500, C['green_light'], C['green_dark'])

def pattern_menu_ttt(t):
    _swap(t, 500, C['magenta'], C['pink_light'])

def pattern_game_ddr(t, speed):
    scroll_ms = max(10, int(60 / speed))
    _scroll(t, scroll_ms, DDR_PAT)

def pattern_memory_watch(t):
    for i in range(DISCO_COUNT):
        disco[i] = C['warm'] if (i % 3 == 0) else C['warm_dim']
    disco.write()

def pattern_memory_play(t):
    _scroll(t, 1000, MEM_PLAY_PAT)

def pattern_game_mole(t):
    offset = (t // 25) % DISCO_COUNT
    n = len(MOLE_PAT)
    for i in range(DISCO_COUNT):
        pos = (i + offset) % DISCO_COUNT
        disco[i] = MOLE_PAT[(pos // 3) % n] if (pos % 3 == 0) else C['off']
    disco.write()

def pattern_ttt_pink(t):
    _scroll(t, 1000, TTT_PINK_PAT)

def pattern_ttt_purple(t):
    _scroll(t, 1000, TTT_PURP_PAT)

def pattern_win(t):
    _scroll(t, 15, WIN_PAT)

def pattern_lose(t):
    _swap(t, 800, C['red'], C['red_dark'])

state = 'off'
speed_mult = 1.0

def change_state(new_state):
    global state, ir_active
    if new_state == state:
        return
    print("State:", state, "->", new_state)
    state = new_state

    if state == 'attract':
        set_sequence([
            ('both', 'cw', 3, 'ccw', 3, 6.0),
            ('wait', 0.5),
            ('both', 'ccw', 3, 'cw', 3, 6.0),
            ('wait', 0.5),
        ], loop=True)
        ir_active = False

    elif state.startswith('menu_'):
        stop_sequence()
        ir_active = False

    elif state == 'game_ddr':
        stop_sequence()
        ir_active = True

    elif state == 'mem_watch':
        stop_sequence()
        ir_active = False

    elif state == 'mem_play':
        ir_active = False

    elif state == 'game_mole':
        stop_sequence()
        ir_active = False

    elif state == 'ttt_pink':
        stop_sequence()
        spin_cw('left', 1, 1.5)
        ir_active = False

    elif state == 'ttt_purple':
        stop_sequence()
        spin_cw('right', 1, 1.5)
        ir_active = False

    elif state == 'win':
        set_sequence([
            ('both', 'cw', 2, 'ccw', 2, 2.0),
            ('both', 'ccw', 2, 'cw', 2, 2.0),
        ], loop=True)
        ir_active = False

    elif state == 'lose':
        stop_sequence()
        ir_active = False

    elif state == 'off':
        stop_sequence()
        disco_off()
        ir_active = False

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


addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
server = socket.socket()
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server.bind(addr)
server.listen(5)

print("HTTP server running on :80")

FRAME_MS = 20

print("Ceiling ready")
change_state('attract')

while True:
    frame_start = ticks_ms()

    try:
        server.setblocking(False)
        conn, _ = server.accept()
        server.setblocking(True)
        try:
            request = conn.recv(1024).decode('utf-8', 'ignore')
            first_line = request.split('\r\n')[0] if request else ''
            url_path = first_line.split(' ')[1] if ' ' in first_line else ''

            if 'GET /ir_state' in first_line:
                payload = '{{"ir":[{},{}]}}'.format(
                    ir_left_triggered, ir_right_triggered)
                send_response(conn, 200, 'application/json', payload)
                ir_left_triggered = 0
                ir_right_triggered = 0

            elif 'GET /set_state' in first_line:
                p = parse_params(url_path)
                new_state = p.get('state', '')
                if new_state:
                    change_state(new_state)
                    send_response(conn, 200, 'text/plain', 'OK')
                else:
                    send_response(conn, 400, 'text/plain', 'NEED_STATE')

            elif 'GET /event' in first_line:
                p = parse_params(url_path)
                event = p.get('type', '')
                if event == 'wrong':
                    spin_cw('left', 1, 0.5)
                    spin_ccw('right', 1, 0.5)
                elif event == 'bonus_left':
                    spin_cw('left', 2, 1.5)
                elif event == 'bonus_right':
                    spin_ccw('right', 2, 1.5)
                send_response(conn, 200, 'text/plain', 'OK')

            elif 'GET /speed' in first_line:
                p = parse_params(url_path)
                try:
                    speed_mult = float(p.get('value', speed_mult))
                    send_response(conn, 200, 'text/plain', 'OK')
                except:
                    send_response(conn, 400, 'text/plain', 'BAD')
            else:
                send_response(conn, 200, 'text/plain', 'CEILING ESP32 OK')
        except Exception as e:
            print("[ERR]", e)
        finally:
            conn.close()

    except OSError:
        pass

    check_ir_sensors()
    t = ticks_ms()
    if   state == 'attract':      pattern_attract(t)
    elif state == 'menu_ddr':     pattern_menu_ddr(t)
    elif state == 'menu_memory':  pattern_menu_memory(t)
    elif state == 'menu_mole':    pattern_menu_mole(t)
    elif state == 'menu_ttt':     pattern_menu_ttt(t)
    elif state == 'game_ddr':     pattern_game_ddr(t, speed_mult)
    elif state == 'mem_watch':    pattern_memory_watch(t)
    elif state == 'mem_play':     pattern_memory_play(t)
    elif state == 'game_mole':    pattern_game_mole(t)
    elif state == 'ttt_pink':     pattern_ttt_pink(t)
    elif state == 'ttt_purple':   pattern_ttt_purple(t)
    elif state == 'win':          pattern_win(t)
    elif state == 'lose':         pattern_lose(t)

    update_sequence()

    elapsed = ticks_diff(ticks_ms(), frame_start)
    if elapsed < FRAME_MS:
        sleep_ms(FRAME_MS - elapsed)

