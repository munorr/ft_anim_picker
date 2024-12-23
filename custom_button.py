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

class TwoColumnMenu(QtWidgets.QMenu):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid_widget = QtWidgets.QWidget(self)
        self.grid_layout = QtWidgets.QGridLayout(self.grid_widget)
        gls = 6 # grid layout spacing
        self.grid_layout.setSpacing(gls)
        self.grid_layout.setContentsMargins(gls, gls, gls, gls)

        self.bg_color = "rgba(35, 35, 35, 1)"
        # Add the grid widget to the menu using a QWidgetAction
        widget_action = QtWidgets.QWidgetAction(self)
        widget_action.setDefaultWidget(self.grid_widget)
        self.addAction(widget_action)
        
        # Apply styling
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        
        self.grid_widget.setStyleSheet(f'''
                QWidget {{
                    background-color: {self.bg_color};
                                            border: 1px solid #444444;
                    border-radius: 3px;
                    padding:  4px 6px;
                }}''')
            #self.context_menu.exec_(self.mapToGlobal(pos))

    def rebuild_grid(self, actions):
        # Clear existing items
        for i in reversed(range(self.grid_layout.count())): 
            self.grid_layout.itemAt(i).widget().setParent(None)
        
        # Separate positioned and unpositioned items
        positioned = []
        unpositioned = []
        max_row = max_col = -1
        
        for item in actions:
            if len(item) == 4:  # Item with position, rowSpan, and colSpan
                action, position, rowSpan, colSpan = item
            else:  # Unpositioned item
                action = item
                position = None
                rowSpan = 1
                colSpan = 1
                
            if position is not None:
                positioned.append((action, position, rowSpan, colSpan))
                max_row = max(max_row, position[0] + rowSpan - 1)
                max_col = max(max_col, position[1] + colSpan - 1)
            else:
                unpositioned.append((action, rowSpan, colSpan))
        
        # Place positioned items first
        for action, pos, rowSpan, colSpan in positioned:
            button = self._create_menu_button(action)
            self.grid_layout.addWidget(button, pos[0], pos[1], rowSpan, colSpan)
        
        # Find available positions for unpositioned items
        if unpositioned:
            next_row = 0 if max_row == -1 else max_row + 1
            next_col = 0
            
            for action, rowSpan, colSpan in unpositioned:
                button = self._create_menu_button(action)
                # If this item would overflow the columns, move to next row
                if next_col + colSpan > 2:
                    next_col = 0
                    next_row += 1
                self.grid_layout.addWidget(button, next_row, next_col, rowSpan, colSpan)
                next_col += colSpan
                if next_col >= 2:
                    next_col = 0
                    next_row += rowSpan
        
        self.grid_widget.adjustSize()
        self.adjustSize()
        
    # In the TwoColumnMenu class, update the _create_menu_button method:
    def _create_menu_button(self, action):
        button = QtWidgets.QPushButton(action.text())
        if action.icon():
            button.setIcon(action.icon())
        
        # Create a wrapper function to handle both closing the menu and triggering the action
        def button_clicked():
            self.close()  # Close the menu first
            action.triggered.emit()  # Then trigger the action
        
        button.clicked.connect(button_clicked)
        
        button.setStyleSheet(f'''
            QPushButton {{
                background-color: {self.bg_color};
                color: white;
                border: none;
                padding: 3px 10px;
                border-radius: 3px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {UT.rgba_value(self.parent().base_color, 1.2)};
            }}
        ''')
        button.setFixedHeight(self.parent().cmHeight)
        return button

class CustomButton(QtWidgets.QPushButton):
    singleClicked = QtCore.Signal()
    doubleClicked = QtCore.Signal()
    rightClicked = QtCore.Signal(QtCore.QPoint)

    def __init__(self, text='', icon=None, color='#4d4d4d', tooltip='', flat=False, size=None, width=None, height=None, parent=None, radius=3, ContextMenu=False, 
                 cmColor='#00749a', cmHeight = 20, onlyContext=False, alpha=1,textColor='white', text_size=12):
        super().__init__(parent)
        self.setFlat(flat)
        self.base_color = color
        self.radius = radius
        self.cmColor = cmColor
        self.onlyContext = onlyContext
        self.alpha = alpha
        self.textSize = text_size
        self.textColor = textColor
        self.menu_actions = []  # Store menu actions
        self.cmHeight = cmHeight
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
            self.context_menu = TwoColumnMenu(self)
            #self.context_menu = QtWidgets.QMenu(self)
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
                    background-color: {UT.rgba_value(color, 1.0)}; 
                    color: {self.textColor};
                    border: none;
                    padding: 1px;
                    border-radius: {radius}px;
                    font-size: {self.textSize}px;
                }}
                QPushButton:hover {{
                    background-color: {UT.rgba_value(color, 1.2)};
                }}
                QPushButton:pressed {{
                    background-color: {UT.rgba_value(color, 0.8)};
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

    def addToMenu(self, name, function, icon=None, position=None, rowSpan=1, colSpan=1):
        """
        Add an item to the context menu.
        Args:
            name (str): Text to display in the menu
            function: Callback function when item is clicked
            icon (str, optional): Icon path/resource
            position (tuple, optional): (row, column) position in the grid
        """
        if self.context_menu:
            action = QtWidgets.QAction(name, self)
            if icon:
                action.setIcon(QtGui.QIcon(f":/{icon}"))
            action.triggered.connect(function)
            # Store position along with the action
            self.menu_actions.append((action, position, rowSpan, colSpan))
            self.context_menu.rebuild_grid(self.menu_actions)

    def show_context_menu(self, pos):
        if self.context_menu:
            self.reset_button_state()
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
        
        # If not grouped, make it behave like a toggle button
        if not group:
            self.auto_exclusive = False
            self.setAutoExclusive(False)  # This is key - it prevents auto-grouping
        
        self.setStyleSheet(self._get_style())
        
        if width is not None or height is not None:
            self.setFixedSize(width or self.sizeHint().width(), height or self.sizeHint().height())

    def mousePressEvent(self, event):
        if not self.group_enabled:
            # Toggle the checked state when clicked
            self.setChecked(not self.isChecked())
        else:
            super().mousePressEvent(event)

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
            self.setAutoExclusive(True)  # Enable auto-exclusive for grouped buttons

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