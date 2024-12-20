try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtGui import QColor, QPainter, QPainterPath
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Qt, QRect
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtGui import QColor, QPainter, QPainterPath
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Qt, QRect
    from shiboken2 import wrapInstance
from . import utils as UT


class CustomButton(QtWidgets.QPushButton):
    singleClicked = QtCore.Signal()
    doubleClicked = QtCore.Signal()
    rightClicked = QtCore.Signal(QtCore.QPoint)

    def __init__(self, text='', icon=None, color='#4d4d4d', tooltip='', flat=False, size=None, width=None, height=None, parent=None, radius=3, ContextMenu=False, 
                 cmColor='#00749a', onlyContext=False, alpha=1,textColor='white', text_size=12):    
        super().__init__(parent)
        self.setFlat(flat)
        self.base_color = color
        self.radius = radius
        self.cmColor = cmColor
        self.onlyContext = onlyContext
        self.alpha = alpha
        self.textSize = text_size
        self.textColor = textColor
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.setStyleSheet(self.get_style_sheet(color, flat, radius))
        
        icon_size = size if size else 24
        
        if icon:
            self.setIcon(QtGui.QIcon(icon))
            self.setIconSize(QtCore.QSize(icon_size, icon_size))
        
        if text:
            self.setText(text)
            if height is None:
                self.setFixedHeight(24)
            if width is None:
                if icon:
                    self.setMinimumWidth(self.calculate_button_width(text, padding=30))
                    self.setStyleSheet(self.styleSheet() + " QPushButton { text-align: right; padding-right: 10px; }")
                else:
                    self.setMinimumWidth(self.calculate_button_width(text))
        elif icon and (width is None or height is None):
            self.setFixedSize(icon_size, icon_size)
        
        if width is not None:
            self.setFixedWidth(width)
        if height is not None:
            self.setFixedHeight(height)
        
        if icon and text:
            self.setLayoutDirection(QtCore.Qt.LeftToRight)
        
        self.setToolTip(f"<html><body><p style='color:white; white-space:nowrap; '>{tooltip}</p></body></html>")
        
        self.context_menu = None
        if ContextMenu or onlyContext:
            self.context_menu = QtWidgets.QMenu(self)
            self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self.customContextMenuRequested.connect(self.show_context_menu)

        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.performSingleClick)
        self.click_count = 0
        self.reset_button_state()

        #--------------------------------------------------------------------------------------------------------
    def get_style_sheet(self, color, flat, radius):
        if flat:
            return "background-color: transparent;"
        else:
            return f'''
                QPushButton {{
                    background-color: {UT.rgba_value(color, 1.0, alpha=self.alpha)};
                    color: {self.textColor};
                    border: none;
                    padding: 1px;
                    border-radius: {radius}px;
                    font-size: {self.textSize}px;
                }}
                QPushButton:hover {{
                    background-color: {UT.rgba_value(color, 1.2, alpha=1)};
                }}
                QPushButton:pressed {{
                    background-color: {UT.rgba_value(color, 0.8, alpha=self.alpha)};
                }}
                QToolTip {{
                    background-color: {color};
                    color: white;
                    border: 0px;
                }}
            '''
        
    def calculate_button_width(self, text, padding=20):
        font_metrics = QtGui.QFontMetrics(QtWidgets.QApplication.font())
        text_width = font_metrics.horizontalAdvance(text)
        return text_width + padding

    def addToMenu(self,name, function,icon=None):
        if self.context_menu:
            action = self.context_menu.addAction(QtGui.QIcon(f":/{icon}"),name)
            action.triggered.connect(function)

    def show_context_menu(self, pos):
        if self.context_menu:
            self.reset_button_state()
            self.context_menu.setWindowFlags(self.context_menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
            self.context_menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
            self.context_menu.setStyleSheet(f'''
                QMenu {{
                    background-color: rgba(35, 35, 35, 1);
                    border: 1px solid #444444;
                    border-radius: 3px;
                    padding:  4px 5px;
                }}
                QMenu::item {{
                    background-color: {UT.rgba_value(self.cmColor, 1, alpha=self.alpha)};
                    padding: 3px 30px 3px 5px;
                    margin: 3px 0px;
                    border-radius: 3px;
                }}
                QMenu::item:selected {{
                    background-color: {UT.rgba_value(self.cmColor, 1.2, alpha=1)};
                }}''')
            self.context_menu.exec_(self.mapToGlobal(pos))
            
        
            
    #--------------------------------------------------------------------------------------------------------
    def mousePressEvent(self, event):
        if self.onlyContext:
            if event.button() in (QtCore.Qt.LeftButton, QtCore.Qt.RightButton):
                self.show_context_menu(event.pos())
                
        else:
            if event.button() == QtCore.Qt.LeftButton:
                self.click_count += 1
                if not self.timer.isActive():
                    self.timer.start(300)
            elif event.button() == QtCore.Qt.RightButton:
                self.rightClicked.emit(event.pos())
            super(CustomButton, self).mousePressEvent(event)
        UT.maya_main_window().activateWindow()
        
    def mouseReleaseEvent(self, event):
        if not self.onlyContext:
            if event.button() == QtCore.Qt.LeftButton:
                if self.click_count == 2:
                    self.timer.stop()
                    self.click_count = 0
                    self.doubleClicked.emit()
        super(CustomButton, self).mouseReleaseEvent(event)
        
    def performSingleClick(self):
        if not self.onlyContext:
            if self.click_count == 1:
                self.singleClicked.emit()
        self.click_count = 0

    def leaveEvent(self, event):
        self.reset_button_state()
        super(CustomButton, self).leaveEvent(event)
        
    def reset_button_state(self):
        self.setStyleSheet(self.get_style_sheet(self.base_color, self.isFlat(), self.radius))
        self.update()

class CustomRadioButton(QtWidgets.QRadioButton):
    def __init__(self, text, color="#5285a6", fill=False, group=False, parent=None, border_radius=3, width=None, height=None):
        super(CustomRadioButton, self).__init__(text, parent)
        self.color = color
        self.fill = fill
        self.group_enabled = group
        self.group_name = None
        self.border_radius = border_radius
        self.custom_width = width
        self.custom_height = height
        self.setStyleSheet(self._get_style())
        
        if width is not None or height is not None:
            self.setFixedSize(width or self.sizeHint().width(), height or self.sizeHint().height())

    def _get_style(self):
        base_style = f"""
            QRadioButton {{
                background-color: {'transparent' if not self.fill else '#555555'};
                color: white;
                padding: 5px;
                border-radius: {self.border_radius}px;
            }}
        """
        
        if self.custom_width is not None:
            base_style += f"QRadioButton {{ min-width: {self.custom_width}px; max-width: {self.custom_width}px; }}"
        
        if self.custom_height is not None:
            base_style += f"QRadioButton {{ min-height: {self.custom_height}px; max-height: {self.custom_height}px; }}"

        if self.fill:
            return base_style + f"""
                QRadioButton::indicator {{
                    width: 0px;
                    height: 0px;
                }}
                QRadioButton:checked {{
                    background-color: {self.color};
                }}
                QRadioButton:hover {{
                    background-color: #6a6a6a;
                }}
                QRadioButton:checked:hover {{
                    background-color: {self._lighten_color(self.color, 1.2)};
                }}
            """
        else:
            return base_style + f"""
                QRadioButton::indicator {{
                    width: 13px;
                    height: 13px;
                }}
                QRadioButton::indicator:unchecked {{
                    background-color: #555555;
                    border: 0px solid #555555;
                    border-radius: {self.border_radius}px;
                }}
                QRadioButton::indicator:checked {{
                    background-color: {self.color};
                    border: 0px solid {self.color};
                    border-radius: 3px;
                }}
                QRadioButton::indicator:hover {{
                    background-color: #6a6a6a;
                }}
                QRadioButton::indicator:checked:hover {{
                    background-color: {self._lighten_color(self.color, 1.2)};
                }}
            """

    def _lighten_color(self, color, factor):
        c = QtGui.QColor(color)
        h, s, l, _ = c.getHslF()
        return QtGui.QColor.fromHslF(h, s, min(1.0, l * factor), 1.0).name()

    def group(self, group_name):
        if self.group_enabled:
            self.group_name = group_name
            if not hasattr(CustomRadioButton, 'groups'):
                CustomRadioButton.groups = {}
            if group_name not in CustomRadioButton.groups:
                CustomRadioButton.groups[group_name] = QtWidgets.QButtonGroup()
            CustomRadioButton.groups[group_name].addButton(self)

class CustomToolTip(QtWidgets.QWidget):
    def __init__(self, parent=None, color='#444444'):
        super().__init__(parent, QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.color = color
        self.text = ""
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        path = QtGui.QPainterPath()
        rect = QtCore.QRect(0, 0, self.width(), self.height())
        path.addRoundedRect(rect, 4, 4)
        
        painter.fillPath(path, QtGui.QColor(self.color))
        painter.setPen(QtGui.QColor(255, 255, 255))  # White border
        painter.drawPath(path)

        # Draw text
        painter.setPen(QtGui.QColor(255, 255, 255))  # White text
        painter.drawText(rect, QtCore.Qt.AlignCenter, self.text)

    def show_tooltip(self, parent, text, pos):
        self.text = text
        self.adjustSize()
        global_pos = parent.mapToGlobal(pos)
        self.move(global_pos + QtCore.QPoint(10, 10))
        self.show()

    def hideEvent(self, event):
        self.text = ""
        super().hideEvent(event)

    def sizeHint(self):
        fm = self.fontMetrics()
        width = fm.horizontalAdvance(self.text) + 20
        height = fm.height() + 10
        return QtCore.QSize(width, height)