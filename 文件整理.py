import os  # 文件与目录操作
import sys  # 程序入口参数与退出
import shutil  # 复制/移动文件
import hashlib  # 文件哈希
from pathlib import Path  # 路径对象
from collections import defaultdict  # 默认字典

from PyQt5.QtCore import QThread, pyqtSignal  # 线程与信号
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QTabWidget,  # 基础窗口组件
    QVBoxLayout, QHBoxLayout, QGridLayout,  # 布局
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,  # 常用控件
    QPlainTextEdit, QFileDialog, QMessageBox,  # 文本框/文件选择/消息框
    QGroupBox, QRadioButton, QCheckBox  # 分组框/单选框/复选框
)


CATEGORY_EXTENSIONS = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic", ".ico"},  # 图片扩展名
    "Audio": {".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma", ".ape"},  # 音频扩展名
    "Video": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".mpeg", ".mpg"},  # 视频扩展名
    "Office": {
        ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".pdf", ".csv", ".txt", ".rtf", ".odt", ".ods", ".odp"
    }  # Office/文档类扩展名
}


def normalize_path(path_text: str) -> str:
    return os.path.abspath(os.path.normpath(path_text))  # 统一并规范化绝对路径


def is_subpath(child_path: str, parent_path: str) -> bool:
    child_path = normalize_path(child_path)  # 规范子路径
    parent_path = normalize_path(parent_path)  # 规范父路径
    return os.path.commonpath([child_path, parent_path]) == parent_path  # 判断 child 是否位于 parent 下


def detect_category(file_path: Path):
    file_suffix = file_path.suffix.lower()  # 取后缀并统一小写
    for category_name, extension_set in CATEGORY_EXTENSIONS.items():  # 遍历分类映射
        if file_suffix in extension_set:  # 命中分类
            return category_name  # 返回分类名
    return None  # 不在已知分类内


def split_name_and_suffix(file_name: str):
    file_path = Path(file_name)  # 构造 Path 对象
    full_suffix = "".join(file_path.suffixes)  # 保留完整后缀，例如 .tar.gz
    if full_suffix:
        base_name = file_path.name[:-len(full_suffix)]  # 去掉完整后缀后的主文件名
    else:
        base_name = file_path.name  # 无后缀则直接使用原名
    return base_name, full_suffix  # 返回主名与完整后缀


def build_unique_destination_path(destination_dir: Path, original_name: str) -> Path:
    base_name, full_suffix = split_name_and_suffix(original_name)  # 拆分文件名和后缀

    candidate_path = destination_dir / f"{base_name}{full_suffix}"  # 优先尝试原文件名
    if not candidate_path.exists():
        return candidate_path  # 不存在则可直接使用

    index = 1  # 冲突计数起始值
    while True:
        candidate_path = destination_dir / f"{base_name}_{index}{full_suffix}"  # 自动追加序号避免覆盖
        if not candidate_path.exists():
            return candidate_path  # 找到可用文件名
        index += 1  # 继续尝试下一个序号


def hash_file(file_path: str, chunk_size: int = 1024 * 1024) -> str:
    sha256 = hashlib.sha256()  # 使用 SHA256 计算哈希
    with open(file_path, "rb") as file_obj:  # 二进制读取文件
        while True:
            chunk = file_obj.read(chunk_size)  # 分块读取，避免一次性占用太多内存
            if not chunk:
                break  # 读完结束
            sha256.update(chunk)  # 累计哈希
    return sha256.hexdigest()  # 返回十六进制哈希串


def find_empty_directories(root_dir: str):
    empty_directories = []  # 保存空目录
    for current_dir, child_dirs, child_files in os.walk(root_dir, topdown=False):  # 自底向上扫描，便于删除
        if not child_dirs and not child_files:
            empty_directories.append(current_dir)  # 记录空目录
    empty_directories.sort(key=lambda p: len(Path(p).parts), reverse=True)  # 深层目录优先
    return empty_directories  # 返回空目录列表


class OrganizeWorker(QThread):
    log_signal = pyqtSignal(str)  # 日志输出信号
    finished_signal = pyqtSignal(dict)  # 任务完成信号，返回统计信息

    def __init__(self, source_directories, target_directory, operation_mode, enabled_categories):
        super().__init__()  # 初始化父类线程
        self.source_directories = source_directories  # 源目录列表
        self.target_directory = target_directory  # 目标目录
        self.operation_mode = operation_mode  # copy 或 move
        self.enabled_categories = enabled_categories  # 启用的分类集合

    def run(self):
        summary = {
            "matched_count": 0,  # 匹配到的文件数
            "processed_count": 0,  # 成功处理数
            "skipped_count": 0,  # 跳过数
            "error_count": 0,  # 错误数
            "category_counts": defaultdict(int)  # 各分类数量统计
        }

        target_directory = normalize_path(self.target_directory)  # 规范目标路径
        os.makedirs(target_directory, exist_ok=True)  # 确保目标目录存在

        matched_files = []  # 存储扫描后命中的文件

        self.log_signal.emit("Start scanning source directories...")  # 输出日志

        for source_directory in self.source_directories:  # 遍历每个源目录
            source_directory = normalize_path(source_directory)  # 规范源目录路径
            if not os.path.isdir(source_directory):
                summary["skipped_count"] += 1  # 无效目录记为跳过
                self.log_signal.emit(f"[Skip] Invalid source directory: {source_directory}")  # 输出日志
                continue  # 继续下一个目录

            for current_dir, child_dirs, file_names in os.walk(source_directory, topdown=True):  # 递归扫描目录
                current_dir = normalize_path(current_dir)  # 规范当前目录路径

                if is_subpath(current_dir, target_directory):
                    child_dirs[:] = []  # 阻止继续向目标目录内扫描
                    continue  # 跳过目标目录及其子目录

                for file_name in file_names:  # 遍历当前目录文件
                    file_path = Path(current_dir) / file_name  # 构造完整路径
                    if file_path.is_symlink():
                        summary["skipped_count"] += 1  # 跳过符号链接
                        continue

                    category_name = detect_category(file_path)  # 根据后缀识别分类
                    if category_name and category_name in self.enabled_categories:
                        matched_files.append((file_path, category_name))  # 保存待处理文件及其分类

        matched_files.sort(key=lambda item: str(item[0]).lower())  # 统一排序，保证顺序稳定
        summary["matched_count"] = len(matched_files)  # 写入匹配数

        self.log_signal.emit(f"Matched files: {len(matched_files)}")  # 输出匹配结果

        for index, (source_file_path, category_name) in enumerate(matched_files, start=1):  # 逐个处理文件
            destination_directory = Path(target_directory) / category_name  # 分类子目录
            destination_directory.mkdir(parents=True, exist_ok=True)  # 确保分类目录存在

            destination_file_path = build_unique_destination_path(destination_directory, source_file_path.name)  # 防覆盖重命名

            try:
                if self.operation_mode == "copy":
                    shutil.copy2(str(source_file_path), str(destination_file_path))  # 复制并保留元数据
                    action_name = "Copied"  # 动作名称
                else:
                    shutil.move(str(source_file_path), str(destination_file_path))  # 移动文件
                    action_name = "Moved"  # 动作名称

                summary["processed_count"] += 1  # 成功数加一
                summary["category_counts"][category_name] += 1  # 分类计数加一
                self.log_signal.emit(
                    f"[{index}/{len(matched_files)}] {action_name}: {source_file_path} -> {destination_file_path}"
                )  # 输出处理日志
            except OSError as exc:
                summary["error_count"] += 1  # 错误数加一
                self.log_signal.emit(f"[Error] Failed: {source_file_path} | {exc}")  # 输出错误日志

        self.finished_signal.emit(summary)  # 发出完成信号


class CleanupScanWorker(QThread):
    log_signal = pyqtSignal(str)  # 日志信号
    finished_signal = pyqtSignal(dict)  # 扫描结果信号

    def __init__(self, root_directory):
        super().__init__()  # 初始化线程
        self.root_directory = root_directory  # 扫描根目录

    def run(self):
        result = {
            "duplicate_groups": [],  # 重复文件分组
            "files_to_delete": [],  # 待删除重复文件
            "empty_directories": []  # 空目录列表
        }

        root_directory = normalize_path(self.root_directory)  # 规范路径
        if not os.path.isdir(root_directory):
            self.log_signal.emit("[Error] Invalid scan directory.")  # 日志提示
            self.finished_signal.emit(result)  # 返回空结果
            return

        self.log_signal.emit("Start scanning file sizes...")  # 开始扫描大小

        files_by_size = defaultdict(list)  # 先按文件大小归类
        total_file_count = 0  # 扫描到的文件总数

        for current_dir, _, file_names in os.walk(root_directory):  # 遍历目录
            for file_name in file_names:  # 遍历文件
                file_path = os.path.join(current_dir, file_name)  # 完整文件路径
                if os.path.islink(file_path):
                    continue  # 跳过符号链接

                try:
                    file_size = os.path.getsize(file_path)  # 读取文件大小
                except OSError as exc:
                    self.log_signal.emit(f"[Skip] Cannot read file size: {file_path} | {exc}")  # 日志
                    continue

                files_by_size[file_size].append(file_path)  # 相同大小归为一组
                total_file_count += 1  # 文件数加一

        self.log_signal.emit(f"Total files scanned: {total_file_count}")  # 输出总文件数

        candidate_groups = [group for group in files_by_size.values() if len(group) > 1]  # 仅保留有重复可能的大小组
        candidate_file_count = sum(len(group) for group in candidate_groups)  # 候选文件总数
        self.log_signal.emit(f"Potential duplicate files: {candidate_file_count}")  # 输出候选数

        files_by_hash = defaultdict(list)  # 再按大小+哈希归类
        hashed_count = 0  # 已哈希文件数

        for candidate_group in candidate_groups:  # 遍历大小相同的候选组
            candidate_group.sort(key=lambda p: p.lower())  # 路径排序，保证保留规则稳定
            for file_path in candidate_group:  # 逐个计算哈希
                try:
                    file_size = os.path.getsize(file_path)  # 再次取得大小，作为哈希分组键的一部分
                    file_hash = hash_file(file_path)  # 计算文件哈希
                except OSError as exc:
                    self.log_signal.emit(f"[Skip] Cannot hash file: {file_path} | {exc}")  # 日志
                    continue

                files_by_hash[(file_size, file_hash)].append(file_path)  # 真正重复内容的文件归为一组
                hashed_count += 1  # 哈希计数

                if hashed_count % 20 == 0:
                    self.log_signal.emit(f"Hashed files: {hashed_count}")  # 每 20 个输出一次进度

        duplicate_groups = []  # 存储重复组
        files_to_delete = []  # 存储需要删除的重复文件

        for duplicate_group in files_by_hash.values():  # 遍历哈希分组
            if len(duplicate_group) > 1:
                duplicate_group.sort(key=lambda p: p.lower())  # 排序后默认保留第一个
                duplicate_groups.append(duplicate_group)  # 记录重复组
                files_to_delete.extend(duplicate_group[1:])  # 除首个外都列为删除对象

        empty_directories = find_empty_directories(root_directory)  # 查找空目录

        result["duplicate_groups"] = duplicate_groups  # 写入重复分组
        result["files_to_delete"] = files_to_delete  # 写入待删除文件
        result["empty_directories"] = empty_directories  # 写入空目录

        self.log_signal.emit(f"Duplicate groups: {len(duplicate_groups)}")  # 输出重复组数量
        self.log_signal.emit(f"Duplicate files to delete: {len(files_to_delete)}")  # 输出待删除数量
        self.log_signal.emit(f"Empty directories: {len(empty_directories)}")  # 输出空目录数量

        self.finished_signal.emit(result)  # 发出扫描完成信号


class DeleteDuplicateFilesWorker(QThread):
    log_signal = pyqtSignal(str)  # 删除日志信号
    finished_signal = pyqtSignal(int)  # 删除完成信号，返回删除数量

    def __init__(self, files_to_delete):
        super().__init__()  # 初始化线程
        self.files_to_delete = files_to_delete  # 待删除文件列表

    def run(self):
        deleted_count = 0  # 已删除数量

        for index, file_path in enumerate(self.files_to_delete, start=1):  # 逐个删除
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)  # 删除文件
                    deleted_count += 1  # 删除数加一
                    self.log_signal.emit(
                        f"[{index}/{len(self.files_to_delete)}] Deleted duplicate file: {file_path}"
                    )  # 输出日志
            except OSError as exc:
                self.log_signal.emit(f"[Error] Cannot delete duplicate file: {file_path} | {exc}")  # 输出错误

        self.finished_signal.emit(deleted_count)  # 发出完成信号


class DeleteEmptyDirectoriesWorker(QThread):
    log_signal = pyqtSignal(str)  # 删除日志信号
    finished_signal = pyqtSignal(int)  # 删除完成信号，返回删除数量

    def __init__(self, empty_directories):
        super().__init__()  # 初始化线程
        self.empty_directories = sorted(
            empty_directories,
            key=lambda p: len(Path(p).parts),
            reverse=True
        )  # 深层目录优先删除

    def run(self):
        deleted_count = 0  # 已删除空目录数量

        for index, directory_path in enumerate(self.empty_directories, start=1):  # 逐个处理空目录
            try:
                if os.path.isdir(directory_path) and not os.listdir(directory_path):
                    os.rmdir(directory_path)  # 删除空目录
                    deleted_count += 1  # 删除计数加一
                    self.log_signal.emit(
                        f"[{index}/{len(self.empty_directories)}] Deleted empty directory: {directory_path}"
                    )  # 输出日志
            except OSError as exc:
                self.log_signal.emit(f"[Error] Cannot delete empty directory: {directory_path} | {exc}")  # 输出错误

        self.finished_signal.emit(deleted_count)  # 发出完成信号


class OrganizerTab(QWidget):
    def __init__(self):
        super().__init__()  # 初始化 QWidget
        self.organize_worker = None  # 文件整理线程实例
        self.setup_ui()  # 构建界面

    def setup_ui(self):
        main_layout = QVBoxLayout(self)  # 主垂直布局

        source_group = QGroupBox("Source Directories")  # 源目录分组
        source_layout = QVBoxLayout(source_group)  # 源目录分组布局

        self.source_list_widget = QListWidget()  # 源目录列表控件

        source_button_layout = QHBoxLayout()  # 源目录按钮行
        self.add_source_button = QPushButton("Add")  # 添加源目录按钮
        self.remove_source_button = QPushButton("Remove Selected")  # 删除选中按钮
        self.clear_source_button = QPushButton("Clear")  # 清空按钮
        source_button_layout.addWidget(self.add_source_button)  # 加入布局
        source_button_layout.addWidget(self.remove_source_button)  # 加入布局
        source_button_layout.addWidget(self.clear_source_button)  # 加入布局

        source_layout.addWidget(self.source_list_widget)  # 添加目录列表
        source_layout.addLayout(source_button_layout)  # 添加按钮布局

        target_group = QGroupBox("Target Directory")  # 目标目录分组
        target_layout = QHBoxLayout(target_group)  # 目标目录布局
        self.target_line_edit = QLineEdit()  # 目标目录输入框
        self.target_line_edit.setPlaceholderText("Select target directory")  # 占位提示
        self.browse_target_button = QPushButton("Browse")  # 浏览按钮
        target_layout.addWidget(self.target_line_edit)  # 加入布局
        target_layout.addWidget(self.browse_target_button)  # 加入布局

        operation_group = QGroupBox("Operation Mode")  # 操作模式分组
        operation_layout = QHBoxLayout(operation_group)  # 操作模式布局
        self.copy_radio_button = QRadioButton("Copy")  # 复制模式
        self.move_radio_button = QRadioButton("Move")  # 移动模式
        self.copy_radio_button.setChecked(True)  # 默认选中复制
        operation_layout.addWidget(self.copy_radio_button)  # 加入布局
        operation_layout.addWidget(self.move_radio_button)  # 加入布局
        operation_layout.addStretch()  # 占位拉伸

        category_group = QGroupBox("Categories")  # 分类分组
        category_layout = QGridLayout(category_group)  # 分类网格布局
        self.images_check_box = QCheckBox("Images")  # 图片分类
        self.audio_check_box = QCheckBox("Audio")  # 音频分类
        self.video_check_box = QCheckBox("Video")  # 视频分类
        self.office_check_box = QCheckBox("Office")  # Office 分类

        self.images_check_box.setChecked(True)  # 默认启用
        self.audio_check_box.setChecked(True)  # 默认启用
        self.video_check_box.setChecked(True)  # 默认启用
        self.office_check_box.setChecked(True)  # 默认启用

        category_layout.addWidget(self.images_check_box, 0, 0)  # 加入网格
        category_layout.addWidget(self.audio_check_box, 0, 1)  # 加入网格
        category_layout.addWidget(self.video_check_box, 1, 0)  # 加入网格
        category_layout.addWidget(self.office_check_box, 1, 1)  # 加入网格

        action_layout = QHBoxLayout()  # 操作按钮布局
        self.start_button = QPushButton("Start Organizing")  # 开始整理按钮
        action_layout.addStretch()  # 左侧留白
        action_layout.addWidget(self.start_button)  # 加入布局

        log_group = QGroupBox("Log")  # 日志分组
        log_layout = QVBoxLayout(log_group)  # 日志布局
        self.log_text_edit = QPlainTextEdit()  # 日志文本框
        self.log_text_edit.setReadOnly(True)  # 只读
        log_layout.addWidget(self.log_text_edit)  # 加入布局

        main_layout.addWidget(source_group)  # 添加源目录区域
        main_layout.addWidget(target_group)  # 添加目标目录区域
        main_layout.addWidget(operation_group)  # 添加操作模式区域
        main_layout.addWidget(category_group)  # 添加分类区域
        main_layout.addLayout(action_layout)  # 添加开始按钮区域
        main_layout.addWidget(log_group)  # 添加日志区域

        self.add_source_button.clicked.connect(self.add_source_directory)  # 绑定添加源目录事件
        self.remove_source_button.clicked.connect(self.remove_selected_source_directory)  # 绑定删除选中事件
        self.clear_source_button.clicked.connect(self.source_list_widget.clear)  # 绑定清空列表
        self.browse_target_button.clicked.connect(self.select_target_directory)  # 绑定浏览目标目录事件
        self.start_button.clicked.connect(self.confirm_and_start)  # 绑定开始整理事件

    def log_message(self, message: str):
        print(message)  # 输出到控制台
        self.log_text_edit.appendPlainText(message)  # 输出到界面日志

    def add_source_directory(self):
        selected_directory = QFileDialog.getExistingDirectory(self, "Select Source Directory")  # 选择目录
        if not selected_directory:
            return  # 用户取消

        selected_directory = normalize_path(selected_directory)  # 规范路径

        for row in range(self.source_list_widget.count()):  # 避免重复添加
            if self.source_list_widget.item(row).text() == selected_directory:
                return

        self.source_list_widget.addItem(QListWidgetItem(selected_directory))  # 加入目录列表

    def remove_selected_source_directory(self):
        current_row = self.source_list_widget.currentRow()  # 当前选中行
        if current_row >= 0:
            self.source_list_widget.takeItem(current_row)  # 删除该项

    def select_target_directory(self):
        selected_directory = QFileDialog.getExistingDirectory(self, "Select Target Directory")  # 选择目标目录
        if selected_directory:
            self.target_line_edit.setText(normalize_path(selected_directory))  # 写入输入框

    def collect_source_directories(self):
        return [
            self.source_list_widget.item(index).text()
            for index in range(self.source_list_widget.count())
        ]  # 读取所有源目录

    def collect_enabled_categories(self):
        enabled_categories = []  # 启用的分类
        if self.images_check_box.isChecked():
            enabled_categories.append("Images")  # 启用图片
        if self.audio_check_box.isChecked():
            enabled_categories.append("Audio")  # 启用音频
        if self.video_check_box.isChecked():
            enabled_categories.append("Video")  # 启用视频
        if self.office_check_box.isChecked():
            enabled_categories.append("Office")  # 启用 Office
        return enabled_categories  # 返回分类列表

    def confirm_and_start(self):
        source_directories = self.collect_source_directories()  # 收集源目录
        target_directory = self.target_line_edit.text().strip()  # 读取目标目录
        enabled_categories = self.collect_enabled_categories()  # 收集分类
        operation_mode = "copy" if self.copy_radio_button.isChecked() else "move"  # 当前模式

        if not source_directories:
            QMessageBox.warning(self, "Warning", "Please add at least one source directory.")  # 提示
            return

        if not target_directory:
            QMessageBox.warning(self, "Warning", "Please select a target directory.")  # 提示
            return

        if not enabled_categories:
            QMessageBox.warning(self, "Warning", "Please select at least one category.")  # 提示
            return

        summary_text = (
            f"Operation: {operation_mode.upper()}\n"
            f"Source directories: {len(source_directories)}\n"
            f"Target directory:\n{target_directory}\n\n"
            f"Categories: {', '.join(enabled_categories)}\n\n"
            "Continue?"
        )  # 确认信息文本

        reply = QMessageBox.question(
            self,
            "Confirm Organize",
            summary_text,
            QMessageBox.Yes | QMessageBox.No
        )  # 整理前确认
        if reply != QMessageBox.Yes:
            return  # 用户取消

        self.log_text_edit.clear()  # 清空旧日志
        self.log_message("===== Organize Task Started =====")  # 开始日志
        self.log_message(f"Operation mode: {operation_mode}")  # 输出模式
        self.log_message(f"Target directory: {target_directory}")  # 输出目标目录
        self.log_message(f"Enabled categories: {', '.join(enabled_categories)}")  # 输出分类

        self.start_button.setEnabled(False)  # 防止重复点击

        self.organize_worker = OrganizeWorker(
            source_directories=source_directories,
            target_directory=target_directory,
            operation_mode=operation_mode,
            enabled_categories=enabled_categories
        )  # 创建整理线程
        self.organize_worker.log_signal.connect(self.log_message)  # 绑定日志信号
        self.organize_worker.finished_signal.connect(self.on_organize_finished)  # 绑定完成信号
        self.organize_worker.start()  # 启动线程

    def on_organize_finished(self, summary):
        self.start_button.setEnabled(True)  # 恢复按钮可用

        self.log_message("===== Organize Task Finished =====")  # 完成日志
        self.log_message(f"Matched files: {summary['matched_count']}")  # 输出匹配数
        self.log_message(f"Processed files: {summary['processed_count']}")  # 输出处理数
        self.log_message(f"Skipped items: {summary['skipped_count']}")  # 输出跳过数
        self.log_message(f"Errors: {summary['error_count']}")  # 输出错误数

        for category_name, file_count in summary["category_counts"].items():
            self.log_message(f"{category_name}: {file_count}")  # 输出分类统计

        QMessageBox.information(self, "Done", "Organize task completed.")  # 完成提示


class CleanupTab(QWidget):
    def __init__(self):
        super().__init__()  # 初始化 QWidget
        self.scan_worker = None  # 扫描线程
        self.delete_duplicates_worker = None  # 删除重复文件线程
        self.delete_empty_directories_worker = None  # 删除空目录线程

        self.duplicate_groups = []  # 当前扫描出的重复组
        self.files_to_delete = []  # 当前待删除重复文件
        self.empty_directories = []  # 当前待删除空目录

        self.setup_ui()  # 构建界面

    def setup_ui(self):
        main_layout = QVBoxLayout(self)  # 主布局

        scan_group = QGroupBox("Scan Directory")  # 扫描目录分组
        scan_layout = QHBoxLayout(scan_group)  # 扫描目录布局
        self.scan_directory_line_edit = QLineEdit()  # 扫描目录输入框
        self.scan_directory_line_edit.setPlaceholderText("Select directory for duplicate scan and empty folder cleanup")  # 占位提示
        self.browse_scan_directory_button = QPushButton("Browse")  # 浏览按钮
        scan_layout.addWidget(self.scan_directory_line_edit)  # 加入布局
        scan_layout.addWidget(self.browse_scan_directory_button)  # 加入布局

        action_group = QGroupBox("Actions")  # 操作分组
        action_layout = QHBoxLayout(action_group)  # 操作布局
        self.scan_button = QPushButton("Scan")  # 扫描按钮
        self.delete_duplicates_button = QPushButton("Delete Duplicates")  # 删除重复文件按钮
        self.delete_empty_directories_button = QPushButton("Delete Empty Directories")  # 删除空目录按钮
        self.delete_duplicates_button.setEnabled(False)  # 初始禁用
        self.delete_empty_directories_button.setEnabled(False)  # 初始禁用

        action_layout.addWidget(self.scan_button)  # 加入布局
        action_layout.addWidget(self.delete_duplicates_button)  # 加入布局
        action_layout.addWidget(self.delete_empty_directories_button)  # 加入布局

        result_group = QGroupBox("Result / Log")  # 结果分组
        result_layout = QVBoxLayout(result_group)  # 结果布局
        self.result_text_edit = QPlainTextEdit()  # 结果文本框
        self.result_text_edit.setReadOnly(True)  # 只读
        result_layout.addWidget(self.result_text_edit)  # 加入布局

        main_layout.addWidget(scan_group)  # 添加扫描目录区域
        main_layout.addWidget(action_group)  # 添加操作按钮区域
        main_layout.addWidget(result_group)  # 添加结果区域

        self.browse_scan_directory_button.clicked.connect(self.select_scan_directory)  # 绑定浏览事件
        self.scan_button.clicked.connect(self.start_scan)  # 绑定扫描事件
        self.delete_duplicates_button.clicked.connect(self.confirm_delete_duplicates)  # 绑定删除重复文件事件
        self.delete_empty_directories_button.clicked.connect(self.confirm_delete_empty_directories)  # 绑定删除空目录事件

    def log_message(self, message: str):
        print(message)  # 输出到控制台
        self.result_text_edit.appendPlainText(message)  # 输出到界面日志

    def select_scan_directory(self):
        selected_directory = QFileDialog.getExistingDirectory(self, "Select Scan Directory")  # 选择扫描目录
        if selected_directory:
            self.scan_directory_line_edit.setText(normalize_path(selected_directory))  # 写入输入框

    def start_scan(self):
        root_directory = self.scan_directory_line_edit.text().strip()  # 获取扫描目录
        if not root_directory or not os.path.isdir(root_directory):
            QMessageBox.warning(self, "Warning", "Please select a valid scan directory.")  # 无效目录提示
            return

        reply = QMessageBox.question(
            self,
            "Confirm Scan",
            f"Scan this directory?\n\n{root_directory}",
            QMessageBox.Yes | QMessageBox.No
        )  # 扫描前确认
        if reply != QMessageBox.Yes:
            return  # 用户取消

        self.result_text_edit.clear()  # 清空旧日志
        self.log_message("===== Scan Started =====")  # 开始日志
        self.log_message(f"Scan directory: {root_directory}")  # 输出目录

        self.scan_button.setEnabled(False)  # 扫描期间禁用
        self.delete_duplicates_button.setEnabled(False)  # 禁用删除重复按钮
        self.delete_empty_directories_button.setEnabled(False)  # 禁用删除空目录按钮

        self.scan_worker = CleanupScanWorker(root_directory)  # 创建扫描线程
        self.scan_worker.log_signal.connect(self.log_message)  # 绑定日志信号
        self.scan_worker.finished_signal.connect(self.on_scan_finished)  # 绑定完成信号
        self.scan_worker.start()  # 启动线程

    def on_scan_finished(self, result):
        self.scan_button.setEnabled(True)  # 恢复扫描按钮

        self.duplicate_groups = result["duplicate_groups"]  # 保存重复组
        self.files_to_delete = result["files_to_delete"]  # 保存待删文件
        self.empty_directories = result["empty_directories"]  # 保存空目录

        self.log_message("===== Scan Finished =====")  # 完成日志
        self.log_message(f"Duplicate groups: {len(self.duplicate_groups)}")  # 输出重复组数
        self.log_message(f"Duplicate files removable: {len(self.files_to_delete)}")  # 输出可删除重复文件数
        self.log_message(f"Empty directories removable: {len(self.empty_directories)}")  # 输出可删除空目录数

        if self.duplicate_groups:
            self.log_message("")  # 空行分隔
            self.log_message("Duplicate details:")  # 详情标题
            for group_index, duplicate_group in enumerate(self.duplicate_groups, start=1):  # 逐组输出
                self.log_message(f"Group {group_index}:")  # 组标题
                self.log_message(f"  Keep: {duplicate_group[0]}")  # 默认保留第一个
                for duplicate_file in duplicate_group[1:]:
                    self.log_message(f"  Delete: {duplicate_file}")  # 其余标记删除

        if self.empty_directories:
            self.log_message("")  # 空行分隔
            self.log_message("Empty directories:")  # 详情标题
            for directory_path in self.empty_directories:
                self.log_message(f"  {directory_path}")  # 输出空目录路径

        self.delete_duplicates_button.setEnabled(bool(self.files_to_delete))  # 有可删重复文件才启用按钮
        self.delete_empty_directories_button.setEnabled(bool(self.empty_directories))  # 有空目录才启用按钮

        QMessageBox.information(self, "Done", "Scan completed.")  # 扫描完成提示

    def confirm_delete_duplicates(self):
        if not self.files_to_delete:
            QMessageBox.information(self, "Info", "No duplicate files to delete.")  # 无重复文件可删
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete Duplicates",
            (
                f"Duplicate groups: {len(self.duplicate_groups)}\n"
                f"Files to delete: {len(self.files_to_delete)}\n\n"
                "At least one file in each duplicate group will be kept.\n"
                "Delete extra duplicate files now?"
            ),
            QMessageBox.Yes | QMessageBox.No
        )  # 删除前确认
        if reply != QMessageBox.Yes:
            return  # 用户取消

        self.delete_duplicates_button.setEnabled(False)  # 执行期间禁用按钮

        self.delete_duplicates_worker = DeleteDuplicateFilesWorker(self.files_to_delete)  # 创建删除线程
        self.delete_duplicates_worker.log_signal.connect(self.log_message)  # 绑定日志
        self.delete_duplicates_worker.finished_signal.connect(self.on_delete_duplicates_finished)  # 绑定完成信号
        self.delete_duplicates_worker.start()  # 启动线程

    def on_delete_duplicates_finished(self, deleted_count):
        self.log_message(f"Deleted duplicate files: {deleted_count}")  # 输出删除数量
        self.files_to_delete = []  # 清空待删列表
        self.delete_duplicates_button.setEnabled(False)  # 删除后禁用按钮
        QMessageBox.information(self, "Done", f"Deleted {deleted_count} duplicate files.")  # 提示完成

    def confirm_delete_empty_directories(self):
        if not self.empty_directories:
            QMessageBox.information(self, "Info", "No empty directories to delete.")  # 无空目录可删
            return

        reply = QMessageBox.question(
            self,
            "Confirm Delete Empty Directories",
            (
                f"Empty directories to delete: {len(self.empty_directories)}\n\n"
                "Delete all detected empty directories now?"
            ),
            QMessageBox.Yes | QMessageBox.No
        )  # 删除前确认
        if reply != QMessageBox.Yes:
            return  # 用户取消

        self.delete_empty_directories_button.setEnabled(False)  # 执行期间禁用按钮

        self.delete_empty_directories_worker = DeleteEmptyDirectoriesWorker(self.empty_directories)  # 创建删除线程
        self.delete_empty_directories_worker.log_signal.connect(self.log_message)  # 绑定日志
        self.delete_empty_directories_worker.finished_signal.connect(self.on_delete_empty_directories_finished)  # 绑定完成信号
        self.delete_empty_directories_worker.start()  # 启动线程

    def on_delete_empty_directories_finished(self, deleted_count):
        self.log_message(f"Deleted empty directories: {deleted_count}")  # 输出删除数量
        self.empty_directories = []  # 清空列表
        self.delete_empty_directories_button.setEnabled(False)  # 删除后禁用按钮
        QMessageBox.information(self, "Done", f"Deleted {deleted_count} empty directories.")  # 提示完成


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()  # 初始化主窗口
        self.setWindowTitle("File Organizer and Duplicate Cleaner")  # 设置窗口标题
        self.resize(980, 720)  # 设置窗口大小
        self.setup_ui()  # 构建界面

    def setup_ui(self):
        tab_widget = QTabWidget()  # 选项卡容器
        tab_widget.addTab(OrganizerTab(), "Organize Files")  # 文件整理选项卡
        tab_widget.addTab(CleanupTab(), "Duplicates / Empty Directories")  # 去重与空目录选项卡
        self.setCentralWidget(tab_widget)  # 设置为主窗口中央控件


def build_orange_theme():
    return """
    QWidget {
        background-color: #fff8f4;
        color: #3b2b24;
        font-size: 14px;
        font-family: "Microsoft YaHei", "PingFang SC", "Segoe UI";
    }

    QMainWindow {
        background-color: #fff8f4;
    }

    QTabWidget::pane {
        border: 1px solid #ffb39c;
        background: #fffdfb;
        border-radius: 8px;
    }

    QTabBar::tab {
        background: #ffd8cc;
        color: #5b3124;
        padding: 10px 18px;
        margin-right: 4px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        min-width: 130px;
    }

    QTabBar::tab:selected {
        background: #ff7043;
        color: white;
        font-weight: bold;
    }

    QGroupBox {
        border: 1px solid #ffb39c;
        border-radius: 8px;
        margin-top: 12px;
        padding-top: 12px;
        background: #fffdfb;
        font-weight: bold;
    }

    QGroupBox::title {
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: #d94e1f;
    }

    QLineEdit, QListWidget, QPlainTextEdit {
        background: white;
        border: 1px solid #ffc5b3;
        border-radius: 6px;
        padding: 6px;
        selection-background-color: #ff9b7a;
    }

    QListWidget::item:selected {
        background: #ffe5dc;
        color: #5b3124;
    }

    QPushButton {
        background-color: #ff7043;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 14px;
        font-weight: bold;
    }

    QPushButton:hover {
        background-color: #ff5a26;
    }

    QPushButton:pressed {
        background-color: #e55322;
    }

    QPushButton:disabled {
        background-color: #efb3a1;
        color: #fff5f2;
    }

    QCheckBox, QRadioButton {
        padding: 4px;
        spacing: 8px;
    }
    """  # 橘红色主题样式表


def main():
    app = QApplication(sys.argv)  # 创建应用对象
    app.setStyle("Fusion")  # 使用 Fusion 风格
    app.setStyleSheet(build_orange_theme())  # 应用橘红主题

    window = MainWindow()  # 创建主窗口
    window.show()  # 显示主窗口

    sys.exit(app.exec_())  # 进入事件循环


if __name__ == "__main__":
    main()  # 程序入口
