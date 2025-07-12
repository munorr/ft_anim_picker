from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
from shiboken6 import wrapInstance

import os

import bpy
from . import blender_ui as UI
from . import utils as UT
from . import picker_button as PB
from . import custom_button as CB
from . import tool_functions as TF
from . import data_management as DM
from . import custom_dialog as CD
from . import pb_transform_guides as TG
from .blender_curve_converter import create_buttons_from_blender_curves

class HUDWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)  # Make the whole widget transparent to mouse events
        self.setStyleSheet("background-color: transparent;")
        
        # Main layout for HUD elements
        self.layout = QtWidgets.QGridLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)
        #--------------------------------------------------------------------------------------------------------------------------------
        # Create the toggle button container that will catch mouse events
        self.button_container = QtWidgets.QWidget(self)
        self.button_container.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, False)  # This widget will catch mouse events
        self.button_container.setFixedSize(24, 24)
        #--------------------------------------------------------------------------------------------------------------------------------
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
        #--------------------------------------------------------------------------------------------------------------------------------
        # Stats container
        self.stats_container = QtWidgets.QWidget(self)
        self.stats_layout = QtWidgets.QHBoxLayout(self.stats_container)
        self.stats_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_layout.setSpacing(10)  # Space between labels
        #--------------------------------------------------------------------------------------------------------------------------------
        # Button count label
        self.button_count_label = QtWidgets.QLabel("Buttons: 0 / 0")
        self.button_count_label.setStyleSheet("color: rgba(255, 255, 255, 0.2);")
        #self.stats_layout.addWidget(self.button_count_label)
        self.layout.addWidget(self.button_count_label, 0, 0, QtCore.Qt.AlignBottom | QtCore.Qt.AlignLeft)
        #--------------------------------------------------------------------------------------------------------------------------------
        # Selection count label
        self.selection_layout = QtWidgets.QHBoxLayout()
        self.selection_layout.setContentsMargins(0, 0, 0, 0)
        self.selection_layout.setSpacing(2)
        self.selection_count_label = QtWidgets.QLabel("Selected: 0")
        self.selection_count_label.setStyleSheet("color: rgba(255, 255, 255, 0.2);")

        self.selected_bone_count_label = QtWidgets.QLabel("Selected: 0")
        self.selected_bone_count_label.setStyleSheet("color: rgba(255, 255, 255, 0.2);")
        #self.stats_layout.addWidget(self.selection_count_label)
        object_icon_label = QtWidgets.QLabel()
        object_icon_pixmap = UT.get_icon("object_data.png", opacity=0.2, size=14)
        object_icon_label.setPixmap(object_icon_pixmap)

        bone_icon_label = QtWidgets.QLabel()
        bone_icon_pixmap = UT.get_icon("bone_data.png", opacity=0.2, size=14)
        bone_icon_label.setPixmap(bone_icon_pixmap)
        
        self.selection_layout.addWidget(object_icon_label)
        self.selection_layout.addWidget(self.selection_count_label)
        self.selection_layout.addWidget(bone_icon_label)
        self.selection_layout.addWidget(self.selected_bone_count_label)

        self.layout.addLayout(self.selection_layout, 0, 1, QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight)
        #--------------------------------------------------------------------------------------------------------------------------------
        self.reset_buttons()
        
        # Store all HUD elements (except toggle button)
        self.hud_elements = [
            self.stats_container,
            self.button_count_label,
            self.selection_layout,
            self.reset_button_frame
        ]

        # Initialize visibility
        self.hud_visible = True
        
        # Start timer for updating Maya selection count
        self.update_timer = QtCore.QTimer(self)
        self.update_timer.timeout.connect(self.update_selection_count)
        self.update_timer.start(100)  

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
        """Update the Blender selection count"""
        try:
            # Get the count of selected objects in Blender
            #sel_count = len(bpy.context.selected_objects)
            sel_obj_count = len(TF.selected_objects())
            sel_bone_count = len(TF.selcected_bones_in_pose_mode())
            self.selection_count_label.setText(f": {sel_obj_count}")
            self.selected_bone_count_label.setText(f": {sel_bone_count}")
        except:
            # Handle case where Blender API access fails
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

        # Custom tooltip management
        self._tooltip_widget = None
        self._tooltip_timer = QtCore.QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_button_tooltip)
        self._current_hover_button = None
        self._tooltip_position = QtCore.QPoint()

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
        """Handle transform guide operations completion with optimized updates"""
        selected_buttons = self.get_selected_buttons()
        main_window = self.window()
        
        if hasattr(main_window, 'batch_update_buttons_to_database'):
            main_window.batch_update_buttons_to_database(selected_buttons)
        self.update_button_positions()
        self.update()

    def update_transform_guides(self):
        """Update transform guides when selection or edit mode changes"""
        if hasattr(self, 'transform_guides'):
            self.transform_guides.update_selection()

    def _update_transform_guides_position(self):
        """Helper method to update transform guides position"""
        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            self.transform_guides.calculate_bounding_rect()
            self.transform_guides.update_position()
    
    def hide_transform_guides(self):
        """Hide transform guides"""
        if hasattr(self, 'transform_guides'):
            self.transform_guides.setVisible(False)
            self.transform_guides.visual_layer.setVisible(False)
    
    def update_pan_offset(self, delta):
        """Simplified pan offset update"""
        self.pan_offset += QtCore.QPointF(delta.x(), delta.y())
        
        # Only update transform guides if actually visible and needed
        if (hasattr(self, 'transform_guides') and 
            self.transform_guides.isVisible() and 
            self.edit_mode):
            QtCore.QTimer.singleShot(10, self.transform_guides.update_position)
    
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

    def update_visual_selection(self, rect, add_to_selection=False, remove_from_selection=False):
        """Update button selection visually during rubber band drag with shape awareness"""
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
            
            # First check if button's bounding rect intersects with selection
            button_pos = button.scene_position
            button_rect = QtCore.QRectF(
                button_pos.x() - button.width/2,
                button_pos.y() - button.height/2,
                button.width,
                button.height
            )
            
            if scene_rect.intersects(button_rect):
                # Now check if the button's actual shape intersects with selection
                if self._button_shape_intersects_rect(button, scene_rect):
                    current_buttons.add(button)
        
        # Track selection changes for signal emission
        selection_changed = False
        
        # Update selection states
        for button in self.buttons:
            old_selection = button.is_selected
            
            if button in current_buttons:
                # Button is in selection rectangle
                if remove_from_selection:
                    # CTRL+SHIFT: Remove from selection when in rectangle
                    button.is_selected = False
                elif add_to_selection:
                    # SHIFT only: Add to selection when in rectangle
                    button.is_selected = True
                else:
                    # No modifiers: Select when in rectangle
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

    def _button_shape_intersects_rect(self, button, scene_rect):
        """
        Check if a button's actual shape intersects with a selection rectangle.
        This provides more precise selection for custom shapes.
        """
        try:
            # Get current zoom factor
            zoom_factor = self.zoom_factor
            
            # Create the button's path in scene coordinates
            button_rect = QtCore.QRectF(
                -button.width/2, -button.height/2,
                button.width, button.height
            )
            
            # Create the button path
            button_path = button._create_button_path(button_rect, button.radius, zoom_factor)
            
            # Transform the path to scene coordinates
            transform = QtGui.QTransform()
            transform.translate(button.scene_position.x(), button.scene_position.y())
            scene_button_path = transform.map(button_path)
            
            # Create a path from the selection rectangle
            selection_path = QtGui.QPainterPath()
            selection_path.addRect(scene_rect)
            
            # Check if the paths intersect
            return scene_button_path.intersects(selection_path)
            
        except Exception as e:
            print(f"Error checking button shape intersection: {e}")
            # Fallback to simple rectangle intersection
            button_pos = button.scene_position
            button_rect = QtCore.QRectF(
                button_pos.x() - button.width/2,
                button_pos.y() - button.height/2,
                button.width,
                button.height
            )
            return scene_rect.intersects(button_rect)
    #------------------------------------------------------------------------------
    def _show_button_tooltip(self):
        """Show tooltip for the currently hovered button"""
        if not self._current_hover_button:
            return
        
        # Rebuild tooltip content if needed
        if self._current_hover_button._tooltip_needs_update:
            self._current_hover_button._rebuild_tooltip_content()
        
        # Get or create tooltip widget
        if not self._tooltip_widget:
            self._tooltip_widget = self._current_hover_button.tooltip_widget
        else:
            # Reuse existing widget but update content
            self._tooltip_widget = self._current_hover_button.tooltip_widget
        
        # Position tooltip with screen boundary checking
        screen = QtWidgets.QApplication.screenAt(self._tooltip_position)
        if screen:
            screen_rect = screen.availableGeometry()
            tooltip_pos = self._tooltip_position + QtCore.QPoint(10, 10)
            
            # Adjust if tooltip would go off screen
            if tooltip_pos.x() + self._tooltip_widget.width() > screen_rect.right():
                tooltip_pos.setX(self._tooltip_position.x() - self._tooltip_widget.width() - 10)
            if tooltip_pos.y() + self._tooltip_widget.height() > screen_rect.bottom():
                tooltip_pos.setY(self._tooltip_position.y() - self._tooltip_widget.height() - 10)
                
            self._tooltip_widget.move(tooltip_pos)
        else:
            self._tooltip_widget.move(self._tooltip_position + QtCore.QPoint(10, 10))
        
        self._tooltip_widget.show()

    def _hide_button_tooltip(self):
        """Hide the current button tooltip"""
        self._tooltip_timer.stop()
        try:
            if self._tooltip_widget and self._tooltip_widget.isVisible():
                self._tooltip_widget.hide()
        except:
            pass
        self._current_hover_button = None

    def _update_hover_button(self, pos):
        """Update which button is being hovered over"""
        # Get button at position
        button = self._get_button_at_position(pos)
        
        if button != self._current_hover_button:
            # Hide current tooltip
            self._hide_button_tooltip()
            
            # Update hover state
            if self._current_hover_button:
                self._current_hover_button.is_hovered = False
                self._current_hover_button.update()
            
            self._current_hover_button = button
            
            if button:
                # Show new button as hovered
                button.is_hovered = True
                button.update()
                
                # Start tooltip timer
                self._tooltip_position = QtGui.QCursor.pos()
                self._tooltip_timer.start(800)  # 800ms delay
    #------------------------------------------------------------------------------
    # SELECTION LOGIC
    #------------------------------------------------------------------------------
    def apply_final_selection(self, add_to_selection=False, ctrl_held=False):
        """Apply final selection with Blender object lookup and counterpart selection"""
        if self.edit_mode:
            return
        
        # Get buttons that should be selected
        if hasattr(self, 'buttons_in_current_drag') and self.buttons_in_current_drag:
            # Use ordered selection for rubber band
            final_selections = self._get_ordered_selections(add_to_selection)
        else:
            # Use current selection (for single clicks) - maintain last selected button
            final_selections = [button for button in self.buttons if button.is_selected]
            
            # For single clicks, ensure proper ordering with last clicked button
            if hasattr(self, 'last_clicked_button') and self.last_clicked_button and self.last_clicked_button.is_selected:
                if self.last_clicked_button in final_selections:
                    final_selections.remove(self.last_clicked_button)
                    final_selections.append(self.last_clicked_button)
        
        if not final_selections:
            # If no buttons selected, clear Blender selection
            try:
                import bpy
                with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                    if bpy.context.mode == 'POSE':
                        bpy.ops.pose.select_all(action='DESELECT')
                    elif bpy.context.mode == 'OBJECT':
                        bpy.ops.object.select_all(action='DESELECT')
            except:
                pass
            return
        
        # Check if we should select counterparts
        if ctrl_held:
            # Select counterparts for all selected buttons
            resolved_items, missing_objects = self._resolve_counterpart_items(final_selections)
        else:
            # Regular selection - resolve objects and bones from button data
            resolved_items, missing_objects = self._resolve_selection_items(final_selections)
        
        # Switch to pose mode if bones are being selected
        if resolved_items['bones']:
            self._enter_pose_mode_for_bones(resolved_items['bones'])
        
        # Apply selection in Blender with proper active item
        self._apply_blender_selection(resolved_items, add_to_selection, final_selections[-1] if final_selections else None)
        
        # Handle UI updates
        self._handle_post_selection_updates(missing_objects)
        import bpy
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            bpy.ops.ed.undo_push(message="Select Object")

    def _get_ordered_selections(self, add_to_selection):
        """Build ordered list of buttons to select based on drag operation"""
        final_selections = []
        
        # For rubber band selection, we need to determine the last selected button differently
        # Since buttons_in_current_drag is a set, we can't rely on iteration order
        
        # Add previously selected buttons if adding to selection
        if add_to_selection:
            for button in self.buttons:
                if button.is_selected and button not in self.buttons_in_current_drag:
                    final_selections.append(button)
        
        # Add buttons from current drag operation
        # Since we can't determine the exact order from the set, we'll add them in a consistent order
        # and rely on the last mouse interaction to determine the active button
        current_drag_buttons = []
        for button in self.buttons_in_current_drag:
            if button.is_selected:
                current_drag_buttons.append(button)
        
        # Sort by some consistent criteria (e.g., position) to ensure predictable ordering
        current_drag_buttons.sort(key=lambda b: (b.scene_position.y(), b.scene_position.x()))
        
        # Add all current drag buttons except the one we'll designate as "last"
        if len(current_drag_buttons) > 1:
            final_selections.extend(current_drag_buttons[:-1])
        
        # Add the last button from current drag (or the only one if there's just one)
        if current_drag_buttons:
            # For rubber band selection, use the last button in our sorted list
            # For single button selection, this will be the clicked button
            final_selections.append(current_drag_buttons[-1])
        
        return final_selections

    def _resolve_selection_items(self, buttons):
        """Resolve button objects to Blender objects/bones"""
        resolved_items = {'bones': [], 'objects': []}
        missing_objects = set()
        
        # Get current namespace for object resolution
        current_namespace = self._get_current_namespace()
        
        for button in buttons:
            if not button.assigned_objects:
                continue
                
            for obj_data in button.assigned_objects:
                try:
                    if obj_data.get('is_bone', False):
                        bone_info = self._resolve_bone(obj_data)
                        if bone_info:
                            resolved_items['bones'].append(bone_info)
                        else:
                            missing_objects.add(self._format_missing_bone(obj_data))
                    else:
                        obj_info = self._resolve_object(obj_data, current_namespace)
                        if obj_info:
                            resolved_items['objects'].append(obj_info)
                        else:
                            missing_objects.add(self._format_missing_object(obj_data))
                except Exception as e:
                    print(f"Error resolving selection item: {e}")
                    continue
        
        return resolved_items, missing_objects

    def _resolve_bone_with_namespace(self, obj_data, current_namespace):
        """Resolve bone data to Blender bone reference with namespace priority"""
        import bpy
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            bone_name = obj_data.get('name', '')
            original_armature_name = obj_data.get('armature', '')
            
            # Priority 1: Try with current namespace if one is selected
            if current_namespace and current_namespace != 'None':
                if (current_namespace in bpy.data.objects and 
                    bpy.data.objects[current_namespace].type == 'ARMATURE' and
                    bone_name in bpy.data.objects[current_namespace].pose.bones):
                    return {
                        'armature': current_namespace,
                        'bone': bone_name
                    }
            
            # Priority 2: Try with original armature (fallback)
            if (original_armature_name in bpy.data.objects and 
                bpy.data.objects[original_armature_name].type == 'ARMATURE' and
                bone_name in bpy.data.objects[original_armature_name].pose.bones):
                return {
                    'armature': original_armature_name,
                    'bone': bone_name
                }
            
            # Priority 3: Search all armatures for the bone name
            for obj in bpy.context.scene.objects:
                if (obj.type == 'ARMATURE' and obj.pose and 
                    bone_name in obj.pose.bones):
                    return {
                        'armature': obj.name,
                        'bone': bone_name
                    }
        
        return None

    def _resolve_bone(self, obj_data):
        """Updated resolve bone method that uses namespace priority"""
        current_namespace = self._get_current_namespace()
        return self._resolve_bone_with_namespace(obj_data, current_namespace)

    def _resolve_object(self, obj_data, current_namespace):
        """Resolve object data to Blender object reference"""
        import bpy
        
        obj_name = obj_data.get('name', '')
        
        # Try direct name match first
        if obj_name in bpy.data.objects:
            return {'name': obj_name}
        
        # Try with namespace prefix
        if current_namespace and current_namespace != 'None':
            namespaced_name = f"{current_namespace}_{obj_name}"
            if namespaced_name in bpy.data.objects:
                return {'name': namespaced_name}
        
        return None

    def _apply_blender_selection(self, resolved_items, add_to_selection, last_selected_button=None):
        """Apply the actual selection in Blender"""
        import bpy
        
        bones = resolved_items['bones']
        objects = resolved_items['objects']
        
        # Find the active item from the last selected button
        active_bone_info = None
        active_object_info = None
        
        if last_selected_button and last_selected_button.assigned_objects:
            for obj_data in last_selected_button.assigned_objects:
                if obj_data.get('is_bone', False):
                    # Find this bone in our resolved bones
                    bone_name = obj_data.get('name', '')
                    for bone_info in bones:
                        if bone_info['bone'] == bone_name:
                            active_bone_info = bone_info
                            break
                else:
                    # Find this object in our resolved objects
                    obj_name = obj_data.get('name', '')
                    for obj_info in objects:
                        if obj_info['name'] == obj_name or obj_info['name'].endswith(f"_{obj_name}"):
                            active_object_info = obj_info
                            break
        
        try:
            if bones:
                self._select_bones_with_namespace(bones, add_to_selection, active_bone_info)
            
            if objects:
                self._select_objects(objects, add_to_selection, has_bones=bool(bones), active_object_info=active_object_info)
                
        except Exception as e:
            print(f"Error during Blender selection: {e}")

    def _deselect_bones(self, armature_name):
        """Deselect all bones in an armature - OPTIMIZED VERSION"""
        try:
            if armature_name not in bpy.data.objects:
                return []
            
            armature_obj = bpy.data.objects[armature_name]
            if armature_obj.type != 'ARMATURE' or not armature_obj.data:
                return []
            
            # Get all bone names
            bone_names = [bone.name for bone in armature_obj.data.bones]
            
            # Deselect all bones at once
            for bone_name in bone_names:
                if bone_name in armature_obj.pose.bones:
                    armature_obj.pose.bones[bone_name].bone.select = False
            
            return bone_names
            
        except Exception as e:
            print(f"Error deselecting bones in armature {armature_name}: {e}")
            return []

    def _select_bones_with_namespace(self, bones, add_to_selection, active_bone_info=None):
        """Updated bone selection with namespace priority and proper active bone"""
        if not bones:
            return
        
        # Get current namespace
        current_namespace = self._get_current_namespace()
        
        selected_bones = []
        armatures_processed = set()
        
        # Group bones by target armature (considering namespace)
        armature_bones = {}
        for bone_info in bones:
            original_armature = bone_info['armature']
            bone_name = bone_info['bone']
            
            # Determine target armature with namespace priority
            target_armature = None
            
            # Priority 1: Current namespace if available
            if (current_namespace and current_namespace != 'None' and 
                current_namespace in bpy.data.objects and
                bpy.data.objects[current_namespace].type == 'ARMATURE' and
                bone_name in bpy.data.objects[current_namespace].pose.bones):
                target_armature = current_namespace
            
            # Priority 2: Original armature (fallback)
            elif (original_armature in bpy.data.objects and 
                bpy.data.objects[original_armature].type == 'ARMATURE' and
                bone_name in bpy.data.objects[original_armature].pose.bones):
                target_armature = original_armature
            
            # Priority 3: Search all armatures
            else:
                for obj in bpy.context.scene.objects:
                    if (obj.type == 'ARMATURE' and obj.pose and 
                        bone_name in obj.pose.bones):
                        target_armature = obj.name
                        break
            
            if target_armature:
                if target_armature not in armature_bones:
                    armature_bones[target_armature] = []
                armature_bones[target_armature].append(bone_name)
            else:
                print(f"Warning: Bone '{bone_name}' not found in any armature")
        
        # Clear bone selections once per armature (only if not adding to selection)
        if not add_to_selection:
            for armature_name in armature_bones.keys():
                self._deselect_bones(armature_name)
        
        # Select all the bones by armature
        active_bone_set = False
        for armature_name, bone_names in armature_bones.items():
            try:
                armature_obj = bpy.data.objects[armature_name]
                
                for bone_name in bone_names:
                    if bone_name in armature_obj.pose.bones:
                        bone_to_select = armature_obj.pose.bones[bone_name].bone
                        bone_to_select.select = True
                        selected_bones.append(f"{bone_name} (in {armature_name})")
                        
                        # Set as active if this is the active bone or if no active bone specified and not set yet
                        if ((active_bone_info and 
                            active_bone_info['bone'] == bone_name and 
                            active_bone_info['armature'] == armature_name) or
                            (not active_bone_info and not active_bone_set)):
                            armature_obj.data.bones.active = bone_to_select
                            active_bone_set = True
                            
            except Exception as e:
                print(f"Error selecting bones in armature {armature_name}: {e}")
                continue
        
        if selected_bones:
            #print(f"Selected bones: {', '.join(selected_bones)}")
            pass
        else:
            print("No bones were selected")
    
    def _enter_pose_mode_for_bones(self, bones):
        """Switch to pose mode for the armature containing the selected bones"""
        import bpy
        
        if not bones:
            return
        
        try:
            with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                # Get the first armature from the bone selection
                first_bone = bones[0]
                armature_name = first_bone['armature']
                
                if armature_name not in bpy.data.objects:
                    print(f"Warning: Armature '{armature_name}' not found")
                    return
                
                armature_obj = bpy.data.objects[armature_name]
                
                # First, ensure we're in object mode to properly set the active object
                if bpy.context.mode != 'OBJECT':
                    try:
                        bpy.ops.object.mode_set(mode='OBJECT')
                    except RuntimeError:
                        # If we can't switch to object mode, clear selections manually
                        pass
                
                # Clear all object selections using direct API instead of operators
                for obj in bpy.context.scene.objects:
                    obj.select_set(False)
                
                # Set the armature as the active and selected object
                bpy.context.view_layer.objects.active = armature_obj
                armature_obj.select_set(True)
                
                # Now switch to pose mode
                if bpy.context.mode != 'POSE':
                    try:
                        bpy.ops.object.mode_set(mode='POSE')
                    except RuntimeError as e:
                        print(f"Failed to switch to pose mode: {e}")
                        return
                
                # Clear any existing pose bone selections
                if bpy.context.mode == 'POSE' and armature_obj.pose:
                    for pose_bone in armature_obj.pose.bones:
                        pose_bone.bone.select = False
                
                #print(f"Successfully switched to pose mode for armature: {armature_name}")
            
        except Exception as e:
            print(f"Error entering pose mode for bones: {e}")
            # Fallback: try without temp_override
            try:
                with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                    # Get the first armature from the bone selection
                    first_bone = bones[0]
                    armature_name = first_bone['armature']
                    
                    if armature_name not in bpy.data.objects:
                        return
                    
                    armature_obj = bpy.data.objects[armature_name]
                    
                    # Simple approach without operators that might fail
                    # Clear selections using direct API
                    for obj in bpy.context.scene.objects:
                        obj.select_set(False)
                    
                    # Set active object
                    bpy.context.view_layer.objects.active = armature_obj
                    armature_obj.select_set(True)
                    
                    # Try to switch mode
                    if bpy.context.active_object == armature_obj and armature_obj.type == 'ARMATURE':
                        if bpy.context.mode != 'POSE':
                            bpy.ops.object.mode_set(mode='POSE')
                            
                        #print(f"Fallback: Successfully switched to pose mode for armature: {armature_name}")
            except Exception as fallback_error:
                print(f"Fallback also failed: {fallback_error}")
        
    def _get_selected_bones(self):
        """Get currently selected bones in pose mode"""
        pass

    def _select_objects(self, objects, add_to_selection, has_bones=False, active_object_info=None):
        """Select regular objects with proper active object"""
        import bpy
        
        # Only switch to object mode if we don't have bones selected
        if not has_bones and bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        # Clear object selection if not adding and no bones
        if not add_to_selection and not has_bones:
            bpy.ops.object.select_all(action='DESELECT')
        
        selected_objects = []
        active_object_set = False
        
        for obj_info in objects:
            obj_name = obj_info['name']
            if obj_name in bpy.data.objects:
                bpy.data.objects[obj_name].select_set(True)
                selected_objects.append(obj_name)
                
                # Set as active if this is the active object or if no active object specified and not set yet
                if not has_bones:  # Only set active object if no bones are selected
                    if ((active_object_info and active_object_info['name'] == obj_name) or
                        (not active_object_info and not active_object_set)):
                        bpy.context.view_layer.objects.active = bpy.data.objects[obj_name]
                        active_object_set = True
        
        #print(f"Selected objects: {', '.join(selected_objects)}")

    def _get_current_namespace(self):
        """Get current namespace from main window"""
        main_window = self.window()
        if hasattr(main_window, 'namespace_dropdown'):
            return main_window.namespace_dropdown.currentText()
        return None

    def _get_item_id(self, obj_data):
        """Get unique identifier for an object/bone"""
        if obj_data.get('is_bone', False):
            return f"{obj_data.get('armature', '')}|{obj_data.get('name', '')}"
        return obj_data.get('name', '')

    def _format_missing_bone(self, obj_data):
        """Format missing bone message"""
        bone_name = obj_data.get('name', '')
        armature_name = obj_data.get('armature', '')
        return f"- {bone_name} (in {armature_name})"

    def _format_missing_object(self, obj_data):
        """Format missing object message"""
        obj_name = obj_data.get('name', '')
        return f"- {obj_name}"

    def _handle_post_selection_updates(self, missing_objects):
        """Handle UI updates after selection"""
        # Show missing objects dialog
        if missing_objects:
            self._show_missing_objects_dialog(missing_objects)
        
        # Update button visuals
        for button in self.buttons:
            button.update()
            button.update_tooltip()
        
        # Emit signals
        self.button_selection_changed.emit()
        self.update_hud_counts()

    def _show_missing_objects_dialog(self, missing_objects):
        """Show dialog for missing objects"""
        '''parent_widget = self.parentWidget()
        dialog = CD.CustomDialog(parent_widget, title="Missing Objects", size=(250, -1), info_box=True)
        message_label = QtWidgets.QLabel("The following objects were not found:")
        details_label = QtWidgets.QLabel('\n'.join(sorted(f"<b><font color='#00ade6'>{objects}</font></b>" for objects in missing_objects)))
        note_label = QtWidgets.QLabel("[Objects may have been deleted or renamed]")
        
        dialog.add_widget(message_label)
        dialog.add_widget(details_label)
        dialog.add_widget(note_label)
        dialog.add_button_box()
        dialog.exec_()'''
        message_txt = "The following objects were not found:"
        details_txt = '\n'.join(sorted(objects for objects in missing_objects))
        note_txt = "[Objects may have been deleted or renamed]"
        print(message_txt)
        print(details_txt)
        print(note_txt)
    #------------------------------------------------------------------------------
    def _resolve_counterpart_items(self, buttons):
        """Resolve counterpart objects/bones for selected buttons"""
        resolved_items = {'bones': [], 'objects': []}
        missing_objects = set()
        
        # Get current namespace for object resolution
        current_namespace = self._get_current_namespace()
        
        # Get naming conventions and mirror preferences
        naming_conventions = self._get_naming_conventions("", "")
        
        for button in buttons:
            if not button.assigned_objects:
                continue
                
            for obj_data in button.assigned_objects:
                try:
                    if obj_data.get('is_bone', False):
                        counterpart_bone = self._resolve_bone_counterpart(obj_data, naming_conventions, current_namespace)
                        if counterpart_bone:
                            resolved_items['bones'].append(counterpart_bone)
                        else:
                            missing_objects.add(f"- {obj_data.get('name', '')} (bone counterpart)")
                    else:
                        counterpart_obj = self._resolve_object_counterpart(obj_data, naming_conventions, current_namespace)
                        if counterpart_obj:
                            resolved_items['objects'].append(counterpart_obj)
                        else:
                            missing_objects.add(f"- {obj_data.get('name', '')} (object counterpart)")
                except Exception as e:
                    print(f"Error resolving counterpart item: {e}")
                    continue
        
        return resolved_items, missing_objects

    def _resolve_bone_counterpart(self, obj_data, naming_conventions, current_namespace):
        """Resolve bone counterpart using naming conventions"""
        import bpy
        
        bone_name = obj_data.get('name', '')
        original_armature_name = obj_data.get('armature', '')
        
        # Find the mirrored bone name
        mirrored_bone_name, is_center_bone = self._find_mirrored_name(bone_name, naming_conventions)
        
        # If it's the same name (center bone), return the original
        if mirrored_bone_name == bone_name:
            return self._resolve_bone_with_namespace(obj_data, current_namespace)
        
        # Create counterpart bone data
        counterpart_data = {
            'name': mirrored_bone_name,
            'armature': original_armature_name,
            'is_bone': True
        }
        
        # Try to resolve the counterpart bone
        return self._resolve_bone_with_namespace(counterpart_data, current_namespace)

    def _resolve_object_counterpart(self, obj_data, naming_conventions, current_namespace):
        """Resolve object counterpart using naming conventions"""
        import bpy
        
        obj_name = obj_data.get('name', '')
        
        # Find the mirrored object name
        mirrored_obj_name, is_center_object = self._find_mirrored_name(obj_name, naming_conventions)
        
        # If it's the same name (center object), return the original
        if mirrored_obj_name == obj_name:
            return self._resolve_object(obj_data, current_namespace)
        
        # Create counterpart object data
        counterpart_data = {
            'name': mirrored_obj_name,
            'is_bone': False
        }
        
        # Try to resolve the counterpart object
        return self._resolve_object(counterpart_data, current_namespace)

    def _get_naming_conventions(self, L, R):
        """
        Returns a list of naming conventions for left and right sides.
        
        Args:
            L (str): Custom left side identifier
            R (str): Custom right side identifier
            
        Returns:
            list: List of dictionaries with left and right patterns
        """
        naming_conventions = [
            # Prefix
            {"left": "L_", "right": "R_"},
            {"left": "left_", "right": "right_"},
            {"left": "Lf_", "right": "Rt_"},
            {"left": "lt_", "right": "rt_"},
            
            # Suffix
            {"left": "_L", "right": "_R"},
            {"left": "_left", "right": "_right"},
            {"left": "_lt", "right": "_rt"},
            {"left": "_lf", "right": "_rf"},
            {"left": "_l_", "right": "_r_"},
            {"left": ".L", "right": ".R"},  # Blender bone naming convention
            {"left": ".l", "right": ".r"},  # Blender bone naming convention
            
            # Other patterns
            {"left": ":l_", "right": ":r_"},
            {"left": "^l_", "right": "^r_"},
            {"left": "_l$", "right": "_r$"},
            {"left": ":L", "right": ":R"},
            {"left": "^L", "right": "^R"},
            {"left": "Left", "right": "Right"},
            {"left": "left", "right": "right"}
        ]
        
        # Add custom naming convention if provided
        if L and R:
            naming_conventions.append({"left": L, "right": R})
            
        return naming_conventions

    def _find_mirrored_name(self, obj_name, naming_conventions):
        """
        Finds the mirrored name for the given object/bone name.
        
        Args:
            obj_name (str): Object/bone name to find mirror for
            naming_conventions (list): List of naming conventions
            
        Returns:
            tuple: (mirrored_name, is_center_object) where mirrored_name is the name of the mirrored object/bone
                and is_center_object is a boolean indicating if the object is a center object
        """
        is_center_object = True  # Assume it's a center object until proven otherwise
        
        for convention in naming_conventions:
            left_pattern = convention["left"]
            right_pattern = convention["right"]
            
            if left_pattern in obj_name:
                is_center_object = False
                mirrored_name = obj_name.replace(left_pattern, right_pattern)
                return mirrored_name, is_center_object
            elif right_pattern in obj_name:
                is_center_object = False
                mirrored_name = obj_name.replace(right_pattern, left_pattern)
                return mirrored_name, is_center_object
        
        # If no pattern matched, it's a center object - return the same name
        return obj_name, is_center_object
    #------------------------------------------------------------------------------
    def get_selected_buttons(self):
        """Cached version of get_selected_buttons for better performance"""
        if not hasattr(self, '_selected_buttons_cache'):
            self._selected_buttons_cache = []
            self._cache_valid = False
        
        if not self._cache_valid:
            self._selected_buttons_cache = [button for button in self.buttons if button.is_selected]
            self._cache_valid = True
        
        return self._selected_buttons_cache

    def clear_selection(self):
        """Clear button selection efficiently"""
        selection_changed = False
        for button in self.buttons:
            if button.is_selected:
                button.is_selected = False
                button.update()
                selection_changed = True
        
        if selection_changed:
            # Invalidate cache
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            self.button_selection_changed.emit()
            self.update_hud_counts()

            if hasattr(self, 'transform_guides'):
                self.transform_guides.setVisible(False)
                self.transform_guides.visual_layer.setVisible(False)

    def on_button_selected(self, button, is_selected):
        """Optimized button selection handler"""
        # Invalidate selection cache
        if hasattr(self, '_cache_valid'):
            self._cache_valid = False
        
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
        """Get the topmost visible button at the given position, respecting button shapes"""
        # Check buttons in reverse order (topmost first due to z-order)
        for button in reversed(self.buttons):
            if not button.isVisible():
                continue
                
            # First check if position is within the button's bounding rectangle
            if not button.geometry().contains(pos):
                continue
            
            # Convert canvas position to button-local coordinates
            local_pos = button.mapFromParent(pos)
            
            # Check if the position is within the button's actual shape
            if button.contains_point(local_pos):
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
    # BUTTON MANAGEMENT
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
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                main_window.update_button_data(button, deleted=True)
            
            # Update HUD button count
            self.update_hud_counts()
            self._update_guides_after_button_change()
            self.transform_guides.setVisible(False)
            self.transform_guides.visual_layer.setVisible(False)

    def update_button_positions(self):
        """Optimized version with batching"""
        if not self.buttons:
            return
            
        visible_rect = self.rect()
        
        # Early exit if no size
        if visible_rect.width() <= 0 or visible_rect.height() <= 0:
            return
        
        # Use larger margin like Maya version
        visible_scene_rect = QtCore.QRectF(
            self.canvas_to_scene_coords(QtCore.QPointF(visible_rect.left(), visible_rect.top())),
            self.canvas_to_scene_coords(QtCore.QPointF(visible_rect.right(), visible_rect.bottom()))
        ).normalized()
        
        # Increase margin from 0.25 to 0.5 like Maya
        margin = max(visible_scene_rect.width() * 0.5, visible_scene_rect.height() * 0.5)
        visible_scene_rect.adjust(-margin, -margin, margin, margin)
        
        # Batch geometry updates
        geometry_updates = []
        buttons_to_show = []
        buttons_to_hide = []
        
        for button in self.buttons:
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
            
        # Apply all updates at once
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
        
    def update_button_data(self, button, deleted=False):
        main_window = self.window()
        if isinstance(main_window, UI.BlenderAnimPickerWindow):
            main_window.update_button_data(button, deleted)

    def on_button_changed(self, button):
        main_window = self.window()
    
        # Only update database if not in batch mode
        if not getattr(main_window, 'batch_update_active', False):
            self.update_button_data(button)
        
        # Throttle transform guide updates
        if (hasattr(self, 'transform_guides') and 
            self.transform_guides.isVisible() and 
            button in self.get_selected_buttons()):
            
            if not hasattr(self, '_guide_update_throttle'):
                self._guide_update_throttle = QtCore.QTimer()
                self._guide_update_throttle.setSingleShot(True)
                self._guide_update_throttle.timeout.connect(
                    lambda: self.transform_guides.update_selection() if hasattr(self, 'transform_guides') else None
                )
            
            self._guide_update_throttle.stop()
            self._guide_update_throttle.start(50)  # 50ms throttle
    
    def update_hud_counts(self):
        """Optimized HUD count update with caching"""
        if not hasattr(self, '_last_hud_counts'):
            self._last_hud_counts = (-1, -1)
        
        selected_count = len(self.get_selected_buttons())
        total_count = len(self.buttons)
        
        # Only update if counts actually changed
        if self._last_hud_counts != (total_count, selected_count):
            self.hud.update_button_count(total_count, selected_count)
            self._last_hud_counts = (total_count, selected_count)
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
    # CANVAS BACKGROUND
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
        if isinstance(main_window, UI.BlenderAnimPickerWindow):
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
        """Handle drag enter events for image and SVG files"""
        if event.mimeData().hasUrls():
            # Check if any of the URLs are image or SVG files
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if self._is_valid_image_file(file_path) or self._is_valid_svg_file(file_path):
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
        """Handle drop events for image and SVG files"""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if self._is_valid_svg_file(file_path):
                    # Handle SVG file - show dialog first
                    drop_position = QtCore.QPointF(event.pos())
                    
                    # Show import options dialog
                    import_options = self._show_svg_import_dialog()
                    
                    if import_options['import']:
                        if import_options['separate']:
                            # Create separate buttons (existing functionality)
                            self._create_buttons_from_svg(file_path, drop_position)
                        else:
                            # Create combined button (new functionality)
                            self._create_combined_button_from_svg(file_path, drop_position)
                    
                    event.acceptProposedAction()
                    return
                
                elif self._is_valid_image_file(file_path):
                    # Handle image file - set as background
                    main_window = self.window()
                    if isinstance(main_window, UI.BlenderAnimPickerWindow):
                        self.set_background_image(file_path)
                        event.acceptProposedAction()
                        return
        event.ignore()
    
    def _is_valid_svg_file(self, file_path):
        """Check if the file is a valid SVG file"""
        if not os.path.isfile(file_path):
            return False
            
        # Get the file extension
        _, ext = os.path.splitext(file_path)
        return ext.lower() == '.svg'
    
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
    def _create_buttons_from_svg(self, svg_file_path, drop_position):
        """Create picker buttons from all paths in an SVG file with preserved layout"""
        import xml.etree.ElementTree as ET
        
        try:
            # Parse the SVG file
            tree = ET.parse(svg_file_path)
            root = tree.getroot()
            
            # Find all path elements
            path_elements = []
            
            # Try with namespace first
            path_elements = root.findall('.//{http://www.w3.org/2000/svg}path')
            if not path_elements:
                # Try without namespace
                path_elements = root.findall('.//path')
            
            if not path_elements:
                # Show error dialog
                dialog = CD.CustomDialog(self, title="No Paths Found", size=(250, 100), info_box=True)
                message_label = QtWidgets.QLabel("The SVG file does not contain any path elements.")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
                return
            
            # Store SVG path for ID generation
            self._current_svg_path = svg_file_path
            
            # STEP 1: Get SVG viewBox/dimensions for coordinate system reference
            svg_bounds = self._get_svg_bounds(root)
            svg_width = svg_bounds['width']
            svg_height = svg_bounds['height']
            svg_x_offset = svg_bounds.get('x', 0)
            svg_y_offset = svg_bounds.get('y', 0)
            
            #print(f"SVG bounds: {svg_width}x{svg_height}, offset: ({svg_x_offset}, {svg_y_offset})")
            
            # STEP 2: Calculate all path bounds in SVG coordinate space
            path_data_list = []
            all_path_bounds = []
            
            for i, path_element in enumerate(path_elements):
                if 'd' not in path_element.attrib:
                    continue
                    
                path_data = path_element.attrib['d']
                
                # Get the bounding box of this path in original SVG coordinates
                path_bounds = self._get_path_bounds_in_svg_coords(path_data, path_element)
                
                if path_bounds and not path_bounds.isEmpty():
                    path_info = {
                        'index': i,
                        'element': path_element,
                        'path_data': path_data,
                        'bounds': path_bounds,
                        'center': path_bounds.center()
                    }
                    path_data_list.append(path_info)
                    all_path_bounds.append(path_bounds)
            
            if not path_data_list:
                print("No valid paths found")
                return
            
            # STEP 3: Calculate the overall layout bounds in SVG coordinates
            if all_path_bounds:
                # Find the bounding rectangle that contains all paths
                min_x = min(bounds.left() for bounds in all_path_bounds)
                max_x = max(bounds.right() for bounds in all_path_bounds)
                min_y = min(bounds.top() for bounds in all_path_bounds)
                max_y = max(bounds.bottom() for bounds in all_path_bounds)
                
                layout_bounds = QtCore.QRectF(min_x, min_y, max_x - min_x, max_y - min_y)
                layout_center = layout_bounds.center()
                
                #print(f"Layout bounds: {layout_bounds}, center: {layout_center}")
            else:
                layout_center = QtCore.QPointF(svg_width/2, svg_height/2)
                layout_bounds = QtCore.QRectF(0, 0, svg_width, svg_height)
            
            # STEP 4: Calculate scale factor for reasonable button sizes
            # Target the entire layout to fit within a reasonable screen area
            target_layout_size = 800  # Target size for the entire layout
            current_layout_size = max(layout_bounds.width(), layout_bounds.height())
            layout_scale = target_layout_size / current_layout_size if current_layout_size > 0 else 1.0
            
            # Clamp scale to reasonable range
            layout_scale = max(0.1, min(layout_scale, 10.0))
            
            #print(f"Layout scale: {layout_scale}")
            
            # Convert drop position to scene coordinates
            scene_drop_pos = self.canvas_to_scene_coords(drop_position)
            
            # STEP 5: Create buttons with preserved spatial relationships
            created_buttons = []
            main_window = self.window()
            
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                current_tab = main_window.tab_system.current_tab
                
                # Get existing IDs to avoid conflicts
                existing_ids = set()
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                for button in tab_data.get('buttons', []):
                    existing_ids.add(button['id'])
                
                # Also add IDs from current canvas buttons
                for button in self.buttons:
                    existing_ids.add(button.unique_id)
                
                # Add any pending IDs from available_ids cache
                if current_tab in main_window.available_ids:
                    existing_ids.update(main_window.available_ids[current_tab])
                
                # Prepare for batch database update
                new_buttons_data = []
                
                for j, path_info in enumerate(path_data_list):
                    # Generate unique ID
                    unique_id = self._generate_svg_unique_id(current_tab, existing_ids, path_info['index'])
                    existing_ids.add(unique_id)
                    
                    # Create button label
                    button_label = path_info['element'].get('id', '')
                    if not button_label:
                        button_label = f"Shape_{j+1}"
                    
                    # Create the button
                    new_button = PB.PickerButton('', self, unique_id=unique_id, color="#3096bb")
                    
                    # Set up the button with SVG path
                    new_button.shape_type = 'custom_path'
                    new_button.svg_path_data = path_info['path_data']
                    new_button.svg_file_path = svg_file_path
                    
                    # CRITICAL: Calculate position to preserve exact SVG layout
                    path_center = path_info['center']
                    
                    # Calculate offset from layout center in SVG coordinates
                    svg_offset_x = path_center.x() - layout_center.x()
                    svg_offset_y = path_center.y() - layout_center.y()
                    
                    # Scale the offset and apply to drop position
                    scaled_offset_x = svg_offset_x * layout_scale
                    scaled_offset_y = svg_offset_y * layout_scale
                    
                    # Position relative to drop position
                    button_x = scene_drop_pos.x() + scaled_offset_x
                    button_y = scene_drop_pos.y() + scaled_offset_y
                    
                    new_button.scene_position = QtCore.QPointF(button_x, button_y)
                    
                    # STEP 6: Calculate button size based on individual path bounds
                    path_bounds = path_info['bounds']
                    
                    # Scale path dimensions
                    scaled_width = path_bounds.width() * layout_scale
                    scaled_height = path_bounds.height() * layout_scale
                    
                    # Set reasonable button size limits
                    min_size = 25
                    max_size = 200
                    
                    new_button.width = max(min_size, min(max_size, scaled_width))
                    new_button.height = max(min_size, min(max_size, scaled_height))
                    
                    # Apply SVG styling
                    self._apply_svg_styling(new_button, path_info['element'])
                    
                    # Add to canvas
                    self.add_button(new_button)
                    created_buttons.append(new_button)
                    
                    # Prepare database entry
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
                        "script_data": new_button.script_data,
                        "shape_type": new_button.shape_type,
                        "svg_path_data": new_button.svg_path_data,
                        "svg_file_path": new_button.svg_file_path
                    }
                    new_buttons_data.append(button_data_for_db)
                
                # Batch database update
                if new_buttons_data:
                    tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                    tab_data['buttons'].extend(new_buttons_data)
                    DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                    DM.PickerDataManager.save_data(DM.PickerDataManager.get_data(), force_immediate=True)
                
                # Select all created buttons
                if created_buttons:
                    self.clear_selection()
                    for button in created_buttons:
                        button.toggle_selection()
                    
                    # Update UI
                    self.update_button_positions()
                    self.update()
                    self.update_hud_counts()
                    
                    #print(f"Created {len(created_buttons)} buttons with preserved SVG layout")
                    
        except Exception as e:
            # Show error dialog
            dialog = CD.CustomDialog(self, title="Error", size=(250, 100), info_box=True)
            message_label = QtWidgets.QLabel(f"Error processing SVG file: {str(e)}")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            dialog.exec_()

    def _create_combined_button_from_svg(self, svg_file_path, drop_position):
        """Create a single button with combined SVG paths"""
        import xml.etree.ElementTree as ET
        
        try:
            # Parse the SVG file
            tree = ET.parse(svg_file_path)
            root = tree.getroot()
            
            # Find all path elements
            path_elements = root.findall('.//{http://www.w3.org/2000/svg}path')
            if not path_elements:
                path_elements = root.findall('.//path')
            
            if not path_elements:
                self._show_no_paths_dialog()
                return
            
            # Combine all paths into one
            combined_path_data = ""
            for path_element in path_elements:
                if 'd' in path_element.attrib:
                    path_data = path_element.attrib['d']
                    if combined_path_data:
                        combined_path_data += " "
                    combined_path_data += path_data
            
            if not combined_path_data:
                self._show_no_paths_dialog()
                return
            
            # Create single button
            main_window = self.window()
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                current_tab = main_window.tab_system.current_tab
                unique_id = main_window.generate_unique_id(current_tab)
                
                # Convert drop position to scene coordinates
                scene_drop_pos = self.canvas_to_scene_coords(drop_position)
                
                # Create button
                new_button = PB.PickerButton('', self, unique_id=unique_id, color="#3096bb")
                new_button.shape_type = 'custom_path'
                new_button.svg_path_data = combined_path_data
                new_button.svg_file_path = svg_file_path
                new_button.scene_position = scene_drop_pos
                
                # Set reasonable size
                new_button.width = 80
                new_button.height = 80
                
                # Apply styling from first path element if available
                if path_elements:
                    self._apply_svg_styling(new_button, path_elements[0])
                
                # Add to canvas
                self.add_button(new_button)
                
                # Update database
                button_data = {
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
                    "script_data": new_button.script_data,
                    "shape_type": new_button.shape_type,
                    "svg_path_data": new_button.svg_path_data,
                    "svg_file_path": new_button.svg_file_path
                }
                
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                tab_data['buttons'].append(button_data)
                DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                DM.PickerDataManager.save_data(DM.PickerDataManager.get_data(), force_immediate=True)
                
                # Select the new button
                self.clear_selection()
                new_button.toggle_selection()
                
                self.update_button_positions()
                self.update()
                self.update_hud_counts()
                
                #print("Created combined SVG button successfully")
                
        except Exception as e:
            self._show_svg_error(str(e))

    def _show_no_paths_dialog(self):
        """Show dialog when no paths are found"""
        dialog = CD.CustomDialog(self, title="No Paths Found", size=(250, 100), info_box=True)
        message_label = QtWidgets.QLabel("The SVG file does not contain any path elements.")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()

    def _show_svg_error(self, error_message):
        """Show SVG processing error dialog"""
        dialog = CD.CustomDialog(self, title="SVG Error", size=(300, 120), info_box=True)
        message_label = QtWidgets.QLabel(f"Error processing SVG file: {error_message}")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()

    def _get_path_bounds_in_svg_coords(self, path_data, path_element):
        """Get path bounds in original SVG coordinate space"""
        try:
            # Create QPainterPath from the SVG path data (using the fixed parser)\

            #picker button
            button = PB.PickerButton("",None)
            path = button._parse_svg_path(path_data)
            if not path:
                return None
            
            # Get bounds in the original coordinate space
            bounds = path.boundingRect()
            
            # Apply any transforms from the path element
            transform = path_element.get('transform')
            if transform:
                bounds = self._apply_simple_transform(bounds, transform)
            
            return bounds
            
        except Exception as e:
            print(f"Error getting path bounds: {e}")
            return None

    def _get_svg_bounds(self, svg_root):
        """Extract SVG viewBox or calculate bounds from width/height with proper coordinate handling"""
        # Try to get viewBox first (most accurate)
        viewbox = svg_root.get('viewBox')
        if viewbox:
            try:
                parts = viewbox.replace(',', ' ').split()
                if len(parts) >= 4:
                    x, y, width, height = map(float, parts[:4])
                    return {'x': x, 'y': y, 'width': width, 'height': height}
            except:
                pass
        
        # Fallback to width/height attributes
        try:
            width_str = svg_root.get('width', '100')
            height_str = svg_root.get('height', '100')
            
            # Remove units (px, pt, mm, etc.)
            width_str = re.sub(r'[^\d.-]', '', width_str)
            height_str = re.sub(r'[^\d.-]', '', height_str)
            
            width = float(width_str) if width_str else 100
            height = float(height_str) if height_str else 100
            
            return {'x': 0, 'y': 0, 'width': width, 'height': height}
        except:
            # Ultimate fallback
            return {'x': 0, 'y': 0, 'width': 100, 'height': 100}
    
    def _get_accurate_path_bounds(self, path_data, path_element):
        """Get accurate path bounds considering transforms and actual visual placement"""
        try:
            # Create QPainterPath from the SVG path data
            path = QtGui.QPainterPath()
            
            # Enhanced SVG path parser
            import re
            
            # Extract coordinates and commands more reliably
            # This regex captures SVG path commands and their parameters
            tokens = re.findall(r'[MmLlHhVvCcSsQqTtAaZz]|[-+]?(?:\d*\.?\d+)(?:[eE][-+]?\d+)?', path_data)
            
            current_pos = QtCore.QPointF(0, 0)
            start_pos = QtCore.QPointF(0, 0)
            
            i = 0
            while i < len(tokens):
                command = tokens[i]
                
                if command.upper() == 'M':  # Move to
                    try:
                        x, y = float(tokens[i+1]), float(tokens[i+2])
                        if command.islower():  # Relative
                            x += current_pos.x()
                            y += current_pos.y()
                        
                        path.moveTo(x, y)
                        current_pos = QtCore.QPointF(x, y)
                        start_pos = QtCore.QPointF(x, y)
                        i += 3
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'L':  # Line to
                    try:
                        x, y = float(tokens[i+1]), float(tokens[i+2])
                        if command.islower():  # Relative
                            x += current_pos.x()
                            y += current_pos.y()
                        
                        path.lineTo(x, y)
                        current_pos = QtCore.QPointF(x, y)
                        i += 3
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'H':  # Horizontal line
                    try:
                        x = float(tokens[i+1])
                        if command.islower():  # Relative
                            x += current_pos.x()
                        
                        path.lineTo(x, current_pos.y())
                        current_pos = QtCore.QPointF(x, current_pos.y())
                        i += 2
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'V':  # Vertical line
                    try:
                        y = float(tokens[i+1])
                        if command.islower():  # Relative
                            y += current_pos.y()
                        
                        path.lineTo(current_pos.x(), y)
                        current_pos = QtCore.QPointF(current_pos.x(), y)
                        i += 2
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'C':  # Cubic Bezier curve
                    try:
                        x1, y1 = float(tokens[i+1]), float(tokens[i+2])
                        x2, y2 = float(tokens[i+3]), float(tokens[i+4])
                        x, y = float(tokens[i+5]), float(tokens[i+6])
                        
                        if command.islower():  # Relative
                            x1 += current_pos.x()
                            y1 += current_pos.y()
                            x2 += current_pos.x()
                            y2 += current_pos.y()
                            x += current_pos.x()
                            y += current_pos.y()
                        
                        path.cubicTo(x1, y1, x2, y2, x, y)
                        current_pos = QtCore.QPointF(x, y)
                        i += 7
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'S':  # Smooth cubic Bezier
                    try:
                        x2, y2 = float(tokens[i+1]), float(tokens[i+2])
                        x, y = float(tokens[i+3]), float(tokens[i+4])
                        
                        if command.islower():  # Relative
                            x2 += current_pos.x()
                            y2 += current_pos.y()
                            x += current_pos.x()
                            y += current_pos.y()
                        
                        # For smooth curves, we approximate with a simple cubic
                        path.cubicTo(current_pos.x(), current_pos.y(), x2, y2, x, y)
                        current_pos = QtCore.QPointF(x, y)
                        i += 5
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'Q':  # Quadratic Bezier curve
                    try:
                        x1, y1 = float(tokens[i+1]), float(tokens[i+2])
                        x, y = float(tokens[i+3]), float(tokens[i+4])
                        
                        if command.islower():  # Relative
                            x1 += current_pos.x()
                            y1 += current_pos.y()
                            x += current_pos.x()
                            y += current_pos.y()
                        
                        path.quadTo(x1, y1, x, y)
                        current_pos = QtCore.QPointF(x, y)
                        i += 5
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'A':  # Arc - simplified approximation
                    try:
                        # Arc parameters: rx ry x-axis-rotation large-arc-flag sweep-flag x y
                        rx, ry = float(tokens[i+1]), float(tokens[i+2])
                        x_axis_rotation = float(tokens[i+3])
                        large_arc_flag = int(float(tokens[i+4]))
                        sweep_flag = int(float(tokens[i+5]))
                        x, y = float(tokens[i+6]), float(tokens[i+7])
                        
                        if command.islower():  # Relative
                            x += current_pos.x()
                            y += current_pos.y()
                        
                        # Simplified: just draw a line for now (arcs are complex)
                        path.lineTo(x, y)
                        current_pos = QtCore.QPointF(x, y)
                        i += 8
                    except (IndexError, ValueError):
                        i += 1
                        
                elif command.upper() == 'Z':  # Close path
                    path.lineTo(start_pos.x(), start_pos.y())
                    current_pos = start_pos
                    i += 1
                    
                else:
                    # Skip unknown commands
                    i += 1
            
            bounds = path.boundingRect()
            
            # Check for any transform attribute on the path element
            transform = path_element.get('transform')
            if transform:
                # Apply basic transform parsing (simplified)
                bounds = self._apply_simple_transform(bounds, transform)
            
            return bounds
            
        except Exception as e:
            print(f"Error in accurate path bounds calculation: {e}")
            return None

    def _apply_simple_transform(self, rect, transform_string):
        """Apply basic SVG transforms to bounding rect"""
        try:
            import re
            
            # Handle translate transform
            translate_match = re.search(r'translate\(\s*([-+]?\d*\.?\d+)(?:\s*,\s*([-+]?\d*\.?\d+))?\s*\)', transform_string)
            if translate_match:
                tx = float(translate_match.group(1))
                ty = float(translate_match.group(2)) if translate_match.group(2) else 0
                rect = QtCore.QRectF(rect.x() + tx, rect.y() + ty, rect.width(), rect.height())
            
            # Handle scale transform
            scale_match = re.search(r'scale\(\s*([-+]?\d*\.?\d+)(?:\s*,\s*([-+]?\d*\.?\d+))?\s*\)', transform_string)
            if scale_match:
                sx = float(scale_match.group(1))
                sy = float(scale_match.group(2)) if scale_match.group(2) else sx
                rect = QtCore.QRectF(rect.x() * sx, rect.y() * sy, rect.width() * sx, rect.height() * sy)
            
            return rect
            
        except Exception as e:
            print(f"Error applying transform: {e}")
            return rect
    
    def _generate_svg_unique_id(self, tab_name, existing_ids, path_index):
        """Generate a unique ID specifically for SVG-created buttons"""
        # Try different naming strategies until we find a unique ID
        
        # Strategy 1: Use SVG filename + path index
        import os
        svg_filename = os.path.splitext(os.path.basename(getattr(self, '_current_svg_path', 'svg')))[0]
        
        base_patterns = [
            f"{tab_name}_{svg_filename}_path_{path_index+1:03d}",
            f"{tab_name}_svg_path_{path_index+1:03d}",
            f"{tab_name}_shape_{path_index+1:03d}",
            f"{tab_name}_button_{len(existing_ids)+path_index+1:03d}"
        ]
        
        for base_pattern in base_patterns:
            if base_pattern not in existing_ids:
                return base_pattern
            
            # If base pattern exists, try with incremental suffix
            counter = 1
            while counter < 1000:  # Safety limit
                candidate_id = f"{base_pattern}_{counter:03d}"
                if candidate_id not in existing_ids:
                    return candidate_id
                counter += 1
        
        # Fallback: use timestamp-based ID (should never reach this)
        import time
        timestamp_id = f"{tab_name}_svg_{int(time.time() * 1000)}_{path_index}"
        return timestamp_id

    def _apply_svg_styling(self, button, path_element):
        """Apply SVG styling to the button"""
        # Extract fill color
        fill = path_element.get('fill')
        if fill and fill != 'none' and not fill.startswith('url('):
            try:
                # Convert SVG color to hex
                if fill.startswith('#'):
                    button.color = fill
                elif fill.startswith('rgb'):
                    # Basic RGB parsing - you might want to enhance this
                    import re
                    rgb_match = re.search(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', fill)
                    if rgb_match:
                        r, g, b = map(int, rgb_match.groups())
                        button.color = f"#{r:02x}{g:02x}{b:02x}"
            except:
                pass  # Keep default color
        
        # Extract opacity
        opacity = path_element.get('opacity')
        if opacity:
            try:
                button.opacity = float(opacity)
            except:
                pass
        
        # You can add more styling extraction here (stroke, etc.)
    
    def _show_svg_import_dialog(self):
        """Show dialog to choose between separate buttons or combined import"""
        dialog = CD.CustomDialog(self, title="SVG Import Options", size=(300, 150))
        
        # Create main layout
        main_layout = QtWidgets.QVBoxLayout()
        
        # Info label
        info_label = QtWidgets.QLabel("How would you like to import the SVG paths?")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        main_layout.addWidget(info_label)
        
        # Radio buttons for import options
        radio_layout = QtWidgets.QVBoxLayout()
        
        self.separate_radio = CB.CustomRadioButton("Separate buttons", group=True)
        self.separate_radio.setToolTip("Each SVG path is imported as a separate picker button")
        
        self.combined_radio = CB.CustomRadioButton("Combined button", group=True)
        self.combined_radio.setToolTip("All SVG paths are merged into one picker button")
        
        self.separate_radio.group('import_option')
        self.combined_radio.group('import_option')
        
        radio_layout.addWidget(self.separate_radio)
        radio_layout.addWidget(self.combined_radio)
        main_layout.addLayout(radio_layout)
        
        dialog.add_layout(main_layout)
        
        dialog.add_button_box()

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            if self.separate_radio.isChecked():
                return {'import': True, 'separate': True}
            else:
                return {'import': True, 'separate': False}
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

            scene_pos = self.get_center_position()  # Use canvas center
            create_button_from_blender_curve_action = menu.addAction(QtGui.QIcon(UT.get_icon('add.png')), "Create Button from Curve")
            create_button_from_blender_curve_action.triggered.connect(lambda: create_buttons_from_blender_curves(self, scene_pos, show_options_dialog=True))
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
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                edit_mode_action.triggered.connect(main_window.toggle_edit_mode)
        else:
            edit_mode_action = menu.addAction(QtGui.QIcon(UT.get_icon('edit.png')),"Edit Picker")
            main_window = self.window()
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                edit_mode_action.triggered.connect(main_window.toggle_edit_mode)
        
        if menu.actions():
            menu.exec_(self.mapToGlobal(position))

    def add_button_at_position(self, position):
        scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(position))
        
        main_window = self.window()
        if isinstance(main_window, UI.BlenderAnimPickerWindow):
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
        """REFACTORED: Simplified paste function that uses horizontal_mirror_button_positions for mirroring"""
        scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(position))
        copied_buttons = PB.ButtonClipboard.instance().get_all_buttons()
        
        if not copied_buttons:
            return
            
        main_window = self.window()
        if isinstance(main_window, UI.BlenderAnimPickerWindow):
            current_tab = main_window.tab_system.current_tab
            new_buttons = []
            
            # CRITICAL FIX: Disable batch mode temporarily for pasting
            # This ensures each button update is processed immediately
            was_batch_active = getattr(main_window, 'batch_update_active', False)
            main_window.batch_update_active = False
            self.setUpdatesEnabled(False)
            
            try:
                # Get tab data once at the beginning
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                
                for button_data in copied_buttons:
                    unique_id = main_window.generate_unique_id(current_tab)
                    new_button = PB.PickerButton(button_data['label'], self, unique_id=unique_id)
                    
                    # Apply all copied attributes including functionality
                    new_button.color = button_data['color']
                    new_button.opacity = button_data['opacity']
                    new_button.selectable = button_data['selectable']
                    new_button.width = button_data['width']
                    new_button.height = button_data['height']
                    new_button.radius = button_data['radius'].copy()
                    new_button.mode = button_data.get('mode', 'select')
                    new_button.script_data = button_data.get('script_data', {}).copy()
                    new_button.shape_type = button_data.get('shape_type', 'rect')
                    new_button.svg_path_data = button_data.get('svg_path_data', '')
                    new_button.svg_file_path = button_data.get('svg_file_path', '')
                    
                    # Always use original assigned objects - counterpart mirroring handled in horizontal_mirror_button_positions
                    new_button.assigned_objects = button_data['assigned_objects'].copy()
                    
                    # Apply pose-specific data if this is a pose button
                    if new_button.mode == 'pose':
                        # Copy thumbnail path if available
                        if 'thumbnail_path' in button_data:
                            new_button.thumbnail_path = button_data['thumbnail_path']
                            
                            # If the thumbnail path exists, load the pixmap
                            if new_button.thumbnail_path and os.path.exists(new_button.thumbnail_path):
                                new_button.thumbnail_pixmap = QtGui.QPixmap(new_button.thumbnail_path)
                        
                        # Copy pose data if available
                        if 'pose_data' in button_data:
                            new_button.pose_data = button_data['pose_data'].copy()
                    
                    # Position relative to cursor point (position mirroring handled separately)
                    relative_position = button_data['relative_position']
                    new_button.scene_position = scene_pos + relative_position
                    
                    # Add button to canvas
                    self.add_button(new_button)
                    new_buttons.append(new_button)
                    
                    # CRITICAL FIX: Create complete button data for database immediately
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
                        "script_data": new_button.script_data,
                        "shape_type": new_button.shape_type,
                        "svg_path_data": new_button.svg_path_data,
                        "svg_file_path": new_button.svg_file_path
                    }
                    
                    # Add pose-specific data to database if this is a pose button
                    if new_button.mode == 'pose':
                        # Add thumbnail path if available
                        if hasattr(new_button, 'thumbnail_path'):
                            button_data_for_db["thumbnail_path"] = new_button.thumbnail_path
                        
                        # Add pose data if available
                        if hasattr(new_button, 'pose_data') and new_button.pose_data:
                            button_data_for_db["pose_data"] = new_button.pose_data
                    
                    # CRITICAL FIX: Add to tab_data immediately
                    tab_data['buttons'].append(button_data_for_db)
                
                # Save the initial button state to database
                DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                
                # Select all newly pasted buttons BEFORE mirroring
                if new_buttons:
                    # Clear current selection
                    self.clear_selection()
                    
                    # Select all new buttons
                    for button in new_buttons:
                        button.toggle_selection()
                    
                    #print(f"Selected {len(new_buttons)} newly pasted buttons")
                
                # Apply position/SVG/counterpart mirroring if requested using existing function
                if mirror and new_buttons:
                    #print("Applying position, SVG, and counterpart mirroring using horizontal_mirror_button_positions...")
                    # Use existing horizontal mirror function with counterpart mirroring enabled
                    self.horizontal_mirror_button_positions(apply_counterparts=True)
                    # Note: horizontal_mirror_button_positions handles its own database updates
                
                action_word = "Mirror pasted" if mirror else "Pasted"
                #print(f"{action_word} {len(new_buttons)} buttons - All saved to database")
            
            finally:
                # Restore batch mode state
                main_window.batch_update_active = was_batch_active
                
                # Re-enable canvas updates
                self.setUpdatesEnabled(True)
                self.update_button_positions()
                self.update()
            
            # Force a final database flush to ensure everything is saved
            if hasattr(main_window, '_flush_pending_updates'):
                main_window._flush_pending_updates()

            # Force immediate main window update
            if hasattr(main_window, 'update_buttons_for_current_tab'):
                main_window.update_buttons_for_current_tab(force_update=True)

    def horizontal_mirror_button_positions(self, apply_counterparts=False):
        """Mirror button positions horizontally with optional counterpart object assignment"""
        selected_buttons = self.get_selected_buttons()
        if not selected_buttons:
            return
        
        main_window = self.window()
        if not isinstance(main_window, UI.BlenderAnimPickerWindow):
            return
        
        # CRITICAL FIX: Disable batch updates to ensure immediate processing
        was_batch_active = getattr(main_window, 'batch_update_active', False)
        main_window.batch_update_active = False
        self.setUpdatesEnabled(False)
        
        try:
            # Get the center of the selected buttons
            min_x = min(button.scene_position.x() for button in selected_buttons)
            max_x = max(button.scene_position.x() for button in selected_buttons)
            center_x = (min_x + max_x) / 2
            
            # Get current tab data for batch database update
            current_tab = main_window.tab_system.current_tab
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            
            # Get namespace and naming conventions for counterpart resolution if needed
            if apply_counterparts:
                current_namespace = self._get_current_namespace()
                naming_conventions = self._get_naming_conventions("", "")
            
            # Track which buttons were updated for database batch update
            updated_button_data = []
            
            # Mirror positions around the center
            for button in selected_buttons:
                # Mirror position
                button.scene_position.setX(center_x - (button.scene_position.x() - center_x))
                
                # Mirror SVG path if applicable
                if button.shape_type == 'custom_path' and button.svg_path_data:
                    button.svg_path_data = button.mirror_svg_path_horizontal(button.svg_path_data, button.width)
                    button._invalidate_mask_cache()
                
                # Apply counterpart mirroring to assigned objects if requested
                if apply_counterparts and button.assigned_objects:
                    mirrored_assigned_objects = []
                    
                    for obj_data in button.assigned_objects:
                        try:
                            if obj_data.get('is_bone', False):
                                # Handle bone mirroring
                                bone_name = obj_data.get('name', '')
                                original_armature_name = obj_data.get('armature', '')
                                
                                # Find the mirrored bone name
                                mirrored_bone_name, is_center_bone = self._find_mirrored_name(bone_name, naming_conventions)
                                
                                # Create counterpart bone data
                                mirrored_obj_data = {
                                    'name': mirrored_bone_name,
                                    'armature': original_armature_name,
                                    'is_bone': True
                                }
                                
                                # Verify the counterpart bone exists
                                counterpart_bone = self._resolve_bone_with_namespace(mirrored_obj_data, current_namespace)
                                if counterpart_bone:
                                    mirrored_assigned_objects.append(mirrored_obj_data)
                                    #print(f"Mirrored bone: {bone_name} -> {mirrored_bone_name}")
                                else:
                                    # If counterpart doesn't exist, keep original
                                    mirrored_assigned_objects.append(obj_data.copy())
                                    print(f"Counterpart bone not found for {bone_name}, keeping original")
                            else:
                                # Handle object mirroring
                                obj_name = obj_data.get('name', '')
                                
                                # Find the mirrored object name
                                mirrored_obj_name, is_center_object = self._find_mirrored_name(obj_name, naming_conventions)
                                
                                # Create counterpart object data
                                mirrored_obj_data = {
                                    'name': mirrored_obj_name,
                                    'is_bone': False
                                }
                                
                                # Verify the counterpart object exists
                                counterpart_object = self._resolve_object(mirrored_obj_data, current_namespace)
                                if counterpart_object:
                                    mirrored_assigned_objects.append(mirrored_obj_data)
                                    #print(f"Mirrored object: {obj_name} -> {mirrored_obj_name}")
                                else:
                                    # If counterpart doesn't exist, keep original
                                    mirrored_assigned_objects.append(obj_data.copy())
                                    print(f"Counterpart object not found for {obj_name}, keeping original")
                                    
                        except Exception as e:
                            print(f"Error mirroring assigned object {obj_data}: {e}")
                            # If there's an error, keep the original object
                            mirrored_assigned_objects.append(obj_data.copy())
                    
                    # Update button's assigned objects
                    button.assigned_objects = mirrored_assigned_objects
                
                # Force immediate visual update
                button.update()
                
                # Prepare button data for database update
                button_data = {
                    "id": button.unique_id,
                    "selectable": button.selectable,
                    "label": button.label,
                    "color": button.color,
                    "opacity": button.opacity,
                    "position": (button.scene_position.x(), button.scene_position.y()),
                    "width": button.width,
                    "height": button.height,
                    "radius": button.radius,
                    "assigned_objects": getattr(button, 'assigned_objects', []),
                    "mode": getattr(button, 'mode', 'select'),
                    "script_data": getattr(button, 'script_data', {'code': '', 'type': 'python'}),
                    "pose_data": getattr(button, 'pose_data', {}),
                    "thumbnail_path": getattr(button, 'thumbnail_path', ''),
                    "shape_type": button.shape_type,
                    "svg_path_data": button.svg_path_data,  # This includes the mirrored path
                    "svg_file_path": button.svg_file_path
                }
                updated_button_data.append(button_data)
                
                counterpart_info = " with counterparts" if apply_counterparts else ""
                #print(f"Mirrored button {button.unique_id}: position={button.scene_position.x():.2f}, svg_updated={bool(button.svg_path_data)}{counterpart_info}")
            
            # CRITICAL FIX: Batch update the database with ALL mirrored buttons at once
            for button_data in updated_button_data:
                # Find and update the existing button data in the tab
                for i, existing_button in enumerate(tab_data['buttons']):
                    if existing_button['id'] == button_data['id']:
                        tab_data['buttons'][i] = button_data
                        break
                else:
                    # If not found (shouldn't happen), add it
                    tab_data['buttons'].append(button_data)
            
            # Single database update for all buttons
            DM.PickerDataManager.update_tab_data(current_tab, tab_data)
            
            action_type = "with counterpart assignment" if apply_counterparts else "position/SVG only"
            #print(f"Horizontally mirrored {len(selected_buttons)} buttons ({action_type}) - All changes saved to database in batch")
            
        finally:
            # Restore previous batch mode state
            main_window.batch_update_active = was_batch_active
            
            # Re-enable canvas updates
            self.setUpdatesEnabled(True)
            self.update_button_positions()
            self.update()
        
        # Force a final database flush to ensure everything is saved
        if hasattr(main_window, '_flush_pending_updates'):
            main_window._flush_pending_updates()

        if hasattr(main_window, 'update_buttons_for_current_tab'):
            main_window.update_buttons_for_current_tab(force_update=True)

    def vertical_mirror_button_positions(self):
        selected_buttons = self.get_selected_buttons()
        if not selected_buttons:
            return
        
        main_window = self.window()
        if not isinstance(main_window, UI.BlenderAnimPickerWindow):
            return
        
        # CRITICAL FIX: Disable batch updates to ensure immediate processing
        was_batch_active = getattr(main_window, 'batch_update_active', False)
        main_window.batch_update_active = False
        self.setUpdatesEnabled(False)
        
        try:
            # Get the center of the selected buttons
            min_y = min(button.scene_position.y() for button in selected_buttons)
            max_y = max(button.scene_position.y() for button in selected_buttons)
            center_y = (min_y + max_y) / 2
            
            # Get current tab data for batch database update
            current_tab = main_window.tab_system.current_tab
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            
            # Track which buttons were updated for database batch update
            updated_button_data = []
            
            # Mirror positions around the center
            for button in selected_buttons:
                # Mirror position
                button.scene_position.setY(center_y - (button.scene_position.y() - center_y))
                
                # Mirror SVG path if applicable
                if button.shape_type == 'custom_path' and button.svg_path_data:
                    button.svg_path_data = button.mirror_svg_path_vertical(button.svg_path_data, button.height)
                    button._invalidate_mask_cache()
                
                # Force immediate visual update
                button.update()
                
                # Prepare button data for database update
                button_data = {
                    "id": button.unique_id,
                    "selectable": button.selectable,
                    "label": button.label,
                    "color": button.color,
                    "opacity": button.opacity,
                    "position": (button.scene_position.x(), button.scene_position.y()),
                    "width": button.width,
                    "height": button.height,
                    "radius": button.radius,
                    "assigned_objects": getattr(button, 'assigned_objects', []),
                    "mode": getattr(button, 'mode', 'select'),
                    "script_data": getattr(button, 'script_data', {'code': '', 'type': 'python'}),
                    "pose_data": getattr(button, 'pose_data', {}),
                    "thumbnail_path": getattr(button, 'thumbnail_path', ''),
                    "shape_type": button.shape_type,
                    "svg_path_data": button.svg_path_data,  # This includes the mirrored path
                    "svg_file_path": button.svg_file_path
                }
                updated_button_data.append(button_data)
                
                #print(f"Mirrored button {button.unique_id}: position={button.scene_position.y():.2f}, svg_updated={bool(button.svg_path_data)}")
            
            # CRITICAL FIX: Batch update the database with ALL mirrored buttons at once
            for button_data in updated_button_data:
                # Find and update the existing button data in the tab
                for i, existing_button in enumerate(tab_data['buttons']):
                    if existing_button['id'] == button_data['id']:
                        tab_data['buttons'][i] = button_data
                        break
                else:
                    # If not found (shouldn't happen), add it
                    tab_data['buttons'].append(button_data)
            
            # Single database update for all buttons
            DM.PickerDataManager.update_tab_data(current_tab, tab_data)
            
            #print(f"Vertically mirrored {len(selected_buttons)} buttons - All changes saved to database in batch")
            
        finally:
            # Restore previous batch mode state
            main_window.batch_update_active = was_batch_active
            
            # Re-enable canvas updates
            self.setUpdatesEnabled(True)
            self.update_button_positions()
            self.update()
        
        # Force a final database flush to ensure everything is saved
        if hasattr(main_window, '_flush_pending_updates'):
            main_window._flush_pending_updates()

        if hasattr(main_window, 'update_buttons_for_current_tab'):
            main_window.update_buttons_for_current_tab(force_update=True)

    def cleanup_selection_manager(self):
        if hasattr(self, 'selection_manager'):
            self.selection_manager.close()
            self.selection_manager.deleteLater()
            del self.selection_manager
    #------------------------------------------------------------------------------
    def wheelEvent(self, event):

        # Hide tooltip during zoom
        self._hide_button_tooltip()
        
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
        
        # Update hover after zoom
        QtCore.QTimer.singleShot(100, lambda: self._update_hover_button(self.mapFromGlobal(QtGui.QCursor.pos())))
        
        # Ensure Maya window stays active
        #UT.blender_main_window() 
        
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
        """Enhanced mouse press handler to track last clicked button"""
        # Hide tooltip immediately
        self._hide_button_tooltip()
        
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
        
        # Handle right-click for context menu
        if event.button() == QtCore.Qt.RightButton:
            self.show_context_menu(event.pos())
            event.accept()
            return
        
        # Check HUD interaction
        hud_pos = self.hud.mapFromParent(event.pos())
        if self.hud.button_container.geometry().contains(hud_pos):
            self.hud.toggle_button.click()
            event.accept()
            return
        
        # Handle left mouse button
        if event.button() == QtCore.Qt.LeftButton:
            # Check for Alt+Left click for panning
            alt_pressed = bool(event.modifiers() & QtCore.Qt.AltModifier)
            ctrl_pressed = bool(event.modifiers() & QtCore.Qt.ControlModifier)
            
            # Store initial selection state for rubber band operations
            self.initial_selection_state = {button: button.is_selected for button in self.buttons}
            self.ctrl_held_during_selection = ctrl_pressed
            
            # Find clicked button
            '''clicked_button = None
            for button in self.buttons:
                if button.isVisible() and button.geometry().contains(event.pos()):
                    clicked_button = button
                    break'''
            clicked_button = self._get_button_at_position(event.pos())
            if clicked_button and not alt_pressed:
                # Button was clicked - let button handle its own selection logic
                # Remove canvas interference - let button's mousePressEvent handle everything
                pass
            elif alt_pressed:
                # Alt+Left click for panning
                self.last_pan_pos = event.pos()
                event.accept()
            else:
                # Empty space clicked without Alt
                shift_held = event.modifiers() & QtCore.Qt.ShiftModifier
                
                # Clear last clicked button when clicking empty space
                self.last_clicked_button = None
                
                # Clear selection if shift not held
                if not shift_held:
                    if self.edit_mode:
                        self.clear_selection()
                    else:
                        # Clear Blender selection
                        try:
                            with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                                if bpy.context.mode == 'POSE':
                                    bpy.ops.pose.select_all(action='DESELECT')
                                elif bpy.context.mode == 'OBJECT':
                                    bpy.ops.object.select_all(action='DESELECT')
                        except:
                            pass
                        self.clear_selection()
                
                # Start rubber band selection
                self.rubberband_origin = event.pos()
                self.rubberband.setGeometry(QtCore.QRect(self.rubberband_origin, QtCore.QSize()))
                self.rubberband.show()
                self.is_selecting = True
                self.buttons_in_current_drag.clear()
            
            event.accept()
            
        elif event.button() == QtCore.Qt.MiddleButton:
            self.last_pan_pos = event.pos()
            event.accept()
        else:
            super().mousePressEvent(event)
            self.setFocus()
        
        UT.blender_main_window()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move events"""
        # Update button hover state and tooltip
        self._update_hover_button(event.pos())

        # Check for Alt+Left drag panning
        alt_pressed = bool(event.modifiers() & QtCore.Qt.AltModifier)
        
        if self.is_selecting:
            # Rubber band selection active
            selection_rect = QtCore.QRect(self.rubberband_origin, event.pos()).normalized()
            self.rubberband.setGeometry(selection_rect)
            
            # Check modifier combinations
            shift_pressed = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
            ctrl_pressed = bool(event.modifiers() & QtCore.Qt.ControlModifier)
            
            # Determine selection mode
            if ctrl_pressed and shift_pressed:
                # Ctrl+Shift: Remove from selection
                self.update_visual_selection(selection_rect, add_to_selection=False, remove_from_selection=True)
            elif shift_pressed:
                # Shift only: Add to selection
                self.update_visual_selection(selection_rect, add_to_selection=True, remove_from_selection=False)
            else:
                # No modifiers: Replace selection
                self.update_visual_selection(selection_rect, add_to_selection=False, remove_from_selection=False)
            
            event.accept()
            
        elif ((event.buttons() == QtCore.Qt.LeftButton and alt_pressed) or 
            event.buttons() == QtCore.Qt.MiddleButton) and self.last_pan_pos:
            # Hide tooltip during zoom
            self._hide_button_tooltip()
            
            # Handle panning (Alt+Left drag or Middle mouse drag)
            self.setUpdatesEnabled(False)
            try:
                delta = event.pos() - self.last_pan_pos
                self.update_pan_offset(delta)
                self.last_pan_pos = event.pos()
                self.update()
                self.update_button_positions()
            finally:
                self.setUpdatesEnabled(True)
            event.accept()
        else:
            any_button_dragging = any(getattr(btn, 'dragging', False) for btn in self.buttons)
            if any_button_dragging:
                # Update transform guides during button drag
                if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
                    QtCore.QTimer.singleShot(1, self._update_transform_guides_position)
            super().mouseMoveEvent(event)
        event.accept()

    def leaveEvent(self, event):
        """Handle mouse leaving the canvas"""
        self._hide_button_tooltip()
        if self._current_hover_button:
            self._current_hover_button.is_hovered = False
            self._current_hover_button.update()
            self._current_hover_button = None
        super().leaveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Enhanced mouse release handler to properly handle last selected button"""
        
        if event.button() == QtCore.Qt.LeftButton and self.is_selecting:
            # End rubber band selection
            self.is_selecting = False
            self.rubberband.hide()
            
            # For rubber band selection, determine the "last selected" based on mouse position
            if self.buttons_in_current_drag:
                # Find the button closest to the final mouse position among selected buttons
                mouse_scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(event.pos()))
                closest_button = None
                min_distance = float('inf')
                
                for button in self.buttons_in_current_drag:
                    if button.is_selected:
                        distance = ((button.scene_position.x() - mouse_scene_pos.x()) ** 2 + 
                                (button.scene_position.y() - mouse_scene_pos.y()) ** 2) ** 0.5
                        if distance < min_distance:
                            min_distance = distance
                            closest_button = button
                
                if closest_button:
                    self.last_clicked_button = closest_button
            
            # Check modifier combinations for apply_final_selection
            shift_pressed = bool(event.modifiers() & QtCore.Qt.ShiftModifier)
            ctrl_pressed = bool(event.modifiers() & QtCore.Qt.ControlModifier)
            ctrl_held = getattr(self, 'ctrl_held_during_selection', False)
            
            # For counterpart selection, we only want ctrl without shift
            counterpart_mode = ctrl_held and not shift_pressed
            
            # Apply final selection from rubber band
            self.apply_final_selection(shift_pressed, counterpart_mode)
            
            # Ensure final selection state is properly set and signals are emitted
            final_selection_changed = False
            for button in self.buttons:
                old_selected = button.is_selected
                
                # Finalize selection state based on current drag
                if button in self.buttons_in_current_drag:
                    if shift_pressed and not ctrl_pressed:
                        # Shift only: Add to selection
                        button.is_selected = True
                    elif ctrl_pressed and shift_pressed:
                        # Ctrl+Shift: Remove from selection
                        button.is_selected = False
                    elif not shift_pressed and not ctrl_pressed:
                        # No modifiers: Replace selection
                        button.is_selected = True
                    # Note: ctrl_only case is handled in apply_final_selection for counterparts
                elif not shift_pressed:
                    # Clear non-dragged buttons if shift not held
                    button.is_selected = False
                # If shift held, preserve existing selection for non-dragged buttons
                
                # Check if state changed and emit signal
                if old_selected != button.is_selected:
                    final_selection_changed = True
                    button.selected.emit(button, button.is_selected)
                
                button.update()
            
            # Update last selected button for edit widgets
            if self.buttons_in_current_drag:
                # Use the stored last_clicked_button if available
                if hasattr(self, 'last_clicked_button') and self.last_clicked_button and self.last_clicked_button.is_selected:
                    self.last_selected_button = self.last_clicked_button
                else:
                    # Fallback: Set the last button in the drag as the reference for edit widgets
                    last_selected = None
                    for button in reversed(list(self.buttons_in_current_drag)):
                        if button.is_selected:
                            last_selected = button
                            break
                    if last_selected:
                        self.last_selected_button = last_selected
            
            # Important: Clear the drag tracking after rubber band selection
            self.buttons_in_current_drag.clear()
            self.initial_selection_state.clear()
            
            # Invalidate cache and emit signals
            if hasattr(self, '_cache_valid'):
                self._cache_valid = False
            
            if final_selection_changed:
                self.button_selection_changed.emit()
                self.update_hud_counts()
        
        # CRITICAL FIX: Handle button dragging completion
        elif event.button() == QtCore.Qt.LeftButton:
            # Check if any buttons were being dragged
            dragged_buttons = [btn for btn in self.buttons if getattr(btn, 'dragging', False)]
            
            if dragged_buttons:
                # CRITICAL FIX: Force immediate position updates for all dragged buttons
                main_window = self.window()
                if isinstance(main_window, UI.BlenderAnimPickerWindow):
                    # Temporarily disable batch mode to ensure immediate updates
                    was_batch_active = getattr(main_window, 'batch_update_active', False)
                    main_window.batch_update_active = False
                    
                    try:
                        # Update each dragged button's data immediately
                        for button in dragged_buttons:
                            # Force immediate database update for position changes
                            main_window._process_single_button_update(button)
                            #print(f"Canvas: Updated position for button {button.unique_id}: {button.scene_position.x()}, {button.scene_position.y()}")
                        
                        # Also update the buttons for the current tab
                        main_window.update_buttons_for_current_tab(force_update=True)
                        
                        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
                            QtCore.QTimer.singleShot(10, self._update_transform_guides_position)
                        
                    finally:
                        # Restore batch mode state
                        main_window.batch_update_active = was_batch_active
            
            # Reset pan position for Alt+Left drag
            self.last_pan_pos = None
            
        elif event.button() == QtCore.Qt.MiddleButton:
            self.last_pan_pos = None
        else:
            super().mouseReleaseEvent(event)
        
        # Always emit clicked signal
        self.clicked.emit()
        UT.blender_main_window()
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_button_positions()
        self.hud.setGeometry(self.rect())
        self.hud.raise_()
        
        # Update transform guides position
        if hasattr(self, 'transform_guides') and self.transform_guides.isVisible():
            self.transform_guides.update_position()
            
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

    def cleanup(self):
        """Clean up resources when canvas is destroyed"""
        self._hide_button_tooltip()
        if self._tooltip_widget:
            self._tooltip_widget.deleteLater()
            self._tooltip_widget = None
        
        # Clean up other resources...
        if hasattr(self, 'transform_guides'):
            self.transform_guides.deleteLater()
        
        if hasattr(self, 'hud'):
            self.hud.deleteLater()
            