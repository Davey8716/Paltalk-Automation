"""Camera opener interface and actions."""

from pathlib import Path
import re

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFileDialog, QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QMenu, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QStyle, QVBoxLayout, QWidget)

from paltalk_automation import settings
from paltalk_automation.camera_opener.ui_tabs.manual_camera_prompt import ManualCameraPromptController
from paltalk_automation.camera_opener.ui_tabs.camera_entry_field import CameraEntryField
from paltalk_automation.camera_opener.ui_tabs.text_import_button import TextImportButton
from paltalk_automation.camera_opener.ui_tabs.camera_name_list import CameraNameDelegate, CameraNameList, LIVE_ROLE
from paltalk_automation.camera_opener.backend.camera_worker import CameraWorker


class CameraOpenerUi:
    def initialize_camera_state(self):
        self.camera_worker = None
        self.camera_prompts = ManualCameraPromptController(self)
        self.camera_restart_pending = False
        self.camera_auto_handled = False

    def create_camera_tab(self, tabs):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(38, 10, 38, 32)
        self.camera_tray_status_label = QLabel('Start in tray: Off')
        layout.addWidget(self.camera_tray_status_label, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addWidget(QLabel('Monitor up to 200 usernames in the visible On Cam list of the rooms you enter.\n' \
        'This is a global camera monitor across rooms and is not room specific.'))
        sort_controls = QHBoxLayout()
        sort_controls.addStretch()
        self.camera_alphabetical = QPushButton('Alphabetical')
        self.camera_alphabetical.setObjectName('cameraAlphabetical')
        self.camera_alphabetical.setCheckable(True)
        sort_controls.addWidget(self.camera_alphabetical)
        self.camera_import = TextImportButton('Import text')
        self.camera_import.setToolTip('Click or drop a text file to import usernames, one per line.')
        sort_controls.addWidget(self.camera_import)
        self.camera_export = QPushButton('Export to text')
        self.camera_export.setToolTip('Export the camera usernames to a text file.')
        self.camera_export_glow = QGraphicsDropShadowEffect(self.camera_export)
        self.camera_export_glow.setColor(QColor('#00cfff'))
        self.camera_export_glow.setBlurRadius(24)
        self.camera_export_glow.setOffset(0, 0)
        self.camera_export_glow.setEnabled(False)
        self.camera_export.setGraphicsEffect(self.camera_export_glow)
        self.camera_export_flash = QTimer(self)
        self.camera_export_flash.setInterval(2000)
        self.camera_export_flash.timeout.connect(self.flash_camera_export)
        self.camera_export_flashes_left = 0
        sort_controls.addWidget(self.camera_export)
        layout.addLayout(sort_controls)
        self.camera_names = CameraNameList()
        self.camera_next_order = 1
        self.camera_names.setItemDelegate(CameraNameDelegate(self.camera_names))
        self.camera_names.setObjectName('cameraNames')
        self.camera_names.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.camera_names.customContextMenuRequested.connect(self.camera_name_menu)
        self.camera_names.deleteRequested.connect(self.remove_camera_name)
        self.camera_names.setToolTip('A green dot marks a live camera detected in the visible room while monitoring. Drag to select usernames; press Delete or Remove selected to remove them.')
        self.camera_names_scroll = QScrollArea()
        self.camera_names_scroll.setWidgetResizable(True)
        self.camera_names_scroll.setWidget(self.camera_names)
        layout.addWidget(self.camera_names_scroll, 2)
        entry = QHBoxLayout()
        self.camera_entry = CameraEntryField()
        self.camera_entry.setPlaceholderText('Exact Paltalk username')
        add = QPushButton('Add')
        remove = QPushButton('Remove selected')
        entry.addWidget(self.camera_entry)
        entry.addWidget(add)
        entry.addWidget(remove)
        layout.addLayout(entry)
        controls = QHBoxLayout()
        self.camera_auto = QPushButton('Start when Paltalk starts')
        self.camera_auto.setObjectName('autoOpenButton')
        self.camera_auto.setCheckable(True)
        
        self.camera_start = QPushButton('Start')
        self.camera_stop = QPushButton('Stop')
        self.camera_portrait_adjustment = QPushButton()
        self.camera_portrait_adjustment.setObjectName('autoOpenButton')
        self.camera_portrait_adjustment.setCheckable(True)
        self.camera_portrait_adjustment.setChecked(True)
        self.camera_portrait_adjustment.setText('Portrait adjustment: On')

        
        self.camera_stop.setEnabled(False)
        for button in (self.camera_auto, self.camera_start, self.camera_stop, self.camera_portrait_adjustment):
            button.setFixedSize(200, 35)
            controls.addWidget(button)
        self.camera_start.setFixedSize(150, 35)
        self.camera_stop.setFixedSize(150, 35)
        controls.addStretch()
        layout.addLayout(controls)
        self.camera_manual_prompt = QPushButton('Prompt to add manually opened cameras: Off')
        self.camera_manual_prompt.setObjectName('autoOpenButton')
        self.camera_manual_prompt.setCheckable(True)
        self.camera_manual_prompt.setToolTip('While monitoring, prompt to add newly opened cameras in the visible room.')
        layout.addWidget(self.camera_manual_prompt, alignment=Qt.AlignmentFlag.AlignLeft)
        output = QHBoxLayout()

        def clear_log_button(label):
            button = QPushButton()
            button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
            button.setIconSize(QSize(16, 16))
            button.setFixedSize(28, 28)
            button.setStyleSheet('padding: 0;')
            button.setToolTip(f'Clear {label} log')
            button.setAccessibleName(f'Clear {label} log')
            return button

        invoked_column = QVBoxLayout()
        invoked_header = QHBoxLayout()
        invoked_header.addWidget(QLabel('Opened Cameras'))
        invoked_clear = clear_log_button('Opened Cameras')
        invoked_header.addWidget(invoked_clear)
        invoked_column.addLayout(invoked_header)
        self.camera_invoked_log = QPlainTextEdit()
        self.camera_invoked_log.setReadOnly(True)
        invoked_clear.clicked.connect(self.camera_invoked_log.clear)
        invoked_column.addWidget(self.camera_invoked_log)
        output.addLayout(invoked_column, 1)
        failed_column = QVBoxLayout()
        failed_header = QHBoxLayout()
        failed_header.addWidget(QLabel('Could not open'))
        failed_clear = clear_log_button('Could not open')
        failed_header.addWidget(failed_clear)
        failed_column.addLayout(failed_header)
        self.camera_failed_log = QPlainTextEdit()
        self.camera_failed_log.setReadOnly(True)
        failed_clear.clicked.connect(self.camera_failed_log.clear)
        failed_column.addWidget(self.camera_failed_log)
        output.addLayout(failed_column, 1)
        activity_column = QVBoxLayout()
        activity_header = QHBoxLayout()
        activity_header.addWidget(QLabel('Other activity'))
        activity_clear = clear_log_button('Other activity')
        activity_header.addWidget(activity_clear)
        activity_column.addLayout(activity_header)
        self.camera_log = QPlainTextEdit()
        self.camera_log.setReadOnly(True)
        activity_clear.clicked.connect(self.camera_log.clear)
        activity_column.addWidget(self.camera_log)
        output.addLayout(activity_column, 1)
        layout.addLayout(output, 1)
        tabs.addTab(page, 'Camera Opener')
        try:
            data = settings.load_camera_settings()
            names = data.get('usernames', [])
            if isinstance(names, list):
                numbers = data.get('username_numbers', [])
                valid_numbers = (isinstance(numbers, list) and len(numbers) == len(names)
                                 and all(type(n) is int and n > 0 for n in numbers)
                                 and len(set(numbers)) == len(numbers))
                for index, name in enumerate(names):
                    if not isinstance(name, str) or not name.strip():
                        continue
                    self.camera_names.addItem(name)
                    item = self.camera_names.item(self.camera_names.count() - 1)
                    item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                    number = numbers[index] if valid_numbers else index + 1
                    item.setData(Qt.ItemDataRole.UserRole, number)
                    self.camera_next_order = max(self.camera_next_order, number + 1)
                self.renumber_camera_names()
            manual_prompt = data.get('manual_camera_prompt', False)
            self.camera_manual_prompt.setChecked(manual_prompt if type(manual_prompt) is bool else False)
            self.camera_manual_prompt.setText('Prompt to add manually opened cameras: ' + ('On' if self.camera_manual_prompt.isChecked() else 'Off'))
            self.camera_auto.setChecked(bool(data.get('start_on_paltalk', False)))
            portrait_adjustment = data.get('portrait_adjustment', True)
            self.camera_portrait_adjustment.setChecked(portrait_adjustment if type(portrait_adjustment) is bool else True)
            self.camera_portrait_adjustment.setText(
                'Portrait adjustment: On' if self.camera_portrait_adjustment.isChecked() else 'Portrait adjustment: Off')
            self.camera_alphabetical.setChecked(bool(data.get('alphabetical', False)))
            if self.camera_alphabetical.isChecked():
                self.sort_camera_names(True)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            self.camera_log.appendPlainText(f'Could not load camera settings: {exc}')
        add.clicked.connect(self.add_camera_name)
        self.camera_import.clicked.connect(self.import_camera_names)
        self.camera_import.fileDropped.connect(self.import_camera_file)
        self.camera_export.clicked.connect(self.export_camera_names)
        self.camera_alphabetical.toggled.connect(self.camera_alphabetical_changed)
        self.camera_names.itemChanged.connect(self.camera_name_changed)
        self.camera_entry.textChanged.connect(self.update_camera_duplicate)
        model = self.camera_names.model()
        model.rowsInserted.connect(self.update_camera_duplicate)
        model.rowsRemoved.connect(self.update_camera_duplicate)
        model.dataChanged.connect(self.update_camera_duplicate)
        self.camera_entry.returnPressed.connect(self.add_camera_name)
        remove.clicked.connect(self.remove_camera_name)
        self.camera_auto.toggled.connect(self.camera_auto_changed)
        self.camera_portrait_adjustment.toggled.connect(self.camera_portrait_adjustment_changed)
        self.camera_manual_prompt.toggled.connect(self.camera_manual_prompt_changed)
        self.camera_start.clicked.connect(self.start_cameras)
        self.camera_stop.clicked.connect(self.stop_cameras)


    def update_camera_duplicate(self, *_args):
        name = self.camera_entry.text().strip().casefold()
        duplicate = bool(name and any(
            self.camera_names.item(i).text().strip().casefold() == name
            for i in range(self.camera_names.count())
        ))
        self.camera_entry.set_duplicate(duplicate)


    def camera_username_list(self):
        items = [self.camera_names.item(i) for i in range(self.camera_names.count())]
        return [item.text().strip() for item in sorted(items, key=lambda item: item.data(Qt.ItemDataRole.UserRole))]


    def renumber_camera_names(self):
        items = sorted((self.camera_names.item(i) for i in range(self.camera_names.count())),
                       key=lambda item: item.data(Qt.ItemDataRole.UserRole))
        signals_blocked = self.camera_names.blockSignals(True)
        try:
            for number, item in enumerate(items, 1):
                item.setData(Qt.ItemDataRole.UserRole, number)
        finally:
            self.camera_names.blockSignals(signals_blocked)
        self.camera_next_order = len(items) + 1


    def import_camera_names(self):
        filename, _ = QFileDialog.getOpenFileName(self, 'Import usernames', '', 'Text files (*.txt);;All files (*)')
        if not filename:
            return
        CameraOpenerUi.import_camera_file(self, filename)


    def import_camera_file(self, filename):
        try:
            lines = Path(filename).read_text(encoding='utf-8-sig').splitlines()
        except (OSError, UnicodeError) as exc:
            QMessageBox.warning(self, 'Import usernames', f'Could not read usernames: {exc}')
            return
        existing = {self.camera_names.item(i).text().strip().casefold() for i in range(self.camera_names.count())}
        names = []
        for line in lines:
            name = re.sub(r'^\s*\d+\.\s+', '', line).strip()
            if name and name.casefold() not in existing:
                names.append(name)
                existing.add(name.casefold())
        if self.camera_names.count() + len(names) > 200:
            QMessageBox.warning(self, 'Import usernames', 'Import would exceed the 200 username limit. No usernames were added.')
            return
        if not names:
            QMessageBox.information(self, 'Import usernames', 'No new usernames were found.')
            return
        previous_order = self.camera_next_order
        added = []
        blocked = self.camera_names.blockSignals(True)
        try:
            for name in names:
                self.camera_names.addItem(name)
                item = self.camera_names.item(self.camera_names.count() - 1)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, self.camera_next_order)
                self.camera_next_order += 1
                added.append(item)
            if self.camera_alphabetical.isChecked():
                self.sort_camera_names(True)
        finally:
            self.camera_names.blockSignals(blocked)
        if not self.save_camera_settings():
            for item in added:
                self.camera_names.takeItem(self.camera_names.row(item))
            self.camera_next_order = previous_order
            return
        if self.camera_worker:
            self.camera_worker.update_names(self.camera_username_list())
        self.remind_camera_export()
        self.camera_log.appendPlainText(f'Imported {len(names)} username(s).')


    def export_camera_names(self):
        names = [(self.camera_names.item(i).data(Qt.ItemDataRole.UserRole) or i + 1,
                  self.camera_names.item(i).text().strip()) for i in range(self.camera_names.count())]
        names = [(number, name) for number, name in names if name]
        if not names:
            QMessageBox.information(self, 'Export usernames', 'There are no usernames to export.')
            return
        filename, _ = QFileDialog.getSaveFileName(
            self, 'Export usernames', 'camera-usernames.txt', 'Text files (*.txt)')
        if not filename:
            return
        try:
            Path(filename).write_text(''.join(f'{number}. {name}\n' for number, name in names),
                                      encoding='utf-8')
        except OSError as exc:
            QMessageBox.warning(self, 'Export usernames', f'Could not export usernames: {exc}')
        else:
            self.clear_camera_export_reminder()


    def flash_camera_export(self):
        highlighted = not self.camera_export.property('exportHighlight')
        self.camera_export.setProperty('exportHighlight', self.camera_export_flash_color if highlighted else '')
        self.camera_export_glow.setEnabled(highlighted)
        self.camera_export.style().unpolish(self.camera_export)
        self.camera_export.style().polish(self.camera_export)
        self.camera_export.update()
        self.camera_export_flashes_left -= 1
        if self.camera_export_flashes_left <= 0:
            self.camera_export_flash.stop()


    def remind_camera_export(self, color='green'):
        self.camera_export.setToolTip('Usernames have changed. Export to text to save an updated list.')
        self.camera_export_flash.stop()
        self.camera_export.setProperty('exportHighlight', '')
        self.camera_export_glow.setEnabled(False)
        self.camera_export_flash_color = color
        self.camera_export_glow.setColor(QColor('#20c86a' if color == 'green' else '#ed4b4b'))
        self.camera_export_flashes_left = 2
        self.flash_camera_export()
        self.camera_export_flash.start()


    def clear_camera_export_reminder(self):
        self.camera_export_flash.stop()
        self.camera_export.setProperty('exportHighlight', '')
        self.camera_export_glow.setEnabled(False)
        self.camera_export.style().unpolish(self.camera_export)
        self.camera_export.style().polish(self.camera_export)
        self.camera_export.update()
        self.camera_export.setToolTip('Export the camera usernames to a text file.')


    def sort_camera_names(self, alphabetical):
        items = [self.camera_names.takeItem(0) for _ in range(self.camera_names.count())]
        if alphabetical:
            items.sort(key=lambda item: (item.text().casefold(), item.data(Qt.ItemDataRole.UserRole)))
        else:
            items.sort(key=lambda item: item.data(Qt.ItemDataRole.UserRole))
        for item in items:
            self.camera_names.addItem(item)


    def camera_name_changed(self, _item):
        blocked = self.camera_names.blockSignals(True)
        try:
            _item.setData(LIVE_ROLE, False)
        finally:
            self.camera_names.blockSignals(blocked)
        if self.camera_alphabetical.isChecked():
            self.sort_camera_names(True)
        self.update_camera_names()


    def update_camera_names(self):
        if self.save_camera_settings() and self.camera_worker:
            self.camera_worker.update_names(self.camera_username_list())


    def update_camera_live_status(self, names):
        live = {name.strip().casefold() for name in names}
        blocked = self.camera_names.blockSignals(True)
        try:
            for i in range(self.camera_names.count()):
                item = self.camera_names.item(i)
                is_live = item.text().strip().casefold() in live
                if bool(item.data(LIVE_ROLE)) != is_live:
                    item.setData(LIVE_ROLE, is_live)
        finally:
            self.camera_names.blockSignals(blocked)


    def camera_alphabetical_changed(self, enabled):
        self.sort_camera_names(enabled)
        self.save_camera_settings()


    def add_camera_name(self):
        name = self.camera_entry.text().strip()
        CameraOpenerUi.add_camera_username(self, name, clear_entry=True)


    def add_camera_username(self, name, clear_entry=False):
        name = name.strip()
        if name and name.casefold() not in {n.casefold() for n in self.camera_username_list()}:
            if self.camera_names.count() >= 200:
                QMessageBox.warning(self, 'Camera usernames', 'The list can contain up to 200 usernames.')
                return
            self.camera_names.blockSignals(True)
            self.camera_names.addItem(name)
            item = self.camera_names.item(self.camera_names.count() - 1)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            item.setData(Qt.ItemDataRole.UserRole, self.camera_next_order)
            self.camera_next_order += 1
            self.camera_names.blockSignals(False)
            if self.camera_alphabetical.isChecked():
                self.sort_camera_names(True)
            self.camera_names.setCurrentItem(item)
            self.camera_names.scrollToItem(item)
            self.camera_names_scroll.ensureVisible(0, self.camera_names.visualItemRect(item).center().y())
            if clear_entry:
                self.camera_entry.clear()
            self.update_camera_names()
            self.remind_camera_export()


    def remove_camera_name(self):
        items = self.camera_names.selectedItems()
        if items:
            self.delete_camera_names(items)


    def camera_name_menu(self, position):
        item = self.camera_names.itemAt(position)
        if item is None:
            return
        menu = QMenu(self.camera_names)
        items = self.camera_names.selectedItems() if item.isSelected() else [item]
        delete_action = menu.addAction('Delete selected usernames' if len(items) > 1 else 'Delete username')
        if menu.exec(self.camera_names.viewport().mapToGlobal(position)) == delete_action:
            self.delete_camera_names(items)


    def delete_camera_name(self, item):
        CameraOpenerUi.delete_camera_names(self, [item])


    def delete_camera_names(self, items):
        rows = sorted(self.camera_names.row(item) for item in items if self.camera_names.row(item) >= 0)
        if not rows:
            return
        old_numbers = [(self.camera_names.item(i), self.camera_names.item(i).data(Qt.ItemDataRole.UserRole))
                       for i in range(self.camera_names.count())]
        old_next_order = self.camera_next_order
        removed = [(row, self.camera_names.takeItem(row)) for row in reversed(rows)]
        self.renumber_camera_names()
        if not self.save_camera_settings():
            for row, item in reversed(removed):
                self.camera_names.insertItem(row, item)
                item.setSelected(True)
            signals_blocked = self.camera_names.blockSignals(True)
            try:
                for original_item, number in old_numbers:
                    original_item.setData(Qt.ItemDataRole.UserRole, number)
            finally:
                self.camera_names.blockSignals(signals_blocked)
            self.camera_next_order = old_next_order
        else:
            if self.camera_worker:
                self.camera_worker.update_names(self.camera_username_list())
            self.remind_camera_export('red')


    def save_camera_settings(self):
        try:
            items = sorted((self.camera_names.item(i) for i in range(self.camera_names.count())),
                           key=lambda item: item.data(Qt.ItemDataRole.UserRole))
            settings.save_camera_settings(self.camera_username_list(), self.camera_auto.isChecked(),
                                          self.camera_alphabetical.isChecked(),
                                          [item.data(Qt.ItemDataRole.UserRole) for item in items],
                                          self.camera_next_order, self.camera_portrait_adjustment.isChecked(),
                                          self.camera_manual_prompt.isChecked())
            self.camera_log.appendPlainText('Camera settings saved.')
            return True
        except OSError as exc:
            QMessageBox.warning(self, 'Camera settings', f'Could not save settings: {exc}')
            return False


    def camera_auto_changed(self, enabled):
        self.save_camera_settings()
        if enabled:
            self.camera_auto_handled = False
            self.paltalk_startup.check()


    def camera_portrait_adjustment_changed(self, enabled):
        self.camera_portrait_adjustment.setText('Portrait adjustment: On' if enabled else 'Portrait adjustment: Off')
        if self.camera_worker:
            self.camera_worker.update_portrait_adjustment(enabled)
        self.save_camera_settings()


    def camera_manual_prompt_changed(self, enabled):
        self.camera_manual_prompt.setText('Prompt to add manually opened cameras: ' + ('On' if enabled else 'Off'))
        if not enabled:
            self.camera_prompts.clear()
        if self.camera_worker:
            self.camera_worker.update_manual_prompt(enabled)
        self.save_camera_settings()


    def start_cameras(self, automatic=False):
        if self.camera_worker:
            return
        names = self.camera_username_list()
        if not names and not self.camera_manual_prompt.isChecked():
            self.camera_log.appendPlainText('Add at least one username before starting.')
            return
        if not self.save_camera_settings():
            return
        self.camera_worker = CameraWorker(names, self.camera_portrait_adjustment.isChecked(),
                                          self.camera_manual_prompt.isChecked())
        self.camera_worker.message.connect(self.camera_log.appendPlainText)
        self.camera_worker.invoked.connect(self.camera_invoked_log.appendPlainText)
        self.camera_worker.failed.connect(self.camera_failed_log.appendPlainText)
        self.camera_worker.live_status.connect(self.update_camera_live_status)
        self.camera_worker.manual_opened.connect(self.camera_prompts.queue)
        self.camera_worker.finished.connect(self.cameras_finished)
        self.camera_start.setEnabled(False)
        self.camera_stop.setEnabled(True)
        self.camera_log.appendPlainText('Camera monitoring started. Keep the On Cam list visible.')
        self.camera_worker.start()


    def stop_cameras(self):
        self.camera_prompts.clear()
        self.camera_restart_pending = False
        self.update_camera_live_status([])
        if self.camera_worker:
            self.camera_worker.requestInterruption()
            self.camera_stop.setEnabled(False)
            self.camera_log.appendPlainText('Stopping camera monitoring...')


    def cameras_finished(self):
        self.camera_prompts.clear()
        self.update_camera_live_status([])
        self.camera_worker = None
        self.camera_start.setEnabled(True)
        self.camera_stop.setEnabled(False)
        self.camera_log.appendPlainText('Camera monitoring stopped.')
        if self.camera_restart_pending:
            self.camera_restart_pending = False
            self.start_cameras()


