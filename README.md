# 更新日志：
- 2025年6月6日，增加了gc9a01的支持
- 2025年6月6日，micropython固件更新为esp32s3-4M（增加了gc9a01模块）
  
# ESP32-S3 智能语音助手

这是一个基于ESP32-S3开发板的智能语音助手项目，使用MicroPython实现与大语言模型进行语音对话的功能。该项目通过WebSocket连接到语音对话智能体API，实现实时语音输入和输出的交互体验。

## 功能特点

- 使用I2S接口连接麦克风和扬声器，实现高质量的音频采集和播放
- 支持VAD（语音活动检测）功能，智能识别用户说话和静音
- 通过WebSocket与云端大语言模型实时通信
- 支持中英文语音输入与输出
- 支持对话历史保存和上下文理解


## 硬件要求

- ESP32-S3开发板
- I2S麦克风 (INMP441)
- I2S扬声器 (max98357)
- 稳定的WiFi连接

## 引脚配置

### 麦克风I2S配置
- SCK: GPIO9
- WS: GPIO8
- SD: GPIO7

### 扬声器I2S配置
- SCK: GPIO11
- WS: GPIO12
- SD: GPIO10

## 软件依赖

- MicroPython固件 (适用于ESP32-S3)
- 自定义aiohttp库 (已包含在项目中)

## 使用方法

1. 将MicroPython固件烧录到ESP32-S3开发板
2. 修改`config.py`文件中的WiFi凭据和API密钥
   ```python
   WIFI_SSID = "你的WiFi名称"
   WIFI_PASSWORD = "你的WiFi密码"
   API_KEY = "你的API密钥"
   instructions = '''你的提示词'''
   ```
3. 上传项目文件到ESP32-S3
4. 重启开发板，程序将自动连接WiFi并启动语音助手
5. 接线图：
<div align="center">
  <img src="https://github.com/zhou19830318/doubao_ai_agent_esp32/blob/main/1.png">
</div>
6. 运行截图：
<div align="center">
  <img src="https://github.com/zhou19830318/doubao_ai_agent_esp32/blob/main/2.png">
</div>
   

## 配置说明

在`config.py`文件中可以调整以下参数：

- WiFi连接信息
- 音频配置 (采样率、通道数、位深度等)
- I2S引脚配置
- API密钥和配置
- 语音模型参数 (如音色ID)

## 项目结构

- `main_ai.py`: 主程序入口，负责WiFi连接和启动聊天客户端
- `doubao_chat.py`: 实现WebSocket客户端和音频处理的核心代码
- `config.py`: 配置参数和API密钥
- `boot.py`: MicroPython启动脚本
- `aiohttp/`: 包含WebSocket客户端实现的自定义库

## 开发者说明

项目使用了以下关键技术：
- I2S音频处理
- WebSocket异步通信
- VAD语音活动检测
- 多线程音频录制和播放
- websocket通讯协议：https://www.volcengine.com/docs/6893/1389041

## 注意事项

- 确保WiFi网络稳定，以获得最佳的语音交互体验
- 调整`doubao_chat.py`中的`SILENCE_THRESHOLD`参数可以优化VAD检测灵敏度
- API密钥请保密，不要泄露到公开场合

## 致谢

-本项目基于大佬开源的代码改写，在此表示感谢！
同时感谢开源社区的每一位贡献者，是你们的无私分享与持续努力，让技术世界变得更加开放与包容。无论是代码、文档，还是思想的碰撞，你们的付出为全球开发者搭建了自由创新的舞台。开源不仅是一种协作方式，更是一种精神，激励着我们共同推动技术进步，解决复杂问题。感谢你们让知识得以共享，让世界因合作而更加美好！
