import eel
import logging
from threading import Thread, Event
import sys

from input_manager import InputManager
from vnc import VNC
import random
import string
import psutil
import socket
import json

from chat import Chat
from video_manager import VideoManager

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)


status = 'None'
connection = 'None'
vnc = VNC()
input_manager = InputManager()
stop_thread = Event()
chat_manager = Chat()

# Video call: separate sender/receiver so both sides can stream
video_sender = VideoManager()
video_receiver = VideoManager()
video_send_thread = None
video_recv_thread = None
video_send_stop = Event()
video_recv_stop = Event()

vnc.disconnect_chat = chat_manager.disconnect_chat

eel.init('web')

@eel.expose
def display_recveive_message(msg):
    """
    msg may be a dict coming from Chat.receive_chat (we modified it to pass full message)
    Format: {"ip": "x.x.x.x", "msg": <string or JSON-string>}
    We look for signaling messages like {"type":"video_port","port":9001}
    """
    try:
        # msg might already be a dict
        data = msg
        if isinstance(msg, str):
            try:
                data = json.loads(msg)
            except Exception:
                data = msg

        # If it's the wrapper from chat: contains 'ip' and 'msg'
        if isinstance(data, dict) and 'msg' in data:
            sender_ip = data.get('from_ip') or data.get('ip')
            inner = data.get('msg')
            # try to parse inner
            try:
                inner_parsed = json.loads(inner) if isinstance(inner, str) else inner
            except Exception:
                inner_parsed = inner

            if isinstance(inner_parsed, dict) and inner_parsed.get('type') == 'video_port':
                # Host should connect to client's video server
                port = inner_parsed.get('port')
                if not port:
                    return
                # start a receiver thread to connect to sender_ip:port
                global video_recv_thread, video_receiver, video_recv_stop
                try:
                    if video_recv_thread and video_recv_thread.is_alive():
                        # already receiving; skip or restart
                        return
                    video_receiver.key = vnc.password if status == 'host' else vnc.requestPassword
                    video_receiver.nonce = vnc.nonce if status == 'host' else vnc.requestNonce
                    video_receiver.ip = sender_ip
                    video_receiver.port = port
                    video_recv_stop.clear()
                    def on_frame(b64):
                        eel.updateVideoFrame(b64)
                    video_recv_thread = Thread(target=video_receiver.receive_video, args=(video_recv_stop, on_frame))
                    video_recv_thread.daemon = True
                    video_recv_thread.start()
                except Exception as e:
                    logging.error(f"Lỗi khi khởi động receiver cho client video: {e}")
                return

            # otherwise treat as normal chat text
            try:
                text = inner_parsed if isinstance(inner_parsed, str) else str(inner_parsed)
                eel.show_message(text)
            except Exception:
                eel.show_message(str(inner))
            return

        # Fallback: display raw message
        eel.show_message(str(msg))
    except Exception as e:
        logging.error(f"Lỗi xử lý message chat: {e}")

@eel.expose
def close_chat_window():
    try:
        eel.closeChatWindow()
    except Exception as e:
        logging.error(f"Lỗi khi đóng cửa sổ chat: {e}")

@eel.expose
def open_chat_window(ip):
    try:
        eel.show(f"chat.html?client={ip}")
        logging.info("Đã mở cửa sổ chat.")
    except Exception as e:
        logging.error(f"Lỗi khi mở cửa sổ chat: {e}")

@eel.expose
def get_ip():
    ip = '127.0.0.1'
    for interface, addrs in psutil.net_if_addrs().items():
        if "VMware" in interface or "VirtualBox" in interface or "Loopback" in interface:
            continue
        for addr in addrs:
            if addr.family == socket.AF_INET and not addr.address.startswith("127.0.0.1") and not addr.address.startswith("169.254"):
                vnc.myIp = addr.address
                return addr.address
    return ip

@eel.expose
def get_password():
    if vnc.password != '':
        return vnc.password
    characters = string.ascii_letters + string.digits
    vnc.password = ''.join(random.choice(characters) for i in range(32))
    input_manager.key = vnc.password
    chat_manager.key = vnc.password
    vnc.nonce = ''.join(random.choice(characters) for i in range(16))
    input_manager.nonce = vnc.nonce
    chat_manager.nonce = vnc.nonce
    logging.debug(f"Send key={vnc.password} nonce={vnc.nonce}")
    return vnc.password

@eel.expose
def host():
    global status
    global vnc
    global transmit_thread
    global input_thread
    global input_manager
    global stop_thread
    global chat_manager
    global chat_thread
    # video globals: separate sender & receiver
    global video_sender, video_send_thread, video_send_stop
    global video_receiver, video_recv_thread, video_recv_stop

    if status == 'None':
        logging.info("Bắt đầu host...")
        status = 'host'
        stop_thread.clear()
        vnc.open_chat_window = open_chat_window
        transmit_thread = Thread(target=vnc.transmit_loop, args=[stop_thread])
        transmit_thread.daemon = True
        transmit_thread.start()

        input_thread = Thread(target=input_manager.receive_input, args=[stop_thread])
        input_thread.daemon = True
        input_thread.start()

        chat_manager.display_message=display_recveive_message
        chat_manager.status = 'host'

        chat_thread = Thread(target=chat_manager.receive_chat, args=[stop_thread])
        chat_thread.daemon = True
        chat_thread.start()

        stop_thread.clear()

        # Start video sender (host publishes its webcam on port 9000)
        video_sender.key = vnc.password
        video_sender.nonce = vnc.nonce
        video_sender.ip = '0.0.0.0'
        video_sender.port = 9000
        video_send_stop.clear()
        video_send_thread = Thread(target=video_sender.send_video, args=(video_send_stop,))
        video_send_thread.daemon = True
        video_send_thread.start()
        logging.debug("Host threads đã khởi chạy")
    elif status == 'host':
        status = 'None'
        chat_manager.status = ''
        logging.debug("Đang dừng host threads...")
        stop_thread.set()
        print("Gửi sự kiện dừng: " + str(stop_thread.is_set()))
        if input_thread and input_thread.is_alive():
            input_thread.join(timeout=0.3)
        if transmit_thread and transmit_thread.is_alive():
            transmit_thread.join(timeout=0.3)
        if chat_thread and chat_thread.is_alive():
            chat_thread.join(timeout=0.3)

        input_thread = None
        transmit_thread = None
        chat_thread = None
        chat_manager.disconnect_chat()
        logging.debug("Host threads đã dừng")

        # Stop video sender (host)
        try:
            video_send_stop.set()
            if video_send_thread and video_send_thread.is_alive():
                video_send_thread.join(timeout=0.3)
        except Exception:
            pass
        video_send_thread = None

@eel.expose
def stop_connect():
    global status
    global vnc
    global chat_manager
    status = 'None'
    try:
        vnc.stop_receive()
    except Exception as e:
        logging.error(f"Lỗi khi dừng kết nối VNC: {e}")

    try:
        input_manager.disconnect_input()
    except Exception as e:
        logging.error(f"Lỗi khi dừng kết nối input: {e}")

    try:
        chat_manager.disconnect_chat()
        chat_manager.status = ''
    except Exception as e:
        logging.error(f"Lỗi khi dừng kết nối chat: {e}")

    logging.info("Đã dừng kết nối đến host.")

@eel.expose
def connect(ip, requestPassword):
    global status
    global vnc
    global connection
    global chat_manager

    global video_receiver
    global video_recv_thread
    global video_recv_stop
    logging.info(f"Đang kết nối tới {ip}...")
    status = 'client'
    vnc.ip = ip
    input_manager.ip = ip
    chat_manager.ip = ip

    try:
        result = vnc.start_receive(requestPassword)
        if not result:
            raise Exception
        chat_manager.connect_chat()
        chat_manager.display_message=display_recveive_message
        chat_manager.status = 'client'

        input_manager.requestKey = vnc.requestPassword
        input_manager.requestNonce = vnc.requestNonce
        chat_manager.requestKey = vnc.requestPassword
        chat_manager.requestNonce = vnc.requestNonce
        input_manager.connect_input()

        chat_thread = Thread(target=chat_manager.receive_chat, args=[stop_thread, True])
        chat_thread.daemon = True
        chat_thread.start()

        connection = 'active'
        eel.show(f"connect.html?host={ip}")
        logging.info(f"Đã kết nối thành công tới {ip}")

        # Start video receive thread (client)
        video_receiver.key = vnc.requestPassword
        video_receiver.nonce = vnc.requestNonce
        video_receiver.ip = ip
        video_receiver.port = 9000
        video_recv_stop.clear()
        def on_frame_callback(b64):
            eel.updateVideoFrame(b64)
        video_recv_thread = Thread(target=video_receiver.receive_video, args=(video_recv_stop, on_frame_callback))
        video_recv_thread.daemon = True
        video_recv_thread.start()
        return True
    except Exception as e:
        logging.error(f"Lỗi khi kết nối tới {ip}: {e}")
        return False

@eel.expose
def start_video_call():
    global status, vnc
    global video_sender, video_receiver
    global video_send_thread, video_recv_thread
    global video_send_stop, video_recv_stop
    try:
        if status == 'host':
            # ensure host is sending (host() already starts sender), start if not
            if not (video_send_thread and video_send_thread.is_alive()):
                video_sender.key = vnc.password
                video_sender.nonce = vnc.nonce
                video_sender.ip = '0.0.0.0'
                video_sender.port = 9000
                video_send_stop.clear()
                video_send_thread = Thread(target=video_sender.send_video, args=(video_send_stop,))
                video_send_thread.daemon = True
                video_send_thread.start()
        elif status == 'client' and vnc.ip:
            # start client sender (listen for host to connect back) and notify host via chat
            if not (video_send_thread and video_send_thread.is_alive()):
                video_sender.key = vnc.requestPassword
                video_sender.nonce = vnc.requestNonce
                video_sender.ip = '0.0.0.0'
                # use 9001 for client->host stream
                video_sender.port = 9001
                video_send_stop.clear()
                video_send_thread = Thread(target=video_sender.send_video, args=(video_send_stop,))
                video_send_thread.daemon = True
                video_send_thread.start()
                # signal host to connect to our sender
                try:
                    chat_manager.send_chat_msg(json.dumps({"type": "video_port", "port": 9001}))
                except Exception as e:
                    logging.error(f"Không thể gửi tín hiệu video_port tới host: {e}")
            # ensure we're receiving host stream (connect() already starts receiver), otherwise start
            if not (video_recv_thread and video_recv_thread.is_alive()):
                video_receiver.key = vnc.requestPassword
                video_receiver.nonce = vnc.requestNonce
                video_receiver.ip = vnc.ip
                video_receiver.port = 9000
                video_recv_stop.clear()
                def on_frame_callback(b64):
                    eel.updateVideoFrame(b64)
                video_recv_thread = Thread(target=video_receiver.receive_video, args=(video_recv_stop, on_frame_callback))
                video_recv_thread.daemon = True
                video_recv_thread.start()
    except Exception as e:
        logging.error(f"Lỗi khi bật video call: {e}")

@eel.expose
def stop_video_call():
    global video_send_stop, video_recv_stop
    global video_send_thread, video_recv_thread
    try:
        # stop sending
        video_send_stop.set()
        if video_send_thread and video_send_thread.is_alive():
            video_send_thread.join(timeout=0.3)
        video_send_thread = None
        # stop receiving
        video_recv_stop.set()
        if video_recv_thread and video_recv_thread.is_alive():
            video_recv_thread.join(timeout=0.3)
        video_recv_thread = None
    except Exception as e:
        logging.error(f"Lỗi khi tắt video call: {e}")

@eel.expose
def transmit_input(data, event_type):
    try:
        if status == 'client':
            if event_type == 'keydown':
                input_manager.transmit_input(keydown=data)
            elif event_type == 'keyup':
                input_manager.transmit_input(keyup=data)
            elif event_type == 'mousemove':
                input_manager.transmit_input(mouse_pos=data)
            elif event_type == 'mousedown':
                input_manager.transmit_input(mouse_pos=data['pos'], mouse_down=data['button'])
            elif event_type == 'mouseup':
                input_manager.transmit_input(mouse_pos=data['pos'], mouse_up=data['button'])
            elif event_type == 'wheel':
                input_manager.transmit_input(wheel=data['deltaY'])
        logging.debug(f"Đã gửi input: {event_type} - {data}")
    except Exception as e:
        logging.error(f"Lỗi khi transmit input: {e}")

@eel.expose
def send_chat_message(msg):
    try:
        return chat_manager.send_chat_msg(msg)
    except Exception as e:
        logging.error(f"Lỗi khi gửi tin nhắn chat: {e}")
        return False

eel.start('index.html', block=False, port=8080, size=(595, 250))
logging.info("Ứng dụng Eel đã khởi động trên port 8080")

while True:
    try:
        if status == 'host':
            eel.updateScreen(vnc.image_serializer().decode())
        elif status == 'client' and connection == 'active':
            screen = vnc.receive()
            if screen is not None:
                eel.updateScreen(screen)
            else:
                eel.closeWindow()
        eel.sleep(.015)
    except Exception as e:
        logging.error(f"Lỗi vòng lặp chính: {e}")