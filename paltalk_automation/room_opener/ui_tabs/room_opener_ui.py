"""Room opener interface actions."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from paltalk_automation import settings
from paltalk_automation.room_opener.backend.room_workers import CloseAllRoomsWorker, CloseRoomWorker, RecentRoomsWorker, RoomStateWorker, RoomWorker


class RoomOpenerUi:
    AUTO_OPEN_DELAY_MS = 5000
    AUTO_OPEN_MAX_ATTEMPTS = 6

    def bind_room_widgets(self):
        self.auto_open_button = self.room_opener_tab.auto_open_button
        self.close_all_button = self.room_opener_tab.close_all_button
        self.delay = self.room_opener_tab.delay
        self.log = self.room_opener_tab.log
        self.mode_group = self.room_opener_tab.mode_group
        self.open_room_buttons = self.room_opener_tab.open_room_buttons
        self.other_rooms_layout = self.room_opener_tab.other_rooms_layout
        self.other_rooms_scroll = self.room_opener_tab.other_rooms_scroll
        self.recent_rooms_button = self.room_opener_tab.recent_rooms_button
        self.regular_button = self.room_opener_tab.regular_button
        self.room_labels = self.room_opener_tab.room_labels
        self.room_tray_status_label = self.room_opener_tab.room_tray_status_label
        self.rooms = self.room_opener_tab.rooms
        self.start_button = self.room_opener_tab.start_button
        self.vip_button = self.room_opener_tab.vip_button

    def initialize_room_state(self):
        self.worker = None
        self.close_room_worker = None
        self.closing_other_room = None
        self.closing_all_rooms = False
        self.room_state_worker = None
        self._pending_single_start = False
        self.recent_rooms_worker = None
        self.recent_rooms_manual_pending = False
        self.room_states = None
        self.other_open_names = []
        self.auto_open_pending = False
        self.auto_open_attempts_remaining = 0
        self.auto_open_handled_for_session = False

    def setup_room_controls(self):
        self.start_button.clicked.connect(self.toggle_opening)
        self.close_all_button.clicked.connect(self.close_all_rooms)
        self.recent_rooms_button.clicked.connect(self.show_recent_rooms)
        self.mode_group.buttonClicked.connect(self.room_mode_changed)
        self.load_saved_settings()
        for field in self.rooms:
            field.textEdited.connect(lambda _text, room=field: self.room_text_edited(room))
            field.editingFinished.connect(lambda room=field: self.finish_room_edit(room))
        self.delay.valueChanged.connect(lambda _value: self.save_current_settings(announce=False))
        self.update_room_limit_appearance()
        self.auto_open_button.toggled.connect(self.on_auto_open_toggled)

    def start_room_timers(self):
        self.room_state_timer = QTimer(self)
        self.room_state_timer.setInterval(3000)
        self.room_state_timer.timeout.connect(self.refresh_room_states)
        self.room_state_timer.start()
        self.refresh_room_states()
        self.recent_rooms_timer = QTimer(self)
        self.recent_rooms_timer.setInterval(1000)
        self.recent_rooms_timer.timeout.connect(self.refresh_recent_rooms)
        self.recent_rooms_timer.start()

    def room_paltalk_stopped(self):
        self.auto_open_pending = False
        self.auto_open_attempts_remaining = 0
        self.auto_open_handled_for_session = False

    def room_paltalk_running(self):
        if (self.auto_open_button.isChecked() and not self.auto_open_handled_for_session
                and not self.auto_open_pending and not self.worker):
            self.begin_automatic_opening("Waiting for Paltalk's Rooms view before opening rooms...")

    def room_mode_changed(self):
        self.update_room_limit_appearance()
        try:
            settings.save_room_mode(self.selected_mode())
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            QMessageBox.warning(self, "Settings", f"Could not save room mode: {exc}")


    def room_text_edited(self, field):
        for room in self.rooms:
            if room is field or room.property('roomDuplicate'):
                name = room.text().strip().casefold()
                duplicate = bool(name and any(other is not room and other.text().strip().casefold() == name
                                              for other in self.rooms))
                self.set_room_duplicate(room, duplicate)
        self.save_current_settings(announce=False)


    @staticmethod
    def set_room_duplicate(field, duplicate):
        if bool(field.property('roomDuplicate')) != duplicate:
            field.setProperty('roomDuplicate', duplicate)
            field.style().unpolish(field)
            field.style().polish(field)


    def finish_room_edit(self, field):
        name = field.text().strip()
        if name and any(other is not field and other.text().strip().casefold() == name.casefold()
                        for other in self.rooms):
            field.clear()
            self.set_room_duplicate(field, False)
            self.log.appendPlainText(f'Room "{name}" is already in the list; duplicate entry cleared.')
            self.save_current_settings(announce=False)


    @staticmethod
    def set_button_enabled(button, enabled):
        # Disabling a focused button otherwise moves focus to the next field.
        if not enabled and button.hasFocus():
            button.clearFocus()
        button.setEnabled(enabled)


    def update_room_buttons(self):
        single_room_action = bool(self.worker and getattr(self.worker, 'check_existing', False))
        for index, (field, button) in enumerate(zip(self.rooms, self.open_room_buttons)):
            name = field.text().strip()
            known = self.room_states is not None and name in self.room_states
            is_open = known and self.room_states[name]
            highlight_open = bool(is_open and field.property('roomAvailable') is not False)
            if field.property("roomOpen") != highlight_open:
                field.setProperty("roomOpen", highlight_open)
                field.style().unpolish(field)
                field.style().polish(field)
            action = "Close" if is_open else "Open"
            button.setText(action)
            button.setAccessibleName(f"{action} Room {index + 1}")
            button.setToolTip(f"{action} the Paltalk room in Room {index + 1}" if known else "Restore Paltalk and check the room before opening")
            self.set_button_enabled(button, bool(
                name and field.property('roomAvailable') is not False
                and (not self.worker or single_room_action) and (not self.close_room_worker or getattr(self, 'closing_other_room', None)
                                         or getattr(self, 'closing_all_rooms', False))
            ))
        if hasattr(self, 'other_rooms_layout'):
            self.update_other_rooms()
        if hasattr(self, 'close_all_button'):
            self.set_button_enabled(self.close_all_button, bool(
                self.room_states is not None
                and (any(self.room_states.get(field.text().strip(), False) for field in self.rooms if field.text().strip())
                     or bool(getattr(self, 'other_open_names', [])))
                and (not self.worker or single_room_action) and (not self.close_room_worker or getattr(self, 'closing_other_room', None)
                                         or getattr(self, 'closing_all_rooms', False))
            ))


    def update_other_rooms(self):
        configured = {field.text().strip() for field in self.rooms
                      if field.text().strip() and field.property('roomAvailable') is not False}
        names = list(dict.fromkeys(name for name in self.other_open_names if name not in configured))
        rows = {}
        while self.other_rooms_layout.count():
            row = self.other_rooms_layout.takeAt(0).widget()
            if row:
                rows[row.property('roomName')] = row
        for name in names:
            row = rows.pop(name, None)
            if row is None:
                row = QWidget()
                row.setProperty('roomName', name)
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                field = QLineEdit(name)
                field.setReadOnly(True)
                field.setProperty('roomOpen', True)
                button = QPushButton('Close')
                button.setAccessibleName(f'Close {name}')
                button.clicked.connect(lambda checked=False, room=name: self.close_other_room(room))
                row_layout.addWidget(field, 1)
                row_layout.addWidget(button)
            button = row.findChild(QPushButton)
            closing_name = getattr(self, 'closing_other_room', None)
            single_room_action = bool(self.worker and getattr(self.worker, 'check_existing', False))
            button.setEnabled((not self.worker or single_room_action) and (not self.close_room_worker or
                              bool(closing_name and closing_name != name) or
                              getattr(self, 'closing_all_rooms', False)))
            self.other_rooms_layout.addWidget(row)
        for row in rows.values():
            row.deleteLater()


    def reorder_rooms(self, source, destination):
        if source == destination or not (0 <= source < len(self.rooms) and 0 <= destination < len(self.rooms)):
            return
        names = [field.text() for field in self.rooms]
        if not names[source].strip():
            return
        names.insert(destination, names.pop(source))
        for field, name in zip(self.rooms, names):
            field.setText(name)
        self.save_current_settings()


    def selected_room_names(self):
        room_limit = 5 if self.selected_mode() == "vip" else 3
        return [field.text().strip() for field in self.rooms[:room_limit] if field.text().strip()]


    def update_room_limit_appearance(self):
        rooms_available = self.selected_mode() == "vip"
        for label, field in zip(self.room_labels[3:], self.rooms[3:]):
            label.setProperty("roomAvailable", rooms_available)
            field.setProperty("roomAvailable", rooms_available)
            label.style().unpolish(label)
            label.style().polish(label)
            field.style().unpolish(field)
            field.style().polish(field)
        self.update_room_buttons()



    def show_recent_rooms(self):
        self.log.setFocus(Qt.FocusReason.OtherFocusReason)
        if self.recent_rooms_worker:
            if self.recent_rooms_worker.automatic:
                self.recent_rooms_manual_pending = True
                self.recent_rooms_button.setEnabled(False)
            return
        self.recent_rooms_button.setEnabled(False)
        self.start_recent_rooms_scan(automatic=False)


    def refresh_recent_rooms(self):
        if (self._quitting or not self.paltalk_was_running or self.recent_rooms_worker
                or self.worker or self.close_room_worker or self.room_state_worker):
            return
        self.start_recent_rooms_scan(automatic=True)


    def start_recent_rooms_scan(self, automatic):
        self.recent_rooms_worker = RecentRoomsWorker(automatic=automatic)
        self.recent_rooms_worker.result.connect(self.recent_rooms_received)
        self.recent_rooms_worker.finished.connect(self.recent_rooms_finished)
        self.recent_rooms_worker.start()


    def recent_rooms_finished(self):
        self.recent_rooms_worker = None
        if self.recent_rooms_manual_pending and not self._quitting:
            self.recent_rooms_manual_pending = False
            self.start_recent_rooms_scan(automatic=False)
            return
        self.recent_rooms_button.setEnabled(True)


    def recent_rooms_received(self, names, error):
        automatic = self.recent_rooms_worker and self.recent_rooms_worker.automatic
        if automatic:
            if not error and names:
                try:
                    settings.merge_recent_rooms(names)
                except (OSError, ValueError, TypeError) as exc:
                    self.log.appendPlainText(f'Could not save recently visited rooms: {exc}')
            return
        scanned_names = names
        try:
            names = settings.load_recent_rooms() if error else settings.merge_recent_rooms(names)
            if not error:
                names = list(dict.fromkeys([*(name for name in scanned_names if name in names), *names]))
        except (OSError, ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Recently visited", f"Could not read or save recent rooms: {exc}")
            return
        if error and not names:
            QMessageBox.warning(self, "Recently visited", error)
        dialog = QDialog(self)
        dialog.setWindowTitle("Recently visited rooms")
        font = dialog.font()
        font.setBold(True)
        dialog.setFont(font)
        dialog.resize(560, 400)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Select a room and click Copy, or double-click its name."))
        alphabetical = QPushButton('Alphabetical')
        alphabetical.setFixedSize(150,35)
        alphabetical.setCheckable(True)
        try:
            alphabetical.setChecked(bool(settings.load_app_state().get('recent_rooms_alphabetical', False)))
        except (OSError, ValueError, TypeError) as exc:
            self.log.appendPlainText(f'Could not load app state: {exc}')
        layout.addWidget(alphabetical)
        rooms = QListWidget()
        rooms.setStyleSheet('QListWidget { font-weight: bold; }')
        rooms.addItems(sorted(names, key=str.casefold) if alphabetical.isChecked() else names)
        layout.addWidget(rooms)
        if not names:
            layout.addWidget(QLabel("No recently visited rooms have been saved."))
        copy_button = QPushButton("Copy selected name")
        copy_button.setFixedSize(200,35)
        copy_button.setEnabled(False)
        def change_sort(enabled):
            try:
                if enabled:
                    settings.sort_recent_rooms()
                settings.save_app_state(recent_rooms_alphabetical=enabled)
            except (OSError, ValueError, TypeError) as exc:
                alphabetical.blockSignals(True)
                alphabetical.setChecked(not enabled)
                alphabetical.blockSignals(False)
                QMessageBox.warning(dialog, 'Recently visited', f'Could not save sort preference or room order: {exc}')
                return
            selected = rooms.currentItem().text() if rooms.currentItem() else None
            rooms.clear()
            rooms.addItems(sorted(names, key=str.casefold) if enabled else names)
            if selected is not None:
                matches = rooms.findItems(selected, Qt.MatchFlag.MatchExactly)
                if matches:
                    rooms.setCurrentItem(matches[0])
            copy_button.setEnabled(rooms.currentItem() is not None)
        alphabetical.toggled.connect(change_sort)
        feedback_timer = QTimer(dialog)
        feedback_timer.setSingleShot(True)
        def clear_copy_feedback():
            copy_button.setText("Copy selected name")
            copy_button.setStyleSheet("")
        feedback_timer.timeout.connect(clear_copy_feedback)
        rooms.itemClicked.connect(lambda item: copy_button.setEnabled(True))
        def copy_item(item):
            if item:
                copy_button.setEnabled(True)
                QApplication.clipboard().setText(item.text())
                copy_button.setText("Copied!")
                copy_button.setStyleSheet("QPushButton { background: #258c5a; color: white; }")
                feedback_timer.start(1200)
        copy_button.clicked.connect(lambda: copy_item(rooms.currentItem()))
        rooms.itemDoubleClicked.connect(copy_item)
        layout.addWidget(copy_button)
        dialog.exec()


    def load_saved_settings(self):
        try:
            data = settings.load_settings()
            saved_rooms = data.get("rooms", {})
            if isinstance(saved_rooms, list):
                saved_rooms = {
                    f"room_{index}": value
                    for index, value in enumerate(saved_rooms, start=1)
                }
            seen = set()
            for index, field in enumerate(self.rooms, start=1):
                name = str(saved_rooms.get(f"room_{index}", ""))
                key = name.strip().casefold()
                if key and key in seen:
                    self.log.appendPlainText(f"Room {index} was cleared because its name duplicates another saved room.")
                    name = ''
                elif key:
                    seen.add(key)
                field.setText(name)
            self.delay.setValue(float(data.get("delay", 5)))
            (self.vip_button if data.get("mode") == "vip" else self.regular_button).setChecked(True)
            self.auto_open_button.setChecked(bool(data.get("open_on_paltalk_start", False)))
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.log.appendPlainText(f"Could not load settings: {exc}")


    def save_current_settings(self, announce=True):
        names = [field.text().strip().casefold() for field in self.rooms if field.text().strip()]
        if len(names) != len(set(names)):
            if announce:
                self.log.appendPlainText('Each configured room must have a different name.')
            return False
        try:
            settings.save_settings(
                [field.text() for field in self.rooms], self.delay.value(), self.selected_mode(),
                self.auto_open_button.isChecked(),
            )
            if announce:
                self.log.appendPlainText("Settings saved.")
            return True
        except OSError as exc:
            QMessageBox.warning(self, "Settings", f"Could not save settings: {exc}")
            return False


    def toggle_opening(self):
        if self.worker:
            self.stop()
        else:
            self.start()


    def start(self, automatic=False):
        mode = self.selected_mode()
        names = self.selected_room_names()
        if not names:
            if automatic:
                self.log.appendPlainText("Automatic opening skipped: no room names are configured.")
                self.auto_open_pending = False
                self.auto_open_handled_for_session = True
            else:
                QMessageBox.warning(self, "No rooms", "Enter at least one room name.")
            return
        self.start_room_worker(names, automatic, f"{mode.title()} room opener with {len(names)} populated room(s)")


    def open_configured_room(self, index):
        name = self.rooms[index].text().strip()
        if not name:
            self.log.appendPlainText(f"Enter a room name in Room {index + 1} before opening it.")
            return
        self.start_room_worker([name], False, f"room: {name}", check_existing=True)


    def start_room_worker(self, names, automatic, description, check_existing=False):
        if self.worker or self.close_room_worker or not self.save_current_settings():
            return
        if not automatic:
            self.auto_open_pending = False
            self.auto_open_attempts_remaining = 0
            self.auto_open_handled_for_session = True
        self.worker = RoomWorker(names, self.delay.value(), automatic=automatic, check_existing=check_existing)
        self.worker.message.connect(self.log.appendPlainText)
        if automatic:
            self.worker.completed.connect(self.automatic_open_finished)
        self.worker.finished.connect(self.finished)
        self.start_button.setText("Stop")
        self.start_button.setEnabled(True)
        if not check_existing:
            for button in self.open_room_buttons:
                self.set_button_enabled(button, False)
            self.set_button_enabled(self.close_all_button, False)
        prefix = "Automatically starting" if automatic else "Starting"
        self.log.appendPlainText(f"{prefix} {description}...")
        if (check_existing or automatic) and self.room_state_worker:
            self._pending_single_start = True
            self.room_state_worker.requestInterruption()
            self.log.appendPlainText('Waiting for the room-status scan to stop...')
        else:
            self.worker.start()


    def on_auto_open_toggled(self, enabled):
        self.save_current_settings()
        if enabled:
            self.auto_open_handled_for_session = False
            self.paltalk_startup.check()
        else:
            self.auto_open_pending = False
            self.auto_open_attempts_remaining = 0


    def begin_automatic_opening(self, message):
        self.auto_open_pending = True
        self.auto_open_attempts_remaining = self.AUTO_OPEN_MAX_ATTEMPTS
        self.log.appendPlainText(message)
        QTimer.singleShot(self.AUTO_OPEN_DELAY_MS, self.start_automatically)


    def start_automatically(self):
        if not self.auto_open_pending:
            return
        if self.auto_open_button.isChecked() and self.paltalk_was_running and not self.worker:
            self.auto_open_attempts_remaining -= 1
            self.start(automatic=True)
        else:
            self.auto_open_pending = False
            self.auto_open_attempts_remaining = 0


    def automatic_open_finished(self, queued_room_count):
        if not self.auto_open_pending:
            return
        if queued_room_count > 0 or queued_room_count == RoomWorker.ALREADY_OPEN:
            self.auto_open_pending = False
            self.auto_open_attempts_remaining = 0
            self.auto_open_handled_for_session = True
            self.log.appendPlainText("Automatic opening completed for this Paltalk session.")
            return
        if self.auto_open_attempts_remaining > 0 and self.auto_open_button.isChecked():
            attempt = self.AUTO_OPEN_MAX_ATTEMPTS - self.auto_open_attempts_remaining + 1
            reason = ("Room status is unavailable" if queued_room_count == RoomWorker.STATE_UNAVAILABLE
                      else "Rooms view is not ready yet")
            self.log.appendPlainText(f"{reason}. Retrying automatic opening ({attempt}/{self.AUTO_OPEN_MAX_ATTEMPTS})...")
            QTimer.singleShot(self.AUTO_OPEN_DELAY_MS, self.start_automatically)
        else:
            self.auto_open_pending = False
            self.auto_open_handled_for_session = True
            reason = ("room status remained unavailable" if queued_room_count == RoomWorker.STATE_UNAVAILABLE
                      else "no configured room tiles became available")
            self.log.appendPlainText(f"Automatic opening stopped: {reason}.")


    def selected_mode(self):
        return "vip" if self.vip_button.isChecked() else "regular"


    def refresh_room_states(self):
        if (self.room_state_worker or self._quitting or self.close_room_worker or
                getattr(self, 'recent_rooms_worker', None) or
                (self.worker and (getattr(self.worker, 'check_existing', False) or getattr(self.worker, 'automatic', False)))):
            return
        self.room_state_worker = RoomStateWorker([field.text().strip() for field in self.rooms])
        self.room_state_worker.result.connect(self.room_states_received)
        self.room_state_worker.message.connect(self.log.appendPlainText)
        self.room_state_worker.finished.connect(self.room_state_finished)
        self.room_state_worker.start()


    def room_states_received(self, states):
        if self.worker and getattr(self.worker, 'check_existing', False):
            return
        if not self.close_room_worker and states is not None:
            if isinstance(states, dict) and 'states' in states and 'open_names' in states:
                self.room_states = states['states']
                self.other_open_names = states['open_names']
            else:
                self.room_states = states
        self.update_room_buttons()


    def room_state_finished(self):
        self.room_state_worker = None
        if self._pending_single_start:
            self._pending_single_start = False
            if self.worker and not self._quitting:
                self.worker.start()
            else:
                self.worker = None


    def close_other_room(self, name):
        if self.worker or self.close_room_worker:
            return
        self.closing_other_room = name
        self.close_room_worker = CloseRoomWorker(name)
        self.close_room_worker.message.connect(self.log.appendPlainText)
        self.close_room_worker.finished.connect(self.close_room_finished)
        self.update_room_buttons()
        self.close_room_worker.start()


    def toggle_configured_room(self, index):
        self.open_configured_room(index)


    def close_configured_room(self, index):
        name = self.rooms[index].text().strip()
        if not name:
            self.log.appendPlainText(f"Enter a room name in Room {index + 1} before closing it.")
            return
        if self.close_room_worker:
            return
        self.close_room_worker = CloseRoomWorker(name)
        self.close_room_worker.message.connect(self.log.appendPlainText)
        self.close_room_worker.finished.connect(self.close_room_finished)
        self.set_button_enabled(self.start_button, False)
        self.update_room_buttons()
        self.close_room_worker.start()


    def close_all_rooms(self):
        if self.worker or self.close_room_worker:
            return
        names = list(dict.fromkeys(
            field.text().strip() for field in self.rooms
            if field.text().strip()
        ))
        names = list(dict.fromkeys(names + getattr(self, 'other_open_names', [])))
        if not names:
            return
        self.auto_open_pending = False
        self.auto_open_attempts_remaining = 0
        self.auto_open_handled_for_session = True
        self.closing_all_rooms = True
        self.close_room_worker = CloseAllRoomsWorker(names)
        self.close_room_worker.message.connect(self.log.appendPlainText)
        self.close_room_worker.finished.connect(self.close_room_finished)
        self.update_room_buttons()
        self.log.appendPlainText("Restoring Paltalk and checking open rooms...")
        self.close_room_worker.start()


    def close_room_finished(self):
        self.close_room_worker = None
        self.closing_other_room = None
        self.closing_all_rooms = False
        self.start_button.setEnabled(True)
        self.update_room_buttons()
        self.refresh_room_states()


    def stop(self):
        self.auto_open_pending = False
        self.auto_open_attempts_remaining = 0
        self.auto_open_handled_for_session = True
        if self.worker:
            if self._pending_single_start:
                self._pending_single_start = False
                self.log.appendPlainText('Stopped before opening the room.')
                self.finished()
                return
            self.worker.requestInterruption()
            self.start_button.setEnabled(False)
            self.log.appendPlainText("Stopping after the current operation...")


    def finished(self):
        self.start_button.setText("Open rooms")
        self.start_button.setEnabled(True)
        self.worker = None
        self.update_room_buttons()
        self.refresh_room_states()


