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
from . import utils as UT

from . import custom_line_edit as CLE

class CustomSlider(QtWidgets.QSlider):
    def __init__(self, min_value=0, max_value=100, parent=None, width=None, height=30, float_precision=0, color="#444444", radius=4, prefix="", suffix="", font_size=10):
        super().__init__(QtCore.Qt.Horizontal, parent)
        
        self.float_precision = float_precision
        self.scale_factor = 10 ** float_precision
        self.color = color
        self.radius = radius
        self.prefix = prefix
        self.suffix = suffix
        self.font_size = font_size
        
        scaled_min = int(min_value * self.scale_factor)
        scaled_max = int(max_value * self.scale_factor)
        self.setRange(scaled_min, scaled_max)
        
        self.current_width = self.width()
        self.updateHandleWidth()
        
        # Label for displaying the value
        self.label = QtWidgets.QLabel(self)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.label.setStyleSheet(f"color: #dddddd; background-color: transparent; font-size: {self.font_size}px;")
        
        # LineEdit for input
        self.line_edit = QtWidgets.QLineEdit(self)
        self.line_edit.setAlignment(QtCore.Qt.AlignCenter)
        self.line_edit.setStyleSheet(f"font-size: {self.font_size}px;")
        self.line_edit.hide()
        
        # Connect signals
        self.valueChanged.connect(self.updateLabel)
        self.line_edit.returnPressed.connect(self.setValueFromText)
        
        if width is not None:
            self.setFixedWidth(width)
        
        if height is not None:
            self.setFixedHeight(height)
        
        # Initialize the label with the default value
        self.updateLabel(self.value())
        self.updateLabelPosition()
    
    def updateHandleWidth(self):
        self.handle_width = max(10, int(self.current_width * 0.05))
    
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)  # Enable anti-aliasing
        
        option = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(option)

        groove_rect = option.rect
        groove_rect.setHeight(self.height())
        
        subpage_rect = groove_rect
        handle_pos = (self.value() - self.minimum()) / (self.maximum() - self.minimum())
        subpage_rect.setWidth(int(handle_pos * groove_rect.width()))
        
        # Draw groove
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor("#2d2d2d"))
        painter.drawRoundedRect(groove_rect, self.radius, self.radius)

        # Draw sub-page with border radius
        painter.setBrush(QtGui.QColor(self.color))
        painter.drawRoundedRect(subpage_rect, self.radius, self.radius)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.current_width = self.width()
        self.updateHandleWidth()
        self.updateLabelPosition()
    
    def updateLabelPosition(self):
        width = self.current_width
        height = self.height()
        
        # Position both label and line edit
        geometry = QtCore.QRect(0, 0, width, height)
        
        self.label.setGeometry(geometry)
        self.line_edit.setGeometry(geometry)
    
    def updateLabel(self, value):
        float_value = value / self.scale_factor
        formatted_value = f"{float_value:.{self.float_precision}f}"
        
        # Add prefix and suffix to the label text
        label_text = f"{self.prefix}{formatted_value}{self.suffix}"
        
        if not self.line_edit.isVisible():
            self.label.setText(label_text)

    def mouseDoubleClickEvent(self, event):
        # Show line edit on double click and hide label
        if not self.line_edit.isVisible():
            float_value = super().value() / self.scale_factor
            formatted_value = f"{float_value:.{self.float_precision}f}"
            text_value = f"{formatted_value}"
            
            # Set current value in line edit and show it
            self.line_edit.setText(text_value)
            self.line_edit.show()
            self.line_edit.setFocus()
            self.label.hide()

    def setValueFromText(self):
        try:
            text_value = float(self.line_edit.text())
            scaled_value = int(text_value * self.scale_factor)

            if scaled_value >= super().minimum() and scaled_value <= super().maximum():
                super().setValue(scaled_value)

            # Hide line edit and show label after setting value
            self.line_edit.hide()
            self.label.show()

            # Update label with new value
            self.updateLabel(super().value())

        except ValueError:
            pass  # Handle invalid input gracefully

    def value(self):
        return super().value() / self.scale_factor
    
    def setValue(self, value):
        super().setValue(int(value * self.scale_factor))


class HorizontalScrollArea(QtWidgets.QScrollArea):
    def wheelEvent(self, event):
        # Get the horizontal scrollbar
        hbar = self.horizontalScrollBar()
        # Use vertical wheel delta for horizontal scrolling
        # You can adjust the 120 value to control scrolling speed
        delta = event.angleDelta().y() // 120 * 30  # Normalize to steps of 120
        hbar.setValue(hbar.value() - delta)

#self.canvas_tab_frame_scroll_area = HorizontalScrollArea()