import os
import shutil
import hashlib
from datetime import datetime
def categorize_file(filepath):
    # Categorize files based on their extension
    extension = os.path.splitext(filepath)[1].lower()
    file_categories = {
        "images": [".jpg", ".jpeg", ".png", ".gif"],
        "documents": [".pdf", ".doc", ".docx", ".txt"],
        "videos": [".mp4", ".avi", ".mkv", ".mov", ".wmv"],
        "audio": [".mp3", ".wav", ".flac"],
        "apps": [".exe"],
        "archives": [".zip", ".rar"]
    }
    # Iterate through the dictionary and return the corresponding file category
    for category, extensions in file_categories.items():
        if extension in extensions:
            return category
    return "other"  # Return "other" if no matching extension is found
def create_folders(directory):
    # Create category folders in the target directory
    categories = ["images", "documents", "videos", "audio", "apps", "archives", "other"]
    for category in categories:
        os.makedirs(os.path.join(directory, category), exist_ok=True)
def hash_file(filepath):
    """Calculate the hash of a file."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()
def sort_files(source_directory, target_directory):
    # Traverse files in the source directory and categorize them into the target directory
    for root, _, files in os.walk(source_directory):
        for filename in files:
            filepath = os.path.join(root, filename)
            file_category = categorize_file(filepath)
            target_path = os.path.join(target_directory, file_category, filename)
            try:
                # Copy file to the target path
                shutil.copy2(filepath, target_path)
                file_date = datetime.fromtimestamp(os.path.getmtime(filepath))
                # Sanitize date for filename to avoid invalid characters
                sanitized_date = file_date.isoformat().replace(":", "-")
                new_filename = f"{sanitized_date}-{filename}"
                new_target_path = os.path.join(target_directory, file_category, new_filename)
                # Ensure the new filename is unique
                counter = 1
                while os.path.exists(new_target_path):
                    new_target_path = os.path.join(target_directory, file_category, f"{sanitized_date}-{counter}-{filename}")
                    counter += 1
                os.rename(target_path, new_target_path)
            except Exception as e:
                print(f"Error processing '{filepath}': {e}")  # Error while processing the file
def remove_duplicates(target_directory):
    """Remove duplicate files, keeping one copy."""
    seen_hashes = {}
    for root, _, files in os.walk(target_directory):
        for filename in files:
            filepath = os.path.join(root, filename)
            file_hash = hash_file(filepath)
            if file_hash in seen_hashes:
                try:
                    os.remove(filepath)
                    print(f"Removed duplicate file: {filepath}")  # Remove duplicate file
                except Exception as e:
                    print(f"Error removing '{filepath}': {e}")  # Error while removing the file
            else:
                seen_hashes[file_hash] = filepath
def main():
    source_directory = input("Please enter the source directory path: ")  # Prompt for source directory
    target_directory = input("Please enter the target directory path: ")  # Prompt for target directory
    create_folders(target_directory)  # Create target folders
    sort_files(source_directory, target_directory)  # Organize files
    # Ask user if they want to remove duplicate files
    user_input = input("Do you want to remove duplicate files? (y/n): ").strip().lower()
    if user_input == 'y':
        remove_duplicates(target_directory)  # Remove duplicate files
        print("Duplicate files have been removed.")  # Confirm removal
    else:
        print("Duplicate files were not removed.")  # Confirm no removal
    print("File organization completed!")  # Completion message


main()
