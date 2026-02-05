
import os
import shutil

# File extensions
FILE_EXTENSIONS = {
    "image": ['.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff'],
    "audio": ['.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a', '.wma'],
    "video": ['.mp4', '.avi', '.wmv', '.mov', '.flv', '.mkv', '.webm'],
    "office": ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.pdf', '.csv', '.txt'],
}

def get_file_type(filename):
    extension = os.path.splitext(filename)[1].lower()
    for category in FILE_EXTENSIONS:
        for ext in FILE_EXTENSIONS[category]:
            if extension == ext:
                return category
    return None

def count_files_and_collect_paths(root_directory):
    stats = {
        "image": 0,
        "audio": 0,
        "video": 0,
        "office": 0,
    }
    file_paths = {
        "image": [],
        "audio": [],
        "video": [],
        "office": [],
    }
    for folder_path, folder_names, filenames in os.walk(root_directory):
        for filename in filenames:
            file_type = get_file_type(filename)
            if file_type is not None:
                full_file_path = os.path.join(folder_path, filename)
                stats[file_type] += 1
                file_paths[file_type].append(full_file_path)
    return stats, file_paths

def print_statistics(stats):
    print("\nFile category statistics:")
    for category in stats:
        print(f"{category}: {stats[category]}")

def get_non_duplicate_name(destination_directory, filename):
    base_name, extension = os.path.splitext(filename)
    counter = 1
    new_filename = filename
    while os.path.exists(os.path.join(destination_directory, new_filename)):
        new_filename = f"{base_name}_{counter}{extension}"
        counter += 1
    return new_filename

def move_files(file_paths, root_directory):
    for category in file_paths:
        target_folder = os.path.join(root_directory, category)
        if not os.path.exists(target_folder):
            os.makedirs(target_folder)
        for filepath in file_paths[category]:
            filename = os.path.basename(filepath)
            new_filename = get_non_duplicate_name(target_folder, filename)
            new_file_path = os.path.join(target_folder, new_filename)
            if filepath != new_file_path:
                shutil.move(filepath, new_file_path)

if __name__ == "__main__":
    root_directory = input("Input the folder path to organize: ").strip()
    if not os.path.isdir(root_directory):
        print("Invalid directory.")
        exit(1)
    stats, file_paths = count_files_and_collect_paths(root_directory)
    print_statistics(stats)

    answer = input("\nMove files to corresponding categorized folders? (y/n): ").strip().lower()
    if answer == 'y':
        move_files(file_paths, root_directory)
        print("File organization completed!")
    else:
        print("Operation cancelled.")
