/*
File: organizer.rs

A simple file organizer utility in Rust.
Features:
- Scans a user-specified directory.
- Classifies files into Image, Audio, Video, and Office document types by extension.
- Moves files into type-specific subdirectories (supports cross-filesystem move).
- After moving, optionally scans for duplicates (by SHA-256 hash) of images, audio, video, and office files.
- Displays duplicate sets and can optionally delete all duplicate files except one in each group.
- Outputs errors to stderr if encountered (file access, I/O etc).
3rd party dependencies: walkdir, sha2, console
Author: wangyifan
Date: 2026
*/

use std::fs::{self, File};
use std::io::{self, Write, Read, BufReader};
use std::path::{Path, PathBuf};
use walkdir::WalkDir;
use console::Style;
use std::collections::HashMap;
use sha2::{Sha256, Digest};

// Supported file extensions for each category
const IMAGE_EXTENSIONS: &[&str] = &["jpg", "jpeg", "png", "bmp", "gif", "webp", "tiff"];
const AUDIO_EXTENSIONS: &[&str] = &["mp3", "wav", "aac", "flac", "ogg", "m4a", "wma"];
const VIDEO_EXTENSIONS: &[&str] = &["mp4", "avi", "wmv", "mov", "flv", "mkv", "webm"];
const OFFICE_EXTENSIONS: &[&str] = &["doc", "docx", "xls", "xlsx", "ppt", "pptx", "pdf", "csv", "txt"];

// Enum for file type categories
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
enum FileType {
    Image,
    Audio,
    Video,
    Office,
}

// Detect the file type based on its extension
fn detect_file_type(file_name: &str) -> Option<FileType> {
    let extension = Path::new(file_name)
        .extension().and_then(|s| s.to_str()).unwrap_or("").to_ascii_lowercase();
    if IMAGE_EXTENSIONS.contains(&extension.as_str()) {
        Some(FileType::Image)
    } else if AUDIO_EXTENSIONS.contains(&extension.as_str()) {
        Some(FileType::Audio)
    } else if VIDEO_EXTENSIONS.contains(&extension.as_str()) {
        Some(FileType::Video)
    } else if OFFICE_EXTENSIONS.contains(&extension.as_str()) {
        Some(FileType::Office)
    } else {
        None
    }
}

// Scans a directory and returns statistics and full file paths grouped by type
fn scan_and_classify_files(root: &Path) -> (HashMap<FileType, usize>, HashMap<FileType, Vec<PathBuf>>) {
    let mut stats = HashMap::from([
        (FileType::Image, 0),
        (FileType::Audio, 0),
        (FileType::Video, 0),
        (FileType::Office, 0),
    ]);
    let mut files: HashMap<FileType, Vec<PathBuf>> = HashMap::new();

    for entry in WalkDir::new(root).into_iter().filter_map(|e| e.ok()) {
        if !entry.file_type().is_file() {
            continue;
        }
        let file_name = entry.file_name().to_string_lossy();
        if let Some(file_type) = detect_file_type(&file_name) {
            stats.entry(file_type.clone()).and_modify(|e| *e += 1);
            files.entry(file_type).or_insert(Vec::new()).push(entry.path().to_path_buf());
        }
    }
    (stats, files)
}

// Print how many files were found in each category
fn print_file_stats(stats: &HashMap<FileType, usize>) {
    let heading = Style::new().blue().bold();
    println!("{}", heading.apply_to("\nFile category statistics:"));
    println!("Images : {}", stats.get(&FileType::Image).unwrap_or(&0));
    println!("Audio  : {}", stats.get(&FileType::Audio).unwrap_or(&0));
    println!("Video  : {}", stats.get(&FileType::Video).unwrap_or(&0));
    println!("Office : {}", stats.get(&FileType::Office).unwrap_or(&0));
}

// Returns a file name (with numeric suffix if needed) that does not exist in dest_folder
fn get_non_duplicate_name(dest_folder: &Path, file_name: &str) -> PathBuf {
    let stem = Path::new(file_name).file_stem().unwrap_or_default().to_os_string();
    let ext = Path::new(file_name).extension().and_then(|s| s.to_str()).unwrap_or("");
    let mut counter = 1;
    let mut candidate = dest_folder.join(file_name);
    while candidate.exists() {
        let mut new_stem = stem.clone();
        new_stem.push(format!("_{}", counter));
        let mut new_name = new_stem.into_string().unwrap();
        if !ext.is_empty() {
            new_name.push('.');
            new_name.push_str(ext);
        }
        candidate = dest_folder.join(&new_name);
        counter += 1;
    }
    candidate
}

// Move a file. If rename fails due to cross-device, fall back to copy and delete
fn move_file_support_cross_partition(src: &Path, dst: &Path) -> io::Result<()> {
    match fs::rename(src, dst) {
        Ok(_) => Ok(()),
        Err(e) => {
            #[allow(deprecated)]
            if e.kind() == io::ErrorKind::CrossDeviceLink {
                fs::copy(src, dst)?;
                fs::remove_file(src)?;
                Ok(())
            } else {
                Err(e)
            }
        }
    }
}

// Move all files for each type into its dedicated subdirectory under root_dir
fn move_files(file_map: &HashMap<FileType, Vec<PathBuf>>, root_dir: &Path) {
    // Mapping of file type to folder names
    let folder_map = [
        (FileType::Image, "image"),
        (FileType::Audio, "audio"),
        (FileType::Video, "video"),
        (FileType::Office, "office"),
    ];
    for (file_type, folder_name) in folder_map.iter() {
        let dest_folder = root_dir.join(folder_name);
        // Create subdirectory if missing
        if !dest_folder.exists() {
            if let Err(e) = fs::create_dir_all(&dest_folder) {
                eprintln!("Failed to create folder {}: {}", dest_folder.display(), e);
                continue;
            }
        }
        if let Some(paths) = file_map.get(file_type) {
            for file_path in paths {
                let file_name = file_path.file_name().unwrap().to_str().unwrap();
                let target_path = get_non_duplicate_name(&dest_folder, file_name);
                if file_path != &target_path {
                    if let Err(e) = move_file_support_cross_partition(file_path, &target_path) {
                        eprintln!("Failed to move {}: {}", file_path.display(), e);
                    }
                }
            }
        }
    }
}

// Compute SHA-256 hash of the file content. Returns lowercase hex string.
fn calc_sha256(path: &Path) -> io::Result<String> {
    let file = File::open(path)?;
    let mut reader = BufReader::new(file);
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 8192];
    loop {
        let len = reader.read(&mut buffer)?;
        if len == 0 { break; }
        hasher.update(&buffer[..len]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

// Given file paths, group files with same contents (hash) as duplicates
fn find_duplicates(paths: &[PathBuf]) -> HashMap<String, Vec<PathBuf>> {
    let mut hash_map: HashMap<String, Vec<PathBuf>> = HashMap::new();
    for path in paths {
        match calc_sha256(path) {
            Ok(hash) => {
                hash_map.entry(hash).or_insert_with(Vec::new).push(path.clone());
            }
            Err(e) => {
                eprintln!("Failed to hash {}: {}", path.display(), e);
            }
        }
    }
    // Retain only those hashes with more than 1 file (i.e., actual duplicates)
    hash_map.into_iter().filter(|(_, files)| files.len() > 1).collect()
}

// Print duplicate file info and return all except the first of each duplicate group for deletion
fn show_and_list_duplicates(duplicates: &HashMap<String, Vec<PathBuf>>, category: &str) -> Vec<PathBuf> {
    if duplicates.is_empty() {
        println!("No duplicate {} files found.", category);
        return Vec::new();
    }

    println!("{}", Style::new().red().bold().apply_to(format!("\nDuplicate {} files found:", category)));
    let mut total = 0usize;
    let mut files_to_delete = Vec::new();
    for (hash, files) in duplicates {
        println!("  Hash: {} ({} files)", &hash, files.len());
        // Retain only the first file
        let mut iter = files.iter();
        if let Some(first) = iter.next() {
            println!("   Keep: {}", first.display());
            for dup in iter {
                println!("   DELETE: {}", dup.display());
                files_to_delete.push(dup.clone());
                total += 1;
            }
        }
    }
    println!("Total duplicate {} files to delete: {}", category, total);
    files_to_delete
}

// Delete files in filesystem, print status
fn delete_files(paths: &[PathBuf]) {
    for path in paths {
        match fs::remove_file(path) {
            Ok(()) => println!("Deleted {}", path.display()),
            Err(e) => eprintln!("Failed to delete {}: {}", path.display(), e),
        }
    }
}

// Main process flow: classify, move, deduplicate, and (optionally) delete duplicates
fn main() {
    // Read user input for directory path
    print!("Please input the directory to organize: ");
    io::stdout().flush().unwrap();

    let mut input_path = String::new();
    io::stdin().read_line(&mut input_path).expect("Failed to read line");
    let input_path = input_path.trim();
    let root = Path::new(input_path);

    if !root.is_dir() {
        eprintln!("Invalid directory.");
        return;
    }

    // Scan and classify files, report statistics
    let (stats, file_map) = scan_and_classify_files(root);
    print_file_stats(&stats);

    // Prompt if files should be moved
    print!("\nMove files to corresponding folders? (y/n): ");
    io::stdout().flush().unwrap();
    let mut answer = String::new();
    io::stdin().read_line(&mut answer).expect("Failed to read line");
    if answer.trim().to_lowercase() != "y" {
        println!("Operation cancelled.");
        return;
    }

    move_files(&file_map, root);
    println!("File organization completed!");

    // Prompt if duplicate search and removal is desired
    print!("\nCheck and remove duplicate files? (y/n): ");
    io::stdout().flush().unwrap();
    let mut answer2 = String::new();
    io::stdin().read_line(&mut answer2).expect("Failed to read line");
    if answer2.trim().to_lowercase() != "y" {
        println!("Duplicate removal skipped.");
        return;
    }

    // For every file category, collect the files under its folder and compute duplicates
    let type_folder_map = [
        (FileType::Image, "image", "Image"),
        (FileType::Audio, "audio", "Audio"),
        (FileType::Video, "video", "Video"),
        (FileType::Office, "office", "Office"),
    ];

    let mut all_files_to_delete = Vec::new();
    for (file_type, folder_name, display_name) in &type_folder_map {
        let folder = root.join(folder_name);
        if !folder.is_dir() {
            continue;
        }
        // Recursively gather all files in category folder
        let files: Vec<_> = WalkDir::new(&folder)
            .min_depth(1)
            .into_iter()
            .filter_map(|e| e.ok())
            .filter(|e| e.file_type().is_file())
            .map(|e| e.into_path())
            .collect();

        // Compute duplicates by content
        let duplicates = find_duplicates(&files);
        // List and collect files to delete
        let files_to_delete = show_and_list_duplicates(&duplicates, display_name);
        all_files_to_delete.extend(files_to_delete);
    }

    if all_files_to_delete.is_empty() {
        println!("\nNo duplicate files detected!");
    } else {
        // Confirm deletion with user
        print!("\nDo you want to delete all duplicate files listed above? (y/n): ");
        io::stdout().flush().unwrap();
        let mut answer3 = String::new();
        io::stdin().read_line(&mut answer3).expect("Failed to read line");
        if answer3.trim().to_lowercase() == "y" {
            delete_files(&all_files_to_delete);
            println!("Duplicate files deleted!");
        } else {
            println!("Deletion cancelled. No files were removed.");
        }
    }
}
