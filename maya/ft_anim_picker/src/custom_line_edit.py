try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Qt, Signal, QSize
    from PySide6.QtGui import QColor, QIntValidator, QDoubleValidator
    from shiboken6 import wrapInstance
    from PySide6.QtGui import QColor, QShortcut, QPainter
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Qt, Signal, QSize
    from PySide2.QtGui import QColor, QIntValidator, QDoubleValidator, QPainter
    from PySide2.QtWidgets import QShortcut
    from shiboken2 import wrapInstance
    
class FocusLosingLineEdit(QtWidgets.QLineEdit):
    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() in (QtCore.Qt.Key_Enter, QtCore.Qt.Key_Return):
            self.clearFocus()

class IntegerLineEdit(QtWidgets.QLineEdit):
    valueChanged = Signal(float)
    applyToAllRequested = Signal(float)  # New signal for apply-to-all functionality

    def __init__(self, parent=None, min_value=0, max_value=100, increment=1, precision=1, width=None, height=None, label=""):
        super(IntegerLineEdit, self).__init__(parent)
        
        self.min_value = float(min_value)
        self.max_value = float(max_value)
        self.increment = float(increment)
        self.precision = max(0, int(precision))  # Ensure precision is non-negative integer
        self.label_text = label
        
        self.setValidator(QDoubleValidator(self.min_value, self.max_value, self.precision, self))
        self.setText(f"{self.min_value:.{self.precision}f}")
        
        self.setStyleSheet("""background-color: #333333; color: #eeeeee; border: 1px solid #444444; 
        border-radius: 3px; padding: 2px; text-align: center; font-size: 11px;""")
        
        self.last_x = None
        self.dragging = False
        self.drag_used = False  # Track if dragging was actually used
        self.apply_to_all_mode = False  # Flag to enable/disable apply-to-all feature

        # Set size if provided
        if width is not None or height is not None:
            self.setCustomSize(width, height)

        # Connect the editingFinished signal to apply the value
        self.editingFinished.connect(self.applyValue)
        
        # Calculate text margins based on label
        self.updateTextMargins()

    def setLabel(self, label):
        """Set the label text"""
        self.label_text = label
        self.updateTextMargins()
        self.update()  # Trigger repaint

    def getLabel(self):
        """Get the current label text"""
        return self.label_text

    def updateTextMargins(self):
        """Update text margins to accommodate the label"""
        if self.label_text:
            # Calculate label width
            font_metrics = self.fontMetrics()
            label_width = font_metrics.horizontalAdvance(self.label_text + ": ")
            # Set left margin to make room for the label
            self.setTextMargins(label_width + 0, 0, 0, 0)
        else:
            self.setTextMargins(2, 0, 2, 0)

    def paintEvent(self, event):
        # First, let the parent class draw the line edit
        super(IntegerLineEdit, self).paintEvent(event)
        
        # Now draw our label
        if self.label_text:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Set up the font and color for the label
            font = self.font()
            painter.setFont(font)
            
            # Set label color at 50% opacity
            label_color = QColor(255, 255, 255, 80)  # #dddddd at 50% opacity
            painter.setPen(label_color)
            
            # Draw the label text
            text_rect = self.rect()
            text_rect.setLeft(4)  # Small left padding
            
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, self.label_text)
            
            painter.end()

    def setApplyToAllMode(self, enabled):
        """Enable or disable the apply-to-all feature"""
        self.apply_to_all_mode = enabled
        
        # Update tooltip to indicate the feature
        if enabled:
            current_tooltip = self.toolTip()
            new_tooltip = current_tooltip + "\n\nPress Enter to apply value to all selected buttons" if current_tooltip else "Press Enter to apply value to all selected buttons"
            self.setToolTip(new_tooltip)
        else:
            # Remove the apply-to-all part from tooltip
            current_tooltip = self.toolTip()
            if current_tooltip and "Press Enter to apply" in current_tooltip:
                lines = current_tooltip.split('\n')
                filtered_lines = [line for line in lines if "Press Enter to apply" not in line]
                self.setToolTip('\n'.join(filtered_lines).strip())

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
        if event.button() == Qt.LeftButton:
            self.last_x = event.x()
            self.dragging = True
            self.drag_used = False  # Reset drag usage flag
            self.setCursor(Qt.SizeHorCursor)  # Change cursor to indicate drag mode
        super(IntegerLineEdit, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging and (event.buttons() & Qt.LeftButton):
            delta = event.x() - self.last_x
            if abs(delta) >= 5:  # Threshold to avoid small movements
                change = (delta // 5) * self.getAdjustedIncrement(event)
                self.updateValue(change)
                self.last_x = event.x()
                self.drag_used = True  # Mark that dragging was actually used
        super(IntegerLineEdit, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Only clear focus if dragging was actually used
            if self.drag_used:
                self.clearFocus()
            self.dragging = False
            self.setCursor(Qt.IBeamCursor)  # Reset cursor to text editing cursor
        super(IntegerLineEdit, self).mouseReleaseEvent(event)

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
            self.setText(f"{new_value:.{self.precision}f}")
            self.valueChanged.emit(new_value)

    def setValue(self, value):
        clamped_value = max(self.min_value, min(self.max_value, float(value)))
        self.setText(f"{clamped_value:.{self.precision}f}")
        self.valueChanged.emit(clamped_value)

    def value(self):
        return float(self.text())

    def keyPressEvent(self, event):
        super(IntegerLineEdit, self).keyPressEvent(event)
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if self.apply_to_all_mode:
                # Apply to all selected buttons
                self.applyToAll()
            else:
                # Normal single value apply
                self.applyValue()

    def applyValue(self):
        """Apply value normally (single button or current behavior)"""
        try:
            value = float(self.text())
            clamped_value = max(self.min_value, min(self.max_value, value))
            self.setText(f"{clamped_value:.{self.precision}f}")
            self.valueChanged.emit(clamped_value)
        except ValueError:
            # If the text is not a valid float, reset to the minimum value
            self.setText(f"{self.min_value:.{self.precision}f}")
            self.valueChanged.emit(self.min_value)

    def applyToAll(self):
        """Apply the entered value to all selected buttons"""
        try:
            value = float(self.text())
            clamped_value = max(self.min_value, min(self.max_value, value))
            self.setText(f"{clamped_value:.{self.precision}f}")
            
            # Emit the special signal for apply-to-all functionality
            self.applyToAllRequested.emit(clamped_value)
            
        except ValueError:
            # If the text is not a valid float, reset to the minimum value
            self.setText(f"{self.min_value:.{self.precision}f}")
            self.applyToAllRequested.emit(self.min_value)

