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
        self.nonce = ''
        self.requestPassword = ''
        self.requestNonce = ''

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
        except (BrokenPipeError, ConnectionResetError) as e:
            logger.warning(f"Client ngắt kết nối: {e}")
        except OSError as e:
            if e.errno == 10054:
                logger.warning("Client đã đóng kết nối (WinError 10054)")
                raise e
            elif e.errno == 32:
                logger.warning("Client đã đóng kết nối (Broken pipe)")
                raise e
            else:
                logger.error(f"Lỗi send_msg không xác định: {e}")
                raise e
        except Exception as e:
            logger.error(f"Lỗi send_msg: {e}")
            raise

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

    def transmit(self, stop_event):
        """Server gửi màn hình liên tục cho client"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sender:
            try:
                sender.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sender.bind((self.ip, self.port))
                sender.listen()
                sender.settimeout(0.5)
                logger.info(f"VNC server đang chạy tại {self.ip}:{self.port}, chờ client...")
                conn = None
                addr = None
                while not stop_event.is_set():
                    try:
                        conn, addr = sender.accept()
                        break 
                    except socket.timeout:
                        continue
                    except Exception as e:
                        logger.error(f"Lỗi accept: {e}")
                        return

                if stop_event.is_set():
                    logger.info("receive_input thread stopped before client connected.")
                    return

                if conn is None:
                    logger.warning("Không thể thiết lập kết nối với input client.")
                    return

            except Exception as e:
                logger.error(f"Lỗi khi bind/listen VNC server: {e}")
                return

            with conn:
                try:
                    raw_msglen = self.recvall(conn, 4)
                    if not raw_msglen:
                        logger.warning("Client ngắt kêt nối khi đang xác thực")
                        return
                    msglen = struct.unpack('>I', raw_msglen)[0]
                    password_data = self.recvall(conn, msglen)
                    if not password_data:
                        logger.warning("Không nhận được mật khâu từ client")
                    client_password = password_data.decode('utf-8')
                    if client_password != self.password:
                        logger.warning("Mật khẩu không đúng")
                        try:
                            conn.sendall(b"AUTH_FAILED")
                        except:
                            pass
                        return
                    else:
                        self.nonce = self.nonce.encode('utf-8')
                        conn.sendall(b"AUTH_SUCCESS " + self.nonce)
                except Exception as e:
                    logger.warning(f"Lỗi mật khẩu: {e}")
                    return

                logger.info(f"VNC client đã kết nối: {addr}")
                while not stop_event.is_set():
                    try:
                        frame = self.image_serializer()
                        if frame is None:
                            continue
                        self.send_msg(conn, frame)
                        logger.debug("Đã gửi frame VNC")
                    except Exception as e:
                        logger.error(f"Lỗi vòng lặp transmit: {e}")
                        break

    def transmit_loop(self, stop_event):
        while not stop_event.is_set():
            self.transmit(stop_event)

    def stop_receive(self):
        try:
            self.conn.close()
        except Exception as e:
            logger.error(f"Lỗi đóng kết nối: {e}")

    def start_receive(self, password):
        """Client khởi động kết nối tới host"""
        try:
            self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.conn.connect((self.ip, self.port))
            password_bytes = password.encode('utf-8')
            raw_password = struct.pack('>I', len(password_bytes)) + password_bytes
            self.conn.sendall(raw_password)
            result = self.conn.recv(1024)
            if b"AUTH_SUCCESS" in result:
                self.requestNonce = result.split(b' ')[1]
                logger.info(f"VNC client đã kết nối tới host {self.ip}:{self.port}")
                return True
            else:
                logger.error("Xác thực thất bại — mật khẩu sai")
                self.conn.close()
                self.conn = None
                return False
        except Exception as e:
            logger.error(f"Lỗi start_receive: {e}")

    def receive(self):
        """Client nhận frame từ host"""
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