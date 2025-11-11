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
from chat import Chat
from audio import Audio
from webcam import Webcam

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
toggle_audio = Event()
toggle_webcam = Event()
toggle_webcam.clear()
chat_manager = Chat()
audio_manager = Audio()
webcam_manager = Webcam()

vnc.disconnect_chat = chat_manager.disconnect_chat

eel.init('template')

@eel.expose
def display_recveive_message(msg):
    eel.show_message(msg)

@eel.expose
def toggle_audio_func():
    if toggle_audio.is_set():
        toggle_audio.audio.clear()
    else:
        toggle_audio.set()

@eel.expose
def toggle_webcam_func():
    print("Toggle webcam called")
    if toggle_webcam.is_set():
        toggle_webcam.clear()
    else:
        toggle_webcam.set()

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
    webcam_manager.key = vnc.password
    webcam_manager.nonce = vnc.nonce
    audio_manager.key = vnc.password
    audio_manager.nonce = vnc.nonce
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
    global audio_manager
    global audio_sending_thread
    global audio_receiving_thread
    global webcam_manager
    global webcam_sending_thread
    global webcam_receiving_thread

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
        chat_manager.close_chat_window = close_chat_window
        chat_manager.status = 'host'

        chat_thread = Thread(target=chat_manager.receive_chat, args=[stop_thread])
        chat_thread.daemon = True
        chat_thread.start()

        audio_manager.status = 'host'
        audio_receiving_thread = Thread(target=audio_manager.start_sending_audio, args=[stop_thread, toggle_audio])
        audio_receiving_thread.daemon = True
        audio_receiving_thread.start()

        audio_sending_thread = Thread(target=audio_manager.receive_audio, args=[stop_thread])
        audio_sending_thread.daemon = True
        audio_sending_thread.start()

        webcam_manager.status = 'host'
        webcam_manager.display_frame = lambda frame: eel.updateClientWebcam(frame)
        webcam_manager.display_frame_2 = lambda frame: eel.updateHostWebcam(frame)
        webcam_receiving_thread = Thread(target=webcam_manager.receive_webcam, args=[stop_thread])
        webcam_receiving_thread.daemon = True
        webcam_receiving_thread.start()

        webcam_sending_thread = Thread(target=webcam_manager.start_webcam_stream, args=[stop_thread, toggle_webcam])
        webcam_sending_thread.daemon = True
        webcam_sending_thread.start()

        stop_thread.clear()

        logging.debug("Host threads đã khởi chạy")
    elif status == 'host':
        status = 'None'
        chat_manager.status = ''
        audio_manager.status = ''
        webcam_manager.status = ''
        logging.debug("Đang dừng host threads...")
        stop_thread.set()
        print("Gửi sự kiện dừng: " + str(stop_thread.is_set()))
        if input_thread and input_thread.is_alive():
            input_thread.join(timeout=0.3)
        if transmit_thread and transmit_thread.is_alive():
            transmit_thread.join(timeout=0.3)
        if chat_thread and chat_thread.is_alive():
            chat_thread.join(timeout=0.3)
        if audio_sending_thread and audio_sending_thread.is_alive():
            audio_sending_thread.join(timeout=0.3)
            audio_receiving_thread.join(timeout=0.3)
        if webcam_sending_thread and webcam_sending_thread.is_alive():
            webcam_sending_thread.join(timeout=0.3)
            webcam_receiving_thread.join(timeout=0.3)

        input_thread = None
        transmit_thread = None
        chat_thread = None
        chat_manager.disconnect_chat()
        logging.debug("Host threads đã dừng")

@eel.expose
def stop_connect():
    global status
    global vnc
    global chat_manager
    global stop_thread
    status = 'None'
    stop_thread.set()
    toggle_audio.clear()
    toggle_webcam.clear()
    try:
        vnc.stop_receive()
    except Exception as e:
        logging.error(f"Lỗi khi dừng kết nối VNC: {e}")

    try:
        input_manager.disconnect_input()
    except Exception as e:
        logging.error(f"Lỗi khi dừng kết nối input: {e}")

    try:
        audio_manager.disconnect_audio()
        audio_manager.status = ''
    except Exception as e:
        logging.error(f"Lỗi khi dừng kết nối audio: {e}")

    try:
        webcam_manager.disconnect_webcam()
        webcam_manager.status = ''
    except Exception as e:
        logging.error(f"Lỗi khi dừng kết nối webcam: {e}")

    try:
        chat_manager.disconnect_chat()
        chat_manager.status = ''
    except Exception as e:
        logging.error(f"Lỗi khi dừng kết nối chat: {e}")

    logging.info("Đã dừng kết nối đến host.")
    stop_thread.clear()

@eel.expose
def connect(ip, requestPassword):
    global status
    global vnc
    global connection
    global chat_manager
    global audio_manager
    global audio_sending_thread
    global audio_receiving_thread
    global webcam_manager
    global webcam_sending_thread
    global webcam_receiving_thread
    
    logging.info(f"Đang kết nối tới {ip}...")
    status = 'client'
    vnc.ip = ip
    input_manager.ip = ip
    chat_manager.ip = ip
    webcam_manager.ip = ip
    audio_manager.ip = ip

    try:
        result = vnc.start_receive(requestPassword)
        if not result:
            raise Exception
        chat_manager.connect_chat()
        chat_manager.display_message=display_recveive_message
        chat_manager.status = 'client'

        audio_manager.connect_audio()
        audio_manager.status = 'client'

        webcam_manager.connect_webcam()
        webcam_manager.display_frame = lambda frame: eel.updateClientWebcam(frame)
        webcam_manager.display_frame_2 = lambda frame: eel.updateHostWebcam(frame)
        webcam_manager.status = 'client'

        input_manager.requestKey = vnc.requestPassword
        input_manager.requestNonce = vnc.requestNonce
        chat_manager.requestKey = vnc.requestPassword
        chat_manager.requestNonce = vnc.requestNonce
        webcam_manager.requestKey = vnc.requestPassword
        webcam_manager.requestNonce = vnc.requestNonce
        audio_manager.requestKey = vnc.requestPassword
        audio_manager.requestNonce = vnc.requestNonce
        chat_manager.close_chat_window = close_chat_window
        input_manager.connect_input()

        chat_thread = Thread(target=chat_manager.receive_chat, args=[stop_thread, True])
        chat_thread.daemon = True
        chat_thread.start()

        webcam_sending_thread = Thread(target=webcam_manager.start_webcam_stream, args=[stop_thread, toggle_webcam])
        webcam_sending_thread.daemon = True
        webcam_sending_thread.start()

        webcam_receiving_thread = Thread(target=webcam_manager.receive_webcam, args=[stop_thread, True])
        webcam_receiving_thread.daemon = True
        webcam_receiving_thread.start()

        connection = 'active'
        eel.show(f"connect.html?host={ip}")
        logging.info(f"Đã kết nối thành công tới {ip}")
        return True
    except Exception as e:
        logging.error(f"Lỗi khi kết nối tới {ip}: {e}")
        return False

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
        # logging.debug(f"Đã gửi input: {event_type} - {data}")
    except Exception as e:
        logging.error(f"Lỗi khi transmit input: {e}")

@eel.expose
def send_chat_message(msg):
    try:
        return chat_manager.send_chat_msg(msg)
    except Exception as e:
        logging.error(f"Lỗi khi gửi tin nhắn chat: {e}")
        return False

eel.start('index.html', block=False, port=8080, size=(595, 200))
logging.info("Ứng dụng Eel đã khởi động trên port 8080")

while True:
    try:
        if status == 'client' and connection == 'active':
            screen = vnc.receive()
            if screen is not None:
                eel.updateScreen(screen)
        eel.sleep(.015)
    except Exception as e:
        logging.error(f"Lỗi vòng lặp chính: {e}")