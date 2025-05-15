import asyncio
from GLM_chat import chat_client
from config import WIFI_SSID, WIFI_PASSWORD


def do_connect():
    import network
    import time
    
    sta_if = network.WLAN(network.STA_IF)
    sta_if.active(True)  # 确保 WiFi 已激活
    
    if not sta_if.isconnected():
        print(f"Connecting to: {WIFI_SSID}...")
        sta_if.connect(WIFI_SSID, WIFI_PASSWORD)
        
        # 等待 10 秒，避免无限循环
        for _ in range(10):
            if sta_if.isconnected():
                break
            time.sleep(2)
            print("Waiting for connection...")
        
        if not sta_if.isconnected():
            print("Failed to connect!")
            print("Scan available networks:", sta_if.scan())  # 扫描可用 WiFi
            raise RuntimeError("WiFi connection failed")
    
    print("Connected! IP:", sta_if.ifconfig()[0])


do_connect()
print("Init Chat !!")

try:
    asyncio.run(chat_client())
except Exception as e:
    print(f"发生错误: {e}")
