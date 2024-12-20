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
import maya.cmds as cmds
from . import ui as UI
from . import utils as UT
from . import picker_button as PB
from . import custom_button as CB
from . import tool_functions as TF
from . import data_management as DM

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

        self.show_axes = True
        # Background properties
        self.background_color = QtGui.QColor(50, 50, 50, 255)
        self.dot_color = QtGui.QColor(40, 40, 40, 255)
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
    #------------------------------------------------------------------------------
    def set_edit_mode(self, enabled):
        self.edit_mode = enabled
        self.border_color = self.edit_mode_border_color if enabled else self.default_border_color
        self.border_width = 1 if enabled else 1
        for button in self.buttons:
            button.edit_mode = enabled
            button.update_cursor()
        self.update()
    
    def set_minimal_mode(self, enabled):
        """Set minimal mode state"""
        self.minimal_mode = enabled
        # Hide/show the HUD based on minimal mode
        self.hud.setVisible(not enabled)
        self.update()  # Trigger repaint
    #------------------------------------------------------------------------------
    def select_buttons_in_rect(self, rect, add_to_selection=False):
        # If not adding to selection and not in shift mode, clear existing selection
        if not add_to_selection:
            self.clear_selection()

        selection_changed = False
        for button in self.buttons:
            button_rect = button.geometry()
            if rect.intersects(button_rect):
                if not button.is_selected:
                    button.set_selected(True)
                    selection_changed = True

        if selection_changed:
            self.button_selection_changed.emit()
            self.update_hud_counts()

    def update_visual_selection(self, rect, add_to_selection=False):
        """Update button selection visually during drag"""
        # Get buttons in current rectangle
        current_buttons = set()
        
        # Convert the selection rect to actual scene coordinates
        rect_center = rect.center()
        rect_top_left = self.canvas_to_scene_coords(QtCore.QPointF(rect.left(), rect.top()))
        rect_bottom_right = self.canvas_to_scene_coords(QtCore.QPointF(rect.right(), rect.bottom()))
        
        # Create a transformed selection rect in scene coordinates
        scene_rect = QtCore.QRectF(
            rect_top_left,
            rect_bottom_right
        ).normalized()
        
        # Check intersection in scene coordinates
        for button in self.buttons:
            # Get button rect in scene coordinates
            button_pos = button.scene_position
            button_width = button.width
            button_height = button.height
            button_rect = QtCore.QRectF(
                button_pos.x() - button_width/2,
                button_pos.y() - button_height/2,
                button_width,
                button_height
            )
            
            # Check intersection in scene coordinates
            if scene_rect.intersects(button_rect):
                current_buttons.add(button)
                
        # Reset visual selection for buttons no longer in rectangle
        for button in self.buttons_in_current_drag - current_buttons:
            if button in self.initial_selection_state:
                button.is_selected = self.initial_selection_state[button]
                button.update()
        
        # Update selection for buttons in rectangle
        for button in current_buttons:
            if add_to_selection:
                # If shift is held, toggle from initial state
                initial_state = self.initial_selection_state.get(button, False)
                button.is_selected = not initial_state
            else:
                button.is_selected = True
            button.update()
        
        self.buttons_in_current_drag = current_buttons
        self.update_hud_counts()

    def apply_final_selection(self, add_to_selection=False):
        """Apply final selection and trigger Maya selection updates"""
        if not self.edit_mode:
            # When not in edit mode, handle Maya selection
            maya_sel = set()
            missing_objects = set()
            
            # First collect what would be selected
            final_selections = set()
            for button in self.buttons:
                if button in self.buttons_in_current_drag:
                    if button.is_selected:
                        final_selections.add(button)
                elif add_to_selection and button.is_selected:
                    final_selections.add(button)

            # Store current Maya selection
            current_maya_selection = set(cmds.ls(selection=True) or [])
            
            # Collect objects that would be selected
            new_maya_selection = set()
            for button in final_selections:
                if button.assigned_objects:
                    main_window = self.window()
                    if isinstance(main_window, UI.AnimPickerWindow):
                        current_namespace = main_window.namespace_dropdown.currentText()
                        if current_namespace and current_namespace != 'None':
                            namespaced_objects = [f"{current_namespace}:{obj}" for obj in button.assigned_objects]
                        else:
                            namespaced_objects = button.assigned_objects
                            
                        for obj in namespaced_objects:
                            if cmds.objExists(obj):
                                new_maya_selection.add(obj)
                            else:
                                nice_name = '- ' + obj.split('|')[-1].split(':')[-1]
                                missing_objects.add(nice_name)

            # Only perform Maya selection if there's an actual change
            if new_maya_selection != current_maya_selection:
                cmds.undoInfo(openChunk=True)
                try:
                    if not add_to_selection:
                        cmds.select(clear=True)
                    if new_maya_selection:
                        cmds.select(list(new_maya_selection), add=True)
                finally:
                    cmds.undoInfo(closeChunk=True)

            # Show dialog if there are missing objects
            if missing_objects:
                missing_list = '\n'.join(sorted(missing_objects))
                message = f"The following objects were not found:\n{missing_list}\n \n [Try reconnecting the object(s) or check the namespace]"
                cmds.confirmDialog(title="Missing Objects", message=message, button=['OK'], 
                                defaultButton='OK', dismissString='OK', icon='warning')
                        
            # Update button visual states
            for button in self.buttons:
                button.update()
        
        self.button_selection_changed.emit()
        self.update_hud_counts()

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

    def get_selected_buttons(self):
        """Get list of currently selected buttons"""
        return [button for button in self.buttons if button.is_selected]
    
    def on_button_selected(self, button, is_selected):
        if not is_selected:
            button.set_selected(False)
        self.button_selection_changed.emit()
        self.update()
        self.update_hud_counts()
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

    def remove_button(self, button):
        if button in self.buttons:
            self.buttons.remove(button)
            self.update_button_positions()
            main_window = self.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                main_window.update_button_data(button, deleted=True)
            
            # Update HUD button count
            self.update_hud_counts()

    def update_button_positions(self):
        visible_rect = self.rect()
        for button in self.buttons:
            canvas_pos = self.scene_to_canvas_coords(button.scene_position)
            if visible_rect.contains(canvas_pos.toPoint()):
                button_width = button.width * self.zoom_factor
                button_height = button.height * self.zoom_factor
                x = canvas_pos.x() - button_width / 2
                y = canvas_pos.y() - button_height / 2
                button.setGeometry(int(x), int(y), int(button_width), int(button_height))
                button.show()
            else:
                button.hide()

    def update_button_data(self, button, deleted=False):
        main_window = self.window()
        if isinstance(main_window, UI.AnimPickerWindow):
            main_window.update_button_data(button, deleted)

    def on_button_changed(self, button):
        self.update_button_data(button)
    
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
        texture_size = self.dot_spacing
        texture = QtGui.QImage(texture_size, texture_size, QtGui.QImage.Format_ARGB32)
        texture.fill(QtCore.Qt.transparent)
        
        painter = QtGui.QPainter(texture)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(self.dot_color)
        painter.drawEllipse(
            texture_size // 2 - self.dot_size // 2, 
            texture_size // 2 - self.dot_size // 2, 
            self.dot_size, 
            self.dot_size
        )
        painter.end()
        
        self.dot_texture = QtGui.QBrush(QtGui.QPixmap.fromImage(texture))
    
    def set_show_axes(self, show):
        """Set whether to show the axes lines"""
        self.show_axes = show
        self.update()

    def set_background_image(self, image_path):
        self.background_image = QtGui.QImage(image_path)
        if self.background_image.isNull():
            self.background_image = None
        else:
            self.focus_canvas()  
        self.update()

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
                    background-color: #2c4759;
                }''')
        
        menu = self.context_menu
        menu.clear()
        
        if self.edit_mode:
            add_button_action = menu.addAction(QtGui.QIcon(":/addClip.png"), "Add Button")
            add_button_action.triggered.connect(lambda: self.add_button_at_position(position))
            
            paste_buttons_action = menu.addAction(QtGui.QIcon(":/pasteUV.png"), "Paste Button")
            paste_buttons_action.triggered.connect(lambda: self.paste_buttons_at_position(position))
            paste_buttons_action.setEnabled(bool(PB.ButtonClipboard.instance().get_all_buttons()))
        
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

    def paste_buttons_at_position(self, position):
        scene_pos = self.canvas_to_scene_coords(QtCore.QPointF(position))
        copied_buttons = PB.ButtonClipboard.instance().get_all_buttons()
        
        if not copied_buttons:
            return
            
        main_window = self.window()
        if isinstance(main_window, UI.AnimPickerWindow):
            current_tab = main_window.tab_system.current_tab
            new_buttons = []
            
            for button_data in copied_buttons:
                unique_id = main_window.generate_unique_id(current_tab)
                new_button = PB.PickerButton(button_data['label'], self, unique_id=unique_id)
                
                # Apply copied attributes
                new_button.color = button_data['color']
                new_button.opacity = button_data['opacity']
                new_button.width = button_data['width']
                new_button.height = button_data['height']
                new_button.radius = button_data['radius'].copy()
                
                # Position relative to cursor point
                new_button.scene_position = scene_pos + button_data['relative_position']
                
                # Add button to canvas
                self.add_button(new_button)
                new_buttons.append(new_button)
                
                # Update database
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
    
    def cleanup_selection_manager(self):
        if hasattr(self, 'selection_manager'):
            self.selection_manager.close()
            self.selection_manager.deleteLater()
            del self.selection_manager
    #------------------------------------------------------------------------------
    def wheelEvent(self, event):
        zoom_factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
        
        # Get mouse position in scene coordinates before zoom
        mouse_pos = QtCore.QPointF(event.position().x(), event.position().y())
        old_scene_pos = self.canvas_to_scene_coords(mouse_pos)

        # Apply zoom
        self.zoom_factor *= zoom_factor

        # Get new scene position and adjust pan to maintain mouse position
        new_scene_pos = self.canvas_to_scene_coords(mouse_pos)
        self.pan_offset += (new_scene_pos - old_scene_pos) * self.zoom_factor

        self.update()
        self.update_button_positions()
        UT.maya_main_window().activateWindow()

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.focus_canvas()
        super().mouseDoubleClickEvent(event)
        
    def mousePressEvent(self, event):
        # Get the position in the HUD's coordinate system
        hud_pos = self.hud.mapFromParent(event.pos())
        
        # Check if the click is within the toggle button's container
        if self.hud.button_container.geometry().contains(hud_pos):
            # Let the HUD handle the event
            self.hud.toggle_button.click()
            return
        
        # Otherwise, handle the event normally
        if event.button() == QtCore.Qt.LeftButton:
            # Store initial selection state for drag operations
            self.initial_selection_state = {button: button.is_selected for button in self.buttons}
            
            # Find if we clicked directly on a button
            clicked_button = None
            for button in self.buttons:
                if button.geometry().contains(event.pos()):
                    clicked_button = button
                    break
            
            if clicked_button:
                shift_held = event.modifiers() & QtCore.Qt.ShiftModifier
                
                # Clear other selections if shift is not held
                if not shift_held:
                    for button in self.buttons:
                        if button != clicked_button:
                            button.set_selected(False)
                            button.selected.emit(button, False)
                    self.buttons_in_current_drag.clear()
                
                # Toggle selection state if shift is held, otherwise select
                if shift_held:
                    new_state = not clicked_button.is_selected
                    clicked_button.set_selected(new_state)
                    clicked_button.selected.emit(clicked_button, new_state)
                else:
                    clicked_button.set_selected(True)
                    clicked_button.selected.emit(clicked_button, True)
                
                # Add to current drag set if selected
                if clicked_button.is_selected:
                    self.buttons_in_current_drag.add(clicked_button)
                else:
                    self.buttons_in_current_drag.discard(clicked_button)
                
                # If not in edit mode, update Maya selection
                if not self.edit_mode:
                    self.apply_final_selection(shift_held)
                
                # Always emit selection changed and update HUD
                self.button_selection_changed.emit()
                self.update_hud_counts()
                QtCore.QCoreApplication.processEvents()  # Force update
                
            else:
                # Clicked empty space
                if not event.modifiers() & QtCore.Qt.ShiftModifier:
                    if self.edit_mode:
                        self.clear_selection()
                        self.buttons_in_current_drag.clear()
                    else:
                        cmds.select(clear=True)
                        self.clear_selection()
                
                # Start rubber band selection
                self.rubberband_origin = event.pos()
                self.rubberband.setGeometry(QtCore.QRect(self.rubberband_origin, QtCore.QSize()))
                self.rubberband.show()
                self.is_selecting = True
            
            event.accept()
            
        elif event.button() == QtCore.Qt.MiddleButton:
            self.last_pan_pos = event.pos()
        else:
            super().mousePressEvent(event)
            self.setFocus()
        
        UT.maya_main_window().activateWindow()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            selection_rect = QtCore.QRect(self.rubberband_origin, event.pos()).normalized()
            self.rubberband.setGeometry(selection_rect)
            
            # Update visual selection without triggering Maya updates
            self.update_visual_selection(selection_rect, event.modifiers() & QtCore.Qt.ShiftModifier)
            event.accept()
        elif event.buttons() == QtCore.Qt.MiddleButton and self.last_pan_pos:
            delta = event.pos() - self.last_pan_pos
            self.pan_offset += QtCore.QPointF(delta.x(), delta.y())
            self.last_pan_pos = event.pos()
            self.update()
            self.update_button_positions()
        else:
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
            
        elif event.button() == QtCore.Qt.MiddleButton:
            self.last_pan_pos = None
        else:
            super().mouseReleaseEvent(event)
        
        self.button_selection_changed.emit()
        self.clicked.emit()
        UT.maya_main_window().activateWindow()

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