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
import maya.OpenMayaUI as omui
import uuid

from . import utils as UT
from . import tool_functions as TF
from .graphics_picker_button import PickerButtonItem

class PickerGraphicsView(QtWidgets.QGraphicsView):
    button_selection_changed = Signal()
    button_changed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Create scene
        self.scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene)
        
        # Set up view properties
        self.setRenderHint(QtGui.QPainter.Antialiasing)
        self.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        self.setRenderHint(QtGui.QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.MinimalViewportUpdate)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        
        # Set background color
        self.setBackgroundBrush(QtGui.QBrush(QtGui.QColor(50, 50, 50)))
        
        # Track buttons
        self.buttons = []
        self.last_selected_button = None
        
        # Track edit mode
        self.edit_mode = False
        
        # Track mouse panning
        self.panning = False
        self.pan_start_pos = None
        
        # Setup rubber band selection
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        self.rubber_band_active = False
        self.rubber_band_origin = None
        self.rubber_band = None
        
        # Set up zoom limits
        self.zoom_min = 0.1
        self.zoom_max = 10.0
        self.zoom_factor = 1.0
        
        # Initialize HUD
        self.hud_widget = HUDWidget(self)
        self.hud_widget.hide()  # Hide initially, will be shown when needed
        
        # Timer for selection updates
        self.selection_timer = QTimer(self)
        self.selection_timer.setSingleShot(True)
        self.selection_timer.timeout.connect(self.apply_final_selection)
        
        # Set viewport to accept mouse tracking for hover effects
        self.setMouseTracking(True)
        
        # Initialize with a default zoom level
        self.reset_view()
    
    def reset_view(self):
        """Reset the view to default zoom and position"""
        self.resetTransform()
        self.zoom_factor = 1.0
        self.centerOn(0, 0)
        self.update()
    
    def add_button(self, label, pos=None, unique_id=None, color='#444444', opacity=1.0, width=80, height=30):
        """Add a new button to the scene"""
        if unique_id is None:
            unique_id = str(uuid.uuid4())
            
        button = PickerButtonItem(label, unique_id=unique_id, color=color, opacity=opacity, width=width, height=height)
        button.edit_mode = self.edit_mode
        
        # Connect signals
        button.deleted.connect(self.remove_button)
        button.selected.connect(self.handle_button_selection)
        button.changed.connect(self.handle_button_changed)
        
        # Add to scene
        self.scene.addItem(button)
        
        # Position the button
        if pos is None:
            # Default to center of view if no position specified
            view_center = self.mapToScene(self.viewport().rect().center())
            button.setPos(view_center)
        else:
            button.setPos(pos)
        
        # Add to our list
        self.buttons.append(button)
        
        # Update tooltip
        button.update_tooltip()
        
        return button
    
    def remove_button(self, button):
        """Remove a button from the scene"""
        if button in self.buttons:
            self.buttons.remove(button)
            self.scene.removeItem(button)
            self.button_changed.emit()
    
    def clear_all_buttons(self):
        """Remove all buttons from the scene"""
        for button in list(self.buttons):  # Create a copy of the list to safely iterate
            self.remove_button(button)
    
    def get_selected_buttons(self):
        """Get all currently selected buttons"""
        return [button for button in self.buttons if button.is_selected]
    
    def clear_selection(self):
        """Clear selection of all buttons"""
        for button in self.buttons:
            if button.is_selected:
                button.is_selected = False
                button.update()
        
        self.last_selected_button = None
        self.button_selection_changed.emit()
    
    def select_all_buttons(self):
        """Select all buttons"""
        for button in self.buttons:
            if not button.is_selected:
                button.is_selected = True
                button.update()
        
        if self.buttons:
            self.last_selected_button = self.buttons[-1]
        
        self.button_selection_changed.emit()
    
    def handle_button_selection(self, button, selected):
        """Handle button selection change"""
        if selected:
            self.last_selected_button = button
        
        self.button_selection_changed.emit()
    
    def handle_button_changed(self, button):
        """Handle button property changes"""
        self.button_changed.emit()
    
    def set_edit_mode(self, enabled):
        """Set edit mode for all buttons"""
        self.edit_mode = enabled
        
        for button in self.buttons:
            button.edit_mode = enabled
            button.update()
        
        # Show/hide HUD based on edit mode
        if enabled:
            self.hud_widget.show()
        else:
            self.hud_widget.hide()
            self.clear_selection()
    
    def apply_final_selection(self, shift_held=False):
        """Apply the final selection to Maya"""
        if self.edit_mode:
            return
            
        # Collect all objects from selected buttons
        objects_to_select = []
        for button in self.buttons:
            if button.is_selected and button.mode == 'select':
                for obj_data in button.assigned_objects:
                    # Try to get the object by UUID first
                    uuid_str = obj_data.get('uuid')
                    if uuid_str:
                        try:
                            obj = cmds.ls(uuid_str, long=True)
                            if obj:
                                objects_to_select.append(obj[0])
                                continue
                        except Exception:
                            pass
                    
                    # Fall back to long name
                    long_name = obj_data.get('long_name')
                    if long_name and cmds.objExists(long_name):
                        objects_to_select.append(long_name)
        
        # Apply selection in Maya
        if objects_to_select:
            if shift_held:
                # Add to current selection
                current_sel = cmds.ls(selection=True, long=True) or []
                cmds.select(current_sel + objects_to_select, add=True)
            else:
                # Replace selection
                cmds.select(objects_to_select, replace=True)
        elif not shift_held:
            # Clear selection if no objects and not shift-selecting
            cmds.select(clear=True)
        
        # Update HUD
        self.hud_widget.update_selection_count()
    
    def rename_button_dialog(self, button):
        """Show dialog to rename a button"""
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Rename Button")
        dialog.setMinimumWidth(250)
        
        layout = QtWidgets.QVBoxLayout(dialog)
        
        # Add line edit for new name
        name_edit = QtWidgets.QLineEdit(button.label)
        layout.addWidget(name_edit)
        
        # Add buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(button_box)
        
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        
        # Show dialog and process result
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            new_name = name_edit.text().strip()
            if new_name:
                button.rename_button(new_name)
    
    def show_script_manager(self, button):
        """Show script manager dialog for a button"""
        from . import script_manager as SM
        
        # Create and show script manager
        script_manager = SM.ScriptManager(self)
        script_manager.set_button(button)
        script_manager.exec_()
    
    def wheelEvent(self, event):
        """Handle mouse wheel events for zooming"""
        # Get the position before scaling, in scene coordinates
        old_pos = self.mapToScene(event.position().toPoint() if hasattr(event, 'position') else event.pos())
        
        # Get zoom factor
        zoom_in_factor = 1.15
        zoom_out_factor = 1 / zoom_in_factor
        
        # Set zoom based on wheel direction
        if event.angleDelta().y() > 0:
            zoom_factor = zoom_in_factor
        else:
            zoom_factor = zoom_out_factor
        
        # Calculate new zoom level
        new_zoom = self.zoom_factor * zoom_factor
        
        # Enforce zoom limits
        if new_zoom < self.zoom_min:
            zoom_factor = self.zoom_min / self.zoom_factor
            new_zoom = self.zoom_min
        elif new_zoom > self.zoom_max:
            zoom_factor = self.zoom_max / self.zoom_factor
            new_zoom = self.zoom_max
        
        # Update zoom factor
        self.zoom_factor = new_zoom
        
        # Scale the view
        self.scale(zoom_factor, zoom_factor)
        
        # Get the position after scaling
        new_pos = self.mapToScene(event.position().toPoint() if hasattr(event, 'position') else event.pos())
        
        # Move scene to old position
        delta = new_pos - old_pos
        self.translate(delta.x(), delta.y())
        
        # Accept the event
        event.accept()
    
    def mousePressEvent(self, event):
        """Handle mouse press events"""
        if event.button() == QtCore.Qt.MiddleButton:
            # Start panning with middle mouse button
            self.panning = True
            self.pan_start_pos = event.pos()
            self.setCursor(QtCore.Qt.ClosedHandCursor)
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton and self.edit_mode:
            # Start rubber band selection in edit mode
            if not (event.modifiers() & QtCore.Qt.ShiftModifier):
                # Clear selection if shift not held
                self.clear_selection()
            
            # Start rubber band selection
            self.rubber_band_active = True
            self.rubber_band_origin = event.pos()
            self.rubber_band = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
            self.rubber_band.setGeometry(QtCore.QRect(self.rubber_band_origin, QtCore.QSize()))
            self.rubber_band.show()
            event.accept()
        else:
            # Pass other events to parent
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move events"""
        if self.panning and self.pan_start_pos is not None:
            # Pan the view
            delta = event.pos() - self.pan_start_pos
            self.pan_start_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
        elif self.rubber_band_active and self.rubber_band is not None:
            # Update rubber band selection
            self.rubber_band.setGeometry(QtCore.QRect(self.rubber_band_origin, event.pos()).normalized())
            event.accept()
        else:
            # Pass other events to parent
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release events"""
        if event.button() == QtCore.Qt.MiddleButton and self.panning:
            # End panning
            self.panning = False
            self.pan_start_pos = None
            self.setCursor(QtCore.Qt.ArrowCursor)
            event.accept()
        elif event.button() == QtCore.Qt.LeftButton and self.rubber_band_active:
            # End rubber band selection
            if self.rubber_band is not None:
                # Get items in rubber band
                rect = self.rubber_band.geometry()
                scene_rect = self.mapToScene(rect).boundingRect()
                
                # Select items in the rubber band rect
                for button in self.buttons:
                    button_rect = button.sceneBoundingRect()
                    if scene_rect.intersects(button_rect):
                        button.is_selected = True
                        button.update()
                        self.last_selected_button = button
                
                # Clean up rubber band
                self.rubber_band.hide()
                self.rubber_band = None
                self.rubber_band_active = False
                self.rubber_band_origin = None
                
                # Emit selection changed signal
                self.button_selection_changed.emit()
            
            event.accept()
        else:
            # Pass other events to parent
            super().mouseReleaseEvent(event)
    
    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == QtCore.Qt.Key_Delete and self.edit_mode:
            # Delete selected buttons in edit mode
            selected_buttons = self.get_selected_buttons()
            if selected_buttons:
                for button in list(selected_buttons):  # Use a copy to safely iterate
                    self.remove_button(button)
                event.accept()
                return
        elif event.key() == QtCore.Qt.Key_A and event.modifiers() & QtCore.Qt.ControlModifier:
            # Select all buttons with Ctrl+A
            self.select_all_buttons()
            event.accept()
            return
        elif event.key() == QtCore.Qt.Key_Escape:
            # Clear selection with Escape
            self.clear_selection()
            event.accept()
            return
        
        # Pass other events to parent
        super().keyPressEvent(event)
    
    def resizeEvent(self, event):
        """Handle resize events"""
        super().resizeEvent(event)
        
        # Update HUD position
        if self.hud_widget and not self.hud_widget.isHidden():
            self.update_hud_position()
    
    def update_hud_position(self):
        """Update the HUD widget position"""
        if self.hud_widget:
            # Position in top-right corner with some padding
            self.hud_widget.move(
                self.width() - self.hud_widget.width() - 10,
                10
            )
    
    def save_data(self):
        """Save button data for serialization"""
        data = {
            'buttons': []
        }
        
        for button in self.buttons:
            button_data = {
                'id': button.unique_id,
                'label': button.label,
                'position': {'x': button.pos().x(), 'y': button.pos().y()},
                'size': {'width': button.width, 'height': button.height},
                'color': button.color,
                'opacity': button.opacity,
                'radius': button.radius,
                'mode': button.mode,
                'assigned_objects': button.assigned_objects,
                'script_data': button.script_data
            }
            data['buttons'].append(button_data)
        
        return data
    
    def load_data(self, data):
        """Load button data from serialized data"""
        # Clear existing buttons
        self.clear_all_buttons()
        
        # Create buttons from data
        if 'buttons' in data:
            for button_data in data['buttons']:
                # Create button
                button = self.add_button(
                    label=button_data.get('label', 'Button'),
                    unique_id=button_data.get('id'),
                    color=button_data.get('color', '#444444'),
                    opacity=button_data.get('opacity', 1.0),
                    width=button_data.get('size', {}).get('width', 80),
                    height=button_data.get('size', {}).get('height', 30)
                )
                
                # Set position
                pos_data = button_data.get('position', {})
                button.setPos(QtCore.QPointF(pos_data.get('x', 0), pos_data.get('y', 0)))
                
                # Set radius
                if 'radius' in button_data:
                    button.radius = button_data['radius']
                
                # Set mode and data
                button.mode = button_data.get('mode', 'select')
                button.assigned_objects = button_data.get('assigned_objects', [])
                button.script_data = button_data.get('script_data', {})
                
                # Update tooltip
                button.update_tooltip()


class HUDWidget(QtWidgets.QWidget):
    """Heads-up display widget for the graphics view"""
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Set up widget properties
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        
        # Create layout
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)
        
        # Create HUD content
        self.selection_count_label = QtWidgets.QLabel("Selected: 0")
        self.selection_count_label.setStyleSheet(
            "color: white; background-color: rgba(0, 0, 0, 120); padding: 3px; border-radius: 3px;")
        layout.addWidget(self.selection_count_label)
        
        # Set size policy
        self.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Minimum)
        
        # Initialize timer for updating selection count
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(500)  # Update every 500ms
        self.update_timer.timeout.connect(self.update_selection_count)
        
        # Track last selection count to avoid unnecessary updates
        self.last_selection_count = 0
    
    def showEvent(self, event):
        """Handle show event"""
        super().showEvent(event)
        
        # Start update timer when shown
        self.update_timer.start()
        
        # Initial update
        self.update_selection_count()
        
        # Position the widget
        if self.parent():
            parent_rect = self.parent().rect()
            self.move(parent_rect.right() - self.width() - 10, 10)
    
    def hideEvent(self, event):
        """Handle hide event"""
        super().hideEvent(event)
        
        # Stop update timer when hidden
        self.update_timer.stop()
    
    def update_selection_count(self):
        """Update the selection count label"""
        try:
            # Get current selection count from Maya
            sel_count = len(cmds.ls(selection=True)) or 0
            
            # Only update if count has changed
            if sel_count != self.last_selection_count:
                self.selection_count_label.setText(f"Selected: {sel_count}")
                self.last_selection_count = sel_count
        except Exception:
            # Handle case where Maya might not be available
            self.selection_count_label.setText("Selected: --")
