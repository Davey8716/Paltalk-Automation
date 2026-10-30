"""Admin Actions tab and chat reader lifecycle."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from paltalk_automation import settings
from paltalk_automation.admin_actions.backend.chat_worker import ChatReaderWorker


class AdminActionsTab(QWidget):
    def __init__(self, parent=None, is_closing=None):
        super().__init__(parent)
        self.is_closing = is_closing or (lambda: False)
        self.chat_reader_worker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(38, 10, 38, 32)
        self.tray_status_label = QLabel('Start in tray: Off')
        layout.addWidget(self.tray_status_label, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(QLabel('Banned phrases'))
        layout.addWidget(QLabel('Add literal phrases to monitor. Double-click a phrase to edit it.'))
        self.admin_phrases = QListWidget()
        self.admin_phrases.setObjectName('adminPhrases')
        layout.addWidget(self.admin_phrases)
        entry = QHBoxLayout()
        self.admin_phrase_entry = QLineEdit()
        self.admin_phrase_entry.setPlaceholderText('Enter or paste a banned phrase, including emoji')
        add = QPushButton('Add')
        edit = QPushButton('Edit selected')
        remove = QPushButton('Remove selected')
        for widget in (self.admin_phrase_entry, add, edit, remove):
            entry.addWidget(widget)
        layout.addLayout(entry)
        save = QPushButton('Save phrases')
        save.setFixedSize(150,35)
        layout.addWidget(save)
        layout.addWidget(QLabel('Selected room chat'))
        self.admin_chat_log = QPlainTextEdit()
        self.admin_chat_log.setReadOnly(True)
        self.admin_chat_log.document().setMaximumBlockCount(2000)
        layout.addWidget(self.admin_chat_log)
        chat_controls = QHBoxLayout()
        self.admin_chat_start = QPushButton('Start reading chat')
        self.admin_chat_stop = QPushButton('Stop reading chat')
        self.admin_chat_stop.setEnabled(False)
        clear = QPushButton('Clear log')
        for button in (self.admin_chat_start, self.admin_chat_stop, clear):
            chat_controls.addWidget(button)
        chat_controls.addStretch()
        layout.addLayout(chat_controls)
        review_label = QLabel('Review mode: new phrase matches are logged for inspection; no users are bounced.')
        review_label.setWordWrap(True)
        layout.addWidget(review_label)
        self.admin_match_log = QPlainTextEdit()
        self.admin_match_log.setReadOnly(True)
        self.admin_match_log.document().setMaximumBlockCount(2000)
        layout.addWidget(self.admin_match_log)
        clear_matches = QPushButton('Clear matches')
        clear_matches.setFixedSize(150,35)
        for button in (self.admin_chat_start, self.admin_chat_stop, clear):
            button.setFixedSize(180, 35)
        layout.addWidget(clear_matches)
        try:
            for phrase in settings.load_admin_phrases():
                self.admin_phrases.addItem(phrase)
                item = self.admin_phrases.item(self.admin_phrases.count() - 1)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Admin actions', f'Could not load banned phrases: {exc}')
        add.clicked.connect(self.add_admin_phrase)
        self.admin_phrase_entry.returnPressed.connect(self.add_admin_phrase)
        edit.clicked.connect(self.edit_admin_phrase)
        remove.clicked.connect(self.remove_admin_phrase)
        save.clicked.connect(self.save_admin_phrases)
        self.admin_chat_start.clicked.connect(self.start_chat_reader)
        self.admin_chat_stop.clicked.connect(self.stop_chat_reader)
        clear.clicked.connect(self.admin_chat_log.clear)
        clear_matches.clicked.connect(self.admin_match_log.clear)

    def start_chat_reader(self):
        if self.chat_reader_worker is not None:
            return
        try:
            phrases = settings.load_admin_phrases()
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, 'Admin actions', f'Could not load banned phrases: {exc}')
            return
        self.chat_reader_worker = ChatReaderWorker(phrases)
        self.chat_reader_worker.message.connect(self.admin_chat_log.appendPlainText)
        self.chat_reader_worker.match.connect(self.admin_match_log.appendPlainText)
        self.admin_match_log.appendPlainText(f'Review mode started with {len(phrases)} saved phrases. Existing messages are ignored; no users will be bounced.')
        self.chat_reader_worker.finished.connect(self.chat_reader_finished)
        self.admin_chat_start.setEnabled(False)
        self.admin_chat_stop.setEnabled(True)
        self.chat_reader_worker.start()

    def stop_chat_reader(self):
        if self.chat_reader_worker:
            self.chat_reader_worker.requestInterruption()
            self.admin_chat_stop.setEnabled(False)

    def chat_reader_finished(self):
        self.chat_reader_worker = None
        self.admin_chat_start.setEnabled(not self.is_closing())
        self.admin_chat_stop.setEnabled(False)
        self.admin_chat_log.appendPlainText('Chat reader stopped.')

    def add_admin_phrase(self):
        phrase = self.admin_phrase_entry.text().strip()
        if not phrase:
            return
        if phrase.casefold() in {self.admin_phrases.item(i).text().strip().casefold()
                                for i in range(self.admin_phrases.count())}:
            QMessageBox.warning(self, 'Admin actions', 'That phrase is already in the list.')
            return
        self.admin_phrases.addItem(phrase)
        item = self.admin_phrases.item(self.admin_phrases.count() - 1)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        self.admin_phrases.setCurrentItem(item)
        self.admin_phrase_entry.clear()

    def edit_admin_phrase(self):
        item = self.admin_phrases.currentItem()
        if item:
            self.admin_phrases.editItem(item)

    def remove_admin_phrase(self):
        row = self.admin_phrases.currentRow()
        if row >= 0:
            item = self.admin_phrases.takeItem(row)
            if not self.save_admin_phrases():
                self.admin_phrases.insertItem(row, item)
                self.admin_phrases.setCurrentItem(item)

    def save_admin_phrases(self):
        phrases = [self.admin_phrases.item(i).text().strip() for i in range(self.admin_phrases.count())]
        if any(not phrase for phrase in phrases) or len({p.casefold() for p in phrases}) != len(phrases):
            QMessageBox.warning(self, 'Admin actions', 'Phrases cannot be empty or duplicated.')
            return False
        try:
            settings.save_admin_phrases(phrases)
            return True
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Admin actions', f'Could not save banned phrases: {exc}')
            return False

