//! 文件整理程序
//!
//! 这个程序递归扫描一个或多个指定的源目录及其所有子目录，识别不同类型的文件（音频、视频、图片、Office 文档、压缩包），并根据用户选择将这些文件移动或复制到指定的目标主目录下对应的分类子目录。
//!
//! 核心逻辑如下：
//! 1. 交互式让用户选择操作类型（移动或复制文件）。  
//! 2. 交互式让用户从预定义的目录列表中多选一个或多个源目录。  
//! 3. 交互式让用户选择一个目标主目录，这将作为所有分类子目录的根。  
//! 4. 确认是否在目标目录不存在时创建它。  
//! 5. 定义 5 类文件扩展名集合：音频、视频、图片、Office 文档、压缩包。  
//! 6. 对每个选中的源目录调用递归函数处理所有子目录和文件。  
//!    - 递归遍历时，如果遇到目录则继续递归。  
//!    - 如果遇到文件，根据扩展名判断分类。  
//!    - 为每个文件构建分类目标路径，并在目标分类目录不存在时创建它。  
//!    - 为避免覆盖同名文件，先检查目标路径是否存在，若存在则生成唯一新的文件名（追加 `_数字` 后缀）。  
//!    - 最后根据用户选择执行移动或复制操作。  
//! 7. 处理完成后输出提示信息。  
//!
//! 分类策略：  
//! - 音频文件：.mp3 .wav .flac .aac .ogg  
//! - 视频文件：.mp4 .avi .mov .mkv .flv  
//! - 图片文件：.jpg .jpeg .png .gif .bmp .tiff  
//! - Office 文档：.doc .docx .xls .xlsx .ppt .pptx .pdf .txt  
//! - 压缩包文件：.zip .rar .7z .tar .gz .bz2  
//!
//! 这个程序可跨平台运行，在 Linux 和 Windows 上都能正确处理路径和文件操作，不依赖平台特定 API。
//!
//! 使用这个程序前请确保你的环境已安装 Rust 以及 dialoguer 库，并在终端中运行程序，通过交互式界面选择目录和操作类型。

use std::collections::HashSet;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use dialoguer::{Confirm, Select};

fn main() -> io::Result<()> {
    // 让用户选择操作类型：移动 或 复制。
    let operation = Select::new()
        .with_prompt("请选择要执行的操作：")
        .items(&["移动文件", "复制文件"])
        .default(0)
        .interact()?;

    // 让用户从预定义的列表中多选源目录。
    let source_dirs = Select::new()
        .with_prompt("选择源目录（可用空格键多选，回车确认）")
        .items(&["./input", "./downloads", "./documents", "./music", "./videos"])
        .multi_select()
        .interact()?;

    // 让用户选择分类文件的主目标目录。
    let destination_dir = Select::new()
        .with_prompt("选择目标主目录")
        .items(&["./audios", "./videos", "./images", "./office", "./archives"])
        .default(0)
        .interact()?;

    // 根据选择的索引映射到实际路径。
    let destination_base = match destination_dir {
        0 => "./audios",
        1 => "./videos",
        2 => "./images",
        3 => "./office",
        4 => "./archives",
        _ => "./audios",
    };

    // 询问是否在目标不存在时创建该目录。
    let create_dirs = Confirm::new()
        .with_prompt("是否创建目标目录（如果不存在）？")
        .default(true)
        .interact()?;

    if create_dirs {
        // 创建主目标目录（含父目录）。
        fs::create_dir_all(destination_base)?;
        println!("目标主目录已创建或已存在。");
    }

    // 定义每类文件对应的扩展名集合。
    let audio_exts: HashSet<&str> =
        vec![".mp3", ".wav", ".flac", ".aac", ".ogg"].into_iter().collect();
    let video_exts: HashSet<&str> =
        vec![".mp4", ".avi", ".mov", ".mkv", ".flv"].into_iter().collect();
    let image_exts: HashSet<&str> =
        vec![".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"]
            .into_iter()
            .collect();
    let office_exts: HashSet<&str> =
        vec![".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf", ".txt"]
            .into_iter()
            .collect();
    let archive_exts: HashSet<&str> =
        vec![".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"]
            .into_iter()
            .collect();

    // 依次处理用户选中的每个源目录。
    for source_index in source_dirs {
        let source_path = Path::new(match source_index {
            0 => "./input",
            1 => "./downloads",
            2 => "./documents",
            3 => "./music",
            4 => "./videos",
            _ => continue,
        });

        process_dir_recursive(
            source_path,
            destination_base,
            operation,
            &audio_exts,
            &video_exts,
            &image_exts,
            &office_exts,
            &archive_exts,
        )?;
    }

    println!("文件整理完成。");
    Ok(())
}

/// 递归遍历给定目录及其子目录，对符合分类规则的文件进行移动/复制。
///
/// `dir`: 当前要扫描的目录路径。  
/// `destination_base`: 所有分类子目录的根目标路径。  
/// `operation`: 0 表示移动，1 表示复制。  
/// 其余参数是各类支持的扩展名集合。
fn process_dir_recursive(
    dir: &Path,
    destination_base: &str,
    operation: usize,
    audio_exts: &HashSet<&str>,
    video_exts: &HashSet<&str>,
    image_exts: &HashSet<&str>,
    office_exts: &HashSet<&str>,
    archive_exts: &HashSet<&str>,
) -> io::Result<()> {
    // 若不是目录，直接结束。
    if !dir.is_dir() {
        return Ok(());
    }

    // 遍历目录项。
    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let path = entry.path();

        if path.is_dir() {
            // 如果是子目录则递归进入。
            process_dir_recursive(
                &path,
                destination_base,
                operation,
                audio_exts,
                video_exts,
                image_exts,
                office_exts,
                archive_exts,
            )?;
        } else if path.is_file() {
            // 若是文件，则检查扩展名。
            if let Some(ext_os) = path.extension() {
                let ext = format!(".{}", ext_os.to_string_lossy().to_lowercase());

                // 依据扩展名确定分类子目录。
                let category_subdir = if audio_exts.contains(ext.as_str()) {
                    "audios"
                } else if video_exts.contains(ext.as_str()) {
                    "videos"
                } else if image_exts.contains(ext.as_str()) {
                    "images"
                } else if office_exts.contains(ext.as_str()) {
                    "office"
                } else if archive_exts.contains(ext.as_str()) {
                    "archives"
                } else {
                    // 不属于任何分类则跳过。
                    continue;
                };

                // 构建该文件的最终目标目录。
                let final_dest_dir = Path::new(destination_base).join(category_subdir);

                // 如果目标分类目录不存在，则创建它。
                if !final_dest_dir.exists() {
                    fs::create_dir_all(&final_dest_dir)?;
                }

                // 使用原文件名构建目标路径，并确保唯一性。
                let dest_path = final_dest_dir.join(entry.file_name());
                let unique_dest = get_unique_filename(&dest_path);

                // 根据用户选择执行移动或复制。
                if operation == 0 {
                    println!("移动文件：{:?} -> {:?}", path, unique_dest);
                    fs::rename(&path, &unique_dest)?;
                } else {
                    println!("复制文件：{:?} -> {:?}", path, unique_dest);
                    fs::copy(&path, &unique_dest)?;
                }
            }
        }
    }
    Ok(())
}

/// 对于可能存在同名文件的目标路径，通过追加 `_数字` 保证唯一性。
///
/// 返回一个在文件系统上尚不存在的路径。
fn get_unique_filename(path: &Path) -> PathBuf {
    // 克隆一份初始路径。
    let mut unique_path = path.to_path_buf();
    let mut count = 1;

    // 如果已经存在，则循环增加后缀直到唯一。
    while unique_path.exists() {
        let stem = unique_path.file_stem().unwrap().to_os_string();
        let ext = unique_path.extension().map(|e| e.to_os_string());

        let mut new_name = stem.clone();
        new_name.push(format!("_{}", count));

        // 附加扩展名（如果有的话）。
        if let Some(ext_val) = ext {
            new_name.push(".");
            new_name.push(ext_val);
        }

        unique_path.set_file_name(new_name);
        count += 1;
    }

    unique_path
}
