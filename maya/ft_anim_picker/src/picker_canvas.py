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
import os
import maya.cmds as cmds
from . import ui as UI
from . import utils as UT
from . import picker_button as PB
from . import custom_button as CB
from . import tool_functions as TF
from . import data_management as DM
from . import custom_dialog as CD
from . import pb_transform_guides as TG

class HUDWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)  # Make the whole widget transparent to mouse events
        self.setStyleSheet("background-color: transparent;")
        
        # Main layout for HUD elements
        self.layout = QtWidgets.QGridLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        
        # Create the toggle button container that will catch mouse events
        self.button_container = QtWidgets.QWidget(self)
        self.button_container.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)  # This widget will catch mouse events
        self.button_container.setFixedSize(24, 24)
        
        # Create the toggle button
        self.toggle_button = QtWidgets.QPushButton("≡", self.button_container)
        self.toggle_button.setFixedSize(24, 24)
        self.toggle_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(50, 50, 50, 0.7);
                color: #dddddd;
                border: 1px solid rgba(80, 80, 80, 0.7);
                border-radius: 3px;
                padding: 0px 0px 2px 0px;
            }
            QPushButton:hover {
                background-color: rgba(60, 60, 60, 0.8);
            }""")
        
        self.toggle_button.clicked.connect(self.toggle_hud)
        self.layout.addWidget(self.button_container, 0, 0, QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        
        # Stats container
        self.stats_container = QtWidgets.QWidget(self)
        self.stats_layout = QtWidgets.QHBoxLayout(self.stats_container)
        self.stats_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_layout.setSpacing(10)  # Space between labels
        
        # Button count label
        self.button_count_label = QtWidgets.QLabel("Buttons: 0 / 0")
        self.button_count_label.setStyleSheet("color: rgba(255, 255, 255, 0.2);")
        #self.stats_layout.addWidget(self.button_count_label)
        self.layout.addWidget(self.button_count_label, 0, 0, QtCore.Qt.AlignBottom | QtCore.Qt.AlignLeft)
        

        # Selection count label
        self.selection_count_label = QtWidgets.QLabel("Selected: 0")
        self.selection_count_label.setStyleSheet("color: rgba(255, 255, 255, 0.2);")
        #self.stats_layout.addWidget(self.selection_count_label)
        self.layout.addWidget(self.selection_count_label, 0, 1, QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight)

        self.reset_buttons()
        
        # Store all HUD elements (except toggle button)
        self.hud_elements = [
            self.stats_container,
            self.button_count_label,
            self.selection_count_label,
            self.reset_button_frame
        ]

        # Initialize visibility
        self.hud_visible = True
        
        # Start timer for updating Maya selection count
        self.update_timer = QtCore.QTimer(self)
        self.update_timer.timeout.connect(self.update_selection_count)
        self.update_timer.start(100)  # Update every 100ms

    def reset_buttons(self):
        button_size = 14
        br = 3
        los = 5
        fbc = 35
        
        # Create a container widget for the reset buttons that will catch mouse events
        self.reset_container = QtWidgets.QWidget(self)
        self.reset_container.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)  # This widget will catch mouse events
        
        # Create the frame inside the container
        self.reset_button_frame = QtWidgets.QFrame(self.reset_container)
        self.reset_button_frame.setStyleSheet(f"background-color: rgba({fbc},{fbc},{fbc},.7); border-radius: {br}px;")
        self.reset_button_frame.setFixedHeight(24)
        
        self.reset_button_layout = QtWidgets.QHBoxLayout(self.reset_button_frame)
        self.reset_button_layout.setContentsMargins(los, los, los, los)
        self.reset_button_layout.setSpacing(los)

        self.reset_move_button = CB.CustomButton(text="Move",tooltip="Reset Position",height=button_size,radius=br)
        self.reset_rotate_button = CB.CustomButton(text="Rotate",tooltip="Reset Rotation",height=button_size,radius=br)
        self.reset_scale_button = CB.CustomButton(text="Scale",tooltip="Reset Scale",height=button_size,radius=br)
        self.reset_all_button = CB.CustomButton(text="All",tooltip="Reset All",height=button_size,radius=br, color='#ff0000')

        self.reset_move_button.clicked.connect(TF.reset_move)
        self.reset_rotate_button.clicked.connect(TF.reset_rotate)
        self.reset_scale_button.clicked.connect(TF.reset_scale)
        self.reset_all_button.clicked.connect(TF.reset_all)

        self.reset_button_layout.addWidget(self.reset_move_button)
        self.reset_button_layout.addWidget(self.reset_rotate_button)
        self.reset_button_layout.addWidget(self.reset_scale_button)
        self.reset_button_layout.addWidget(self.reset_all_button)

        # Add the container to the main layout
        self.layout.addWidget(self.reset_container, 0, 1, QtCore.Qt.AlignTop | QtCore.Qt.AlignRight)
        
        # Ensure the frame fills the container
        container_layout = QtWidgets.QHBoxLayout(self.reset_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        #container_layout.addWidget(self.reset_button_frame)
        
    def toggle_hud(self):
        self.hud_visible = not self.hud_visible
        for element in self.hud_elements:
            element.setVisible(self.hud_visible)

    def update_button_count(self, total_count, selected_count=0):
        """Update the button count display with both total and selected counts"""
        self.button_count_label.setText(f"Buttons: {selected_count} / {total_count}")
        
    def update_selection_count(self):
        """Update the Maya selection count"""
        try:
            sel_count = len(cmds.ls(selection=True)) or 0
            self.selection_count_label.setText(f"Selected: {sel_count}")
        except:
            # Handle case where Maya command fails
            self.selection_count_label.setText("Selected: --")

class PickerCanvas(QtWidgets.QWidget):
    clicked = Signal()
    button_selection_changed = Signal()
    selection_count_changed = Signal(int)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAutoFillBackground(True)

        # Enable drag and drop for the canvas
        self.setAcceptDrops(True)

        self.show_axes = True
        self.show_dots = True 
        self.show_grid = False  
        self.grid_size = 50  

        # Background properties
        self.background_color = QtGui.QColor(50, 50, 50, 255)
        self.dot_color = QtGui.QColor(40, 40, 40, 255)
        self.grid_color = QtGui.QColor(10, 10, 10, 255)
        self.dot_size = 3
        self.dot_spacing = 12

        # Border properties
        self.default_border_color = QtGui.QColor(82, 133, 166, 150) #(36, 36, 36, 255)
        self.edit_mode_border_color = QtGui.QColor(145, 203, 8,255)   #(82, 133, 166, 255) blue  (108, 152, 9,255) green
        self.border_color = self.default_border_color
        self.border_width = 1
        self.border_radius = 4

        # Image properties
        self.background_image = None
        self.image_opacity = 1.0

        # Canvas transform properties
        self.zoom_factor = 1.0
        self.pan_offset = QtCore.QPointF(0, 0)
        self.last_pan_pos = None

        self.buttons = []
        self.setup_dot_texture()
        
        # Set size policy to allow expanding
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.setMouseTracking(True)
        self.rubberband = QtWidgets.QRubberBand(QtWidgets.QRubberBand.Rectangle, self)
        self.rubberband_origin = QtCore.QPoint()
        self.is_selecting = False
        self.buttons_in_current_drag = set()  # Track buttons in current drag operation
        self.initial_selection_state = {}  # Store initial selection state when drag starts

        self.edit_mode = False
        self.image_scale = 1.0

        self.hud = HUDWidget(self)
        self.hud.raise_()

        self.minimal_mode = False
        self.last_selected_button = None

        # Transform guides for edit mode (add after HUD initialization)
        self.transform_guides = TG.TransformGuides(self, self)
        self.transform_guides.transform_finished.connect(self.on_transform_finished)
    #------------------------------------------------------------------------------
    def set_edit_mode(self, enabled):
        self.edit_mode = enabled
        self.border_color = self.edit_mode_border_color if enabled else self.default_border_color
        self.border_width = 1 if enabled else 1
        for button in self.buttons:
            button.edit_mode = enabled
            button.update_cursor()

        # Update transform guides
        if hasattr(self, 'transform_guides'):
            if enabled:
                self.transform_guides.update_selection()
            else:
                self.transform_guides.setVisible(False)
                self.transform_guides.visual_layer.setVisible(False)
                
        self.update()
    
    def set_minimal_mode(self, enabled):
        """Set minimal mode state"""
        self.minimal_mode = enabled
        # Hide/show the HUD based on minimal mode
        self.hud.setVisible(not enabled)
        self.update()  # Trigger repaint
    #------------------------------------------------------------------------------
    # TRANSFORM GUIDES
    #------------------------------------------------------------------------------
    def on_transform_finished(self):
        """Handle transform guide operations completion"""
        # Force update of button positions and data
        self.update_button_positions()
        self.update()
        
        # Update button data for all selected buttons
        for button in self.get_selected_buttons():
            self.update_button_data(button)

    def update_transform_guides(self):
        """Update transform guides when selection or edit mode changes"""
        if hasattr(self, 'transform_guides'):
            self.transform_guides.update_selection()

    def hide_transform_guides(self):
        """Hide transform guides"""
        if hasattr(self, 'transform_guides'):
            self.transform_guides.setVisible(False)
            self.transform_guides.visual_layer.setVisible(False)
    
    def update_pan_offset(self, delta):
        """Helper method to update pan offset and transform guides"""
        self.pan_offset += QtCore.QPointF(delta.x(), delta.y())
        
        # Update transform guides immediately during panning
        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            QtCore.QTimer.singleShot(5, self.transform_guides.update_position)
        
        # Update transform guides immediately during panning
        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            QtCore.QTimer.singleShot(5, self.transform_guides.update_position)
    
    def _update_guides_after_button_change(self):
        """Update transform guides after button changes"""
        if hasattr(self, 'transform_guides') and self.edit_mode:
            QtCore.QTimer.singleShot(10, self.transform_guides.update_selection)
    
    def connect_button_signals(self, button):
        """Connect button signals for real-time transform guide updates"""
        button.deleted.connect(self.remove_button)
        button.selected.connect(self.on_button_selected)
        button.changed.connect(self.on_button_changed)
        
        # CRITICAL FIX: Connect to position changes for transform guides
        if hasattr(button, 'position_changed'):
            button.position_changed.connect(self._update_transform_guides_position)
    #------------------------------------------------------------------------------
    def select_buttons_in_rect(self, rect, add_to_selection=False):
        # If not adding to selection and not in shift mode, clear existing selection
        if not add_to_selection:
            self.clear_selection()

        selection_changed = False
        for button in self.buttons:
            # Skip buttons that are not selectable in select mode
            if not self.edit_mode and hasattr(button, 'selectable') and not button.selectable:
                continue
                
            button_rect = button.geometry()
            if rect.intersects(button_rect):
                if not button.is_selected:
                    button.set_selected(True)
                    selection_changed = True

        if selection_changed:
            self.button_selection_changed.emit()
            self.update_hud_counts()

    def update_visual_selection(self, rect, add_to_selection=False):
        """Update button selection visually during rubber band drag"""
        # Get buttons in current rectangle
        current_buttons = set()
        
        # Convert selection rect to scene coordinates
        rect_top_left = self.canvas_to_scene_coords(QtCore.QPointF(rect.left(), rect.top()))
        rect_bottom_right = self.canvas_to_scene_coords(QtCore.QPointF(rect.right(), rect.bottom()))
        
        scene_rect = QtCore.QRectF(rect_top_left, rect_bottom_right).normalized()
        
        # Find buttons that intersect with selection rectangle
        for button in self.buttons:
            if not button.isVisible():
                continue
                
            # Skip non-selectable buttons in select mode
            if not self.edit_mode and hasattr(button, 'selectable') and not button.selectable:
                continue
                
            # Get button rect in scene coordinates
            button_pos = button.scene_position
            button_rect = QtCore.QRectF(
                button_pos.x() - button.width/2,
                button_pos.y() - button.height/2,
                button.width,
                button.height
            )
            
            if scene_rect.intersects(button_rect):
                current_buttons.add(button)
        
        # Track selection changes for signal emission
        selection_changed = False
        
        # Update selection states
        for button in self.buttons:
            old_selection = button.is_selected
            
            if button in current_buttons:
                # Button is in selection rectangle
                if add_to_selection:
                    # Toggle from initial state when shift is held
                    initial_state = self.initial_selection_state.get(button, False)
                    button.is_selected = not initial_state
                else:
                    # Select when shift not held
                    button.is_selected = True
            else:
                # Button not in rectangle - restore initial state
                if button in self.initial_selection_state:
                    button.is_selected = self.initial_selection_state[button]
            
            # Check if selection state changed
            if old_selection != button.is_selected:
                selection_changed = True
                # Emit individual button selection signal
                button.selected.emit(button, button.is_selected)
            
            button.update()
        
        # Track current drag buttons for final selection
        self.buttons_in_current_drag = current_buttons
        
        # Invalidate selection cache
        if hasattr(self, '_cache_valid'):
            self._cache_valid = False
        
        # Update HUD and emit selection changed signal if anything changed
        if selection_changed:
            self.update_hud_counts()
            self.button_selection_changed.emit()
    #------------------------------------------------------------------------------
    def apply_final_selection(self, add_to_selection=False):
        """Apply final selection with improved object lookup and UUID updating"""
        if self.edit_mode:
            return
            
        try:
            # Prepare selection data
            deselected_buttons = self._get_deselected_buttons()
            final_selections = self._build_ordered_selection_list(add_to_selection)
            
            # Resolve objects and update UUIDs
            new_selection, missing_objects, uuid_updates = self._resolve_objects(final_selections)
            
            # Apply Maya selection
            self._apply_maya_selection(new_selection, deselected_buttons, add_to_selection)
            
            # Handle missing objects
            if missing_objects:
                self._show_missing_objects_dialog(missing_objects)
            
            # Update UI state
            self._update_ui_state(uuid_updates)
            
        except Exception as e:
            print(f"Error in apply_final_selection: {e}")

    def _get_deselected_buttons(self):
        """Get buttons that were deselected during current drag"""
        return {button for button in self.buttons_in_current_drag 
                if not button.is_selected}

    def _build_ordered_selection_list(self, add_to_selection):
        """Build ordered list of selected buttons"""
        final_selections = []
        
        # Add previously selected buttons if adding to selection
        if add_to_selection:
            for button in self.buttons:
                if button.is_selected and button not in self.buttons_in_current_drag:
                    final_selections.append(button)
        
        # Add currently selected buttons (except last clicked)
        last_clicked = next(reversed(list(self.buttons_in_current_drag)), None)
        for button in self.buttons_in_current_drag:
            if button.is_selected and button != last_clicked:
                final_selections.append(button)
        
        # Add last clicked button at the end
        if last_clicked and last_clicked.is_selected:
            final_selections.append(last_clicked)
        
        return final_selections

    def _resolve_objects(self, final_selections):
        """Resolve objects for selected buttons and update UUIDs"""
        new_selection = []
        missing_objects = set()
        uuid_updates = False
        
        for button in final_selections:
            if not button.assigned_objects:
                continue
                
            resolved_objects, button_missing, button_uuid_updates = self._resolve_button_objects(button)
            new_selection.extend(resolved_objects)
            missing_objects.update(button_missing)
            uuid_updates = uuid_updates or button_uuid_updates
        
        return new_selection, missing_objects, uuid_updates

    def _resolve_button_objects(self, button):
        """Resolve objects for a single button"""
        main_window = self.window()
        if not isinstance(main_window, UI.AnimPickerWindow):
            return [], set(), False
        
        current_namespace = main_window.namespace_dropdown.currentText()
        resolved_objects = []
        missing_objects = set()
        updated_objects = []
        uuid_updates = False
        
        for obj_data in button.assigned_objects:
            resolved_node, new_uuid, was_updated = self._resolve_single_object(
                obj_data, current_namespace
            )
            
            if resolved_node:
                resolved_objects.append(resolved_node)
                updated_objects.append({
                    'uuid': new_uuid or obj_data['uuid'],
                    'long_name': resolved_node
                })
                if was_updated:
                    uuid_updates = True
            else:
                base_name = obj_data['long_name'].split('|')[-1].split(':')[-1]
                missing_objects.add(f"- {base_name}")
                updated_objects.append(obj_data)
        
        # Update button's assigned objects with new UUIDs
        button.assigned_objects = updated_objects
        if uuid_updates:
            button.changed.emit(button)
        
        return resolved_objects, missing_objects, uuid_updates

    def _resolve_single_object(self, obj_data, current_namespace):
        """Resolve a single object using multiple fallback strategies"""
        uuid = obj_data['uuid']
        long_name = obj_data['long_name']
        base_name = long_name.split('|')[-1].split(':')[-1]
        
        # Strategy 1: Try UUID resolution
        resolved_node, new_uuid = self._try_uuid_resolution(uuid)
        if resolved_node:
            return resolved_node.split(':')[-1], new_uuid, False
        
        # Strategy 2: Try exact long name
        resolved_node, new_uuid = self._try_exact_name_resolution(long_name)
        if resolved_node:
            return resolved_node, new_uuid, True
        
        # Strategy 3: Try namespaced resolution
        if current_namespace and current_namespace != 'None':
            resolved_node, new_uuid = self._try_namespaced_resolution(
                current_namespace, base_name
            )
            if resolved_node:
                return resolved_node, new_uuid, True
        
        # Strategy 4: Try base name resolution
        resolved_node, new_uuid = self._try_base_name_resolution(base_name)
        if resolved_node:
            return resolved_node, new_uuid, True
        
        return None, None, False

    def _try_uuid_resolution(self, uuid):
        """Try to resolve object by UUID"""
        try:
            nodes = cmds.ls(uuid, long=True)
            if nodes:
                return nodes[0], uuid
        except:
            pass
        return None, None

    def _try_exact_name_resolution(self, long_name):
        """Try to resolve object by exact long name"""
        try:
            if cmds.objExists(long_name):
                new_uuid = cmds.ls(long_name, uuid=True)[0]
                return long_name, new_uuid
        except:
            pass
        return None, None

    def _try_namespaced_resolution(self, namespace, base_name):
        """Try to resolve object with current namespace"""
        try:
            namespaced_node = f"{namespace}:{base_name}"
            if cmds.objExists(namespaced_node):
                new_uuid = cmds.ls(namespaced_node, uuid=True)[0]
                return namespaced_node, new_uuid
        except:
            pass
        return None, None

    def _try_base_name_resolution(self, base_name):
        """Try to resolve object by base name only"""
        try:
            if cmds.objExists(base_name):
                new_uuid = cmds.ls(base_name, uuid=True)[0]
                return base_name, new_uuid
        except:
            pass
        return None, None

    def _apply_maya_selection(self, new_selection, deselected_buttons, add_to_selection):
        """Apply the selection in Maya"""
        cmds.undoInfo(openChunk=True)
        try:
            if not add_to_selection:
                cmds.select(clear=True)
            else:
                self._deselect_button_objects(deselected_buttons)
            
            if new_selection:
                self._select_resolved_objects(new_selection)
        finally:
            cmds.undoInfo(closeChunk=True)

    def _deselect_button_objects(self, deselected_buttons):
        """Deselect objects from deselected buttons"""
        for button in deselected_buttons:
            for obj_data in button.assigned_objects:
                resolved_node = self._get_existing_object(obj_data)
                if resolved_node:
                    try:
                        cmds.select(resolved_node, deselect=True)
                    except:
                        continue

    def _get_existing_object(self, obj_data):
        """Get existing object from obj_data, trying UUID first then long_name"""
        try:
            # Try UUID first
            nodes = cmds.ls(obj_data['uuid'], long=True)
            if nodes:
                return nodes[0]
            
            # Fallback to long name
            if cmds.objExists(obj_data['long_name']):
                return obj_data['long_name']
        except:
            pass
        return None

    def _select_resolved_objects(self, new_selection):
        """Select the resolved objects in Maya"""
        main_window = self.window()
        current_namespace = main_window.namespace_dropdown.currentText()
        
        resolved_selection = []
        resolved_names = []
        
        for sel in new_selection:
            namespaced_node = f"{current_namespace}:{sel}"
            if cmds.objExists(namespaced_node):
                resolved_selection.append(namespaced_node)
            else:
                resolved_selection.append(sel)
            
            sel_name = sel.split(':')[-1].split('|')[-1]
            resolved_names.append(sel_name)
        
        print(f"Selecting: {', '.join(resolved_names)}")
        cmds.select(resolved_selection, add=True)
        
        # Make last node active
        if resolved_selection:
            cmds.select(resolved_selection[-1], toggle=True)
            cmds.select(resolved_selection[-1], add=True)

    def _show_missing_objects_dialog(self, missing_objects):
        """Show dialog for missing objects"""
        parent_widget = self.parentWidget()
        dialog = CD.CustomDialog(
            parent_widget, 
            title="Missing Objects", 
            size=(250, -1), 
            info_box=True
        )
        
        message_label = QtWidgets.QLabel("The following objects were not found:")
        details_label = QtWidgets.QLabel(
            '\n'.join(sorted(f"<b><font color='#00ade6'>{obj}</font></b>" 
                            for obj in missing_objects))
        )
        note_label = QtWidgets.QLabel("[Objects may have been deleted or renamed]")
        
        dialog.add_widget(message_label)
        dialog.add_widget(details_label)
        dialog.add_widget(note_label)
        dialog.add_button_box()
        dialog.exec_()

    def _update_ui_state(self, uuid_updates):
        """Update UI state after selection changes"""
        for button in self.buttons:
            button.update()
            button.update_tooltip()
        
        self.button_selection_changed.emit()
        self.update_hud_counts()
        
        if uuid_updates:
            main_window = self.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                main_window.update_buttons_for_current_tab()
    #------------------------------------------------------------------------------
    def clear_selection(self):
        selection_changed = False
        for button in self.buttons:
            if button.is_selected:
                button.set_selected(False)
                button.selected.emit(button, False)  # Emit the button's selected signal
                selection_changed = True
        
        if selection_changed:
            self.button_selection_changed.emit()
            self.update_hud_counts()

            if hasattr(self, 'transform_guides'):
                self.transform_guides.setVisible(False)
                self.transform_guides.visual_layer.setVisible(False)

    def get_selected_buttons(self):
        """Get list of currently selected buttons"""
        return [button for button in self.buttons if button.is_selected]
    
    def on_button_selected(self, button, is_selected):
        if not is_selected:
            button.set_selected(False)
        
        # Batch UI updates
        if not hasattr(self, '_selection_update_timer'):
            self._selection_update_timer = QtCore.QTimer()
            self._selection_update_timer.setSingleShot(True)
            self._selection_update_timer.timeout.connect(self._emit_selection_changed)
        
        self._selection_update_timer.stop()
        self._selection_update_timer.start(10)  # 10ms debounce

    def _get_button_at_position(self, pos):
        """Get the topmost visible button at the given position"""
        # Check buttons in reverse order (topmost first due to z-order)
        for button in reversed(self.buttons):
            if button.isVisible() and button.geometry().contains(pos):
                return button
        return None

    def _emit_selection_changed(self):
        """Emit selection changed signals with batching"""
        if hasattr(self, '_cache_valid'):
            self._cache_valid = False  # Invalidate cache
        self.button_selection_changed.emit()
        self.update_hud_counts()
        self.update()
    
        # Update transform guides
        if hasattr(self, 'transform_guides'):
            QtCore.QTimer.singleShot(10, self.transform_guides.update_selection)
    #------------------------------------------------------------------------------
    def add_button(self, button):
        # Preserve original functionality
        self.buttons.append(button)
        button.setParent(self)
        button.show()
        button.deleted.connect(self.remove_button)
        button.selected.connect(self.on_button_selected)
        button.changed.connect(self.on_button_changed)
        button.edit_mode = self.edit_mode
        button.update_cursor()
        self.update_button_positions()
        
        # Update HUD button count
        self.update_hud_counts()
        self._update_guides_after_button_change()

    def remove_button(self, button):
        if button in self.buttons:
            self.buttons.remove(button)
            self.update_button_positions()
            main_window = self.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                main_window.update_button_data(button, deleted=True)
            
            # Update HUD button count
            self.update_hud_counts()
            self._update_guides_after_button_change()
            self.transform_guides.setVisible(False)
            self.transform_guides.visual_layer.setVisible(False)

    def update_button_positions(self):
        """Optimized button position updating with better culling"""
        if not self.buttons:
            return
            
        visible_rect = self.rect()
        
        # Early exit if no size
        if visible_rect.width() <= 0 or visible_rect.height() <= 0:
            return
            
        # Calculate visible area with larger margin for smoother experience
        visible_scene_rect = QtCore.QRectF(
            self.canvas_to_scene_coords(QtCore.QPointF(visible_rect.left(), visible_rect.top())),
            self.canvas_to_scene_coords(QtCore.QPointF(visible_rect.right(), visible_rect.bottom()))
        ).normalized()
        
        # Larger margin to prevent popping
        margin = max(visible_scene_rect.width() * 0.5, visible_scene_rect.height() * 0.5)
        visible_scene_rect.adjust(-margin, -margin, margin, margin)
        
        # Batch geometry updates
        geometry_updates = []
        buttons_to_show = []
        buttons_to_hide = []
        
        for button in self.buttons:
            # Quick visibility test
            button_pos = button.scene_position
            button_width = button.width
            button_height = button.height
            button_rect = QtCore.QRectF(
                button_pos.x() - button_width/2,
                button_pos.y() - button_height/2,
                button_width,
                button_height
            )
            
            if visible_scene_rect.intersects(button_rect):
                # Calculate geometry
                canvas_pos = self.scene_to_canvas_coords(button_pos)
                scaled_width = button_width * self.zoom_factor
                scaled_height = button_height * self.zoom_factor
                x = canvas_pos.x() - scaled_width / 2
                y = canvas_pos.y() - scaled_height / 2
                
                geometry_updates.append((button, int(x), int(y), int(scaled_width), int(scaled_height)))
                buttons_to_show.append(button)
            else:
                buttons_to_hide.append(button)
        
        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            QtCore.QTimer.singleShot(5, self._update_transform_guides_position)

        # Apply all geometry updates at once
        self.setUpdatesEnabled(False)
        
        for button, x, y, w, h in geometry_updates:
            button.setGeometry(x, y, w, h)
            
        for button in buttons_to_show:
            if not button.isVisible():
                button.show()
                
        for button in buttons_to_hide:
            if button.isVisible():
                button.hide()
        
        self.setUpdatesEnabled(True)
    
    def _update_transform_guides_position(self):
        """Helper method to update transform guides position"""
        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            self.transform_guides.calculate_bounding_rect()
            self.transform_guides.update_position()

    def update_button_data(self, button, deleted=False):
        main_window = self.window()
        if isinstance(main_window, UI.AnimPickerWindow):
            main_window.update_button_data(button, deleted)

    def on_button_changed(self, button):
        self.update_button_data(button)
        if (hasattr(self, 'transform_guides') and 
            self.transform_guides.isVisible() and 
            button in self.get_selected_buttons()):
            QtCore.QTimer.singleShot(5, self._update_transform_guides_position)
    
    def update_hud_counts(self):
        """Update HUD with current button counts"""
        selected_count = len(self.get_selected_buttons())
        total_count = len(self.buttons)
        self.hud.update_button_count(total_count, selected_count)
    #------------------------------------------------------------------------------
    def scene_to_canvas_coords(self, pos):
        # Convert scene coordinates to canvas coordinates
        center = QtCore.QPointF(self.width() / 2, self.height() / 2)
        canvas_pos = (pos * self.zoom_factor) + center + self.pan_offset
        return canvas_pos

    def canvas_to_scene_coords(self, pos):
        # Convert canvas coordinates to scene coordinates
        center = QtCore.QPointF(self.width() / 2, self.height() / 2)
        scene_pos = (pos - center - self.pan_offset) / self.zoom_factor
        return scene_pos
    
    def get_center_position(self):
        # Convert the center of the widget to scene coordinates
        center = QtCore.QPointF(self.width() / 2, self.height() / 2)
        self.update()
        return self.canvas_to_scene_coords(center)
    #------------------------------------------------------------------------------
    def setup_dot_texture(self):
        # Create a higher resolution texture for smoother dots
        texture_size = self.dot_spacing
        # Use a higher resolution for the texture
        scale_factor = 4
        hi_res_size = texture_size * scale_factor
        
        # Create a high resolution temporary image for anti-aliased drawing
        hi_res_texture = QtGui.QImage(hi_res_size, hi_res_size, QtGui.QImage.Format_ARGB32)
        hi_res_texture.fill(QtCore.Qt.transparent)
        
        # Set up painter for high resolution drawing
        painter = QtGui.QPainter(hi_res_texture)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
        
        # Calculate scaled dot size
        scaled_dot_size = self.dot_size * scale_factor
        
        # Create gradient for smoother appearance
        gradient = QtGui.QRadialGradient(
            hi_res_size // 2,
            hi_res_size // 2,
            scaled_dot_size // 2
        )
        
        # Define gradient stops for smoother edges
        dot_color = self.dot_color
        gradient.setColorAt(0.0, dot_color)
        gradient.setColorAt(0.7, dot_color)  # Maintain solid color for most of the dot
        gradient.setColorAt(1.0, QtGui.QColor(dot_color.red(), dot_color.green(), dot_color.blue(), 0))
        
        # Draw the dot with gradient
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawEllipse(
            (hi_res_size - scaled_dot_size) // 2,
            (hi_res_size - scaled_dot_size) // 2,
            scaled_dot_size,
            scaled_dot_size
        )
        painter.end()
        
        # Scale down to final size with smooth transform
        final_texture = hi_res_texture.scaled(
            texture_size,
            texture_size,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        
        # Create brush from the final texture
        self.dot_texture = QtGui.QBrush(QtGui.QPixmap.fromImage(final_texture))
    
    def set_show_axes(self, show):
        """Set whether to show the axes lines"""
        self.show_axes = show
        self.update()
    
    def set_show_dots(self, show):
        """Set whether to show the background dots"""
        self.show_dots = show
        self.update()
    
    def toggle_dots(self, show):
        """Toggle the visibility of background dots"""
        self.show_dots = show
        self.update()
    #------------------------------------------------------------------------------
    def set_show_grid(self, show):
        """Set whether to show the background grid"""
        self.show_grid = show
        self.update()

    def set_grid_size(self, size):
        """Set the grid size"""
        self.grid_size = max(1, size)  # Ensure minimum size of 1
        self.update()

    def draw_grid(self, painter, visible_rect):
        """Draw grid lines on the canvas"""
        if not self.show_grid:
            return
        
        # Use the dynamic grid color that changes with background
        pen = QtGui.QPen(self.grid_color)
        pen.setWidthF(0.5 / self.zoom_factor)  # Scale with zoom
        painter.setPen(pen)
        
        # Calculate grid spacing in scene coordinates
        grid_spacing = self.grid_size
        
        # Convert visible area to scene coordinates for efficient drawing
        top_left = self.canvas_to_scene_coords(QtCore.QPointF(visible_rect.left(), visible_rect.top()))
        bottom_right = self.canvas_to_scene_coords(QtCore.QPointF(visible_rect.right(), visible_rect.bottom()))
        
        # Calculate grid bounds
        left = int(top_left.x() / grid_spacing) * grid_spacing
        right = int(bottom_right.x() / grid_spacing + 1) * grid_spacing
        top = int(top_left.y() / grid_spacing) * grid_spacing
        bottom = int(bottom_right.y() / grid_spacing + 1) * grid_spacing
        
        # Draw vertical lines
        x = left
        while x <= right:
            painter.drawLine(QtCore.QLineF(x, top_left.y(), x, bottom_right.y()))
            x += grid_spacing
        
        # Draw horizontal lines
        y = top
        while y <= bottom:
            painter.drawLine(QtCore.QLineF(top_left.x(), y, bottom_right.x(), y))
            y += grid_spacing
    #------------------------------------------------------------------------------
    def set_background_value(self, value):
        """Set the background color value where 0 is black and 100 is white"""
        # Convert percentage to RGB value (0-255)
        bg_value = int((value / 100.0) * 255)
        self.background_color = QtGui.QColor(bg_value, bg_value, bg_value)
        
        # Set dot color to be 10% darker than background
        dot_value = max(0, int(bg_value * 0.8))  # Ensure value doesn't go below 0
        self.dot_color = QtGui.QColor(dot_value, dot_value, dot_value)

        # Set grid color to be 10% darker than background
        grid_value = max(0, int(bg_value * 0.8))  # Ensure value doesn't go below 0
        self.grid_color = QtGui.QColor(grid_value, grid_value, grid_value)
        
        # Update dot texture with new color
        self.setup_dot_texture()
        self.update()

    def set_background_image(self, image_path):
        """Set the background image from a file path"""
        if image_path is None:
            self.background_image = None
        else:
            self.background_image = QtGui.QImage(image_path)
            if self.background_image.isNull():
                self.background_image = None
            else:
                # Store the image path for saving in the tab data
                self.background_image_path = image_path
                # Update the tab data with the background image path
                self._update_tab_data_with_background(image_path)
                self.focus_canvas()
        self.update()
        
    def _update_tab_data_with_background(self, image_path):
        """Update the tab data with the background image path"""
        main_window = self.window()
        if isinstance(main_window, UI.AnimPickerWindow):
            current_tab = main_window.tab_system.current_tab
            if current_tab:
                # Update the tab system data structure
                main_window.tab_system.tabs[current_tab]['image_path'] = image_path
                
                # Get current opacity and scale values
                current_opacity = main_window.tab_system.tabs[current_tab].get('image_opacity', 1.0)
                current_scale = self.image_scale
                
                # Update the data manager
                DM.PickerDataManager.update_image_data(
                    current_tab, 
                    image_path, 
                    current_opacity,
                    current_scale
                )
                
                # Enable the remove image button if it exists
                if hasattr(main_window, 'remove_image'):
                    main_window.remove_image.setEnabled(True)
    
    def set_background_from_image(self, image):
        """Set the background image from a QImage object"""
        if image and not image.isNull():
            self.background_image = image
            self.focus_canvas()
            self.update()
            return True
        return False
        
    def dragEnterEvent(self, event):
        """Handle drag enter events for image files"""
        if event.mimeData().hasUrls():
            # Check if any of the URLs are image files
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if self._is_valid_image_file(file_path):
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def dragMoveEvent(self, event):
        """Handle drag move events"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dropEvent(self, event):
        """Handle drop events for image files"""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if self._is_valid_image_file(file_path):
                    # Process regardless of edit mode
                    main_window = self.window()
                    if isinstance(main_window, UI.AnimPickerWindow):
                        self.set_background_image(file_path)
                        event.acceptProposedAction()
                        return
        event.ignore()
    
    def _is_valid_image_file(self, file_path):
        """Check if the file is a valid image file"""
        if not os.path.isfile(file_path):
            return False
            
        # Get the file extension
        _, ext = os.path.splitext(file_path)
        if not ext:
            return False
            
        # Check if the extension is a supported image format
        valid_extensions = ['.png', '.jpg', '.jpeg', '.bmp', '.gif']
        return ext.lower() in valid_extensions

    def set_image_opacity(self, opacity):
        self.image_opacity = max(0.0, min(1.0, opacity))
        self.update()
    
    def set_image_scale(self, scale):
        self.image_scale = scale #max(0.1, scale)
        self.update()

    def focus_canvas(self):
        view_rect = self.rect()
        selected_buttons = self.get_selected_buttons()

        if selected_buttons:
            # Focus on the selected buttons
            button_rect = self.get_buttons_bounding_rect(selected_buttons)

            # Apply zoom to fit the button_rect in the view
            self.fit_rect_in_view(button_rect)

            # Center the selected buttons
            center_scene = button_rect.center()
            center_view = QtCore.QPointF(1, 1) 

            if len(selected_buttons) == 1:
                self.zoom_factor = 2
            else:
                self.zoom_factor = .6
            self.pan_offset = center_view - (center_scene * (self.zoom_factor))
            

        elif self.background_image and not self.background_image.isNull():
            # Focus on the full image
            image_rect = QtCore.QRectF(
                -self.background_image.width() / 2,
                -self.background_image.height() / 2,
                self.background_image.width(),
                self.background_image.height()
            )
            self.fit_rect_in_view(image_rect)

        elif self.buttons:
            # If no buttons are selected, focus on all buttons
            all_buttons_rect = self.get_buttons_bounding_rect()
            self.fit_rect_in_view(all_buttons_rect)

        else:
            # If no buttons and no image, reset to default view
            self.zoom_factor = 1.0
            self.pan_offset = QtCore.QPointF(0, 0)

        self.update()
        self.update_button_positions()

    def fit_rect_in_view(self, rect):
        view_rect = self.rect()

        # Check for zero width or height
        if rect.width() == 0 or rect.height() == 0:
            self.zoom_factor = 1.0
            self.pan_offset = QtCore.QPointF(0, 0)
            return

        # Calculate the zoom factor to fit the rect within the view
        sf = .8 / self.image_scale # scale factor
        scale_x = (view_rect.width() / rect.width() ) * sf
        scale_y = (view_rect.height() / rect.height()) * sf
        self.zoom_factor = min(scale_x, scale_y)

        # Limit the zoom factor to prevent extreme zoom levels
        self.zoom_factor = max(0.1, min(self.zoom_factor, 10))

        # Calculate the pan offset to center the rect (done in focus_canvas now)
        scaled_width = rect.width() * self.zoom_factor
        scaled_height = rect.height() * self.zoom_factor

        self.pan_offset = QtCore.QPointF(1,1)
        #(view_rect.width() - scaled_width) / 2

    def get_buttons_bounding_rect(self, buttons=None):
        if buttons is None:
            buttons = self.buttons

        if not buttons:
            return QtCore.QRectF(0, 0, 1, 1)

        min_x = min(button.scene_position.x() for button in buttons) 
        max_x = max(button.scene_position.x() for button in buttons)
        min_y = min(button.scene_position.y() for button in buttons)
        max_y = max(button.scene_position.y() for button in buttons)

        width = max(max_x - min_x, 1) 
        height = max(max_y - min_y, 1) 

        return QtCore.QRectF(min_x, min_y, width, height)
    #------------------------------------------------------------------------------
    def show_context_menu(self, position):
        if not hasattr(self, 'context_menu'):
            self.context_menu = QtWidgets.QMenu()
            self.context_menu.setWindowFlags(self.context_menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
            self.context_menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
            self.context_menu.setStyleSheet('''
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
                }''')
        
        menu = self.context_menu
        menu.clear()
        
        if self.edit_mode:
            add_button_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')), "Add Button")
            add_button_action.triggered.connect(lambda: self.add_button_at_position(position))
            
            # Get clipboard state to determine if paste actions should be enabled
            has_clipboard = bool(PB.ButtonClipboard.instance().get_all_buttons())
            
            # Create regular paste action
            paste_buttons_action = menu.addAction(QtGui.QIcon(UT.get_icon('paste.png')), "Paste Button")
            paste_buttons_action.triggered.connect(lambda: self.paste_buttons_at_position(position, mirror=False))
            paste_buttons_action.setEnabled(has_clipboard)
            
            # Create mirrored paste action
            paste_mirror_action = menu.addAction(QtGui.QIcon(UT.get_icon('paste.png')), "Paste Mirror")
            paste_mirror_action.triggered.connect(lambda: self.paste_buttons_at_position(position, mirror=True))
            paste_mirror_action.setEnabled(has_clipboard)

            menu.addSeparator()
            edit_mode_action = menu.addAction(QtGui.QIcon(UT.get_icon('edit.png')),"Exit Edit Mode")
            main_window = self.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                edit_mode_action.triggered.connect(main_window.toggle_edit_mode)
        else:
            edit_mode_action = menu.addAction(QtGui.QIcon(UT.get_icon('edit.png')),"Edit Picker")
            main_window = self.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                edit_mode_action.triggered.connect(main_window.toggle_edit_mode)
        
        if menu.actions():
            menu.exec_(self.mapToGlobal(position))

    def add_button_at_position(self, position):
        scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(position))
        
        main_window = self.window()
        if isinstance(main_window, UI.AnimPickerWindow):
            current_tab = main_window.tab_system.current_tab
            unique_id = main_window.generate_unique_id(current_tab)
            
            # Create button with default properties
            new_button = PB.PickerButton("Button", self, unique_id=unique_id)
            new_button.scene_position = scene_pos
            
            # Add button to canvas
            self.add_button(new_button)
            
            # Create button data for database
            button_data = {
                "id": unique_id,
                "label": new_button.label,
                "color": new_button.color,
                "opacity": new_button.opacity,
                "position": (new_button.scene_position.x(), new_button.scene_position.y()),
                "width": new_button.width,
                "height": new_button.height,
                "radius": new_button.radius,
                "assigned_objects": []
            }
            
            # Update PickerDataManager
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            tab_data['buttons'].append(button_data)
            DM.PickerDataManager.update_tab_data(current_tab, tab_data)

            self.update_button_positions()
            self.update()

    def paste_buttons_at_position(self, position, mirror=False):
        """FIXED: Paste buttons with proper batch database updates"""
        scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(position))
        copied_buttons = PB.ButtonClipboard.instance().get_all_buttons()
        
        #print(f"DEBUG: Attempting to paste {len(copied_buttons)} buttons")
        
        if not copied_buttons:
            return
            
        main_window = self.window()
        if isinstance(main_window, UI.AnimPickerWindow):
            current_tab = main_window.tab_system.current_tab
            #print(f"DEBUG: Current tab is {current_tab}")
            
            # Get initial button count for verification
            tab_data_before = DM.PickerDataManager.get_tab_data(current_tab)
            initial_count = len(tab_data_before['buttons'])
            #print(f"DEBUG: Initial button count in database: {initial_count}")
            
            # CRITICAL FIX: Collect all new button data BEFORE any database operations
            new_buttons_data = []
            new_buttons_widgets = []
            
            # STEP 1: Create all button widgets without database updates
            for i, button_data in enumerate(copied_buttons):
                #print(f"DEBUG: Processing button {i+1}/{len(copied_buttons)}")
                
                unique_id = main_window.generate_unique_id(current_tab)
                # CRITICAL FIX: Track newly generated IDs to prevent duplicates
                if current_tab not in main_window.available_ids:
                    main_window.available_ids[current_tab] = set()
                main_window.available_ids[current_tab].add(unique_id)
                #print(f"DEBUG: Generated unique_id: {unique_id}")
                
                # Create the button widget
                new_button = PB.PickerButton(button_data['label'], self, unique_id=unique_id)
                
                # Apply all copied attributes
                new_button.color = button_data['color']
                new_button.selectable = button_data['selectable']
                new_button.opacity = button_data['opacity']
                new_button.width = button_data['width']
                new_button.height = button_data['height']
                new_button.radius = button_data['radius'].copy() if hasattr(button_data['radius'], 'copy') else list(button_data['radius'])
                new_button.assigned_objects = button_data['assigned_objects'].copy() if button_data['assigned_objects'] else []
                new_button.mode = button_data.get('mode', 'select')
                new_button.script_data = button_data.get('script_data', {}).copy() if button_data.get('script_data') else {}
                
                # Handle pose-specific data
                if new_button.mode == 'pose':
                    if 'thumbnail_path' in button_data and button_data['thumbnail_path']:
                        new_button.thumbnail_path = button_data['thumbnail_path']
                        if os.path.exists(new_button.thumbnail_path):
                            new_button.thumbnail_pixmap = QtGui.QPixmap(new_button.thumbnail_path)
                    
                    if 'pose_data' in button_data and button_data['pose_data']:
                        new_button.pose_data = button_data['pose_data'].copy()
                
                # Position with mirroring option
                relative_position = button_data['relative_position']
                if mirror:
                    relative_position = QtCore.QPointF(-relative_position.x(), relative_position.y())
                new_button.scene_position = scene_pos + relative_position
                
                # CRITICAL: Add to canvas WITHOUT triggering database update
                # We need to modify add_button to accept an update_db parameter
                if hasattr(self, 'add_button_without_db_update'):
                    self.add_button_without_db_update(new_button)
                else:
                    # Fallback: temporarily disable database updates
                    old_method = main_window.update_button_data
                    main_window.update_button_data = lambda *args, **kwargs: None
                    self.add_button(new_button)
                    main_window.update_button_data = old_method
                
                new_buttons_widgets.append(new_button)
                
                # Prepare complete button data for database
                button_data_for_db = {
                    "id": unique_id,
                    "selectable": new_button.selectable,
                    "label": new_button.label,
                    "color": new_button.color,
                    "opacity": new_button.opacity,
                    "position": (new_button.scene_position.x(), new_button.scene_position.y()),
                    "width": new_button.width,
                    "height": new_button.height,
                    "radius": new_button.radius,
                    "assigned_objects": new_button.assigned_objects,
                    "mode": new_button.mode,
                    "script_data": new_button.script_data
                }
                
                # Add pose-specific data to database if needed
                if new_button.mode == 'pose':
                    if hasattr(new_button, 'thumbnail_path') and new_button.thumbnail_path:
                        button_data_for_db["thumbnail_path"] = new_button.thumbnail_path
                    if hasattr(new_button, 'pose_data') and new_button.pose_data:
                        button_data_for_db["pose_data"] = new_button.pose_data
                
                new_buttons_data.append(button_data_for_db)
            
            #print(f"DEBUG: Created {len(new_buttons_data)} button data entries")
            
            # STEP 2: Perform SINGLE batch database update
            if new_buttons_data:
                # Get fresh tab data
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                before_count = len(tab_data['buttons'])
                
                # Add ALL new buttons to tab data in one operation
                tab_data['buttons'].extend(new_buttons_data)
                after_count = len(tab_data['buttons'])
                
                # Update database once with all new data
                DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                
                # Force immediate save to ensure persistence
                DM.PickerDataManager.save_data(DM.PickerDataManager.get_data(), force_immediate=True)
                
                # Verify the operation succeeded
                verification_data = DM.PickerDataManager.get_tab_data(current_tab)
                final_count = len(verification_data['buttons'])
                
                #print(f"DEBUG: Database update - Before: {before_count}, After extend: {after_count}, Final: {final_count}")
                #print(f"DEBUG: Successfully added {final_count - initial_count} buttons to database")
                
                # Additional verification
                if final_count != initial_count + len(new_buttons_data):
                    print(f"WARNING: Expected {initial_count + len(new_buttons_data)} buttons, but database has {final_count}")
            if new_buttons_widgets:
                self.clear_selection()
                for button in new_buttons_widgets:
                    button.toggle_selection()
            # STEP 3: Update UI
            self.update_button_positions()
            self.update()
            self.update_hud_counts()  # Update HUD counter
            
            print(f"Paste operation completed: {len(new_buttons_widgets)} buttons created and saved")

    def mirror_button_positions(self):
        selected_buttons = self.get_selected_buttons()
        if selected_buttons:
            # Get the center of the selected buttons
            min_x = min(button.scene_position.x() for button in selected_buttons)
            max_x = max(button.scene_position.x() for button in selected_buttons)
            center_x = (min_x + max_x) / 2
            
            # Mirror positions around the center
            for button in selected_buttons:
                button.scene_position.setX(center_x - (button.scene_position.x() - center_x))
                button.update()
                button.changed.emit(button)
            
            # Update the canvas
            self.update_button_positions()
            # Update the database
        
    def cleanup_selection_manager(self):
        if hasattr(self, 'selection_manager'):
            self.selection_manager.close()
            self.selection_manager.deleteLater()
            del self.selection_manager
    #------------------------------------------------------------------------------
    def wheelEvent(self, event):
        # Get the wheel delta value - positive for wheel up, negative for wheel down
        delta_y = event.angleDelta().y()
        
        # Check for modifier keys
        alt_pressed = bool(event.modifiers() & QtCore.Qt.AltModifier)
        ctrl_pressed = bool(event.modifiers() & QtCore.Qt.ControlModifier)
        
        # Determine zoom direction based on wheel direction
        zoom_in = delta_y > 0
        
        # Set zoom factors based on modifiers
        if alt_pressed:
            event.ignore()
            return
        elif ctrl_pressed:
            # Ctrl key for finer control
            zoom_factor = 1.05 if zoom_in else 1 / 1.05
        else:
            # Default zoom speed
            zoom_factor = 1.2 if zoom_in else 1 / 1.2
        
        # Get mouse position in scene coordinates before zoom
        mouse_pos = QtCore.QPointF(event.position().x(), event.position().y())
        old_scene_pos = self.canvas_to_scene_coords(mouse_pos)

        # Apply zoom (only once!)
        self.zoom_factor *= zoom_factor
        
        # Limit zoom range for better performance
        self.zoom_factor = max(0.01, min(self.zoom_factor, 100.0))

        # Get new scene position and adjust pan to maintain mouse position
        new_scene_pos = self.canvas_to_scene_coords(mouse_pos)
        self.pan_offset += (new_scene_pos - old_scene_pos) * self.zoom_factor

        # Batch updates
        self.setUpdatesEnabled(False)
        self.update()
        self.update_button_positions()
        self.setUpdatesEnabled(True)
        
        # Update transform guides if visible
        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            self.transform_guides.update_position()

        self.setCursor(QtCore.Qt.ArrowCursor)
        # Ensure Maya window stays active
        #UT.maya_main_window().activateWindow()
        
        # Accept the event to prevent it from being processed further
        event.accept()

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            # Reset to original size when double-clicked
            self.zoom_factor = 1.0
            self.pan_offset = QtCore.QPointF(0, 0)
            self.update()
            self.update_button_positions()
            self.focus_canvas()
        super().mouseDoubleClickEvent(event)
        
    def mousePressEvent(self, event):
        if (hasattr(self, 'transform_guides') and self.transform_guides.isVisible() and event.button() == QtCore.Qt.LeftButton):
            # Convert to transform guides coordinates
            guides_pos = self.transform_guides.mapFromParent(event.pos())
            if self.transform_guides.geometry().contains(event.pos()):
                # Check if we're actually clicking on a handle first
                guides_pos_f = QtCore.QPointF(guides_pos)
                handle = self.transform_guides.get_handle_at_pos(guides_pos_f)
                
                if handle:
                    # We clicked on an actual handle - let transform guides handle it
                    transform_event = QtGui.QMouseEvent(
                        event.type(), guides_pos, event.globalPos(), 
                        event.button(), event.buttons(), event.modifiers()
                    )
                    self.transform_guides.mousePressEvent(transform_event)
                    if transform_event.isAccepted():
                        event.accept()
                        return
        
        # Get the position in the HUD's coordinate system
        hud_pos = self.hud.mapFromParent(event.pos())
        if self.hud.button_container.geometry().contains(hud_pos):
            # Let the HUD handle the event
            self.hud.toggle_button.click()
            return
        
        # Otherwise, handle the event normally
        if event.button() == QtCore.Qt.LeftButton:
            alt_pressed = bool(event.modifiers() & QtCore.Qt.AltModifier)
            
            # Store initial selection state for drag operations
            self.initial_selection_state = {button: button.is_selected for button in self.buttons}
            
            # Find if we clicked directly on a button
            clicked_button = None
            for button in self.buttons:
                if button.geometry().contains(event.pos()):
                    clicked_button = button
                    break
            
            if clicked_button:
                # Button was clicked - let the button handle its own selection logic
                pass
            elif alt_pressed:
                self.last_pan_pos = event.pos()
                event.accept()
            else:
                # Clicked empty space
                shift_held = event.modifiers() & QtCore.Qt.ShiftModifier
                
                if not shift_held:
                    # Clear selection when shift is not held
                    if self.edit_mode:
                        self.clear_selection()
                    else:
                        cmds.select(clear=True)
                        self.clear_selection()
                    
                    # IMPORTANT: Update initial selection state after clearing
                    self.initial_selection_state = {button: False for button in self.buttons}
                    
                    # Clear the drag tracking
                    self.buttons_in_current_drag.clear()
                    
                    # Hide transform guides immediately
                    if hasattr(self, 'transform_guides'):
                        self.transform_guides.setVisible(False)
                        self.transform_guides.visual_layer.setVisible(False)
                    
                    # Emit selection changed to update UI
                    self.button_selection_changed.emit()
                    self.update_hud_counts()
                self.setCursor(QtCore.Qt.ArrowCursor)
                # Start rubber band selection
                self.rubberband_origin = event.pos()
                self.rubberband.setGeometry(QtCore.QRect(self.rubberband_origin, QtCore.QSize()))
                self.rubberband.show()
                self.is_selecting = True
                
            event.accept()
            
        elif event.button() == QtCore.Qt.MiddleButton:
            self.last_pan_pos = event.pos()
            self.setCursor(QtCore.Qt.ArrowCursor)
            event.accept()
        else:
            super().mousePressEvent(event)
            self.setFocus()
        
        UT.maya_main_window().activateWindow()

    def mouseMoveEvent(self, event):
        alt_pressed = bool(event.modifiers() & QtCore.Qt.AltModifier)
        if self.is_selecting:
            selection_rect = QtCore.QRect(self.rubberband_origin, event.pos()).normalized()
            self.rubberband.setGeometry(selection_rect)
            
            # Update visual selection without triggering Maya updates
            self.update_visual_selection(selection_rect, event.modifiers() & QtCore.Qt.ShiftModifier)
            event.accept()
        elif ((event.buttons() == QtCore.Qt.LeftButton and alt_pressed) or 
              event.buttons() == QtCore.Qt.MiddleButton) and self.last_pan_pos:
            # Batch updates during pan
            self.setUpdatesEnabled(False)
            
            delta = event.pos() - self.last_pan_pos
            self.pan_offset += QtCore.QPointF(delta.x(), delta.y())
            self.last_pan_pos = event.pos()
            
            self.update()
            self.update_button_positions()
            
            self.setUpdatesEnabled(True)
        else:
            any_button_dragging = any(getattr(btn, 'dragging', False) for btn in self.buttons)
            if any_button_dragging:
                # Update transform guides during button drag
                if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
                    QtCore.QTimer.singleShot(1, self._update_transform_guides_position)
            super().mouseMoveEvent(event)
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.rubberband.hide()
            
            # Apply final selection and trigger Maya updates
            self.apply_final_selection(event.modifiers() & QtCore.Qt.ShiftModifier)
            
            # Clear temporary tracking sets
            self.buttons_in_current_drag.clear()
            self.initial_selection_state.clear()

            if self.edit_mode and hasattr(self, 'transform_guides'):
                QtCore.QTimer.singleShot(15, self.transform_guides.update_selection)
        elif event.button() == QtCore.Qt.LeftButton:
            self.last_pan_pos = None
            
        elif event.button() == QtCore.Qt.MiddleButton:
            self.last_pan_pos = None
        else:
            super().mouseReleaseEvent(event)
        
        self.button_selection_changed.emit()
        self.clicked.emit()
        UT.maya_main_window().activateWindow()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_button_positions()
        self.hud.setGeometry(self.rect())
        self.hud.raise_()
        # Update selection manager position if it exists and is visible
        if hasattr(self, 'selection_manager') and self.selection_manager.isVisible():
            button = self.selection_manager.picker_button
            if button:
                pos = button.mapToGlobal(button.rect().topRight())
                canvas_pos = self.mapFromGlobal(pos)
                self.selection_manager.move(canvas_pos + QtCore.QPoint(10, 0))

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Create a path for clipping
        clip_path = QtGui.QPainterPath()
        clip_path.addRoundedRect(
            self.rect().adjusted(1, 1, -1, -1),
            self.border_radius,
            self.border_radius
        )
        painter.setClipPath(clip_path)

        if not self.minimal_mode:
            # Draw background only in normal mode
            painter.fillRect(self.rect(), self.background_color)

            # Draw static dot pattern only in normal mode
            if self.show_dots:
                painter.save()
                painter.setOpacity(0.5)
                painter.fillRect(self.rect(), self.dot_texture)
                painter.restore()

        # Set up transform for canvas elements
        painter.save()
        center = QtCore.QPointF(self.width() / 2, self.height() / 2)
        painter.translate(center + self.pan_offset)
        painter.scale(self.zoom_factor, self.zoom_factor)

        # Calculate visible area in scene coordinates
        top_left = self.canvas_to_scene_coords(QtCore.QPointF(0, 0))
        bottom_right = self.canvas_to_scene_coords(QtCore.QPointF(self.width(), self.height()))
        visible_rect = self.rect()

        # Draw grid BEFORE axes (so axes appear on top)
        if not self.minimal_mode:
            self.draw_grid(painter, visible_rect)

        if not self.minimal_mode and self.show_axes:
            # Draw axes lines only in normal mode and when show_axes is True
            pen_width = .2 / self.zoom_factor
            
            # Draw X axis (red)
            pen = QtGui.QPen(QtGui.QColor(255, 0, 0))
            pen.setWidthF(pen_width)
            painter.setPen(pen)
            painter.drawLine(QtCore.QLineF(top_left.x(), 0, bottom_right.x(), 0))

            # Draw Y axis (green)
            pen.setColor(QtGui.QColor(0, 255, 0))
            painter.setPen(pen)
            painter.drawLine(QtCore.QLineF(0, top_left.y(), 0, bottom_right.y()))

        # Draw background image if available
        if self.background_image and not self.background_image.isNull():
            painter.setOpacity(self.image_opacity)
            scaled_width = self.background_image.width() * self.image_scale
            scaled_height = self.background_image.height() * self.image_scale
            image_rect = QtCore.QRectF(
                -scaled_width / 2,
                -scaled_height / 2,
                scaled_width,
                scaled_height
            )
            painter.drawImage(image_rect, self.background_image)

        painter.restore()

        # Remove clipping to draw the border
        painter.setClipping(False)

        if not self.minimal_mode:
            # Draw border only in normal mode
            pen = QtGui.QPen(self.border_color)
            pen.setWidth(self.border_width)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.NoBrush)
            painter.drawRoundedRect(
                self.rect().adjusted(1, 1, -1, -1),
                self.border_radius,
                self.border_radius
            )   