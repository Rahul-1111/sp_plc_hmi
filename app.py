import logging
import threading
import time
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from plc_connector import PLCConnector

# Logging setup (optional: hide noisy access logs)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Flask & SocketIO setup
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(
    app,
    async_mode='threading',
    logger=False,          # disable SocketIO logs
    engineio_logger=False  # disable Engine.IO logs
)

# PLC configuration
PLC_IP = '192.168.3.39'
PLC_PORT = 5002
plc = PLCConnector(PLC_IP, PLC_PORT)

# Tags for bits and words (from SP.xlsx)
BIT_TAGS = [
    'M7', 'M9', 'M100', 'M101', 'M102', 'M103', 'M200', 'M201', 'M202', 'M203',
    'M204', 'M205', 'M206', 'M207', 'M208', 'M209', 'M210', 'M211', 'M212', 'M213',
    'M214', 'M215', 'M216', 'M217', 'M218', 'M219', 'M220', 'M221', 'M222', 'M223',
    'M224', 'M225', 'M226', 'M227', 'M228', 'M229', 'M230', 'M231', 'M232', 'M233',
    'M234', 'M235', 'M236', 'M237', 'M238', 'M239', 'M240', 'M241', 'M242', 'M243',
    'M244', 'M245', 'M246', 'M247', 'M248', 'M300', 'M301', 'M305', 'M309', 'M313',
    'M317', 'M321', 'M325', 'M329', 'M400', 'M401', 'M405', 'M409', 'M413', 'M417',
    'M423', 'M500', 'M501', 'M505', 'M509', 'M513', 'M517', 'M521', 'M525', 'M529',
    'M533', 'M537', 'M541', 'M545', 'M549', 'M553', 'M557', 'M563', 'M569', 'M805',
    'M806', 'M807', 'L100', 'L101', 'L102'
]

WORD_TAGS = [
    'D302', 'D304', 'D306', 'D310', 'D312', 'D314', 'D316', 'D318', 'D320', 'D322',
    'D324', 'D326', 'D328', 'D330', 'D332', 'D334', 'D336', 'D338', 'D340', 'D342',
    'D344', 'D346', 'D348', 'D350', 'D352', 'D354', 'D356', 'D358', 'D360', 'D362',
    'D364', 'D366', 'D368', 'D410', 'D412', 'D414', 'D416', 'D418', 'D420', 'D422',
    'D424', 'D426', 'D428', 'D430', 'D432', 'D434', 'D436', 'D438', 'D440', 'D442',
    'D444', 'D446', 'D448', 'D450', 'D452', 'D454', 'D456', 'D458', 'D460', 'D462',
    'D464', 'D466', 'D468', 'D500', 'D512', 'D520', 'D530', 'D550', 'D552', 'D554',
    'D610', 'D612', 'D614', 'D616', 'D618', 'D620', 'D622', 'D624', 'D626', 'D628',
    'D630', 'D632', 'D634', 'D636', 'D638', 'D640', 'D642', 'D644', 'D646', 'D648',
    'D650', 'D652', 'D654', 'D656', 'D658', 'D660', 'D662', 'D664', 'D666', 'D668'
]

# Runtime state
last_bits = {}
last_words = {}

# PLC polling
def poll_plc():
    """
    Continuously read bits & integer words from the PLC
    and send updates to connected clients.
    """
    global last_bits, last_words

    # Define ranges based on BIT_TAGS (M7 to M807) and WORD_TAGS (D302 to D668)
    bit_start = "M7"
    bit_size = 807 - 7 + 1  # From M7 to M807
    word_start = "D302"
    word_size = 668 - 302 + 1  # From D302 to D668

    # Map tag names to their indices in the batch
    bit_indices = {tag: int(tag[1:]) - 7 for tag in BIT_TAGS}  # e.g., M7 -> 0, M9 -> 2
    word_indices = {tag: int(tag[1:]) - 302 for tag in WORD_TAGS}  # e.g., D302 -> 0, D304 -> 2

    # Force initial emission
    initial = True

    while True:
        try:
            # Read entire ranges in one call
            bit_values = plc.batch_read_bits(bit_start, bit_size)
            word_values = plc.batch_read_words(word_start, word_size)

            # Extract only the needed tags
            bits = {tag: bit_values[bit_indices[tag]] for tag in BIT_TAGS}
            words = {tag: word_values[word_indices[tag]] for tag in WORD_TAGS}

            # Emit on first poll or if data changes
            if initial or bits != last_bits or words != last_words:
                socketio.emit('plc_data', {'bits': bits, 'words': words})
                last_bits = bits.copy()
                last_words = words.copy()
                initial = False

        except Exception as e:
            print(f"[PLC Poll Error] {e}")

        time.sleep(0.1)  # Poll interval (100 ms)

# Socket.IO events
@socketio.on('connect')
def handle_connect():
    print("[Client] Connected")
    # Send current PLC state to newly connected client
    socketio.emit('plc_data', {'bits': last_bits, 'words': last_words})

@socketio.on('toggle_bit')
def handle_toggle_bit(tag):
    """
    Flip a PLC bit (ON/OFF).
    """
    try:
        print(f"[DEBUG] Toggle request for {tag}")
        current = plc.read_bit(tag)
        plc.write_bit(tag, not current)
    except Exception as e:
        print(f"[Toggle Bit Error] {tag}: {e}")

@socketio.on('write_word')
def handle_write_word(data):
    """
    Write an integer (16-bit word) to the PLC.
    Expected payload: {"tag": "D396", "value": 123}
    """
    tag = data.get('tag')
    value = data.get('value')

    if tag is None or value is None:
        emit('write_response', {'status': 'error', 'message': 'Missing tag or value'})
        return

    try:
        # Ensure only integer is written
        int_value = int(value)
        plc.write_word(tag, int_value)
        emit('write_response', {'status': 'success', 'tag': tag, 'value': int_value})
    except Exception as e:
        emit('write_response', {'status': 'error', 'tag': tag, 'message': str(e)})

# Routes
@app.route('/')
def index():
    return render_template('hmi.html', bit_tags=BIT_TAGS, word_tags=WORD_TAGS)

# Entry point
if __name__ == '__main__':
    # Start the background polling thread
    threading.Thread(target=poll_plc, daemon=True).start()

    # Launch the server
    socketio.run(app, host='0.0.0.0', port=5000)