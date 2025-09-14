#!/usr/bin/env python3
"""
file_organizer_gui.py

A multithreaded Tkinter GUI application to organize files from a source directory
into categorized folders in a destination directory.

- UI, labels, prompts and comments are in English.
- Worker runs in a background thread to prevent GUI blocking.
- Communication from worker to GUI uses a thread-safe queue; GUI updates occur only on the main thread.
- A stop request mechanism is provided and the worker periodically checks the stop event to exit early.
- All functions are fully implemented and documented.
"""

import os
import shutil
import hashlib
from datetime import datetime
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import queue
import time
# -------------------------
# File categorization & helper functions
# -------------------------
def categorize_file_by_extension(filepath):
    """
    Return a category name (string) for a given file path based on its extension.
    Unknown extensions return 'other'.

    Args:
        filepath (str): Full path or filename.

    Returns:
        str: One of the category names: images, documents, videos, audio, apps, archives, other.
    """
    extension = os.path.splitext(filepath)[1].lower()
    categories_map = {
        "images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"],
        "documents": [".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx", ".ppt", ".pptx", ".odt"],
        "videos": [".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv"],
        "audio": [".mp3", ".wav", ".flac", ".aac", ".ogg"],
        "apps": [".exe", ".msi", ".deb", ".apk"],
        "archives": [".zip", ".rar", ".7z", ".tar", ".gz"]
    }
    for category, exts in categories_map.items():
        if extension in exts:
            return category
    return "other"
def create_category_directories(dst_base):
    """
    Create category directories inside dst_base. This function is idempotent.
    Args:
        dst_base (str): Destination base directory where category folders will be created.
    """
    categories = ["images", "documents", "videos", "audio", "apps", "archives", "other"]
    for cat in categories:
        os.makedirs(os.path.join(dst_base, cat), exist_ok=True)

def compute_md5(filepath, chunk_size=8192):
    """
    Compute MD5 hash for a file. Useful for duplicate detection.

    Args:
        filepath (str): Path to file to hash.
        chunk_size (int): Bytes to read per loop.
    Returns:
        str: Hex digest of sha256
    """
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
def safe_filename_with_timestamp(src_path):
    """
    Build a safer filename by prefixing the file's modification timestamp (ISO-like, ':' replaced).
    Ensures the timestamp is filesystem-friendly.
    Args:
        src_path (str): Source file path.
    Returns:
        str: Filename string like '2025-09-14T12-34-56.123456-originalname.ext'
    """
    mod_time = datetime.fromtimestamp(os.path.getmtime(src_path))
    timestamp = mod_time.isoformat().replace(":", "-")
    original_name = os.path.basename(src_path)
    return f"{timestamp}-{original_name}"
# -------------------------
# Worker that runs in the background thread
# -------------------------
def organize_files_worker(src_dir, dst_dir, remove_duplicates, stop_event, message_queue):
    """
    Background worker that copies files from src_dir to categorized folders in dst_dir.
    It periodically checks stop_event to exit early if requested.
    Communication to GUI is done via message_queue as tuples: (type, text)
      - type 'log': informational text for the log window
      - type 'progress': progress numeric or textual updates (currently used as textual)
      - type 'error': error message that should be shown to the user
      - type 'done': indicates worker finished normally
      - type 'stopped': indicates worker stopped due to stop_event
    Args:
        src_dir (str): Source directory path.
        dst_dir (str): Destination directory path.
        remove_duplicates (bool): Whether to delete duplicate files in dst_dir after copying.
        stop_event (threading.Event): Event set by GUI to request a stop.
        message_queue (queue.Queue): Thread-safe queue to send messages to GUI.
    """
    try:
        message_queue.put(("log", f"Starting organization: {src_dir} -> {dst_dir}"))
        create_category_directories(dst_dir)
        files_processed = 0
        start_time = time.time()

        # Walk the source directory
        for root, _, files in os.walk(src_dir):
            for filename in files:
                # Check stop request periodically to allow responsive stopping
                if stop_event.is_set():
                    message_queue.put(("log", "Stop requested — worker will exit after current file."))
                    message_queue.put(("stopped", "Stopped by user request."))
                    return

                src_path = os.path.join(root, filename)
                try:
                    category = categorize_file_by_extension(src_path)
                    # Create the initial destination path (original name), then rename with timestamp to avoid collisions
                    dst_category_dir = os.path.join(dst_dir, category)
                    os.makedirs(dst_category_dir, exist_ok=True)
                    temp_dst_path = os.path.join(dst_category_dir, filename)

                    # Copy file preserving metadata
                    shutil.copy2(src_path, temp_dst_path)

                    # Build timestamped filename and guarantee uniqueness
                    timestamped_name = safe_filename_with_timestamp(src_path)
                    final_dst_path = os.path.join(dst_category_dir, timestamped_name)

                    counter = 1
                    while os.path.exists(final_dst_path):
                        final_dst_path = os.path.join(dst_category_dir, f"{timestamped_name}-{counter}-{filename}")
                        counter += 1

                    os.rename(temp_dst_path, final_dst_path)

                    files_processed += 1
                    message_queue.put(("log", f"Copied: {src_path} -> {final_dst_path}"))
                except Exception as ex:
                    # Catch per-file exceptions but continue processing other files
                    message_queue.put(("log", f"Error processing '{src_path}': {ex}"))

            # After completing each directory level, check stop_event again
            if stop_event.is_set():
                message_queue.put(("log", "Stop requested — worker will exit after finishing current directory."))
                message_queue.put(("stopped", "Stopped by user request."))
                return

        elapsed = time.time() - start_time
        message_queue.put(("log", f"File copy phase complete. Files copied: {files_processed}. Time elapsed: {elapsed:.1f}s"))

        # Optional duplicate removal phase (keeps the first encountered file for each hash)
        if remove_duplicates:
            message_queue.put(("log", "Starting duplicate removal..."))
            seen_hashes = {}
            removed_count = 0
            # Walk destination directory
            for root, _, files in os.walk(dst_dir):
                for filename in files:
                    if stop_event.is_set():
                        message_queue.put(("log", "Stop requested — stopping duplicate removal."))
                        message_queue.put(("stopped", "Stopped by user request."))
                        return
                    path = os.path.join(root, filename)
                    try:
                        file_hash = compute_md5(path)
                    except Exception as e:
                        message_queue.put(("log", f"Failed to hash '{path}': {e}"))
                        continue
                    if file_hash in seen_hashes:
                        try:
                            os.remove(path)
                            removed_count += 1
                            message_queue.put(("log", f"Removed duplicate: {path}"))
                        except Exception as e:
                            message_queue.put(("log", f"Failed to remove duplicate '{path}': {e}"))
                    else:
                        seen_hashes[file_hash] = path

            message_queue.put(("log", f"Duplicate removal complete. Files removed: {removed_count}"))

        message_queue.put(("done", "Organization task completed successfully."))
    except Exception as fatal:
        # Any unexpected fatal error
        message_queue.put(("error", f"Worker encountered a fatal error: {fatal}"))

# -------------------------
# GUI class (main thread only updates GUI)
# -------------------------

class FileOrganizerApp:
    """
    Tkinter application that provides:
      - Source and destination directory pickers
      - A checkbox to enable duplicate removal
      - Start and Stop controls
      - A scrollable log area that displays worker messages
    """

    def __init__(self, root):
        self.root = root
        root.title("File Organizer (multithreaded)")
        root.geometry("800x540")

        # Queue for worker -> GUI messages
        self._msg_queue = queue.Queue()

        # Stop event to request worker termination
        self._stop_event = threading.Event()

        # Worker thread reference
        self._worker_thread = None

        # UI elements
        self._build_ui()

        # Periodically process messages from the queue
        self.root.after(150, self._process_worker_messages)

    def _build_ui(self):
        """Construct UI widgets and layout."""
        # Source directory label, entry, and browse button
        tk.Label(self.root, text="Source Directory:").place(x=10, y=10)
        self.src_var = tk.StringVar()
        tk.Entry(self.root, textvariable=self.src_var, width=86).place(x=130, y=10)
        tk.Button(self.root, text="Browse...", command=self._browse_source).place(x=720, y=6)

        # Destination directory
        tk.Label(self.root, text="Destination Directory:").place(x=10, y=40)
        self.dst_var = tk.StringVar()
        tk.Entry(self.root, textvariable=self.dst_var, width=86).place(x=130, y=40)
        tk.Button(self.root, text="Browse...", command=self._browse_destination).place(x=720, y=36)

        # Option to remove duplicates after copying
        self.remove_duplicates_var = tk.BooleanVar(value=True)
        tk.Checkbutton(self.root, text="Remove duplicates after organizing", variable=self.remove_duplicates_var).place(x=130, y=72)
        # Start and Stop buttons
        self.start_button = tk.Button(self.root, text="Start Organizing", width=18, command=self._confirm_and_start)
        self.start_button.place(x=130, y=100)
        self.stop_button = tk.Button(self.root, text="Request Stop", width=18, state="disabled", command=self._request_stop)
        self.stop_button.place(x=300, y=100)
        # Log area (readonly scrolled text)
        self.log_widget = scrolledtext.ScrolledText(self.root, state="disabled", wrap="word")
        self.log_widget.place(x=10, y=140, width=780, height=380)
    # UI helper methods
    def _browse_source(self):
        """Open directory chooser for source and set src_var."""
        path = filedialog.askdirectory()
        if path:
            self.src_var.set(path)

    def _browse_destination(self):
        """Open directory chooser for destination and set dst_var."""
        path = filedialog.askdirectory()
        if path:
            self.dst_var.set(path)
    def _append_log(self, text):
        """
        Append text to log widget from the main thread only.
        The log widget is read-only to the user.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", f"[{timestamp}] {text}\n")
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")
    def _confirm_and_start(self):
        """
        Confirm with the user before starting, then start the worker thread.
        The confirmation explains that the destination will be written to.
        """
        src = self.src_var.get().strip()
        dst = self.dst_var.get().strip()
        if not src or not os.path.isdir(src):
            messagebox.showerror("Invalid Source", "Please select a valid source directory.")
            return
        if not dst:
            messagebox.showerror("Invalid Destination", "Please select or enter a destination directory.")
            return
        confirm_msg = (
            "Files from the source directory will be copied into the destination directory.\n\n"
            f"Source: {src}\nDestination: {dst}\n\n"
            "The destination directory will be created if it does not exist and files will be written there.\n\n"
            "Do you want to continue?"
        )
        if not messagebox.askokcancel("Confirm Start", confirm_msg):
            return
        # Ensure destination exists
        os.makedirs(dst, exist_ok=True)
        # Disable start button and enable stop button
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self._stop_event.clear()
        # Start worker thread (daemon so it won't prevent app from closing)
        self._worker_thread = threading.Thread(
            target=organize_files_worker,
            args=(src, dst, self.remove_duplicates_var.get(), self._stop_event, self._msg_queue),
            daemon=True,
            name="FileOrganizerWorker"
        )
        self._worker_thread.start()
        self._append_log("Background worker started.")
    def _request_stop(self):
        """
        Ask user to confirm stop request. If confirmed, set the stop event.
        The worker checks the stop event and should finish quickly.
        """
        if messagebox.askyesno("Request Stop", "Request to stop the background task? The operation will stop as soon as possible."):
            self._stop_event.set()
            self._append_log("Stop requested by user.")
            # disable stop button to avoid duplicate clicks; worker will send 'stopped' or 'done'
            self.stop_button.config(state="disabled")
    # Periodically process messages from the worker thread
    def _process_worker_messages(self):
        """
        Dequeue all available messages and handle them on the GUI thread.
        Then re-schedule itself with after().
        """
        try:
            while True:
                msg_type, text = self._msg_queue.get_nowait()
                if msg_type == "log":
                    self._append_log(text)
                elif msg_type == "progress":
                    self._append_log(f"[progress] {text}")
                elif msg_type == "error":
                    self._append_log(f"[ERROR] {text}")
                    messagebox.showerror("Background Error", text)
                elif msg_type == "done":
                    self._append_log(text)
                    self.start_button.config(state="normal")
                    self.stop_button.config(state="disabled")
                elif msg_type == "stopped":
                    self._append_log(text)
                    self.start_button.config(state="normal")
                    self.stop_button.config(state="disabled")
                else:
                    self._append_log(f"[unknown message type '{msg_type}'] {text}")
                self._msg_queue.task_done()
        except queue.Empty:
            pass
        # Schedule next check
        self.root.after(150, self._process_worker_messages)
# -------------------------
# Main entry point
# -------------------------
def main():
    root = tk.Tk()
    app = FileOrganizerApp(root)
    root.mainloop()
if __name__ == "__main__":
    main()
