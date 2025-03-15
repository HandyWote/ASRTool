import logging
import os
from pathlib import Path
import platform
import subprocess
import sys
import webbrowser

# FIX: 修复中文路径报错 https://github.com/WEIFENG2333/AsrTools/issues/18  设置QT_QPA_PLATFORM_PLUGIN_PATH 
plugin_path = os.path.join(sys.prefix, 'Lib', 'site-packages', 'PyQt5', 'Qt5', 'plugins')
os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = plugin_path

from PyQt5.QtCore import Qt, QRunnable, QThreadPool, QObject, pyqtSignal as Signal, pyqtSlot as Slot, QSize, QThread, \
    pyqtSignal, QTimer
from PyQt5.QtGui import QCursor, QColor, QFont
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFileDialog,
                             QTableWidgetItem, QHeaderView, QSizePolicy)
from qfluentwidgets import (ComboBox, PushButton, LineEdit, TableWidget, FluentIcon as FIF,
                            Action, RoundMenu, InfoBar, InfoBarPosition,
                            FluentWindow, BodyLabel, MessageBox, ProgressBar)
from bk_asr.BcutASR import BcutASR
from bk_asr.JianYingASR import JianYingASR
from bk_asr.ASRData import ASRDataSeg

# 设置日志配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class WorkerSignals(QObject):
    finished = Signal(str, str)
    errno = Signal(str, str)


class ASRWorker(QRunnable):
    """ASR处理工作线程"""
    def __init__(self, file_path, asr_engine, export_format):
        super().__init__()
        self.file_path = file_path
        self.asr_engine = asr_engine
        self.export_format = export_format
        self.signals = WorkerSignals()

        self.audio_path = None

    @Slot()
    def run(self):
        try:
            use_cache = True
            
            # 检查文件类型,如果不是音频则转换
            logging.info("[+]正在进ffmpeg转换")
            audio_exts = ['.mp3', '.wav']
            if not any(self.file_path.lower().endswith(ext) for ext in audio_exts):
                temp_audio = self.file_path.rsplit(".", 1)[0] + ".mp3"
                if not video2audio(self.file_path, temp_audio):
                    raise Exception("音频转换失败，确保安装ffmpeg")
                self.audio_path = temp_audio
            else:
                self.audio_path = self.file_path
            
            # 根据选择的 ASR 引擎实例化相应的类
            if self.asr_engine == 'B 接口':
                asr = BcutASR(self.audio_path, use_cache=use_cache)
            elif self.asr_engine == 'J 接口':
                asr = JianYingASR(self.audio_path, use_cache=use_cache)
            # Whisper选项已移除
            else:
                raise ValueError(f"未知的 ASR 引擎: {self.asr_engine}")

            logging.info(f"开始处理文件: {self.file_path} 使用引擎: {self.asr_engine}")
            result = asr.run()
            
            # 根据导出格式选择转换方法
            save_ext = self.export_format.lower()
            if save_ext == 'srt':
                result_text = result.to_srt()
            elif save_ext == 'ass':
                result_text = result.to_ass()
            elif save_ext == 'txt':
                result_text = result.to_txt()
                
            logging.info(f"完成处理文件: {self.file_path} 使用引擎: {self.asr_engine}")
            save_path = self.file_path.rsplit(".", 1)[0] + "." + save_ext
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(result_text)
            self.signals.finished.emit(self.file_path, result_text)
        except Exception as e:
            logging.error(f"处理文件 {self.file_path} 时出错: {str(e)}")
            self.signals.errno.emit(self.file_path, f"处理时出错: {str(e)}")


class ASRWidget(QWidget):
    """ASR处理界面"""

    def __init__(self):
        super().__init__()
        self.max_threads = 3  # 设置最大线程数
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(self.max_threads)
        self.processing_queue = []
        self.workers = {}  # 维护文件路径到worker的映射
        self.audio_recorder = None
        self.duration_timer = QTimer()
        self.duration_timer.timeout.connect(self.update_duration)
        self.stream_asr = None  # 流式ASR实例
        self.init_ui()
        
        self.record_widget.setVisible(False)
        self.file_widget.setVisible(True)

    def setObjectName(self, name):
        """重写 setObjectName 以在名称变更时更新界面"""
        super().setObjectName(name)
        self.update_interface_mode()
        
    def update_interface_mode(self):
        """根据 objectName 更新界面模式"""
        is_record_mode = self.objectName() == "record"
        self.record_widget.setVisible(is_record_mode)
        self.file_widget.setVisible(not is_record_mode)
        self.adjustSize()
        
    def init_ui(self):
        layout = QVBoxLayout(self)

        # ASR引擎选择区域
        engine_layout = QHBoxLayout()
        engine_label = BodyLabel("选择接口:", self)
        engine_label.setFixedWidth(70)
        self.combo_box = ComboBox(self)
        self.combo_box.addItems(['B 接口', 'J 接口'])
        engine_layout.addWidget(engine_label)
        engine_layout.addWidget(self.combo_box)
        layout.addLayout(engine_layout)

        # 导出格式选择区域 
        format_layout = QHBoxLayout()
        format_label = BodyLabel("导出格式:", self)
        format_label.setFixedWidth(70)
        self.format_combo = ComboBox(self)
        self.format_combo.addItems(['TXT', 'SRT', 'ASS'])
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        layout.addLayout(format_layout)




        # 录音控制按钮
        self.record_widget = QWidget(self)
        self.record_layout = QHBoxLayout(self.record_widget)
        
        # 添加录音时长显示
        self.duration_label = BodyLabel("00:00", self)
        self.duration_label.setFixedWidth(60)
        self.record_layout.addWidget(self.duration_label)
        
        # 添加音量指示器
        self.volume_indicator = ProgressBar(self)
        self.volume_indicator.setFixedWidth(100)
        self.volume_indicator.setRange(0, 100)
        self.record_layout.addWidget(self.volume_indicator)
        
        self.start_record_button = PushButton("开始录音", self)
        self.stop_record_button = PushButton("停止录音", self)
        self.start_record_button.clicked.connect(self.start_recording)
        self.stop_record_button.clicked.connect(self.stop_recording)
        self.record_layout.addWidget(self.start_record_button)
        self.record_layout.addWidget(self.stop_record_button)
        self.stop_record_button.setEnabled(False)
        self.record_widget.setVisible(True)
        layout.addWidget(self.record_widget)

        # 文件选择区域
        self.file_widget = QWidget(self)
        file_layout = QHBoxLayout(self.file_widget)
        self.file_input = LineEdit(self)
        self.file_input.setPlaceholderText("拖拽文件或文件夹到这里")
        self.file_input.setReadOnly(True)
        self.file_button = PushButton("选择文件", self)
        self.file_button.clicked.connect(self.select_file)
        file_layout.addWidget(self.file_input)
        file_layout.addWidget(self.file_button)
        layout.addWidget(self.file_widget)

        # 文件列表表格
        self.table = TableWidget(self)
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(['文件名', '状态'])
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        layout.addWidget(self.table)

        # 设置表格列的拉伸模式
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 100)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # 处理按钮
        self.process_button = PushButton("开始处理", self)
        self.process_button.clicked.connect(self.process_files)
        self.process_button.setEnabled(False)  # 初始禁用
        layout.addWidget(self.process_button)

        self.setAcceptDrops(True)

    def on_stream_mode_changed(self, text):
        """处理录音模式切换"""
        # 显示/隐藏录音控制按钮和文件选择区域
        self.record_widget.setVisible(text == '录音模式')
        self.file_widget.setVisible(text != '录音模式')
        
        # 清空文件列表
        if text == '录音模式':
            self.table.setRowCount(0)
            self.update_start_button_state()

    def start_recording(self):
        """开始录音"""
        from audio.audio_recorder import AudioRecorder
        
        if not self.audio_recorder:
            self.audio_recorder = AudioRecorder()
            self.audio_recorder.set_volume_callback(self.update_volume)
        
        self.audio_recorder.start()
        self.duration_timer.start(1000)  # 每秒更新一次时长
        self.start_record_button.setEnabled(False)
        self.stop_record_button.setEnabled(True)

    def stop_recording(self):
        """停止录音并自动处理生成的音频文件"""
        if self.audio_recorder:
            output_path = self.audio_recorder.stop()
            
            if output_path:
                self.add_file_to_table(output_path)
                InfoBar.success(
                    title='录音完成',
                    content=f"录音已保存到: {output_path}",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )
                
                # 自动处理生成的音频文件
                if self.objectName() == 'record':
                    # 使用当前选择的引擎和格式自动处理录音文件
                    self.process_file(output_path)
                    InfoBar.info(
                        title='自动处理',
                        content=f"正在使用{self.combo_box.currentText()}引擎处理录音文件",
                        orient=Qt.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=3000,
                        parent=self
                    )
            
            self.duration_timer.stop()
            self.duration_label.setText("00:00")
            self.volume_indicator.setValue(0)
            self.start_record_button.setEnabled(True)
            self.stop_record_button.setEnabled(False)

    def on_stream_result(self, segment: ASRDataSeg):
        """处理流式识别结果
        
        Args:
            segment: 识别结果片段
        """
        # 在表格中显示识别结果
        row_count = self.table.rowCount()
        self.table.insertRow(row_count)
        
        # 添加时间戳和文本
        time_text = f"{segment.start//1000:02d}:{(segment.start%1000)//10:02d} -> {segment.end//1000:02d}:{(segment.end%1000)//10:02d}"
        time_item = QTableWidgetItem(time_text)
        text_item = QTableWidgetItem(segment.text)
        
        self.table.setItem(row_count, 0, time_item)
        self.table.setItem(row_count, 1, text_item)
        
        # 滚动到最新的行
        self.table.scrollToBottom()

    def update_duration(self):
        """更新录音时长显示"""
        if self.audio_recorder:
            duration = int(self.audio_recorder.get_duration())
            minutes = duration // 60
            seconds = duration % 60
            self.duration_label.setText(f"{minutes:02d}:{seconds:02d}")

    def update_volume(self, volume: float):
        """更新音量显示"""
        self.volume_indicator.setValue(int(volume * 100))

    def select_file(self):
        """选择文件对话框"""
        files, _ = QFileDialog.getOpenFileNames(self, "选择音频或视频文件", "",
                                                "Media Files (*.mp3 *.wav *.ogg *.mp4 *.avi *.mov *.ts)")
        for file in files:
            self.add_file_to_table(file)
        self.update_start_button_state()

    def add_file_to_table(self, file_path):
        """将文件添加到表格中"""
        # 转换为绝对路径
        abs_path = os.path.abspath(file_path)
        
        if self.find_row_by_file_path(abs_path) != -1:
            InfoBar.warning(
                title='文件已存在',
                content=f"文件 {os.path.basename(abs_path)} 已经添加到列表中。",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=2000,
                parent=self
            )
            return

        row_count = self.table.rowCount()
        self.table.insertRow(row_count)
        
        # 使用QTableWidgetItem的setData方法存储完整路径
        filename_item = self.create_non_editable_item(os.path.basename(abs_path))
        filename_item.setData(Qt.UserRole, abs_path)  # 存储完整路径
        
        status_item = self.create_non_editable_item("未处理")
        status_item.setForeground(QColor("gray"))
        
        self.table.setItem(row_count, 0, filename_item)
        self.table.setItem(row_count, 1, status_item)
        
        # 更新开始处理按钮状态
        self.update_start_button_state()

    def create_non_editable_item(self, text):
        """创建不可编辑的表格项"""
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def show_context_menu(self, pos):
        """显示右键菜单"""
        current_row = self.table.rowAt(pos.y())
        if current_row < 0:
            return

        self.table.selectRow(current_row)

        menu = RoundMenu(self)
        reprocess_action = Action(FIF.SYNC, "重新处理")
        delete_action = Action(FIF.DELETE, "删除任务")
        open_dir_action = Action(FIF.FOLDER, "打开文件目录")
        menu.addActions([reprocess_action, delete_action, open_dir_action])

        delete_action.triggered.connect(self.delete_selected_row)
        open_dir_action.triggered.connect(self.open_file_directory)
        reprocess_action.triggered.connect(self.reprocess_selected_file)

        menu.exec(QCursor.pos())

    def delete_selected_row(self):
        """删除选中的行"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            file_path = self.table.item(current_row, 0).data(Qt.UserRole)
            if file_path in self.workers:
                worker = self.workers[file_path]
                worker.signals.finished.disconnect(self.update_table)
                worker.signals.errno.disconnect(self.handle_error)
                # QThreadPool 不支持直接终止线程，通常需要设计任务可中断
                # 这里仅移除引用
                self.workers.pop(file_path, None)
            self.table.removeRow(current_row)
            self.update_start_button_state()

    def open_file_directory(self):
        """打开文件所在目录"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            current_item = self.table.item(current_row, 0)
            if current_item:
                file_path = current_item.data(Qt.UserRole)
                directory = os.path.dirname(file_path)
                try:
                    if platform.system() == "Windows":
                        os.startfile(directory)
                    elif platform.system() == "Darwin":
                        subprocess.Popen(["open", directory])
                    else:
                        subprocess.Popen(["xdg-open", directory])
                except Exception as e:
                    InfoBar.error(
                        title='无法打开目录',
                        content=str(e),
                        orient=Qt.Horizontal,
                        isClosable=True,
                        position=InfoBarPosition.TOP,
                        duration=3000,
                        parent=self
                    )

    def reprocess_selected_file(self):
        """重新处理选中的文件"""
        current_row = self.table.currentRow()
        if current_row >= 0:
            file_path = self.table.item(current_row, 0).data(Qt.UserRole)
            status = self.table.item(current_row, 1).text()
            if status == "处理中":
                InfoBar.warning(
                    title='当前文件正在处理中',
                    content="请等待当前文件处理完成后再重新处理。",
                    orient=Qt.Horizontal,
                    isClosable=True,
                    position=InfoBarPosition.TOP,
                    duration=3000,
                    parent=self
                )
                return
            self.add_to_queue(file_path)

    def add_to_queue(self, file_path):
        """将文件添加到处理队列并更新状态"""
        self.processing_queue.append(file_path)
        self.process_next_in_queue()

    def process_files(self):
        """处理所有未处理的文件"""

        for row in range(self.table.rowCount()):
            if self.table.item(row, 1).text() == "未处理":
                file_path = self.table.item(row, 0).data(Qt.UserRole)
                self.processing_queue.append(file_path)
        self.process_next_in_queue()

    def process_next_in_queue(self):
        """处理队列中的下一个文件"""
        while self.thread_pool.activeThreadCount() < self.max_threads and self.processing_queue:
            file_path = self.processing_queue.pop(0)
            if file_path not in self.workers:
                self.process_file(file_path)

    def process_file(self, file_path):
        """处理单个文件"""
        selected_engine = self.combo_box.currentText()
        selected_format = self.format_combo.currentText()
        worker = ASRWorker(file_path, selected_engine, selected_format)
        worker.signals.finished.connect(self.update_table)
        worker.signals.errno.connect(self.handle_error)
        self.thread_pool.start(worker)
        self.workers[file_path] = worker

        row = self.find_row_by_file_path(file_path)
        if row != -1:
            status_item = self.create_non_editable_item("处理中")
            status_item.setForeground(QColor("orange"))
            self.table.setItem(row, 1, status_item)
            self.update_start_button_state()

    def update_table(self, file_path, result):
        """更新表格中文件的处理状态"""
        row = self.find_row_by_file_path(file_path)
        if row != -1:
            item_status = self.create_non_editable_item("已处理")
            item_status.setForeground(QColor("green"))
            self.table.setItem(row, 1, item_status)

            InfoBar.success(
                title='处理完成',
                content=f"文件 {self.table.item(row, 0).text()} 已处理完成",
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=1500,
                parent=self
            )

        self.workers.pop(file_path, None)
        self.process_next_in_queue()
        self.update_start_button_state()

    def handle_error(self, file_path, error_message):
        """处理错误信息"""
        row = self.find_row_by_file_path(file_path)
        if row != -1:
            item_status = self.create_non_editable_item("错误")
            item_status.setForeground(QColor("red"))
            self.table.setItem(row, 1, item_status)

            InfoBar.error(
                title='处理出错',
                content=error_message,
                orient=Qt.Horizontal,
                isClosable=True,
                position=InfoBarPosition.TOP,
                duration=3000,
                parent=self
            )

        self.workers.pop(file_path, None)
        self.process_next_in_queue()
        self.update_start_button_state()

    def find_row_by_file_path(self, file_path):
        """根据文件路径查找表格中的行号"""
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item.data(Qt.UserRole) == file_path:
                return row
        return -1

    def update_start_button_state(self):
        """根据文件列表更新开始处理按钮的状态"""
        has_unprocessed = any(
            self.table.item(row, 1).text() == "未处理"
            for row in range(self.table.rowCount())
        )
        self.process_button.setEnabled(has_unprocessed)

    def dragEnterEvent(self, event):
        """拖拽进入事件"""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """拖拽释放事件"""
        supported_formats = ('.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.wma',  # 音频格式
                           '.mp4', '.avi', '.mov', '.ts', '.mkv', '.wmv', '.flv', '.webm', '.rmvb')  # 视频格式
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for file in files:
            if os.path.isdir(file):
                for root, dirs, files_in_dir in os.walk(file):
                    for f in files_in_dir:
                        if f.lower().endswith(supported_formats):
                            self.add_file_to_table(os.path.join(root, f))
            elif file.lower().endswith(supported_formats):
                self.add_file_to_table(file)
        self.update_start_button_state()




class ModeWidget(QWidget):
    """模式选择界面"""
    def __init__(self, asr_widget):
        super().__init__()
        self.asr_widget = asr_widget
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)

        # 模式选择
        mode_label = BodyLabel("识别模式", self)
        mode_label.setFont(QFont("Segoe UI", 20, QFont.Bold))
        layout.addWidget(mode_label)

        self.mode_combo = ComboBox(self)
        self.mode_combo.addItems(['普通模式', '录音模式'])
        self.mode_combo.currentTextChanged.connect(self.asr_widget.on_stream_mode_changed)
        layout.addWidget(self.mode_combo)

class MainWindow(FluentWindow):
    """主窗口"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle('ASR Processing Tool')

        # 普通模式界面
        self.asr_widget = ASRWidget()
        self.asr_widget.setObjectName("normal")
        self.addSubInterface(self.asr_widget, FIF.DOCUMENT, '普通模式')

        # 录音模式界面
        self.record_widget = ASRWidget()
        self.record_widget.setObjectName("record")
        self.addSubInterface(self.record_widget, FIF.MICROPHONE, '录音模式')


def video2audio(input_file: str, output: str = "") -> bool:
    """使用ffmpeg将视频转换为音频"""
    # 创建output目录
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output = str(output)

    cmd = [
        'ffmpeg',
        '-i', input_file,
        '-ac', '1',
        '-f', 'mp3',
        '-af', 'aresample=async=1',
        '-y',
        output
    ]
    result = subprocess.run(cmd, capture_output=True, check=True, encoding='utf-8', errors='replace')

    if result.returncode == 0 and Path(output).is_file():
        return True
    else:
        return False

def start():
    # enable dpi scale
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    # setTheme(Theme.DARK)  # 如果需要深色主题，取消注释此行
    window = MainWindow()
    window.show()
    window.activateWindow()  # 确保窗口被激活
    window.raise_()  # 将窗口置于最前
    sys.exit(app.exec_())


if __name__ == '__main__':
    start()
