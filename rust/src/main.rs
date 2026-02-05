
use std::fs;
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use walkdir::WalkDir;
use console::Style;
use std::collections::HashMap;

// 文件类型分类，支持的扩展名
const IMAGE_EXTENSIONS: &[&str] = &["jpg", "jpeg", "png", "bmp", "gif", "webp", "tiff"];
const AUDIO_EXTENSIONS: &[&str] = &["mp3", "wav", "aac", "flac", "ogg", "m4a", "wma"];
const VIDEO_EXTENSIONS: &[&str] = &["mp4", "avi", "wmv", "mov", "flv", "mkv", "webm"];
const OFFICE_EXTENSIONS: &[&str] = &["doc", "docx", "xls", "xlsx", "ppt", "pptx", "pdf", "csv", "txt"];

// 枚举要整理的文件类型
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
enum FileType {
    Image, Audio, Video, Office
}

// 判断文件类型
fn get_file_type(filename: &str) -> Option<FileType> {
    let ext = Path::new(filename)
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if IMAGE_EXTENSIONS.contains(&ext.as_str()) {
        Some(FileType::Image)
    } else if AUDIO_EXTENSIONS.contains(&ext.as_str()) {
        Some(FileType::Audio)
    } else if VIDEO_EXTENSIONS.contains(&ext.as_str()) {
        Some(FileType::Video)
    } else if OFFICE_EXTENSIONS.contains(&ext.as_str()) {
        Some(FileType::Office)
    } else {
        None
    }
}

// 扫描文件目录，统计每种文件类型的数量，收集要整理的文件路径
fn scan_and_classify(root: &Path) -> (HashMap<FileType, usize>, HashMap<FileType, Vec<PathBuf>>) {
    let mut stats = HashMap::from([
        (FileType::Image, 0),
        (FileType::Audio, 0),
        (FileType::Video, 0),
        (FileType::Office, 0),
    ]);
    let mut files: HashMap<FileType, Vec<PathBuf>> = HashMap::new();

    // 遍历所有子目录和文件
    for entry in WalkDir::new(root).into_iter().filter_map(|e| e.ok()) {
        if !entry.file_type().is_file() {
            continue;
        }
        let filename = entry.file_name().to_string_lossy();
        if let Some(ftype) = get_file_type(&filename) {
            stats.entry(ftype.clone()).and_modify(|e| *e += 1);
            files.entry(ftype).or_insert(Vec::new()).push(entry.path().to_path_buf());
        }
    }
    (stats, files)
}

// 打印统计结果
fn print_stats(stats: &HashMap<FileType, usize>) {
    let heading = Style::new().blue().bold();
    println!("{}", heading.apply_to("\nFile category statistics:"));
    println!("Images : {}", stats.get(&FileType::Image).unwrap_or(&0));
    println!("Audio  : {}", stats.get(&FileType::Audio).unwrap_or(&0));
    println!("Video  : {}", stats.get(&FileType::Video).unwrap_or(&0));
    println!("Office : {}", stats.get(&FileType::Office).unwrap_or(&0));
}

// 文件重名时自动加后缀
fn get_non_duplicate_name(dest_folder: &Path, filename: &str) -> PathBuf {
    let base = Path::new(filename).file_stem().unwrap_or_default().to_os_string();
    let ext = Path::new(filename).extension().and_then(|s| s.to_str()).unwrap_or("");
    let mut counter = 1;
    let mut candidate = dest_folder.join(filename);
    while candidate.exists() {
        let mut new_name = base.clone();
        new_name.push(format!("_{}", counter));
        let mut final_name = new_name.into_string().unwrap();
        if !ext.is_empty() {
            final_name.push('.');
            final_name.push_str(ext);
        }
        candidate = dest_folder.join(&final_name);
        counter += 1;
    }
    candidate
}

// 移动文件到对应文件夹
fn move_files(file_map: HashMap<FileType, Vec<PathBuf>>, root_dir: &Path) {
    // 四种类型及对应文件夹名
    let folder_map = [
        (FileType::Image, "image"),
        (FileType::Audio, "audio"),
        (FileType::Video, "video"),
        (FileType::Office, "office"),
    ];
    for (ftype, folder_name) in folder_map {
        let dest_folder = root_dir.join(folder_name);
        // 文件夹不存在则新建
        if !dest_folder.exists() {
            if let Err(e) = fs::create_dir_all(&dest_folder) {
                eprintln!("Failed to create folder {}: {}", dest_folder.display(), e);
                continue;
            }
        }
        // 遍历对应类型的文件进行移动并重命名
        for file_path in file_map.get(&ftype).unwrap_or(&Vec::new()) {
            let file_name = file_path.file_name().unwrap().to_str().unwrap();
            let target_path = get_non_duplicate_name(&dest_folder, file_name);
            if file_path != &target_path {
                if let Err(e) = fs::rename(&file_path, &target_path) {
                    eprintln!("Failed to move {}: {}", file_path.display(), e);
                }
            }
        }
    }
}

fn main() {
    // 获取用户输入的目录路径
    print!("Please input the directory to organize: ");
    io::stdout().flush().unwrap();

    let mut input_path = String::new();
    io::stdin().read_line(&mut input_path).expect("Failed to read line");
    let input_path = input_path.trim();
    let root = Path::new(input_path);

    // 校验目录
    if !root.is_dir() {
        eprintln!("Invalid directory.");
        return;
    }

    // 统计文件信息并展示
    let (stats, file_map) = scan_and_classify(root);
    print_stats(&stats);

    // 询问是否执行整理
    print!("\nMove files to corresponding folders? (y/n): ");
    io::stdout().flush().unwrap();
    let mut answer = String::new();
    io::stdin().read_line(&mut answer).expect("Failed to read line");
    if answer.trim().to_lowercase() == "y" {
        move_files(file_map, root);
        println!("File organization completed!");
    } else {
        println!("Operation cancelled.");
    }
}
