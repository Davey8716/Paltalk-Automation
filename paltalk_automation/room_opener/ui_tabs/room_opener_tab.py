"""Room opener tab and room drag controls."""

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (QButtonGroup, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget)


class RoomNameField(QLineEdit):
    """Accept a room dragged from another room field or its handle."""

    def __init__(self, index, reorder):
        super().__init__()
        self.room_index = index
        self.reorder = reorder
        self.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.textChanged.connect(self._show_start_when_unfocused)

    def _show_start_when_unfocused(self):
        if not self.hasFocus():
            self.setCursorPosition(0)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setCursorPosition(0)

    def dragEnterEvent(self, event):
        if isinstance(event.source(), (RoomNameField, RoomDragHandle)):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if isinstance(event.source(), (RoomNameField, RoomDragHandle)):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        source = event.source()
        if isinstance(source, (RoomNameField, RoomDragHandle)):
            self.reorder(source.room_index, self.room_index)
            # CopyAction prevents QLineEdit from deleting its selected source text.
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dropEvent(event)


class RoomDragHandle(QLabel):
    def __init__(self, index, reorder):
        super().__init__('⋮⋮')
        self.room_index = index
        self.reorder = reorder
        self.setObjectName('roomDragHandle')
        self.setAcceptDrops(True)
        self.setToolTip('Drag to move this room to another position')
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_highlighted(self, highlighted):
        self.setProperty('dragHighlight', highlighted)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()

    def dragEnterEvent(self, event):
        if isinstance(event.source(), (RoomDragHandle, RoomNameField)) and event.source() is not self:
            self.set_highlighted(True)
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if isinstance(event.source(), (RoomDragHandle, RoomNameField)) and event.source() is not self:
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.set_highlighted(False)
        event.accept()

    def dropEvent(self, event):
        self.set_highlighted(False)
        source = event.source()
        if isinstance(source, (RoomDragHandle, RoomNameField)) and source is not self:
            self.reorder(source.room_index, self.room_index)
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.MouseButton.LeftButton and hasattr(self, 'start_position')
                and (event.position().toPoint() - self.start_position).manhattanLength() >= 10):
            drag = QDrag(self)
            mime = QMimeData()
            mime.setText('room')
            drag.setMimeData(mime)
            self.set_highlighted(True)
            try:
                drag.exec(Qt.DropAction.CopyAction)
            finally:
                self.set_highlighted(False)
        else:
            super().mouseMoveEvent(event)


class RoomOpenerTab(QWidget):
    def __init__(self, owner):
        super().__init__(owner)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(38, 10, 38, 32)
        layout.setSpacing(18)
        self.room_tray_status_label = QLabel('Start in tray: Off')
        layout.addWidget(self.room_tray_status_label, alignment=Qt.AlignmentFlag.AlignRight)
        instruction_row = QHBoxLayout()
        instruction_row.addWidget(QLabel("Enter exact room names. Drag a ⋮⋮ handle or selected text to reorder."))
        recent_rooms_controls = QVBoxLayout()
        recent_rooms_controls.setSpacing(2)
        self.recent_rooms_button = QPushButton("Recently visited")
        self.recent_rooms_button.setFixedSize(150,35)
        recent_rooms_controls.addWidget(self.recent_rooms_button)
        instruction_row.addLayout(recent_rooms_controls)
        layout.addLayout(instruction_row)

        form = QGridLayout()
        form.setColumnStretch(2, 1)
        form.setColumnStretch(4, 1)
        self.rooms = []
        self.room_labels = []
        self.open_room_buttons = []
        for index in range(5):
            field = RoomNameField(index, owner.reorder_rooms)
            field.setPlaceholderText(f"Room {index + 1} name")
            field.setMaximumWidth(580)
            label = QLabel(f"Room {index + 1}:")
            form.addWidget(RoomDragHandle(index, owner.reorder_rooms), index, 0)
            form.addWidget(label, index, 1)
            form.addWidget(field, index, 2)
            open_button = QPushButton("Open")
            open_button.setEnabled(False)
            open_button.clicked.connect(lambda checked=False, i=index: owner.toggle_configured_room(i))
            field.textChanged.connect(owner.update_room_buttons)
            form.addWidget(open_button, index, 3)
            self.rooms.append(field)
            self.room_labels.append(label)
            self.open_room_buttons.append(open_button)
        self.delay = QDoubleSpinBox()
        self.delay.setRange(5, 60)
        self.delay.setValue(5)
        self.delay.setSuffix(" seconds")
        self.delay.setMaximumWidth(580)
        form.addWidget(QLabel("Delay between rooms:"), 5, 0, 1, 2)
        form.addWidget(self.delay, 5, 2)
        self.start_button = QPushButton("Open rooms")
        form.addWidget(self.start_button, 5, 3)
        self.close_all_button = QPushButton("Close all")
        self.close_all_button.setEnabled(False)
        room_columns = QHBoxLayout()
        room_columns.addLayout(form, 3)
        other_panel = QVBoxLayout()
        other_panel.addWidget(QLabel('Other open rooms'))
        self.other_rooms_scroll = QScrollArea()
        self.other_rooms_scroll.setWidgetResizable(True)
        self.other_rooms_scroll.setMinimumWidth(250)
        self.other_rooms_scroll.setMaximumHeight(260)
        other_container = QWidget()
        self.other_rooms_layout = QVBoxLayout(other_container)
        self.other_rooms_layout.setContentsMargins(0, 0, 0, 0)
        self.other_rooms_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.other_rooms_scroll.setWidget(other_container)
        other_panel.addWidget(self.other_rooms_scroll)
        other_panel.addWidget(self.close_all_button, alignment=Qt.AlignmentFlag.AlignLeft)
        room_columns.addLayout(other_panel, 2)
        layout.addLayout(room_columns)

        layout.addWidget(QLabel("Open Paltalk and display the My Rooms / Rooms view before starting."))
        buttons = QHBoxLayout()
        self.regular_button = QPushButton("Regular (3 rooms)")
        self.vip_button = QPushButton("VIP (5 rooms)")
        self.regular_button.setObjectName("regularModeButton")
        self.vip_button.setObjectName("vipModeButton")
        for button in (self.regular_button, self.vip_button):
            button.setFixedSize(150,35)
            button.setCheckable(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_group.addButton(self.regular_button)
        self.mode_group.addButton(self.vip_button)
        self.regular_button.setChecked(True)

        self.auto_open_button = QPushButton("Open when Paltalk starts")
        self.auto_open_button.setFixedSize(180,35)
        self.auto_open_button.setObjectName("autoOpenButton")
        self.auto_open_button.setCheckable(True)

        for button in (
            self.regular_button, self.vip_button, self.auto_open_button,
        ):
            buttons.addWidget(button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log)
