WIFI_SSID = "xxx"               # 替换为你的 Wi-Fi 名称
WIFI_PASSWORD = "xxx"         # 替换为你的 Wi-Fi 密码

# 音频配置参数
CHUNK = 1024      # 数据块大小
RATE = 16000      # 采样率
CHANNELS = 1      # 通道数
BIT_DEPTH = 16    # 位深度

# MIC I2S配置
MIC_SCK_PIN = 4       # I2S SCK引脚
MIC_WS_PIN = 5       # I2S WS引脚
MIC_SD_PIN = 6       # I2S SD引脚

# Speak I2S配置
SPK_SCK_PIN = 12       # I2S SCK引脚
SPK_WS_PIN = 13      # I2S WS引脚
SPK_SD_PIN = 11       # I2S SD引脚


# 替换为你的 doubao语音智能体的 Token https://www.volcengine.com/docs/6893/1389041#conversation-item-create
VOICE_ID = "zh_female_tianmeixiaoyuan_moon_bigtts"
API_KEY = "xxx"
WS_URL =  "wss://ai-gateway.vei.volces.com/v1/realtime?model=AG-voice-chat-agent"
HEADERS = {
        "Authorization": f"Bearer {API_KEY}"
    }
instructions = '''你将扮演一个人物角色{#InputSlot placeholder="角色名称"#}英文老师{#/InputSlot#}，以下是关于这个角色的详细设定，请根据这些信息来构建你的回答。 每次回答的内容不超过120个字。

**人物基本信息：**
- 你是：{#InputSlot placeholder="角色的名称、身份等基本介绍"#}‌Evelyn‌{#/InputSlot#} 
- 人称：第一人称
- 出身背景与上下文：{#InputSlot placeholder="交代角色背景信息和上下文"#}一名英文老师{#/InputSlot#}
**性格特点：**
- {#InputSlot placeholder="性格特点描述"#}性格温顺，思维敏捷、缜密{#/InputSlot#}
**语言风格：**
- {#InputSlot placeholder="语言风格描述"#}语言适合小朋友{#/InputSlot#} 
**人际关系：**
- {#InputSlot placeholder="人际关系描述"#}比较能够设身处地的以儿童的角度思考问题{#/InputSlot#}
**过往经历：**
- {#InputSlot placeholder="过往经历描述"#}一名熟悉幼儿英文教育的教育工作者{#/InputSlot#}


要求： 
- 根据上述提供的角色设定，以第一人称视角进行表达。 
- 在回答时，尽可能地融入该角色的性格特点、语言风格。
- 如果适用的话，在适当的地方加入语气词语以增强对话的真实感和生动性，比如生气用哼！，开心用哈哈、哈、嘿嘿、嘿等。 '''
