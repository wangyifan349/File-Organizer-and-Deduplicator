#!/usr/bin/env python3
"""
media_collector_tk_improved.py
Tkinter GUI to collect image/video/audio files from multiple source directories
into a single destination. Improved naming, comments, fewer blank lines, and
robust threading to keep the UI responsive.

Run: python media_collector_tk_improved.py
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
import shutil
import csv
import queue

# File type extensions (can extend as needed)
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".flv", ".webm"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}
CATEGORY_EXTS = {"images": IMAGE_EXTS, "videos": VIDEO_EXTS, "audios": AUDIO_EXTS}
def scan_media_files(sources, follow_symlinks=False):
    """
    Generator: yield (source_path: Path, category: str) for each media file found.
    Do not perform I/O or GUI updates here.
    """
    for src in sources:
        base = Path(src)
        if not base.exists():
            continue
        for p in base.rglob("*"):
            try:
                if p.is_file():
                    ext = p.suffix.lower()
                    for category, exts in CATEGORY_EXTS.items():
                        if ext in exts:
                            yield p, category
                            break
            except PermissionError:
                continue
def make_safe_target(dest_root: Path, category: str, src_path: Path, strategy: str):
    """
    Compute a non-conflicting target Path for src_path under dest_root/category.
    strategy: 'number' -> append (1),(2)... ; 'prefix' -> prepend sanitized source path.
    This function does not create files; it only computes the Path.
    """
    dest_dir = dest_root / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    candidate = dest_dir / src_path.name
    if strategy == "prefix":
        sanitized = src_path.as_posix().lstrip("/").replace("/", "__").replace(":", "")
        candidate = dest_dir / f"{sanitized}__{src_path.name}"
        i = 1
        stem = candidate.stem
        suffix = candidate.suffix
        while candidate.exists():
            candidate = dest_dir / f"{stem}({i}){suffix}"
            i += 1
        return candidate
    if strategy == "number":
        if not candidate.exists():
            return candidate
        base = candidate.stem
        suffix = candidate.suffix
        i = 1
        while True:
            candidate = dest_dir / f"{base}({i}){suffix}"
            if not candidate.exists():
                return candidate
            i += 1
    raise ValueError("Unknown strategy")
def worker_collect(sources, dest, strategy, move_files, follow_symlinks,
                   dry_run, log_path, progress_q, stop_event):
    """
    Worker thread function:
    - Scans files
    - For each file, computes safe target and performs copy/move (unless dry_run)
    - Puts progress messages into progress_q (thread-safe)
    - Responds to stop_event to cancel operation
    Message protocol (dict):
      {'type':'count', 'total': int}
      {'type':'item', 'index':i, 'total':n, 'src':str, 'tgt':str, 'action':str}
      {'type':'done', 'processed':int, 'errors':int}
      {'type':'error', 'msg':str}
    """
    try:
        items = list(scan_media_files(sources, follow_symlinks=follow_symlinks))
        total = len(items)
        progress_q.put({"type": "count", "total": total})
        results = []
        errors = []
        for idx, (src_path, category) in enumerate(items, start=1):
            if stop_event.is_set():
                break
            try:
                target = make_safe_target(Path(dest), category, src_path, strategy)
                action = "would_move" if (dry_run and move_files) else ("would_copy" if dry_run else ("moved" if move_files else "copied"))
                if not dry_run:
                    if move_files:
                        shutil.move(str(src_path), str(target))
                    else:
                        shutil.copy2(str(src_path), str(target))
                    action = "moved" if move_files else "copied"
                results.append((str(src_path), str(target), category, action, "ok"))
                progress_q.put({"type": "item", "index": idx, "total": total, "src": str(src_path), "tgt": str(target), "action": action})
            except Exception as e:
                errors.append((str(src_path), category, str(e)))
                results.append((str(src_path), "", category, "error", str(e)))
                progress_q.put({"type": "item", "index": idx, "total": total, "src": str(src_path), "tgt": "", "action": "error", "error": str(e)})
        if log_path:
            try:
                with open(log_path, "w", newline="", encoding="utf-8") as fh:
                    writer = csv.writer(fh)
                    writer.writerow(["source", "target", "category", "action", "status"])
                    writer.writerows(results)
            except Exception as e:
                progress_q.put({"type": "error", "msg": f"Failed to write log: {e}"})
        progress_q.put({"type": "done", "processed": len(results), "errors": len(errors)})
    except Exception as e:
        progress_q.put({"type": "error", "msg": str(e)})
class MediaCollectorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Media Collector")
        self.geometry("820x560")
        self._sources = []
        self._progress_q = queue.Queue()
        self._stop_event = threading.Event()
        self._worker = None
        self._create_widgets()
        self.after(150, self._poll_queue)
    def _create_widgets(self):
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True, padx=8, pady=8)

        sframe = ttk.LabelFrame(frm, text="Source folders")
        sframe.pack(fill="x", pady=6)
        btn_add = ttk.Button(sframe, text="Add folder", command=self._add_source)
        btn_add.grid(row=0, column=0, padx=4, pady=4, sticky="w")
        btn_remove = ttk.Button(sframe, text="Remove selected", command=self._remove_selected)
        btn_remove.grid(row=0, column=1, padx=4, pady=4, sticky="w")
        self._listbox = tk.Listbox(sframe, height=4)
        self._listbox.grid(row=1, column=0, columnspan=4, sticky="we", padx=6, pady=4)
        sframe.columnconfigure(2, weight=1)

        dframe = ttk.Frame(frm)
        dframe.pack(fill="x", pady=6)
        ttk.Label(dframe, text="Destination:").grid(row=0, column=0, sticky="w")
        self._dest_entry = ttk.Entry(dframe)
        self._dest_entry.grid(row=0, column=1, sticky="we", padx=6)
        ttk.Button(dframe, text="Choose", command=self._choose_dest).grid(row=0, column=2)
        dframe.columnconfigure(1, weight=1)
        oframe = ttk.Frame(frm)
        oframe.pack(fill="x", pady=6)
        ttk.Label(oframe, text="Conflict strategy:").grid(row=0, column=0, sticky="w")
        self._strategy = tk.StringVar(value="number")
        ttk.Radiobutton(oframe, text="Append number", variable=self._strategy, value="number").grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(oframe, text="Prefix source path", variable=self._strategy, value="prefix").grid(row=0, column=2, sticky="w")
        self._move_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(oframe, text="Move files (otherwise copy)", variable=self._move_var).grid(row=1, column=0, sticky="w")
        self._follow_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(oframe, text="Follow symlinks", variable=self._follow_var).grid(row=1, column=1, sticky="w")
        self._dry_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(oframe, text="Dry run (no disk writes)", variable=self._dry_var).grid(row=1, column=2, sticky="w")
        lframe = ttk.Frame(frm)
        lframe.pack(fill="x", pady=6)
        ttk.Label(lframe, text="Log CSV:").grid(row=0, column=0, sticky="w")
        self._log_entry = ttk.Entry(lframe)
        self._log_entry.grid(row=0, column=1, sticky="we", padx=6)
        ttk.Button(lframe, text="Choose", command=self._choose_log).grid(row=0, column=2)
        lframe.columnconfigure(1, weight=1)
        cframe = ttk.Frame(frm)
        cframe.pack(fill="x", pady=6)
        ttk.Button(cframe, text="Preview (first 20)", command=self._preview).grid(row=0, column=0, padx=4)
        self._start_btn = ttk.Button(cframe, text="Start", command=self._start)
        self._start_btn.grid(row=0, column=1, padx=4)
        self._stop_btn = ttk.Button(cframe, text="Stop", command=self._stop, state="disabled")
        self._stop_btn.grid(row=0, column=2, padx=4)
        pframe = ttk.LabelFrame(frm, text="Progress / Log")
        pframe.pack(fill="both", expand=True, pady=6)
        self._progress = ttk.Progressbar(pframe, orient="horizontal", mode="determinate")
        self._progress.pack(fill="x", padx=6, pady=6)
        self._log_text = tk.Text(pframe, height=14)
        self._log_text.pack(fill="both", expand=True, padx=6, pady=6)
    def _add_source(self):
        d = filedialog.askdirectory()
        if d:
            self._sources.append(d)
            self._listbox.insert("end", d)
    def _remove_selected(self):
        sel = list(self._listbox.curselection())
        for i in reversed(sel):
            self._listbox.delete(i)
            del self._sources[i]
    def _choose_dest(self):
        d = filedialog.askdirectory()
        if d:
            self._dest_entry.delete(0, "end")
            self._dest_entry.insert(0, d)

    def _choose_log(self):
        f = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if f:
            self._log_entry.delete(0, "end")
            self._log_entry.insert(0, f)
    def _preview(self):
        if not self._sources:
            messagebox.showwarning("Warning", "Add at least one source folder.")
            return
        dest = self._dest_entry.get().strip()
        if not dest:
            messagebox.showwarning("Warning", "Choose a destination folder.")
            return
        items = []
        for p, cat in scan_media_files(self._sources, follow_symlinks=self._follow_var.get()):
            items.append((p, cat))
            if len(items) >= 20:
                break
        self._log_text.delete("1.0", "end")
        self._log_text.insert("end", f"Preview (up to 20): found {len(items)} files\n")
        for i, (p, cat) in enumerate(items, start=1):
            tgt = make_safe_target(Path(dest), cat, p, self._strategy.get())
            self._log_text.insert("end", f"{i}. [{cat}] {p} -> {tgt}\n")
        if not items:
            self._log_text.insert("end", "No media found.\n")
    def _start(self):
        if not self._sources:
            messagebox.showwarning("Warning", "Add at least one source folder.")
            return
        dest = self._dest_entry.get().strip()
        if not dest:
            messagebox.showwarning("Warning", "Choose a destination folder.")
            return
        self._log_text.delete("1.0", "end")
        self._progress["value"] = 0
        self._progress["maximum"] = 1
        self._stop_event.clear()
        self._start_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        args = {
            "sources": list(self._sources),
            "dest": dest,
            "strategy": self._strategy.get(),
            "move_files": self._move_var.get(),
            "follow_symlinks": self._follow_var.get(),
            "dry_run": self._dry_var.get(),
            "log_path": self._log_entry.get().strip() or None,
            "progress_q": self._progress_q,
            "stop_event": self._stop_event,
        }
        self._worker = threading.Thread(target=worker_collect, kwargs=args, daemon=True)
        self._worker.start()
        self._log_text.insert("end", "Task started...\n")
    def _stop(self):
        if messagebox.askyesno("Confirm", "Stop the current task?"):
            self._stop_event.set()
            self._log_text.insert("end", "Stop requested...\n")
            self._stop_btn.config(state="disabled")
    def _poll_queue(self):
        try:
            while True:
                msg = self._progress_q.get_nowait()
                mtype = msg.get("type")
                if mtype == "count":
                    total = msg.get("total", 0)
                    self._progress["maximum"] = max(total, 1)
                    self._log_text.insert("end", f"Total files: {total}\n")
                elif mtype == "item":
                    idx = msg.get("index", 0)
                    total = msg.get("total", 1)
                    action = msg.get("action", "")
                    src = msg.get("src", "")
                    tgt = msg.get("tgt", "")
                    if action == "error":
                        err = msg.get("error", "")
                        self._log_text.insert("end", f"[{idx}/{total}] ERROR: {src} -> {err}\n")
                    else:
                        self._log_text.insert("end", f"[{idx}/{total}] {action}: {src} -> {tgt}\n")
                    self._progress["value"] = idx
                    self._log_text.see("end")
                elif mtype == "done":
                    processed = msg.get("processed", 0)
                    errors = msg.get("errors", 0)
                    self._log_text.insert("end", f"Done: processed={processed}, errors={errors}\n")
                    self._start_btn.config(state="normal")
                    self._stop_btn.config(state="disabled")
                elif mtype == "error":
                    self._log_text.insert("end", f"Error: {msg.get('msg')}\n")
                    self._start_btn.config(state="normal")
                    self._stop_btn.config(state="disabled")
                else:
                    self._log_text.insert("end", f"Message: {msg}\n")
        except queue.Empty:
            pass
        finally:
            self.after(150, self._poll_queue)
if __name__ == "__main__":
    app = MediaCollectorApp()
    app.mainloop()
