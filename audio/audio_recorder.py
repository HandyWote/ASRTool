import os
import wave
import time
import struct
import threading
import pyaudio
import math
from typing import Optional, Callable
from datetime import datetime

class AudioRecorder:
    """音频录制管理类"""
    
    def __init__(self, chunk_size: int = 1024, audio_format: int = pyaudio.paInt16,
                 channels: int = 1, rate: int = 16000):
        self.chunk_size = chunk_size
        self.audio_format = audio_format
        self.channels = channels
        self.rate = rate
        
        self.audio = pyaudio.PyAudio()
        # 检查并选择可用的输入设备
        print("正在检查音频输入设备...")
        self.input_device_index = self._get_valid_input_device()
        if self.input_device_index is None:
            print("错误：未找到可用的音频输入设备")
            raise RuntimeError("未找到可用的音频输入设备")
        else:
            print(f"已选择音频输入设备（索引：{self.input_device_index}）")
            
        self.stream: Optional[pyaudio.Stream] = None
        self.frames = []
        self.is_recording = False
        self._record_thread: Optional[threading.Thread] = None
        self.start_time = 0
        self.volume_callback: Optional[Callable[[float], None]] = None
        self.audio_callback: Optional[Callable[[bytes], None]] = None
    
    def __init__(self, chunk_size: int = 1024, audio_format: int = pyaudio.paInt16,
                 channels: int = 1, rate: int = 16000):
        self.chunk_size = chunk_size
        self.audio_format = audio_format
        self.channels = channels
        self.rate = rate
        
        self.audio = pyaudio.PyAudio()
        # 检查并选择可用的输入设备
        print("正在检查音频输入设备...")
        self.input_device_index = self._get_valid_input_device()
        if self.input_device_index is None:
            print("错误：未找到可用的音频输入设备")
            raise RuntimeError("未找到可用的音频输入设备")
        else:
            print(f"已选择音频输入设备（索引：{self.input_device_index}）")
            
        self.stream: Optional[pyaudio.Stream] = None
        self.frames = []
        self.is_recording = False
        self._record_thread: Optional[threading.Thread] = None
        self.start_time = 0
        self.volume_callback: Optional[Callable[[float], None]] = None
        self.audio_callback: Optional[Callable[[bytes], None]] = None
    
    def _get_valid_input_device(self) -> Optional[int]:
        """获取有效的音频输入设备索引"""
        print(f"可用设备数量：{self.audio.get_device_count()}")
        for i in range(self.audio.get_device_count()):
            device_info = self.audio.get_device_info_by_index(i)
            print(f"检查设备 {i}: {device_info.get('name')}")
            if device_info.get('maxInputChannels') > 0:
                print(f"设备 {i} 支持输入，尝试打开音频流...")
                # 验证设备是否真正可用
                try:
                    stream = self.audio.open(
                        format=self.audio_format,
                        channels=self.channels,
                        rate=self.rate,
                        input=True,
                        input_device_index=i,
                        frames_per_buffer=self.chunk_size
                    )
                    stream.close()
                    print(f"设备 {i} 验证成功")
                    return i
                except Exception as e:
                    print(f"设备 {i} 验证失败：{str(e)}")
                    continue
            else:
                print(f"设备 {i} 不支持输入")
        print("未找到任何可用的音频输入设备")
        return None
    
    def start(self):
        """开始录音"""
        if self.is_recording:
            return
            
        self.frames = []
        self.is_recording = True
        self.start_time = time.time()
        
        # 打开音频流，使用已验证的输入设备
        try:
            print("正在打开音频流...")
            self.stream = self.audio.open(
                format=self.audio_format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                input_device_index=self.input_device_index,
                frames_per_buffer=self.chunk_size
            )
            print("音频流打开成功")
        except Exception as e:
            print(f"打开音频流失败：{str(e)}")
            self.is_recording = False
            raise RuntimeError(f"无法启动音频录制：{str(e)}")
        
        # 启动录音线程
        self._record_thread = threading.Thread(target=self._record)
        self._record_thread.daemon = True
        self._record_thread.start()
    
    def stop(self) -> str:
        """停止录音并保存文件
        
        Returns:
            str: 保存的文件路径
        """
        if not self.is_recording:
            return ""
            
        self.is_recording = False
        if self._record_thread:
            self._record_thread.join()
            
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            
        # 确保输出目录存在
        output_dir = os.path.join(os.getcwd(), "recordings")
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成输出文件路径
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(output_dir, f"recording_{timestamp}.wav")
        
        # 保存录音文件
        with wave.open(output_path, 'wb') as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(self.audio.get_sample_size(self.audio_format))
            wf.setframerate(self.rate)
            wf.writeframes(b''.join(self.frames))
            
        return output_path
    
    def get_duration(self) -> float:
        """获取当前录音时长（秒）"""
        if not self.is_recording:
            return 0
        return time.time() - self.start_time
    
    def set_volume_callback(self, callback: Callable[[float], None]):
        """设置音量回调函数
        
        Args:
            callback: 接收音量值(0-1)的回调函数
        """
        self.volume_callback = callback
    
    def set_audio_callback(self, callback: Callable[[bytes], None]):
        """设置音频数据回调函数
        
        Args:
            callback: 接收音频数据的回调函数
        """
        self.audio_callback = callback
    
    def _record(self):
        """录音线程主循环"""
        while self.is_recording and self.stream:
            try:
                data = self.stream.read(self.chunk_size, exception_on_overflow=False)
                if not data:
                    continue
                    
                self.frames.append(data)
                
                # 计算音量并通知
                if self.volume_callback:
                    volume = self._calculate_volume(data)
                    self.volume_callback(volume)
                    
                # 发送音频数据到回调函数
                if self.audio_callback:
                    self.audio_callback(data)
            except Exception as e:
                print(f"录音过程中出现错误：{str(e)}")
                self.is_recording = False
                break
                
    def _calculate_volume(self, data: bytes) -> float:
        """计算音频块的音量值
        
        Args:
            data: 音频数据
            
        Returns:
            float: 音量值(0-1)
        """
        # 将字节转换为整数数组
        count = len(data) // 2
        format = '%dh' % count
        shorts = struct.unpack(format, data)
        
        # 计算音量值
        sum_squares = sum(s * s for s in shorts)
        rms = (sum_squares / count) ** 0.5
        
        # 使用线性映射计算音量值
        normalized = rms / 32767
        # 应用平方根来提高低音量的灵敏度
        volume = min(1.0, math.sqrt(normalized))
        return volume