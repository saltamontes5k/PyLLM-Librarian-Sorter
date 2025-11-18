# PyLLM-Librarian-Sorter
A powerful and flexible command-line tool to automatically organize and manage your ebook collection using an Ollama LLM and python.

What It Does
ebook-organizer scans a source directory for ebook files (like EPUB, MOBI, PDF, etc.), extracts their metadata (title, author), and moves them to a target directory in a clean, hierarchical structure based on genre, llm decision making, search, and if required user input.

It operates in two distinct modes to suit your workflow:

Automated Mode (--auto): The "set it and forget it" option. Perfect for batch processing large collections without any user interaction.

Interactive Mode (--interactive): Gives you full control. It presents you with each file and the proposed action, allowing you to approve, skip, or modify it before any changes are made.

Key Features

Dual-Mode Operation: Choose between fast automation or granular interactive control.

Metadata Extraction: Reads metadata from within ebook files to intelligently determine author and title.

Broad Format Support: Works with common ebook formats including .epub, .mobi, .pdf, .azw, and .azw3.

Safe Logging: Keeps a detailed log of all actions, so you always know what was moved and where.

Dry Run Mode: (Optional feature) Preview what changes would be made without actually touching your files.

Prerequisites;

Before you begin, ensure you have the following installed:

Python 3.7 - 3.10: If you have newer editions of python you may need to run this through a conda environment
ollama, and by default I use gemma3:12b, but you're free to use another llm

Specifics;

# Automated Mode
Use this mode to process an entire folder of ebooks without prompts.

# Basic usage
python organize_ebooks.py --auto --source ~/Downloads/Unsorted_Books

# Specify a custom target directory
python organize_ebooks.py -a -s ~/Downloads/Unsorted_Books -t ~/Documents/My_Library
What happens: The script will scan ~/Downloads/Unsorted_Books, read each ebook's metadata, and move it to ~/Documents/My_Library/Author Name/Book Title/Book Name.extension.

Interactive Mode
Use this mode to review and approve each action individually.

python organize_ebooks.py --interactive --source ~/Downloads/Unsorted_Books
What happens: You will be prompted for each file found:

Found file: 'a-great-book_v2.epub'
Metadata -> Author: 'Jane Doe', Title: 'A Great Book'
Proposed Action: Move to '/path/to/target/Jane Doe/A Great Book/a-great-book.epub'
Proceed? [y/N/s/q] >
y (yes): Perform the move.
N (no): Skip this file.
s (skip): Skip this file and all others by the same author.
q (quit): Exit the script.

Example: Before & After
Running the script can transform a messy folder into a well-organized library.

Before:
Unsorted_Books/
├── a-great-book_v2.epub
├── learning_python.pdf
├── some-other-mobi-file.mobi
└── The_Hobbit-Tolkien.epub

After:
Biographical or Memoir
├── a-great-book_v2.epub
Computer Science
├── learning_python.pdf
Educational or Pedagogy
├── some-other-mobi-file.mobi
Fantasy
└── The_Hobbit-Tolkien.epub

│   └── The Hobbit/
│       └── The_Hobbit-Tolkien.epub
