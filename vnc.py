from PIL import Image
from io import BytesIO
import socket
import mss
import base64
import struct
import time
import logging

logger = logging.getLogger(__name__)

class VNC:

    def __init__(self, ip='0.0.0.0', port=7000):
        self.ip = ip
        self.port = port
        self.conn = None
        self.password = ''
        self.requestPassword = ''

    # ---------------- Screenshot helpers ----------------

    def screenshot(self):
        try:
            with mss.mss() as sct:
                img = sct.grab(sct.monitors[1])
            return self.rgba_to_rgb(img)
        except Exception as e:
            logger.error(f"Lỗi khi chụp màn hình: {e}")
            return None

    def rgba_to_rgb(self, image):
        try:
            return Image.frombytes('RGB', image.size, image.bgra, 'raw', 'BGRX')
        except Exception as e:
            logger.error(f"Lỗi convert RGBA->RGB: {e}")
            return None

    def image_serializer(self, resolution=(1800, 900)):
        try:
            image = self.screenshot()
            if image is None:
                return None
            image = image.resize(resolution, Image.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format='jpeg')
            data_string = base64.b64encode(buffer.getvalue())
            logger.debug(f"Đã serialize ảnh ({len(data_string)} bytes)")
            return data_string
        except Exception as e:
            logger.error(f"Lỗi serialize ảnh: {e}")
            return None

    def image_deserializer(self, image_string):
        try:
            return Image.open(BytesIO(base64.b64decode(image_string)))
        except Exception as e:
            logger.error(f"Lỗi deserialize ảnh: {e}")
            return None

    # ---------------- Socket helpers ----------------

    def send_msg(self, sock, msg):
        try:
            msg = struct.pack('>I', len(msg)) + msg
            sock.sendall(msg)
            logger.debug(f"Đã gửi message ({len(msg)} bytes)")
        except Exception as e:
            logger.error(f"Lỗi send_msg: {e}")

    def recv_msg(self, sock):
        try:
            raw_msglen = self.recvall(sock, 4)
            if not raw_msglen:
                return None
            msglen = struct.unpack('>I', raw_msglen)[0]
            return self.recvall(sock, msglen)
        except Exception as e:
            logger.error(f"Lỗi recv_msg: {e}")
            return None

    def recvall(self, sock, n):
        data = b''
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data += packet
        return data

    # ---------------- Network roles ----------------

    def transmit(self):
        """Server gửi màn hình liên tục cho client"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sender:
            try:
                sender.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sender.bind((self.ip, self.port))
                sender.listen()
                logger.info(f"VNC server đang chạy tại {self.ip}:{self.port}, chờ client...")
                conn, addr = sender.accept()
            except Exception as e:
                logger.error(f"Lỗi khi bind/listen VNC server: {e}")
                return

            with conn:
                logger.info(f"VNC client đã kết nối: {addr}")
                while True:
                    try:
                        frame = self.image_serializer()
                        if frame is None:
                            continue
                        self.send_msg(conn, frame)
                        logger.debug("Đã gửi frame VNC")
                    except Exception as e:
                        logger.error(f"Lỗi vòng lặp transmit: {e}")
                        break

    def start_receive(self, password):
        """Client khởi động kết nối tới server"""
        try:
            self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if password != self.password:
                raise Exception
            self.requestPassword = password
            self.conn.connect((self.ip, self.port))
            logger.info(f"VNC client đã kết nối tới server {self.ip}:{self.port}")
        except Exception as e:
            logger.error(f"Lỗi start_receive: {e}")

    def receive(self):
        """Client nhận frame từ server"""
        try:
            data_string = self.recv_msg(self.conn)
            if data_string:
                logger.debug(f"Đã nhận frame ({len(data_string)} bytes)")
                return data_string.decode()
            else:
                logger.warning("Mất kết nối VNC hoặc frame rỗng")
                return None
        except Exception as e:
            logger.error(f"Lỗi receive VNC: {e}")
            return None
