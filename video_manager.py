
import cv2
import threading
import socket
import struct
import base64
import time
import numpy as np
from chacha20_util import encrypt, decrypt

class VideoManager:
    def __init__(self, ip='0.0.0.0', port=9000, key='', nonce=''):
        self.ip = ip
        self.port = port
        self.key = key
        self.nonce = nonce
        self.conn = None
        self.running = False
        self.capture = None
        self.thread = None

    def start_capture(self):
        self.capture = cv2.VideoCapture(0)
        if not self.capture.isOpened():
            raise Exception('Cannot open webcam')

    def stop_capture(self):
        if self.capture:
            self.capture.release()
            self.capture = None

    def send_video(self, stop_event):
        self.start_capture()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((self.ip, self.port))
            s.listen(1)
            self.conn, addr = s.accept()
            while not stop_event.is_set():
                ret, frame = self.capture.read()
                if not ret:
                    continue
                _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                data = buffer.tobytes()
                if self.key and self.nonce:
                    data = encrypt(self.key, self.nonce, data)
                length = struct.pack('>I', len(data))
                try:
                    self.conn.sendall(length + data)
                except Exception:
                    break
                time.sleep(1/20)  # ~20 FPS
            self.conn.close()
        self.stop_capture()

    def receive_video(self, stop_event, on_frame_callback):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((self.ip, self.port))
            while not stop_event.is_set():
                raw_len = self.recvall(s, 4)
                if not raw_len:
                    break
                msglen = struct.unpack('>I', raw_len)[0]
                data = self.recvall(s, msglen)
                if self.key and self.nonce:
                    data = decrypt(self.key, self.nonce, data)
                frame = cv2.imdecode(
                    np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    _, jpg = cv2.imencode('.jpg', frame)
                    b64 = base64.b64encode(jpg.tobytes()).decode('utf-8')
                    on_frame_callback(b64)

    def recvall(self, sock, n):
        data = b''
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data += packet
        return data
