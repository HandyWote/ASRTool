import json
import logging
import os
import zlib
import tempfile
import threading
import requests
from typing import Optional, Dict

from .ASRData import ASRDataSeg, ASRData


class BaseASR:
    """语音识别基类
    
    提供了基础的音频文件处理、缓存管理和HTTP请求功能。子类需要实现具体的ASR服务对接逻辑。
    
    属性:
        SUPPORTED_SOUND_FORMAT: 支持的音频格式列表
        CACHE_FILE: 缓存文件路径
        _lock: 线程锁，用于保护缓存文件的并发访问
    """
    
    SUPPORTED_SOUND_FORMAT = ["flac", "m4a", "mp3", "wav"]
    CACHE_FILE = os.path.join(tempfile.gettempdir(), "bk_asr", "asr_cache.json")
    _lock = threading.Lock()

    def __init__(self, audio_path: [str, bytes], use_cache: bool = False):
        """初始化ASR实例
        
        Args:
            audio_path: 音频文件路径或二进制数据
            use_cache: 是否启用缓存功能
        """
        self.audio_path = audio_path
        self.file_binary = None

        self.crc32_hex = None  # 音频文件的CRC32校验值
        self.use_cache = use_cache

        self._set_data()

        self.cache = self._load_cache()

    def _load_cache(self) -> Dict:
        """加载缓存数据
        
        从缓存文件中读取历史识别结果。如果缓存文件不存在或损坏，则返回空字典。
        使用线程锁确保并发安全。
        
        Returns:
            包含历史识别结果的字典
        """
        if not self.use_cache:
            return {}
        os.makedirs(os.path.dirname(self.CACHE_FILE), exist_ok=True)
        with self._lock:
            if os.path.exists(self.CACHE_FILE):
                try:
                    with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                        cache = json.load(f)
                        if isinstance(cache, dict):
                            return cache
                except (json.JSONDecodeError, IOError):
                    return {}
            return {}

    def _save_cache(self) -> None:
        """保存缓存数据
        
        将当前的识别结果写入缓存文件。使用线程锁确保并发安全。
        如果缓存文件大小超过10MB，则自动清理缓存。
        """
        if not self.use_cache:
            return
        with self._lock:
            try:
                with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                    json.dump(self.cache, f, ensure_ascii=False, indent=2)
                if os.path.exists(self.CACHE_FILE) and os.path.getsize(self.CACHE_FILE) > 10 * 1024 * 1024:
                    os.remove(self.CACHE_FILE)
            except IOError as e:
                logging.error(f"Failed to save cache: {e}")

    def _set_data(self) -> None:
        """设置音频数据
        
        读取音频文件或二进制数据，并计算CRC32校验值。
        支持从文件路径或直接的二进制数据读取。
        
        Raises:
            AssertionError: 当文件格式不支持或文件不存在时
        """
        if isinstance(self.audio_path, bytes):
            self.file_binary = self.audio_path
        else:
            ext = self.audio_path.split(".")[-1].lower()
            assert ext in self.SUPPORTED_SOUND_FORMAT, f"Unsupported sound format: {ext}"
            assert os.path.exists(self.audio_path), f"File not found: {self.audio_path}"
            with open(self.audio_path, "rb") as f:
                self.file_binary = f.read()
        crc32_value = zlib.crc32(self.file_binary) & 0xFFFFFFFF
        self.crc32_hex = format(crc32_value, '08x')

    def _get_key(self) -> str:
        """生成缓存键
        
        根据类名和音频文件的CRC32校验值生成唯一的缓存键。
        
        Returns:
            str: 缓存键字符串
        """
        return f"{self.__class__.__name__}-{self.crc32_hex}"

    def run(self) -> ASRData:
        """执行语音识别
        
        主要流程：
        1. 检查缓存中是否存在结果
        2. 如果没有缓存，调用具体ASR服务进行识别
        3. 将识别结果保存到缓存
        4. 解析识别结果生成字幕片段
        
        Returns:
            ASRData: 包含识别结果的数据对象
        """
        k = self._get_key()
        if k in self.cache and self.use_cache:
            resp_data = self.cache[k]
        else:
            resp_data = self._run()
            # Cache the result
            self.cache[k] = resp_data
            self._save_cache()
        segments = self._make_segments(resp_data)
        return ASRData(segments)

    def _make_segments(self, resp_data: dict) -> list[ASRDataSeg]:
        raise NotImplementedError("_make_segments method must be implemented in subclass")

    def _run(self) -> dict:
        """ Run the ASR service and return the response data. """
        raise NotImplementedError("_run method must be implemented in subclass")
        
    def _make_http_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """统一的HTTP请求处理
        
        Args:
            method: HTTP方法 (GET, POST, PUT等)
            url: 请求URL
            **kwargs: 请求参数
            
        Returns:
            Response对象
            
        Raises:
            requests.exceptions.RequestException: 当请求失败时
        """
        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            logging.error(f"HTTP请求失败: {e}")
            raise
            
    def _handle_response(self, response: requests.Response, error_msg: str = "请求失败") -> dict:
        """统一的响应处理
        
        Args:
            response: Response对象
            error_msg: 错误信息
            
        Returns:
            解析后的JSON数据
            
        Raises:
            ValueError: 当响应状态异常或解析失败时
        """
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError(f"{error_msg}: 响应格式错误")
            return data
        except (ValueError, json.JSONDecodeError) as e:
            logging.error(f"{error_msg}: {e}")
            raise ValueError(f"{error_msg}: {str(e)}")



