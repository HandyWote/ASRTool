import io
import threading
from typing import Optional, Callable
from queue import Queue
from .ASRData import ASRDataSeg, ASRData

class StreamBaseASR:
    """流式ASR基类，用于处理实时音频输入和识别"""
    
    CHUNK_SIZE = 1024 * 16  # 16KB 音频块大小
    MAX_QUEUE_SIZE = 100    # 最大队列大小
    
    def __init__(self):
        self.audio_queue = Queue(maxsize=self.MAX_QUEUE_SIZE)
        self.result_callback: Optional[Callable[[ASRDataSeg], None]] = None
        self.is_running = False
        self._process_thread: Optional[threading.Thread] = None
        self._buffer = io.BytesIO()
        self._lock = threading.Lock()
    
    def set_result_callback(self, callback: Callable[[ASRDataSeg], None]):
        """设置识别结果回调函数
        
        Args:
            callback: 回调函数，接收ASRDataSeg作为参数
        """
        self.result_callback = callback
    
    def feed_audio(self, audio_chunk: bytes) -> bool:
        """输入音频数据
        
        Args:
            audio_chunk: 音频数据块
            
        Returns:
            bool: 是否成功加入队列
        """
        try:
            self.audio_queue.put(audio_chunk, block=False)
            return True
        except Queue.Full:
            return False
    
    def start(self):
        """启动流式识别"""
        if self.is_running:
            return
            
        self.is_running = True
        self._process_thread = threading.Thread(target=self._process_audio)
        self._process_thread.daemon = True
        self._process_thread.start()
    
    def stop(self):
        """停止流式识别"""
        self.is_running = False
        if self._process_thread:
            self._process_thread.join()
            self._process_thread = None
        
        # 处理剩余的音频数据
        with self._lock:
            if self._buffer.tell() > 0:
                self._process_buffer()
    
    def _process_audio(self):
        """处理音频数据的主循环"""
        while self.is_running:
            try:
                chunk = self.audio_queue.get(timeout=0.1)
                with self._lock:
                    self._buffer.write(chunk)
                    
                    # 当缓冲区达到指定大小时进行处理
                    if self._buffer.tell() >= self.CHUNK_SIZE:
                        self._process_buffer()
            except Queue.Empty:
                continue
    
    def _process_buffer(self):
        """处理缓冲区中的音频数据
        
        子类需要实现此方法来处理具体的识别逻辑
        """
        raise NotImplementedError("_process_buffer method must be implemented in subclass")
    
    def _notify_result(self, segment: ASRDataSeg):
        """通知识别结果
        
        Args:
            segment: 识别结果片段
        """
        if self.result_callback:
            self.result_callback(segment)