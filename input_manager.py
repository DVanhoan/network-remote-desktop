import socket
import time
import pyautogui
import struct
import logging
from pynput import mouse, keyboard
import chacha20_util

logger = logging.getLogger(__name__)

class InputManager:

    def __init__(self, ip='0.0.0.0', port=6969):
        self.input = {
            "mouse_pos": [0.0, 0.0],
            "lmb": False,
            "rmb": False,
            "keys": [],
        }
        self.ip = ip
        self.key = None
        self.nonce = None
        self.requestKey = None
        self.requestNonce = None
        self.port = port
        self.conn = None
        self.width, self.height = (0, 0)

    # ---------------- Socket helpers ----------------

    def send_msg(self, sock, msg):
        try:
            encrypt = chacha20_util.encrypt(self.requestKey, self.requestNonce, msg)
            data = struct.pack('>I', len(encrypt)) + encrypt
            sock.sendall(data)
            logger.debug(f"Đã gửi message {len(msg)} bytes")
        except Exception as e:
            logger.error(f"Lỗi khi gửi message: {e}")

    def recv_msg(self, sock):
        try:
            raw_msglen = self.recvall(sock, 4)
            if not raw_msglen:
                return None
            msglen = struct.unpack('>I', raw_msglen)[0]
            encrypted_data = self.recvall(sock, msglen)
            decrypt = chacha20_util.decrypt(self.key, self.nonce, encrypted_data)
            return decrypt
        except Exception as e:
            logger.error(f"Lỗi khi nhận message: {e}")
            return None
    
    def recvall(self, sock, n):
        data = b''
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data += packet
        return data

    # ---------------- Event handling ----------------

    def set_resolution(self, width=1280, height=720):
        self.width = width
        self.height = height
        logger.info(f"Set resolution: {self.width}x{self.height}")

    def motion(self, event):
        self.input["mouse_pos"] = [event.x/self.width, event.y/self.height]
        self.send_msg(self.conn, str(self.input).encode())

    def key_pressed(self, event):
        try:
            logger.debug(f"Key Press: {repr(event.char)}")
            self.input["keys"].append(repr(event.char))
            self.input["keys"] = list(set(self.input["keys"]))
            self.send_msg(self.conn, str(self.input).encode())
        except Exception as e:
            logger.error(f"Lỗi key_pressed: {e}")
    
    def key_released(self, event):
        try:
            logger.debug(f"Key Released: {repr(event.char)}")
            if repr(event.char) in self.input["keys"]:
                self.input["keys"].remove(repr(event.char))
            self.send_msg(self.conn, str(self.input).encode())
        except Exception as e:
            logger.error(f"Lỗi key_released: {e}")

    def left_click_pressed(self, event):
        self.input["mouse_pos"] = [event.x/self.width, event.y/self.height]
        self.input["lmb"] = True
        self.send_msg(self.conn, str(self.input).encode())

    def left_click_released(self, event):
        self.input["mouse_pos"] = [event.x/self.width, event.y/self.height]
        self.input["lmb"] = False
        self.send_msg(self.conn, str(self.input).encode())

    def right_click_pressed(self, event):
        self.input["mouse_pos"] = [event.x/self.width, event.y/self.height]
        self.input["rmb"] = True
        self.send_msg(self.conn, str(self.input).encode())

    def right_click_released(self, event):
        self.input["mouse_pos"] = [event.x/self.width, event.y/self.height]
        self.input["rmb"] = False
        self.send_msg(self.conn, str(self.input).encode())

    # ---------------- Network roles ----------------

    def transmit(self):
        try:
            self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.conn.connect((self.ip, self.port))
            logger.info(f"Đã kết nối tới server input {self.ip}:{self.port}")
        except Exception as e:
            logger.error(f"Lỗi transmit(): {e}")

    def receive(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sender:
            try:
                sender.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sender.bind((self.ip, self.port))
                sender.listen()
                logger.info(f"Đang chờ kết nối input tại {self.ip}:{self.port}...")
                conn, addr = sender.accept()
            except Exception as e:
                logger.error(f"Lỗi khi bind/listen: {e}")
                return

            with conn:
                logger.info(f"Client input đã kết nối: {addr}")

                width, height = pyautogui.size()
                mouse_var = mouse.Controller()
                keyboard_var = keyboard.Controller()
                last_mouse_input = [0, 0]

                while True:
                    try:
                        raw_data = self.recv_msg(conn)
                        if not raw_data:
                            logger.warning("Mất kết nối input")
                            break
                        received_input = eval(raw_data.decode())
                        logger.debug(f"Nhận input: {received_input}")

                        # Mouse
                        mouse_input = received_input["mouse_pos"]
                        mouse_input[0] *= width
                        mouse_input[1] *= height
                        if mouse_input != last_mouse_input:
                            mouse_var.position = tuple(mouse_input)
                            last_mouse_input = mouse_input

                        if received_input['lmb']:
                            mouse_var.click(mouse.Button.left)
                            logger.debug("Click LMB")
                        if received_input['rmb']:
                            mouse_var.click(mouse.Button.right)
                            logger.debug("Click RMB")
                        if received_input['wheel']:
                            mouse_var.scroll(dx=0, dy=120)
                            logger.debug("Mouse scroll")

                        # Keyboard
                        for k in received_input['keys']:
                            try:
                                keyboard_var.press(str(eval(k)))
                                logger.debug(f"Key press: {k}")
                            except Exception:
                                pass

                    except Exception as e:
                        logger.error(f"Lỗi vòng lặp receive: {e}")
                        break

    # ---------------- EEL roles ----------------

    def connect_input(self):
        try:
            if self.conn:
                try:
                    self.conn.close()
                except:
                    pass
                self.conn = None
            self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.conn.connect((self.ip, self.port))
            logger.info(f"Đã kết nối tới input server {self.ip}:{self.port}")
        except Exception as e:
            self.conn.close()
            self.conn = None
            logger.error(f"Lỗi connect_input: {e}")

    def disconnect_input(self):
        try:
            self.conn.close()
            self.conn = None
            logger.info(f"Đã ngắt kết nối tới input host {self.ip}:{self.port}")
        except Exception as e:
            logger.error(f"Lỗi disconnect_input: {e}")

    def transmit_input(self, mouse_pos=None, mouse_down=None, mouse_up=None, keydown=None, keyup=None, wheel=None):
        try:
            key_input = {
                "mouse_pos": mouse_pos,
                "mouse_down": mouse_down,
                "mouse_up": mouse_up,
                "keydown": keydown,
                "keyup": keyup,
                "wheel": wheel
            }
            self.send_msg(self.conn, str(key_input).encode())
            logger.debug(f"Đã gửi input: {key_input}")
        except Exception as e:
            logger.error(f"Lỗi transmit_input: {e}")

    def receive_input(self, stop_event):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sender:
            try:
                sender.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sender.bind((self.ip, self.port))
                sender.listen()
                sender.settimeout(0.5)
                logger.info(f"Đang chờ input client tại {self.ip}:{self.port}...")
            except Exception as e:
                logger.error(f"Lỗi khi bind/listen receive_input: {e}")
                return
            
            while not stop_event.is_set():
                conn = None
                try:
                    while not stop_event.is_set():
                        try:
                            conn, addr = sender.accept()
                            break
                        except socket.timeout:
                            continue
                        except Exception as e:
                            logger.error(f"Lỗi accept: {e}")
                            return
                    if conn == None:
                        logger.debug(f"Dừng kết nối receive_input")
                        return
                except Exception as e:
                    logger.error(f"Lỗi khi accept client: {e}")
                    return

                with conn:
                    logger.info(f"Input client đã kết nối: {addr}")

                    width, height = pyautogui.size()
                    mouse_controller = mouse.Controller()
                    keyboard_controller = keyboard.Controller()

                    while not stop_event.is_set():
                        try:
                            raw_data = self.recv_msg(conn)
                            if not raw_data:
                                logger.warning("Mất kết nối input client")
                                break

                            received_input = eval(raw_data.decode())
                            logger.debug(f"Nhận input: {received_input}")

                            mouse_input = received_input['mouse_pos']
                            wheel_input = received_input['wheel']
                            if mouse_input:
                                mouse_input[0] *= width
                                mouse_input[1] *= height
                                mouse_controller.position = tuple(mouse_input)

                            if received_input['mouse_down'] == 0:
                                mouse_controller.press(mouse.Button.left)
                            if received_input['mouse_up'] == 0:
                                mouse_controller.release(mouse.Button.left)

                            if received_input['mouse_down'] == 1:
                                mouse_controller.press(mouse.Button.middle)
                            if received_input['mouse_up'] == 1:
                                mouse_controller.release(mouse.Button.middle)

                            if received_input['mouse_down'] == 2:
                                mouse_controller.press(mouse.Button.right)
                            if received_input['mouse_up'] == 2:
                                mouse_controller.release(mouse.Button.right)

                            if received_input['wheel']:
                                mouse_controller.scroll(dx=0, dy=-180/wheel_input)

                            if received_input['keydown']:
                                keyboard_controller.press(keyboard.KeyCode(received_input['keydown']))
                            if received_input['keyup']:
                                keyboard_controller.release(keyboard.KeyCode(received_input['keyup']))

                        except Exception as e:
                            logger.error(f"Lỗi vòng lặp receive_input: {e}")
                            break

                logger.info("Client input đã ngắt kết nối — chuẩn bị accept client mới...")