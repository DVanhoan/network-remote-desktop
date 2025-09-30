import socket
import chacha20_util
import struct
import logging
import socket
import json

logger = logging.getLogger(__name__)

class Chat:
    def __init__(self, ip='0.0.0.0', port=7001, myIp=None, display_message=None):
        self.ip = ip
        self.myIp = myIp
        self.port = port
        self.conn = None
        self.key = ''
        self.nonce = ''
        self.requestKey = ''
        self.requestNonce = ''
        self.status = ''
        self.myIp = ''
        self.display_message = display_message

    def recv_all(self, conn, length):
        data = b""
        while len(data) < length:
            packet = conn.recv(length - len(data))
            if not packet:
                return None
            data += packet
        return data

    def recv_msg(self):
        try:
            raw_length = self.recv_all(self.conn, 4)
            if not raw_length:
                return None
            msglen = struct.unpack('>I', raw_length)[0]
            encrypted_data = self.recv_all(self.conn, msglen)
            if self.status == 'host':
                decrypt = chacha20_util.decrypt(self.key, self.nonce, encrypted_data)
                return decrypt
            elif self.status == 'client':
                decrypt = chacha20_util.decrypt(self.requestKey, self.requestNonce, encrypted_data)
                return decrypt
        except Exception as e:
            logger.error(f"Lỗi khi nhân chat message: {e}")
            return None

    def send_msg(self, sock, msg):
        try:
            if self.status == 'client':
                encrypt = chacha20_util.encrypt(self.requestKey, self.requestNonce, msg)
            elif self.status == 'host':
                encrypt = chacha20_util.encrypt(self.key, self.nonce, msg)
            data = struct.pack('>I', len(encrypt)) + encrypt
            sock.sendall(data)
            logger.debug(f"Đã gửi chat message {len(msg)} bytes")
        except Exception as e:
            logger.error(f"Lỗi khi gửi chat message: {e}")

    def receive_chat(self, stop_event, client_mode = False):
        if client_mode:
            logger.info(f"Đã kết nối đến chat host: {self.ip}")

            while not stop_event.is_set() and self.conn is not None:
                try:
                    raw_msg = self.recv_msg()
                    raw_msg = json.loads(raw_msg.decode('utf-8'))
                    msg_data = raw_msg
                    if not raw_msg:
                        logger.error(f"Mất kết nối chat")
                        break
                    logger.debug(f"Đã nhận message: {msg_data}")
                    if self.display_message:
                        self.display_message(msg_data['msg'])
                except Exception as e:
                    logger.error(f"Lỗi vòng lặp receive_chat (client): {e}")
                    break
        else:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
                try:
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    listener.bind((self.ip, self.port))
                    listener.listen()
                    listener.settimeout(0.5)
                except Exception as e:
                    logger.error(f"Lỗi khi bind/listen receive_input: {e}")
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
                                logger.error(f"Lỗi accept: {e}")
                                return
                        if self.conn == None:
                            logger.debug(f"Dừng kết nối receive_chat")
                            return
                    except Exception as e:
                        logger.error(f"Lỗi khi accept client chat: {e}")
                    
                    with self.conn:
                        logger.info(f"Chat client đã kết nối: {addr}")

                        while not stop_event.is_set():
                            try:
                                raw_msg = self.recv_msg()
                                raw_msg = json.loads(raw_msg.decode('utf-8'))
                                msg_data = raw_msg
                                if not raw_msg:
                                    logger.error(f"Mất kết nối chat")
                                    break
                                logger.debug(f"Đã nhận message: {msg_data}")
                                if self.display_message:
                                    self.display_message(msg_data['msg'])
                            except Exception as e:
                                logger.error(f"Lỗi vòng lặp receive_chat (host): {e}")
                                break

    def send_chat_msg(self, msg):
        try:
            data = {"ip": self.ip, "msg": msg}
            self.send_msg(self.conn, json.dumps(data).encode())
            logger.info(f"Đã gửi chat message: {data}")
            return True
        except Exception as e:
            logger.error(f"Lỗi send_chat_msg: {e}")
            return False

    def connect_chat(self):
        try:
            if self.conn:
                try:
                    self.conn.close()
                except:
                    pass
                self.conn = None
            self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.conn.connect((self.ip, self.port))
            logger.debug(f"Đã kết nối chat đến host: {self.ip}, {self.port}")
        except Exception as e:
            self.conn.close()
            self.conn = None
            logger.error(f"Lỗi connect_chat: {e}")

    def disconnect_chat(self):
        try:
            self.conn.close()
            self.conn = None
        except Exception as e:
            logger.warning(f"Lỗi khi đóng kết nối chat")
