"""Application stylesheet."""

APP_STYLE = """
    QMainWindow { background: #171a21; }
    QTabWidget::pane { border: 1px solid #3b4252; background: #20252e; }
    QTabBar::tab {
        background: #2a3140; color: white; font-weight: 700;
        padding: 14px 28px; margin-right: 2px;
    }
    QTabBar::tab:selected { background: #6d3cc8; }
    QLabel, QPushButton, QLineEdit, QDoubleSpinBox, QPlainTextEdit {
        color: white; font-weight: 700;
    }
    QLabel[roomAvailable="false"], QLineEdit[roomAvailable="false"] {
        color: #7d8594;
    }
    QLineEdit, QDoubleSpinBox, QPlainTextEdit {
        background: #11151c; border: 1px solid #4b5568;
        border-radius: 5px; padding: 8px;
    }
    QLineEdit:focus, QDoubleSpinBox:focus { border: 2px solid #9a6cff; }
    QPushButton {
        background: #6d3cc8; border: none; border-radius: 5px;
        padding: 10px 18px;
    }
    QPushButton:hover { background: #8256d8; }
    QPushButton:disabled { background: #454b57; color: #c4c7cf; }
    QPushButton#regularModeButton, QPushButton#vipModeButton, QPushButton#autoOpenButton {
        background: #343b48;
    }
    QPushButton#regularModeButton:checked, QPushButton#vipModeButton:checked,
    QPushButton#autoOpenButton:checked {
        background: #6d3cc8;
    }
"""
