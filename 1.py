import random
import sqlite3
import sys
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class DatabaseManager:

    def __init__(self, db_path="german_vocab.db"):
        self.db_path = db_path

    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def fetch_word_set(self, mode="unseen", limit=10, cefr_levels=None):
        """Fetches 10 words based on selected source mode and active CEFR level filter."""
        conn = self.get_connection()
        cursor = conn.cursor()

        # Build CEFR level SQL WHERE clause filter
        cefr_filter_sql = ""
        params = []

        if cefr_levels:
            placeholders = ",".join(["?"] * len(cefr_levels))
            cefr_filter_sql = f" AND UPPER(cefr_level) IN ({placeholders})"
            params.extend([lvl.upper() for lvl in cefr_levels])

        if mode == "unseen":
            query = f"""
                SELECT * FROM vocabulary 
                WHERE (times_shown = 0 OR times_shown IS NULL){cefr_filter_sql}
                ORDER BY id ASC LIMIT ?
            """
            cursor.execute(query, params + [limit])

        elif mode in ("random_shown", "no_spell_check"):
            query = f"""
                SELECT * FROM vocabulary 
                WHERE times_shown > 0{cefr_filter_sql}
                ORDER BY RANDOM() LIMIT ?
            """
            cursor.execute(query, params + [limit])

        elif mode == "wrong_words":
            query = f"""
                SELECT * FROM vocabulary 
                WHERE times_wrong > 0{cefr_filter_sql}
                ORDER BY times_wrong DESC, RANDOM() LIMIT ?
            """
            cursor.execute(query, params + [limit])

        rows = cursor.fetchall()

        # Fallback: If not enough matching words, fill remaining within the selected CEFR levels
        if len(rows) < limit:
            existing_ids = tuple([r["id"] for r in rows]) if rows else (-1,)
            placeholder_ids = ",".join(["?"] * len(existing_ids))

            fallback_query = f"""
                SELECT * FROM vocabulary 
                WHERE id NOT IN ({placeholder_ids}){cefr_filter_sql}
                ORDER BY id ASC LIMIT ?
            """
            fallback_params = list(existing_ids) + params + [limit - len(rows)]
            cursor.execute(fallback_query, fallback_params)
            fallback_rows = cursor.fetchall()
            rows.extend(fallback_rows)

        conn.close()
        return [dict(row) for row in rows]

    def get_distractors(self, target_id, field="lemma", count=3):
        conn = self.get_connection()
        cursor = conn.cursor()
        query = f"SELECT {field} FROM vocabulary WHERE id != ? AND {field} IS NOT NULL AND {field} != '' ORDER BY RANDOM() LIMIT ?"
        cursor.execute(query, (target_id, count))
        rows = cursor.fetchall()
        conn.close()
        return [r[field] for r in rows]

    def update_stats(self, word_id, is_correct):
        conn = self.get_connection()
        cursor = conn.cursor()
        if is_correct:
            cursor.execute(
                """
                UPDATE vocabulary 
                SET times_shown = COALESCE(times_shown, 0) + 1,
                    times_correct = COALESCE(times_correct, 0) + 1
                WHERE id = ?
            """,
                (word_id,),
            )
        else:
            cursor.execute(
                """
                UPDATE vocabulary 
                SET times_shown = COALESCE(times_shown, 0) + 1,
                    times_wrong = COALESCE(times_wrong, 0) + 1
                WHERE id = ?
            """,
                (word_id,),
            )
        conn.commit()
        conn.close()


class GermanLearningApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.words = []
        self.current_word_idx = 0
        self.skip_spell_check = False

        self.setWindowTitle("German Learning & Testing Engine")
        self.setGeometry(100, 100, 850, 700)

        self.init_ui()

    def init_ui(self):
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.layout = QVBoxLayout(self.main_widget)

        self.stacked_widget = QStackedWidget()
        self.layout.addWidget(self.stacked_widget)

        # Setup stacked views
        self.setup_start_view()
        self.setup_flashcard_view()
        self.setup_mc_eng_deu_view()
        self.setup_mc_deu_eng_view()
        self.setup_spell_check_view()
        self.setup_matching_view()
        self.setup_summary_view()

        self.stacked_widget.setCurrentIndex(0)

    def get_full_german_word(self, word_dict):
        lemma = word_dict.get("lemma", "").strip()
        article = word_dict.get("article", "")

        if article and not isinstance(article, float):
            article = str(article).strip()
            if lemma.lower().startswith(article.lower() + " "):
                return lemma
            return f"{article} {lemma}"
        return lemma

    # --- 0. START SCREEN WITH CEFR LEVEL SETTINGS ---
    def setup_start_view(self):
        view = QWidget()
        layout = QVBoxLayout(view)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("German Vocabulary Trainer")
        title.setStyleSheet(
            "font-size: 26px; font-weight: bold; margin-bottom: 15px;"
        )

        # CEFR Filter Settings Group
        settings_frame = QFrame()
        settings_frame.setFrameShape(QFrame.StyledPanel)
        settings_frame.setStyleSheet(
            "background-color: #f8f9fa; border: 1px solid #dcdde1; border-radius: 8px; padding: 10px;"
        )
        settings_layout = QVBoxLayout(settings_frame)

        cefr_title = QLabel("Filter CEFR Levels:")
        cefr_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50;")

        checkboxes_layout = QHBoxLayout()
        self.cefr_checkboxes = {}

        # CEFR level checkboxes (A1 to C2)
        for level in ["A1", "A2", "B1", "B2", "C1", "C2"]:
            cb = QCheckBox(level)
            cb.setStyleSheet("font-size: 14px; font-weight: bold; margin-right: 10px;")
            cb.setChecked(True)  # Checked by default
            self.cefr_checkboxes[level] = cb
            checkboxes_layout.addWidget(cb)

        settings_layout.addWidget(cefr_title)
        settings_layout.addLayout(checkboxes_layout)

        label_source = QLabel("Select Word Source Batch:")
        label_source.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 15px;")

        self.source_combo = QComboBox()
        self.source_combo.setFixedWidth(400)
        self.source_combo.setStyleSheet("font-size: 14px; padding: 6px;")
        self.source_combo.addItem(
            "Next 10 Unseen Words (Ordered by ID)", "unseen"
        )
        self.source_combo.addItem(
            "10 Random Previously Shown Words", "random_shown"
        )
        self.source_combo.addItem(
            "10 Shown Words (Skip Spell Check Exercise)", "no_spell_check"
        )
        self.source_combo.addItem(
            "10 Frequently Wrong Words (Weak Spot Revision)", "wrong_words"
        )

        btn_start = QPushButton("Start Learning Session")
        btn_start.setFixedSize(400, 50)
        btn_start.setStyleSheet(
            "font-size: 16px; background-color: #27ae60; color: white; border-radius: 5px; font-weight: bold;"
        )
        btn_start.clicked.connect(self.start_session)

        layout.addWidget(title)
        layout.addWidget(settings_frame)
        layout.addWidget(label_source)
        layout.addWidget(self.source_combo)
        layout.addSpacing(20)
        layout.addWidget(btn_start)

        self.stacked_widget.addWidget(view)

    def get_selected_cefr_levels(self):
        """Returns a list of currently checked CEFR levels."""
        return [
            lvl
            for lvl, cb in self.cefr_checkboxes.items()
            if cb.isChecked()
        ]

    def start_session(self):
        selected_mode = self.source_combo.currentData()
        self.skip_spell_check = selected_mode == "no_spell_check"

        selected_cefr = self.get_selected_cefr_levels()

        if not selected_cefr:
            QMessageBox.warning(
                self, "Filter Error", "Please select at least one CEFR level!"
            )
            return

        self.words = self.db.fetch_word_set(
            mode=selected_mode, limit=10, cefr_levels=selected_cefr
        )

        if not self.words:
            QMessageBox.warning(
                self, "No Data", "No words found matching the selected filters!"
            )
            return

        self.current_word_idx = 0
        self.show_flashcard()
        self.stacked_widget.setCurrentIndex(1)

    # --- 1. FLASHCARD VIEW ---
    def setup_flashcard_view(self):
        view = QWidget()
        layout = QVBoxLayout(view)

        self.fc_progress = QLabel("Word 1 of 10")
        self.fc_progress.setAlignment(Qt.AlignCenter)
        self.fc_progress.setStyleSheet(
            "font-size: 14px; color: #7f8c8d; font-weight: bold;"
        )

        self.card = QFrame()
        self.card.setFrameShape(QFrame.StyledPanel)
        self.card.setStyleSheet(
            "background-color: #ffffff; border: 2px solid #bdc3c7; border-radius: 10px; min-height: 220px;"
        )
        card_layout = QVBoxLayout(self.card)

        self.fc_front = QLabel("German Word")
        self.fc_front.setAlignment(Qt.AlignCenter)
        self.fc_front.setStyleSheet("font-size: 28px; font-weight: bold;")

        self.fc_back = QLabel("English Translation")
        self.fc_back.setAlignment(Qt.AlignCenter)
        self.fc_back.setStyleSheet("font-size: 22px; color: #2c3e50;")
        self.fc_back.hide()

        card_layout.addWidget(self.fc_front)
        card_layout.addWidget(self.fc_back)

        self.btn_flip = QPushButton("Flip Card")
        self.btn_flip.setStyleSheet(
            "font-size: 15px; padding: 10px; background-color: #3498db; color: white;"
        )
        self.btn_flip.clicked.connect(self.flip_flashcard)

        self.grade_layout = QHBoxLayout()
        self.btn_got_it = QPushButton("Got it")
        self.btn_got_it.setStyleSheet(
            "font-size: 15px; padding: 10px; background-color: #2ecc71; color: white;"
        )
        self.btn_got_it.clicked.connect(lambda: self.grade_flashcard(True))

        self.btn_forgot = QPushButton("Forgot it")
        self.btn_forgot.setStyleSheet(
            "font-size: 15px; padding: 10px; background-color: #e74c3c; color: white;"
        )
        self.btn_forgot.clicked.connect(lambda: self.grade_flashcard(False))

        self.grade_layout.addWidget(self.btn_got_it)
        self.grade_layout.addWidget(self.btn_forgot)

        self.grade_widget = QWidget()
        self.grade_widget.setLayout(self.grade_layout)
        self.grade_widget.hide()

        layout.addWidget(self.fc_progress)
        layout.addWidget(self.card)
        layout.addWidget(self.btn_flip)
        layout.addWidget(self.grade_widget)

        self.stacked_widget.addWidget(view)

    def show_flashcard(self):
        word = self.words[self.current_word_idx]
        cefr = word.get("cefr_level", "")
        cefr_tag = f" [{cefr}]" if cefr else ""

        self.fc_progress.setText(
            f"Flashcard {self.current_word_idx + 1} of {len(self.words)}{cefr_tag}"
        )
        self.fc_front.setText(self.get_full_german_word(word))
        self.fc_back.setText(word.get("translation", ""))
        self.fc_back.hide()
        self.btn_flip.show()
        self.grade_widget.hide()

    def flip_flashcard(self):
        self.fc_back.show()
        self.btn_flip.hide()
        self.grade_widget.show()

    def grade_flashcard(self, is_correct):
        word = self.words[self.current_word_idx]
        self.db.update_stats(word["id"], is_correct)

        self.current_word_idx += 1
        if self.current_word_idx < len(self.words):
            self.show_flashcard()
        else:
            self.start_mc_eng_deu()

    # --- 2. MULTIPLE CHOICE: ENG -> DEU ---
    def setup_mc_eng_deu_view(self):
        view = QWidget()
        layout = QVBoxLayout(view)

        self.mc1_progress = QLabel("MC Eng -> Deu")
        self.mc1_progress.setAlignment(Qt.AlignCenter)
        self.mc1_prompt = QLabel("English Prompt")
        self.mc1_prompt.setAlignment(Qt.AlignCenter)
        self.mc1_prompt.setStyleSheet(
            "font-size: 24px; font-weight: bold; margin: 20px;"
        )

        layout.addWidget(self.mc1_progress)
        layout.addWidget(self.mc1_prompt)

        self.mc1_btn_group = QButtonGroup(self)
        self.mc1_buttons = []
        for i in range(4):
            btn = QPushButton(f"Option {i+1}")
            btn.setStyleSheet("font-size: 16px; padding: 12px;")
            self.mc1_btn_group.addButton(btn, i)
            self.mc1_buttons.append(btn)
            layout.addWidget(btn)

        self.mc1_btn_group.buttonClicked.connect(self.handle_mc1_answer)
        self.stacked_widget.addWidget(view)

    def start_mc_eng_deu(self):
        self.current_word_idx = 0
        self.show_mc1_question()
        self.stacked_widget.setCurrentIndex(2)

    def show_mc1_question(self):
        word = self.words[self.current_word_idx]
        self.mc1_progress.setText(
            f"Test 1/4: MC (ENG → DEU) - Word {self.current_word_idx + 1} of {len(self.words)}"
        )
        self.mc1_prompt.setText(word.get("translation", ""))

        correct_answer = self.get_full_german_word(word)
        distractors = self.db.get_distractors(word["id"], field="lemma", count=3)

        options = [correct_answer] + distractors
        random.shuffle(options)

        for btn, opt in zip(self.mc1_buttons, options):
            btn.setText(opt)
            btn.setEnabled(True)
            btn.setStyleSheet("font-size: 16px; padding: 12px;")

    def handle_mc1_answer(self, btn):
        word = self.words[self.current_word_idx]
        correct_answer = self.get_full_german_word(word)

        is_correct = btn.text() == correct_answer
        self.db.update_stats(word["id"], is_correct)

        self.current_word_idx += 1
        if self.current_word_idx < len(self.words):
            self.show_mc1_question()
        else:
            self.start_mc_deu_eng()

    # --- 3. MULTIPLE CHOICE: DEU -> ENG ---
    def setup_mc_deu_eng_view(self):
        view = QWidget()
        layout = QVBoxLayout(view)

        self.mc2_progress = QLabel("MC Deu -> Eng")
        self.mc2_progress.setAlignment(Qt.AlignCenter)
        self.mc2_prompt = QLabel("German Prompt")
        self.mc2_prompt.setAlignment(Qt.AlignCenter)
        self.mc2_prompt.setStyleSheet(
            "font-size: 24px; font-weight: bold; margin: 20px;"
        )

        layout.addWidget(self.mc2_progress)
        layout.addWidget(self.mc2_prompt)

        self.mc2_btn_group = QButtonGroup(self)
        self.mc2_buttons = []
        for i in range(4):
            btn = QPushButton(f"Option {i+1}")
            btn.setStyleSheet("font-size: 16px; padding: 12px;")
            self.mc2_btn_group.addButton(btn, i)
            self.mc2_buttons.append(btn)
            layout.addWidget(btn)

        self.mc2_btn_group.buttonClicked.connect(self.handle_mc2_answer)
        self.stacked_widget.addWidget(view)

    def start_mc_deu_eng(self):
        self.current_word_idx = 0
        self.show_mc2_question()
        self.stacked_widget.setCurrentIndex(3)

    def show_mc2_question(self):
        word = self.words[self.current_word_idx]
        self.mc2_progress.setText(
            f"Test 2/4: MC (DEU → ENG) - Word {self.current_word_idx + 1} of {len(self.words)}"
        )
        self.mc2_prompt.setText(self.get_full_german_word(word))

        correct_answer = word.get("translation", "")
        distractors = self.db.get_distractors(
            word["id"], field="translation", count=3
        )

        options = [correct_answer] + distractors
        random.shuffle(options)

        for btn, opt in zip(self.mc2_buttons, options):
            btn.setText(opt)
            btn.setEnabled(True)
            btn.setStyleSheet("font-size: 16px; padding: 12px;")

    def handle_mc2_answer(self, btn):
        word = self.words[self.current_word_idx]
        correct_answer = word.get("translation", "")

        is_correct = btn.text() == correct_answer
        self.db.update_stats(word["id"], is_correct)

        self.current_word_idx += 1
        if self.current_word_idx < len(self.words):
            self.show_mc2_question()
        else:
            if self.skip_spell_check:
                self.start_matching_exercise()
            else:
                self.start_spell_check()

    # --- 4. SPELL CHECK EXERCISE ---
    def setup_spell_check_view(self):
        view = QWidget()
        layout = QVBoxLayout(view)

        self.sc_progress = QLabel("Spell Check")
        self.sc_progress.setAlignment(Qt.AlignCenter)
        self.sc_prompt = QLabel("English Prompt")
        self.sc_prompt.setAlignment(Qt.AlignCenter)
        self.sc_prompt.setStyleSheet(
            "font-size: 22px; font-weight: bold; margin-top: 10px;"
        )

        self.sc_input = QLineEdit()
        self.sc_input.setReadOnly(True)
        self.sc_input.setAlignment(Qt.AlignCenter)
        self.sc_input.setStyleSheet(
            "font-size: 22px; letter-spacing: 3px; padding: 8px;"
        )

        self.letters_layout = QHBoxLayout()
        self.letters_widget = QWidget()
        self.letters_widget.setLayout(self.letters_layout)

        controls_layout = QHBoxLayout()
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(self.clear_spell_input)
        btn_submit = QPushButton("Submit")
        btn_submit.setStyleSheet(
            "background-color: #27ae60; color: white; font-weight: bold;"
        )
        btn_submit.clicked.connect(self.verify_spell_check)

        controls_layout.addWidget(btn_clear)
        controls_layout.addWidget(btn_submit)

        layout.addWidget(self.sc_progress)
        layout.addWidget(self.sc_prompt)
        layout.addWidget(self.sc_input)
        layout.addWidget(self.letters_widget)
        layout.addLayout(controls_layout)

        self.stacked_widget.addWidget(view)

    def start_spell_check(self):
        self.current_word_idx = 0
        self.show_spell_question()
        self.stacked_widget.setCurrentIndex(4)

    def show_spell_question(self):
        self.clear_spell_input()
        word = self.words[self.current_word_idx]
        self.sc_progress.setText(
            f"Test 3/4: Spell Check - Word {self.current_word_idx + 1} of {len(self.words)}"
        )
        self.sc_prompt.setText(word.get("translation", ""))

        self.target_spelling = self.get_full_german_word(word)

        letters = [c for c in self.target_spelling if c != " "]
        random.shuffle(letters)

        for i in reversed(range(self.letters_layout.count())):
            child = self.letters_layout.itemAt(i).widget()
            if child:
                child.setParent(None)

        for char in letters:
            btn = QPushButton(char)
            btn.setFixedSize(40, 40)
            btn.setStyleSheet("font-size: 16px; font-weight: bold;")
            btn.clicked.connect(lambda _, c=char, b=btn: self.append_letter(c, b))
            self.letters_layout.addWidget(btn)

    def append_letter(self, char, btn):
        self.sc_input.setText(self.sc_input.text() + char)
        btn.setEnabled(False)

    def clear_spell_input(self):
        self.sc_input.clear()
        for i in range(self.letters_layout.count()):
            btn = self.letters_layout.itemAt(i).widget()
            if btn:
                btn.setEnabled(True)

    def verify_spell_check(self):
        word = self.words[self.current_word_idx]
        user_entry = self.sc_input.text().replace(" ", "").lower()
        target = self.target_spelling.replace(" ", "").lower()

        is_correct = user_entry == target
        self.db.update_stats(word["id"], is_correct)

        self.current_word_idx += 1
        if self.current_word_idx < len(self.words):
            self.show_spell_question()
        else:
            self.start_matching_exercise()

    # --- 5. MATCHING EXERCISE ---
    def setup_matching_view(self):
        view = QWidget()
        layout = QVBoxLayout(view)

        title = QLabel("Test 4/4: Match English Words to German")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold;")

        grid_layout = QHBoxLayout()

        self.eng_list_widget = QWidget()
        self.eng_layout = QVBoxLayout(self.eng_list_widget)

        self.deu_list_widget = QWidget()
        self.deu_layout = QVBoxLayout(self.deu_list_widget)

        grid_layout.addWidget(self.eng_list_widget)
        grid_layout.addWidget(self.deu_list_widget)

        layout.addWidget(title)
        layout.addLayout(grid_layout)

        self.stacked_widget.addWidget(view)

    def start_matching_exercise(self):
        self.selected_eng_btn = None
        self.selected_deu_btn = None
        self.matched_count = 0

        for l in [self.eng_layout, self.deu_layout]:
            for i in reversed(range(l.count())):
                w = l.itemAt(i).widget()
                if w:
                    w.setParent(None)

        self.pairs_eng = [
            (w["id"], w.get("translation", "")) for w in self.words
        ]
        self.pairs_deu = [
            (w["id"], self.get_full_german_word(w)) for w in self.words
        ]

        random.shuffle(self.pairs_eng)
        random.shuffle(self.pairs_deu)

        for w_id, txt in self.pairs_eng:
            btn = QPushButton(txt)
            btn.setStyleSheet("font-size: 14px; padding: 8px;")
            btn.clicked.connect(
                lambda _, b=btn, i=w_id: self.handle_match_select("eng", b, i)
            )
            self.eng_layout.addWidget(btn)

        for w_id, txt in self.pairs_deu:
            btn = QPushButton(txt)
            btn.setStyleSheet("font-size: 14px; padding: 8px;")
            btn.clicked.connect(
                lambda _, b=btn, i=w_id: self.handle_match_select("deu", b, i)
            )
            self.deu_layout.addWidget(btn)

        self.stacked_widget.setCurrentIndex(5)

    def handle_match_select(self, side, btn, word_id):
        if side == "eng":
            if self.selected_eng_btn:
                self.selected_eng_btn.setStyleSheet(
                    "font-size: 14px; padding: 8px;"
                )
            self.selected_eng_btn = btn
            self.selected_eng_id = word_id
            btn.setStyleSheet("font-size: 14px; padding: 8px; background-color: #3498db; color: white;")
        else:
            if self.selected_deu_btn:
                self.selected_deu_btn.setStyleSheet(
                    "font-size: 14px; padding: 8px;"
                )
            self.selected_deu_btn = btn
            self.selected_deu_id = word_id
            btn.setStyleSheet("font-size: 14px; padding: 8px; background-color: #3498db; color: white;")

        if self.selected_eng_btn and self.selected_deu_btn:
            if self.selected_eng_id == self.selected_deu_id:
                self.selected_eng_btn.setStyleSheet(
                    "background-color: #2ecc71; color: white;"
                )
                self.selected_deu_btn.setStyleSheet(
                    "background-color: #2ecc71; color: white;"
                )
                self.selected_eng_btn.setEnabled(False)
                self.selected_deu_btn.setEnabled(False)

                self.db.update_stats(self.selected_eng_id, is_correct=True)
                self.matched_count += 1
            else:
                self.selected_eng_btn.setStyleSheet(
                    "background-color: #e74c3c; color: white;"
                )
                self.selected_deu_btn.setStyleSheet(
                    "background-color: #e74c3c; color: white;"
                )
                self.db.update_stats(self.selected_eng_id, is_correct=False)

            self.selected_eng_btn = None
            self.selected_deu_btn = None

            if self.matched_count == len(self.words):
                self.show_summary()

    # --- 6. SUMMARY VIEW ---
    def setup_summary_view(self):
        view = QWidget()
        layout = QVBoxLayout(view)

        title = QLabel("Session Finished - Database Updated!")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #27ae60;")

        self.summary_table = QTableWidget()
        self.summary_table.setColumnCount(6)
        self.summary_table.setHorizontalHeaderLabels(
            ["ID", "CEFR", "German", "English", "Times Shown", "Times Wrong"]
        )
        self.summary_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )

        btn_restart = QPushButton("Main Menu / New Batch")
        btn_restart.setStyleSheet(
            "font-size: 16px; padding: 10px; background-color: #2980b9; color: white;"
        )
        btn_restart.clicked.connect(
            lambda: self.stacked_widget.setCurrentIndex(0)
        )

        layout.addWidget(title)
        layout.addWidget(self.summary_table)
        layout.addWidget(btn_restart)

        self.stacked_widget.addWidget(view)

    def show_summary(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        ids = tuple([w["id"] for w in self.words])
        placeholder = ",".join(["?"] * len(ids))
        cursor.execute(
            f"SELECT id, cefr_level, lemma, article, translation, times_shown, times_wrong FROM vocabulary WHERE id IN ({placeholder})",
            ids,
        )
        updated_records = cursor.fetchall()
        conn.close()

        self.summary_table.setRowCount(len(updated_records))
        for row_idx, record in enumerate(updated_records):
            word_dict = {"lemma": record["lemma"], "article": record["article"]}
            german_full = self.get_full_german_word(word_dict)

            self.summary_table.setItem(
                row_idx, 0, QTableWidgetItem(str(record["id"]))
            )
            self.summary_table.setItem(
                row_idx, 1, QTableWidgetItem(str(record["cefr_level"]))
            )
            self.summary_table.setItem(
                row_idx, 2, QTableWidgetItem(german_full)
            )
            self.summary_table.setItem(
                row_idx, 3, QTableWidgetItem(record["translation"])
            )
            self.summary_table.setItem(
                row_idx, 4, QTableWidgetItem(str(record["times_shown"]))
            )
            self.summary_table.setItem(
                row_idx, 5, QTableWidgetItem(str(record["times_wrong"]))
            )

        self.stacked_widget.setCurrentIndex(6)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GermanLearningApp()
    window.show()
    sys.exit(app.exec_())