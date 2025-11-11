import socket
import chacha20_util
import struct
import logging
import socket
import sounddevice as sd
import numpy as np
import time

logger = logging.getLogger(__name__)

class Audio:
    def __init__(self, ip='0.0.0.0', port=7003, myIp=None):
        self.ip = ip
        self.myIp = myIp
        self.port = port
        self.conn = None
        self.key = ''
        self.nonce = ''
        self.requestKey = ''
        self.requestNonce = ''
        self.status = ''
        self.myIp = myIp

    def recv_all(self, conn, length):
        data = b""
        while len(data) < length:
            packet = conn.recv(length - len(data))
            if not packet:
                return None
            data += packet
        return data
    
    def audio_serialize(self, audio_data):
        audio_data = np.array(audio_data, dtype=np.float32)
        return audio_data.tobytes()

    def audio_deserialize(self, data):
        audio_data = np.frombuffer(data, dtype=np.float32)
        return audio_data
    
    def recv_audio(self, conn):
        try:
            raw_length = self.recv_all(conn, 4)
            if not raw_length:
                return None
            msglen = struct.unpack('>I', raw_length)[0]
            encrypted_data = self.recv_all(conn, msglen)
            if self.status == 'host':
                decrypt = chacha20_util.decrypt(self.key, self.nonce, encrypted_data)
            elif self.status == 'client':
                decrypt = chacha20_util.decrypt(self.requestKey, self.requestNonce, encrypted_data)
            audio_data = self.audio_deserialize(decrypt)
            return audio_data
        except Exception as e:
            logger.error(f"Lỗi khi nhận dữ liệu âm thanh: {e}")
            return None
        
    def play_audio(self, audio_data, fs=44100):
        try:
            sd.play(audio_data, fs)
            sd.wait()
        except Exception as e:
            logger.error(f"Lỗi khi phát âm thanh: {e}")

    def send_audio(self, sock, audio_data):
        try:
            serialized_data = self.audio_serialize(audio_data)
            if self.status == 'client':
                encrypt = chacha20_util.encrypt(self.requestKey, self.requestNonce, serialized_data)
            elif self.status == 'host':
                encrypt = chacha20_util.encrypt(self.key, self.nonce, serialized_data)
            data = struct.pack('>I', len(encrypt)) + encrypt
            sock.sendall(data)
            logger.debug(f"Đã gửi dữ liệu âm thanh {len(serialized_data)} bytes")
        except Exception as e:
            logger.error(f"Lỗi khi gửi dữ liệu âm thanh: {e}")

    def record_audio(self, duration=1/10, fs=44100):
        try:
            audio_data = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='float32')
            sd.wait()
            return audio_data.flatten()
        except Exception as e:
            logger.error(f"Lỗi khi ghi âm thanh: {e}")
            return np.array([])
        
    def start_sending_audio(self, stop_event, toggle_audio, interval=2/10, fs=44100):
        while not stop_event.is_set():
            if not toggle_audio.is_set():
                time.sleep(interval)
                continue
            audio_data = self.record_audio(duration=interval, fs=fs)
            if audio_data.size > 0:
                self.send_audio(self.conn, audio_data)

    def receive_audio(self, stop_event, client_mode = False):
        if client_mode:
            logger.info(f"Đã kết nối đến audio host: {self.ip}")

            while not stop_event.is_set() and self.conn is not None:
                try:
                    audio_data = self.recv_audio(self.conn)
                    if audio_data is not None:
                        self.play_audio(audio_data)
                except Exception as e:
                    logger.error(f"Lỗi khi nhận dữ liệu âm thanh: {e}")
                    break
        else:
            logger.info(f"Đang chờ kết nối audio từ client...")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listner:
                try:
                    listner.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    listner.bind((self.ip, self.port))
                    listner.listen()
                    listner.settimeout(0.5)
                except Exception as e:
                    logger.error(f"Lỗi khi bind/listen receive_audio: {e}")
                    return
                while not stop_event.is_set():
                    self.conn = None
                    try:
                        while not stop_event.is_set():
                            try:
                                self.conn, addr = listner.accept()
                                break
                            except socket.timeout:
                                continue
                            except Exception as e:
                                logger.error(f"Lỗi accept audio: {e}")
                                return
                        if self.conn == None:
                            logger.debug(f"Dừng kết nối receive_audio")
                            return
                    except Exception as e:
                        logger.error(f"Lỗi vòng lặp receive_audio (host): {e}")
                        break

                    with self.conn:
                        logger.info(f"Audio client đã kết nối: {addr}")
                        while not stop_event.is_set():
                            try:
                                audio_data = self.recv_audio(self.conn)
                                if audio_data is not None:
                                    self.play_audio(audio_data)
                            except Exception as e:
                                logger.error(f"Lỗi khi nhận dữ liệu âm thanh: {e}")
                                break

    def connect_audio(self):
        try:
            if self.conn:
                try:
                    self.conn.close()
                except:
                    pass
            self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.conn.connect((self.ip, self.port))
            logger.info(f"Đã kết nối đến audio host: {self.ip}")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi kết nối đến audio host: {e}")
            return False
        
    def disconnect_audio(self):
        try:
            if self.conn:
                self.conn.close()
                self.conn = None
                logger.info("Đã ngắt kết nối audio")
        except Exception as e:
            logger.error(f"Lỗi khi ngắt kết nối audio: {e}")