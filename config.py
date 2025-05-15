WIFI_SSID = "Prefoco"               # 替换为你的 Wi-Fi 名称
WIFI_PASSWORD = "18961210318"         # 替换为你的 Wi-Fi 密码

# 音频配置参数
CHUNK = 1024      # 数据块大小
RATE = 16000      # 采样率
CHANNELS = 1      # 通道数
BIT_DEPTH = 16    # 位深度

# MIC I2S配置
MIC_SCK_PIN = 9       # I2S SCK引脚
MIC_WS_PIN = 8       # I2S WS引脚
MIC_SD_PIN = 7       # I2S SD引脚

# Speak I2S配置
SPK_SCK_PIN = 11       # I2S SCK引脚
SPK_WS_PIN = 12      # I2S WS引脚
SPK_SD_PIN = 10       # I2S SD引脚


# 替换为你的 ChatGLM Token
VOICE_ID = "zh_female_tianmeiyueyue_moon_bigtts"
API_KEY = "sk-xxx"
WS_URL =  "wss://ai-gateway.vei.volces.com/v1/realtime?model=AG-voice-chat-agent"
HEADERS = {
        "Authorization": f"Bearer {API_KEY}"
    }
