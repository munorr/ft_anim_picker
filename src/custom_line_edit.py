try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Qt, Signal, QSize
    from PySide6.QtGui import QColor, QIntValidator, QDoubleValidator
    from shiboken6 import wrapInstance
    from PySide6.QtGui import QColor, QShortcut
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Qt, Signal, QSize
    from PySide2.QtGui import QColor, QIntValidator, QDoubleValidator
    from PySide2.QtWidgets import QShortcut
    from shiboken2 import wrapInstance
    
class FocusLosingLineEdit(QtWidgets.QLineEdit):
    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
            self.clearFocus()


class IntegerLineEdit(QtWidgets.QLineEdit):
    valueChanged = Signal(float)

    def __init__(self, parent=None, min_value=0, max_value=100, increment=1, width=None, height=None):
        super(IntegerLineEdit, self).__init__(parent)
        
        self.min_value = float(min_value)
        self.max_value = float(max_value)
        self.increment = float(increment)
        
        self.setValidator(QDoubleValidator(self.min_value, self.max_value, 1, self))
        self.setText(f"{self.min_value:.1f}")
        
        self.setStyleSheet("background-color: #333333; color: #dddddd; border: 1px solid #444444; border-radius: 3px;")
        
        self.last_x = None

        # Set size if provided
        if width is not None or height is not None:
            self.setCustomSize(width, height)

        # Connect the editingFinished signal to apply the value
        self.editingFinished.connect(self.applyValue)

    def setCustomSize(self, width=None, height=None):
        if width is not None and height is not None:
            self.setFixedSize(width, height)
        elif width is not None:
            self.setFixedWidth(width)
        elif height is not None:
            self.setFixedHeight(height)

    def sizeHint(self):
        # Provide a default size hint if no custom size is set
        return QSize(100, 25)

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self.last_x = event.x()
        super(IntegerLineEdit, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MiddleButton:
            delta = event.x() - self.last_x
            if abs(delta) >= 5:  # Threshold to avoid small movements
                change = (delta // 5) * self.getAdjustedIncrement(event)
                self.updateValue(change)
                self.last_x = event.x()
        super(IntegerLineEdit, self).mouseMoveEvent(event)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        adjusted_increment = self.getAdjustedIncrement(event)
        if delta > 0:
            self.updateValue(adjusted_increment)
        elif delta < 0:
            self.updateValue(-adjusted_increment)
        event.accept()

    def getAdjustedIncrement(self, event):
        if event.modifiers() & Qt.ShiftModifier:
            return self.increment / 2
        elif event.modifiers() & Qt.ControlModifier:
            return self.increment * 5
        return self.increment

    def updateValue(self, change):
        current_value = float(self.text())
        new_value = max(self.min_value, min(self.max_value, current_value + change))
        if new_value != current_value:
            self.setText(f"{new_value:.1f}")
            self.valueChanged.emit(new_value)

    def setValue(self, value):
        clamped_value = max(self.min_value, min(self.max_value, float(value)))
        self.setText(f"{clamped_value:.1f}")
        self.valueChanged.emit(clamped_value)

    def value(self):
        return float(self.text())

    def keyPressEvent(self, event):
        super(IntegerLineEdit, self).keyPressEvent(event)
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            self.applyValue()

    def applyValue(self):
        try:
            value = float(self.text())
            clamped_value = max(self.min_value, min(self.max_value, value))
            self.setText(f"{clamped_value:.1f}")
            self.valueChanged.emit(clamped_value)
        except ValueError:
            # If the text is not a valid float, reset to the minimum value
            self.setText(f"{self.min_value:.1f}")
            self.valueChanged.emit(self.min_value)