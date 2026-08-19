German Vocabulary Trainer & Testing Engine
A PyQt5 desktop application and SQLite database engine for learning German vocabulary from English. Built for reading comprehension and active recall, this application features CEFR level filtering, detailed word history tracking, interactive flashcards, and 4 test modes.

Key Features
CEFR Level Filtering: Filter batches by difficulty (A1, A2, B1, B2, C1, C2).

Smart Word Batching:

Unseen Words: Grab the next 10 unreviewed words ordered by ID.

Random Revision: Revisit 10 previously shown words.

Weak Spot Revision: Target words with the highest error count (times_wrong > 0).

Custom Sequences: Option to skip spell check exercises for faster sessions.

Smart Article Formatting: Automatically handles German noun articles (der, die, das) alongside lemma terms without duplicating prefixes.

4 Interactive Study & Test Modes:

Flashcard Flip: Self-graded active recall (Got it vs. Forgot it).

Multiple Choice (ENG → DEU): English prompt with 4 German options.

Multiple Choice (DEU → ENG): German prompt with 4 English options.

Spell Check: Scrambled letter buttons for spelling practice.

Matching Box: Interactive pair matching for up to 10 English and German terms.

Progress Analytics: Real-time SQLite tracking of times_shown, times_correct, and times_wrong per word.

Project Structure
Plaintext
.
├── german_vocab.db         # SQLite database containing vocabulary & stats
├── cefr_vocabulary.csv     # Raw VocabForge CSV dataset (Semicolon separated, UTF-8)
├── import_csv_to_db.py     # Script to parse UTF-8 CSV and initialize SQLite schema
├── main.py                 # PyQt5 application entry point
└── README.md
Database Schema
The app connects to a german_vocab.db SQLite database with the following table structure:

SQL
CREATE TABLE vocabulary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cefr_level TEXT,
    category TEXT,
    lemma TEXT,
    term TEXT,
    translation TEXT,
    article TEXT,
    aliases TEXT,
    times_shown INTEGER DEFAULT 0,
    times_correct INTEGER DEFAULT 0,
    times_wrong INTEGER DEFAULT 0
);
Getting Started
Prerequisites
Python 3.8 or higher

PyQt5

Pandas

Install dependencies via pip:

Bash
pip install PyQt5 pandas
1. Initialize the Database
If you are setting up the database from a semicolon-separated UTF-8 CSV file (cefr_vocabulary.csv):

Bash
python import_csv_to_db.py
2. Run the Application
Launch the PyQt5 desktop GUI:

Bash
python main.py
Usage Guide
Select CEFR Levels: Check/uncheck target levels (e.g., check A1 and A2 for beginner reading).

Choose Source Batch: Select between Unseen Words, Revision, or Frequently Wrong Words.

Review Flashcards: Click Flip Card to reveal the English translation, then grade your recall.

Complete Exercises: Complete the sequential Multiple Choice, Spell Check, and Matching tests.

Session Summary: Review updated error counts and attempt history at the end of each session.
