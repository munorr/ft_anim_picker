import maya.cmds as cmds
import maya.api.OpenMaya as om
import math

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

from .custom_dialog import CustomDialog
from .custom_button import CustomButton, CustomRadioButton
from .utils import undoable

# =============================================================================
# COORDINATE PLANE CONFIGURATION
# =============================================================================
# 
# Enhanced coordinate plane detection system for Maya curve conversion.
# Features:
# - Automatic detection of the flattest coordinate plane from curves, meshes, and bone shapes
# - Per-curve optimal plane detection for mixed-orientation curve sets
# - Confidence scoring for detection accuracy
# - Support for multiple object types in a single analysis
# - Improved flatness analysis using 3D bounding box calculations
# - Backward compatibility with existing code
# 
# NEW: Per-Curve Plane Detection
# - Each curve is analyzed individually to find its optimal coordinate plane
# - Curves with different orientations get their own optimal plane
# - Maintains proper 2D projection regardless of curve orientation
# - Can be enabled/disabled via use_per_curve_planes parameter
# =============================================================================

class CoordinatePlaneConfig:
    """
    Centralized configuration for coordinate plane mapping.
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
            'default': False
        },
        'XZ': {
            'name': 'XZ',
            'description': 'Use local X and Z axes',
            'x_axis': 0,  # Local X -> SVG X
            'y_axis': 2,  # Local Z -> SVG Y
            'flip_x': False,
            'flip_y': False,
            'default': True
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
            'flip_y': True,  # Flip Z axis
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
    _current_plane = 'XZ'
    
    @classmethod
    def set_plane(cls, plane_name):
        """Set the active coordinate plane."""
        if plane_name in cls.PLANES:
            cls._current_plane = plane_name
            #print(f"Coordinate plane set to: {cls.PLANES[plane_name]['name']}")
        else:
            available = ', '.join(cls.PLANES.keys())
            #print(f"Invalid plane '{plane_name}'. Available planes: {available}")
    
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
            local_point: tuple (x, y, z) in local coordinates
            
        Returns:
            tuple: (x, y) in SVG coordinates
        """
        config = cls.get_current_plane()
        
        # Convert to tuple if needed
        if hasattr(local_point, '__len__'):
            point_tuple = tuple(local_point)
        else:
            point_tuple = local_point
        
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
    def detect_flat_plane_from_curves(cls, curve_objects=None, mesh_objects=None, bone_shapes=None):
        """
        Automatically detect the best coordinate plane based on selected curves, meshes, and bone shapes.
        
        Args:
            curve_objects: List of Maya curve shape nodes (optional, will auto-detect if None)
            mesh_objects: List of Maya mesh objects (optional)
            bone_shapes: List of bone shape tuples (optional)
            
        Returns:
            tuple: (plane_name, confidence_score, analysis_info)
        """
        # Auto-detect objects if not provided
        if curve_objects is None and mesh_objects is None and bone_shapes is None:
            selected_objects = cmds.ls(selection=True, long=True)
            if not selected_objects:
                return cls._current_plane, 0.0, "No objects selected for auto-detection"
            
            # Auto-detect curve objects from selection
            curve_objects = []
            for obj in selected_objects:
                curve_shapes = cmds.listRelatives(obj, shapes=True, type='nurbsCurve', fullPath=True) or []
                curve_objects.extend(curve_shapes)
            
            # Auto-detect mesh objects from selection
            mesh_objects = _get_selected_mesh_objects()
            
            # Auto-detect bone shapes from selection
            bone_shapes = _get_selected_bones_with_shapes()
        
        if not curve_objects and not mesh_objects and not bone_shapes:
            return cls._current_plane, 0.0, "No objects to analyze"
        
        # Collect all 3D bounds
        all_bounds = []
        
        # Analyze curves
        if curve_objects:
            for curve_shape in curve_objects:
                try:
                    bounds = _get_curve_bounds_3d(curve_shape)
                    if bounds:
                        all_bounds.append(bounds)
                except Exception as e:
                    print(f"Error analyzing curve {curve_shape}: {e}")
                    continue
        
        # Analyze meshes (if implemented)
        if mesh_objects:
            for mesh_obj in mesh_objects:
                try:
                    # Get mesh bounds in local space
                    bbox = cmds.exactWorldBoundingBox(mesh_obj)
                    bounds = {
                        'min_x': bbox[0], 'max_x': bbox[3],
                        'min_y': bbox[1], 'max_y': bbox[4],
                        'min_z': bbox[2], 'max_z': bbox[5]
                    }
                    all_bounds.append(bounds)
                except Exception as e:
                    print(f"Error analyzing mesh {mesh_obj}: {e}")
                    continue
        
        # Analyze bone shapes (if implemented)
        if bone_shapes:
            for bone, shape_obj, armature_obj in bone_shapes:
                try:
                    # Get bone shape bounds in local space
                    bbox = cmds.exactWorldBoundingBox(shape_obj)
                    bounds = {
                        'min_x': bbox[0], 'max_x': bbox[3],
                        'min_y': bbox[1], 'max_y': bbox[4],
                        'min_z': bbox[2], 'max_z': bbox[5]
                    }
                    all_bounds.append(bounds)
                except Exception as e:
                    print(f"Error analyzing bone shape {shape_obj}: {e}")
                    continue
        
        if not all_bounds:
            return cls._current_plane, 0.0, "No valid bounds found"
        
        # Calculate combined bounds
        combined_bounds = cls._calculate_combined_3d_bounds(all_bounds)
        
        # Analyze flatness in each plane
        plane_analysis = cls._analyze_flatness_in_planes(combined_bounds)
        
        # Find the flattest plane
        best_plane, confidence, analysis = cls._find_flattest_plane(plane_analysis)
        
        print(f"Auto-detected coordinate plane: {best_plane} (confidence: {confidence:.2f})")
        print(f"Analysis: {analysis['description']}")
        
        return best_plane, confidence, analysis
    
    @classmethod
    def _calculate_combined_3d_bounds(cls, bounds_list):
        """Calculate combined 3D bounds from a list of individual bounds."""
        if not bounds_list:
            return {'min_x': 0, 'max_x': 1, 'min_y': 0, 'max_y': 1, 'min_z': 0, 'max_z': 1, 'width_x': 1, 'width_y': 1, 'width_z': 1}
        
        min_x = min(bounds['min_x'] for bounds in bounds_list)
        max_x = max(bounds['max_x'] for bounds in bounds_list)
        min_y = min(bounds['min_y'] for bounds in bounds_list)
        max_y = max(bounds['max_y'] for bounds in bounds_list)
        min_z = min(bounds['min_z'] for bounds in bounds_list)
        max_z = max(bounds['max_z'] for bounds in bounds_list)
        
        return {
            'min_x': min_x, 'max_x': max_x,
            'min_y': min_y, 'max_y': max_y,
            'min_z': min_z, 'max_z': max_z,
            'width_x': max_x - min_x,
            'width_y': max_y - min_y,
            'width_z': max_z - min_z
        }
    
    @classmethod
    def _analyze_flatness_in_planes(cls, bounds_3d):
        """Analyze how flat the geometry is in each coordinate plane."""
        # Calculate dimensions
        dim_x = bounds_3d['width_x']
        dim_y = bounds_3d['width_y']
        dim_z = bounds_3d['width_z']
        
        # Calculate flatness ratios (smaller dimension = flatter)
        total_xy = dim_x + dim_y
        total_xz = dim_x + dim_z
        total_yz = dim_y + dim_z
        
        # Flatness is inverse to the smallest dimension
        flatness_xy = dim_z / (total_xy + dim_z) if (total_xy + dim_z) > 0 else 1.0
        flatness_xz = dim_y / (total_xz + dim_y) if (total_xz + dim_y) > 0 else 1.0
        flatness_yz = dim_x / (total_yz + dim_x) if (total_yz + dim_x) > 0 else 1.0
        
        return {
            'XY': {
                'flatness': flatness_xy,
                'confidence': 1.0 - flatness_xy,
                'dimensions': (dim_x, dim_y, dim_z),
                'description': f"XY plane: {dim_x:.2f} x {dim_y:.2f} (Z depth: {dim_z:.2f})"
            },
            'XZ': {
                'flatness': flatness_xz,
                'confidence': 1.0 - flatness_xz,
                'dimensions': (dim_x, dim_z, dim_y),
                'description': f"XZ plane: {dim_x:.2f} x {dim_z:.2f} (Y depth: {dim_y:.2f})"
            },
            'YZ': {
                'flatness': flatness_yz,
                'confidence': 1.0 - flatness_yz,
                'dimensions': (dim_y, dim_z, dim_x),
                'description': f"YZ plane: {dim_y:.2f} x {dim_z:.2f} (X depth: {dim_x:.2f})"
            }
        }
    
    @classmethod
    def _find_flattest_plane(cls, plane_analysis):
        """Find the flattest plane and determine if it needs flipping."""
        best_plane = None
        best_confidence = 0.0
        best_analysis = None
        
        for plane_name, analysis in plane_analysis.items():
            if analysis['confidence'] > best_confidence:
                best_confidence = analysis['confidence']
                best_plane = plane_name
                best_analysis = analysis
        
        # Determine if we need flipped version based on typical Maya conventions
        # For most cases, we want Y-down orientation for SVG compatibility
        if best_plane == 'XY':
            # XY is typically used with Y flipped for SVG
            final_plane = 'XY'  # Keep as XY (already has Y flip in config)
        elif best_plane == 'XZ':
            # XZ is typically used without flipping
            final_plane = 'XZ'  # Keep as XZ (no flip in config)
        elif best_plane == 'YZ':
            # YZ is typically used without flipping
            final_plane = 'YZ'  # Keep as YZ (no flip in config)
        else:
            final_plane = 'XZ'  # Fallback to Maya default
        
        return final_plane, best_confidence, best_analysis
    
    @classmethod
    def detect_optimal_plane_for_curve(cls, curve_shape):
        """
        Detect the optimal coordinate plane for a single curve.
        
        Args:
            curve_shape: Maya curve shape node
            
        Returns:
            tuple: (plane_name, confidence_score, analysis_info)
        """
        try:
            # Get bounds for this specific curve
            bounds = _get_curve_bounds_3d(curve_shape)
            if not bounds:
                return cls._current_plane, 0.0, "No valid bounds found"
            
            # Analyze flatness in each plane
            plane_analysis = cls._analyze_flatness_in_planes(bounds)
            
            # Find the flattest plane
            best_plane, confidence, analysis = cls._find_flattest_plane(plane_analysis)
            
            return best_plane, confidence, analysis
            
        except Exception as e:
            print(f"Error detecting optimal plane for curve {curve_shape}: {e}")
            return cls._current_plane, 0.0, f"Error: {str(e)}"
    
    @classmethod
    def transform_point_with_plane(cls, local_point, plane_name):
        """
        Transform a local 3D point to 2D SVG coordinates using a specific plane.
        
        Args:
            local_point: tuple (x, y, z) in local coordinates
            plane_name: Name of the plane to use for transformation
            
        Returns:
            tuple: (x, y) in SVG coordinates
        """
        if plane_name not in cls.PLANES:
            print(f"Warning: Unknown plane '{plane_name}', using current plane")
            return cls.transform_point(local_point)
        
        config = cls.PLANES[plane_name]
        
        # Convert to tuple if needed
        if hasattr(local_point, '__len__'):
            point_tuple = tuple(local_point)
        else:
            point_tuple = local_point
        
        # Extract the two coordinates for the specified plane
        svg_x = point_tuple[config['x_axis']]
        svg_y = point_tuple[config['y_axis']]
        
        # Apply flipping if needed
        if config['flip_x']:
            svg_x = -svg_x
        if config['flip_y']:
            svg_y = -svg_y
            
        return (svg_x, svg_y)
    
    @classmethod
    def show_plane_selector_dialog(cls, parent=None, show_spline_options=False):
        """Show a dialog to select the coordinate plane and optionally spline separation mode."""
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
            
            # Add curve mode options if requested
            curve_radio_buttons = {}
            if show_spline_options:
                # Add curve mode description
                curve_option_layout = QtWidgets.QHBoxLayout()
                curve_desc_label = QtWidgets.QLabel("<b>Curve handling:</b>")
                curve_desc_label.setWordWrap(True)
                dialog.add_widget(curve_desc_label)
                
                separate_radio = CustomRadioButton("Separate", group=True, height=16)
                separate_radio.group('curve_mode')
                separate_radio.setToolTip("Create one button per curve shape")
                separate_radio.setChecked(True)  # Default to separate
                curve_radio_buttons['separate'] = separate_radio
                curve_option_layout.addWidget(separate_radio)
                
                combine_radio = CustomRadioButton("Combined", group=True, height=16)
                combine_radio.group('curve_mode')
                combine_radio.setToolTip("Create one button per transform with all curve shapes combined")
                curve_radio_buttons['combine'] = combine_radio
                curve_option_layout.addWidget(combine_radio)
                
                dialog.add_layout(curve_option_layout)
            
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
                
                # Find which curve mode is selected (if applicable)
                separate_curves = True  # Default
                if show_spline_options:
                    for mode_key, radio in curve_radio_buttons.items():
                        if radio.isChecked():
                            separate_curves = (mode_key == 'separate')
                            break
                
                # Return appropriate format based on whether curve options were shown
                if show_spline_options:
                    return {'plane': selected_plane, 'separate_curves': separate_curves}
                else:
                    return selected_plane  # Maintain backward compatibility
            else:
                return None
            
        except Exception as e:
            print(f"Could not show plane selector dialog: {e}")
            if show_spline_options:
                return {'plane': cls._current_plane, 'separate_curves': True}
            else:
                return cls._current_plane

# Initialize with default plane
CoordinatePlaneConfig.set_plane('XZ')

@undoable
def create_buttons_from_maya_curves(canvas, drop_position=None, show_options_dialog=False, use_per_curve_planes=True, use_smart_layout=True):
    """
    Create picker buttons from selected NURBS curves in Maya scene.
    Converts curve to SVG path data for custom button shapes.
    
    Args:
        canvas: The picker canvas to add buttons to
        drop_position (QPointF, optional): Position to place buttons. If None, uses canvas center.
        show_options_dialog (bool): Whether to show coordinate plane and curve options dialog
        use_per_curve_planes (bool): Whether to detect optimal plane for each curve individually
        use_smart_layout (bool): Whether to use smart grid layout for multiple objects
    
    Returns:
        list: List of created buttons
    """
    from . import picker_button as PB
    from . import data_management as DM
    from . import ui as UI
    
    # Get curve mode from canvas or use default
    separate_curves = canvas.get_separate_curves_mode()
    
    # Check if auto-detection is enabled
    auto_detect_enabled = canvas.get_auto_detect_plane_mode()
    
    # Show options dialog if requested
    if show_options_dialog:
        result = CoordinatePlaneConfig.show_plane_selector_dialog(canvas, show_spline_options=True)
        if result is None:
            return []
        # Handle the dictionary return format
        if isinstance(result, dict):
            separate_curves = result['separate_curves']
            # Update canvas setting
            canvas.set_separate_curves_mode(separate_curves)
        else:
            # Fallback for backward compatibility
            separate_curves = True
            canvas.set_separate_curves_mode(separate_curves)
    
    # Get selected curves - simplified approach
    selected_curves = []
    
    # Get selected objects
    selection = cmds.ls(selection=True) or []
    
    # Get selected curves - improved approach to handle CV selection
    selected_curves = []
    curve_shapes_found = set()  # Use set to avoid duplicates

    # Get selected objects
    selection = cmds.ls(selection=True) or []

    for obj in selection:
        try:
            # If it's a component selection (like curve.cv[0]), extract the base name
            if '.' in obj and ('[' in obj and ']' in obj):
                base_name = obj.split('.')[0]
                obj = base_name  # Use the base curve/transform name instead
            
            # Check if it's a curve shape directly
            if cmds.nodeType(obj) == 'nurbsCurve':
                curve_shapes_found.add(obj)
            # Check if it's a transform with curve shapes
            elif cmds.nodeType(obj) == 'transform':
                shapes = cmds.listRelatives(obj, shapes=True, type='nurbsCurve') or []
                curve_shapes_found.update(shapes)
            # Also handle case where component might be from a transform (like transform.cv[0])
            else:
                # Try to get shapes in case the extracted base_name is a transform
                try:
                    shapes = cmds.listRelatives(obj, shapes=True, type='nurbsCurve') or []
                    curve_shapes_found.update(shapes)
                except RuntimeError:
                    pass
                
        except RuntimeError:
            # Skip invalid objects
            continue

    # Process curves based on separate_curves setting
    if separate_curves:
        # Original behavior - each curve shape becomes a button
        selected_curves = list(curve_shapes_found)
    else:
        # Combined behavior - group curve shapes by their transform parent
        # and create one button per transform
        transform_to_curves = {}
        for curve_shape in curve_shapes_found:
            try:
                # Get the parent transform
                parent_transforms = cmds.listRelatives(curve_shape, parent=True, type='transform')
                if parent_transforms:
                    transform = parent_transforms[0]
                    if transform not in transform_to_curves:
                        transform_to_curves[transform] = []
                    transform_to_curves[transform].append(curve_shape)
                else:
                    # Orphaned shape - treat as individual
                    if 'orphaned_shapes' not in transform_to_curves:
                        transform_to_curves['orphaned_shapes'] = []
                    transform_to_curves['orphaned_shapes'].append(curve_shape)
            except Exception as e:
                print(f"Error processing curve shape {curve_shape}: {e}")
                continue
        
        # Convert to a format that works with the rest of the function
        # For combined mode, we'll process transform groups
        selected_curves = transform_to_curves
    
    # Auto-detect coordinate plane if enabled
    if auto_detect_enabled and selected_curves:
        # Prepare curve objects for detection
        curve_objects_for_detection = []
        if separate_curves:
            curve_objects_for_detection = selected_curves
        else:
            # For combined mode, collect all curve shapes
            for transform, curves in selected_curves.items():
                curve_objects_for_detection.extend(curves)
        
        detected_plane, confidence, analysis = CoordinatePlaneConfig.detect_flat_plane_from_curves(
            curve_objects=curve_objects_for_detection,
            mesh_objects=_get_selected_mesh_objects(),
            bone_shapes=_get_selected_bones_with_shapes()
        )
        if detected_plane and confidence > 0.1:  # Only use if confidence is reasonable
            CoordinatePlaneConfig.set_plane(detected_plane)
            print(f"Auto-detected and set coordinate plane to: {detected_plane} (confidence: {confidence:.2f})")
            print(f"Analysis: {analysis['description']}")
        else:
            print(f"Auto-detection confidence too low ({confidence:.2f}), keeping current plane")
    
    if not selected_curves:
        # Show error dialog
        from . import custom_dialog as CD
        dialog = CD.CustomDialog(canvas, title="No Curves Selected", size=(300, 220), info_box=True)
        
        message_label = QtWidgets.QLabel("Please select NURBS curves in Maya to create buttons from.")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        
        # Add current plane info
        current_plane = CoordinatePlaneConfig.get_current_plane()
        plane_label = QtWidgets.QLabel(f"Current plane: {current_plane['name']}")
        plane_label.setStyleSheet("font-style: italic; color: #666;")
        dialog.add_widget(plane_label)
        
        # Add curve mode info
        mode_text = "Separate curves" if separate_curves else "Combine curves"
        mode_label = QtWidgets.QLabel(f"Mode: {mode_text}")
        mode_label.setStyleSheet("font-style: italic; color: #666;")
        dialog.add_widget(mode_label)
        
        # Add button to change options
        def change_options():
            result = CoordinatePlaneConfig.show_plane_selector_dialog(dialog, show_spline_options=True)
            if result and isinstance(result, dict):
                nonlocal separate_curves
                separate_curves = result['separate_curves']
                mode_label.setText(f"Mode: {'Separate curves' if separate_curves else 'Combine curves'}")
                plane_label.setText(f"Current plane: {CoordinatePlaneConfig.get_current_plane()['name']}")
        
        change_options_btn = QtWidgets.QPushButton("Change Import Options")
        change_options_btn.clicked.connect(change_options)
        dialog.add_widget(change_options_btn)
        
        dialog.add_button_box()
        dialog.exec_()
        return []
    
    # Set default drop position if not provided
    if drop_position is None:
        drop_position = canvas.get_center_position()
    
    created_buttons = []
    main_window = canvas.window()
    
    if isinstance(main_window, UI.AnimPickerWindow):
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
        if separate_curves:
            # Original behavior - calculate bounds for individual curves
            curve_bounds = _calculate_curves_bounding_box(selected_curves)
        else:
            # Combined behavior - calculate bounds for all curves from all transforms
            all_curve_shapes = []
            for transform, curves in selected_curves.items():
                all_curve_shapes.extend(curves)
            curve_bounds = _calculate_curves_bounding_box(all_curve_shapes)
        
        layout_center = QtCore.QPointF(
            (curve_bounds['min_x'] + curve_bounds['max_x']) / 2,
            (curve_bounds['min_y'] + curve_bounds['max_y']) / 2
        )
        
        # Scale factor for reasonable button sizes
        max_dimension = max(curve_bounds['width'], curve_bounds['height'])
        scale_factor = 200 / max_dimension if max_dimension > 0 else 1.0
        
        # Prepare for batch database update
        new_buttons_data = []
        
        if separate_curves:
            # Original behavior - one button per curve shape
            for i, curve in enumerate(selected_curves):
                try:
                    # Generate SVG path data from curve with optimal plane detection
                    svg_path_data = _convert_curve_to_svg_path(curve, use_optimal_plane=use_per_curve_planes)
                    
                    if not svg_path_data:
                        print(f"Warning: Could not generate path data for curve {curve}")
                        continue
                    
                    # Generate unique ID
                    unique_id = _generate_curve_unique_id(current_tab, existing_ids, i)
                    existing_ids.add(unique_id)
                    
                    # Get curve name for button label
                    curve_transform = cmds.listRelatives(curve, parent=True)
                    if curve_transform:
                        button_label = curve_transform[0].split(':')[-1]  # Remove namespace
                    else:
                        button_label = curve.split(':')[-1]
                    
                    # Calculate bounds using optimal plane for this curve
                    curve_bounds = _calculate_curve_bounding_box(curve, use_optimal_plane=use_per_curve_planes)
                    
                    # Create and setup button
                    new_button = _create_and_setup_button(
                        canvas, unique_id, svg_path_data, curve, button_label,
                        curve, drop_position, layout_center, scale_factor, curve_bounds
                    )
                    
                    if new_button:
                        created_buttons.append(new_button)
                        new_buttons_data.append(_create_button_data_for_db(new_button))
                    
                except Exception as e:
                    print(f"Error processing curve {curve}: {e}")
                    continue
        else:
            # Combined behavior - one button per transform with all curves combined
            transform_index = 0
            for transform_name, curve_list in selected_curves.items():
                try:
                    if not curve_list:
                        continue
                    
                    # Generate combined SVG path data from all curves in this transform
                    # Each curve uses its optimal plane
                    svg_path_data = _convert_curves_to_combined_svg_path(curve_list, use_optimal_plane=use_per_curve_planes)
                    
                    if not svg_path_data:
                        print(f"Warning: Could not generate path data for transform {transform_name}")
                        continue
                    
                    # Generate unique ID for the combined transform
                    unique_id = _generate_transform_unique_id(current_tab, existing_ids, transform_name, transform_index)
                    existing_ids.add(unique_id)
                    
                    # Create button label from transform name
                    if transform_name == 'orphaned_shapes':
                        button_label = 'orphaned_curves'
                    else:
                        button_label = transform_name.split(':')[-1]  # Remove namespace
                    
                    # Calculate combined bounds for this transform's curves using optimal planes
                    if use_per_curve_planes:
                        transform_bounds = _calculate_curves_bounding_box_with_optimal_planes(curve_list)
                    else:
                        transform_bounds = _calculate_curves_bounding_box(curve_list)
                    
                    # Create and setup button
                    new_button = _create_and_setup_combined_button(
                        canvas, unique_id, svg_path_data, curve_list, button_label,
                        transform_name, drop_position, layout_center, scale_factor, transform_bounds
                    )
                    
                    if new_button:
                        created_buttons.append(new_button)
                        new_buttons_data.append(_create_button_data_for_db(new_button))
                    
                    transform_index += 1
                    
                except Exception as e:
                    print(f"Error processing transform {transform_name}: {e}")
                    continue
        
        # Apply smart layout if multiple buttons were created
        if use_smart_layout and len(created_buttons) > 1:
            _apply_grid_layout_to_buttons(created_buttons, drop_position, padding=30)
            print(f"Applied grid layout to {len(created_buttons)} buttons")
        
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
                button.is_selected = True
                button.selected.emit(button, True)
            
            # Update UI
            canvas.update_button_positions()
            canvas.update()
            canvas.update_hud_counts()
            
            plane_name = CoordinatePlaneConfig.get_current_plane()['name']
            mode_text = "separate curves" if separate_curves else "combined curves"
            curve_count = len(selected_curves) if separate_curves else sum(len(curves) for curves in selected_curves.values())
            print(f"Created {len(created_buttons)} buttons from {curve_count} curve(s) using {plane_name} plane ({mode_text})")
    
    return created_buttons

def _convert_curve_to_svg_path(curve_shape, use_optimal_plane=True):
    """
    Convert a Maya NURBS curve to SVG path data.
    Uses the object's local coordinate system directly via coordinate plane configuration.
    
    Args:
        curve_shape (str): Name of the NURBS curve shape node
        use_optimal_plane (bool): Whether to detect optimal plane for this curve
        
    Returns:
        str: SVG path data string
    """
    try:
        # Get curve information
        degree = cmds.getAttr(f"{curve_shape}.degree")
        cv_count = cmds.getAttr(f"{curve_shape}.controlPoints", size=True)
        is_closed = cmds.getAttr(f"{curve_shape}.form") == 2
        
        # Choose conversion method based on curve properties
        if degree == 1:
            # Linear curve - use CV positions directly
            return _convert_linear_curve(curve_shape, is_closed, use_optimal_plane)
        else:
            # NURBS curve - use proper Maya curve evaluation
            return _convert_nurbs_curve(curve_shape, is_closed, use_optimal_plane)
            
    except Exception as e:
        print(f"Error converting curve {curve_shape}: {e}")
        return None
#-------------------------------------------------------------------------
def _convert_nurbs_curve(curve_shape, is_closed, use_optimal_plane=True):
    """
    Improved NURBS curve conversion using TRUE local coordinates.
    Uses current coordinate plane configuration with PURE LOCAL coordinates.
    """
    try:
        # Detect optimal plane for this curve if requested
        optimal_plane = None
        if use_optimal_plane:
            optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_curve(curve_shape)
            if confidence > 0.1:  # Only use if confidence is reasonable
                print(f"  Using optimal plane {optimal_plane} for curve {curve_shape} (confidence: {confidence:.2f})")
            else:
                optimal_plane = None  # Fall back to current plane
        
        # Get curve parameter range
        min_param = cmds.getAttr(f"{curve_shape}.minValue")
        max_param = cmds.getAttr(f"{curve_shape}.maxValue")
        degree = cmds.getAttr(f"{curve_shape}.degree")
        
        # Check if this is a rational curve (like circles)
        is_rational = _is_rational_curve(curve_shape)
        
        # Special handling for circles and rational curves
        if is_rational or _is_circle_like_curve(curve_shape):
            return _convert_rational_curve(curve_shape, is_closed, optimal_plane)
        
        # Calculate appropriate resolution based on curve properties
        try:
            curve_length = cmds.arclen(curve_shape)
            # Higher resolution for complex curves
            base_resolution = max(16, min(64, int(curve_length * 4)))
            # Additional points for higher degree curves
            degree_factor = max(1.0, degree / 3.0)
            resolution = int(base_resolution * degree_factor)
        except Exception as e:
            # Fallback resolution based on degree
            resolution = max(16, degree * 8)
        
        # Sample points using TRUE local coordinate extraction
        points = []
        tangents = []
        
        for i in range(resolution + 1):
            if resolution == 0:
                param = min_param
            else:
                param = min_param + (max_param - min_param) * (i / resolution)
            
            try:
                # Use TRUE local coordinates via pointOnCurveInfo node
                pos = _get_true_local_curve_point(curve_shape, param)
                tangent = _get_true_local_curve_tangent(curve_shape, param)
                
                # Transform using optimal plane or current plane configuration
                if optimal_plane:
                    svg_point = CoordinatePlaneConfig.transform_point_with_plane(pos, optimal_plane)
                    svg_tangent = CoordinatePlaneConfig.transform_point_with_plane(tangent, optimal_plane)
                else:
                    svg_point = CoordinatePlaneConfig.transform_point(pos)
                    svg_tangent = CoordinatePlaneConfig.transform_point(tangent)
                
                points.append(svg_point)
                tangents.append(svg_tangent)
            except Exception as e:
                print(f"  Error at parameter {param}: {e}")
                continue
        
        #print(f"  Sampled {len(points)} points using true local coordinates")
        
        if len(points) < 2:
            print("  ERROR: Not enough points sampled")
            return None
        
        # Create accurate path using tangent information
        result = _create_accurate_bezier_path(points, tangents, is_closed)
        return result
        
    except Exception as e:
        print(f"Error converting NURBS curve: {e}")
        import traceback
        traceback.print_exc()
        return None

def _is_rational_curve(curve_shape):
    """
    Check if a curve is rational (has non-uniform weights).
    Rational curves like circles need special handling.
    """
    try:
        # Get control vertex count
        cv_count = cmds.getAttr(f"{curve_shape}.controlPoints", size=True)
        
        # Check weights - if any weight is not 1.0, it's rational
        for i in range(cv_count):
            try:
                weight = cmds.getAttr(f"{curve_shape}.controlPoints[{i}].w")
                if abs(weight - 1.0) > 0.001:  # Allow for floating point precision
                    return True
            except:
                continue
        
        return False
        
    except Exception as e:
        print(f"Error checking if curve is rational: {e}")
        return False

def _is_circle_like_curve(curve_shape):
    """
    Detect if a curve is circle-like based on its properties.
    """
    try:
        # Check degree (circles are typically degree 2 or 3)
        degree = cmds.getAttr(f"{curve_shape}.degree")
        if degree not in [2, 3]:
            return False
        
        # Check if it's closed
        is_closed = cmds.getAttr(f"{curve_shape}.form") == 2
        if not is_closed:
            return False
        
        # Get CV count (circles typically have specific CV counts)
        cv_count = cmds.getAttr(f"{curve_shape}.controlPoints", size=True)
        
        # Common circle configurations:
        # - Degree 3 circle: 7 CVs
        # - Degree 2 circle: varies
        if degree == 3 and cv_count == 7:
            return True
        
        # Check if control points form a roughly circular pattern
        return _check_circular_pattern(curve_shape)
        
    except Exception as e:
        print(f"Error checking if curve is circle-like: {e}")
        return False

def _create_smooth_rational_path(points, tangents, is_closed):
    """
    Create smooth SVG path specifically optimized for rational curves like circles.
    """
    if len(points) < 4:
        return None
    
    path_commands = [f"M {points[0][0]:.3f},{points[0][1]:.3f}"]
    
    # For rational curves, use cubic Bezier with careful control point calculation
    # Process points in groups to create smooth cubic segments
    
    num_segments = len(points) - 1 if not is_closed else len(points)
    
    for i in range(num_segments):
        current_point = points[i]
        next_point = points[(i + 1) % len(points)]
        
        # Get tangents with bounds checking
        current_tangent = tangents[i] if i < len(tangents) else (0, 0)
        next_tangent = tangents[(i + 1) % len(tangents)] if (i + 1) % len(tangents) < len(tangents) else (0, 0)
        
        # Calculate segment length
        segment_length = ((next_point[0] - current_point[0])**2 + 
                         (next_point[1] - current_point[1])**2)**0.5
        
        # For circles, use a specific tangent scale that works well
        tangent_scale = segment_length * 0.25  # Slightly shorter for smoother circles
        
        # Normalize and scale tangents
        def normalize_and_scale(tangent, scale):
            length = (tangent[0]**2 + tangent[1]**2)**0.5
            if length > 0.001:  # Avoid division by very small numbers
                return (tangent[0] / length * scale, tangent[1] / length * scale)
            return (scale * 0.1, 0)  # Fallback for zero tangents
        
        current_tangent_scaled = normalize_and_scale(current_tangent, tangent_scale)
        next_tangent_scaled = normalize_and_scale(next_tangent, tangent_scale)
        
        # Calculate control points
        control1_x = current_point[0] + current_tangent_scaled[0]
        control1_y = current_point[1] + current_tangent_scaled[1]
        control2_x = next_point[0] - next_tangent_scaled[0]
        control2_y = next_point[1] - next_tangent_scaled[1]
        
        # Add cubic Bezier curve command
        path_commands.append(
            f"C {control1_x:.3f},{control1_y:.3f} "
            f"{control2_x:.3f},{control2_y:.3f} "
            f"{next_point[0]:.3f},{next_point[1]:.3f}"
        )
    
    if is_closed:
        path_commands.append("Z")
    
    result = " ".join(path_commands)
    return result
#---------------------------------------------------------
def _convert_rational_curve(curve_shape, is_closed, optimal_plane=None):
    """
    Special conversion for rational curves using TRUE local coordinates.
    Uses higher resolution and handles potential numerical issues.
    """
    try:
        print("  Converting rational curve with TRUE local coordinates")
        
        # Get curve parameter range
        min_param = cmds.getAttr(f"{curve_shape}.minValue")
        max_param = cmds.getAttr(f"{curve_shape}.maxValue")
        
        # Use much higher resolution for rational curves
        resolution = 64  # Fixed high resolution for accuracy
        
        # For closed curves, ensure we don't duplicate the start/end point
        if is_closed:
            resolution_steps = resolution
        else:
            resolution_steps = resolution + 1
        
        points = []
        tangents = []
        
        for i in range(resolution_steps):
            # Adjust parameter calculation for closed curves
            if is_closed:
                param = min_param + (max_param - min_param) * (i / resolution)
            else:
                param = min_param + (max_param - min_param) * (i / resolution)
            
            try:
                # Use TRUE local coordinate extraction
                pos = _get_true_local_curve_point(curve_shape, param)
                tangent = _get_true_local_curve_tangent(curve_shape, param)
                
                # Transform using optimal plane or current plane configuration
                if optimal_plane:
                    svg_point = CoordinatePlaneConfig.transform_point_with_plane(pos, optimal_plane)
                    svg_tangent = CoordinatePlaneConfig.transform_point_with_plane(tangent, optimal_plane)
                else:
                    svg_point = CoordinatePlaneConfig.transform_point(pos)
                    svg_tangent = CoordinatePlaneConfig.transform_point(tangent)
                
                points.append(svg_point)
                tangents.append(svg_tangent)
                
            except Exception as e:
                print(f"    Error sampling at parameter {param}: {e}")
                continue
        
        print(f"  Rational curve: sampled {len(points)} points using true local coordinates")
        
        if len(points) < 4:
            print("  ERROR: Not enough points for rational curve")
            return None
        
        # Use specialized path creation for smooth rational curves
        return _create_smooth_rational_path(points, tangents, is_closed)
        
    except Exception as e:
        print(f"Error converting rational curve: {e}")
        return None

def _get_cv_bounds_true_local(curve_shape):
    """
    Fallback method using control vertex bounds in TRUE local space.
    """
    try:
        cv_count = cmds.getAttr(f"{curve_shape}.controlPoints", size=True)
        x_coords = []
        y_coords = []
        z_coords = []
        
        for i in range(cv_count):
            cv_pos = _get_true_local_cv_position(curve_shape, i)
            x_coords.append(cv_pos[0])
            y_coords.append(cv_pos[1])
            z_coords.append(cv_pos[2])
        
        if not x_coords:
            return {'min_x': 0, 'max_x': 100, 'min_y': 0, 'max_y': 100, 'min_z': 0, 'max_z': 100, 'width': 100, 'height': 100, 'depth': 100, 'width_x': 100, 'width_y': 100, 'width_z': 100}
        
        return {
            'min_x': min(x_coords),
            'max_x': max(x_coords),
            'min_y': min(y_coords),
            'max_y': max(y_coords),
            'min_z': min(z_coords),
            'max_z': max(z_coords),
            'width': max(x_coords) - min(x_coords),
            'height': max(y_coords) - min(y_coords),
            'depth': max(z_coords) - min(z_coords),
            'width_x': max(x_coords) - min(x_coords),
            'width_y': max(y_coords) - min(y_coords),
            'width_z': max(z_coords) - min(z_coords)
        }
        
    except Exception as e:
        print(f"Error getting CV bounds in true local: {e}")
        return {'min_x': 0, 'max_x': 100, 'min_y': 0, 'max_y': 100, 'min_z': 0, 'max_z': 100, 'width': 100, 'height': 100, 'depth': 100, 'width_x': 100, 'width_y': 100, 'width_z': 100}

def _check_circular_pattern(curve_shape):
    """
    Check if control vertices form a roughly circular pattern.
    """
    try:
        cv_count = cmds.getAttr(f"{curve_shape}.controlPoints", size=True)
        if cv_count < 4:
            return False
        
        # Get all CV positions using correct Maya command
        cv_positions = []
        for i in range(cv_count):
            cv_pos = cmds.pointPosition(f"{curve_shape}.cv[{i}]", local=True)
            cv_positions.append(cv_pos)
        
        # Calculate centroid
        center_x = sum(pos[0] for pos in cv_positions) / len(cv_positions)
        center_y = sum(pos[1] for pos in cv_positions) / len(cv_positions) 
        center_z = sum(pos[2] for pos in cv_positions) / len(cv_positions)
        
        # Calculate distances from center
        distances = []
        for pos in cv_positions:
            dist = ((pos[0] - center_x)**2 + (pos[1] - center_y)**2 + (pos[2] - center_z)**2)**0.5
            distances.append(dist)
        
        # Check if distances are roughly equal (within 20% tolerance)
        if not distances:
            return False
        
        avg_distance = sum(distances) / len(distances)
        tolerance = avg_distance * 0.2
        
        for dist in distances:
            if abs(dist - avg_distance) > tolerance:
                return False
        
        return True
        
    except Exception as e:
        print(f"Error checking circular pattern: {e}")
        return False

def _convert_linear_curve(curve_shape, is_closed, use_optimal_plane=True):
    """
    Convert linear (degree 1) curve using TRUE local coordinates.
    Uses current coordinate plane configuration with PURE LOCAL coordinates.
    """
    try:
        # Detect optimal plane for this curve if requested
        optimal_plane = None
        if use_optimal_plane:
            optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_curve(curve_shape)
            if confidence > 0.1:  # Only use if confidence is reasonable
                print(f"  Using optimal plane {optimal_plane} for linear curve {curve_shape} (confidence: {confidence:.2f})")
            else:
                optimal_plane = None  # Fall back to current plane
        
        cv_count = cmds.getAttr(f"{curve_shape}.controlPoints", size=True)
        points = []
        
        for i in range(cv_count):
            # Get CV position using TRUE local coordinates
            cv_pos = _get_true_local_cv_position(curve_shape, i)
            # Transform using optimal plane or current plane configuration
            if optimal_plane:
                svg_point = CoordinatePlaneConfig.transform_point_with_plane(cv_pos, optimal_plane)
            else:
                svg_point = CoordinatePlaneConfig.transform_point(cv_pos)
            points.append(svg_point)
        
        if len(points) < 2:
            return None
        
        # Create path commands
        path_commands = [f"M {points[0][0]:.3f},{points[0][1]:.3f}"]
        
        # Connect with lines
        for point in points[1:]:
            path_commands.append(f"L {point[0]:.3f},{point[1]:.3f}")
        
        if is_closed:
            path_commands.append("Z")
        
        return " ".join(path_commands)
        
    except Exception as e:
        print(f"Error converting linear curve: {e}")
        return None

def _create_accurate_bezier_path(points, tangents, is_closed):
    """
    Create an accurate SVG path from sampled points with tangent information.
    Uses cubic Bezier curves for smooth representation of NURBS.
    """
    if len(points) < 2:
        return None
    
    path_commands = [f"M {points[0][0]:.3f},{points[0][1]:.3f}"]
    
    # For very short sequences, use simple lines
    if len(points) <= 3:
        for point in points[1:]:
            path_commands.append(f"L {point[0]:.3f},{point[1]:.3f}")
    else:
        # Use cubic Bezier curves with proper tangent handling
        for i in range(len(points) - 1):
            current_point = points[i]
            next_point = points[i + 1]
            current_tangent = tangents[i] if i < len(tangents) else (0, 0)
            next_tangent = tangents[i + 1] if i + 1 < len(tangents) else (0, 0)
            
            # Calculate control points based on tangents
            # The control point distance is proportional to the segment length
            segment_length = ((next_point[0] - current_point[0])**2 + 
                            (next_point[1] - current_point[1])**2)**0.5
            
            # Scale tangents based on segment length
            tangent_scale = segment_length * 0.33  # Standard Bezier control point distance
            
            # Normalize tangents and apply scaling
            def normalize_and_scale(tangent, scale):
                length = (tangent[0]**2 + tangent[1]**2)**0.5
                if length > 0:
                    return (tangent[0] / length * scale, tangent[1] / length * scale)
                return (0, 0)
            
            current_tangent_scaled = normalize_and_scale(current_tangent, tangent_scale)
            next_tangent_scaled = normalize_and_scale(next_tangent, tangent_scale)
            
            # Calculate control points
            control1_x = current_point[0] + current_tangent_scaled[0]
            control1_y = current_point[1] + current_tangent_scaled[1]
            control2_x = next_point[0] - next_tangent_scaled[0]
            control2_y = next_point[1] - next_tangent_scaled[1]
            
            # Add cubic Bezier curve command
            path_commands.append(
                f"C {control1_x:.3f},{control1_y:.3f} "
                f"{control2_x:.3f},{control2_y:.3f} "
                f"{next_point[0]:.3f},{next_point[1]:.3f}"
            )
    
    if is_closed:
        path_commands.append("Z")
    
    return " ".join(path_commands)

def _get_true_local_curve_point(curve_shape, parameter):
    """
    Get a point on the curve in TRUE local object space coordinates.
    This bypasses Maya's sometimes inconsistent local space handling.
    
    Args:
        curve_shape: Maya curve shape node
        parameter: Parameter value along the curve
        
    Returns:
        tuple: (x, y, z) in true local object coordinates
    """
    try:
        # Method 1: Use curve's local space directly through curve info node
        point_on_curve_info = cmds.createNode('pointOnCurveInfo')
        
        # Connect the curve's LOCAL space (not world space)
        cmds.connectAttr(f"{curve_shape}.local", f"{point_on_curve_info}.inputCurve")
        cmds.setAttr(f"{point_on_curve_info}.parameter", parameter)
        
        # Get the position - this should be in true local space
        local_pos = cmds.getAttr(f"{point_on_curve_info}.position")[0]
        
        # Cleanup
        cmds.delete(point_on_curve_info)
        
        return local_pos
        
    except Exception as e:
        print(f"True local point extraction failed: {e}, using fallback")
        
        try:
            # Fallback: Use standard pointOnCurve (may not be pure local)
            pos = cmds.pointOnCurve(curve_shape, parameter=parameter, position=True)
            return pos
            
        except Exception as e2:
            print(f"Fallback point extraction failed: {e2}")
            return [0, 0, 0]

def _get_true_local_curve_tangent(curve_shape, parameter):
    """
    Get a tangent vector on the curve in TRUE local object space coordinates.
    """
    try:
        # Use curve info node for consistent local space tangent
        point_on_curve_info = cmds.createNode('pointOnCurveInfo')
        cmds.connectAttr(f"{curve_shape}.local", f"{point_on_curve_info}.inputCurve")
        cmds.setAttr(f"{point_on_curve_info}.parameter", parameter)
        
        local_tangent = cmds.getAttr(f"{point_on_curve_info}.tangent")[0]
        
        cmds.delete(point_on_curve_info)
        return local_tangent
        
    except Exception as e:
        print(f"True local tangent extraction failed: {e}, using fallback")
        try:
            return cmds.pointOnCurve(curve_shape, parameter=parameter, tangent=True)
        except Exception as e2:
            print(f"Fallback tangent extraction failed: {e2}")
            return [0, 0, 0]

def _get_true_local_cv_position(curve_shape, cv_index):
    """
    Get a control vertex position in TRUE local coordinates.
    """
    try:
        # Method 1: Direct attribute access to the shape's CV
        cv_pos = cmds.getAttr(f"{curve_shape}.controlPoints[{cv_index}]")[0]
        # This gives us the raw CV position without transform influence
        return cv_pos[:3]  # Return only x, y, z (ignore weight)
        
    except Exception as e:
        print(f"Direct CV access failed: {e}, using fallback")
        
        try:
            # Method 2: pointPosition with explicit local flag
            transform_nodes = cmds.listRelatives(curve_shape, parent=True, type='transform')
            if transform_nodes:
                # Use the transform's CV reference in local space
                cv_pos = cmds.pointPosition(f"{transform_nodes[0]}.cv[{cv_index}]", local=True)
                return cv_pos
            else:
                # No transform, use shape CV directly
                cv_pos = cmds.pointPosition(f"{curve_shape}.cv[{cv_index}]", local=True)
                return cv_pos
                
        except Exception as e2:
            print(f"Fallback CV position extraction failed: {e2}")
            # Ultimate fallback
            return [0, 0, 0]

def _get_curve_bounds_3d(curve_shape):
    """
    Get 3D bounding box using TRUE local coordinates.
    More reliable than CV-based bounds for complex curves.
    """
    try:
        # Get curve parameter range
        min_param = cmds.getAttr(f"{curve_shape}.minValue")
        max_param = cmds.getAttr(f"{curve_shape}.maxValue")
        
        # Sample points for bounds calculation
        x_coords = []
        y_coords = []
        z_coords = []
        
        # Use enough samples to get accurate bounds
        samples = 20
        for i in range(samples + 1):
            if samples == 0:
                param = min_param
            else:
                param = min_param + (max_param - min_param) * (i / samples)
            
            try:
                # Use TRUE local coordinate extraction
                pos = _get_true_local_curve_point(curve_shape, param)
                x_coords.append(pos[0])
                y_coords.append(pos[1])
                z_coords.append(pos[2])
            except Exception as e:
                print(f"Error sampling bounds at parameter {param}: {e}")
                continue
        
        if not x_coords:
            # Fallback to CV bounds
            print("No points sampled for bounds, using CV bounds fallback")
            return _get_cv_bounds_true_local(curve_shape)
        
        bounds = {
            'min_x': min(x_coords),
            'max_x': max(x_coords),
            'min_y': min(y_coords),
            'max_y': max(y_coords),
            'min_z': min(z_coords),
            'max_z': max(z_coords),
            'width': max(x_coords) - min(x_coords),
            'height': max(y_coords) - min(y_coords),
            'depth': max(z_coords) - min(z_coords),
            'width_x': max(x_coords) - min(x_coords),
            'width_y': max(y_coords) - min(y_coords),
            'width_z': max(z_coords) - min(z_coords)
        }
        
        return bounds
        
    except Exception as e:
        print(f"Error getting true local curve bounds: {e}")
        return _get_cv_bounds_true_local(curve_shape)

def _calculate_curve_bounding_box(curve_shape, use_optimal_plane=True):
    """
    Calculate the 2D bounding box of a curve for layout purposes.
    Uses optimal plane detection or current coordinate plane configuration.
    """
    try:
        bounds_3d = _get_curve_bounds_3d(curve_shape)
        
        # Use optimal plane if requested
        if use_optimal_plane:
            optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_curve(curve_shape)
            if confidence > 0.1:  # Only use if confidence is reasonable
                # Get bounds for the optimal plane
                config = CoordinatePlaneConfig.PLANES[optimal_plane]
                
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
        
        # Fall back to current plane configuration
        return CoordinatePlaneConfig.get_bounds_for_plane(bounds_3d)
        
    except Exception as e:
        print(f"Error calculating bounding box for {curve_shape}: {e}")
        return {'min_x': 0, 'max_x': 100, 'min_y': 0, 'max_y': 100, 'width': 100, 'height': 100}

def _calculate_curves_bounding_box(curve_list):
    """
    Calculate the combined 2D bounding box of multiple curves.
    """
    if not curve_list:
        return {'min_x': 0, 'max_x': 100, 'min_y': 0, 'max_y': 100, 'width': 100, 'height': 100}
    
    # Get bounding box for each curve
    all_bounds = [_calculate_curve_bounding_box(curve) for curve in curve_list]
    
    # Find overall bounds
    min_x = min(bounds['min_x'] for bounds in all_bounds)
    max_x = max(bounds['max_x'] for bounds in all_bounds)
    min_y = min(bounds['min_y'] for bounds in all_bounds)
    max_y = max(bounds['max_y'] for bounds in all_bounds)
    
    return {
        'min_x': min_x,
        'max_x': max_x,
        'min_y': min_y,
        'max_y': max_y,
        'width': max_x - min_x,
        'height': max_y - min_y
    }

def _calculate_curves_bounding_box_with_optimal_planes(curve_list):
    """
    Calculate the combined 2D bounding box of multiple curves using optimal planes for each.
    """
    if not curve_list:
        return {'min_x': 0, 'max_x': 100, 'min_y': 0, 'max_y': 100, 'width': 100, 'height': 100}
    
    # Get bounding box for each curve using optimal planes
    all_bounds = [_calculate_curve_bounding_box(curve, use_optimal_plane=True) for curve in curve_list]
    
    # Find overall bounds
    min_x = min(bounds['min_x'] for bounds in all_bounds)
    max_x = max(bounds['max_x'] for bounds in all_bounds)
    min_y = min(bounds['min_y'] for bounds in all_bounds)
    max_y = max(bounds['max_y'] for bounds in all_bounds)
    
    return {
        'min_x': min_x,
        'max_x': max_x,
        'min_y': min_y,
        'max_y': max_y,
        'width': max_x - min_x,
        'height': max_y - min_y
    }

def _generate_curve_unique_id(tab_name, existing_ids, curve_index):
    """Generate a unique ID for curve-created buttons"""
    base_patterns = [
        f"{tab_name}_curve_{curve_index+1:03d}",
        f"{tab_name}_maya_curve_{curve_index+1:03d}",
        f"{tab_name}_shape_{curve_index+1:03d}",
        f"{tab_name}_button_{len(existing_ids)+curve_index+1:03d}"
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
    timestamp_id = f"{tab_name}_curve_{int(time.time() * 1000)}_{curve_index}"
    return timestamp_id
#-------------------------------------------------------------------------
def _convert_curves_to_combined_svg_path(curve_list, use_optimal_plane=True):
    """
    Convert multiple Maya curves to a single combined SVG path data.
    Each curve uses its optimal plane for conversion.
    
    Args:
        curve_list: List of Maya curve shape nodes
        use_optimal_plane: Whether to use optimal plane detection for each curve
        
    Returns:
        str: Combined SVG path data string
    """
    try:
        all_path_commands = []
        
        for i, curve_shape in enumerate(curve_list):
            curve_path = _convert_curve_to_svg_path(curve_shape, use_optimal_plane=use_optimal_plane)
            if curve_path:
                if i == 0:
                    # First curve - use as is
                    all_path_commands.append(curve_path)
                else:
                    # Additional curves - ensure they start new paths
                    all_path_commands.append(curve_path)
        
        if not all_path_commands:
            return None
        
        return " ".join(all_path_commands)
        
    except Exception as e:
        print(f"Error converting combined curves: {e}")
        return None

def _create_and_setup_button(canvas, unique_id, svg_path_data, curve, button_label, 
                           source_reference, drop_position, layout_center, scale_factor, curve_bounds=None):
    """Helper function to create and setup individual curve buttons."""
    from . import picker_button as PB
    
    try:
        # Create the button
        new_button = PB.PickerButton('', canvas, unique_id=unique_id, color="#3096bb")
        
        # Set up the button with curve path data
        new_button.shape_type = 'custom_path'
        new_button.svg_path_data = svg_path_data
        new_button.svg_file_path = f"maya_curve:{source_reference}"
        
        # Use provided curve bounds or calculate them
        if curve_bounds is None:
            curve_bounds_individual = _calculate_curve_bounding_box(curve, use_optimal_plane=True)
        else:
            curve_bounds_individual = curve_bounds
        
        # Position button relative to drop position
        curve_center_x = (curve_bounds_individual['min_x'] + curve_bounds_individual['max_x']) / 2
        curve_center_y = (curve_bounds_individual['min_y'] + curve_bounds_individual['max_y']) / 2
        
        # Calculate offset from layout center
        offset_x = (curve_center_x - layout_center.x()) * scale_factor
        offset_y = (curve_center_y - layout_center.y()) * scale_factor
        
        # Position the button
        button_x = drop_position.x() + offset_x
        button_y = drop_position.y() + offset_y
        new_button.scene_position = QtCore.QPointF(button_x, button_y)
        
        # Set button size based on curve bounds
        scaled_width = max(30, curve_bounds_individual['width'] * scale_factor)
        scaled_height = max(30, curve_bounds_individual['height'] * scale_factor)
        new_button.width = min(150, scaled_width)
        new_button.height = min(150, scaled_height)
        
        # Add to canvas
        canvas.add_button(new_button)
        
        return new_button
        
    except Exception as e:
        print(f"Error creating button for curve {curve}: {e}")
        return None

def _create_and_setup_combined_button(canvas, unique_id, svg_path_data, curve_list, button_label,
                                    transform_name, drop_position, layout_center, scale_factor, transform_bounds):
    """Helper function to create and setup combined curve buttons."""
    from . import picker_button as PB
    
    try:
        # Create the button
        new_button = PB.PickerButton('', canvas, unique_id=unique_id, color="#3096bb")
        
        # Set up the button with combined curve path data
        new_button.shape_type = 'custom_path'
        new_button.svg_path_data = svg_path_data
        new_button.svg_file_path = f"maya_transform:{transform_name}:combined"
        
        # Position button relative to drop position using transform bounds
        transform_center_x = (transform_bounds['min_x'] + transform_bounds['max_x']) / 2
        transform_center_y = (transform_bounds['min_y'] + transform_bounds['max_y']) / 2
        
        # Calculate offset from layout center
        offset_x = (transform_center_x - layout_center.x()) * scale_factor
        offset_y = (transform_center_y - layout_center.y()) * scale_factor
        
        # Position the button
        button_x = drop_position.x() + offset_x
        button_y = drop_position.y() + offset_y
        new_button.scene_position = QtCore.QPointF(button_x, button_y)
        
        # Set button size based on transform bounds
        scaled_width = max(30, transform_bounds['width'] * scale_factor)
        scaled_height = max(30, transform_bounds['height'] * scale_factor)
        new_button.width = min(150, scaled_width)
        new_button.height = min(150, scaled_height)
        
        # Add to canvas
        canvas.add_button(new_button)
        
        return new_button
        
    except Exception as e:
        print(f"Error creating combined button for transform {transform_name}: {e}")
        return None

def _create_button_data_for_db(button):
    """Helper function to create database entry for a button."""
    return {
        "id": button.unique_id,
        "selectable": button.selectable,
        "label": button.label,
        "color": button.color,
        "opacity": button.opacity,
        "position": (button.scene_position.x(), button.scene_position.y()),
        "width": button.width,
        "height": button.height,
        "radius": button.radius,
        "assigned_objects": button.assigned_objects,
        "mode": button.mode,
        "script_data": button.script_data,
        "shape_type": button.shape_type,
        "svg_path_data": button.svg_path_data,
        "svg_file_path": button.svg_file_path
    }

def _generate_transform_unique_id(tab_name, existing_ids, transform_name, transform_index):
    """Generate a unique ID for transform-combined buttons"""
    # Clean transform name for use in ID
    clean_transform_name = "".join(c for c in transform_name if c.isalnum() or c in "_-").lower()
    
    base_patterns = [
        f"{tab_name}_{clean_transform_name}",
        f"{tab_name}_{clean_transform_name}_combined",
        f"{tab_name}_transform_{transform_index:03d}",
        f"{tab_name}_button_{len(existing_ids)+transform_index+1:03d}"
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
    timestamp_id = f"{tab_name}_transform_{int(time.time() * 1000)}_{transform_index}"
    return timestamp_id

def _get_selected_mesh_objects():
    """
    Get selected mesh objects for plane detection.
    
    Returns:
        list: List of mesh transform nodes
    """
    selected_objects = cmds.ls(selection=True, long=True)
    mesh_objects = []
    
    for obj in selected_objects:
        try:
            # Check if it's a mesh transform
            shapes = cmds.listRelatives(obj, shapes=True, type='mesh', fullPath=True) or []
            if shapes:
                mesh_objects.append(obj)
        except Exception as e:
            print(f"Error checking mesh object {obj}: {e}")
            continue
    
    return mesh_objects

def _get_selected_bones_with_shapes():
    """
    Get selected bones with custom shapes for plane detection.
    
    Returns:
        list: List of (bone, shape_obj, armature_obj) tuples
    """
    selected_objects = cmds.ls(selection=True, long=True)
    bone_shapes = []
    
    for obj in selected_objects:
        try:
            # Check if it's a joint (bone)
            if cmds.nodeType(obj) == 'joint':
                # Look for custom shape objects
                connections = cmds.listConnections(obj, type='transform', destination=True) or []
                for connection in connections:
                    # Check if this transform has mesh shapes (custom bone shape)
                    shapes = cmds.listRelatives(connection, shapes=True, type='mesh', fullPath=True) or []
                    if shapes:
                        # Find the armature (parent of the joint)
                        armature = cmds.listRelatives(obj, parent=True, type='transform')
                        armature_obj = armature[0] if armature else None
                        bone_shapes.append((obj, connection, armature_obj))
                        break
        except Exception as e:
            print(f"Error checking bone object {obj}: {e}")
            continue
    
    return bone_shapes

def detect_flat_plane_from_curves_simple():
    """
    Backward compatibility function for the old simple detection method.
    
    Returns:
        str: The detected plane name (e.g., 'XY', 'XZ', 'YZ')
    """
    plane_name, confidence, analysis = CoordinatePlaneConfig.detect_flat_plane_from_curves()
    return plane_name
    
# Context menu integration
def create_buttons_from_maya_curves_context_menu(self):
    """Context menu action to create buttons from selected Maya curves"""
    scene_pos = self.get_center_position()  # Use canvas center
    create_buttons_from_maya_curves(self, scene_pos, use_per_curve_planes=True)

def create_buttons_from_maya_curves_with_plane_selector(self):
    """Context menu action to create buttons with plane selector dialog"""
    scene_pos = self.get_center_position()
    create_buttons_from_maya_curves(self, scene_pos, show_options_dialog=True, use_per_curve_planes=True)

# Utility functions for external access
def set_coordinate_plane(plane_name):
    """
    Set the coordinate plane for Maya curve conversion.
    
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

def test_enhanced_plane_detection():
    """
    Test function to demonstrate the enhanced plane detection capabilities.
    Run this function to test the new detection system with selected objects.
    """
    print("=== Enhanced Plane Detection Test ===")
    
    # Test the new detection method
    plane_name, confidence, analysis = CoordinatePlaneConfig.detect_flat_plane_from_curves()
    
    print(f"Detected plane: {plane_name}")
    print(f"Confidence: {confidence:.3f}")
    print(f"Analysis: {analysis['description']}")
    
    # Show all available planes and their analysis
    print("\n=== All Plane Analysis ===")
    selected_objects = cmds.ls(selection=True, long=True)
    if not selected_objects:
        print("No objects selected for analysis")
        return
    
    # Get curve objects for analysis
    curve_objects = []
    for obj in selected_objects:
        curve_shapes = cmds.listRelatives(obj, shapes=True, type='nurbsCurve', fullPath=True) or []
        curve_objects.extend(curve_shapes)
    
    if curve_objects:
        # Calculate combined bounds
        all_bounds = []
        for curve_shape in curve_objects:
            try:
                bounds = _get_curve_bounds_3d(curve_shape)
                if bounds:
                    all_bounds.append(bounds)
            except Exception as e:
                print(f"Error getting bounds for {curve_shape}: {e}")
                continue
        
        if all_bounds:
            combined_bounds = CoordinatePlaneConfig._calculate_combined_3d_bounds(all_bounds)
            plane_analysis = CoordinatePlaneConfig._analyze_flatness_in_planes(combined_bounds)
            
            for plane_name, analysis in plane_analysis.items():
                print(f"{plane_name}: {analysis['description']} (confidence: {analysis['confidence']:.3f})")
    
    print("=== Test Complete ===")

def test_per_curve_plane_detection():
    """
    Test function to demonstrate per-curve plane detection.
    Run this function to test individual curve plane detection with selected curves.
    """
    print("=== Per-Curve Plane Detection Test ===")
    
    selected_objects = cmds.ls(selection=True, long=True)
    if not selected_objects:
        print("No objects selected for analysis")
        return
    
    # Get curve objects for analysis
    curve_objects = []
    for obj in selected_objects:
        curve_shapes = cmds.listRelatives(obj, shapes=True, type='nurbsCurve', fullPath=True) or []
        curve_objects.extend(curve_shapes)
    
    if not curve_objects:
        print("No curves found in selection")
        return
    
    print(f"Analyzing {len(curve_objects)} curves for optimal planes:")
    print("-" * 60)
    
    for i, curve_shape in enumerate(curve_objects):
        try:
            # Get curve name for display
            curve_transform = cmds.listRelatives(curve_shape, parent=True)
            if curve_transform:
                curve_name = curve_transform[0].split(':')[-1]
            else:
                curve_name = curve_shape.split(':')[-1]
            
            # Detect optimal plane for this curve
            plane_name, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_curve(curve_shape)
            
            print(f"Curve {i+1}: {curve_name}")
            print(f"  Optimal plane: {plane_name} (confidence: {confidence:.3f})")
            print(f"  Analysis: {analysis['description']}")
            print()
            
        except Exception as e:
            print(f"Error analyzing curve {curve_shape}: {e}")
            continue
    
    print("=== Per-Curve Test Complete ===")

def _apply_grid_layout_to_buttons(buttons, drop_position, padding=30):
    """
    Apply a simple grid layout to multiple buttons to prevent overlapping.
    
    Args:
        buttons: List of PickerButton objects
        drop_position: QPointF center position for the grid
        padding: Padding between buttons
    """
    if len(buttons) <= 1:
        return
    
    # Calculate grid dimensions
    import math
    cols = math.ceil(math.sqrt(len(buttons)))
    rows = math.ceil(len(buttons) / cols)
    
    # Calculate button sizes for grid
    max_width = max(button.width for button in buttons)
    max_height = max(button.height for button in buttons)
    
    # Calculate grid dimensions
    grid_width = cols * max_width + (cols - 1) * padding
    grid_height = rows * max_height + (rows - 1) * padding
    
    # Calculate starting position to center the grid
    start_x = drop_position.x() - grid_width / 2
    start_y = drop_position.y() - grid_height / 2
    
    # Position each button
    for i, button in enumerate(buttons):
        row = i // cols
        col = i % cols
        
        x = start_x + col * (max_width + padding)
        y = start_y + row * (max_height + padding)
        
        # Center the button within its grid cell
        x += (max_width - button.width) / 2
        y += (max_height - button.height) / 2
        
        button.scene_position = QtCore.QPointF(x, y)