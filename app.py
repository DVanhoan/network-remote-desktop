import eel
import logging
from vnc import VNC
from threading import Thread
import sys

from input_manager import InputManager
from vnc import VNC
import random
import netifaces

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
def get_ip():
    ip = "127.0.0.1"
    try:
        gws = netifaces.gateways()
        default_gateway = gws.get('default', {}).get(netifaces.AF_INET)
        if default_gateway:
            gateway_ip, interface = default_gateway
            addresses = netifaces.ifaddresses(interface)
            ip_info = addresses.get(netifaces.AF_INET)
            if ip_info:
                ip = ip_info[0]['addr']
    except Exception:
        pass
    return ip

@eel.expose
def get_password():
    vnc.password = random.randbytes(8).hex()
    return vnc.password

@eel.expose
def host():
    global status
    global vnc
    global transmit_thread
    global input_manager

    if status == 'None':
        logging.info("Bắt đầu host...")
        status = 'host'

        transmit_thread = Thread(target=vnc.transmit)
        transmit_thread.daemon = True
        transmit_thread.start()

        input_thread = Thread(target=input_manager.receive_input, args=[])
        input_thread.daemon = True
        input_thread.start()
        logging.debug("Host threads đã khởi chạy")
    elif status == 'host':
        logging.debug("Đang tắt kết nối...")
        status = 'None'

        if vnc.conn:
            vnc.conn.close()
            vnc.conn = None

@eel.expose
def stop_host():
    global status
    status = 'None'
    logging.info("Đã dừng server host.")

@eel.expose
def connect(ip, requestPassword):
    global status
    global vnc
    global connection
    logging.info(f"Đang kết nối tới {ip}...")
    status = 'client'
    vnc.ip = ip
    input_manager.ip = ip
    try:
        vnc.start_receive(requestPassword)
        input_manager.connect_input()
        connection = 'active'
        logging.info(f"Đã kết nối thành công tới {ip}")
        eel.start("connect.html", block=False, port=8080)
        print(True)
        return True
    except Exception as e:
        logging.error(f"Lỗi khi kết nối tới {ip}: {e}")
        print(False)
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
        logging.debug(f"Đã gửi input: {event_type} - {data}")
    except Exception as e:
        logging.error(f"Lỗi khi transmit input: {e}")

eel.start('index.html', block=False, port=8080, size=(595, 200))
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