"""Application stylesheet."""

APP_STYLE = """
    QMainWindow { background: #171a21; }
    QTabWidget::pane { border: 1px solid #3b4252; background: #20252e; }
    QTabBar::tab {
        background: #2a3140; color: white; font-weight: 700;
        padding: 14px 28px; margin-right: 2px;
    }
    QTabBar::tab:selected { background: #075b8c; }
    QTabBar::tab:disabled { background: #252932; color: #777e8b; }
    QToolButton#settingsMenuButton {
        background: #2a3140; color: white; border: none;
        font-size: 20px; padding: 8px 14px;
    }
    QToolButton#settingsMenuButton:hover { background: #075b8c; }
    QToolButton#settingsMenuButton::menu-indicator { image: none; }
    QMenu { background: #2a3140; color: white; border: 1px solid #4b5568; }
    QMenu::item { padding: 8px 28px; }
    QMenu::item:selected { background: #075b8c; }
    QLabel, QPushButton, QLineEdit, QDoubleSpinBox, QPlainTextEdit {
        color: white; font-weight: 700;
    }
    QLabel[roomAvailable="false"], QLineEdit[roomAvailable="false"] {
        color: #7d8594;
    }
    QLabel#micTimerStatus {
        background: #11151c; color: white; border: 1px solid #4b5568;
        border-radius: 5px; padding: 8px;
    }
    QLabel#roomDragHandle { padding: 6px; border-radius: 5px; }
    QLabel#roomDragHandle[dragHighlight="true"] { background: #168ac5; color: white; }
    QLineEdit, QDoubleSpinBox, QPlainTextEdit {
        background: #11151c; border: 1px solid #4b5568;
        border-radius: 5px; padding: 8px;
    }
    QLineEdit:focus, QDoubleSpinBox:focus { border: 2px solid #9a6cff; }
    QLineEdit[roomOpen="true"] {
        color: white; background: #102d3d; border: 2px solid #168ac5;
    }
    QLineEdit[roomOpen="true"]:focus { border: 2px solid #249bd6; }
    QListWidget#cameraNames {
        background: #000000; color: white; font-weight: 700;
        border: 1px solid #4b5568; border-radius: 5px;
    }
    QListWidget#cameraNames::item:selected { background: #168ac5; color: white; }
    QListWidget#adminPhrases {
        background: #11151c; color: white; font-weight: 700;
        border: 1px solid #4b5568; border-radius: 5px; padding: 8px;
    }
    QListWidget#adminPhrases::item:selected { background: #168ac5; color: white; }
    QPushButton {
        background: #168ac5; border: none; border-radius: 5px;
        padding: 10px 18px;
    }
    QPushButton:hover { background: #249bd6; }
    QPushButton:disabled { background: #454b57; color: #c4c7cf; }
    QPushButton#regularModeButton, QPushButton#vipModeButton { background: #343b48; }
    QPushButton#autoOpenButton { background: #168ac5; }
    QPushButton#cameraAlphabetical { background: #168ac5; }
    QPushButton#cameraAlphabetical:checked { background: #075b8c; }
    QPushButton[exportHighlight="green"] {
        background: #168c49; color: white; border: 2px solid #a0efbf;
    }
    QPushButton[exportHighlight="red"] {
        background: #bf3030; color: white; border: 2px solid #ffabab;
    }
    QPushButton#regularModeButton:checked, QPushButton#vipModeButton:checked {
        background: #075b8c;
    }
    QPushButton#autoOpenButton:checked { background: #6d3cc8; }
"""
