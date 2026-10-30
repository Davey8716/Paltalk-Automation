"""Mic timer tab and its worker lifecycle."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ..worker import MicTimerWorker


class MicTimerTab(QWidget):
    def __init__(self, parent=None, is_closing=None):
        super().__init__(parent)
        self.is_closing = is_closing or (lambda: False)
        self.mic_timer_worker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(38, 10, 38, 32)
        layout.addWidget(QLabel('Time the person shown in Talking Now. Keep the room member list visible and unobscured.'))
        controls = QHBoxLayout()
        self.mic_timer_start = QPushButton('Start mic timer')
        self.mic_timer_stop = QPushButton('Stop mic timer')
        self.mic_timer_clear = QPushButton('Clear logs')
        self.mic_timer_stop.setEnabled(False)
        controls.addWidget(self.mic_timer_start)
        controls.addWidget(self.mic_timer_stop)
        controls.addWidget(self.mic_timer_clear)
        controls.addStretch()
        layout.addLayout(controls)
        self.mic_timer_status = QLabel('Start the timer to monitor the visible room.')
        self.mic_timer_status.setObjectName('micTimerStatus')
        self.mic_timer_status.setMinimumHeight(48)
        self.mic_timer_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.mic_timer_status.setWordWrap(True)
        layout.addWidget(self.mic_timer_status)
        self.mic_timer_rooms = {}
        self.mic_timer_logs = []
        columns = QHBoxLayout()
        for index in range(3):
            column = QVBoxLayout()
            column.addWidget(QLabel(f'Room {index + 1}'))
            log = QPlainTextEdit()
            log.setReadOnly(True)
            log.document().setMaximumBlockCount(2000)
            column.addWidget(log)
            self.mic_timer_logs.append(log)
            columns.addLayout(column)
        layout.addLayout(columns)
        self.mic_timer_start.clicked.connect(self.start_mic_timer)
        self.mic_timer_stop.clicked.connect(self.stop_mic_timer)
        self.mic_timer_clear.clicked.connect(self.clear_mic_timer_logs)

    def clear_mic_timer_logs(self):
        for log in self.mic_timer_logs:
            log.clear()

    def log_mic_timer_room(self, room, message):
        room = tuple(room)
        if room not in self.mic_timer_rooms:
            if len(self.mic_timer_rooms) >= len(self.mic_timer_logs):
                self.mic_timer_status.setText('More than three rooms detected; only the first three have logs. Restart the timer to reassign them.')
                return
            self.mic_timer_rooms[room] = len(self.mic_timer_rooms)
        self.mic_timer_logs[self.mic_timer_rooms[room]].appendPlainText(message)

    def start_mic_timer(self):
        if self.mic_timer_worker:
            return
        self.mic_timer_worker = MicTimerWorker()
        self.mic_timer_rooms.clear()
        for log in self.mic_timer_logs:
            log.appendPlainText('â€” New timer session â€”')
        self.mic_timer_worker.message.connect(self.mic_timer_status.setText)
        self.mic_timer_worker.room_message.connect(self.log_mic_timer_room)
        self.mic_timer_worker.finished.connect(self.mic_timer_finished)
        self.mic_timer_start.setEnabled(False)
        self.mic_timer_stop.setEnabled(True)
        self.mic_timer_status.setText('Mic timer started; waiting for a confirmed speaker.')
        self.mic_timer_worker.start()

    def stop_mic_timer(self):
        if self.mic_timer_worker:
            self.mic_timer_worker.requestInterruption()
            self.mic_timer_stop.setEnabled(False)

    def mic_timer_finished(self):
        self.mic_timer_worker = None
        self.mic_timer_start.setEnabled(not self.is_closing())
        self.mic_timer_stop.setEnabled(False)
        self.mic_timer_status.setText('Mic timer stopped.')

