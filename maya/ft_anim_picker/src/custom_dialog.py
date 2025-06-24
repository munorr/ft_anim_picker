try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtGui import QColor
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtGui import QColor
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve
    from shiboken2 import wrapInstance

class CustomDialog(QtWidgets.QDialog):
    def __init__(self, parent=None, title="", size=(250, 150), info_box = False):
        super(CustomDialog, self).__init__(parent)
        self.info_box = info_box
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setFixedSize(*size)
        self.setStyleSheet('''
            QFrame {
                background-color: rgba(40, 40, 40, 1);
                border-radius: 5px;
                border: 1px solid #444444;
            }
            QDialog {
                background-color: rgba(40, 40, 40, 0.9);
                border-radius: 5px;
            }
            QLabel, QRadioButton {
                color: white;
                background-color: transparent;
                border: none;
            }
            QLineEdit {
                background-color: #4d4d4d;
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton {
                color: white;
                border: none;
                padding: 5px;
                border-radius: 3px;
            }
            QPushButton#acceptButton {
                background-color: #00749a;
            }
            QPushButton#acceptButton:hover {
                background-color: #00ade6;
            }
            QPushButton#closeButton {
                background-color: #a30000;
            }
            QPushButton#closeButton:hover {
                background-color: #ff0000;
            }
            QPushButton#okayButton {
                background-color: #00749a;
            }
            QPushButton#okayButton:hover {
                background-color: #00ade6;
            }
            QComboBox {
                background-color: #444444;
                color: white;
                padding: 5px;
            }
        ''')
        self.frame = QtWidgets.QFrame(self)
        self.frame.setFixedSize(*size)

        self.layout = QtWidgets.QVBoxLayout(self.frame)
        self.layout.setContentsMargins(10, 10, 10, 10)
        self.layout.setSpacing(10)

        # Add Enter key shortcut
        
        try:
            self.enter_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return), self)
        except:
            self.enter_shortcut = QtGui.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return), self)
        self.enter_shortcut.activated.connect(self.accept)

    def add_widget(self, widget):
        self.layout.addWidget(widget)

    def add_layout(self, layout):
        self.layout.addLayout(layout)

    def add_button_box(self):
        if self.info_box:
            button_layout = QtWidgets.QHBoxLayout()
            okay_button = QtWidgets.QPushButton("Okay")
            okay_button.setObjectName("okayButton")
            #button_layout.addStretch()
            button_layout.addWidget(okay_button)
            self.layout.addStretch()
            self.layout.addLayout(button_layout)
            okay_button.clicked.connect(self.accept)
            return okay_button
        else:
            button_layout = QtWidgets.QHBoxLayout()
            accept_button = QtWidgets.QPushButton("Accept")
            close_button = QtWidgets.QPushButton("Close")
            accept_button.setObjectName("acceptButton")
            close_button.setObjectName("closeButton")
            #accept_button.setFixedWidth(80)
            #close_button.setFixedWidth(80)
            button_layout.addWidget(accept_button)
            button_layout.addWidget(close_button)
            self.layout.addStretch()
            self.layout.addLayout(button_layout)
            accept_button.clicked.connect(self.accept)
            close_button.clicked.connect(self.reject)
            return accept_button, close_button
    