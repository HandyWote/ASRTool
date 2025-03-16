# AsrTools

> 本项目基于 [WEIFENG2333/AsrTools](https://github.com/WEIFENG2333/AsrTools) 项目修改，在原有基础上增加了录音模式、优化了缓存机制，并提供了更友好的用户界面。

## 项目说明

本项目是一个多平台语音识别工具。项目采用模块化设计，便于扩展和维护。主要提供以下功能：

- **普通模式**：支持对本地音频文件进行语音识别，自动生成字幕文本
- **录音模式**：支持实时录音并进行语音识别，适用于会议记录、实时字幕等场景
- **字幕导出**：支持将识别结果导出为多种字幕格式，如SRT、TXT等

## 技术原理

项目采用统一的ASR（自动语音识别）接口设计，通过工厂模式动态创建不同平台的ASR实例。主要技术特点：

1. **模块化ASR引擎**：
   - BaseASR：定义统一的ASR接口
   - BcutASR：必剪语音识别实现
   - JianYingASR：剪映语音识别实现

2. **智能缓存机制**：
   - 使用CRC32对音频文件进行校验
   - 缓存识别结果，避免重复识别
   - 支持缓存过期和手动清理

## 功能流程

```mermaid
graph TB
    %% 定义样式
    classDef handDrawn font-family:'Comic Sans MS',stroke-width:3px,fill:#FFF;
    classDef startEnd fill:#4CAF50,stroke:#388E3C,color:white;
    classDef process fill:#2196F3,stroke:#1976D2,color:white;
    classDef decision fill:#FF9800,stroke:#F57C00,color:white;
    classDef cache stroke-dasharray:5 5;
    linkStyle default stroke:#666,stroke-width:2px;

    %% 流程图结构
    Start([开始]):::startEnd --> Mode{选择模式}:::decision
    Mode -->|📁 普通模式| A[选择音频文件]:::process
    Mode -->|🎤 录音模式| Rec[开始录音]:::process
    Rec --> Stop[⏹️ 停止录音]:::process
    Stop --> A
    A --> B{选择平台}:::decision
    B -->|✂️ Bcut| C1[BcutASR]:::process
    B -->|✂️ 剪映| C2[JianYingASR]:::process
    C1 --> D[📦 加载音频文件]:::process
    C2 --> D
    D --> E[🔢 计算CRC32]:::process
    E --> F{📥 检查缓存}:::decision
    F -->|✅ 命中| G[返回ASRData]:::process
    F -->|❌ 未命中| H[☁️ 调用API识别]:::process
    H --> I1[⏫ 分片上传]:::process
    H --> I2[⤴️ 直接提交]:::process
    I1 --> J[🔄 轮询状态]:::process
    I2 --> J
    J --> K[📥 获取响应]:::process
    K --> L[🔍 解析数据]:::process
    L --> M[⚙️ 生成ASRData]:::process
    M --> N[💾 保存缓存]:::process
    N --> G
    G --> O[📝 输出字幕]:::process
    O --> End([结束]):::startEnd

    %% 虚线框区域
    subgraph 缓存系统
    F
    G
    N
    end

    %% 样式增强
    style 缓存系统 stroke:#9E9E9E,stroke-dasharray:5,5,fill:none
    class F,G,N cache;
```

## 主要特性

- 多平台支持：支持必剪、剪映和Whisper等多个语音识别平台
- 缓存机制：通过CRC32校验实现音频识别结果缓存
- 模块化设计：统一的ASR接口，便于扩展新的识别平台
- 音频格式支持：支持wav、mp3、m4a、flac等多种音频格式
- 实时录音：支持实时录音并识别，可用于会议记录
- 友好界面：提供图形用户界面，操作简单直观
- 字幕格式：支持多种字幕格式导出

## 使用说明

1. 安装依赖
```bash
pip install -r requirements.txt
```

2. 命令行使用
```python
from bk_asr import transcribe

# 使用必剪平台进行识别
result = transcribe("audio.mp3", "bcut")
print(result.text)  # 输出识别文本

# 使用剪映平台进行识别
result = transcribe("audio.wav", "jianying")
result.save_srt("output.srt")  # 保存为SRT字幕

```

3. 图形界面使用
```bash
# 启动GUI程序
python asr_gui.py
```

4. 录音模式
```python
from audio.audio_recorder import AudioRecorder
from bk_asr import transcribe

# 创建录音实例
recorder = AudioRecorder()

# 开始录音
recorder.start_recording("record.wav")

# 停止录音
recorder.stop_recording()

# 识别录音文件
result = transcribe("record.wav", "whisper")
print(result.text)
```