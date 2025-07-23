from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor, QPainter, QPainterPath, QAction
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Qt, QRect
from shiboken6 import wrapInstance

from . import utils as UT

class TwoColumnMenu(QtWidgets.QMenu):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.grid_widget = QtWidgets.QWidget(self)
        self.grid_layout = QtWidgets.QGridLayout(self.grid_widget)
        gls = 6
        self.grid_layout.setSpacing(gls)
        self.grid_layout.setContentsMargins(gls, gls, gls, gls)

        self.bg_color = "rgba(35, 35, 35, 1)"
        widget_action = QtWidgets.QWidgetAction(self)
        widget_action.setDefaultWidget(self.grid_widget)
        self.addAction(widget_action)
        
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        
        self.setStyleSheet(f"""
            QMenu {{
                background-color: {self.bg_color};
                border: 1px solid #444444;
                border-radius: 4px;
            }}
        """)
        
        self.grid_widget.setStyleSheet(f'''
            QWidget {{
                background-color: transparent;
                padding: 4px 6px;
            }}''')

    def _create_separator(self):
        separator = QtWidgets.QFrame()
        #separator.setFrameShape(QtWidgets.QFrame.HLine)
        separator.setFixedHeight(1)
        separator.setStyleSheet("""
            QFrame {
                background-color: #333333;
                margin: 0px 10px;
            }
        """)
        return separator
    
    def _create_menu_label(self, text):
        label = QtWidgets.QLabel(text)
        label.setStyleSheet(f'''
            QLabel {{
                color: #666666;
                background-color: transparent;
                border: none;
                padding: 0px 10px;
            }}
        ''')
        label.setFixedHeight(self.parent().cmHeight)
        return label

    def _create_menu_button(self, action):
        button = QtWidgets.QPushButton(action.text())
        if action.icon():
            button.setIcon(action.icon())
            
        # Handle notification indicator for menu items
        if action.data() and isinstance(action.data(), dict):
            action_data = action.data()
            if action_data.get("notification", False):
                original_paintEvent = button.paintEvent
                
                def custom_paintEvent(event):
                    # Call original paintEvent
                    original_paintEvent(event)
                    
                    # Draw notification indicator
                    painter = QPainter(button)
                    painter.setRenderHint(QPainter.Antialiasing)
                    
                    # Calculate size and position
                    icon_size = min(8, button.height() // 3)  # Slightly smaller for menu items
                    margin = 2
                    
                    x = button.width() - icon_size - margin
                    y = button.height() - icon_size - margin
                    rect = QtCore.QRectF(x, y, icon_size, icon_size)
                    
                    # Set color from notification_color property
                    painter.setBrush(QColor(action_data.get("notification_color", "#7db305")))
                    painter.setPen(Qt.NoPen)
                    
                    # Draw the circle
                    painter.drawEllipse(rect)
                
                # Replace the paintEvent method
                button.paintEvent = custom_paintEvent
        
        def button_clicked():
            self.close()
            action.triggered.emit()
        
        button.clicked.connect(button_clicked)
        
        button.setStyleSheet(f'''
            QPushButton {{
                background-color: {self.bg_color};
                color: white;
                border: none;
                padding: 2px 10px;
                border-radius: 3px;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: #444444;
            }}
        ''')
        button.setFixedHeight(self.parent().cmHeight)
        return button

    def rebuild_grid(self, items):
        for i in reversed(range(self.grid_layout.count())): 
            self.grid_layout.itemAt(i).widget().setParent(None)
        
        positioned = []
        unpositioned = []
        max_row = max_col = -1
        
        for item in items:
            if isinstance(item, tuple):
                if item[0] == 'separator':
                    _, position = item
                    positioned.append(('separator', None, position, 1, 2))
                    max_row = max(max_row, position[0])
                elif len(item) == 2:  # Label with position
                    label_text, position = item
                    positioned.append(('label', label_text, position, 1, 1))
                    max_row = max(max_row, position[0])
                    max_col = max(max_col, position[1])
                elif len(item) == 4:  # Action with position and spans
                    action, position, rowSpan, colSpan = item
                    positioned.append(('action', action, position, rowSpan, colSpan))
                    max_row = max(max_row, position[0] + rowSpan - 1)
                    max_col = max(max_col, position[1] + colSpan - 1)
            else:  # Unpositioned action
                unpositioned.append(('action', item, 1, 1))

        for item_type, item, pos, rowSpan, colSpan in positioned:
            if item_type == 'separator':
                widget = self._create_separator()
            elif item_type == 'label':
                widget = self._create_menu_label(item)
            else:
                widget = self._create_menu_button(item)
            self.grid_layout.addWidget(widget, pos[0], pos[1], rowSpan, colSpan)
        
        if unpositioned:
            next_row = 0 if max_row == -1 else max_row + 1
            next_col = 0
            
            for item_type, item, rowSpan, colSpan in unpositioned:
                widget = self._create_menu_button(item)
                if next_col + colSpan > 2:
                    next_col = 0
                    next_row += 1
                self.grid_layout.addWidget(widget, next_row, next_col, rowSpan, colSpan)
                next_col += colSpan
                if next_col >= 2:
                    next_col = 0
                    next_row += rowSpan

        self.grid_widget.adjustSize()
        self.adjustSize()

class CustomButton(QtWidgets.QPushButton):
    singleClicked = QtCore.Signal()
    doubleClicked = QtCore.Signal()
    rightClicked = QtCore.Signal(QtCore.QPoint)

    def __init__(self, text='', icon=None, color='#4d4d4d', tooltip='', flat=False, size=None, width=None, height=None, parent=None, radius=3, ContextMenu=False, 
                 cmColor='#00749a', cmHeight = 20, onlyContext=False, alpha=1,textColor='white', text_size=12, notification=False, notification_color='#7db305'):
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
        self.notification = notification
        self.notification_color = notification_color
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
            return f'''
                QPushButton {{
                    background-color: transparent;
                    color: {self.textColor};
                    border: none;
                    padding: 1px;
                    border-radius: {radius}px;
                    font-size: {self.textSize}px;
                }}
                QPushButton:hover {{
                    color: {UT.rgba_value(self.textColor, 1.2)};
                }}
                QToolTip {{background-color: #222222; 
                    color: #eeeeee ; 
                    border: 1px solid rgba(255,255,255,.2); 
                    padding: 0px;
                    border-radius: 0px;
                }}
            '''
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
                QToolTip {{background-color: {UT.rgba_value(color,.8,alpha=1)}; 
                    color: #eeeeee ; 
                    border: 1px solid rgba(255,255,255,.2); 
                    padding: 0px;
                    border-radius: 0px;
                }}
            '''
        
    def calculate_button_width(self, text, padding=20):
        font_metrics = QtGui.QFontMetrics(QtWidgets.QApplication.font())
        text_width = font_metrics.horizontalAdvance(text)
        return text_width + padding

    def addMenuSeparator(self, position=None):
        """
        Add a separator line to the context menu.
        Args:
            position (tuple, optional): (row) position in the grid
        """
        if self.context_menu:
            self.menu_actions.append(('separator', position))
            self.context_menu.rebuild_grid(self.menu_actions)

    def addMenuLabel(self, text, position=None):
        """
        Add a label to the context menu.
        Args:
            text (str): Text to display in the menu
            position (tuple, optional): (row, column) position in the grid
        """
        if self.context_menu:
            self.menu_actions.append((text, position))
            self.context_menu.rebuild_grid(self.menu_actions)

    def addToMenu(self, name, function, icon=None, position=None, rowSpan=1, colSpan=1, notification=False, notification_color='#7db305'):
        """
        Add an item to the context menu.
        Args:
            name (str): Text to display in the menu
            function: Callback function when item is clicked
            icon (str, optional): Icon path/resource
            position (tuple, optional): (row, column) position in the grid
        """
        if self.context_menu:
            action = QAction(name, self)
            # Store notification state in action's data
            action.setData({"notification": notification, "notification_color": notification_color})
            if icon:
                if isinstance(icon, QtGui.QPixmap):
                    action.setIcon(QtGui.QIcon(icon))
                else:
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
        #UT.blender_main_window() 
        
    def mouseReleaseEvent(self, event):
        if not self.onlyContext:
            if event.button() == QtCore.Qt.LeftButton:
                if self.click_count == 2:
                    self.timer.stop()
                    self.click_count = 0
                    self.doubleClicked.emit()

                main_window = self.window()
                if main_window.edit_mode == False:
                    UT.blender_main_window() 
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
        
    def paintEvent(self, event):
        # First, let the QPushButton draw itself normally
        super(CustomButton, self).paintEvent(event)

        # If notification is enabled, draw a small circle indicator at bottom right
        if self.notification == True:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            
            # Calculate the size and position of the circle
            icon_size = min(10, self.height() // 2.5)  # Size proportional to button height, max 10px
            margin = 2  # Margin from the bottom-right edge
            
            x = self.width() - icon_size - margin
            y = self.height() - icon_size - margin
            rect = QtCore.QRectF(x, y, icon_size, icon_size)
            
            # Set color from notification_color property
            painter.setBrush(QColor(self.notification_color))
            painter.setPen(Qt.NoPen)  # No border
            
            # Draw the circle
            painter.drawEllipse(rect)
        
    def set_notification(self, state=True, color="#7db305"):
        """Set notification state and color for the button"""
        self.notification = state
        self.notification_color = color
        self.update()
        
    def set_menu_item_notification(self, action_name, state=True, color="#7db305"):
        """Set notification state and color for a menu item by name"""
        for item in self.menu_actions:
            if isinstance(item, tuple) and len(item) >= 4 and isinstance(item[0], QAction):
                action = item[0]
                if action.text() == action_name:
                    action.setData({"notification": state, "notification_color": color})
                    self.context_menu.rebuild_grid(self.menu_actions)
                    break

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
        # Use different padding for fill mode to make it look more like a button
        padding = "2px" 
        base_style = f"""
            QRadioButton {{
                background-color: {'transparent' if not self.fill else '#555555'};
                color: white;
                padding: {padding};
                border-radius: {self.border_radius}px;
                text-align: {'center' if self.fill else 'left'};    
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
                    border: none;
                    background: none;
                    outline: none;
                }}
                QRadioButton::indicator:unchecked,
                QRadioButton::indicator:checked {{
                    width: 0px;
                    height: 0px;
                    border: none;
                    background: transparent;
                    outline: none;
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

class CustomTooltipWidget(QtWidgets.QWidget):
    def __init__(self, parent=None, bg_color="#1b1b1b", border_color="#333333"):
        super().__init__(parent)
        self.setWindowFlags(QtCore.Qt.ToolTip | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, True)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating, True)
        self.bg_color = bg_color
        self.border_color = border_color
        
        # Create main layout with padding
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(6, 8, 6, 8)
        self.main_layout.setSpacing(4)
        

        # Track if we need to auto-size
        self._auto_resize = True
        
    def add_text(self, text, rich_text=True):
        """Add a text label to the tooltip"""
        label = QtWidgets.QLabel(text)
        label.setTextFormat(QtCore.Qt.RichText if rich_text else QtCore.Qt.PlainText)
        label.setWordWrap(True)
        label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                color: #ffffff;
                font-size: 11px;
                border: none;
                padding: 0px;
                margin: 0px;
            }
        """)
        label.setMaximumWidth(400)
        self.main_layout.addWidget(label)
        return label
    
    def add_widget(self, widget):
        """Add a custom widget to the tooltip"""
        self.main_layout.addWidget(widget)
        return widget
    
    def add_layout(self, layout):
        """Add a layout to the tooltip"""
        self.main_layout.addLayout(layout)
        return layout
    
    def add_separator(self):
        """Add a horizontal separator line"""
        line = QtWidgets.QFrame()
        line.setFrameShape(QtWidgets.QFrame.HLine)
        line.setStyleSheet("""
            QFrame {
                color: #444444;
                background-color: #444444;
                border: none;
                max-height: 1px;
            }
        """)
        self.main_layout.addWidget(line)
        return line
    
    def add_spacing(self, size):
        """Add vertical spacing"""
        self.main_layout.addSpacing(size)
    
    def set_max_width(self, width):
        """Set maximum width for the tooltip"""
        self.setMaximumWidth(width + 24)  # Add padding
        
    def finalize(self):
        """Call this after adding all content to resize the tooltip"""
        if self._auto_resize:
            self.adjustSize()
            # Add some extra padding to the widget size
            current_size = self.size()
            self.setFixedSize(current_size.width() + 4, current_size.height() + 4)
    
    def clear_content(self):
        """Clear all content from the tooltip widget"""
        # Clear the layout with safety checks
        try:
            layout = self.layout()
            if layout:
                while layout.count():
                    item = layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                    elif item.layout():
                        self._clear_layout(item.layout())
        except:
            # Layout is in an invalid state, likely due to widget deletion
            pass
        
    def _clear_layout(self, layout):
        """Recursively clear a layout"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_layout(item.layout())
    
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        # Draw rounded rectangle background
        rect = self.rect()
        path = QtGui.QPainterPath()
        path.addRoundedRect(QtCore.QRectF(rect), 4, 4)
        
        # Fill background
        painter.fillPath(path, QtGui.QColor(self.bg_color))
        
        # Draw border
        painter.setPen(QtGui.QPen(QtGui.QColor(self.border_color), 1))
        painter.drawPath(path)


        