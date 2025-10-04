import logging
import threading
import time
import struct
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from plc_connector import PLCConnector

# --- Logging setup ---
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# --- Flask & SocketIO setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(
    app,
    async_mode='threading',
    logger=False,
    engineio_logger=False
)

# --- PLC configuration (adjust IP/PORT if needed) ---
PLC_IP = '192.168.3.39'
PLC_PORT = 5002
plc = PLCConnector(PLC_IP, PLC_PORT, retry_interval=5)

# --- Tags ---
BIT_TAGS = [
    'M3','M7','M13','M14','M15','M16','M17','M20','M21','M22','M33',
    'M9','M100','M101','M102','M103','M200','M201','M202','M203',
    'M204','M205','M206','M207','M208','M209','M210','M211','M212','M213',
    'M214','M215','M216','M217','M218','M219','M220','M221','M222','M223',
    'M224','M225','M226','M227','M228','M229','M230','M231','M232','M233',
    'M234','M235','M236','M237','M238','M239','M240','M241','M242','M243',
    'M244','M245','M246','M247','M248','M300','M301','M305','M309','M313',
    'M317','M321','M325','M329','M400','M401','M405','M409','M413','M417',
    'M423','M448','M449','M500','M501','M505','M509','M513','M517','M521','M525','M529',
    'M533','M537','M541','M545','M549','M553','M557','M563','M569','L100','L101','L102'
]

WORD_TAGS = [
    'D302','D304','D306','D310','D312','D314','D316','D318','D320','D322',
    'D324','D326','D328','D330','D332','D334','D336','D338','D340','D342',
    'D344','D346','D348','D350','D352','D354','D356','D358','D360','D362',
    'D364','D366','D368','D410','D412','D414','D416','D418','D420','D422',
    'D424','D426','D428','D430','D432','D434','D436','D438','D440','D442',
    'D444','D446','D448','D450','D452','D454','D456','D458','D460','D462',
    'D464','D466','D468','D500','D512','D520','D530','D550','D552','D554',
    'D610','D612','D614','D616','D618','D620','D622','D624','D626','D628',
    'D630','D632','D634','D636','D638','D640','D642','D644','D646','D648',
    'D650','D652','D654','D656','D658','D660','D662','D664','D666','D668',
    'D802','D803','D812','D813'  # float registers (low+high)
]

# runtime caches
last_bits = {}
last_words = {}
last_floats = {}

import struct

def plc_read_float(tag: str) -> float:
    if tag == "D802":   # first float (little-endian)
        low = plc.read_word("D802")
        high = plc.read_word("D803")
        packed = struct.pack('<HH', low, high)
    elif tag == "D812":  # second float (big-endian)
        high = plc.read_word("D813")
        low = plc.read_word("D812")
        packed = struct.pack('<HH', high, low)
    else:
        raise ValueError(f"Unknown float tag: {tag}")
    val = struct.unpack('<f', packed)[0]
    print(f"[DEBUG] Read float {tag}: words=({low},{high}) → {val}")
    return val

def plc_write_float(tag: str, value: float):
    packed = struct.pack('<f', float(value))
    low_word, high_word = struct.unpack('<HH', packed)
    if tag == "D802":  # first float (little-endian)
        plc.write_word("D802", low_word)
        plc.write_word("D803", high_word)
    elif tag == "D812":  # second float (big-endian)
        plc.write_word("D812", low_word)
        plc.write_word("D813", high_word)
    else:
        raise ValueError(f"Unknown float tag: {tag}")
    print(f"[DEBUG] Wrote float {value} → {tag} as words ({low_word},{high_word})")

def poll_plc():
    global last_bits, last_words, last_floats
    bit_start = "M7"
    bit_size = 569 - 7 + 1
    word_start = "D302"
    word_size = 813 - 302 + 1
    bit_indices = {tag: int(tag[1:]) - 7 for tag in BIT_TAGS}
    word_indices = {tag: int(tag[1:]) - 302 for tag in WORD_TAGS}
    initial = True

    while True:
        try:
            bit_values = plc.batch_read_bits(bit_start, bit_size)
            word_values = plc.batch_read_words(word_start, word_size)
            bits = {tag: bit_values[bit_indices[tag]] for tag in BIT_TAGS}
            words = {tag: word_values[word_indices[tag]] for tag in WORD_TAGS}
            floats = {
                "D802": plc_read_float("D802"),
                "D812": plc_read_float("D812")
            }

            if initial or bits != last_bits or words != last_words or floats != last_floats:
                socketio.emit('plc_data', {'bits': bits, 'words': words, 'floats': floats})
                last_bits = bits.copy()
                last_words = words.copy()
                last_floats = floats.copy()
                initial = False
        except Exception as e:
            print(f"[PLC Poll Error] {e}")
            plc.reconnect()
        time.sleep(0.5)

@socketio.on('connect')
def handle_connect():
    print("[Client] Connected")
    # send current cached state to client
    socketio.emit('plc_data', {'bits': last_bits, 'words': last_words, 'floats': last_floats})

@socketio.on('write_word')
def handle_write_word(data):
    """
    Unified write handler. Frontend can continue to emit write_word for everything.
    For float tags (D802, D812) this writes a 32-bit float (two words).
    For others it writes a single 16-bit word integer.
    """
    tag = data.get('tag')
    value = data.get('value')
    if tag is None or value is None:
        emit('write_response', {'status': 'error', 'message': 'Missing tag or value'})
        return

    try:
        # Float tags (automatic handling)
        if tag in ('D802', 'D812'):
            float_val = float(value)
            print(f"[FRONTEND] Request to write FLOAT {float_val} -> {tag}")
            confirmed = plc_write_float(tag, float_val)
            if confirmed is not None:
                emit('write_response', {'status': 'success', 'tag': tag, 'value': confirmed})
            else:
                emit('write_response', {'status': 'error', 'tag': tag, 'message': 'Write succeeded but confirm failed'})
            return

        # Normal word write (16-bit integer)
        int_val = int(value)
        print(f"[FRONTEND] Request to write INT {int_val} -> {tag}")
        plc.write_word(tag, int_val)
        emit('write_response', {'status': 'success', 'tag': tag, 'value': int_val})

    except Exception as e:
        print(f"[Write Word Error] {tag}: {e}")
        emit('write_response', {'status': 'error', 'tag': tag, 'message': str(e)})
        try:
            plc.reconnect()
        except Exception as re:
            print(f"[WriteWord] reconnect failed: {re}")

@socketio.on('write_float')
def handle_write_float(data):
    tag = data.get('tag')
    value = data.get('value')
    if tag is None or value is None:
        emit('write_float_response', {'status': 'error', 'message': 'Missing tag or value'})
        return
    try:
        if tag not in ["D802", "D812"]:
            emit('write_float_response', {'status': 'error', 'tag': tag, 'message': f'Invalid float tag: {tag}'})
            return
        plc_write_float(tag, float(value))
        emit('write_float_response', {'status': 'success', 'tag': tag, 'value': float(value)})
    except Exception as e:
        print(f"[Write Float Error] {tag}: {e}")
        emit('write_float_response', {'status': 'error', 'tag': tag, 'message': str(e)})
        plc.reconnect()

@socketio.on('set_bit')
def handle_set_bit(data):
    """
    Set a bit to true/false.
    Accepts: {'tag':'M13', 'value': true/false}
    """
    try:
        if isinstance(data, dict):
            tag = data.get('tag')
            value = data.get('value', True)
        else:
            tag = data
            value = True
        if not isinstance(value, bool):
            value = bool(value)
        print(f"[FRONTEND] Set bit {tag} -> {value}")
        if tag not in BIT_TAGS:
            emit('set_bit_response', {'status': 'error', 'tag': tag, 'message': f'Invalid tag: {tag}'})
            return
        plc.write_bit(tag, value)
        emit('set_bit_response', {'status': 'success', 'tag': tag, 'value': value})
    except Exception as e:
        print(f"[Set Bit Error] {tag}: {e}")
        emit('set_bit_response', {'status': 'error', 'tag': tag, 'message': str(e)})
        try:
            plc.reconnect()
        except Exception as re:
            print(f"[SetBit] reconnect failed: {re}")

@socketio.on('toggle_bit')
def handle_toggle_bit(data):
    """
    Toggle a bit (flip current value).
    Accepts payload: {'tag': 'M13'} or just 'M13'
    """
    try:
        tag = data['tag'] if isinstance(data, dict) and 'tag' in data else data
        print(f"[FRONTEND] Toggle bit requested: {tag}")
        if tag not in BIT_TAGS:
            emit('toggle_response', {'status': 'error', 'tag': tag, 'message': f'Invalid tag: {tag}'})
            return
        current = plc.read_bit(tag)
        plc.write_bit(tag, not current)
        emit('toggle_response', {'status': 'success', 'tag': tag, 'value': not current})
    except Exception as e:
        print(f"[Toggle Bit Error] {tag}: {e}")
        emit('toggle_response', {'status': 'error', 'tag': tag, 'message': str(e)})
        try:
            plc.reconnect()
        except Exception as re:
            print(f"[ToggleBit] reconnect failed: {re}")

# --- Routes ---
@app.route('/')
def index():
    return render_template('hmi.html', bit_tags=BIT_TAGS, word_tags=WORD_TAGS)

# --- Main entrypoint ---
if __name__ == '__main__':
    # start polling thread
    threading.Thread(target=poll_plc, daemon=True).start()
    # run socketio app
    socketio.run(app, host='0.0.0.0', port=5000)
