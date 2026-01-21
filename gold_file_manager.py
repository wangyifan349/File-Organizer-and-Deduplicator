# -*- coding: utf-8 -*-
"""
gold_file_manager.py
A safe and user-friendly file organization and deduplication tool using PyQt5, 
with a gold theme.
Main Features:
- File organization: Classify office/image/audio/video files to categorized directories,
  handling name conflicts safely.
- File deduplication: Check files by hash and keep only one for each unique content.
- Two-tab UX: One for organization, one for deduplication, both working in background threads.
- Modern gold UI theme, large controls for ease of use, safety checks throughout.
"""
import os                                                  # OS operations
import sys                                                 # System interaction
import shutil                                              # Copying files with metadata
import hashlib                                             # For file hashing
from PyQt5.QtWidgets import (
    QApplication, QWidget, QMainWindow, QFileDialog, QPushButton,
    QLineEdit, QLabel, QVBoxLayout, QHBoxLayout, QTabWidget,
    QMessageBox, QTextEdit, QProgressBar
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal           # For multithreading and signals
from collections import defaultdict                        # For grouping files by type
# ===== File type definitions =========================================================
FILE_TYPE_EXTENSION_MAP = {
    'office': ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.pdf'],
    'image':  ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'],
    'audio':  ['.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a'],
    'video':  ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv', '.rmvb'],
}
def get_file_category_by_extension(file_extension):
    """
    Returns the file category by extension, or None if not classified.
    """
    extension_lowercase = file_extension.lower()
    for category, extension_list in FILE_TYPE_EXTENSION_MAP.items():
        if extension_lowercase in extension_list:
            return category
    return None
def ensure_directory_exists(directory_path):
    """
    Ensures a directory exists, creates it if not.
    """
    if not os.path.exists(directory_path):
        os.makedirs(directory_path)
def calculate_file_md5(file_path):
    """
    Calculates the MD5 hash of a file. Returns None if any error occurs.
    """
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as file:
            for chunk in iter(lambda: file.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception as error:
        return None
# ====== File Organization Worker Thread =============================================
class FileOrganizationWorker(QThread):
    """
    Background thread for scanning and copying files by category.
    Emits log, progress, and finish signals for UI update.
    """
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()
    def __init__(self, source_root_directory, target_base_directory):
        super().__init__()
        self.source_root_directory = source_root_directory
        self.target_base_directory = target_base_directory

    def run(self):
        """
        Main worker thread run method.
        1. Scan source directory for classified files;
        2. Copy them to target category directories, resolve name conflicts safely;
        3. Update log, progress, and done signal.
        """
        try:
            self.log_signal.emit("Scanning files...")                                  # Notify UI: start scan
            categorized_file_paths = defaultdict(list)                                 # {category: [full_path, ...]}
            total_files_count = 0                                                      # Used for progress reporting

            # Step 1: Scan and categorize all files in source directory recursively
            for directory_path, _, file_names in os.walk(self.source_root_directory):
                for file_name in file_names:
                    file_extension = os.path.splitext(file_name)[1]
                    file_category = get_file_category_by_extension(file_extension)
                    if file_category:
                        full_file_path = os.path.join(directory_path, file_name)
                        categorized_file_paths[file_category].append(full_file_path)
                        total_files_count += 1

            # Step 2: Prepare the target category folders
            category_target_directory_map = {
                'office': os.path.join(self.target_base_directory, 'Office'),
                'image':  os.path.join(self.target_base_directory, 'Images'),
                'audio':  os.path.join(self.target_base_directory, 'Audio'),
                'video':  os.path.join(self.target_base_directory, 'Video'),
            }
            for directory in category_target_directory_map.values():
                ensure_directory_exists(directory)

            processed_files_count = 0

            # Step 3: Copy files for each category, renaming duplicates
            for category, file_path_list in categorized_file_paths.items():
                for source_file_path in file_path_list:
                    file_name = os.path.basename(source_file_path)
                    target_directory = category_target_directory_map[category]
                    destination_file_path = os.path.join(target_directory, file_name)

                    file_name_base, file_extension = os.path.splitext(file_name)
                    version_index = 1

                    # If duplicate name: check if identical by hash, if not, rename with suffix
                    while os.path.exists(destination_file_path):
                        if calculate_file_md5(destination_file_path) == calculate_file_md5(source_file_path):
                            break                                                      # Identical, skip copy
                        destination_file_path = os.path.join(
                            target_directory, 
                            f"{file_name_base}_{version_index}{file_extension}"
                        )
                        version_index += 1

                    # Skip copy if identical already exists, otherwise copy file (with new name if needed)
                    if not os.path.exists(destination_file_path):
                        shutil.copy2(source_file_path, destination_file_path)          # Copy with metadata

                    processed_files_count += 1
                    self.progress_signal.emit(int(100 * processed_files_count / total_files_count))   # Update progress

                self.log_signal.emit(f"Category '{category}' finished organizing.")

            self.log_signal.emit("All files have been organized.")
        except Exception as error:
            self.log_signal.emit(f"Error: {str(error)}")                                # Log any errors
        self.finished_signal.emit()                                                     # Notify UI: finished

# ====== File Deduplication Worker Thread ============================================

class FileDeduplicationWorker(QThread):
    """
    Background thread for deduplicating files by content in a directory.
    Emits log, progress, and finish signals for UI update.
    """
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal()

    def __init__(self, target_directory):
        super().__init__()
        self.target_directory = target_directory

    def run(self):
        """
        Main worker thread run method.
        1. Scan files, compute their hashes;
        2. For files with the same hash, delete duplicates;
        3. Update UI via signals.
        """
        try:
            self.log_signal.emit("Calculating file hashes...")                           # UI log: start hash pass
            hash_to_file_paths_map = defaultdict(list)                                   # {hash: [file1, file2, ...]}
            all_file_paths = []

            # Step 1: Scan all files recursively to a list
            for directory_path, _, file_names in os.walk(self.target_directory):
                for file_name in file_names:
                    full_file_path = os.path.join(directory_path, file_name)
                    all_file_paths.append(full_file_path)

            total_files_count = len(all_file_paths)

            # Step 2: Compute and group by hash
            for index, file_path in enumerate(all_file_paths):
                file_md5 = calculate_file_md5(file_path)
                if file_md5:
                    hash_to_file_paths_map[file_md5].append(file_path)
                self.progress_signal.emit(int(100 * (index + 1) / total_files_count))    # Progress update

            self.log_signal.emit("Checking duplicate files...")

            deleted_files_count = 0

            # Step 3: For each group of identical files, keep one and delete the rest
            for duplicate_file_list in hash_to_file_paths_map.values():
                for redundant_file_path in duplicate_file_list[1:]:                      # Keep first, delete the rest
                    if os.path.exists(redundant_file_path):
                        try:
                            os.remove(redundant_file_path)
                            self.log_signal.emit(f"Deleted duplicate: {redundant_file_path}")
                            deleted_files_count += 1
                        except Exception as error:
                            self.log_signal.emit(f"Failed to delete {redundant_file_path}: {str(error)}")

            self.log_signal.emit(f"Deduplication complete, {deleted_files_count} file(s) deleted.")
        except Exception as error:
            self.log_signal.emit(f"Error: {str(error)}")
        self.finished_signal.emit()                                                     # Notify UI: finished

# ====== Tab Widget for File Organization ============================================

class FileOrganizationTab(QWidget):
    """
    Tab for file organization. Lets user pick source and target directory, 
    start background scan/copy, and view log/progress.
    """
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self.worker_thread = None                                                      # Will store running worker

    def _setup_ui(self):
        layout = QVBoxLayout()
        font = self.font()
        font.setPointSize(11)
        self.setFont(font)

        # ----- Source Dir -----
        source_layout = QHBoxLayout()
        self.source_directory_line_edit = QLineEdit()
        self.source_directory_line_edit.setPlaceholderText("Select source directory")
        self.source_directory_line_edit.setMinimumHeight(36)
        browse_source_button = QPushButton("Browse")
        browse_source_button.setMinimumHeight(36)
        browse_source_button.clicked.connect(self._browse_source_directory)
        source_layout.addWidget(QLabel("Source:"))
        source_layout.addWidget(self.source_directory_line_edit)
        source_layout.addWidget(browse_source_button)
        layout.addLayout(source_layout)

        # ----- Target Dir -----
        target_layout = QHBoxLayout()
        self.target_directory_line_edit = QLineEdit()
        self.target_directory_line_edit.setPlaceholderText("Select target directory")
        self.target_directory_line_edit.setMinimumHeight(36)
        browse_target_button = QPushButton("Browse")
        browse_target_button.setMinimumHeight(36)
        browse_target_button.clicked.connect(self._browse_target_directory)
        target_layout.addWidget(QLabel("Target:"))
        target_layout.addWidget(self.target_directory_line_edit)
        target_layout.addWidget(browse_target_button)
        layout.addLayout(target_layout)

        # ----- Start Button -----
        self.start_organize_button = QPushButton("Start Organizing")
        self.start_organize_button.setMinimumHeight(40)
        self.start_organize_button.setStyleSheet("font-size:18px;")
        self.start_organize_button.clicked.connect(self._on_start)
        layout.addWidget(self.start_organize_button)

        # ----- Progress Bar -----
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(15)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # ----- Log Text Box -----
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setMinimumHeight(150)
        self.log_text_edit.setReadOnly(True)
        layout.addWidget(self.log_text_edit)

        layout.addStretch()
        self.setLayout(layout)

    def _browse_source_directory(self):
        """
        Show directory picker for source directory.
        """
        selected_directory = QFileDialog.getExistingDirectory(self, "Select source directory to organize")
        if selected_directory:
            self.source_directory_line_edit.setText(selected_directory)

    def _browse_target_directory(self):
        """
        Show directory picker for target directory.
        """
        selected_directory = QFileDialog.getExistingDirectory(self, "Select target directory for categorized files")
        if selected_directory:
            self.target_directory_line_edit.setText(selected_directory)

    def _on_start(self):
        """
        Slot to handle 'Start Organizing' button. Runs checks and starts background worker.
        """
        source_directory = self.source_directory_line_edit.text().strip()
        target_directory = self.target_directory_line_edit.text().strip()
        if (not source_directory) or (not target_directory) or (not os.path.isdir(source_directory)) or (not os.path.isdir(target_directory)):
            QMessageBox.warning(self, "Error", "Please choose valid source and target directories.")
            return

        if os.path.abspath(source_directory) == os.path.abspath(target_directory):
            QMessageBox.warning(self, "Error", "Source and target directories cannot be the same.")
            return

        self.log_text_edit.clear()                                                     # Clear old log
        self.start_organize_button.setEnabled(False)                                   # Disable button during job

        # Start worker thread for file organization
        self.worker_thread = FileOrganizationWorker(source_directory, target_directory)
        self.worker_thread.log_signal.connect(self._append_log)
        self.worker_thread.progress_signal.connect(self.progress_bar.setValue)
        self.worker_thread.finished_signal.connect(self._on_job_finished)
        self.worker_thread.start()

    def _append_log(self, message):
        """
        Slot for worker log signal. Appends message to log text.
        """
        self.log_text_edit.append(message)
        self.log_text_edit.ensureCursorVisible()

    def _on_job_finished(self):
        """
        Slot for job finished signal. Shows dialog and re-enables button.
        """
        QMessageBox.information(self, "Complete", "File organization complete!")
        self.start_organize_button.setEnabled(True)
        self.progress_bar.setValue(0)

# ====== Tab Widget for File Deduplication ===========================================

class FileDeduplicationTab(QWidget):
    """
    Tab for file deduplication. Lets user pick a directory and deduplicate files in it.
    """
    def __init__(self):
        super().__init__()
        self._setup_ui()
        self.worker_thread = None                                                      # Will store running worker

    def _setup_ui(self):
        layout = QVBoxLayout()
        font = self.font()
        font.setPointSize(11)
        self.setFont(font)

        # ----- Directory Picker -----
        dir_layout = QHBoxLayout()
        self.deduplication_directory_line_edit = QLineEdit()
        self.deduplication_directory_line_edit.setPlaceholderText("Select directory to remove duplicates")
        self.deduplication_directory_line_edit.setMinimumHeight(36)
        browse_directory_button = QPushButton("Browse")
        browse_directory_button.setMinimumHeight(36)
        browse_directory_button.clicked.connect(self._browse_deduplication_directory)
        dir_layout.addWidget(QLabel("Deduplication target:"))
        dir_layout.addWidget(self.deduplication_directory_line_edit)
        dir_layout.addWidget(browse_directory_button)
        layout.addLayout(dir_layout)

        # ----- Start Button -----
        self.start_deduplication_button = QPushButton("Start Deduplication")
        self.start_deduplication_button.setMinimumHeight(40)
        self.start_deduplication_button.setStyleSheet("font-size:18px;")
        self.start_deduplication_button.clicked.connect(self._on_start)
        layout.addWidget(self.start_deduplication_button)

        # ----- Progress Bar -----
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimumHeight(15)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # ----- Log Text Box -----
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setMinimumHeight(150)
        self.log_text_edit.setReadOnly(True)
        layout.addWidget(self.log_text_edit)

        layout.addStretch()
        self.setLayout(layout)

    def _browse_deduplication_directory(self):
        """
        Show directory picker for deduplication directory.
        """
        selected_directory = QFileDialog.getExistingDirectory(self, "Select directory to deduplicate")
        if selected_directory:
            self.deduplication_directory_line_edit.setText(selected_directory)

    def _on_start(self):
        """
        Start deduplication process in a worker thread.
        """
        directory_to_deduplicate = self.deduplication_directory_line_edit.text().strip()
        if (not directory_to_deduplicate) or (not os.path.isdir(directory_to_deduplicate)):
            QMessageBox.warning(self, "Error", "Please choose a valid directory to deduplicate.")
            return

        self.log_text_edit.clear()
        self.start_deduplication_button.setEnabled(False)

        self.worker_thread = FileDeduplicationWorker(directory_to_deduplicate)
        self.worker_thread.log_signal.connect(self._append_log)
        self.worker_thread.progress_signal.connect(self.progress_bar.setValue)
        self.worker_thread.finished_signal.connect(self._on_job_finished)
        self.worker_thread.start()

    def _append_log(self, message):
        """
        Append a message to the log.
        """
        self.log_text_edit.append(message)
        self.log_text_edit.ensureCursorVisible()

    def _on_job_finished(self):
        """
        Show completion dialog and re-enable button.
        """
        QMessageBox.information(self, "Complete", "Deduplication process is finished!")
        self.start_deduplication_button.setEnabled(True)
        self.progress_bar.setValue(0)

# ====== Main Application Window =====================================================

class MainWindow(QMainWindow):
    """
    Main logic and UI window for the tool, handles both tab pages.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Organizer & Deduplication Tool")
        self.resize(700, 460)
        main_tab_widget = QTabWidget()
        main_tab_widget.setFont(self.font())
        main_tab_widget.addTab(FileOrganizationTab(), "Organize Files")
        main_tab_widget.addTab(FileDeduplicationTab(), "Remove Duplicates")
        self.setCentralWidget(main_tab_widget)
        self.setStyleSheet(self._gold_theme_qss())

    def _gold_theme_qss(self):
        """
        Returns gold-colored QSS string for styling the UI.
        """
        return """
QMainWindow{background:#26221B;}
QTabWidget::pane { border: 2px solid #FFD700; }
QTabBar::tab:selected {background: #FFD700; color:#202020;}
QTabBar::tab { background: #766339; color:#FFD700; font-size:18px; min-width:110px; min-height:30px; border-radius:8px;}
QPushButton { background:#FFD700; color:#202020; font-weight:bold; border:none; border-radius:8px; min-width:100px; min-height:36px;}
QPushButton:pressed {background:#CCAC00;}
QProgressBar { border:1px solid #FFD700; background:#685d3d; height:22px; border-radius:8px; text-align:center; color:#FFD700;}
QProgressBar::chunk { background-color: #FFD700; }
QLineEdit, QTextEdit { background: #FFF8DC; color:#222; border:1px solid #FFD700; border-radius:7px;}
QLabel{color:#FFD700; font-size:16px; font-family:微软雅黑;}
"""
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())
