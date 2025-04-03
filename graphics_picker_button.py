try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtGui import QColor
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtGui import QColor
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
    from shiboken2 import wrapInstance

import math
import maya.cmds as cmds
from . import utils as UT
from . import script_manager as SM
from . import tool_functions as TF

class PickerButtonItem(QtWidgets.QGraphicsObject):
    deleted = Signal(object)
    selected = Signal(object, bool)
    changed = Signal(object)
    
    def __init__(self, label, parent=None, unique_id=None, color='#444444', opacity=1, width=80, height=30):
        super().__init__(parent)
        self.label = label
        self.unique_id = unique_id
        self.color = color
        self.opacity = opacity
        self.width = width
        self.height = height
        self.radius = [3, 3, 3, 3]  # [top_left, top_right, bottom_right, bottom_left]
        self.is_selected = False
        self.edit_mode = False
        self.assigned_objects = []
        self.mode = 'select'  # 'select' or 'script'
        self.script_data = {}
        
        # Enable flags for better performance
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsSelectable)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, False)  # We'll handle movement manually
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        self.setCacheMode(QtWidgets.QGraphicsItem.DeviceCoordinateCache)  # Cache rendering
        
        # Set tooltip
        self.setToolTip(f"Select Set\nID: [{self.unique_id}]")
        
        # Accept hover events
        self.setAcceptHoverEvents(True)
        
        # Track dragging state
        self.dragging = False
        self.drag_start_pos = None
        self.button_start_pos = None
    
    def boundingRect(self):
        # Return the bounding rectangle of the button
        return QtCore.QRectF(-self.width/2, -self.height/2, self.width, self.height)
    
    def paint(self, painter, option, widget):
        # Paint the button (similar to the current paintEvent)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        
        # Create path with rounded corners
        path = QtGui.QPainterPath()
        rect = self.boundingRect()
        
        # Apply radius
        tl = self.radius[0]
        tr = self.radius[1]
        br = self.radius[2]
        bl = self.radius[3]
        
        # Create the path with adjusted radii
        path.moveTo(rect.left() + tl, rect.top())
        path.lineTo(rect.right() - tr, rect.top())
        path.arcTo(rect.right() - 2*tr, rect.top(), 2*tr, 2*tr, 90, -90)
        path.lineTo(rect.right(), rect.bottom() - br)
        path.arcTo(rect.right() - 2*br, rect.bottom() - 2*br, 2*br, 2*br, 0, -90)
        path.lineTo(rect.left() + bl, rect.bottom())
        path.arcTo(rect.left(), rect.bottom() - 2*bl, 2*bl, 2*bl, -90, -90)
        path.lineTo(rect.left(), rect.top() + tl)
        path.arcTo(rect.left(), rect.top(), 2*tl, 2*tl, 180, -90)
        
        # Draw button background
        if not self.is_selected:
            painter.setBrush(QtGui.QColor(self.color))
        else:
            painter.setBrush(QtGui.QColor(255, 255, 255, 120))
        
        painter.setOpacity(self.opacity)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawPath(path)
        
        # Draw selection border if selected
        if self.is_selected:
            if self.edit_mode:
                painter.setBrush(QtGui.QColor(self.color))
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 2)
                pen.setCosmetic(True)  # Ensures the pen width is always 2 pixels regardless of zoom
                painter.setPen(pen)
                painter.drawPath(path)
            else:   
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 120), 1)
                pen.setCosmetic(True)  # Ensures the pen width is always 2 pixels regardless of zoom
                painter.setPen(pen)
                painter.drawPath(path)
        
        # Draw text
        painter.setOpacity(1.0)  # Reset opacity for text
        painter.setPen(QtGui.QColor('white'))
        font = painter.font()
        font_size = self.height * 0.5
        font.setPixelSize(int(font_size))
        painter.setFont(font)
        
        # Draw text centered
        painter.drawText(rect, QtCore.Qt.AlignCenter, self.label)
    
    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            view = self.scene().views()[0] if self.scene() and self.scene().views() else None
            if not view:
                return
                
            if self.edit_mode:
                # Start dragging in edit mode
                self.dragging = True
                self.drag_start_pos = event.scenePos()
                self.button_start_pos = self.pos()
                
                # Handle selection
                shift_held = event.modifiers() & QtCore.Qt.ShiftModifier
                if not self.is_selected and not shift_held:
                    view.clear_selection()
                    self.is_selected = True
                    self.selected.emit(self, True)
                    view.last_selected_button = self
                    self.update()
                elif shift_held:
                    self.is_selected = not self.is_selected
                    if self.is_selected:
                        view.last_selected_button = self
                    self.selected.emit(self, self.is_selected)
                    self.update()
                
                # Store start positions for all selected buttons
                for button in view.get_selected_buttons():
                    button.button_start_pos = button.pos()
            else:
                if self.mode == 'select':
                    # Handle selection in normal mode
                    shift_held = event.modifiers() & QtCore.Qt.ShiftModifier
                    if not shift_held:
                        view.clear_selection()
                    
                    self.is_selected = not self.is_selected if shift_held else True
                    self.update()
                    
                    # Apply selection to Maya
                    view.apply_final_selection(shift_held)
                else:
                    # Execute script
                    self.execute_script_command()
            
            event.accept()
        elif event.button() == QtCore.Qt.RightButton:
            # Show context menu
            if not self.is_selected:
                view = self.scene().views()[0] if self.scene() and self.scene().views() else None
                if view:
                    view.clear_selection()
                    self.toggle_selection()
            
            self.show_context_menu(event.screenPos())
            event.accept()
        else:
            super().mousePressEvent(event)
        
        # Activate Maya window
        UT.maya_main_window().activateWindow()
    
    def mouseMoveEvent(self, event):
        if self.dragging and (event.buttons() & QtCore.Qt.LeftButton):
            view = self.scene().views()[0] if self.scene() and self.scene().views() else None
            if not view:
                return
                
            # Calculate the delta in scene coordinates
            delta = event.scenePos() - self.drag_start_pos
            
            # Move all selected buttons
            for button in view.get_selected_buttons():
                if hasattr(button, 'button_start_pos') and button.button_start_pos is not None:
                    button.setPos(button.button_start_pos + delta)
            
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.dragging:
            self.dragging = False
            self.drag_start_pos = None
            
            # Notify about position change
            self.changed.emit(self)
            
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def toggle_selection(self):
        self.is_selected = not self.is_selected
        self.selected.emit(self, self.is_selected)
        self.update()
    
    def set_selected(self, selected):
        if self.is_selected != selected:
            self.is_selected = selected
            self.update()
    
    def update_tooltip(self):
        if self.mode == 'select':
            # Create tooltip for selection mode
            objects_str = ""
            if self.assigned_objects:
                objects_str = "\n\nObjects:\n"
                for i, obj_data in enumerate(self.assigned_objects[:5]):
                    if 'long_name' in obj_data:
                        name = obj_data['long_name'].split('|')[-1].split(':')[-1]
                        objects_str += f"- {name}\n"
                
                if len(self.assigned_objects) > 5:
                    objects_str += f"...and {len(self.assigned_objects) - 5} more"
            
            self.setToolTip(f"Label: {self.label}\nMode: Select{objects_str}\nID: [{self.unique_id}]")
        else:
            # Create tooltip for script mode
            script_type = self.script_data.get('language', 'Python')
            self.setToolTip(f"Label: {self.label}\nMode: Script ({script_type})\nID: [{self.unique_id}]")
    
    def execute_script_command(self):
        if self.mode == 'script' and self.script_data:
            language = self.script_data.get('language', 'python')
            script = self.script_data.get('script', '')
            
            if not script:
                return
                
            # Get namespace from main window if available
            namespace = ''
            view = self.scene().views()[0] if self.scene() and self.scene().views() else None
            if view:
                main_window = view.window()
                if hasattr(main_window, 'namespace_dropdown'):
                    namespace = main_window.namespace_dropdown.currentText()
                    if namespace == 'None':
                        namespace = ''
            
            # Replace namespace token in script
            if namespace:
                script = script.replace('$NAMESPACE', namespace)
            else:
                script = script.replace('$NAMESPACE:', '')
            
            # Execute the script
            if language.lower() == 'python':
                try:
                    exec(script)
                except Exception as e:
                    cmds.warning(f"Error executing Python script: {e}")
            elif language.lower() == 'mel':
                try:
                    import maya.mel as mel
                    mel.eval(script)
                except Exception as e:
                    cmds.warning(f"Error executing MEL script: {e}")
    
    def set_mode(self, mode):
        self.mode = mode
        self.update_tooltip()
    
    def set_script_data(self, data):
        self.script_data = data.copy() if data else {}
        self.update_tooltip()
    
    def set_size(self, width, height):
        self.prepareGeometryChange()
        self.width = width
        self.height = height
        self.update()
        self.changed.emit(self)
    
    def set_radius(self, top_left, top_right, bottom_right, bottom_left):
        self.radius = [top_left, top_right, bottom_right, bottom_left]
        self.update()
        self.changed.emit(self)
    
    def change_color(self, color):
        self.color = color
        self.update()
        self.changed.emit(self)
    
    def change_opacity(self, value):
        self.opacity = value
        self.update()
        self.changed.emit(self)
    
    def rename_button(self, new_label):
        self.label = new_label
        self.update()
        self.update_tooltip()
        self.changed.emit(self)
    
    def delete_button(self):
        self.deleted.emit(self)
    
    def add_selected_objects(self):
        selected = cmds.ls(selection=True, long=True)
        if not selected:
            return
        
        # Store both UUID and long name for each object
        for obj in selected:
            try:
                uuid = cmds.ls(obj, uuid=True)[0]
                # Check if object is already assigned
                if not any(data.get('uuid') == uuid for data in self.assigned_objects):
                    self.assigned_objects.append({
                        'uuid': uuid,
                        'long_name': obj
                    })
            except Exception as e:
                cmds.warning(f"Error getting UUID for {obj}: {e}")
        
        self.update_tooltip()
        self.changed.emit(self)
    
    def remove_all_objects(self):
        self.assigned_objects = []
        self.update_tooltip()
        self.changed.emit(self)
    
    def show_context_menu(self, position):
        view = self.scene().views()[0] if self.scene() and self.scene().views() else None
        if not view:
            return
            
        # Create context menu
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
                background-color: #2c4759;
            }''')
        
        if self.edit_mode:
            # Edit mode context menu
            rename_action = menu.addAction("Rename")
            rename_action.triggered.connect(lambda: view.rename_button_dialog(self))
            
            color_menu = menu.addMenu("Change Color")
            colors = ['#444444', '#5285a6', '#91cb08', '#cb0891', '#cb4f08', '#ff0000', '#00ff00', '#0000ff']
            for color in colors:
                color_action = color_menu.addAction("")
                color_action.setIcon(UT.create_color_icon(color))
                color_action.triggered.connect(lambda checked, c=color: self.change_color(c))
            
            menu.addSeparator()
            
            if self.mode == 'select':
                # Selection mode options
                add_objects_action = menu.addAction("Add Selected Objects")
                add_objects_action.triggered.connect(self.add_selected_objects)
                
                remove_objects_action = menu.addAction("Remove All Objects")
                remove_objects_action.triggered.connect(self.remove_all_objects)
                
                menu.addSeparator()
                
                script_mode_action = menu.addAction("Switch to Script Mode")
                script_mode_action.triggered.connect(lambda: self.set_mode('script'))
            else:
                # Script mode options
                edit_script_action = menu.addAction("Edit Script")
                edit_script_action.triggered.connect(lambda: view.show_script_manager(self))
                
                select_mode_action = menu.addAction("Switch to Select Mode")
                select_mode_action.triggered.connect(lambda: self.set_mode('select'))
            
            menu.addSeparator()
            
            delete_action = menu.addAction("Delete Button")
            delete_action.triggered.connect(self.delete_button)
        else:
            # Normal mode context menu
            if self.mode == 'select':
                select_action = menu.addAction("Select Objects")
                select_action.triggered.connect(lambda: view.apply_final_selection(False))
            else:
                execute_action = menu.addAction("Execute Script")
                execute_action.triggered.connect(self.execute_script_command)
        
        # Show the menu at the specified position
        menu.exec_(position.toPoint())
