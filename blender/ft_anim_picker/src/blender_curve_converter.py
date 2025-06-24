import bpy
import bmesh
import mathutils
from mathutils import Vector
import math

try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtGui import QColor
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
    from shiboken6 import wrapInstance
except ImportError:
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
        from PySide2.QtGui import QColor
        from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
        from shiboken2 import wrapInstance
    except ImportError:
        # Fallback for Blender's built-in Qt (if available)
        QtWidgets = QtCore = QtGui = None

from .custom_dialog import CustomDialog
from .custom_button import CustomButton, CustomRadioButton

# =============================================================================
# COORDINATE PLANE CONFIGURATION
# =============================================================================

class CoordinatePlaneConfig:
    """
    Centralized configuration for coordinate plane mapping in Blender.
    Uses object's local coordinate axes for 2D projection.
    """
    
    # Available plane configurations using local axes
    PLANES = {
        'XY': {
            'name': 'XY',
            'description': 'Use local X and Y axes',
            'x_axis': 0,  # Local X -> SVG X
            'y_axis': 1,  # Local Y -> SVG Y
            'flip_x': False,
            'flip_y': True,  # Flip Y to match SVG orientation (Y-down)
            'default': True
        },
        'XZ': {
            'name': 'XZ',
            'description': 'Use local X and Z axes',
            'x_axis': 0,  # Local X -> SVG X
            'y_axis': 2,  # Local Z -> SVG Y
            'flip_x': False,
            'flip_y': True,
            'default': False
        },
        'YZ': {
            'name': 'YZ',
            'description': 'Use local Y and Z axes',
            'x_axis': 1,  # Local Y -> SVG X
            'y_axis': 2,  # Local Z -> SVG Y
            'flip_x': False,
            'flip_y': False,
            'default': False
        },
        'XY_FLIPPED': {
            'name': '-XY',
            'description': 'Use local X and Y axes with Y flipped',
            'x_axis': 0,  # Local X -> SVG X
            'y_axis': 1,  # Local Y -> SVG Y
            'flip_x': False,
            'flip_y': False,  # No Y flip (keep local orientation)
            'default': False
        },
        'XZ_FLIPPED': {
            'name': '-XZ',
            'description': 'Use local X and Z axes with Z flipped',
            'x_axis': 0,  # Local X -> SVG X
            'y_axis': 2,  # Local Z -> SVG Y
            'flip_x': False,
            'flip_y': False,  # Flip Z axis
            'default': False
        },
        'YZ_FLIPPED': {
            'name': '-YZ',
            'description': 'Use local Y and Z axes with Z flipped',
            'x_axis': 1,  # Local Y -> SVG X
            'y_axis': 2,  # Local Z -> SVG Y
            'flip_x': False,
            'flip_y': True,  # Flip Z axis
            'default': False
        }
    }
    
    # Current active configuration
    _current_plane = 'XY'
    
    @classmethod
    def set_plane(cls, plane_name):
        """Set the active coordinate plane."""
        if plane_name in cls.PLANES:
            cls._current_plane = plane_name
            print(f"Coordinate plane set to: {cls.PLANES[plane_name]['name']}")
        else:
            available = ', '.join(cls.PLANES.keys())
            print(f"Invalid plane '{plane_name}'. Available planes: {available}")
    
    @classmethod
    def get_current_plane(cls):
        """Get the current coordinate plane configuration."""
        return cls.PLANES[cls._current_plane]
    
    @classmethod
    def get_current_plane_name(cls):
        """Get the current coordinate plane name."""
        return cls._current_plane
    
    @classmethod
    def transform_point(cls, local_point):
        """
        Transform a local 3D point to 2D SVG coordinates using current plane config.
        
        Args:
            local_point: tuple/Vector (x, y, z) in local coordinates
            
        Returns:
            tuple: (x, y) in SVG coordinates
        """
        config = cls.get_current_plane()
        
        # Convert to tuple if it's a Vector
        if hasattr(local_point, 'x'):
            point_tuple = (local_point.x, local_point.y, local_point.z)
        else:
            point_tuple = tuple(local_point)
        
        # Extract the two coordinates for the current plane
        svg_x = point_tuple[config['x_axis']]
        svg_y = point_tuple[config['y_axis']]
        
        # Apply flipping if needed
        if config['flip_x']:
            svg_x = -svg_x
        if config['flip_y']:
            svg_y = -svg_y
            
        return (svg_x, svg_y)
    
    @classmethod
    def get_bounds_for_plane(cls, bounds_3d):
        """
        Extract 2D bounds from 3D bounds based on current plane configuration.
        
        Args:
            bounds_3d: dict with min_x, max_x, min_y, max_y, min_z, max_z
            
        Returns:
            dict: 2D bounds with min_x, max_x, min_y, max_y, width, height
        """
        config = cls.get_current_plane()
        
        # Map axes
        x_keys = ['min_x', 'max_x'] if config['x_axis'] == 0 else (['min_y', 'max_y'] if config['x_axis'] == 1 else ['min_z', 'max_z'])
        y_keys = ['min_x', 'max_x'] if config['y_axis'] == 0 else (['min_y', 'max_y'] if config['y_axis'] == 1 else ['min_z', 'max_z'])
        
        min_x = bounds_3d[x_keys[0]]
        max_x = bounds_3d[x_keys[1]]
        min_y = bounds_3d[y_keys[0]]
        max_y = bounds_3d[y_keys[1]]
        
        # Apply flipping to bounds if needed
        if config['flip_x']:
            min_x, max_x = -max_x, -min_x
        if config['flip_y']:
            min_y, max_y = -max_y, -min_y
        
        return {
            'min_x': min_x,
            'max_x': max_x,
            'min_y': min_y,
            'max_y': max_y,
            'width': max_x - min_x,
            'height': max_y - min_y
        }
    
    @classmethod
    def show_plane_selector_dialog(cls, parent=None, show_spline_options=False):
        """Show a dialog to select the coordinate plane and optionally spline separation mode."""
        if not QtWidgets:
            # Fallback for when Qt is not available
            print("Available coordinate planes:")
            for i, (plane_key, plane_config) in enumerate(cls.PLANES.items()):
                marker = " (current)" if plane_key == cls._current_plane else ""
                print(f"  {i+1}. {plane_config['name']}{marker}")
            
            try:
                choice = input("Enter plane number (1-{}): ".format(len(cls.PLANES)))
                plane_keys = list(cls.PLANES.keys())
                selected_key = plane_keys[int(choice) - 1]
                cls.set_plane(selected_key)
                
                separate_splines = True  # Default for fallback
                if show_spline_options:
                    spline_choice = input("Separate splines? (y/n, default=y): ").lower()
                    separate_splines = spline_choice != 'n'
                
                return {'plane': selected_key, 'separate_splines': separate_splines}
            except (ValueError, IndexError):
                print("Invalid choice, keeping current plane.")
                return {'plane': cls._current_plane, 'separate_splines': True}
        
        try:
            from . import custom_dialog as CD
            
            dialog_height = 200 if show_spline_options else 160
            dialog_title = "Curve Import Options" if show_spline_options else "Select Coordinate Plane"
            dialog = CD.CustomDialog(parent, title=dialog_title, size=(240, dialog_height))
            
            # Add description
            desc_label = QtWidgets.QLabel("<b>Choose curve flat plane:</b>")
            desc_label.setWordWrap(True)
            dialog.add_widget(desc_label)
            
            # Add radio buttons for each plane
            plane_button_group = QtWidgets.QButtonGroup()
            plane_radio_buttons = {}
            # 3 column grid
            radio_button_layout = QtWidgets.QGridLayout()
            for i, (plane_key, plane_config) in enumerate(cls.PLANES.items()):
                radio = CustomRadioButton(f"{plane_config['name']}", group=True, height=16)
                radio.group('plane_selector')
                radio.setToolTip(plane_config['description'])
                if plane_key == cls._current_plane:
                    radio.setChecked(True)
                plane_button_group.addButton(radio)
                plane_radio_buttons[plane_key] = radio
                
                # Calculate row and column from index
                row = i // 3  # Integer division for row
                col = i % 3   # Modulo for column
                radio_button_layout.addWidget(radio, row, col)

            dialog.add_layout(radio_button_layout)
            
            # Add spline separation options if requested
            spline_radio_buttons = {}
            if show_spline_options:
                # Add spline mode description
                spline_option_layout = QtWidgets.QHBoxLayout()
                spline_desc_label = QtWidgets.QLabel("<b>Spline handling:</b>")
                spline_desc_label.setWordWrap(True)
                dialog.add_widget(spline_desc_label)
                
                separate_radio = CustomRadioButton("Separate", group=True, height=16)
                separate_radio.group('spline_mode')
                separate_radio.setToolTip("Create one button per spline")
                separate_radio.setChecked(True)  # Default to separate
                spline_radio_buttons['separate'] = separate_radio
                spline_option_layout.addWidget(separate_radio)
                
                combine_radio = CustomRadioButton("Combined", group=True, height=16)
                combine_radio.group('spline_mode')
                combine_radio.setToolTip("Create one button per curve object with all splines combined")
                spline_radio_buttons['combine'] = combine_radio
                spline_option_layout.addWidget(combine_radio)
                
                dialog.add_layout(spline_option_layout)
            
            # Add buttons
            button_box = dialog.add_button_box()
            
            if dialog.exec_() == QtWidgets.QDialog.Accepted:
                # Find which plane radio button is selected
                selected_plane = cls._current_plane
                for plane_key, radio in plane_radio_buttons.items():
                    if radio.isChecked():
                        cls.set_plane(plane_key)
                        selected_plane = plane_key
                        break
                
                # Find which spline mode is selected (if applicable)
                separate_splines = True  # Default
                if show_spline_options:
                    for mode_key, radio in spline_radio_buttons.items():
                        if radio.isChecked():
                            separate_splines = (mode_key == 'separate')
                            break
                
                # Return appropriate format based on whether spline options were shown
                if show_spline_options:
                    return {'plane': selected_plane, 'separate_splines': separate_splines}
                else:
                    return selected_plane  # Maintain backward compatibility
            else:
                return None
            
        except Exception as e:
            print(f"Could not show plane selector dialog: {e}")
            if show_spline_options:
                return {'plane': cls._current_plane, 'separate_splines': True}
            else:
                return cls._current_plane

# Initialize with default plane
CoordinatePlaneConfig.set_plane('XY')

def create_buttons_from_blender_curves(canvas, drop_position=None, show_options_dialog=False):
    """
    Create picker buttons from selected curve objects in Blender scene.
    
    Args:
        canvas: The picker canvas to add buttons to
        drop_position (QPointF, optional): Position to place buttons. If None, uses canvas center.
        show_options_dialog (bool): Whether to show coordinate plane and spline options dialog
    
    Returns:
        list: List of created buttons
    """
    from . import picker_button as PB
    from . import data_management as DM
    from . import blender_ui as UI
    
    # Default settings
    separate_splines = True
    
    # Show options dialog if requested
    if show_options_dialog:
        result = CoordinatePlaneConfig.show_plane_selector_dialog(canvas, show_spline_options=True)
        if result is None:
            return []
        # Handle the dictionary return format
        if isinstance(result, dict):
            separate_splines = result['separate_splines']
        else:
            # Fallback for backward compatibility
            separate_splines = True
    
    # Get selected curve objects
    selected_curves = []
    
    # Check selected objects for curves
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        for obj in bpy.context.selected_objects:
            if obj.type == 'CURVE':
                selected_curves.append(obj)
        
        # Also check if we have any curve objects in the scene if nothing selected
        if not selected_curves:
            # Check if current active object is a curve
            if bpy.context.active_object and bpy.context.active_object.type == 'CURVE':
                selected_curves.append(bpy.context.active_object)
    
    if not selected_curves:
        # Show error dialog
        if QtWidgets:
            from . import custom_dialog as CD
            dialog = CD.CustomDialog(canvas, title="No Curves Selected", size=(300, 220), info_box=True)
            
            message_label = QtWidgets.QLabel("Please select curve objects in Blender to create buttons from.")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            
            # Add current plane info
            current_plane = CoordinatePlaneConfig.get_current_plane()
            plane_label = QtWidgets.QLabel(f"Current plane: {current_plane['name']}")
            plane_label.setStyleSheet("font-style: italic; color: #666;")
            dialog.add_widget(plane_label)
            
            # Add spline mode info
            mode_text = "Separate splines" if separate_splines else "Combine splines"
            mode_label = QtWidgets.QLabel(f"Mode: {mode_text}")
            mode_label.setStyleSheet("font-style: italic; color: #666;")
            dialog.add_widget(mode_label)
            
            # Add button to change options
            def change_options():
                result = CoordinatePlaneConfig.show_plane_selector_dialog(dialog, show_spline_options=True)
                if result and isinstance(result, dict):
                    nonlocal separate_splines
                    separate_splines = result['separate_splines']
                    mode_label.setText(f"Mode: {'Separate splines' if separate_splines else 'Combine splines'}")
                    plane_label.setText(f"Current plane: {CoordinatePlaneConfig.get_current_plane()['name']}")
            
            change_options_btn = QtWidgets.QPushButton("Change Import Options")
            change_options_btn.clicked.connect(change_options)
            dialog.add_widget(change_options_btn)
            
            dialog.add_button_box()
            dialog.exec_()
        else:
            print("No curves selected. Please select curve objects in Blender.")
            current_plane = CoordinatePlaneConfig.get_current_plane()
            print(f"Current coordinate plane: {current_plane['name']}")
            mode_text = "separate splines" if separate_splines else "combine splines"
            print(f"Mode: {mode_text}")
        return []
    
    # Set default drop position if not provided
    if drop_position is None:
        drop_position = canvas.get_center_position()
    
    created_buttons = []
    main_window = canvas.window()
    
    if isinstance(main_window, UI.BlenderAnimPickerWindow):
        current_tab = main_window.tab_system.current_tab
        
        # Get existing IDs to avoid conflicts
        existing_ids = set()
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        for button in tab_data.get('buttons', []):
            existing_ids.add(button['id'])
        
        # Also add IDs from current canvas buttons
        for button in canvas.buttons:
            existing_ids.add(button.unique_id)
        
        # Add any pending IDs from available_ids cache
        if current_tab in main_window.available_ids:
            existing_ids.update(main_window.available_ids[current_tab])
        
        # Calculate layout bounds for positioning
        if separate_splines:
            # Calculate bounds for all individual splines
            all_spline_bounds = []
            for curve_obj in selected_curves:
                spline_bounds_list = _calculate_all_splines_bounding_boxes(curve_obj)
                all_spline_bounds.extend(spline_bounds_list)
        else:
            # Calculate bounds for whole curve objects
            all_spline_bounds = []
            for curve_obj in selected_curves:
                curve_bounds = _calculate_curve_bounding_box(curve_obj)
                all_spline_bounds.append(curve_bounds)
        
        if all_spline_bounds:
            layout_bounds = _calculate_combined_bounds(all_spline_bounds)
            layout_center = QtCore.QPointF(
                (layout_bounds['min_x'] + layout_bounds['max_x']) / 2,
                (layout_bounds['min_y'] + layout_bounds['max_y']) / 2
            )
            
            # Scale factor for reasonable button sizes
            max_dimension = max(layout_bounds['width'], layout_bounds['height'])
            scale_factor = 200 / max_dimension if max_dimension > 0 else 1.0
        else:
            layout_center = drop_position
            scale_factor = 1.0
        
        # Prepare for batch database update
        new_buttons_data = []
        button_index = 0
        
        # Process each curve object
        for curve_obj in selected_curves:
            try:
                curve_data = curve_obj.data
                
                if not curve_data.splines:
                    print(f"No splines found in curve {curve_obj.name}")
                    continue
                
                if separate_splines:
                    # Create separate button for each spline (original behavior)
                    for spline_idx, spline in enumerate(curve_data.splines):
                        try:
                            # Generate SVG path data for this specific spline
                            svg_path_data = _convert_spline_to_svg_path(spline)
                            
                            if not svg_path_data:
                                print(f"Warning: Could not generate path data for spline {spline_idx} in curve {curve_obj.name}")
                                continue
                            
                            # Convert path commands to string
                            svg_path_string = " ".join(svg_path_data)
                            
                            # Generate unique ID
                            unique_id = _generate_spline_unique_id(current_tab, existing_ids, curve_obj.name, spline_idx, button_index)
                            existing_ids.add(unique_id)
                            
                            # Create button label
                            if len(curve_data.splines) > 1:
                                button_label = f"{curve_obj.name}.{spline_idx:03d}"
                            else:
                                button_label = curve_obj.name
                            
                            # Create the button
                            new_button = PB.PickerButton('', canvas, unique_id=unique_id, color="#3096bb")
                            
                            # Set up the button with spline path data
                            new_button.shape_type = 'custom_path'
                            new_button.svg_path_data = svg_path_string
                            new_button.svg_file_path = f"blender_curve:{curve_obj.name}:spline_{spline_idx}"
                            
                            # Calculate individual spline bounds for positioning
                            spline_bounds = _calculate_spline_bounding_box(spline)
                            
                            # Position button relative to drop position
                            spline_center_x = (spline_bounds['min_x'] + spline_bounds['max_x']) / 2
                            spline_center_y = (spline_bounds['min_y'] + spline_bounds['max_y']) / 2
                            
                            # Calculate offset from layout center
                            offset_x = (spline_center_x - layout_center.x()) * scale_factor
                            offset_y = (spline_center_y - layout_center.y()) * scale_factor
                            
                            # Position the button
                            button_x = drop_position.x() + offset_x
                            button_y = drop_position.y() + offset_y
                            new_button.scene_position = QtCore.QPointF(button_x, button_y)
                            
                            # Set button size based on spline bounds
                            scaled_width = max(30, spline_bounds['width'] * scale_factor)
                            scaled_height = max(30, spline_bounds['height'] * scale_factor)
                            new_button.width = min(150, scaled_width)
                            new_button.height = min(150, scaled_height)
                            
                            # Add to canvas
                            canvas.add_button(new_button)
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
                            button_index += 1
                            
                        except Exception as e:
                            print(f"Error processing spline {spline_idx} in curve {curve_obj.name}: {e}")
                            continue
                
                else:
                    # Combine all splines into a single button per curve object
                    try:
                        # Generate SVG path data for the entire curve (all splines combined)
                        svg_path_string = _convert_curve_to_svg_path(curve_obj)
                        
                        if not svg_path_string:
                            print(f"Warning: Could not generate path data for curve {curve_obj.name}")
                            continue
                        
                        # Generate unique ID for the combined curve
                        unique_id = _generate_curve_unique_id(current_tab, existing_ids, curve_obj.name, button_index)
                        existing_ids.add(unique_id)
                        
                        # Create button label
                        button_label = curve_obj.name
                        
                        # Create the button
                        new_button = PB.PickerButton('', canvas, unique_id=unique_id, color="#3096bb")
                        
                        # Set up the button with combined curve path data
                        new_button.shape_type = 'custom_path'
                        new_button.svg_path_data = svg_path_string
                        new_button.svg_file_path = f"blender_curve:{curve_obj.name}:combined"
                        
                        # Calculate curve bounds for positioning
                        curve_bounds = _calculate_curve_bounding_box(curve_obj)
                        
                        # Position button relative to drop position
                        curve_center_x = (curve_bounds['min_x'] + curve_bounds['max_x']) / 2
                        curve_center_y = (curve_bounds['min_y'] + curve_bounds['max_y']) / 2
                        
                        # Calculate offset from layout center
                        offset_x = (curve_center_x - layout_center.x()) * scale_factor
                        offset_y = (curve_center_y - layout_center.y()) * scale_factor
                        
                        # Position the button
                        button_x = drop_position.x() + offset_x
                        button_y = drop_position.y() + offset_y
                        new_button.scene_position = QtCore.QPointF(button_x, button_y)
                        
                        # Set button size based on curve bounds
                        scaled_width = max(30, curve_bounds['width'] * scale_factor)
                        scaled_height = max(30, curve_bounds['height'] * scale_factor)
                        new_button.width = min(150, scaled_width)
                        new_button.height = min(150, scaled_height)
                        
                        # Add to canvas
                        canvas.add_button(new_button)
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
                        button_index += 1
                        
                    except Exception as e:
                        print(f"Error processing combined curve {curve_obj.name}: {e}")
                        continue
                        
            except Exception as e:
                print(f"Error processing curve {curve_obj.name}: {e}")
                continue
        
        # Batch database update
        if new_buttons_data:
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            tab_data['buttons'].extend(new_buttons_data)
            DM.PickerDataManager.update_tab_data(current_tab, tab_data)
            DM.PickerDataManager.save_data(DM.PickerDataManager.get_data(), force_immediate=True)
        
        # Select all created buttons
        if created_buttons:
            canvas.clear_selection()
            for button in created_buttons:
                button.toggle_selection()
            
            # Update UI
            canvas.update_button_positions()
            canvas.update()
            canvas.update_hud_counts()
            
            plane_name = CoordinatePlaneConfig.get_current_plane()['name']
            mode_text = "separate splines" if separate_splines else "combined splines"
            print(f"Created {len(created_buttons)} buttons from {len(selected_curves)} curve object(s) using {plane_name} plane ({mode_text})")
    
    return created_buttons

def _convert_curve_to_svg_path(curve_obj):
    """
    Convert a Blender curve object to SVG path data.
    Uses the object's local coordinate system directly via coordinate plane configuration.
    
    Args:
        curve_obj: Blender curve object
        
    Returns:
        str: SVG path data string
    """
    try:
        # Get curve data
        curve_data = curve_obj.data
        
        if not curve_data.splines:
            print(f"No splines found in curve {curve_obj.name}")
            return None
        
        # Process all splines in the curve using LOCAL coordinates only
        all_path_commands = []
        
        for spline_idx, spline in enumerate(curve_data.splines):
            spline_path = _convert_spline_to_svg_path(spline)
            if spline_path:
                if spline_idx == 0:
                    all_path_commands.extend(spline_path)
                else:
                    # For additional splines, we need to start a new path
                    all_path_commands.extend(spline_path)
        
        if not all_path_commands:
            return None
        
        return " ".join(all_path_commands)
        
    except Exception as e:
        print(f"Error converting curve {curve_obj.name}: {e}")
        return None

def _convert_spline_to_svg_path(spline):
    """
    Convert a single spline to SVG path commands using local coordinates only.
    
    Args:
        spline: Blender spline object
        
    Returns:
        list: List of SVG path command strings
    """
    path_commands = []
    
    try:
        # Handle different spline types using LOCAL coordinates
        if spline.type == 'BEZIER':
            points = _get_bezier_points(spline)
            path_commands = _create_bezier_path(points, spline.use_cyclic_u)
            
        elif spline.type == 'NURBS':
            points = _get_nurbs_points(spline)
            path_commands = _create_nurbs_path(points, spline.use_cyclic_u)
            
        elif spline.type == 'POLY':
            points = _get_poly_points(spline)
            path_commands = _create_poly_path(points, spline.use_cyclic_u)
            
        else:
            print(f"Unsupported spline type: {spline.type}")
            return []
            
    except Exception as e:
        print(f"Error converting spline: {e}")
        return []
    
    return path_commands

def _get_bezier_points(spline):
    """Extract points from Bezier spline using local coordinates and coordinate plane configuration."""
    points = []
    
    for point in spline.bezier_points:
        # Get control point coordinates in LOCAL space (no world matrix transformation)
        co_local = point.co
        handle_left_local = point.handle_left
        handle_right_local = point.handle_right
        
        # Transform using current plane configuration (using local coordinates directly)
        co_2d = CoordinatePlaneConfig.transform_point(co_local)
        handle_left_2d = CoordinatePlaneConfig.transform_point(handle_left_local)
        handle_right_2d = CoordinatePlaneConfig.transform_point(handle_right_local)
        
        points.append({
            'co': co_2d,
            'handle_left': handle_left_2d,
            'handle_right': handle_right_2d,
            'handle_left_type': point.handle_left_type,
            'handle_right_type': point.handle_right_type
        })
    
    return points

def _get_nurbs_points(spline):
    """Extract points from NURBS spline by sampling using local coordinates and coordinate plane configuration."""
    points = []
    
    # For NURBS, we'll sample points along the spline
    resolution = max(12, len(spline.points) * 2)  # Adaptive resolution
    
    for i in range(resolution + 1):
        t = i / resolution
        
        # Sample point at parameter t
        if len(spline.points) >= 2:
            # Linear interpolation as fallback
            num_points = len(spline.points)
            segment_t = t * (num_points - 1)
            segment_idx = int(segment_t)
            local_t = segment_t - segment_idx
            
            if segment_idx >= num_points - 1:
                segment_idx = num_points - 2
                local_t = 1.0
            
            p1 = spline.points[segment_idx]
            p2 = spline.points[segment_idx + 1]
            
            # Interpolate between points in LOCAL space
            co_local = Vector((
                p1.co.x * (1 - local_t) + p2.co.x * local_t,
                p1.co.y * (1 - local_t) + p2.co.y * local_t,
                p1.co.z * (1 - local_t) + p2.co.z * local_t,
                1.0
            ))
            
            # Transform using current plane configuration (local coordinates)
            co_2d = CoordinatePlaneConfig.transform_point(co_local)
            points.append(co_2d)
    
    return points

def _get_poly_points(spline):
    """Extract points from Poly spline using local coordinates and coordinate plane configuration."""
    points = []
    
    for point in spline.points:
        # Use LOCAL coordinates directly (point.co is a 4D vector)
        co_local = point.co
        
        # Transform using current plane configuration (local coordinates)
        co_2d = CoordinatePlaneConfig.transform_point(co_local)
        points.append(co_2d)
    
    return points

def _create_bezier_path(bezier_points, is_closed):
    """Create SVG path from Bezier control points."""
    if not bezier_points:
        return []
    
    path_commands = []
    
    # Start with first point
    first_point = bezier_points[0]
    path_commands.append(f"M {first_point['co'][0]:.3f},{first_point['co'][1]:.3f}")
    
    # Create curves between points
    for i in range(1, len(bezier_points)):
        prev_point = bezier_points[i-1]
        curr_point = bezier_points[i]
        
        # Check if we need a curve or just a line
        if (prev_point['handle_right_type'] == 'VECTOR' and 
            curr_point['handle_left_type'] == 'VECTOR'):
            # Straight line
            path_commands.append(f"L {curr_point['co'][0]:.3f},{curr_point['co'][1]:.3f}")
        else:
            # Cubic Bezier curve
            c1 = prev_point['handle_right']
            c2 = curr_point['handle_left']
            end = curr_point['co']
            
            path_commands.append(f"C {c1[0]:.3f},{c1[1]:.3f} {c2[0]:.3f},{c2[1]:.3f} {end[0]:.3f},{end[1]:.3f}")
    
    # Handle closed curves
    if is_closed and len(bezier_points) > 2:
        # Close back to first point
        last_point = bezier_points[-1]
        first_point = bezier_points[0]
        
        if (last_point['handle_right_type'] == 'VECTOR' and 
            first_point['handle_left_type'] == 'VECTOR'):
            path_commands.append("Z")
        else:
            # Cubic curve back to start
            c1 = last_point['handle_right']
            c2 = first_point['handle_left']
            end = first_point['co']
            
            path_commands.append(f"C {c1[0]:.3f},{c1[1]:.3f} {c2[0]:.3f},{c2[1]:.3f} {end[0]:.3f},{end[1]:.3f}")
            path_commands.append("Z")
    
    return path_commands

def _create_nurbs_path(points, is_closed):
    """Create SVG path from NURBS sample points."""
    if len(points) < 2:
        return []
    
    path_commands = []
    
    # Start with first point
    path_commands.append(f"M {points[0][0]:.3f},{points[0][1]:.3f}")
    
    # Create smooth curves through points
    if len(points) <= 4:
        # Simple case - use lines or single curve
        for point in points[1:]:
            path_commands.append(f"L {point[0]:.3f},{point[1]:.3f}")
    else:
        # Use quadratic curves for smoothness
        for i in range(1, len(points) - 1, 2):
            if i + 1 < len(points):
                control_point = points[i]
                end_point = points[i + 1]
                path_commands.append(f"Q {control_point[0]:.3f},{control_point[1]:.3f} {end_point[0]:.3f},{end_point[1]:.3f}")
            else:
                # Last point
                path_commands.append(f"L {points[i][0]:.3f},{points[i][1]:.3f}")
    
    if is_closed:
        path_commands.append("Z")
    
    return path_commands

def _create_poly_path(points, is_closed):
    """Create SVG path from Poly points (straight lines)."""
    if len(points) < 2:
        return []
    
    path_commands = []
    
    # Start with first point
    path_commands.append(f"M {points[0][0]:.3f},{points[0][1]:.3f}")
    
    # Connect all points with lines
    for point in points[1:]:
        path_commands.append(f"L {point[0]:.3f},{point[1]:.3f}")
    
    if is_closed:
        path_commands.append("Z")
    
    return path_commands

def _get_object_bounds_3d(obj):
    """Get object bounding box in LOCAL coordinates (not world coordinates)."""
    bbox_corners = []
    
    # Get all 8 corners of the bounding box in LOCAL space
    for corner in obj.bound_box:
        local_corner = Vector(corner)
        bbox_corners.append(local_corner)
    
    # Find min/max in each local axis
    min_x = min(corner.x for corner in bbox_corners)
    max_x = max(corner.x for corner in bbox_corners)
    min_y = min(corner.y for corner in bbox_corners)
    max_y = max(corner.y for corner in bbox_corners)
    min_z = min(corner.z for corner in bbox_corners)
    max_z = max(corner.z for corner in bbox_corners)
    
    return {
        'min_x': min_x,
        'max_x': max_x,
        'min_y': min_y,
        'max_y': max_y,
        'min_z': min_z,
        'max_z': max_z,
        'width': max_x - min_x,
        'height': max_y - min_y,
        'depth': max_z - min_z
    }

def _calculate_curve_bounding_box(curve_obj):
    """
    Calculate the 2D bounding box of a curve object using coordinate plane configuration.
    
    Args:
        curve_obj: Blender curve object
        
    Returns:
        dict: Dictionary with min_x, max_x, min_y, max_y, width, height
    """
    try:
        bounds_3d = _get_object_bounds_3d(curve_obj)
        return CoordinatePlaneConfig.get_bounds_for_plane(bounds_3d)
    except Exception as e:
        print(f"Error calculating bounding box for {curve_obj.name}: {e}")
        return {'min_x': 0, 'max_x': 100, 'min_y': 0, 'max_y': 100, 'width': 100, 'height': 100}

def _calculate_all_splines_bounding_boxes(curve_obj):
    """
    Calculate bounding boxes for all splines in a curve object.
    
    Args:
        curve_obj: Blender curve object
        
    Returns:
        list: List of bounding box dictionaries for each spline
    """
    spline_bounds = []
    
    try:
        curve_data = curve_obj.data
        
        for spline in curve_data.splines:
            bounds = _calculate_spline_bounding_box(spline)
            spline_bounds.append(bounds)
            
    except Exception as e:
        print(f"Error calculating spline bounds for {curve_obj.name}: {e}")
    
    return spline_bounds

def _calculate_spline_bounding_box(spline):
    """
    Calculate the 2D bounding box of a single spline using coordinate plane configuration.
    
    Args:
        spline: Blender spline object
        
    Returns:
        dict: Dictionary with min_x, max_x, min_y, max_y, width, height
    """
    try:
        points_2d = []
        
        # Get 2D points based on spline type
        if spline.type == 'BEZIER':
            bezier_points = _get_bezier_points(spline)
            for point in bezier_points:
                points_2d.append(point['co'])
                points_2d.append(point['handle_left'])
                points_2d.append(point['handle_right'])
                
        elif spline.type == 'NURBS':
            points_2d = _get_nurbs_points(spline)
            
        elif spline.type == 'POLY':
            points_2d = _get_poly_points(spline)
        
        if not points_2d:
            return {'min_x': 0, 'max_x': 10, 'min_y': 0, 'max_y': 10, 'width': 10, 'height': 10}
        
        # Find bounds
        min_x = min(point[0] for point in points_2d)
        max_x = max(point[0] for point in points_2d)
        min_y = min(point[1] for point in points_2d)
        max_y = max(point[1] for point in points_2d)
        
        return {
            'min_x': min_x,
            'max_x': max_x,
            'min_y': min_y,
            'max_y': max_y,
            'width': max_x - min_x,
            'height': max_y - min_y
        }
        
    except Exception as e:
        print(f"Error calculating spline bounding box: {e}")
        return {'min_x': 0, 'max_x': 10, 'min_y': 0, 'max_y': 10, 'width': 10, 'height': 10}

def _calculate_combined_bounds(bounds_list):
    """
    Calculate combined bounding box from a list of individual bounds.
    
    Args:
        bounds_list: List of bounding box dictionaries
        
    Returns:
        dict: Combined bounding box
    """
    if not bounds_list:
        return {'min_x': 0, 'max_x': 100, 'min_y': 0, 'max_y': 100, 'width': 100, 'height': 100}
    
    min_x = min(bounds['min_x'] for bounds in bounds_list)
    max_x = max(bounds['max_x'] for bounds in bounds_list)
    min_y = min(bounds['min_y'] for bounds in bounds_list)
    max_y = max(bounds['max_y'] for bounds in bounds_list)
    
    return {
        'min_x': min_x,
        'max_x': max_x,
        'min_y': min_y,
        'max_y': max_y,
        'width': max_x - min_x,
        'height': max_y - min_y
    }

def _generate_curve_unique_id(tab_name, existing_ids, curve_name, button_index):
    """Generate a unique ID for combined curve buttons"""
    # Clean curve name for use in ID
    clean_curve_name = "".join(c for c in curve_name if c.isalnum() or c in "_-").lower()
    
    base_patterns = [
        f"{tab_name}_{clean_curve_name}",
        f"{tab_name}_{clean_curve_name}_combined",
        f"{tab_name}_curve_{button_index:03d}",
        f"{tab_name}_button_{len(existing_ids)+button_index+1:03d}"
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
    
    # Fallback: use timestamp-based ID
    import time
    timestamp_id = f"{tab_name}_curve_{int(time.time() * 1000)}_{button_index}"
    return timestamp_id

def _generate_spline_unique_id(tab_name, existing_ids, curve_name, spline_index, button_index):
    """Generate a unique ID for spline-created buttons"""
    # Clean curve name for use in ID
    clean_curve_name = "".join(c for c in curve_name if c.isalnum() or c in "_-").lower()
    
    base_patterns = [
        f"{tab_name}_{clean_curve_name}_spline_{spline_index:03d}",
        f"{tab_name}_{clean_curve_name}_{spline_index:03d}",
        f"{tab_name}_spline_{button_index:03d}",
        f"{tab_name}_button_{len(existing_ids)+button_index+1:03d}"
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
    
    # Fallback: use timestamp-based ID
    import time
    timestamp_id = f"{tab_name}_spline_{int(time.time() * 1000)}_{button_index}"
    return timestamp_id

# Context menu integration
def create_buttons_from_blender_curves_context_menu(self):
    """Context menu action to create buttons from selected Blender curves"""
    scene_pos = self.get_center_position()  # Use canvas center
    create_buttons_from_blender_curves(self, scene_pos)

def create_buttons_from_blender_curves_with_plane_selector(self):
    """Context menu action to create buttons with plane selector dialog"""
    scene_pos = self.get_center_position()
    create_buttons_from_blender_curves(self, scene_pos, show_plane_selector=True)

# Utility functions for external access
def set_coordinate_plane(plane_name):
    """
    Set the coordinate plane for Blender curve conversion.
    
    Args:
        plane_name (str): One of 'XY', 'XZ', 'YZ', 'XY_FLIPPED', 'XZ_FLIPPED', 'YZ_FLIPPED'
    """
    CoordinatePlaneConfig.set_plane(plane_name)

def get_available_planes():
    """Get list of available coordinate planes."""
    return list(CoordinatePlaneConfig.PLANES.keys())

def get_current_plane_info():
    """Get current coordinate plane information."""
    return CoordinatePlaneConfig.get_current_plane()

# Blender operator for easy integration
class CURVE_OT_to_picker_buttons(bpy.types.Operator):
    """Convert selected curves to picker buttons"""
    bl_idname = "curve.to_picker_buttons"
    bl_label = "Curves to Picker Buttons"
    bl_description = "Convert selected curve objects to picker buttons"
    bl_options = {'REGISTER', 'UNDO'}
    
    show_plane_selector: bpy.props.BoolProperty(
        name="Show Plane Selector",
        description="Show coordinate plane selector dialog",
        default=False
    )
    
    @classmethod
    def poll(cls, context):
        return context.selected_objects and any(obj.type == 'CURVE' for obj in context.selected_objects)
    
    def execute(self, context):
        print("Converting curves to picker buttons...")
        
        # You would call your main function here with the picker canvas:
        # create_buttons_from_blender_curves(your_canvas, show_plane_selector=self.show_plane_selector)
        
        # For now, just show the current plane info
        current_plane = CoordinatePlaneConfig.get_current_plane()
        self.report({'INFO'}, f"Using coordinate plane: {current_plane['name']}")
        
        return {'FINISHED'}
    
    def invoke(self, context, event):
        if self.show_plane_selector:
            # Show plane selector dialog
            result = CoordinatePlaneConfig.show_plane_selector_dialog()
            if result is None:
                return {'CANCELLED'}
        
        return self.execute(context)

class CURVE_OT_set_coordinate_plane(bpy.types.Operator):
    """Set coordinate plane for curve conversion"""
    bl_idname = "curve.set_coordinate_plane"
    bl_label = "Set Coordinate Plane"
    bl_description = "Set the coordinate plane for curve to button conversion"
    bl_options = {'REGISTER', 'UNDO'}
    
    plane_name: bpy.props.EnumProperty(
        name="Coordinate Plane",
        description="Choose which local coordinate axes to use for curve conversion",
        items=[
            ('XY', 'XY Plane', 'Use local X and Y axes'),
            ('XZ', 'XZ Plane', 'Use local X and Z axes'),
            ('YZ', 'YZ Plane', 'Use local Y and Z axes'),
            ('XY_FLIPPED', 'XY Plane (Y Flipped)', 'Use local X and Y axes with Y flipped'),
            ('XZ_FLIPPED', 'XZ Plane (Z Flipped)', 'Use local X and Z axes with Z flipped'),
            ('YZ_FLIPPED', 'YZ Plane (Z Flipped)', 'Use local Y and Z axes with Z flipped'),
        ],
        default='XY'
    )
    
    def execute(self, context):
        CoordinatePlaneConfig.set_plane(self.plane_name)
        current_plane = CoordinatePlaneConfig.get_current_plane()
        self.report({'INFO'}, f"Coordinate plane set to: {current_plane['name']}")
        return {'FINISHED'}

# Registration for Blender
def register():
    bpy.utils.register_class(CURVE_OT_to_picker_buttons)
    bpy.utils.register_class(CURVE_OT_set_coordinate_plane)

def unregister():
    bpy.utils.unregister_class(CURVE_OT_to_picker_buttons)
    bpy.utils.unregister_class(CURVE_OT_set_coordinate_plane)