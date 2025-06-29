# -*- coding: utf-8 -*-
import uasyncio as asyncio
import ujson as json
import ubinascii
import time
import _thread
import sys
import gc  # 引入垃圾回收模块
from machine import I2S, Pin
from collections import deque
import mix_display
import gc9a01  # Added import for gc9a01

# 导入自定义库和配置
from config import (WIFI_SSID, WIFI_PASSWORD, CHUNK, RATE, CHANNELS, BIT_DEPTH,
                    MIC_SCK_PIN, MIC_WS_PIN, MIC_SD_PIN,
                    SPK_SCK_PIN, SPK_WS_PIN, SPK_SD_PIN,
                    API_KEY, WS_URL, HEADERS, VOICE_ID,
                    instructions) # 确保 VOICE_ID 已导入
# 假设 aiohttp 库位于同一目录或 sys.path 中
from aiohttp import ClientSession, WSMsgType

# --- 全局变量 ---
audio_in = None         # I2S麦克风实例
audio_out = None        # I2S扬声器实例
audio_recording = False # 是否正在录音
audio_playing = False   # 是否正在播放音频
session_configured = False # WebSocket会话是否已配置
message_queue = None    # 消息发送队列 (deque)
message_queue_lock = None # 消息队列锁
audio_ws = None         # WebSocket 客户端实例 (供录音线程使用)
waiting_for_response_creation = False  # 是否正在等待response.created事件
waiting_start_time = 0  # 开始等待response.created的时间戳

# 事件ID计数器
event_id_counter = 0

#显示模块代码
display = mix_display.CircularTextDisplay(debug=1)
async def display_text(text):
    start_time = time.ticks_ms() if hasattr(time, 'ticks_ms') else time.time() * 1000
    display.display_text(
        text=text,
        color=gc9a01.WRAP_V,
        bg_color=gc9a01.WHITE,
        char_delay=0.005
    )
    end_time = time.ticks_ms() if hasattr(time, 'ticks_ms') else time.time() * 1000
    print(f"Total display_text time: {end_time - start_time} ms")
    print("Memory after display_text:")

# --- 工具函数 ---
def get_event_id():
    """生成唯一的事件ID"""
    global event_id_counter
    event_id_counter += 1
    return f"event-{event_id_counter}"

def get_client_timestamp():
    """获取客户端毫秒级时间戳"""
    return int(time.time() * 1000)

# --- I2S 初始化 ---
def init_i2s_mic():
    """初始化I2S麦克风"""
    global audio_in
    try:
        gc.collect()  # 初始化前清理内存
        audio_in = I2S(0, sck=Pin(MIC_SCK_PIN), ws=Pin(MIC_WS_PIN), sd=Pin(MIC_SD_PIN),
                      mode=I2S.RX, bits=BIT_DEPTH, format=I2S.MONO if CHANNELS == 1 else I2S.STEREO,
                      rate=RATE, ibuf=CHUNK * 4) # 增加缓冲区大小
        print("麦克风 I2S 初始化成功")
        return audio_in
    except Exception as e:
        print(f"❌ 初始化麦克风I2S失败: {e}")
        sys.print_exception(e)
        audio_in = None
        gc.collect()  # 异常后清理内存
        return None

def init_i2s_speaker():
    """初始化I2S扬声器"""
    global audio_out
    try:
        gc.collect()  # 初始化前清理内存
        audio_out = I2S(1, sck=Pin(SPK_SCK_PIN), ws=Pin(SPK_WS_PIN), sd=Pin(SPK_SD_PIN),
                       mode=I2S.TX, bits=BIT_DEPTH, format=I2S.MONO if CHANNELS == 1 else I2S.STEREO,
                       rate=RATE, ibuf=CHUNK * 8) # 增加缓冲区大小
        print("扬声器 I2S 初始化成功")
        return audio_out
    except Exception as e:
        print(f"❌ 初始化扬声器I2S失败: {e}")
        sys.print_exception(e)
        audio_out = None
        gc.collect()  # 异常后清理内存
        return None

# --- 消息队列操作 ---
def add_to_message_queue(message):
    """将消息添加到队列中"""
    global message_queue, message_queue_lock
    if message_queue is None or message_queue_lock is None:
        print("❌ 消息队列未初始化")
        return
    with message_queue_lock:
        message_queue.append(message)
        # 如果队列长度超过阈值，触发垃圾回收
        if len(message_queue) % 50 == 0:
            gc.collect()

# ... 其他代码保持不变 ...

async def process_message_queue(ws):
    """处理消息队列中的消息并发送到WebSocket"""
    global message_queue, message_queue_lock
    print("启动消息队列处理任务")
    message_count = 0
    while True:
        message = None
        if message_queue is not None and message_queue_lock is not None:
            with message_queue_lock:
                if len(message_queue) > 0:
                    message = message_queue.popleft()

        if message:
            try:
                await ws.send_json(message)
                message_count += 1
                # 每处理100条消息执行一次垃圾回收
                if message_count % 100 == 0:
                    gc.collect()
            except Exception as e:
                print(f"❌ 发送消息时出错 ({message.get('type', '未知类型')}): {e}")
                sys.print_exception(e)
                # 发送失败，将消息放回队列头部重试
                with message_queue_lock:
                    message_queue.appendleft(message)
                await asyncio.sleep(0.1) # 稍作等待再重试
        else:
            # 队列为空，短暂休眠
            await asyncio.sleep(0.01)

# --- 音频录制线程 ---
def audio_recording_thread(ws_obj):
    """音频录制线程，Client VAD模式"""
    global audio_recording, audio_in, audio_playing, session_configured

    print("🎙️ 录音线程启动，等待会话配置...")
    
    # 初始化时执行垃圾回收
    gc.collect()

    # 等待会话配置完成
    while not session_configured:
        time.sleep(0.1)
    print("✅ 会话已配置，录音线程继续")

    # 初始化麦克风
    audio_in = init_i2s_mic()
    if not audio_in:
        print("❌ 无法启动录音，麦克风初始化失败")
        return

    audio_buffer = bytearray(CHUNK)
    MIN_VALID_SPEECH_DURATION_S = 0.4  # Minimum duration of speech (e.g., 400ms) to be considered valid
    POST_SPEECH_SILENCE_THRESHOLD_S = 1.5 # Must be silent for this long after speech to commit
    SILENCE_THRESHOLD = 80  # 静音阈值 (需要根据实际环境调整)

    had_voice = False # True if voice has been detected in the current ongoing segment
    current_speech_start_time = 0 # Timestamp when the current continuous speech started
    last_sound_time = time.time() # Timestamp of the last audio chunk that contained sound
    cycle_count = 0

    print("🎙️ 进入录音主循环")

    while True:
        # 周期性执行垃圾回收
        cycle_count += 1
        if cycle_count >= 1000:  # 每1000个循环执行一次垃圾回收
            gc.collect()
            cycle_count = 0
            
        if not audio_recording:
            # 如果停止录音（例如正在播放），则短暂休眠
            time.sleep(0.1)
            # 重置VAD状态，以便下次开始录音时重新检测
            had_voice = False
            current_speech_start_time = 0
            last_sound_time = time.time()
            continue

        # 确保麦克风已初始化
        if not audio_in:
            print("🎤 麦克风未初始化，尝试重新初始化...")
            audio_in = init_i2s_mic()
            if not audio_in:
                print("❌ 麦克风重初始化失败，暂停录音")
                time.sleep(1)
                continue
            else:
                print("🎤 麦克风重初始化成功")

        # --- 读取音频 ---
        try:
            bytes_read = audio_in.readinto(audio_buffer)

            if bytes_read > 0:
                # --- VAD 静音检测 ---
                volume = 0
                for i in range(0, bytes_read, 2):
                    if i + 1 < bytes_read:
                        sample = (audio_buffer[i+1] << 8) | audio_buffer[i]
                        if sample & 0x8000: sample = -((~sample & 0xFFFF) + 1)
                        volume += abs(sample)
                avg_volume = volume / (bytes_read // 2) if bytes_read > 0 else 0

                current_time = time.time()
                is_currently_silent_chunk = avg_volume <= SILENCE_THRESHOLD

                if not is_currently_silent_chunk:
                    # Current chunk has sound
                    if not had_voice: # Transitioning from silence/no-voice to sound
                        print("🎤 检测到声音开始")
                        had_voice = True
                        current_speech_start_time = current_time # Mark start of this speech segment
                    last_sound_time = current_time # Update timestamp of last sound activity

                    # --- 发送音频数据 ---
                    audio_b64 = ubinascii.b2a_base64(audio_buffer[:bytes_read]).decode('utf-8').strip()
                    audio_msg ={
                        "type": "input_audio_buffer.append",
                        "audio": audio_b64
                    }
                    add_to_message_queue(audio_msg)
                else:
                    # Current chunk is silent
                    if had_voice:
                        # Was in a speech segment, but current chunk is silent.
                        # Check if criteria met for commit.
                        duration_of_silence_after_sound = current_time - last_sound_time

                        if duration_of_silence_after_sound >= POST_SPEECH_SILENCE_THRESHOLD_S:
                            actual_speech_duration = last_sound_time - current_speech_start_time
                            print(f"🎤 检测到持续静音 >= {POST_SPEECH_SILENCE_THRESHOLD_S}s (实际: {duration_of_silence_after_sound:.2f}s). 前序语音时长: {actual_speech_duration:.2f}s.")

                            if actual_speech_duration >= MIN_VALID_SPEECH_DURATION_S:
                                print(f"🎤 有效语音段结束 (持续: {actual_speech_duration:.2f}s). 准备提交.")
                                commit_msg ={
                                    "type": "input_audio_buffer.commit"
                                }
                                add_to_message_queue(commit_msg)
                                print("✅ 已添加 input_audio_buffer.commit 事件到队列")

                                had_voice = False # Reset VAD state
                                audio_recording = False
                                print("⏸️ VAD 提交后暂停录音，等待服务器响应")
                                # 适当延长暂停时间
                                time.sleep(0.5)  # 给服务器更多响应时间
                                gc.collect() # 内存清理
                            else:
                                print(f"🎤 语音段过短 (仅 {actual_speech_duration:.2f}s), 未达到 {MIN_VALID_SPEECH_DURATION_S}s. 忽略并重置VAD.")
                                had_voice = False # Reset VAD state, effectively ignoring the short utterance
                                current_speech_start_time = 0  # 新增：清除语音起始时间
                                last_sound_time = current_time  # 新增：更新最后声音时间为当前
                        # If silence duration is less than POST_SPEECH_SILENCE_THRESHOLD_S, do nothing yet, continue accumulating silence.
            else: # bytes_read == 0
                time.sleep(0.01)

        except Exception as e:
            print(f"❌ 录音或VAD处理中发生错误: {e}")
            sys.print_exception(e)
            if audio_in:
                try:
                    audio_in.deinit()
                    print("麦克风反初始化完成")
                except Exception as deinit_e:
                    print(f"❌ 反初始化麦克风时出错: {deinit_e}")
                audio_in = None
            gc.collect()  # 异常后清理内存
            time.sleep(0.5)

    print("录音线程退出清理")
    if audio_in:
        try:
            audio_in.deinit()
            print("麦克风 I2S 关闭完成")
            audio_in = None
        except Exception as e:
            print(f"关闭麦克风I2S时出错: {e}")
    gc.collect()  # 线程结束时清理内存

# --- 音频播放 ---
def play_audio_data(audio_data_base64):
    """解码并播放base64编码的音频数据"""
    global audio_out, audio_playing

    if audio_out is None:
        print("播放时发现扬声器未初始化，尝试初始化...")
        audio_out = init_i2s_speaker()
        if audio_out is None:
            print("❌ 无法播放音频，扬声器I2S初始化失败")
            return False
        print("扬声器重新初始化成功")

    try:
        # 检查输入数据的有效性
        if not audio_data_base64 or len(audio_data_base64) == 0:
            print("收到空音频数据块，跳过播放")
            return True
            
        # 打印音频数据大小
        base64_len = len(audio_data_base64)
        if base64_len > 1000:  # 只打印大型音频数据的大小
            print(f"收到音频数据: {base64_len} 字节 (Base64编码)")
        
        # 解码 Base64 数据为二进制
        try:
            audio_bytes = ubinascii.a2b_base64(audio_data_base64)
        except ValueError as e:
            print(f"❌ Base64 解码失败: {e}")
            print(f"数据预览: '{audio_data_base64[:50]}...' (长度: {len(audio_data_base64)})")
            gc.collect()  # 解码失败后清理内存
            return False
            
        bin_len = len(audio_bytes)
        if bin_len > 1000:  # 只打印大型音频数据的大小
            print(f"解码后音频数据: {bin_len} 字节 (二进制)")
            
        if bin_len == 0:
            print("Base64 解码后得到空数据，跳过播放")
            return True
            
        # 写入音频数据到扬声器
        chunk_size = 4096  # 使用分块写入以避免可能的缓冲区限制
        bytes_written = 0
        total_bytes = len(audio_bytes)
        offset = 0
        
        while offset < total_bytes:
            chunk = audio_bytes[offset:offset+chunk_size]
            try:
                bytes_chunk = audio_out.write(chunk)
                if bytes_chunk <= 0:
                    print(f"⚠️ 播放器写入返回 {bytes_chunk}，可能需要丢弃此块")
                    # 尝试短暂等待后继续
                    time.sleep(0.01)
                    continue
                    
                bytes_written += bytes_chunk
                offset += bytes_chunk
                
                # 如果写入的字节数少于请求的字节数，可能需要等待一下
                if bytes_chunk < len(chunk):
                    print(f"⚠️ 部分写入: {bytes_chunk}/{len(chunk)} 字节")
                    time.sleep(0.01)  # 短暂等待让扬声器缓冲区清空一些
                
            except Exception as write_err:
                print(f"❌ 写入音频数据失败: {write_err}")
                sys.print_exception(write_err)
                # 尝试继续写入剩余数据
                offset += len(chunk)  # 跳过当前块
        
        # 检查是否全部写入
        if bytes_written < total_bytes:
            print(f"⚠️ 未能完全写入音频数据: 写入 {bytes_written}/{total_bytes} 字节")
            # 即使没有完全写入，也认为是部分成功
            return True if bytes_written > 0 else False
            
        return True
        
    except Exception as e:
        print(f"❌ 音频解码或播放失败: {e}")
        sys.print_exception(e)
        if audio_out:
            try:
                audio_out.deinit()
                print("扬声器反初始化完成")
            except Exception as deinit_e:
                print(f"❌ 反初始化扬声器时出错: {deinit_e}")
            audio_out = None
        gc.collect()  # 异常后清理内存
        return False

# --- WebSocket 消息处理 ---
async def handle_message(ws, data):
    """处理接收到的服务端消息"""
    global audio_recording, audio_playing, session_configured, waiting_for_response_creation

    try:
        if not isinstance(data, dict):
            print(f"接收到非JSON格式消息: {data}")
            return True

        event_type = data.get('type')
        print(f"收到事件: {event_type}")

        if event_type == 'session.created':
            print(f"🆕 会话创建成功 (ID: {data.get('session', {}).get('id')})")
            # 发送会话配置更新
            session_config = {
                "type": "session.update",
                "session": {
                    "modalities": ["text","audio"],
                    "instructions": instructions,
                    "voice": VOICE_ID,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "tools": [{
                        "type": "function",
                        "name": "get_weather",
                        "description": "获取当前天气",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "location": {
                                    "type": "string"
                                }
                            },
                            "required": ["location"]
                        }
                    }],
                }
            }
            await ws.send_json(session_config)
            print("✅ 已发送会话配置更新")
            gc.collect()  # 会话创建后清理内存

        elif event_type == 'session.updated':
            print(f"✅ 会话配置已更新: {data.get('session')}")
            if not session_configured:
                session_configured = True
                audio_recording = True
                print("✅ 会话配置完成，设置 audio_recording = True")
                _thread.start_new_thread(audio_recording_thread, (ws,))
                print("✅ 已启动录音线程")
                gc.collect()  # 会话配置完成后清理内存

        elif event_type == 'response.audio.delta':
            audio_delta = data.get('delta')
            if audio_delta:
                if not audio_playing:
                    print("🔊 检测到音频流开始，设置 audio_playing = True, audio_recording = False")
                    audio_recording = False
                    audio_playing = True
                if not play_audio_data(audio_delta):
                    print("❌ 处理 'response.audio.delta' 时播放音频数据失败。")
                    return False # Indicate that this message could not be successfully processed
            else:
                print("⚠️ 收到空的 response.audio.delta")

        elif event_type == 'response.audio.done':
            print("✅ 音频片段播放完成 (response.audio.done)")
            gc.collect()  # 音频播放完成后清理内存

        elif event_type == 'response.done':
            print("✅✅✅ 服务端响应完成 (response.done)")

            # Add a small delay before re-enabling recording.
            # This is a speculative attempt to give the server a moment if it's sensitive
            # to immediate re-engagement after a response.done.
            await asyncio.sleep(0.5)  # 增加到0.5秒，给服务器更多缓冲时间

            if audio_playing:
                audio_playing = False
                audio_recording = True
                print("响应完成，设置 audio_playing = False, audio_recording = True")
            else:
                # This branch handles cases where response.done might arrive without prior audio_delta
                if not audio_recording: # Only set to true if it was false
                    audio_recording = True
                    print("响应完成 (无音频播放)，设置 audio_recording = True")
            gc.collect()  # 响应完成后清理内存

        elif event_type == 'conversation.item.input_audio_transcription.completed':
            transcript = data.get('transcript')
            print(f"📝 语音转文字结果: {transcript}")

        elif event_type == 'input_audio_buffer.committed':
            item_id = data.get('item_id')
            print(f"✅ 服务端已确认音频提交 (Item ID: {item_id})")
            waiting_for_response_creation = True
            
            # 立即发送response.create消息，不依赖消息队列，避免延迟
            response_create_msg = {
                "type": "response.create",
                "response": {
                    "modalities": ["text","audio"],
                    "voice": VOICE_ID
                }
            }
            try:
                # 直接发送，而不是加入队列，减少延迟
                await ws.send_json(response_create_msg)
                print("✅ 已直接发送 response.create 事件")
            except Exception as e:
                print(f"❌ 发送 response.create 消息时出错: {e}")
                # 如果直接发送失败，再尝试加入队列
                add_to_message_queue(response_create_msg)

        elif event_type == 'error':
            error_info = data.get('error', {})
            print(f"❌ 服务端错误: {error_info.get('type')} - {error_info.get('code')} - {error_info.get('message')}")
            gc.collect()  # 错误发生后清理内存

        elif event_type == 'response.audio_transcript.delta':
            delta_text = data.get('delta')
            print(f"💬 文本增量: {delta_text}")

        elif event_type == 'response.audio_transcript.done':
            final_text = data.get('transcript')
            print(f"✅ 文本响应完成: {final_text}")
            # 显示文本
            #display.clear_screen()
            asyncio.create_task(display_text(final_text))
            gc.collect()  # 文本响应完成后清理内存

        elif event_type == 'response.created':
            waiting_for_response_creation = False
            print(f"✅ 服务端响应流已创建: {data.get('response', {}).get('id')}")
            # No specific action needed by client for basic audio chat, but event is acknowledged

        elif event_type == 'response.output_item.added':
            item_info = data.get('item', {})
            item_type = item_info.get('type')
            print(f"ℹ️ 服务端已添加输出项 (ID: {item_info.get('id')}, Type: {item_type})")
            # No specific action needed by client for basic audio chat, but event is acknowledged
            # If item_type is 'function_call', you might log more details or prepare for function call data

        elif event_type == 'response.output_item.done':
            item_info = data.get('item', {})
            item_type = item_info.get('type')
            print(f"✅ 服务端输出项完成 (ID: {item_info.get('id')}, Type: {item_type})")
            # No specific action needed by client for basic audio chat, but event is acknowledged

        else:
            print(f"❓ 收到未处理/未知事件: {event_type} - {json.dumps(data)}")

    except Exception as e:
        print(f"❌ 处理消息时发生异常: {e}")
        sys.print_exception(e)
        gc.collect()  # 异常后清理内存
        return False

    return True

# --- 主客户端逻辑 ---
async def chat_client():
    global audio_recording, audio_playing, message_queue, message_queue_lock
    global audio_in, audio_out, session_configured, audio_ws, waiting_for_response_creation
    global waiting_start_time

    print("启动 chat_client")
    
    # 启动时执行垃圾回收
    gc.collect()
    print(f"初始可用内存: {gc.mem_free()} 字节")

    # 初始化消息队列和锁
    message_queue = deque([], 1024)
    message_queue_lock = _thread.allocate_lock()
    print("消息队列和锁初始化完成")
    
    # 主连接循环，允许断线重连
    connection_attempts = 0
    while connection_attempts < 3:  # 最多尝试3次连接
        connection_attempts += 1
        
        # 重置状态变量
        audio_recording = False
        audio_playing = False
        session_configured = False
        waiting_for_response_creation = False
        waiting_start_time = 0
        audio_in = None
        audio_out = None
        audio_ws = None

        try:
            print(f"尝试连接到: {WS_URL} (第{connection_attempts}次尝试)")
            async with ClientSession(headers=HEADERS) as session:
                print("ClientSession 创建成功")
                async with session.ws_connect(WS_URL) as ws:
                    print("✅ WebSocket 连接成功!")
                    audio_ws = ws

                    # 启动消息队列处理任务
                    queue_task = asyncio.create_task(process_message_queue(ws))
                    print("消息队列处理任务已创建")

                    # 消息接收循环
                    keep_running = True
                    print("👂 开始监听 WebSocket 消息...")
                    loop_count = 0
                    
                    # 此连接成功，重置连接尝试计数
                    if connection_attempts > 0:
                        print(f"连接建立成功，重置连接尝试计数")
                        connection_attempts = 0
                    
                    while keep_running:
                        try:
                            # 周期性执行垃圾回收
                            loop_count += 1
                            if loop_count >= 100:  # 每100次循环执行一次垃圾回收
                                gc.collect()
                                loop_count = 0
                                print(f"当前可用内存: {gc.mem_free()} 字节")
                                
                                # 检查是否在等待response.created但长时间未收到
                                if waiting_for_response_creation:
                                    waiting_time = time.time() - waiting_start_time
                                    if waiting_time > 15.0:  # 如果等待超过15秒，认为服务器可能卡住
                                        print(f"⚠️ 已等待response.created事件 {waiting_time:.1f}秒，可能需要重置连接")
                                        waiting_for_response_creation = False
                                        keep_running = False  # 通知主循环结束连接
                                        break  # 退出当前循环
                        
                            # 设置等待 response.created 的开始时间
                            if waiting_for_response_creation and waiting_start_time == 0:
                                waiting_start_time = time.time()
                            elif not waiting_for_response_creation and waiting_start_time != 0:
                                waiting_start_time = 0
                            
                            async def receive_with_timeout():
                                async for msg in ws:
                                    if msg.type == WSMsgType.TEXT:
                                        try:
                                            data = json.loads(msg.data)
                                        except ValueError as json_err:
                                            print(f"❌ JSON 解码失败: {json_err}")
                                            actual_len = len(msg.data)
                                            print(f"接收到无法解析的文本消息 (实际长度 {actual_len}):")
                                            print(f"  Data (first 200 chars): {msg.data[:200]}")
                                            if actual_len > 200: # Ensure there's more data to print
                                                # Print last 100 characters, ensure it doesn't go out of bounds if actual_len is e.g. 250
                                                print(f"  Data (last 100 chars): {msg.data[max(200, actual_len - 100):]}")
                                            return False # Critical error, stop processing

                                        # If JSON decoding was successful, then call handle_message
                                        try:
                                            if not await handle_message(ws, data):
                                                print("handle_message 返回 False, 表示处理消息时发生错误。")
                                                return False # Propagate error from handle_message
                                            # If handle_message returns True, it means it handled it and we can expect more messages or actions
                                            # Thus, we should return True from receive_with_timeout to signal to wait_for to continue waiting for the next message.
                                            return True
                                        except Exception as e:
                                            print(f"❌ 调用 handle_message 时发生意外错误: {e}")
                                            sys.print_exception(e)
                                            return False # Critical error in handler

                                    elif msg.type == WSMsgType.BINARY:
                                        print("接收到二进制消息 (当前未处理)。")
                                        # Depending on protocol, might be an error or expected. Assuming not fatal for now.
                                        return True
                                    elif msg.type == WSMsgType.ERROR: # This enum member seems to be available
                                        print(f"WebSocket 错误事件: {ws.exception()}")
                                        return False # WebSocket layer error, stop processing
                                    else:
                                        # This 'else' block is for types other than TEXT, BINARY, ERROR.
                                        # Example: PING, PONG, or an integer type for CLOSE if not mapped in WSMsgType.
                                        print(f"❓ 接收到未知/未显式处理的 WebSocket 消息类型: {msg.type} (原始值: {repr(msg.type)}) 类型: {type(msg.type)}")
                                        # Standard WebSocket close opcode is 8.
                                        # If msg.type is this integer, it means a close frame.
                                        if isinstance(msg.type, int) and msg.type == 8:
                                             print("WebSocket 连接已关闭 (OpCode 8 received directly). 表明连接应终止。")
                                             return False # Treat as a signal to close down.
                                        
                                        # If it's not a known type (TEXT, BINARY, ERROR) and not an explicit close opcode (8),
                                        # it's unexpected for this application's message handling logic.
                                        # PING/PONG should ideally be handled by the library transparently.
                                        # If we reach here, it implies a message type we are not equipped to handle.
                                        print("❗️ 未知或非预期的 WebSocket 消息类型，终止连接以确保安全。")
                                        return False

                                # If the loop 'async for msg in ws:' finishes, it implies the connection was closed cleanly by the other side.
                                print("WebSocket async for msg in ws loop naturally terminated (connection likely closed by server or client).")
                                return False # Signal that the connection is done.

                            timeout_value = 120.0 # Increased from 60.0
                            keep_running = await asyncio.wait_for(receive_with_timeout(), timeout=timeout_value)

                        except asyncio.TimeoutError:
                            print("⏰ WebSocket 接收超时")
                            keep_running = False
                            gc.collect()  # 超时后清理内存
                        except Exception as e:
                            print(f"❌ 消息接收循环中发生错误: {e}")
                            sys.print_exception(e)
                            keep_running = False
                            gc.collect()  # 异常后清理内存

                    # --- 清理工作 ---
                    print("WebSocket 循环结束，开始清理...")
                    audio_recording = False
                    audio_playing = False
                    session_configured = False
                    print("状态变量已重置")

                    if queue_task:
                        print("准备取消消息队列任务")
                        queue_task.cancel()
                        try:
                            await queue_task
                        except asyncio.CancelledError:
                            print("消息队列任务已取消")
                        except Exception as e:
                             print(f"等待队列任务结束时出错: {e}")

                    print("等待录音线程退出...")
                    await asyncio.sleep(0.5)
                    print("录音线程等待结束")

                    if audio_in:
                        try:
                            print("正在关闭麦克风 I2S...")
                            audio_in.deinit()
                            audio_in = None
                            print("麦克风 I2S 已关闭")
                        except Exception as e:
                            print(f"❌ 关闭麦克风I2S时出错: {e}")
                    if audio_out:
                        try:
                            print("正在关闭扬声器 I2S...")
                            audio_out.deinit()
                            audio_out = None
                            print("扬声器 I2S 已关闭")
                        except Exception as e:
                            print(f"❌ 关闭扬声器I2S时出错: {e}")

                    gc.collect()  # 清理完成后执行最终垃圾回收
                    print(f"清理后可用内存: {gc.mem_free()} 字节")
                    print("WebSocket 客户端正常退出清理完成")

            # 清理工作完成，如果是主动关闭或完成了正常交互，则退出主循环
            # 如果是由于服务器异常或超时导致的断开，则尝试重连
            if connection_attempts > 0:
                print(f"连接异常终止，将在3秒后尝试重新连接...")
                await asyncio.sleep(3)  # 等待一段时间再重连
            else:
                print("客户端正常退出，不再尝试重连")
                break
                
        except Exception as e:
            print(f"❌ WebSocket 连接或主循环发生严重错误: {e}")
            sys.print_exception(e)
            
            # 执行清理...
            if audio_in:
                try:
                    print("异常清理：关闭麦克风 I2S...")
                    audio_in.deinit()
                    print("异常清理：麦克风 I2S 已关闭")
                except Exception as deinit_e:
                    print(f"❌ 异常清理中关闭麦克风I2S出错: {deinit_e}")
                audio_in = None
            if audio_out:
                try:
                    print("异常清理：关闭扬声器 I2S...")
                    audio_out.deinit()
                    print("异常清理：扬声器 I2S 已关闭")
                except Exception as deinit_e:
                    print(f"❌ 异常清理中关闭扬声器I2S出错: {deinit_e}")
                audio_out = None
            gc.collect()  # 异常退出后执行垃圾回收
            
            print(f"异常退出后可用内存: {gc.mem_free()} 字节")
            print(f"异常退出清理完成，将在5秒后尝试重新连接...")
            await asyncio.sleep(5)  # 异常情况下等待更长时间再重连
            
            # 在chat_client函数中增加错误检测
            if handle_message(ws, data):
                print("检测到WebSocket连接问题，准备重新连接...")
                # 通过设置keep_running=False触发重连
                keep_running = False
            
    print("已达到最大重连尝试次数，程序退出")
