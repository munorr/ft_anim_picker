from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
from shiboken6 import wrapInstance

import os

from .import picker_canvas as PC
from . import data_management as DM
from . import custom_dialog as CD
from . import bpicker_format as BPF
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
        QToolTip {{background-color: #222222; color: #eeeeee ; border: 1px solid rgba(255,255,255,.2); padding: 0px;}}
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
        #UT.blender_main_window()
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
        from .new_tab_dialog import NewTabDialog

        parent_widget = self.tab_layout.parentWidget()
        top_window = parent_widget.window() if parent_widget else None
        result = NewTabDialog.show(top_window)
        if result is None:
            return

        tab_name = result["tab_name"]
        template_path = result.get("template_path")

        if not tab_name:
            return

        if template_path:
            self._add_tab_from_template(tab_name, template_path)
        else:
            self.add_tab(tab_name, switch=True)
            DM.PickerDataManager.add_tab(tab_name)

    def _add_tab_from_template(self, tab_name, template_path):
        """Load the first tab from a template .bpicker and add it as a new tab."""
        import shutil
        import uuid

        try:
            info = BPF.BPickerArchive.read(template_path)
            manifest = info["manifest"]
            template_tabs = manifest.get("tabs", {})
        except Exception as e:
            print(f"[tab_system] Failed to read template: {e}")
            self.add_tab(tab_name, switch=True)
            DM.PickerDataManager.add_tab(tab_name)
            return

        if not template_tabs:
            self.add_tab(tab_name, switch=True)
            DM.PickerDataManager.add_tab(tab_name)
            return

        # Take the first tab from the template
        source_tab_name, source_tab_data = next(iter(template_tabs.items()))

        # Extract template to temp, copy media into active session
        session = DM.PickerDataManager.get_active_session()
        source_temp = BPF.BPickerArchive.extract_to_temp(template_path)

        try:
            if session:
                from . import picker_io as PIO
                tab_data = PIO._remap_imported_media(
                    dict(source_tab_data), source_temp, session
                )
            else:
                # Convert manifest paths to bpicker:// format
                converted = BPF.build_picker_data_from_manifest(
                    {"tabs": {tab_name: source_tab_data}}
                )
                tab_data = converted["tabs"].get(tab_name, source_tab_data)
        finally:
            shutil.rmtree(source_temp, ignore_errors=True)

        # Normalize button data to PickerDataManager format
        self._normalize_buttons(tab_data)

        # Add data FIRST so it's ready when on_tab_switched reads it
        DM.PickerDataManager.add_tab(tab_name)
        DM.PickerDataManager.update_tab_data(tab_name, tab_data)

        # Now create the UI tab and switch (triggers create_buttons which reads data)
        self.add_tab(tab_name, switch=True)

    @staticmethod
    def _normalize_buttons(tab_data):
        """Ensure buttons have the fields _create_single_button expects."""
        import uuid
        for btn in tab_data.get("buttons", []):
            # Generate id if missing
            if "id" not in btn:
                btn["id"] = str(uuid.uuid4())[:8]

            # Convert x/y to position tuple
            if "position" not in btn and ("x" in btn or "y" in btn):
                btn["position"] = (btn.pop("x", 0), btn.pop("y", 0))
            elif "position" not in btn:
                btn["position"] = (0, 0)

            # Convert float-list color [r,g,b] to hex string
            c = btn.get("color")
            if isinstance(c, (list, tuple)) and len(c) >= 3:
                if all(isinstance(v, float) and v <= 1.0 for v in c):
                    btn["color"] = "#{:02x}{:02x}{:02x}".format(
                        int(c[0] * 255), int(c[1] * 255), int(c[2] * 255)
                    )

            # Ensure defaults for required fields
            btn.setdefault("opacity", 1.0)
            btn.setdefault("radius", [3, 3, 3, 3])
            btn.setdefault("assigned_objects", [])

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
            dialog = CD.CustomDialog(self, "Cannot Delete", (200, 100))
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
                        background-color: rgba(255, 255, 255, .2);
                        font-weight: bold;
                        color: white;
                        border-radius: 8px;
                        padding: 0px 0px 1px 0px;
                        font-size: 10px;
                    }
                }
                    QToolTip {{background-color: #222222; color: #eeeeee ; border: 1px solid rgba(255,255,255,.2); padding: 0px;}}
                ''')
            else:
                button.setStyleSheet('''
                    QPushButton {
                        background-color: rgba(255, 255, 255, 0);
                        color: rgba(255, 255, 255, .5);
                        border-radius: 8px;
                        padding: 0px 0px 1px 0px;
                        font-size: 10px;
                    }
                    QPushButton:hover {
                        color: rgba(255, 255, 255, .8);
                    }
                QToolTip {{background-color: #222222; color: #eeeeee ; border: 1px solid rgba(255,255,255,.2); padding: 0px;}}
                ''')
    #-----------------------------------------------------------------------------------
    def clear_all_tabs(self):
        """OPTIMIZED: Properly cleanup all canvases and buttons before clearing tabs"""
        # First, cleanup all canvases and their buttons
        for tab_name, tab_data in list(self.tabs.items()):
            canvas = tab_data.get('canvas')
            if canvas:
                # Cleanup all buttons in the canvas
                for button in list(canvas.buttons):
                    try:
                        # Disconnect signals to prevent memory leaks
                        button.setParent(None)
                        button.deleteLater()
                    except (RuntimeError, AttributeError):
                        pass
                
                # Clear the buttons list
                canvas.buttons.clear()
                
                # Disconnect canvas signals
                try:
                    canvas.button_selection_changed.disconnect()
                    canvas.clicked.disconnect()
                except:
                    pass
                
                # Remove canvas from parent and delete
                canvas.setParent(None)
                canvas.deleteLater()
        
        # Now remove all tab buttons from layout
        for i in reversed(range(self.tab_layout.count() - 1)):  # -1 to keep the add button
            widget = self.tab_layout.itemAt(i).widget()
            if isinstance(widget, TabButton):
                self.tab_layout.removeWidget(widget)
                widget.deleteLater()
        
        # Clear the tabs dictionary
        self.tabs.clear()
        self.current_tab = None
        
        # Force Qt to process deletion events
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()

    def setup_tabs(self):
        data = DM.PickerDataManager.get_data()
        for tab_name in data['tabs']:
            self.add_tab(tab_name, switch=False)
    
    def on_tab_context_menu_requested(self, pos):
        button = self.sender()
        self.show_tab_context_menu(pos, button)

    def show_tab_context_menu(self, pos, button):
        menu = UT.create_styled_menu()
        
        rename_action = menu.addAction(QtGui.QIcon(UT.get_icon("rename.png")), "Rename Tab")
        delete_action = menu.addAction(QtGui.QIcon(UT.get_icon("delete_red.png")), "Delete Tab")
        menu.addSeparator()
        export_action = menu.addAction(QtGui.QIcon(UT.get_icon("save.png")), "Export Tab...")
        import_action = menu.addAction(QtGui.QIcon(UT.get_icon("load.png")), "Import Tab...")
        menu.addSeparator()
        save_template_action = menu.addAction(QtGui.QIcon(UT.get_icon("add.png")), "Save as Template")

        action = menu.exec_(button.mapToGlobal(pos))

        if action == rename_action:
            self.rename_tab(button)
        elif action == delete_action:
            self.delete_tab(button)
        elif action == export_action:
            self._export_tab(button)
        elif action == import_action:
            self._import_tab()
        elif action == save_template_action:
            self._save_tab_as_template(button)

    # ── Tab Export / Import ────────────────────────────────────────────
    def _export_tab(self, button):
        """Export the clicked tab as a standalone .bpicker file."""
        from . import picker_io as PIO
        tab_name = button.tab_name
        parent_widget = self.tab_layout.parentWidget()

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            parent_widget,
            f"Export Tab '{tab_name}'",
            os.path.expanduser(f"~/{tab_name}.bpicker"),
            "BPicker Files (*.bpicker)"
        )
        if file_path:
            PIO.export_tab_as_bpicker(tab_name, file_path)

    def _import_tab(self):
        """Import tabs from a .bpicker file into the current picker."""
        from . import picker_io as PIO
        parent_widget = self.tab_layout.parentWidget()

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            parent_widget,
            "Import Tab from BPicker",
            os.path.expanduser("~"),
            "BPicker Files (*.bpicker)"
        )
        if not file_path:
            return

        imported_tabs = PIO.import_tabs_from_bpicker(file_path)
        for tab_name in imported_tabs:
            if tab_name not in self.tabs:
                self.add_tab(tab_name, switch=False)
        if imported_tabs:
            self.switch_tab(imported_tabs[-1])
            self.tab_reordered.emit()

    def _save_tab_as_template(self, button):
        """Save the clicked tab as a template .bpicker in the templates folder."""
        from . import picker_io as PIO
        from .config.settings import TEMPLATE_DIR

        tab_name = button.tab_name
        os.makedirs(str(TEMPLATE_DIR), exist_ok=True)

        # Sanitize filename
        safe_name = tab_name.strip()
        for ch in r'<>:"/\|?*':
            safe_name = safe_name.replace(ch, '_')
        dest_path = os.path.join(str(TEMPLATE_DIR), f"{safe_name}.bpicker")

        if PIO.export_tab_as_bpicker(tab_name, dest_path):
            # Capture canvas preview and inject into the archive
            if self.current_tab == tab_name:
                canvas = self.tabs[tab_name]['canvas']
                try:
                    import tempfile
                    preview_path = os.path.join(tempfile.gettempdir(), "template_preview.png")
                    pixmap = canvas.grab()
                    scaled = pixmap.scaled(256, 256, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
                    scaled.save(preview_path, "PNG")
                    BPF.BPickerArchive.add_media(dest_path, "cache/preview.png", open(preview_path, 'rb').read())
                    os.remove(preview_path)
                except Exception as e:
                    print(f"[tab_system] Could not capture template preview: {e}")

            print(f"[tab_system] Saved tab '{tab_name}' as template: {dest_path}")

