"""Queue and display prompts for manually opened cameras."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QInputDialog


class ManualCameraPromptController:
    def __init__(self, owner):
        self.owner = owner
        self.dialog = None
        self.queue_items = []

    def clear(self):
        self.queue_items.clear()
        if self.dialog is not None:
            dialog = self.dialog
            self.dialog = None
            dialog.reject()
            dialog.deleteLater()

    def queue(self, name):
        if not self.owner.camera_worker or self.owner.camera_worker.isInterruptionRequested() or not self.owner.camera_manual_prompt.isChecked():
            return
        if name.casefold() in {n.casefold() for n in self.owner.camera_username_list()}:
            return
        if name.casefold() not in {n.casefold() for n in self.queue_items}:
            self.queue_items.append(name)
        self.show_next()

    def show_next(self):
        if self.dialog is not None or not self.queue_items:
            return
        if not self.owner.camera_worker or self.owner.camera_worker.isInterruptionRequested() or not self.owner.camera_manual_prompt.isChecked():
            self.queue_items.clear()
            return
        name = self.queue_items.pop(0)
        if name.casefold() in {n.casefold() for n in self.owner.camera_username_list()}:
            self.show_next()
            return
        dialog = QInputDialog(self.owner)
        dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dialog.setWindowTitle('Add camera username')
        dialog.setLabelText('Check the detected username and correct it if needed:')
        dialog.setTextValue(name)
        dialog.setOkButtonText('Add')
        dialog.setCancelButtonText('Cancel')
        self.dialog = dialog

        def finished(result):
            if self.dialog is not dialog:
                return
            self.dialog = None
            if (result == QDialog.DialogCode.Accepted and self.owner.camera_worker
                    and not self.owner.camera_worker.isInterruptionRequested() and self.owner.camera_manual_prompt.isChecked()):
                self.owner.add_camera_username(dialog.textValue())
            dialog.deleteLater()
            self.show_next()

        dialog.finished.connect(finished)
        dialog.open()
        dialog.raise_()
        dialog.activateWindow()

