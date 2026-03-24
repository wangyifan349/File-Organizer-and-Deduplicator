#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件整理工具说明
本程序用于将多个源目录中的常见资料文件统一整理到一个目标目录中，并按照文件类型自动分类存放。程序会递归扫描用户提供的所有源目录及其子目录，只处理预设支持的文件类型，包括图片、视频、音频、文档和压缩包。整理后的文件会分别进入目标目录下对应的“图片”“视频”“音频”“文档”“压缩包”子目录，便于集中归档、后续查找与管理。
在处理过程中，程序通过计算文件 SHA256 哈希值判断内容是否重复，若目标目录中已存在相同内容的文件，则直接跳过，不重复保存；若仅文件名相同但内容不同，则自动生成不冲突的新文件名，确保不会覆盖已有文件。程序同时支持 copy 与 move 两种模式：copy 模式用于复制文件并保留源文件，适合首次测试或稳妥整理；move 模式用于移动文件到目标目录，适合确认规则无误后的正式归档操作。
"""



"""
免责声明
本程序按当前预设规则对文件进行分类整理，仅依据文件扩展名识别类型，并依据 SHA256 哈希值判断内容重复。程序已尽量采取“跳过重复”“自动重命名”“不覆盖已有文件”等保护措施，但仍不能替代用户对重要数据的自行核对、备份与管理责任。对于因误选目录、误用 move 模式、源文件本身异常、权限问题、路径冲突或其他不可预见情况造成的数据整理结果偏差、文件位置变化或潜在损失，使用者应自行承担风险。
在处理重要资料、工作文件、个人照片、原始工程文件或其他不可替代数据前，建议先使用 copy 模式测试，并提前完成独立备份。使用本程序即视为你已理解其工作方式、适用范围与潜在风险，并愿意自行承担因使用本程序所产生的一切后果。
"""





import hashlib                                                      # 用于计算文件哈希
import shutil                                                       # 用于复制和移动文件
from pathlib import Path                                            # 用于处理路径
HASH_CHUNK_SIZE = 1024 * 1024                                       # 分块读取大小：1MB
IMAGE_SUFFIX_SET = {                                                # 图片类扩展名
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic", ".heif", ".raw",
}
VIDEO_SUFFIX_SET = {                                                # 视频类扩展名
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".m4v", ".ts", ".mpeg", ".mpg", ".webm", ".3gp",
}
AUDIO_SUFFIX_SET = {                                                # 音频类扩展名
    ".mp3", ".wav", ".flac", ".aac", ".m4a", ".ogg", ".wma", ".ape", ".alac", ".aiff", ".opus",
}
DOCUMENT_SUFFIX_SET = {                                             # 文档类扩展名
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pdf", ".wps", ".et", ".dps", ".csv", ".txt",
}
ARCHIVE_SUFFIX_SET = {                                              # 压缩包类扩展名
    ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz", ".tbz2", ".txz", ".iso",
}
CATEGORY_DIRECTORY_NAME_MAP = {                                     # 类型对应的目标子目录名称
    "image": "图片",
    "video": "视频",
    "audio": "音频",
    "document": "文档",
    "archive": "压缩包",
}


def calculate_file_sha256(file_path):
    sha256 = hashlib.sha256()                                       # 创建 SHA256 哈希对象
    with file_path.open("rb") as file_object:                       # 以二进制只读方式打开文件
        while True:
            chunk_bytes = file_object.read(HASH_CHUNK_SIZE)         # 分块读取文件内容
            if not chunk_bytes:
                break                                               # 读取结束
            sha256.update(chunk_bytes)                              # 更新哈希
    return sha256.hexdigest()                                       # 返回十六进制哈希字符串
def build_non_conflicting_path(target_path):
    if not target_path.exists():
        return target_path                                          # 目标不存在，直接可用
    file_stem = target_path.stem                                    # 文件主名
    file_suffix = target_path.suffix                                # 文件扩展名
    parent_directory = target_path.parent                           # 父目录
    duplicate_index = 1                                             # 重名序号起始值
    while True:
        renamed_path = parent_directory / "{0} ({1}){2}".format(
            file_stem,
            duplicate_index,
            file_suffix,
        )                                                           # 生成新名字
        if not renamed_path.exists():
            return renamed_path                                     # 找到一个未占用名称
        duplicate_index += 1                                        # 继续尝试下一个序号
def get_file_category(file_path):
    file_suffix = file_path.suffix.lower()                          # 统一使用小写扩展名

    if file_suffix in IMAGE_SUFFIX_SET:
        return "image"                                              # 图片类
    if file_suffix in VIDEO_SUFFIX_SET:
        return "video"                                              # 视频类
    if file_suffix in AUDIO_SUFFIX_SET:
        return "audio"                                              # 音频类
    if file_suffix in DOCUMENT_SUFFIX_SET:
        return "document"                                           # 文档类
    if file_suffix in ARCHIVE_SUFFIX_SET:
        return "archive"                                            # 压缩包类
    return None                                                     # 不支持的类型
def print_supported_types():
    print("本程序只整理以下类型文件：")                                   # 输出支持的文件类型
    print("图片类   : {0}".format(", ".join(sorted(IMAGE_SUFFIX_SET))))   # 输出图片扩展名
    print("视频类   : {0}".format(", ".join(sorted(VIDEO_SUFFIX_SET))))   # 输出视频扩展名
    print("音频类   : {0}".format(", ".join(sorted(AUDIO_SUFFIX_SET))))   # 输出音频扩展名
    print("文档类   : {0}".format(", ".join(sorted(DOCUMENT_SUFFIX_SET))))  # 输出文档扩展名
    print("压缩类   : {0}".format(", ".join(sorted(ARCHIVE_SUFFIX_SET))))  # 输出压缩扩展名
    print("")                                                        # 空行
def print_program_intro():
    print("=" * 72)                                                 # 分隔线
    print("文件整理工具（安全提示版）")                                 # 标题
    print("=" * 72)                                                 # 分隔线
    print("用途：")                                                  # 用途说明
    print("  将多个源目录中的常见资料文件，整理到一个目标目录。")           # 用途内容
    print("")                                                        # 空行
    print("整理后的目录结构：")                                        # 目录结构说明
    print("  目标目录/图片")                                          # 图片目录
    print("  目标目录/视频")                                          # 视频目录
    print("  目标目录/音频")                                          # 音频目录
    print("  目标目录/文档")                                          # 文档目录
    print("  目标目录/压缩包")                                        # 压缩包目录
    print("")                                                        # 空行
    print("安全说明：")                                               # 安全说明标题
    print("  1. 本程序不会覆盖目标目录中已有文件。")                      # 不覆盖保证
    print("  2. 若目标目录中已存在同名文件，会自动改名保存。")              # 重名处理
    print("  3. 若文件内容相同（按 SHA256 哈希判断），会直接跳过。")        # 重复处理
    print("  4. 只处理图片 / 视频 / 音频 / 文档 / 压缩包。")               # 处理范围
    print("  5. 会递归扫描源目录的所有子目录。")                          # 递归说明
    print("  6. 选择 move 模式时，会从源目录移走文件，请务必先确认。")       # move 风险提示
    print("")                                                        # 空行
    print("使用建议：")                                               # 使用建议标题
    print("  - 第一次建议先使用 copy 模式测试。")                        # 建议先 copy
    print("  - 确认整理结果无误后，再考虑使用 move 模式。")                 # 建议后 move
    print("  - 整理重要数据前，建议你自己先备份。")                        # 备份建议
    print("")                                                        # 空行
    print_supported_types()                                         # 输出支持类型
def ask_yes_no(question_text, default_value):
    if default_value:
        prompt_text = " [Y/n]: "                                    # 默认 yes
    else:
        prompt_text = " [y/N]: "                                    # 默认 no
    user_input = input(question_text + prompt_text).strip().lower() # 读取用户输入
    if not user_input:
        return default_value                                        # 直接回车采用默认值
    return user_input in ("y", "yes")                               # yes 判断
def prompt_source_directories():
    print("请输入源目录，多个目录每行一个，直接回车结束：")                      # 提示输入多个源目录
    source_directory_list = []                                      # 保存有效源目录

    while True:
        user_input = input("源目录: ").strip()                      # 读取用户输入
        if not user_input:
            break                                                   # 空输入表示结束

        source_directory = Path(user_input).expanduser().resolve()  # 展开并规范化路径
        if not source_directory.exists() or not source_directory.is_dir():
            print("  无效目录，已跳过。")                              # 非法目录直接跳过
            continue
        if source_directory in source_directory_list:
            print("  重复目录，已跳过。")                              # 重复目录不重复添加
            continue
        source_directory_list.append(source_directory)              # 加入有效目录列表
        print("  已添加: {0}".format(source_directory))             # 提示已添加目录
    return source_directory_list                                    # 返回源目录列表

def prompt_target_directory():
    user_input = input("目标目录: ").strip()                        # 读取目标目录
    if not user_input:
        return None                                                 # 空输入表示无效
    return Path(user_input).expanduser().resolve()                  # 返回规范化后的目标目录


def prompt_operation_mode():
    print("")                                                        # 空行
    print("请选择运行模式：")                                         # 模式说明
    print("  copy  = 复制文件到目标目录，源文件保留")                    # copy 说明
    print("  move  = 移动文件到目标目录，源文件会被移走")                 # move 说明
    print("  建议第一次先用 copy")                                    # 安全建议
    user_input = input("模式（copy/move，默认 copy）: ").strip().lower()  # 读取操作模式
    if not user_input:
        return "copy"                                               # 默认使用 copy
    if user_input in ("copy", "move"):
        return user_input                                           # 仅接受 copy / move
    return None                                                     # 其他输入视为无效


def print_selected_configuration(source_directory_list, target_directory, operation_mode):
    print("")                                                        # 空行
    print("=" * 72)                                                 # 分隔线
    print("请再次确认本次操作：")                                     # 二次确认标题
    print("=" * 72)                                                 # 分隔线
    print("源目录：")                                                # 输出源目录标题
    for source_directory in source_directory_list:
        print("  - {0}".format(source_directory))                   # 输出每个源目录
    print("目标目录：")                                              # 输出目标目录标题
    print("  {0}".format(target_directory))                         # 输出目标目录
    print("运行模式：")                                              # 输出模式标题
    print("  {0}".format(operation_mode))                           # 输出模式
    print("处理方式：")                                              # 输出处理方式标题
    print("  - 递归扫描所有子目录")                                   # 递归说明
    print("  - 按类型分别放入 图片/视频/音频/文档/压缩包 子目录")         # 分类说明
    print("  - 按哈希跳过重复文件")                                    # 去重说明
    print("  - 绝不覆盖已有文件")                                     # 不覆盖说明
    print("  - 重名文件自动改名")                                     # 重名说明
    print("")                                                        # 空行
    if operation_mode == "move":
        print("警告：你当前选择的是 move 模式。")                       # move 警告
        print("这会把源目录中的文件移动到目标目录。")                     # move 说明
        print("请确认你已经理解该操作。")                              # move 提醒
        print("")                                                    # 空行


def scan_target_hashes(target_directory):
    target_hash_map = {}                                            # 哈希 -> 目标文件路径
    print("\n正在扫描目标目录已有文件...")                              # 提示开始扫描目标目录
    for existing_file_path in target_directory.rglob("*"):          # 递归遍历目标目录
        if not existing_file_path.is_file():
            continue                                                # 只处理文件
        file_category = get_file_category(existing_file_path)       # 判断文件分类
        if file_category is None:
            continue                                                # 只扫描支持的类型
        file_sha256 = calculate_file_sha256(existing_file_path)     # 计算目标文件哈希
        target_hash_map[file_sha256] = existing_file_path           # 记录哈希和路径
    return target_hash_map                                          # 返回目标哈希映射


def collect_source_files(source_directory_list, target_directory):
    collected_file_entry_list = []                                  # 保存 (源文件, 分类)
    skipped_unsupported_count = 0                                   # 不支持类型的跳过计数

    for source_root_directory in source_directory_list:             # 遍历每个源目录
        for source_file_path in source_root_directory.rglob("*"):   # 递归遍历目录内全部内容
            if not source_file_path.is_file():
                continue                                            # 只处理文件
            if target_directory == source_file_path:
                continue                                            # 保护性跳过
            if target_directory in source_file_path.parents:
                continue                                            # 跳过目标目录中的文件，避免重复处理
            file_category = get_file_category(source_file_path)     # 获取文件分类
            if file_category is None:
                skipped_unsupported_count += 1                      # 记录不支持的文件类型
                continue
            collected_file_entry_list.append((source_file_path, file_category))  # 保存文件及分类
    return collected_file_entry_list, skipped_unsupported_count     # 返回待处理文件及不支持计数


def build_destination_path(source_file_path, target_directory, file_category):
    category_directory_name = CATEGORY_DIRECTORY_NAME_MAP[file_category]  # 获取分类目录名
    return target_directory / category_directory_name / source_file_path.name  # 按类型放入子目录


def main():
    print_program_intro()                                           # 打印程序说明和安全提示
    if not ask_yes_no("是否继续？", True):
        print("已取消运行。")                                        # 用户取消
        return
    print("")                                                        # 空行
    source_directory_list = prompt_source_directories()             # 获取源目录列表
    if not source_directory_list:
        print("未提供有效源目录。")                                    # 没有可用源目录
        return
    target_directory = prompt_target_directory()                    # 获取目标目录
    if target_directory is None:
        print("未提供目标目录。")                                      # 没有目标目录
        return
    operation_mode = prompt_operation_mode()                        # 获取操作模式
    if operation_mode is None:
        print("模式只能是 copy 或 move。")                             # 模式非法
        return
    for source_directory in source_directory_list:
        if source_directory == target_directory:
            print("源目录不能与目标目录相同: {0}".format(source_directory))  # 禁止源目标相同
            return
    print_selected_configuration(
        source_directory_list,
        target_directory,
        operation_mode,
    )                                                               # 输出最终配置
    if not ask_yes_no("确认开始执行？", False):
        print("已取消运行。")                                        # 用户取消最终执行
        return
    target_directory.mkdir(parents=True, exist_ok=True)             # 创建目标目录
    existing_target_hash_map = scan_target_hashes(target_directory) # 扫描目标目录现有哈希
    source_file_entry_list, skipped_unsupported_count = collect_source_files(
        source_directory_list,
        target_directory,
    )                                                               # 收集支持类型的源文件
    if not source_file_entry_list:
        print("没有找到可处理文件。")                                  # 没有可处理内容
        print("已跳过不支持的文件数量: {0}".format(skipped_unsupported_count))  # 输出不支持数量
        return
    total_file_count = len(source_file_entry_list)                  # 总文件数
    copied_file_count = 0                                           # 复制计数
    moved_file_count = 0                                            # 移动计数
    skipped_duplicate_count = 0                                     # 跳过重复计数
    renamed_file_count = 0                                          # 改名计数
    print("\n共找到 {0} 个可整理文件，开始处理...\n".format(total_file_count))  # 开始处理提示
    for current_index, (source_file_path, file_category) in enumerate(source_file_entry_list, 1):
        source_file_hash = calculate_file_sha256(source_file_path)  # 计算源文件哈希
        if source_file_hash in existing_target_hash_map:
            print(
                "[{0}/{1}] 跳过重复文件: {2}".format(
                    current_index,
                    total_file_count,
                    source_file_path,
                )
            )                                                       # 已存在相同内容
            skipped_duplicate_count += 1
            continue
        destination_path = build_destination_path(
            source_file_path,
            target_directory,
            file_category,
        )                                                           # 计算目标路径
        destination_path.parent.mkdir(parents=True, exist_ok=True)  # 确保目标父目录存在
        final_output_path = build_non_conflicting_path(destination_path)  # 生成绝不覆盖的最终路径
        if final_output_path != destination_path:
            renamed_file_count += 1
            print(
                "[{0}/{1}] 重名改名: {2} -> {3}".format(
                    current_index,
                    total_file_count,
                    destination_path.name,
                    final_output_path.name,
                )
            )                                                       # 输出重命名信息
        if operation_mode == "copy":
            shutil.copy2(source_file_path, final_output_path)       # 保留元信息复制文件
            copied_file_count += 1
            action_text = "复制"
        else:
            shutil.move(str(source_file_path), str(final_output_path))  # 移动文件
            moved_file_count += 1
            action_text = "移动"
        existing_target_hash_map[source_file_hash] = final_output_path  # 更新已存在哈希映射
        print(
            "[{0}/{1}] 已{2}: {3} -> {4}".format(
                current_index,
                total_file_count,
                action_text,
                source_file_path,
                final_output_path,
            )
        )                                                           # 输出处理结果
    print("\n" + "=" * 72)                                          # 分隔线
    print("处理完成")                                                # 结束标题
    print("=" * 72)                                                 # 分隔线
    print("可整理文件总数: {0}".format(total_file_count))             # 输出可处理总数
    print("复制数量: {0}".format(copied_file_count))                 # 输出复制数量
    print("移动数量: {0}".format(moved_file_count))                  # 输出移动数量
    print("跳过重复: {0}".format(skipped_duplicate_count))           # 输出跳过重复数量
    print("重命名数: {0}".format(renamed_file_count))                # 输出重命名数量
    print("跳过不支持类型: {0}".format(skipped_unsupported_count))    # 输出不支持类型数量
    print("")                                                        # 空行
    print("说明：")                                                  # 结果说明
    print("  - 没有任何已有文件被覆盖。")                              # 不覆盖再次确认
    print("  - 重复文件已按哈希跳过。")                                # 去重确认
    print("  - 重名文件已自动改名保存。")                              # 重名确认
    print("")                                                        # 空行
if __name__ == "__main__":
    main()
