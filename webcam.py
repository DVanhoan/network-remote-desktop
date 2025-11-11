import socket
import time
import chacha20_util
import struct
import logging
import socket
import cv2
import numpy as np
import base64
import eel

logger = logging.getLogger(__name__)

class Webcam:
    def __init__(self, ip='0.0.0.0', port=7002, myIp=None, display_frame=None, display_frame_2=None):
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
        self.display_frame = display_frame
        self.display_frame_2 = display_frame_2

    def image_serialize(self, frame):
        _, buffer = cv2.imencode('.jpg', frame)
        return base64.b64encode(buffer).decode('utf-8')
    
    def image_deserialize(self, data):
        img_data = base64.b64decode(data)
        nparr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return frame

    def recv_all(self, conn, length):
        data = b""
        while len(data) < length:
            packet = conn.recv(length - len(data))
            if not packet:
                return None
            data += packet
        return data
    
    def recv_frame(self, conn):
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
            return decrypt.decode('utf-8')
        except Exception as e:
            logger.error(f"Lỗi recv_frame webcam: {e}")
            return None
        
    def send_frame(self, sock, frame):
        try:
            data = self.image_serialize(frame).encode('utf-8')
            if self.status == 'client':
                encrypt = chacha20_util.encrypt(self.requestKey, self.requestNonce, data)
            elif self.status == 'host':
                encrypt = chacha20_util.encrypt(self.key, self.nonce, data)
            packet = struct.pack('>I', len(encrypt)) + encrypt
            sock.sendall(packet)
            # logger.debug(f"Đã gửi frame webcam {len(data)} bytes")
        except Exception as e:
            logger.error(f"Lỗi khi gửi frame webcam: {e}")

    def receive_webcam(self, stop_event, client_mode = False):
        if client_mode:
            logger.info(f"Đã kết nối đến webcam host: {self.ip}")

            while not stop_event.is_set() and self.conn is not None:
                try:
                    frame = self.recv_frame(self.conn)
                    if frame is not None and self.display_frame_2 is not None:
                            self.display_frame_2(frame)
                except Exception as e:
                    logger.error(f"Lỗi receive_webcam: {e}")
                    break
        else:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                try:
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    listener.bind((self.ip, self.port))
                    listener.listen()
                    listener.settimeout(0.5)
                except Exception as e:
                    logger.error(f"Lỗi khi bind/listen receive_webcam: {e}")
                    return
                
                while not stop_event.is_set():
                    self.conn = None
                    try:
                        while not stop_event.is_set():
                            try:
                                self.conn, addr = listener.accept()
                                break
                            except socket.timeout:
                                continue
                            except Exception as e:
                                logger.error(f"Lỗi accept chat: {e}")
                                return
                        if self.conn == None:
                            logger.debug(f"Dừng kết nối receive_webcam")
                            return
                    except Exception as e:
                        logger.error(f"Lỗi vòng lặp receive_webcam (host): {e}")
                        break
                    
                    with self.conn:
                        logger.info(f"Kết nối webcam từ {addr}")
                        while not stop_event.is_set():
                            try:
                                frame = self.recv_frame(self.conn)
                                if frame is not None and self.display_frame is not None:
                                    self.display_frame(frame)
                            except Exception as e:
                                logger.error(f"Lỗi receive_webcam: {e}")
                                break

    def start_webcam_stream(self, stop_event, toggle_webcam=False):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            logger.error("Không thể mở webcam")
            return
        while not stop_event.is_set():
            if self.conn is None:
                time.sleep(0.2)
                continue
            ret, frame = cap.read()
            if not ret:
                logger.error("Không thể đọc frame từ webcam")
                break
            if toggle_webcam:
                frame = cv2.flip(frame, 1)
                try:
                    if toggle_webcam.is_set() and self.display_frame is not None and self.display_frame_2 is not None:
                        self.send_frame(self.conn, frame)
                        if self.status == 'client':
                            self.display_frame(self.image_serialize(frame))
                        elif self.status == 'host':
                            self.display_frame_2(self.image_serialize(frame))
                except Exception as e:
                    logger.error(f"Lỗi khi gửi frame webcam: {e}")
        cap.release()

    def connect_webcam(self):
        try:
            if self.conn:
                try:
                    self.conn.close()
                except:
                    pass
            self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.conn.connect((self.ip, self.port))
            logger.info(f"Đã kết nối đến webcam host: {self.ip}")
            return True
        except Exception as e:
            logger.error(f"Lỗi khi kết nối đến webcam host: {e}")
            return False
        
    def disconnect_webcam(self):
        try:
            if self.conn:
                self.conn.close()
                self.conn = None
                logger.info("Đã ngắt kết nối webcam")
        except Exception as e:
            logger.error(f"Lỗi khi ngắt kết nối webcam: {e}")
