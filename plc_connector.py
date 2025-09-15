import pymcprotocol
import time

class PLCConnector:
    def __init__(self, ip, port, retry_interval=2, max_retries=5):
        self.ip = ip
        self.port = port
        self.retry_interval = retry_interval
        self.max_retries = max_retries
        self.client = pymcprotocol.Type3E()
        self.connected = False
        self.retry_count = 0
        self.connect_with_retry()

    def connect_with_retry(self):
        while not self.connected and self.retry_count < self.max_retries:
            try:
                self.client.connect(self.ip, self.port)
                self.connected = True
                self.retry_count = 0
                print(f"[PLCConnector] ✅ Connected to {self.ip}:{self.port}")
            except Exception as e:
                self.retry_count += 1
                print(f"[PLCConnector] ❌ Connect failed: {e} (Attempt {self.retry_count}/{self.max_retries})")
                time.sleep(self.retry_interval)
        if not self.connected:
            print(f"[PLCConnector] ❌ Failed to connect after {self.max_retries} attempts")

    def reconnect(self):
        try:
            self.client.close()
        except:
            pass
        self.connected = False
        self.retry_count = 0
        print("[PLCConnector] 🔁 Reconnecting...")
        self.connect_with_retry()

    def read_bit(self, device):
        try:
            result = self.client.batchread_bitunits(headdevice=device, readsize=1)
            return bool(result[0]) if result else False
        except Exception as e:
            print(f"[PLCConnector] Read Bit Error ({device}): {e}")
            self.reconnect()
            return False

    def write_bit(self, device, value):
        try:
            self.client.batchwrite_bitunits(headdevice=device, values=[int(value)])
        except Exception as e:
            print(f"[PLCConnector] Write Bit Error ({device}): {e}")
            self.reconnect()

    def read_word(self, device):
        try:
            result = self.client.batchread_wordunits(headdevice=device, readsize=1)
            return int(result[0]) if result else 0
        except Exception as e:
            print(f"[PLCConnector] Read Word Error ({device}): {e}")
            self.reconnect()
            return 0

    def write_word(self, device, value):
        try:
            self.client.batchwrite_wordunits(headdevice=device, values=[int(value)])
        except Exception as e:
            print(f"[PLCConnector] Write Word Error ({device}): {e}")
            self.reconnect()

    def batch_read_bits(self, start_device, size):
        try:
            result = self.client.batchread_bitunits(headdevice=start_device, readsize=size)
            return [bool(val) for val in result]
        except Exception as e:
            print(f"[PLCConnector] Batch Read Bits Error ({start_device}, size={size}): {e}")
            self.reconnect()
            return [False] * size

    def batch_read_words(self, start_device, size):
        try:
            result = self.client.batchread_wordunits(headdevice=start_device, readsize=size)
            return [int(val) for val in result]
        except Exception as e:
            print(f"[PLCConnector] Batch Read Words Error ({start_device}, size={size}): {e}")
            self.reconnect()
            return [0] * size