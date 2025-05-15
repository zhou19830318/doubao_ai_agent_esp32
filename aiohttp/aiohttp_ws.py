# MicroPython aiohttp library
# MIT license; Copyright (c) 2023 Carlos Gil
# adapted from https://github.com/danni/uwebsockets
# and https://github.com/miguelgrinberg/microdot/blob/main/src/microdot_asyncio_websocket.py

import asyncio
import random
import json as _json
import binascii
import re
import struct
import sys
from collections import namedtuple
import time

URL_RE = re.compile(r"(wss|ws)://([A-Za-z0-9-\.]+)(?:\:([0-9]+))?(/.+)?")
URI = namedtuple("URI", ("protocol", "hostname", "port", "path"))  # noqa: PYI024


def urlparse(uri):
    """Parse ws:// URLs"""
    match = URL_RE.match(uri)
    if match:
        protocol = match.group(1)
        host = match.group(2)
        port = match.group(3)
        path = match.group(4)

        if protocol == "wss":
            if port is None:
                port = 443
        elif protocol == "ws":
            if port is None:
                port = 80
        else:
            raise ValueError("Scheme {} is invalid".format(protocol))

        return URI(protocol, host, int(port), path)


class WebSocketMessage:
    def __init__(self, opcode, data):
        self.type = opcode
        self.data = data


class WSMsgType:
    TEXT = 1
    BINARY = 2
    ERROR = 258


class WebSocketClient:
    CONT = 0
    TEXT = 1
    BINARY = 2
    CLOSE = 8
    PING = 9
    PONG = 10

    def __init__(self, params):
        self.params = params
        self.closed = False
        self.reader = None
        self.writer = None

    async def connect(self, uri, ssl=None, handshake_request=None, headers={}):
        uri = urlparse(uri)
        assert uri
        if uri.protocol == "wss":
            if not ssl:
                ssl = True
        await self.handshake(uri, ssl, handshake_request, headers)

    @classmethod
    def _parse_frame_header(cls, header):
        byte1, byte2 = struct.unpack("!BB", header)

        # Byte 1: FIN(1) _(1) _(1) _(1) OPCODE(4)
        fin = bool(byte1 & 0x80)
        opcode = byte1 & 0x0F

        # Byte 2: MASK(1) LENGTH(7)
        mask = bool(byte2 & (1 << 7))
        length = byte2 & 0x7F

        return fin, opcode, mask, length

    def _process_websocket_frame(self, opcode, payload):
        if opcode == self.TEXT:
            payload = str(payload, "utf-8")
        elif opcode == self.BINARY:
            pass
        elif opcode == self.CLOSE:
            # raise OSError(32, "Websocket connection closed")
            return opcode, payload
        elif opcode == self.PING:
            return self.PONG, payload
        elif opcode == self.PONG:  # pragma: no branch
            return None, None
        return None, payload

    @classmethod
    def _encode_websocket_frame(cls, opcode, payload):
        if opcode == cls.TEXT:
            payload = payload.encode()

        length = len(payload)
        fin = mask = True

        # Frame header
        # Byte 1: FIN(1) _(1) _(1) _(1) OPCODE(4)
        byte1 = 0x80 if fin else 0
        byte1 |= opcode

        # Byte 2: MASK(1) LENGTH(7)
        byte2 = 0x80 if mask else 0

        if length < 126:  # 126 is magic value to use 2-byte length header
            byte2 |= length
            frame = struct.pack("!BB", byte1, byte2)

        elif length < (1 << 16):  # Length fits in 2-bytes
            byte2 |= 126  # Magic code
            frame = struct.pack("!BBH", byte1, byte2, length)

        elif length < (1 << 64):
            byte2 |= 127  # Magic code
            frame = struct.pack("!BBQ", byte1, byte2, length)

        else:
            raise ValueError

        # Mask is 4 bytes
        mask_bits = struct.pack("!I", random.getrandbits(32))
        frame += mask_bits
        payload = bytes(b ^ mask_bits[i % 4] for i, b in enumerate(payload))
        return frame + payload

    async def handshake(self, uri, ssl, req, headers={}):
        # 使用传入的headers，而不是创建一个空的headers字典
        _http_proto = "http" if uri.protocol != "wss" else "https"
        url = f"{_http_proto}://{uri.hostname}:{uri.port}{uri.path or '/'}"
        key = binascii.b2a_base64(bytes(random.getrandbits(8) for _ in range(16)))[:-1]
        headers["Host"] = f"{uri.hostname}:{uri.port}"
        headers["Connection"] = "Upgrade"
        headers["Upgrade"] = "websocket"
        headers["Sec-WebSocket-Key"] = str(key, "utf-8")
        headers["Sec-WebSocket-Version"] = "13"
        headers["Origin"] = f"{_http_proto}://{uri.hostname}:{uri.port}"

        self.reader, self.writer = await req(
            "GET",
            url,
            ssl=ssl,
            headers=headers,
            is_handshake=True,
            version="HTTP/1.1",
        )

        header = await self.reader.readline()
        header = header[:-2]
        assert header.startswith(b"HTTP/1.1 101 "), header

        while header:
            header = await self.reader.readline()
            header = header[:-2]

    async def _read_frame(self):
        header = await self.reader.read(2)
        if len(header) != 2:  # pragma: no cover
            # raise OSError(32, "Websocket connection closed")
            opcode = self.CLOSE
            payload = b""
            return fin, opcode, payload
        fin, opcode, has_mask, length = self._parse_frame_header(header)
        if length == 126:  # Magic number, length header is 2 bytes
            (length,) = struct.unpack("!H", await self.reader.read(2))
        elif length == 127:  # Magic number, length header is 8 bytes
            (length,) = struct.unpack("!Q", await self.reader.read(8))

        if has_mask:  # pragma: no cover
            mask = await self.reader.read(4)
            
        # 对于大型数据，使用分块读取
        payload = b""
        chunk_size = 4096  # 使用较小的块大小 (4KB)
        remaining = length
        
        # 记录是否已经打印过进度
        progress_markers = set()
        total_chunks = (length + chunk_size - 1) // chunk_size  # 总的分块数
        
        # 增强的读取循环，确保读取完整的载荷
        start_time = time.time()
        while remaining > 0:
            try:
                chunk = await self.reader.read(min(chunk_size, remaining))
                # 如果没有读取到数据，尝试等待一小段时间后重试
                if not chunk:
                    # 短暂休眠后重试，而不是立即退出
                    await asyncio.sleep(0.05)  # 增加等待时间，给网络栈更多处理时间
                    
                    # 减少重试次数的计数器
                    retry_count = getattr(self, '_retry_count', 10)  # 增加默认重试次数
                    if retry_count <= 0:
                        elapsed = time.time() - start_time
                        print(f"WARNING: EOF reading frame payload after {len(payload)}/{length} bytes (elapsed: {elapsed:.2f}s)")
                        break
                    
                    self._retry_count = retry_count - 1
                    continue
                else:
                    # 重置重试计数器
                    self._retry_count = 10
                
                payload += chunk
                remaining -= len(chunk)
                
                # 打印进度日志（对于大型载荷）
                if length > 8192:
                    # 计算已完成百分比
                    percent_complete = (len(payload) * 100) // length
                    # 每 25% 打印一次进度，避免重复日志
                    marker = percent_complete // 25
                    if marker not in progress_markers and marker > 0:
                        progress_markers.add(marker)
                        elapsed = time.time() - start_time
                        print(f"Reading WebSocket frame: {len(payload)}/{length} bytes ({percent_complete}%) in {elapsed:.2f}s")
                
            except Exception as e:
                print(f"Error reading WebSocket frame: {e}")
                sys.print_exception(e)
                break
        
        # 载荷读取完成后检查是否读取了声明的完整长度
        if len(payload) < length:
            elapsed = time.time() - start_time
            print(f"WARNING: Incomplete frame payload: got {len(payload)}/{length} bytes in {elapsed:.2f}s")
        elif length > 8192:
            elapsed = time.time() - start_time
            print(f"COMPLETE: Read full frame of {length} bytes in {elapsed:.2f}s")
                
        if has_mask:  # pragma: no cover
            payload = bytes(x ^ mask[i % 4] for i, x in enumerate(payload))
        
        return fin, opcode, payload

    async def receive(self):
        """
        接收 WebSocket 消息，支持处理分片消息
        分片消息由多个帧组成，第一个帧的 opcode 指定了消息类型，
        后续帧的 opcode 为 0 (CONT)，最后一个帧的 fin 为 True
        """
        # 用于收集分片消息的状态变量
        message_opcode = None
        message_payload = b""
        
        try:
            # 超时设置，防止无限循环
            start_time = time.time()
            max_receive_time = 60  # 最多尝试 60 秒
            
            while True:
                # 检查接收时间是否过长
                if time.time() - start_time > max_receive_time:
                    print(f"WARNING: Receiving WebSocket message exceeded {max_receive_time}s timeout")
                    if self.closed:
                        return self.CLOSE, b""
                    else:
                        # 强制关闭并返回
                        self.closed = True
                        return self.CLOSE, b"timeout"
                
                try:
                    fin, opcode, payload = await self._read_frame()
                except Exception as e:
                    print(f"Error in _read_frame: {e}")
                    sys.print_exception(e)
                    if self.closed:
                        return self.CLOSE, b""
                    else:
                        # 出错时尝试重新启动读取
                        await asyncio.sleep(0.1)
                        continue
                
                # 处理控制帧 (PING, PONG, CLOSE)
                if opcode in (self.PING, self.PONG, self.CLOSE):
                    send_opcode, data = self._process_websocket_frame(opcode, payload)
                    if send_opcode:  # pragma: no cover
                        try:
                            await self.send(data, send_opcode)
                        except Exception as e:
                            print(f"Error sending control frame response: {e}")
                    if opcode == self.CLOSE:
                        self.closed = True
                        return self.CLOSE, data
                    # 控制帧处理后继续等待数据帧
                    continue
                    
                # 处理数据帧 (TEXT, BINARY, CONT)
                if opcode == self.CONT:
                    # 连续帧 - 必须已有一个消息开始
                    if message_opcode is None:
                        print("ERROR: Received CONT frame without initial frame")
                        continue
                    # 将载荷添加到正在收集的消息中
                    message_payload += payload
                else:
                    # 新的消息开始 (TEXT 或 BINARY)
                    message_opcode = opcode
                    message_payload = payload
                
                # 如果是最终帧，处理并返回完整消息
                if fin:
                    if message_payload:  # 确保有数据
                        _, data = self._process_websocket_frame(message_opcode, message_payload)
                        if data:
                            return message_opcode, data
                    # 重置分片消息的状态
                    message_opcode = None
                    message_payload = b""
        except Exception as e:
            print(f"Unexpected error in receive: {e}")
            sys.print_exception(e)
            self.closed = True
            return self.CLOSE, b"error"

    async def send(self, data, opcode=None):
        frame = self._encode_websocket_frame(
            opcode or (self.TEXT if isinstance(data, str) else self.BINARY), data
        )
        self.writer.write(frame)
        await self.writer.drain()

    async def close(self):
        if not self.closed:  # pragma: no cover
            self.closed = True
            await self.send(b"", self.CLOSE)


class ClientWebSocketResponse:
    def __init__(self, wsclient):
        self.ws = wsclient

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            msg_type, msg_data = await self.ws.receive()
            # 添加更多日志，帮助诊断
            if msg_type == self.ws.CLOSE:
                print(f"WebSocket connection closing: {msg_data}")
                self.ws.closed = True
                raise StopAsyncIteration
            
            if not msg_data and self.ws.closed:
                print("WebSocket already closed, stopping iteration")
                raise StopAsyncIteration
                
            msg = WebSocketMessage(msg_type, msg_data)
            return msg
        except Exception as e:
            print(f"Error in __anext__: {e}")
            sys.print_exception(e)
            self.ws.closed = True
            raise StopAsyncIteration

    async def close(self):
        await self.ws.close()

    async def send_str(self, data):
        if not isinstance(data, str):
            raise TypeError("data argument must be str (%r)" % type(data))
        await self.ws.send(data)

    async def send_bytes(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("data argument must be byte-ish (%r)" % type(data))
        await self.ws.send(data)

    async def send_json(self, data):
        try:
            await self.send_str(_json.dumps(data))
        except Exception as e:
            print(e)
            print("data: ", data)
            raise TypeError("data argument must be json-able")

    async def receive_str(self):
        msg = WebSocketMessage(*await self.ws.receive())
        if msg.type != self.ws.TEXT:
            raise TypeError(f"Received message {msg.type}:{msg.data!r} is not str")
        return msg.data

    async def receive_bytes(self):
        msg = WebSocketMessage(*await self.ws.receive())
        if msg.type != self.ws.BINARY:
            raise TypeError(f"Received message {msg.type}:{msg.data!r} is not bytes")
        return msg.data

    async def receive_json(self):
        try:
            data = await self.receive_str()
            return _json.loads(data)
        except Exception as e:
            sys.print_exception(e)
            print("data: ", data)
            print("data length: ", len(data) if data else 0)
            raise TypeError("data argument must be json-able, error processing large JSON data")


class _WSRequestContextManager:
    def __init__(self, client, request_co):
        self.reqco = request_co
        self.client = client

    async def __aenter__(self):
        return await self.reqco

    async def __aexit__(self, *args):
        await self.client._reader.aclose()
        return await asyncio.sleep(0)

