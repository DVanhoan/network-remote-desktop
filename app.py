import eel
import logging
from vnc import VNC
from threading import Thread
import atexit
import sys

from input_manager import InputManager
from vnc import VNC

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

eel.init('web')

@eel.expose
def host():
    global status
    global vnc
    global transmit_thread
    global input_manager

    logging.info("Bắt đầu host...")
    status = 'host'

    transmit_thread = Thread(target=vnc.transmit)
    transmit_thread.daemon = True
    transmit_thread.start()

    input_thread = Thread(target=input_manager.receive_input, args=[])
    input_thread.daemon = True
    input_thread.start()
    logging.debug("Host threads đã khởi chạy")

@eel.expose
def stop_host():
    global status
    status = 'None'
    logging.info("Đã dừng server host.")

@eel.expose
def connect(ip):
    global status
    global vnc
    global connection
    logging.info(f"Đang kết nối tới {ip}...")
    status = 'client'
    vnc.ip = ip
    input_manager.ip = ip
    try:
        vnc.start_receive()
        input_manager.connect_input()
        connection = 'active'
        logging.info(f"Đã kết nối thành công tới {ip}")
    except Exception as e:
        logging.error(f"Lỗi khi kết nối tới {ip}: {e}")

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
        logging.debug(f"Đã gửi input: {event_type} - {data}")
    except Exception as e:
        logging.error(f"Lỗi khi transmit input: {e}")

eel.start('index.html', block=False, port=8080)
logging.info("Ứng dụng Eel đã khởi động trên port 8080")

while True:
    try:
        if status == 'host':
            eel.updateScreen(vnc.image_serializer().decode())
        elif status == 'client' and connection == 'active':
            eel.updateScreen(vnc.receive())
        eel.sleep(.01)
    except Exception as e:
        logging.error(f"Lỗi vòng lặp chính: {e}")