from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
from shiboken6 import wrapInstance

from .import picker_canvas as PC
from . import data_management as DM 
from . import custom_dialog as CD
from collections import OrderedDict
from . import utils as UT

class TabButton(QtWidgets.QPushButton):
    tab_clicked = QtCore.Signal(str)
    tab_drag_started = QtCore.Signal(QtWidgets.QWidget)
    tab_drag_moved = QtCore.Signal(QtWidgets.QWidget, QtCore.QPoint)
    tab_drag_ended = QtCore.Signal(QtWidgets.QWidget)
    tab_hover_enter = QtCore.Signal(QtWidgets.QWidget)
    tab_hover_leave = QtCore.Signal(QtWidgets.QWidget)

    def __init__(self, text, parent=None):
        super(TabButton, self).__init__(text, parent)
        self.tab_name = text
        self.setStyleSheet('''
            QPushButton {
                background-color: #4d4d4d;
                color: rgba(255, 255, 255, .5);
                border-radius: 8px;
                padding: 1px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
        ''')
        self.setFixedHeight(16)
        self.setFixedWidth(self.calculate_button_width(text))
        self.setToolTip('Select Tab')
        self.clicked.connect(self.on_clicked)
        
        self.drag_start_position = None
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.drag_start_position = event.pos()
            # DON'T emit tab_drag_started here - wait for actual drag movement
        event.accept()
        super(TabButton, self).mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & QtCore.Qt.LeftButton and self.drag_start_position:
            drag_distance = (event.pos() - self.drag_start_position).manhattanLength()
            if drag_distance >= QtWidgets.QApplication.startDragDistance():
                # Only emit drag_started when we actually start dragging
                if not hasattr(self, '_drag_active') or not self._drag_active:
                    self._drag_active = True
                    self.tab_drag_started.emit(self)
                
                # Continue with drag movement
                self.tab_drag_moved.emit(self, self.mapToParent(event.pos()))
        event.accept()
        super(TabButton, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if hasattr(self, '_drag_active') and self._drag_active:
                # We were dragging, so emit drag_ended
                self.tab_drag_ended.emit(self)
                self._drag_active = False
            elif self.drag_start_position:
                # We weren't dragging, this was just a click - emit the click signal
                # This ensures tab switching still works for simple clicks
                pass  # The clicked signal will be emitted by the parent class
            
            self.drag_start_position = None
        event.accept()
        UT.blender_main_window()
        super(TabButton, self).mouseReleaseEvent(event)

    def leaveEvent(self, event):
        # Clean up any drag state if mouse leaves the button
        if hasattr(self, '_drag_active'):
            self._drag_active = False
        self.tab_hover_leave.emit(self)
        super(TabButton, self).leaveEvent(event)

    def enterEvent(self, event):
        self.tab_hover_enter.emit(self)
        super(TabButton, self).enterEvent(event)

    def calculate_button_width(self, text, padding=10):
        font_metrics = QtGui.QFontMetrics(QtWidgets.QApplication.font())
        text_width = font_metrics.horizontalAdvance(text)
        return text_width + padding

    def on_clicked(self):
        self.tab_clicked.emit(self.tab_name)

class TabSystem(QtCore.QObject):
    tab_switched = QtCore.Signal(str)
    tab_renamed = QtCore.Signal(str, str)
    tab_deleted = QtCore.Signal(str)
    tab_reordered = QtCore.Signal()

    def __init__(self, tab_layout, add_tab_button):
        super(TabSystem, self).__init__()
        self.tab_layout = tab_layout
        self.add_tab_button = add_tab_button
        self.tabs = OrderedDict()
        self.current_tab = None
        #self.add_tab_button.clicked.connect(self.add_new_tab)
        self.dragged_tab = None
        self.hovered_tab = None
        self.drag_indicator = QtWidgets.QWidget(self.tab_layout.parentWidget())
        self.drag_indicator.setStyleSheet("background-color: #5285a6;")
        self.drag_indicator.setFixedSize(2, 16)
        self.drag_indicator.hide()
    #-----------------------------------------------------------------------------------
    def on_tab_drag_started(self, tab_button):
        self.dragged_tab = tab_button
        self.drag_indicator.raise_()
        self.drag_indicator.show()
    
    def on_tab_drag_moved(self, tab_button, pos):
        if self.dragged_tab:
            target_index = self.tab_layout.count() - 2  # Default to last position before "Add Tab" button
            last_tab_widget = self.tab_layout.itemAt(self.tab_layout.count() - 2).widget()
            
            for i in range(self.tab_layout.count() - 1):  # Exclude "Add Tab" button
                widget = self.tab_layout.itemAt(i).widget()
                if isinstance(widget, TabButton) and widget != self.dragged_tab:
                    widget_center = widget.pos().x() + widget.width() / 2
                    if pos.x() < widget_center:
                        target_index = i
                        self.drag_direction = 'left'
                        break
                    elif pos.x() >= widget_center:
                        if i == self.tab_layout.count() - 2:  # If it's the last tab
                            if pos.x() > widget.pos().x() + widget.width():
                                target_index = i + 1
                                self.drag_direction = 'right'
                            else:
                                target_index = i
                                self.drag_direction = 'left'
                        else:
                            target_index = i + 1
                            self.drag_direction = 'right'

            self.update_drag_indicator(target_index)

    def get_target_index(self, pos):
        for i in range(self.tab_layout.count() - 1):  # Exclude "Add Tab" button
            widget = self.tab_layout.itemAt(i).widget()
            if isinstance(widget, TabButton) and widget != self.dragged_tab:
                if pos.x() < widget.pos().x() + widget.width() / 2:
                    return i
        return self.tab_layout.count() - 2  # Last position before "Add Tab" button

    def on_tab_hover_enter(self, tab_button):
        if self.dragged_tab and tab_button != self.dragged_tab:
            self.hovered_tab = tab_button
            self.update_drag_indicator()

    def on_tab_hover_leave(self, tab_button):
        if self.dragged_tab and tab_button == self.hovered_tab:
            self.hovered_tab = None
            self.drag_indicator.hide()

    def update_drag_indicator(self, index):
        if index == self.tab_layout.count() - 1:
            # Position indicator at the end
            last_widget = self.tab_layout.itemAt(index - 1).widget()
            pos = last_widget.pos()
            self.drag_indicator.move(pos.x() + last_widget.width() + 1, pos.y())
        else:
            widget = self.tab_layout.itemAt(index).widget()
            pos = widget.pos()
            if self.drag_direction == 'left':
                self.drag_indicator.move(pos.x() - 1, pos.y())
            else:
                self.drag_indicator.move(pos.x() + widget.width() + 1, pos.y())
        self.drag_indicator.show()

    def on_tab_drag_ended(self, tab_button):
        if self.dragged_tab:
            drag_index = self.tab_layout.indexOf(self.dragged_tab)
            target_index = self.tab_layout.count() - 2  # Default to last position before "Add Tab" button

            for i in range(self.tab_layout.count() - 1):  # Exclude "Add Tab" button
                widget = self.tab_layout.itemAt(i).widget()
                if isinstance(widget, TabButton) and widget != self.dragged_tab:
                    widget_center = widget.pos().x() + widget.width() / 2
                    if self.drag_indicator.x() < widget_center:
                        target_index = i
                        break
                    elif self.drag_indicator.x() >= widget_center:
                        target_index = i + 1

            if drag_index != target_index:
                # Remove the dragged tab from its current position
                self.tab_layout.removeWidget(self.dragged_tab)
                
                # Insert the dragged tab at the new position
                if target_index > drag_index:
                    target_index -= 1  # Adjust target index if moving right
                self.tab_layout.insertWidget(target_index, self.dragged_tab)
                
                # Reorder tabs in the data structure
                self.reorder_tabs()

            self.dragged_tab = None
            self.drag_indicator.hide()
    #-----------------------------------------------------------------------------------
    def add_tab(self, tab_name, switch=False):
        if tab_name not in self.tabs:
            tab_button = TabButton(tab_name)
            tab_button.tab_clicked.connect(lambda: self.switch_tab(tab_name))
            tab_button.tab_drag_started.connect(self.on_tab_drag_started)
            tab_button.tab_drag_moved.connect(self.on_tab_drag_moved)
            tab_button.tab_drag_ended.connect(self.on_tab_drag_ended)
            tab_button.tab_hover_enter.connect(self.on_tab_hover_enter)
            tab_button.tab_hover_leave.connect(self.on_tab_hover_leave)
            tab_button.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            tab_button.customContextMenuRequested.connect(self.on_tab_context_menu_requested)
            self.tab_layout.insertWidget(self.tab_layout.count() - 1, tab_button)
            self.tabs[tab_name] = {
                'button': tab_button,
                'canvas': PC.PickerCanvas(),
                'image_path': None,
                'image_opacity': 1.0,
                'namespace': 'None'  # Initialize with default namespace
            }
            if switch or not self.current_tab:
                self.switch_tab(tab_name)

    def add_new_tab(self):
        '''new_tab_name, ok = QtWidgets.QInputDialog.getText(None, "New Tab", "Enter tab name:")
        if ok and new_tab_name:
            self.add_tab(new_tab_name, switch=True)
            
            # Update PickerToolData
            DM.PickerDataManager.add_tab(new_tab_name)'''
        
        # Get the parent widget (the window/widget containing the tab system)
        parent_widget = self.tab_layout.parentWidget()
        dialog = CD.CustomDialog(parent_widget, "New Tab", (180, 100))
        dialog.add_widget(QtWidgets.QLabel("Enter tab name:"))
        input_field = QtWidgets.QLineEdit()
        dialog.add_widget(input_field)
        dialog.add_button_box()

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            new_tab_name = input_field.text()
            if new_tab_name:
                self.add_tab(new_tab_name, switch=True)
                DM.PickerDataManager.add_tab(new_tab_name)

    def rename_tab(self, button):
        old_name = button.text()
        parent_widget = self.tab_layout.parentWidget()
        
        dialog = CD.CustomDialog(parent_widget, "Rename Tab", (180, 100))
        dialog.add_widget(QtWidgets.QLabel("Enter new tab name:"))
        input_field = QtWidgets.QLineEdit(old_name)
        dialog.add_widget(input_field)
        dialog.add_button_box()

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            new_name = input_field.text()
            if new_name and new_name != old_name and new_name not in self.tabs:
                new_tabs = OrderedDict()
                for tab_name, tab_data in self.tabs.items():
                    if tab_name == old_name:
                        new_tabs[new_name] = tab_data
                    else:
                        new_tabs[tab_name] = tab_data
                self.tabs = new_tabs

                button.setText(new_name)
                button.setFixedWidth(button.calculate_button_width(new_name))
                button.tab_clicked.disconnect()
                button.tab_clicked.connect(lambda: self.switch_tab(new_name))
                button.tab_name = new_name
                
                if self.current_tab == old_name:
                    self.current_tab = new_name
                
                DM.PickerDataManager.rename_tab(old_name, new_name)
                self.tab_renamed.emit(old_name, new_name)
                self.update_tab_order()

    def delete_tab(self, button):
        tab_name = button.text()
        parent_widget = self.tab_layout.parentWidget()
        
        if len(self.tabs) <= 1:
            dialog = CD.CustomDialog(parent_widget, "Cannot Delete", (200, 100))
            dialog.add_widget(QtWidgets.QLabel("You must have at least one tab."))
            accept_button, _ = dialog.add_button_box()
            accept_button.setText("OK")
            dialog.exec_()
            return

        dialog = CD.CustomDialog(parent_widget, "Confirm Delete", (180, 80))
        label = QtWidgets.QLabel(f"Delete tab <b><font color='#00ade6'>'{tab_name}'</font></b>?")
        label.setAlignment(QtCore.Qt.AlignCenter)
        dialog.add_widget(label)
        accept_button, close_button = dialog.add_button_box()
        accept_button.setText("Yes")
        close_button.setText("No")

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            del self.tabs[tab_name]
            self.tab_layout.removeWidget(button)
            button.deleteLater()
            
            if self.current_tab == tab_name:
                self.current_tab = next(iter(self.tabs))
            
            self.update_tab_buttons()
            DM.PickerDataManager.delete_tab(tab_name)
            self.tab_deleted.emit(tab_name)
    #-----------------------------------------------------------------------------------
    def reorder_tabs(self):
        new_order = OrderedDict()
        for i in range(self.tab_layout.count() - 1):  # Exclude "Add Tab" button
            widget = self.tab_layout.itemAt(i).widget()
            if isinstance(widget, TabButton):
                new_order[widget.tab_name] = self.tabs[widget.tab_name]
        
        self.tabs = new_order
        
        # Update the PickerDataManager
        DM.PickerDataManager.reorder_tabs(list(self.tabs.keys()))
        
        # Update the UI to reflect the new order
        self.update_tab_order()
        self.tab_reordered.emit()
    
    def update_tab_order(self):
            # Remove all tab buttons from the layout
            for i in reversed(range(self.tab_layout.count() - 1)):  # -1 to keep the add button
                widget = self.tab_layout.itemAt(i).widget()
                if isinstance(widget, TabButton):
                    self.tab_layout.removeWidget(widget)

            # Add tab buttons back in the correct order
            for tab_name in self.tabs.keys():
                self.tab_layout.insertWidget(self.tab_layout.count() - 1, self.tabs[tab_name]['button'])

            self.update_tab_buttons()

    def switch_tab(self, tab_name):
        if tab_name in self.tabs:
            self.current_tab = tab_name
            self.update_tab_buttons()
            self.tab_switched.emit(tab_name)

    def update_tab_buttons(self):
        for tab_name, tab_data in self.tabs.items():
            button = tab_data['button']
            if tab_name == self.current_tab:
                button.setStyleSheet('''
                    QPushButton {
                        background-color: #3096bb;
                        font-weight: bold;
                        color: white;
                        border-radius: 8px;
                        padding: 0px 0px 1px 0px;
                        font-size: 10px;
                    }
                ''')
            else:
                button.setStyleSheet('''
                    QPushButton {
                        background-color: #444444;
                        color: rgba(255, 255, 255, .5);
                        border-radius: 8px;
                        padding: 0px 0px 1px 0px;
                        font-size: 10px;
                    }
                ''')
    #-----------------------------------------------------------------------------------
    def clear_all_tabs(self):
        # Remove all tab buttons and clear the tabs dictionary
        for i in reversed(range(self.tab_layout.count() - 1)):  # -1 to keep the add button
            widget = self.tab_layout.itemAt(i).widget()
            if isinstance(widget, TabButton):
                self.tab_layout.removeWidget(widget)
                widget.deleteLater()
        
        # Clear the tabs dictionary
        self.tabs.clear()
        self.current_tab = None

    def setup_tabs(self):
        data = DM.PickerDataManager.get_data()
        for tab_name in data['tabs']:
            self.add_tab(tab_name, switch=False)
    
    def on_tab_context_menu_requested(self, pos):
        button = self.sender()
        self.show_tab_context_menu(pos, button)

    def show_tab_context_menu(self, pos, button):
        menu = QtWidgets.QMenu()
        menu.setWindowFlags(menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
        menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        menu.setStyleSheet('''
            QMenu {
                background-color: rgba(30, 30, 30, .9);
                border: 1px solid #444444;
                border-radius: 3px;
                padding: 5px 7px;
            }
            QMenu::item {
                background-color: transparent;
                padding: 3px 10px 3px 3px; ;
                margin: 3px 0px  ;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #444444;
            }
            QMenu::item:disabled {
                padding-left: 0px;
                color: #888888;
            }''')
        
        #label = menu.addAction("Tab Options")
        #label.setEnabled(False)
        
        #menu.addSeparator()
        rename_action = menu.addAction(QtGui.QIcon(UT.get_icon("rename.png")),"Rename Tab")
        delete_action = menu.addAction(QtGui.QIcon(UT.get_icon("delete_red.png")),"Delete Tab")

        action = menu.exec_(button.mapToGlobal(pos))

        if action == rename_action:
            self.rename_tab(button)
        elif action == delete_action:
            self.delete_tab(button)

    