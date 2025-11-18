import os
import re
import csv
import json
import requests
import logging
import tkinter as tk
from tkinter import simpledialog, messagebox
from pathlib import Path
from datetime import datetime
import time
from urllib.parse import quote_plus
import pickle
import sys

# Configuration
EBOOK_LIBRARY_PATH = "Driveletter:\\ToBooks"
LOG_PATH = "Driveletter:\\Whereyouwantlogs\\OrganizerLog.txt"
CSV_OUTPUT_PATH = "Driveletter:\\Whereyouwantlogs\\EbookLibrary.csv"
OLLAMA_API = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "gemma3:12b"
MAX_PAGES_TO_READ = 10
PROGRESS_INTERVAL = 10
PROGRESS_FILE = "Driveletter:\\Whereyouwantlogs\\organizer_progress.pkl"
UNSORTED_FOLDER = "UNSORTED"  # Folder for files that can't be categorized

# Mode selection
INTERACTIVE_MODE = None  # Will be set based on user input or command line argument

# Supported ebook extensions (now includes DJVU, CBR, and AZW3)
EBOOK_EXTENSIONS = ['.pdf', '.epub', '.mobi', '.txt', '.azw', '.azw3', '.fb2', '.lit', '.pdb', '.tcr', '.djvu', '.cbr']

def parse_arguments():
    """Parse command line arguments"""
    global INTERACTIVE_MODE
    
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ['--auto', '-a', '--automated']:
            INTERACTIVE_MODE = False
            print("Running in AUTOMATED mode - uncertain files will be moved to UNSORTED folder")
        elif arg in ['--interactive', '-i', '--prompt']:
            INTERACTIVE_MODE = True
            print("Running in INTERACTIVE mode - you will be prompted for uncertain files")
        else:
            print(f"Unknown argument: {arg}")
            print("Usage: python organize_ebooks.py [--auto|--interactive]")
            sys.exit(1)
    else:
        # No arguments provided, ask user
        choose_mode()

def choose_mode():
    """Let user choose between automated and interactive mode"""
    global INTERACTIVE_MODE
    
    print("\n" + "="*60)
    print("EBOOK LIBRARY ORGANIZER")
    print("="*60)
    print("\nChoose operating mode:")
    print("1. AUTOMATED mode - Uncertain files go to UNSORTED folder")
    print("2. INTERACTIVE mode - Prompt for uncertain files")
    print("\nPress 1 for Automated, 2 for Interactive, or Q to quit")
    
    while True:
        choice = input("\nEnter your choice (1/2/Q): ").strip().upper()
        
        if choice == '1':
            INTERACTIVE_MODE = False
            print("\nSelected: AUTOMATED mode")
            break
        elif choice == '2':
            INTERACTIVE_MODE = True
            print("\nSelected: INTERACTIVE mode")
            break
        elif choice == 'Q':
            print("Exiting...")
            sys.exit(0)
        else:
            print("Invalid choice. Please enter 1, 2, or Q")

# Set up logging
def setup_logging():
    """Initialize logging system"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mode_text = "INTERACTIVE" if INTERACTIVE_MODE else "AUTOMATED"
    log_header = f"===== EBOOK ORGANIZER LOG STARTED AT {timestamp} ({mode_text} MODE) =====\n"
    
    # Create directory if it doesn't exist
    log_dir = os.path.dirname(LOG_PATH)
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(LOG_PATH),
            logging.StreamHandler()
        ]
    )
    
    # Write header to log file
    with open(LOG_PATH, 'a') as f:  # Changed to 'a' to append to existing log
        if os.path.getsize(LOG_PATH) == 0:  # Only write header if file is empty
            f.write(log_header)
    
    logging.info("Starting ebook organization process")
    logging.info(f"Library path: {EBOOK_LIBRARY_PATH}")
    logging.info(f"Ollama API: {OLLAMA_API}")
    logging.info(f"Ollama model: {OLLAMA_MODEL}")
    logging.info(f"Mode: {mode_text}")
    if not INTERACTIVE_MODE:
        logging.info(f"Uncertain files will be moved to: {UNSORTED_FOLDER}")

def load_progress():
    """Load progress from file or return empty progress if first run"""
    # First try to load from progress file
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'rb') as f:
                progress_data = pickle.load(f)
            logging.info(f"Loaded progress from {PROGRESS_FILE}")
            logging.info(f"Previously processed {len(progress_data['processed_files'])} files")
            return progress_data['processed_files'], progress_data['csv_data'], progress_data['genre_stats']
        except Exception as e:
            logging.error(f"Error loading progress file: {str(e)}")
    
    # If no progress file, return empty progress
    logging.info("No existing progress file found - starting fresh")
    return set(), [], {}

def is_genre_folder(folder_path):
    """Check if a folder is likely a genre folder (not system folder)"""
    folder_name = os.path.basename(folder_path)
    
    # Skip system folders and common non-genre folders
    system_folders = [
        'System Volume Information', '$RECYCLE.BIN', 'RECYCLER', 
        'Windows', 'Program Files', 'Program Files (x86)', 'ProgramData',
        'Users', 'Documents and Settings', 'AppData', 'Temp', 'tmp',
        '.git', '.svn', '__pycache__', 'node_modules'
    ]
    
    # Skip hidden folders (starting with .)
    if folder_name.startswith('.'):
        return False
    
    # Skip system folders
    if folder_name in system_folders:
        return False
    
    # Skip UNSORTED folder (we handle this separately)
    if folder_name == UNSORTED_FOLDER:
        return False
    
    # If it contains ebook files, it's likely a genre folder
    for file in os.listdir(folder_path):
        file_path = os.path.join(folder_path, file)
        if os.path.isfile(file_path) and any(file.lower().endswith(ext) for ext in EBOOK_EXTENSIONS):
            return True
    
    return False

def detect_existing_progress():
    """Scan existing genre folders to detect already processed files"""
    processed_files = set()
    csv_data = []
    genre_stats = {}
    
    logging.info("Detecting existing progress by scanning genre folders...")
    
    # Walk through library and find files in genre folders
    for root, dirs, files in os.walk(EBOOK_LIBRARY_PATH):
        # Skip root level and non-genre folders
        if root == EBOOK_LIBRARY_PATH:
            continue
        
        # Check if this is a genre folder
        if not is_genre_folder(root):
            continue
            
        # Extract genre from folder name
        genre = os.path.basename(root)
        
        for file in files:
            if any(file.lower().endswith(ext) for ext in EBOOK_EXTENSIONS):
                file_path = os.path.join(root, file)
                processed_files.add(file_path)
                
                # Add to CSV data
                csv_data.append({
                    'Filename': file,
                    'OriginalPath': file_path,
                    'Genre': genre,
                    'ProcessingDate': datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Use current date as fallback
                })
                
                # Update genre statistics
                if genre in genre_stats:
                    genre_stats[genre] += 1
                else:
                    genre_stats[genre] = 1
    
    # Also check UNSORTED folder
    unsorted_path = os.path.join(EBOOK_LIBRARY_PATH, UNSORTED_FOLDER)
    if os.path.exists(unsorted_path):
        for root, _, files in os.walk(unsorted_path):
            for file in files:
                if any(file.lower().endswith(ext) for ext in EBOOK_EXTENSIONS):
                    file_path = os.path.join(root, file)
                    processed_files.add(file_path)
                    
                    # Add to CSV data
                    csv_data.append({
                        'Filename': file,
                        'OriginalPath': file_path,
                        'Genre': UNSORTED_FOLDER,
                        'ProcessingDate': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
                    # Update genre statistics
                    if UNSORTED_FOLDER in genre_stats:
                        genre_stats[UNSORTED_FOLDER] += 1
                    else:
                        genre_stats[UNSORTED_FOLDER] = 1
    
    logging.info(f"Detected {len(processed_files)} already processed files in {len(genre_stats)} genre folders")
    return processed_files, csv_data, genre_stats

def save_progress(processed_files, csv_data, genre_stats):
    """Save current progress to file"""
    progress_data = {
        'processed_files': processed_files,
        'csv_data': csv_data,
        'genre_stats': genre_stats,
        'timestamp': datetime.now().isoformat()
    }
    
    try:
        with open(PROGRESS_FILE, 'wb') as f:
            pickle.dump(progress_data, f)
        logging.info(f"Progress saved to {PROGRESS_FILE}")
    except Exception as e:
        logging.error(f"Error saving progress: {str(e)}")

def get_genre_from_ollama(prompt, model=OLLAMA_MODEL):
    """Query Ollama for genre determination"""
    try:
        body = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3  # Lower temperature for more consistent results
            }
        }
        
        response = requests.post(OLLAMA_API, json=body, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result.get('response', '').strip()
    except Exception as e:
        logging.error(f"Error querying Ollama: {str(e)}")
        return None

def get_genre_from_filename(filename):
    """Determine genre from filename"""
    # Clean up filename for better analysis
    clean_filename = re.sub(r'\.(pdf|epub|mobi|azw|azw3|fb2|lit|pdb|tcr|txt|djvu|cbr)$', '', filename, flags=re.IGNORECASE)
    clean_filename = re.sub(r'\(.*?\)|\[.*?\]|\{.*?\}', '', clean_filename)  # Remove content in brackets
    clean_filename = re.sub(r'^\d+[\.\-_]?\s*', '', clean_filename)  # Remove leading numbers
    
    prompt = f"""Based on the filename '{clean_filename}', determine the most specific genre of this book. 
    Be as specific as possible. For non-fiction books, don't just say "Non-Fiction" - use more specific categories like:
    - Geography, Travel, or Regional Studies
    - Neuroscience, Psychology, or Cognitive Science
    - Philosophy, Ethics, or Logic
    - History (with specific time period if possible)
    - Science (Physics, Chemistry, Biology, etc.)
    - Mathematics, Statistics, or Data Science
    - Economics, Finance, or Business
    - Politics, Sociology, or Anthropology
    - Technology, Computer Science, or Engineering
    - Education, Teaching, or Pedagogy
    - Art, Music, or Literature Criticism
    - Biography or Memoir
    - Self-Help, Personal Development, or Productivity
    - Cooking, Food, or Nutrition
    - Health, Medicine, or Fitness
    - Religion, Spirituality, or Mythology
    
    For fiction, use specific genres like:
    - Science Fiction, Fantasy, or Horror
    - Mystery, Thriller, or Crime
    - Romance, Historical Fiction, or Literary Fiction
    - Young Adult, Children's, or Middle Grade
    
    Respond with only the most specific genre name. If uncertain, respond with 'UNCERTAIN'."""
    
    genre = get_genre_from_ollama(prompt)
    
    if genre == "UNCERTAIN" or not genre:
        return None
    
    return genre

def get_first_pages_text(file_path, max_pages=MAX_PAGES_TO_READ):
    """Extract text from first pages of an ebook"""
    extension = Path(file_path).suffix.lower()
    
    try:
        if extension == '.txt':
            # For text files, just read the first X lines
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = []
                for _ in range(max_pages * 50):  # Assuming ~50 lines per page
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line)
                return '\n'.join(lines)
        elif extension in ['.djvu', '.cbr']:
            # For DJVU and CBR files, specialized libraries would be needed
            # djvufile for DJVU, comicapi for CBR/CBZ
            logging.warning(f"Text extraction for {extension} files requires specialized libraries (e.g., djvulibre, comicapi). Skipping content analysis.")
            return None
        else:
            # For other formats, we'd need specialized libraries
            # This is a simplified implementation
            logging.warning(f"Text extraction for {extension} files requires specialized libraries. Skipping content analysis.")
            return None
    except Exception as e:
        logging.error(f"Error extracting text from {file_path}: {str(e)}")
        return None

def get_genre_from_content(content, filename):
    """Determine genre from content"""
    if not content:
        return None
        
    # Truncate content if too long for API
    max_length = 8000  # Adjust based on your model's context window
    if len(content) > max_length:
        content = content[:max_length] + "..."
    
    prompt = f"""Based on the following content from the beginning of '{filename}', determine the most specific genre of this book. 
    Be as specific as possible. For non-fiction books, don't just say "Non-Fiction" - use more specific categories like:
    - Geography, Travel, or Regional Studies
    - Neuroscience, Psychology, or Cognitive Science
    - Philosophy, Ethics, or Logic
    - History (with specific time period if possible)
    - Science (Physics, Chemistry, Biology, etc.)
    - Mathematics, Statistics, or Data Science
    - Economics, Finance, or Business
    - Politics, Sociology, or Anthropology
    - Technology, Computer Science, or Engineering
    - Education, Teaching, or Pedagogy
    - Art, Music, or Literature Criticism
    - Biography or Memoir
    - Self-Help, Personal Development, or Productivity
    - Cooking, Food, or Nutrition
    - Health, Medicine, or Fitness
    - Religion, Spirituality, or Mythology
    
    For fiction, use specific genres like:
    - Science Fiction, Fantasy, or Horror
    - Mystery, Thriller, or Crime
    - Romance, Historical Fiction, or Literary Fiction
    - Young Adult, Children's, or Middle Grade
    
    Respond with only the most specific genre name. If uncertain, respond with 'UNCERTAIN'.
    
    Content:
    {content}"""
    
    genre = get_genre_from_ollama(prompt)
    
    if genre == "UNCERTAIN" or not genre:
        return None
    
    return genre

def get_genre_from_online_search(filename):
    """Search online for genre information"""
    # Extract potential title from filename
    title = Path(filename).stem
    
    # Clean up the title - remove common patterns
    title = re.sub(r'\(.*?\)|\[.*?\]|\{.*?\}', '', title)  # Remove content in brackets
    title = re.sub(r'^\d+[\.\-_]?\s*', '', title)  # Remove leading numbers
    
    try:
        # Use DuckDuckGo for search (no API key required)
        search_query = f"book genre \"{title}\""
        escaped_query = quote_plus(search_query)
        search_uri = f"https://duckduckgo.com/html/?q={escaped_query}"
        
        response = requests.get(search_uri, timeout=15)
        response.raise_for_status()
        html = response.text
        
        # Extract search results (simple approach)
        pattern = r'<a[^>]*class="result__a"[^>]*>(.*?)</a>'
        matches = re.findall(pattern, html)
        
        if matches:
            # Take first few results for analysis
            search_results = "\n".join(matches[:3])
            
            # Use Ollama to analyze search results
            prompt = f"""Based on these search results for '{title}', determine the most specific genre of this book. 
            Be as specific as possible. For non-fiction books, don't just say "Non-Fiction" - use more specific categories like:
            - Geography, Travel, or Regional Studies
            - Neuroscience, Psychology, or Cognitive Science
            - Philosophy, Ethics, or Logic
            - History (with specific time period if possible)
            - Science (Physics, Chemistry, Biology, etc.)
            - Mathematics, Statistics, or Data Science
            - Economics, Finance, or Business
            - Politics, Sociology, or Anthropology
            - Technology, Computer Science, or Engineering
            - Education, Teaching, or Pedagogy
            - Art, Music, or Literature Criticism
            - Biography or Memoir
            - Self-Help, Personal Development, or Productivity
            - Cooking, Food, or Nutrition
            - Health, Medicine, or Fitness
            - Religion, Spirituality, or Mythology
            
            For fiction, use specific genres like:
            - Science Fiction, Fantasy, or Horror
            - Mystery, Thriller, or Crime
            - Romance, Historical Fiction, or Literary Fiction
            - Young Adult, Children's, or Middle Grade
            
            Respond with only the most specific genre name. If uncertain, respond with 'UNCERTAIN'.
            
            Search Results:
            {search_results}"""
            
            genre = get_genre_from_ollama(prompt)
            
            if genre == "UNCERTAIN" or not genre:
                return None
            
            return genre
        
        return None
    except Exception as e:
        logging.error(f"Error during online search: {str(e)}")
        return None

def get_genre_from_user(filename):
    """Prompt user for genre (only in interactive mode)"""
    if not INTERACTIVE_MODE:
        return None
        
    title = Path(filename).stem
    
    # Create a simple dialog to get user input
    root = tk.Tk()
    root.withdraw()  # Hide the main window
    
    message = f"""Unable to determine genre for '{title}'.

Please enter a specific genre. Examples of specific genres:
- Geography, Travel, or Regional Studies
- Neuroscience, Psychology, or Cognitive Science
- Philosophy, Ethics, or Logic
- History (with specific time period if possible)
- Science (Physics, Chemistry, Biology, etc.)
- Mathematics, Statistics, or Data Science
- Economics, Finance, or Business
- Politics, Sociology, or Anthropology
- Technology, Computer Science, or Engineering
- Education, Teaching, or Pedagogy
- Art, Music, or Literature Criticism
- Biography or Memoir
- Self-Help, Personal Development, or Productivity
- Cooking, Food, or Nutrition
- Health, Medicine, or Fitness
- Religion, Spirituality, or Mythology
- Science Fiction, Fantasy, or Horror
- Mystery, Thriller, or Crime
- Romance, Historical Fiction, or Literary Fiction
- Young Adult, Children's, or Middle Grade

Or enter 'SKIP' to move to UNSORTED folder."""
    
    genre = simpledialog.askstring("Genre Determination", message)
    
    if genre:
        genre = genre.strip()
        if genre.upper() == 'SKIP':
            return UNSORTED_FOLDER
        return genre
    
    return None

def ensure_folder_exists(folder_path):
    """Create folder if it doesn't exist"""
    if not os.path.exists(folder_path):
        try:
            os.makedirs(folder_path)
            logging.info(f"Created folder: {folder_path}")
            return True
        except Exception as e:
            logging.error(f"Error creating folder {folder_path}: {str(e)}")
            return False
    
    return True

def move_to_genre_folder(source_path, genre, library_path=EBOOK_LIBRARY_PATH):
    """Move file to genre folder or UNSORTED folder"""
    filename = os.path.basename(source_path)
    
    # Determine destination based on genre
    if genre == UNSORTED_FOLDER:
        destination_folder = os.path.join(library_path, UNSORTED_FOLDER)
    else:
        destination_folder = os.path.join(library_path, genre)
    
    destination_path = os.path.join(destination_folder, filename)
    
    # Ensure destination folder exists
    if not ensure_folder_exists(destination_folder):
        return False
    
    try:
        # Check if file already exists at destination
        if os.path.exists(destination_path):
            base_name = Path(filename).stem
            extension = Path(filename).suffix
            counter = 1
            
            while True:
                new_filename = f"{base_name}({counter}){extension}"
                destination_path = os.path.join(destination_folder, new_filename)
                if not os.path.exists(destination_path):
                    break
                counter += 1
            
            logging.warning(f"File '{filename}' already exists in '{genre}' folder. Renaming to '{new_filename}'")
        
        os.rename(source_path, destination_path)
        logging.info(f"Moved '{filename}' to '{genre}' folder")
        return True
    except Exception as e:
        logging.error(f"Error moving '{filename}' to '{genre}' folder: {str(e)}")
        return False

def get_all_ebooks(library_path=EBOOK_LIBRARY_PATH):
    """Get all ebook files recursively"""
    all_ebooks = []
    
    for root, _, files in os.walk(library_path):
        for file in files:
            if any(file.lower().endswith(ext) for ext in EBOOK_EXTENSIONS):
                all_ebooks.append(os.path.join(root, file))
    
    return all_ebooks

def organize_ebook_library():
    """Main function to organize the library"""
    # Parse command line arguments or ask user for mode
    parse_arguments()
    
    setup_logging()
    
    # Load existing progress or start fresh
    if os.path.exists(PROGRESS_FILE):
        processed_files, csv_data, genre_stats = load_progress()
    else:
        # First run, only detect files in genre folders
        processed_files, csv_data, genre_stats = detect_existing_progress()
    
    # Get all ebook files
    all_ebooks = get_all_ebooks()
    total_ebooks = len(all_ebooks)
    
    # Filter out already processed files
    remaining_ebooks = [ebook for ebook in all_ebooks if ebook not in processed_files]
    remaining_count = len(remaining_ebooks)
    
    if remaining_count == 0:
        logging.info("All ebooks have already been processed!")
        print("All ebooks have already been processed!")
        return
    
    mode_text = "INTERACTIVE" if INTERACTIVE_MODE else "AUTOMATED"
    logging.info(f"Found {total_ebooks} total ebooks, {len(processed_files)} already processed, {remaining_count} remaining to process")
    print(f"\nFound {total_ebooks} total ebooks, {len(processed_files)} already processed, {remaining_count} remaining to process")
    print(f"Running in {mode_text} mode")
    
    # Process each remaining ebook
    for i, ebook_path in enumerate(remaining_ebooks):
        progress_percent = round((i / remaining_count) * 100)
        filename = os.path.basename(ebook_path)
        
        # Update progress
        if i % PROGRESS_INTERVAL == 0 or i == remaining_count - 1:
            print(f"Progress: {progress_percent}% - Processing {filename} ({i + 1} of {remaining_count} remaining)")
        
        logging.info(f"Processing {filename} ({i + 1} of {remaining_count} remaining)")
        
        # Step 1: Try to determine genre from filename
        genre = get_genre_from_filename(filename)
        
        # Step 2: If uncertain, try to determine from content
        if not genre:
            logging.info(f"Could not determine genre from filename for {filename}. Analyzing content...")
            content = get_first_pages_text(ebook_path)
            if content:
                genre = get_genre_from_content(content, filename)
        
        # Step 3: If still uncertain, try online search
        if not genre:
            logging.info(f"Could not determine genre from content for {filename}. Searching online...")
            genre = get_genre_from_online_search(filename)
        
        # Step 4: If still uncertain, handle based on mode
        if not genre:
            if INTERACTIVE_MODE:
                logging.info(f"Could not determine genre for {filename}. Prompting user...")
                genre = get_genre_from_user(filename)
            else:
                logging.info(f"Could not determine genre for {filename}. Moving to {UNSORTED_FOLDER} folder.")
                genre = UNSORTED_FOLDER
        
        # If we have a genre, move the file
        if genre:
            if move_to_genre_folder(ebook_path, genre):
                # Add to CSV data
                csv_data.append({
                    'Filename': filename,
                    'OriginalPath': ebook_path,
                    'Genre': genre,
                    'ProcessingDate': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                
                # Update genre statistics
                if genre in genre_stats:
                    genre_stats[genre] += 1
                else:
                    genre_stats[genre] = 1
                
                # Mark as processed
                processed_files.add(ebook_path)
        else:
            logging.warning(f"Could not determine genre for {filename}. Skipping.")
            
            # Add to CSV data with no genre
            csv_data.append({
                'Filename': filename,
                'OriginalPath': ebook_path,
                'Genre': "UNDETERMINED",
                'ProcessingDate': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            
            # Update genre statistics
            if "UNDETERMINED" in genre_stats:
                genre_stats["UNDETERMINED"] += 1
            else:
                genre_stats["UNDETERMINED"] = 1
            
            # Mark as processed
            processed_files.add(ebook_path)
        
        # Save progress every 10 files
        if (i + 1) % 10 == 0:
            save_progress(processed_files, csv_data, genre_stats)
    
    # Final progress save
    save_progress(processed_files, csv_data, genre_stats)
    
    # Create directory for CSV output if it doesn't exist
    csv_dir = os.path.dirname(CSV_OUTPUT_PATH)
    if not os.path.exists(csv_dir):
        os.makedirs(csv_dir)
    
    # Export CSV
    try:
        with open(CSV_OUTPUT_PATH, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Filename', 'OriginalPath', 'Genre', 'ProcessingDate']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_data)
        logging.info(f"Exported ebook data to {CSV_OUTPUT_PATH}")
    except Exception as e:
        logging.error(f"Error exporting CSV: {str(e)}")
    
    # Log genre statistics
    logging.info("Genre Statistics:")
    for genre in sorted(genre_stats.keys()):
        logging.info(f"{genre}: {genre_stats[genre]} books")
    
    logging.info(f"Ebook organization complete. Processed {len(processed_files)} ebooks.")
    
    # Display summary
    print("\n" + "="*60)
    print("EBOOK ORGANIZATION SUMMARY")
    print("="*60)
    print(f"Total ebooks processed: {len(processed_files)}")
    print(f"Genres identified: {len(genre_stats)}")
    if UNSORTED_FOLDER in genre_stats:
        print(f"Files moved to {UNSORTED_FOLDER}: {genre_stats[UNSORTED_FOLDER]}")
    print(f"CSV report saved to: {CSV_OUTPUT_PATH}")
    print(f"Log file saved to: {LOG_PATH}")
    print(f"Progress file saved to: {PROGRESS_FILE}")
    if not INTERACTIVE_MODE:
        print(f"\nYou can manually review files in '{UNSORTED_FOLDER}' folder later.")
    print("="*60)

if __name__ == "__main__":
    organize_ebook_library()