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
from .utils import undoable

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
    def detect_flat_plane_from_curves(cls, curve_objects, mesh_objects=None, bone_shapes=None):
        """
        Automatically detect the best coordinate plane based on selected curves, meshes, and bone shapes.
        
        Args:
            curve_objects: List of Blender curve objects
            mesh_objects: List of Blender mesh objects (optional)
            bone_shapes: List of bone shape tuples (optional)
            
        Returns:
            tuple: (plane_name, confidence_score, analysis_info)
        """
        if not curve_objects and not mesh_objects and not bone_shapes:
            return cls._current_plane, 0.0, "No objects to analyze"
        
        # Collect all 3D bounds
        all_bounds = []
        
        # Analyze curves
        for curve_obj in curve_objects:
            try:
                bounds = _get_object_bounds_3d(curve_obj)
                all_bounds.append(bounds)
            except Exception as e:
                print(f"Error analyzing curve {curve_obj.name}: {e}")
                continue
        
        # Analyze meshes
        if mesh_objects:
            for mesh_obj in mesh_objects:
                try:
                    bounds = _get_object_bounds_3d(mesh_obj)
                    all_bounds.append(bounds)
                except Exception as e:
                    print(f"Error analyzing mesh {mesh_obj.name}: {e}")
                    continue
        
        # Analyze bone shapes
        if bone_shapes:
            for bone, shape_obj, armature_obj in bone_shapes:
                try:
                    bounds = _get_object_bounds_3d(shape_obj)
                    all_bounds.append(bounds)
                except Exception as e:
                    print(f"Error analyzing bone shape {shape_obj.name}: {e}")
                    continue
        
        if not all_bounds:
            return cls._current_plane, 0.0, "No valid bounds found"
        
        # Calculate combined bounds
        combined_bounds = cls._calculate_combined_3d_bounds(all_bounds)
        
        # Analyze flatness in each plane
        plane_analysis = cls._analyze_flatness_in_planes(combined_bounds)
        
        # Find the flattest plane
        best_plane = cls._find_flattest_plane(plane_analysis)
        
        return best_plane
    
    @classmethod
    def _calculate_combined_3d_bounds(cls, bounds_list):
        """Calculate combined 3D bounds from a list of individual bounds."""
        if not bounds_list:
            return {'min_x': 0, 'max_x': 1, 'min_y': 0, 'max_y': 1, 'min_z': 0, 'max_z': 1}
        
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
        
        # Determine if we need flipped version based on typical Blender conventions
        # For most cases, we want Y-down orientation for SVG compatibility
        if best_plane == 'XY':
            # XY is typically used with Y flipped for SVG
            final_plane = 'XY'  # Keep as XY (already has Y flip in config)
        elif best_plane == 'XZ':
            # XZ is typically used with Z flipped for SVG
            final_plane = 'XZ'  # Keep as XZ (already has Z flip in config)
        elif best_plane == 'YZ':
            # YZ is typically used without flipping
            final_plane = 'YZ'  # Keep as YZ (no flip in config)
        else:
            final_plane = 'XY'  # Fallback
        
        return final_plane, best_confidence, best_analysis
    
    @classmethod
    def detect_optimal_plane_for_object(cls, obj):
        """
        Detect the optimal coordinate plane for a single Blender object.
        
        Args:
            obj: Blender object (curve, mesh, etc.)
            
        Returns:
            tuple: (plane_name, confidence_score, analysis_info)
        """
        try:
            # Get bounds for this specific object
            bounds = _get_object_bounds_3d(obj)
            if not bounds:
                return cls._current_plane, 0.0, "No valid bounds found"
            
            # Analyze flatness in each plane
            plane_analysis = cls._analyze_flatness_in_planes(bounds)
            
            # Find the flattest plane
            best_plane, confidence, analysis = cls._find_flattest_plane(plane_analysis)
            
            return best_plane, confidence, analysis
            
        except Exception as e:
            print(f"Error detecting optimal plane for object {obj.name}: {e}")
            return cls._current_plane, 0.0, f"Error: {str(e)}"
    
    @classmethod
    def detect_optimal_plane_for_spline(cls, spline):
        """
        Detect the optimal coordinate plane for a single spline.
        
        Args:
            spline: Blender spline object
            
        Returns:
            tuple: (plane_name, confidence_score, analysis_info)
        """
        try:
            # Get 3D points from spline for bounds calculation
            points_3d = []
            
            if spline.type == 'BEZIER':
                for point in spline.bezier_points:
                    points_3d.append(point.co)
                    points_3d.append(point.handle_left)
                    points_3d.append(point.handle_right)
            elif spline.type == 'NURBS':
                for point in spline.points:
                    points_3d.append(point.co)
            elif spline.type == 'POLY':
                for point in spline.points:
                    points_3d.append(point.co)
            
            if not points_3d:
                return cls._current_plane, 0.0, "No valid points found"
            
            # Calculate 3D bounds
            min_x = min(point.x for point in points_3d)
            max_x = max(point.x for point in points_3d)
            min_y = min(point.y for point in points_3d)
            max_y = max(point.y for point in points_3d)
            min_z = min(point.z for point in points_3d)
            max_z = max(point.z for point in points_3d)
            
            bounds = {
                'min_x': min_x, 'max_x': max_x,
                'min_y': min_y, 'max_y': max_y,
                'min_z': min_z, 'max_z': max_z,
                'width_x': max_x - min_x,
                'width_y': max_y - min_y,
                'width_z': max_z - min_z
            }
            
            # Analyze flatness in each plane
            plane_analysis = cls._analyze_flatness_in_planes(bounds)
            
            # Find the flattest plane
            best_plane, confidence, analysis = cls._find_flattest_plane(plane_analysis)
            
            return best_plane, confidence, analysis
            
        except Exception as e:
            print(f"Error detecting optimal plane for spline: {e}")
            return cls._current_plane, 0.0, f"Error: {str(e)}"
    
    @classmethod
    def detect_optimal_plane_for_mesh(cls, mesh_obj):
        """
        Detect the optimal coordinate plane for a mesh by analyzing actual vertex positions.
        This provides more accurate results than using object bounding box.
        
        Args:
            mesh_obj: Blender mesh object
            
        Returns:
            tuple: (plane_name, confidence_score, analysis_info)
        """
        try:
            mesh_data = mesh_obj.data
            
            if not mesh_data.vertices:
                return cls._current_plane, 0.0, "No vertices found"
            
            # Get 3D points from actual mesh vertices (in local coordinates)
            points_3d = []
            for vertex in mesh_data.vertices:
                points_3d.append(vertex.co)
            
            if not points_3d:
                return cls._current_plane, 0.0, "No valid vertex points found"
            
            # Calculate 3D bounds from actual vertex positions
            min_x = min(point.x for point in points_3d)
            max_x = max(point.x for point in points_3d)
            min_y = min(point.y for point in points_3d)
            max_y = max(point.y for point in points_3d)
            min_z = min(point.z for point in points_3d)
            max_z = max(point.z for point in points_3d)
            
            bounds = {
                'min_x': min_x, 'max_x': max_x,
                'min_y': min_y, 'max_y': max_y,
                'min_z': min_z, 'max_z': max_z,
                'width_x': max_x - min_x,
                'width_y': max_y - min_y,
                'width_z': max_z - min_z
            }
            
            # Analyze flatness in each plane
            plane_analysis = cls._analyze_flatness_in_planes(bounds)
            
            # Find the flattest plane
            best_plane, confidence, analysis = cls._find_flattest_plane(plane_analysis)
            
            return best_plane, confidence, analysis
            
        except Exception as e:
            print(f"Error detecting optimal plane for mesh {mesh_obj.name}: {e}")
            return cls._current_plane, 0.0, f"Error: {str(e)}"
    
    @classmethod
    def transform_point_with_plane(cls, local_point, plane_name):
        """
        Transform a local 3D point to 2D SVG coordinates using a specific plane.
        
        Args:
            local_point: Vector or tuple (x, y, z) in local coordinates
            plane_name: Name of the plane to use for transformation
            
        Returns:
            tuple: (x, y) in SVG coordinates
        """
        if plane_name not in cls.PLANES:
            print(f"Warning: Unknown plane '{plane_name}', using current plane")
            return cls.transform_point(local_point)
        
        config = cls.PLANES[plane_name]
        
        # Convert to tuple if needed
        if hasattr(local_point, 'x'):
            # Blender Vector
            point_tuple = (local_point.x, local_point.y, local_point.z)
        elif hasattr(local_point, '__len__'):
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
        if not QtWidgets:
            # Fallback for when Qt is not available
            #print("Available coordinate planes:")
            for i, (plane_key, plane_config) in enumerate(cls.PLANES.items()):
                marker = " (current)" if plane_key == cls._current_plane else ""
                #print(f"  {i+1}. {plane_config['name']}{marker}")
            
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
#--------------------------------------------------------------------------------------------------------------
# Initialize with default plane
CoordinatePlaneConfig.set_plane('XY')
#--------------------------------------------------------------------------------------------------------------
@undoable
def create_buttons_from_blender_curves(canvas, drop_position=None, show_options_dialog=False, use_per_object_planes=True, use_smart_layout=True):
    """
    Create picker buttons from selected curve objects and mesh objects (vertices only) in Blender scene.
    
    Args:
        canvas: The picker canvas to add buttons to
        drop_position (QPointF, optional): Position to place buttons. If None, uses canvas center.
        show_options_dialog (bool): Whether to show coordinate plane and spline options dialog
        use_per_object_planes (bool): Whether to detect optimal plane for each object/spline individually
    
    Returns:
        list: List of created buttons
    """
    from . import picker_button as PB
    from . import data_management as DM
    from . import blender_ui as UI
    
    # Get spline mode from canvas or use default
    separate_splines = canvas.get_separate_splines_mode()
    
    # Show options dialog if requested
    if show_options_dialog:
        result = CoordinatePlaneConfig.show_plane_selector_dialog(canvas, show_spline_options=True)
        if result is None:
            return []
        # Handle the dictionary return format
        if isinstance(result, dict):
            separate_splines = result['separate_splines']
            # Update canvas setting
            canvas.set_separate_splines_mode(separate_splines)
        else:
            # Fallback for backward compatibility
            separate_splines = True
            canvas.set_separate_splines_mode(separate_splines)
    
    # Get selected curve and mesh objects
    selected_curves = []
    selected_meshes = []
    
    # Check selected objects for curves and meshes
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        for obj in bpy.context.selected_objects:
            if obj.type == 'CURVE':
                selected_curves.append(obj)
            elif obj.type == 'MESH':
                # Check if mesh has faces - we only want vertex-only meshes
                mesh_data = obj.data
                if not mesh_data.polygons:  # No faces
                    selected_meshes.append(obj)
        
        # Also check if current active object is a curve or valid mesh
        if bpy.context.active_object:
            if bpy.context.active_object.type == 'CURVE':
                if bpy.context.active_object not in selected_curves:
                    selected_curves.append(bpy.context.active_object)
            elif bpy.context.active_object.type == 'MESH':
                mesh_data = bpy.context.active_object.data
                if not mesh_data.polygons and bpy.context.active_object not in selected_meshes:
                    selected_meshes.append(bpy.context.active_object)
    
    # Check for selected bones with custom shapes
    selected_bone_shapes = _get_selected_bones_with_shapes()
    
    # Auto-detect the best coordinate plane if we have objects to analyze and auto-detection is enabled
    # Skip global auto-detection if using per-object planes to avoid conflicts
    auto_detect_enabled = canvas.get_auto_detect_plane_mode()
    if auto_detect_enabled and not use_per_object_planes and (selected_curves or selected_meshes or selected_bone_shapes):
        detected_plane, confidence, analysis = CoordinatePlaneConfig.detect_flat_plane_from_curves(
            selected_curves, selected_meshes, selected_bone_shapes
        )
        
        # Only auto-set if confidence is high enough (avoid false positives)
        if confidence > 0.7:  # 70% confidence threshold
            CoordinatePlaneConfig.set_plane(detected_plane)
            print(f"Auto-detected coordinate plane: {detected_plane} (confidence: {confidence:.1%})")
            if analysis:
                print(f"Analysis: {analysis['description']}")
        else:
            print(f"Auto-detection confidence too low ({confidence:.1%}), keeping current plane: {CoordinatePlaneConfig.get_current_plane_name()}")
    elif not auto_detect_enabled:
        print("Auto-detection disabled - using manually selected coordinate plane")
    elif use_per_object_planes:
        print("Per-object plane detection enabled - skipping global auto-detection")
    

    
    if not selected_curves and not selected_meshes and not selected_bone_shapes:
        # Show error dialog
        if QtWidgets:
            from . import custom_dialog as CD
            dialog = CD.CustomDialog(canvas, title="No Valid Objects Selected", size=(300, 250), info_box=True)
            
            message_label = QtWidgets.QLabel(
                "Please select one of the following in Blender:\n"
                "• Curve objects\n"
                "• Mesh objects without faces (vertices only)\n"
                "• Bones with custom shapes (in Pose mode)"
            )
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
            print("No valid objects selected. Please select curve objects, mesh objects without faces, or bones with custom shapes.")
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
        
        # Calculate layout bounds for positioning (combine curves and meshes)
        all_object_bounds = []
        
        # Process curves
        if separate_splines:
            for curve_obj in selected_curves:
                spline_bounds_list = _calculate_all_splines_bounding_boxes(curve_obj, use_per_object_planes)
                all_object_bounds.extend(spline_bounds_list)
        else:
            for curve_obj in selected_curves:
                curve_bounds = _calculate_curve_bounding_box(curve_obj, use_per_object_planes)
                all_object_bounds.append(curve_bounds)
        
        # Process meshes
        if separate_splines:
            for mesh_obj in selected_meshes:
                # Detect optimal plane for layout bounds if enabled
                optimal_plane_for_layout = None
                if use_per_object_planes:
                    optimal_plane_for_layout, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_mesh(mesh_obj)
                    if confidence <= 0.1:  # Fall back to None if confidence is too low
                        optimal_plane_for_layout = None
                
                mesh_component_bounds_list = _calculate_mesh_component_bounding_boxes(mesh_obj, optimal_plane_for_layout)
                all_object_bounds.extend(mesh_component_bounds_list)
        else:
            for mesh_obj in selected_meshes:
                mesh_bounds = _calculate_mesh_bounding_box(mesh_obj, use_per_object_planes)
                all_object_bounds.append(mesh_bounds)
        
        # Process bones with custom shapes
        for bone, shape_obj, armature_obj in selected_bone_shapes:
            bone_bounds = _calculate_bone_shape_bounding_box(bone, shape_obj, armature_obj)
            all_object_bounds.append(bone_bounds)
        
        if all_object_bounds:
            layout_bounds = _calculate_combined_bounds(all_object_bounds)
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
        
        # Collect all button information for smart layout
        button_info_list = []
        
        # If using smart layout, collect all button bounds first
        if use_smart_layout:
            smart_layout_bounds = []
            smart_layout_buttons = []
        
        # Process each curve object (existing curve processing logic)
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
                            # Detect optimal plane for this specific spline if enabled
                            optimal_plane = None
                            if use_per_object_planes:
                                optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_spline(spline)
                                if confidence > 0.1:  # Only use if confidence is reasonable
                                    print(f"    Using optimal plane {optimal_plane} for spline {spline_idx} (confidence: {confidence:.2f})")
                                else:
                                    optimal_plane = None  # Fall back to current plane
                            
                            # Generate SVG path data for this specific spline
                            svg_path_data = _convert_spline_to_svg_path(spline, optimal_plane)
                            
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
                            spline_bounds = _calculate_spline_bounding_box(spline, use_per_object_planes)
                            
                            # Position and size button
                            spline_center_x = (spline_bounds['min_x'] + spline_bounds['max_x']) / 2
                            spline_center_y = (spline_bounds['min_y'] + spline_bounds['max_y']) / 2
                            
                            offset_x = (spline_center_x - layout_center.x()) * scale_factor
                            offset_y = (spline_center_y - layout_center.y()) * scale_factor
                            
                            button_x = drop_position.x() + offset_x
                            button_y = drop_position.y() + offset_y
                            new_button.scene_position = QtCore.QPointF(button_x, button_y)
                            
                            scaled_width = max(30, spline_bounds['width'] * scale_factor)
                            scaled_height = max(30, spline_bounds['height'] * scale_factor)
                            new_button.width = min(150, scaled_width)
                            new_button.height = min(150, scaled_height)
                            
                            # Add to canvas and prepare for database
                            canvas.add_button(new_button)
                            created_buttons.append(new_button)
                            
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
                        svg_path_string = _convert_curve_to_svg_path(curve_obj, use_per_object_planes)
                        
                        if not svg_path_string:
                            print(f"Warning: Could not generate path data for curve {curve_obj.name}")
                            continue
                        
                        unique_id = _generate_curve_unique_id(current_tab, existing_ids, curve_obj.name, button_index)
                        existing_ids.add(unique_id)
                        
                        new_button = PB.PickerButton('', canvas, unique_id=unique_id, color="#3096bb")
                        
                        new_button.shape_type = 'custom_path'
                        new_button.svg_path_data = svg_path_string
                        new_button.svg_file_path = f"blender_curve:{curve_obj.name}:combined"
                        
                        curve_bounds = _calculate_curve_bounding_box(curve_obj, use_per_object_planes)
                        
                        curve_center_x = (curve_bounds['min_x'] + curve_bounds['max_x']) / 2
                        curve_center_y = (curve_bounds['min_y'] + curve_bounds['max_y']) / 2
                        
                        offset_x = (curve_center_x - layout_center.x()) * scale_factor
                        offset_y = (curve_center_y - layout_center.y()) * scale_factor
                        
                        button_x = drop_position.x() + offset_x
                        button_y = drop_position.y() + offset_y
                        new_button.scene_position = QtCore.QPointF(button_x, button_y)
                        
                        scaled_width = max(30, curve_bounds['width'] * scale_factor)
                        scaled_height = max(30, curve_bounds['height'] * scale_factor)
                        new_button.width = min(150, scaled_width)
                        new_button.height = min(150, scaled_height)
                        
                        canvas.add_button(new_button)
                        created_buttons.append(new_button)
                        
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
        
        # Process each mesh object (UPDATED MESH PROCESSING)
        for mesh_obj in selected_meshes:
            try:
                mesh_data = mesh_obj.data
                
                if not mesh_data.vertices:
                    print(f"No vertices found in mesh {mesh_obj.name}")
                    continue
                
                if separate_splines and mesh_data.edges:
                    # Detect optimal plane for this mesh if enabled
                    optimal_plane = None
                    if use_per_object_planes:
                        optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_mesh(mesh_obj)
                        if confidence > 0.1:  # Only use if confidence is reasonable
                            print(f"  Using optimal plane {optimal_plane} for mesh {mesh_obj.name} (confidence: {confidence:.2f})")
                            if analysis:
                                print(f"    Analysis: {analysis['description']}")
                        else:
                            optimal_plane = None  # Fall back to current plane
                    
                    # Create separate button for each connected component
                    svg_path_strings = _convert_mesh_to_svg_path(mesh_obj, separate_components=True, optimal_plane=optimal_plane)
                    
                    if not svg_path_strings:
                        print(f"Warning: Could not generate path data for mesh {mesh_obj.name}")
                        continue
                    
                    # Get component bounds for positioning
                    component_bounds_list = _calculate_mesh_component_bounding_boxes(mesh_obj, optimal_plane)
                    
                    for component_idx, (svg_path_string, component_bounds) in enumerate(zip(svg_path_strings, component_bounds_list)):
                        try:
                            # Generate unique ID for this component
                            unique_id = _generate_mesh_component_unique_id(current_tab, existing_ids, mesh_obj.name, component_idx, button_index)
                            existing_ids.add(unique_id)
                            
                            # Create the button
                            new_button = PB.PickerButton('', canvas, unique_id=unique_id, color="#bb3096")
                            
                            # Set up the button with component path data
                            new_button.shape_type = 'custom_path'
                            new_button.svg_path_data = svg_path_string
                            new_button.svg_file_path = f"blender_mesh:{mesh_obj.name}:component_{component_idx}"
                            
                            # Position button relative to drop position
                            component_center_x = (component_bounds['min_x'] + component_bounds['max_x']) / 2
                            component_center_y = (component_bounds['min_y'] + component_bounds['max_y']) / 2
                            
                            # Calculate offset from layout center
                            offset_x = (component_center_x - layout_center.x()) * scale_factor
                            offset_y = (component_center_y - layout_center.y()) * scale_factor
                            
                            # Position the button
                            button_x = drop_position.x() + offset_x
                            button_y = drop_position.y() + offset_y
                            new_button.scene_position = QtCore.QPointF(button_x, button_y)
                            
                            # Set button size based on component bounds
                            scaled_width = max(30, component_bounds['width'] * scale_factor)
                            scaled_height = max(30, component_bounds['height'] * scale_factor)
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
                            print(f"Error processing mesh component {component_idx} in {mesh_obj.name}: {e}")
                            continue
                
                else:
                    # Detect optimal plane for this mesh if enabled
                    optimal_plane = None
                    if use_per_object_planes:
                        optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_mesh(mesh_obj)
                        if confidence > 0.1:  # Only use if confidence is reasonable
                            print(f"  Using optimal plane {optimal_plane} for mesh {mesh_obj.name} (confidence: {confidence:.2f})")
                            if analysis:
                                print(f"    Analysis: {analysis['description']}")
                        else:
                            optimal_plane = None  # Fall back to current plane
                    
                    # Create single combined button for entire mesh (original behavior)
                    svg_path_string = _convert_mesh_to_svg_path(mesh_obj, separate_components=False, optimal_plane=optimal_plane)
                    
                    if not svg_path_string:
                        print(f"Warning: Could not generate path data for mesh {mesh_obj.name}")
                        continue
                    
                    # Generate unique ID for mesh
                    unique_id = _generate_mesh_unique_id(current_tab, existing_ids, mesh_obj.name, button_index)
                    existing_ids.add(unique_id)
                    
                    # Create the button
                    new_button = PB.PickerButton('', canvas, unique_id=unique_id, color="#bb3096")
                    
                    # Set up the button with mesh path data
                    new_button.shape_type = 'custom_path'
                    new_button.svg_path_data = svg_path_string
                    new_button.svg_file_path = f"blender_mesh:{mesh_obj.name}:vertices"
                    
                    # Calculate mesh bounds for positioning
                    mesh_bounds = _calculate_mesh_bounding_box(mesh_obj)
                    
                    # Position button relative to drop position
                    mesh_center_x = (mesh_bounds['min_x'] + mesh_bounds['max_x']) / 2
                    mesh_center_y = (mesh_bounds['min_y'] + mesh_bounds['max_y']) / 2
                    
                    # Calculate offset from layout center
                    offset_x = (mesh_center_x - layout_center.x()) * scale_factor
                    offset_y = (mesh_center_y - layout_center.y()) * scale_factor
                    
                    # Position the button
                    button_x = drop_position.x() + offset_x
                    button_y = drop_position.y() + offset_y
                    new_button.scene_position = QtCore.QPointF(button_x, button_y)
                    
                    # Set button size based on mesh bounds
                    scaled_width = max(30, mesh_bounds['width'] * scale_factor)
                    scaled_height = max(30, mesh_bounds['height'] * scale_factor)
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
                print(f"Error processing mesh {mesh_obj.name}: {e}")
                continue
        
        # Process each bone shape (NEW BONE SHAPE PROCESSING)
        for bone, custom_shape_obj, armature_obj in selected_bone_shapes:
            try:
                # Generate SVG path data for bone shape
                svg_path_string = _convert_bone_shape_to_svg_path(bone, custom_shape_obj, armature_obj)
                
                if not svg_path_string:
                    print(f"Warning: Could not generate path data for bone shape {bone.name} -> {custom_shape_obj.name}")
                    continue
                
                # Generate unique ID for bone shape
                unique_id = _generate_bone_shape_unique_id(current_tab, existing_ids, bone.name, custom_shape_obj.name, button_index)
                existing_ids.add(unique_id)
                
                # Create the button
                new_button = PB.PickerButton('', canvas, unique_id=unique_id, color="#bb9630")  # Different color for bone shapes
                
                # Set up the button with bone shape path data
                new_button.shape_type = 'custom_path'
                new_button.svg_path_data = svg_path_string
                new_button.svg_file_path = f"blender_bone_shape:{armature_obj.name}:{bone.name}:{custom_shape_obj.name}"
                
                # Calculate bone shape bounds for positioning
                bone_shape_bounds = _calculate_bone_shape_bounding_box(bone, custom_shape_obj, armature_obj)
                
                # Position button relative to drop position
                shape_center_x = (bone_shape_bounds['min_x'] + bone_shape_bounds['max_x']) / 2
                shape_center_y = (bone_shape_bounds['min_y'] + bone_shape_bounds['max_y']) / 2
                
                # Calculate offset from layout center
                offset_x = (shape_center_x - layout_center.x()) * scale_factor
                offset_y = (shape_center_y - layout_center.y()) * scale_factor
                
                # Position the button
                button_x = drop_position.x() + offset_x
                button_y = drop_position.y() + offset_y
                new_button.scene_position = QtCore.QPointF(button_x, button_y)
                
                # Set button size based on bone shape bounds
                scaled_width = max(30, bone_shape_bounds['width'] * scale_factor)
                scaled_height = max(30, bone_shape_bounds['height'] * scale_factor)
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
                print(f"Error processing bone shape {bone.name} -> {custom_shape_obj.name}: {e}")
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
            mode_text = "separate splines" if separate_splines else "combined splines"
            curve_count = len(selected_curves)
            mesh_count = len(selected_meshes)
            bone_shape_count = len(selected_bone_shapes)
            print(f"Created {len(created_buttons)} buttons from {curve_count} curve(s), {mesh_count} mesh(es), and {bone_shape_count} bone shape(s) using {plane_name} plane ({mode_text})")

    return created_buttons

def _convert_curve_to_svg_path(curve_obj, use_optimal_plane=True):
    """
    Convert a Blender curve object to SVG path data.
    Uses the object's local coordinate system directly via coordinate plane configuration.
    
    Args:
        curve_obj: Blender curve object
        use_optimal_plane (bool): Whether to detect optimal plane for this curve
        
    Returns:
        str: SVG path data string
    """
    try:
        # Detect optimal plane for this curve if requested
        optimal_plane = None
        if use_optimal_plane:
            optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_object(curve_obj)
            if confidence > 0.1:  # Only use if confidence is reasonable
                print(f"  Using optimal plane {optimal_plane} for curve {curve_obj.name} (confidence: {confidence:.2f})")
            else:
                optimal_plane = None  # Fall back to current plane
        
        # Get curve data
        curve_data = curve_obj.data
        
        if not curve_data.splines:
            print(f"No splines found in curve {curve_obj.name}")
            return None
        
        # Process all splines in the curve using LOCAL coordinates only
        all_path_commands = []
        
        for spline_idx, spline in enumerate(curve_data.splines):
            spline_path = _convert_spline_to_svg_path(spline, optimal_plane)
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

def _convert_spline_to_svg_path(spline, optimal_plane=None):
    """
    Convert a single spline to SVG path commands using local coordinates only.
    
    Args:
        spline: Blender spline object
        optimal_plane: Optional plane name to use for transformation
        
    Returns:
        list: List of SVG path command strings
    """
    path_commands = []
    
    try:
        # Handle different spline types using LOCAL coordinates
        if spline.type == 'BEZIER':
            points = _get_bezier_points(spline, optimal_plane)
            path_commands = _create_bezier_path(points, spline.use_cyclic_u)
            
        elif spline.type == 'NURBS':
            points = _get_nurbs_points(spline, optimal_plane)
            path_commands = _create_nurbs_path(points, spline.use_cyclic_u)
            
        elif spline.type == 'POLY':
            points = _get_poly_points(spline, optimal_plane)
            path_commands = _create_poly_path(points, spline.use_cyclic_u)
            
        else:
            print(f"Unsupported spline type: {spline.type}")
            return []
            
    except Exception as e:
        print(f"Error converting spline: {e}")
        return []
    
    return path_commands

def _get_bezier_points(spline, optimal_plane=None):
    """Extract points from Bezier spline using local coordinates and coordinate plane configuration."""
    points = []
    
    for point in spline.bezier_points:
        # Get control point coordinates in LOCAL space (no world matrix transformation)
        co_local = point.co
        handle_left_local = point.handle_left
        handle_right_local = point.handle_right
        
        # Transform using optimal plane or current plane configuration
        if optimal_plane:
            co_2d = CoordinatePlaneConfig.transform_point_with_plane(co_local, optimal_plane)
            handle_left_2d = CoordinatePlaneConfig.transform_point_with_plane(handle_left_local, optimal_plane)
            handle_right_2d = CoordinatePlaneConfig.transform_point_with_plane(handle_right_local, optimal_plane)
        else:
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

def _get_nurbs_points(spline, optimal_plane=None):
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
            
            # Transform using optimal plane or current plane configuration
            if optimal_plane:
                co_2d = CoordinatePlaneConfig.transform_point_with_plane(co_local, optimal_plane)
            else:
                co_2d = CoordinatePlaneConfig.transform_point(co_local)
            points.append(co_2d)
    
    return points

def _get_poly_points(spline, optimal_plane=None):
    """Extract points from Poly spline using local coordinates and coordinate plane configuration."""
    points = []
    
    for point in spline.points:
        # Use LOCAL coordinates directly (point.co is a 4D vector)
        co_local = point.co
        
        # Transform using optimal plane or current plane configuration
        if optimal_plane:
            co_2d = CoordinatePlaneConfig.transform_point_with_plane(co_local, optimal_plane)
        else:
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

def _calculate_curve_bounding_box(curve_obj, use_optimal_plane=True):
    """
    Calculate the 2D bounding box of a curve object using coordinate plane configuration.
    
    Args:
        curve_obj: Blender curve object
        use_optimal_plane (bool): Whether to use optimal plane detection
        
    Returns:
        dict: Dictionary with min_x, max_x, min_y, max_y, width, height
    """
    try:
        # Use optimal plane if requested
        if use_optimal_plane:
            optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_object(curve_obj)
            if confidence > 0.1:  # Only use if confidence is reasonable
                # Get bounds for the optimal plane
                bounds_3d = _get_object_bounds_3d(curve_obj)
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
        bounds_3d = _get_object_bounds_3d(curve_obj)
        return CoordinatePlaneConfig.get_bounds_for_plane(bounds_3d)
        
    except Exception as e:
        print(f"Error calculating bounding box for {curve_obj.name}: {e}")
        return {'min_x': 0, 'max_x': 100, 'min_y': 0, 'max_y': 100, 'width': 100, 'height': 100}

def _calculate_all_splines_bounding_boxes(curve_obj, use_optimal_plane=True):
    """
    Calculate bounding boxes for all splines in a curve object.
    
    Args:
        curve_obj: Blender curve object
        use_optimal_plane (bool): Whether to use optimal plane detection
        
    Returns:
        list: List of bounding box dictionaries for each spline
    """
    spline_bounds = []
    
    try:
        curve_data = curve_obj.data
        
        for spline in curve_data.splines:
            bounds = _calculate_spline_bounding_box(spline, use_optimal_plane)
            spline_bounds.append(bounds)
            
    except Exception as e:
        print(f"Error calculating spline bounds for {curve_obj.name}: {e}")
    
    return spline_bounds

def _calculate_spline_bounding_box(spline, use_optimal_plane=True):
    """
    Calculate the 2D bounding box of a single spline using coordinate plane configuration.
    
    Args:
        spline: Blender spline object
        use_optimal_plane (bool): Whether to use optimal plane detection
        
    Returns:
        dict: Dictionary with min_x, max_x, min_y, max_y, width, height
    """
    try:
        # Detect optimal plane for this spline if requested
        optimal_plane = None
        if use_optimal_plane:
            optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_spline(spline)
            if confidence > 0.1:  # Only use if confidence is reasonable
                print(f"    Using optimal plane {optimal_plane} for spline (confidence: {confidence:.2f})")
            else:
                optimal_plane = None  # Fall back to current plane
        
        points_2d = []
        
        # Get 2D points based on spline type
        if spline.type == 'BEZIER':
            bezier_points = _get_bezier_points(spline, optimal_plane)
            for point in bezier_points:
                points_2d.append(point['co'])
                points_2d.append(point['handle_left'])
                points_2d.append(point['handle_right'])
                
        elif spline.type == 'NURBS':
            points_2d = _get_nurbs_points(spline, optimal_plane)
            
        elif spline.type == 'POLY':
            points_2d = _get_poly_points(spline, optimal_plane)
        
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
#--------------------------------------------------------------------------------------------------------------
def _convert_mesh_to_svg_path(mesh_obj, separate_components=False, optimal_plane=None):
    """
    Convert a Blender mesh object (vertices only) to SVG path data.
    
    Args:
        mesh_obj: Blender mesh object
        separate_components: If True, return separate paths for each connected component
        optimal_plane: Optional plane name to use for transformation
        
    Returns:
        str or list: SVG path data string (combined) or list of strings (separated)
    """
    try:
        # Get mesh data
        mesh_data = mesh_obj.data
        
        if not mesh_data.vertices:
            print(f"No vertices found in mesh {mesh_obj.name}")
            return None if not separate_components else []
        
        # Convert vertices to 2D points using coordinate plane configuration
        vertices_2d = []
        for vertex in mesh_data.vertices:
            # Use LOCAL coordinates directly
            co_local = vertex.co
            
            # Transform using optimal plane or current plane configuration
            if optimal_plane:
                co_2d = CoordinatePlaneConfig.transform_point_with_plane(co_local, optimal_plane)
            else:
                co_2d = CoordinatePlaneConfig.transform_point(co_local)
            vertices_2d.append(co_2d)
        
        if separate_components and mesh_data.edges:
            # Create separate paths for each connected component
            return _create_separated_mesh_paths(vertices_2d, mesh_data.edges)
        else:
            # Create single combined path (original behavior)
            if mesh_data.edges:
                path_commands = _create_mesh_edge_path(vertices_2d, mesh_data.edges)
            else:
                path_commands = _create_mesh_vertex_path(vertices_2d)
            
            if not path_commands:
                return None if not separate_components else []
            
            return " ".join(path_commands) if not separate_components else [" ".join(path_commands)]
        
    except Exception as e:
        print(f"Error converting mesh {mesh_obj.name}: {e}")
        return None if not separate_components else []

def _create_separated_mesh_paths(vertices_2d, edges):
    """
    Create separate SVG paths for each connected component in the mesh.
    
    Args:
        vertices_2d: List of 2D vertex coordinates
        edges: Mesh edges data
        
    Returns:
        list: List of SVG path strings, one for each connected component
    """
    if not vertices_2d or not edges:
        return []
    
    # Group connected edges into separate components
    edge_connections = {}
    for edge in edges:
        v1, v2 = edge.vertices
        if v1 not in edge_connections:
            edge_connections[v1] = []
        if v2 not in edge_connections:
            edge_connections[v2] = []
        edge_connections[v1].append(v2)
        edge_connections[v2].append(v1)
    
    # Find all connected components
    visited_vertices = set()
    separate_paths = []
    
    for start_vertex in range(len(vertices_2d)):
        if start_vertex in visited_vertices or start_vertex not in edge_connections:
            continue
        
        # Find all vertices in this connected component
        component_vertices = _find_connected_component(start_vertex, edge_connections, visited_vertices)
        
        if component_vertices:
            # Create path for this component
            component_path_commands = []
            
            # Start with first vertex in component
            first_vertex = component_vertices[0]
            component_path_commands.append(f"M {vertices_2d[first_vertex][0]:.3f},{vertices_2d[first_vertex][1]:.3f}")
            
            # Connect all vertices in the component following edges
            component_visited = {first_vertex}
            current_vertex = first_vertex
            
            while len(component_visited) < len(component_vertices):
                # Find next unvisited connected vertex in this component
                next_vertex = None
                for connected_vertex in edge_connections.get(current_vertex, []):
                    if connected_vertex in component_vertices and connected_vertex not in component_visited:
                        next_vertex = connected_vertex
                        break
                
                if next_vertex is not None:
                    component_path_commands.append(f"L {vertices_2d[next_vertex][0]:.3f},{vertices_2d[next_vertex][1]:.3f}")
                    component_visited.add(next_vertex)
                    current_vertex = next_vertex
                else:
                    # No more connected vertices, find any unvisited vertex in component to continue
                    remaining_vertices = set(component_vertices) - component_visited
                    if remaining_vertices:
                        next_vertex = next(iter(remaining_vertices))
                        component_path_commands.append(f"M {vertices_2d[next_vertex][0]:.3f},{vertices_2d[next_vertex][1]:.3f}")
                        component_visited.add(next_vertex)
                        current_vertex = next_vertex
                    else:
                        break
            
            if component_path_commands:
                separate_paths.append(" ".join(component_path_commands))
    
    return separate_paths

def _find_connected_component(start_vertex, edge_connections, visited_vertices):
    """
    Find all vertices in the connected component containing start_vertex.
    
    Args:
        start_vertex: Starting vertex index
        edge_connections: Dictionary mapping vertex indices to connected vertices
        visited_vertices: Set of globally visited vertices (will be updated)
        
    Returns:
        list: List of vertex indices in this connected component
    """
    if start_vertex in visited_vertices:
        return []
    
    component = []
    queue = [start_vertex]
    component_visited = set()
    
    while queue:
        current_vertex = queue.pop(0)
        if current_vertex in component_visited:
            continue
            
        component_visited.add(current_vertex)
        visited_vertices.add(current_vertex)
        component.append(current_vertex)
        
        # Add all connected vertices to queue
        for connected_vertex in edge_connections.get(current_vertex, []):
            if connected_vertex not in component_visited:
                queue.append(connected_vertex)
    
    return component

def _calculate_mesh_component_bounding_boxes(mesh_obj, optimal_plane=None):
    """
    Calculate bounding boxes for each connected component in a mesh object.
    
    Args:
        mesh_obj: Blender mesh object
        optimal_plane: Optional plane name to use for transformation
        
    Returns:
        list: List of bounding box dictionaries for each component
    """
    component_bounds = []
    
    try:
        mesh_data = mesh_obj.data
        
        if not mesh_data.vertices:
            return component_bounds
        
        # Convert vertices to 2D points
        vertices_2d = []
        for vertex in mesh_data.vertices:
            co_local = vertex.co
            
            # Transform using optimal plane or current plane configuration
            if optimal_plane:
                co_2d = CoordinatePlaneConfig.transform_point_with_plane(co_local, optimal_plane)
            else:
                co_2d = CoordinatePlaneConfig.transform_point(co_local)
            vertices_2d.append(co_2d)
        
        if mesh_data.edges:
            # Group edges into connected components
            edge_connections = {}
            for edge in mesh_data.edges:
                v1, v2 = edge.vertices
                if v1 not in edge_connections:
                    edge_connections[v1] = []
                if v2 not in edge_connections:
                    edge_connections[v2] = []
                edge_connections[v1].append(v2)
                edge_connections[v2].append(v1)
            
            # Find connected components and calculate bounds for each
            visited_vertices = set()
            
            for start_vertex in range(len(vertices_2d)):
                if start_vertex in visited_vertices or start_vertex not in edge_connections:
                    continue
                
                component_vertices = _find_connected_component(start_vertex, edge_connections, visited_vertices)
                
                if component_vertices:
                    # Calculate bounds for this component
                    component_points = [vertices_2d[v] for v in component_vertices]
                    if component_points:
                        min_x = min(point[0] for point in component_points)
                        max_x = max(point[0] for point in component_points)
                        min_y = min(point[1] for point in component_points)
                        max_y = max(point[1] for point in component_points)
                        
                        component_bounds.append({
                            'min_x': min_x,
                            'max_x': max_x,
                            'min_y': min_y,
                            'max_y': max_y,
                            'width': max_x - min_x,
                            'height': max_y - min_y
                        })
        else:
            # No edges, treat whole mesh as one component
            component_bounds.append(_calculate_mesh_bounding_box(mesh_obj, use_optimal_plane=(optimal_plane is not None)))
            
    except Exception as e:
        print(f"Error calculating mesh component bounds for {mesh_obj.name}: {e}")
    
    return component_bounds

def _create_mesh_edge_path(vertices_2d, edges):
    """
    Create SVG path from mesh vertices connected by edges.
    
    Args:
        vertices_2d: List of 2D vertex coordinates
        edges: Mesh edges data
        
    Returns:
        list: List of SVG path command strings
    """
    if not vertices_2d or not edges:
        return []
    
    path_commands = []
    processed_edges = set()
    
    # Group connected edges into paths
    edge_connections = {}
    for edge in edges:
        v1, v2 = edge.vertices
        if v1 not in edge_connections:
            edge_connections[v1] = []
        if v2 not in edge_connections:
            edge_connections[v2] = []
        edge_connections[v1].append(v2)
        edge_connections[v2].append(v1)
    
    # Find connected components
    visited_vertices = set()
    
    for start_vertex in range(len(vertices_2d)):
        if start_vertex in visited_vertices or start_vertex not in edge_connections:
            continue
        
        # Trace connected path from this vertex
        current_path = _trace_connected_path(start_vertex, edge_connections, visited_vertices, vertices_2d)
        
        if current_path:
            # Add this path to commands
            if path_commands:  # Not the first path, so we need to move to start a new subpath
                path_commands.append(f"M {current_path[0][0]:.3f},{current_path[0][1]:.3f}")
            else:
                path_commands.append(f"M {current_path[0][0]:.3f},{current_path[0][1]:.3f}")
            
            for point in current_path[1:]:
                path_commands.append(f"L {point[0]:.3f},{point[1]:.3f}")
    
    return path_commands

def _trace_connected_path(start_vertex, edge_connections, visited_vertices, vertices_2d):
    """
    Trace a connected path of vertices starting from start_vertex.
    
    Args:
        start_vertex: Starting vertex index
        edge_connections: Dictionary mapping vertex indices to connected vertices
        visited_vertices: Set of already visited vertices
        vertices_2d: List of 2D vertex coordinates
        
    Returns:
        list: List of 2D points forming the path
    """
    if start_vertex in visited_vertices:
        return []
    
    path = []
    current_vertex = start_vertex
    visited_vertices.add(current_vertex)
    path.append(vertices_2d[current_vertex])
    
    # Follow the connected edges
    while current_vertex in edge_connections:
        # Find next unvisited connected vertex
        next_vertex = None
        for connected_vertex in edge_connections[current_vertex]:
            if connected_vertex not in visited_vertices:
                next_vertex = connected_vertex
                break
        
        if next_vertex is None:
            break  # No more unvisited connections
        
        visited_vertices.add(next_vertex)
        path.append(vertices_2d[next_vertex])
        current_vertex = next_vertex
    
    return path

def _create_mesh_vertex_path(vertices_2d):
    """
    Create SVG path from mesh vertices (no edge information).
    Connects vertices in order or creates individual points.
    
    Args:
        vertices_2d: List of 2D vertex coordinates
        
    Returns:
        list: List of SVG path command strings
    """
    if not vertices_2d:
        return []
    
    path_commands = []
    
    if len(vertices_2d) == 1:
        # Single point - create a small circle
        x, y = vertices_2d[0]
        path_commands.append(f"M {x:.3f},{y:.3f}")
        path_commands.append(f"m -2,0")
        path_commands.append(f"a 2,2 0 1,0 4,0")
        path_commands.append(f"a 2,2 0 1,0 -4,0")
    elif len(vertices_2d) == 2:
        # Two points - create line
        path_commands.append(f"M {vertices_2d[0][0]:.3f},{vertices_2d[0][1]:.3f}")
        path_commands.append(f"L {vertices_2d[1][0]:.3f},{vertices_2d[1][1]:.3f}")
    else:
        # Multiple points - connect in order
        path_commands.append(f"M {vertices_2d[0][0]:.3f},{vertices_2d[0][1]:.3f}")
        for point in vertices_2d[1:]:
            path_commands.append(f"L {point[0]:.3f},{point[1]:.3f}")
    
    return path_commands

def _calculate_mesh_bounding_box(mesh_obj, use_optimal_plane=True):
    """
    Calculate the 2D bounding box of a mesh object using coordinate plane configuration.
    
    Args:
        mesh_obj: Blender mesh object
        use_optimal_plane (bool): Whether to use optimal plane detection
        
    Returns:
        dict: Dictionary with min_x, max_x, min_y, max_y, width, height
    """
    try:
        # Use optimal plane if requested
        if use_optimal_plane:
            optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_mesh(mesh_obj)
            if confidence > 0.1:  # Only use if confidence is reasonable
                # Get bounds for the optimal plane using detailed vertex analysis
                mesh_data = mesh_obj.data
                if mesh_data.vertices:
                    # Analyze actual vertices instead of object bounding box
                    points_3d = [vertex.co for vertex in mesh_data.vertices]
                    
                    min_x = min(point.x for point in points_3d)
                    max_x = max(point.x for point in points_3d)
                    min_y = min(point.y for point in points_3d)
                    max_y = max(point.y for point in points_3d)
                    min_z = min(point.z for point in points_3d)
                    max_z = max(point.z for point in points_3d)
                    
                    bounds_3d = {
                        'min_x': min_x, 'max_x': max_x,
                        'min_y': min_y, 'max_y': max_y,
                        'min_z': min_z, 'max_z': max_z
                    }
                else:
                    # Fallback to object bounds if no vertices
                    bounds_3d = _get_object_bounds_3d(mesh_obj)
                
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
        bounds_3d = _get_object_bounds_3d(mesh_obj)
        return CoordinatePlaneConfig.get_bounds_for_plane(bounds_3d)
    except Exception as e:
        print(f"Error calculating bounding box for mesh {mesh_obj.name}: {e}")
        return {'min_x': 0, 'max_x': 100, 'min_y': 0, 'max_y': 100, 'width': 100, 'height': 100}

def _generate_mesh_component_unique_id(tab_name, existing_ids, mesh_name, component_idx, button_index):
    """Generate a unique ID for mesh component buttons"""
    clean_mesh_name = "".join(c for c in mesh_name if c.isalnum() or c in "_-").lower()
    
    base_patterns = [
        f"{tab_name}_{clean_mesh_name}_comp_{component_idx:03d}",
        f"{tab_name}_{clean_mesh_name}_{component_idx:03d}",
        f"{tab_name}_mesh_comp_{button_index:03d}",
        f"{tab_name}_button_{len(existing_ids)+button_index+1:03d}"
    ]
    
    for base_pattern in base_patterns:
        if base_pattern not in existing_ids:
            return base_pattern
        
        counter = 1
        while counter < 1000:
            candidate_id = f"{base_pattern}_{counter:03d}"
            if candidate_id not in existing_ids:
                return candidate_id
            counter += 1
    
    import time
    return f"{tab_name}_mesh_comp_{int(time.time() * 1000)}_{button_index}"
    
def _generate_mesh_unique_id(tab_name, existing_ids, mesh_name, button_index):
    """Generate a unique ID for mesh-created buttons"""
    # Clean mesh name for use in ID
    clean_mesh_name = "".join(c for c in mesh_name if c.isalnum() or c in "_-").lower()
    
    base_patterns = [
        f"{tab_name}_{clean_mesh_name}",
        f"{tab_name}_{clean_mesh_name}_mesh",
        f"{tab_name}_mesh_{button_index:03d}",
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
    timestamp_id = f"{tab_name}_mesh_{int(time.time() * 1000)}_{button_index}"
    return timestamp_id
#--------------------------------------------------------------------------------------------------------------
def _get_selected_bones_with_shapes():
    """Get selected bones that have custom bone shapes assigned."""
    bones_with_shapes = []
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        # Check if we're in pose mode with an armature selected
        if bpy.context.mode == 'POSE':
            armature_obj = bpy.context.active_object
            if armature_obj and armature_obj.type == 'ARMATURE':
                for bone in bpy.context.selected_pose_bones:
                    if bone.custom_shape:
                        bones_with_shapes.append((bone, bone.custom_shape, armature_obj))
        
        # Also check if we have armature objects selected and look at their bones
        elif bpy.context.mode == 'OBJECT':
            for obj in bpy.context.selected_objects:
                if obj.type == 'ARMATURE':
                    # In object mode, we'll check all bones with custom shapes
                    for bone in obj.pose.bones:
                        if bone.custom_shape:
                            bones_with_shapes.append((bone, bone.custom_shape, obj))
    
    return bones_with_shapes

def _convert_bone_shape_to_svg_path(bone, custom_shape_obj, armature_obj):
    """Convert a bone's custom shape object to SVG path data."""
    try:
        # Determine if the custom shape is a curve or mesh
        if custom_shape_obj.type == 'CURVE':
            return _convert_curve_to_svg_path(custom_shape_obj)
        elif custom_shape_obj.type == 'MESH':
            # Check if it's a vertex-only mesh
            if not custom_shape_obj.data.polygons:
                return _convert_mesh_to_svg_path(custom_shape_obj)
            else:
                print(f"Bone shape {custom_shape_obj.name} is a mesh with faces, skipping")
                return None
        else:
            print(f"Unsupported bone shape type: {custom_shape_obj.type}")
            return None
    except Exception as e:
        print(f"Error converting bone shape {custom_shape_obj.name}: {e}")
        return None

def _calculate_bone_shape_bounding_box(bone, custom_shape_obj, armature_obj):
    """Calculate the 2D bounding box of a bone's custom shape."""
    try:
        if custom_shape_obj.type == 'CURVE':
            return _calculate_curve_bounding_box(custom_shape_obj)
        elif custom_shape_obj.type == 'MESH':
            return _calculate_mesh_bounding_box(custom_shape_obj)
        else:
            return {'min_x': 0, 'max_x': 50, 'min_y': 0, 'max_y': 50, 'width': 50, 'height': 50}
    except Exception as e:
        print(f"Error calculating bone shape bounding box for {custom_shape_obj.name}: {e}")
        return {'min_x': 0, 'max_x': 50, 'min_y': 0, 'max_y': 50, 'width': 50, 'height': 50}

def _generate_bone_shape_unique_id(tab_name, existing_ids, bone_name, shape_name, button_index):
    """Generate a unique ID for bone shape buttons"""
    clean_bone_name = "".join(c for c in bone_name if c.isalnum() or c in "_-").lower()
    clean_shape_name = "".join(c for c in shape_name if c.isalnum() or c in "_-").lower()
    
    base_patterns = [
        f"{tab_name}_{clean_bone_name}_{clean_shape_name}",
        f"{tab_name}_bone_{clean_bone_name}",
        f"{tab_name}_bone_shape_{button_index:03d}",
        f"{tab_name}_button_{len(existing_ids)+button_index+1:03d}"
    ]
    
    for base_pattern in base_patterns:
        if base_pattern not in existing_ids:
            return base_pattern
        
        counter = 1
        while counter < 1000:
            candidate_id = f"{base_pattern}_{counter:03d}"
            if candidate_id not in existing_ids:
                return candidate_id
            counter += 1
    
    import time
    return f"{tab_name}_bone_shape_{int(time.time() * 1000)}_{button_index}"

def detect_flat_plane_from_curves_simple():
    """Simple wrapper for backward compatibility."""
    return CoordinatePlaneConfig.detect_flat_plane_from_curves([], [], [])[0]

def test_enhanced_plane_detection():
    """Test the enhanced plane detection with multiple objects."""
    print("=== Testing Enhanced Plane Detection ===")
    
    # Get selected objects
    selected_curves = []
    selected_meshes = []
    
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        for obj in bpy.context.selected_objects:
            if obj.type == 'CURVE':
                selected_curves.append(obj)
            elif obj.type == 'MESH':
                mesh_data = obj.data
                if not mesh_data.polygons:  # No faces
                    selected_meshes.append(obj)
    
    selected_bone_shapes = _get_selected_bones_with_shapes()
    
    if not selected_curves and not selected_meshes and not selected_bone_shapes:
        print("No valid objects selected for testing")
        return
    
    # Test global detection
    print("\n--- Global Plane Detection ---")
    detected_plane, confidence, analysis = CoordinatePlaneConfig.detect_flat_plane_from_curves(
        selected_curves, selected_meshes, selected_bone_shapes
    )
    print(f"Global detected plane: {detected_plane} (confidence: {confidence:.2f})")
    if analysis:
        print(f"Global analysis: {analysis['description']}")
    
    # Test per-object detection
    print("\n--- Per-Object Plane Detection ---")
    for curve_obj in selected_curves:
        optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_object(curve_obj)
        print(f"Curve {curve_obj.name}: {optimal_plane} (confidence: {confidence:.2f})")
        if analysis:
            print(f"  Analysis: {analysis['description']}")
    
    for mesh_obj in selected_meshes:
        optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_object(mesh_obj)
        print(f"Mesh {mesh_obj.name}: {optimal_plane} (confidence: {confidence:.2f})")
        if analysis:
            print(f"  Analysis: {analysis['description']}")
    
    for bone, shape_obj, armature_obj in selected_bone_shapes:
        optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_object(shape_obj)
        print(f"Bone shape {bone.name} -> {shape_obj.name}: {optimal_plane} (confidence: {confidence:.2f})")
        if analysis:
            print(f"  Analysis: {analysis['description']}")

def test_per_spline_plane_detection():
    """Test per-spline plane detection."""
    print("=== Testing Per-Spline Plane Detection ===")
    
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        for obj in bpy.context.selected_objects:
            if obj.type == 'CURVE':
                print(f"\n--- Curve: {obj.name} ---")
                curve_data = obj.data
                
                for spline_idx, spline in enumerate(curve_data.splines):
                    optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_spline(spline)
                    print(f"  Spline {spline_idx}: {optimal_plane} (confidence: {confidence:.2f})")
                    if analysis:
                        print(f"    Analysis: {analysis['description']}")

def test_per_spline_conversion():
    """Test per-spline conversion with optimal planes."""
    print("=== Testing Per-Spline Conversion with Optimal Planes ===")
    
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        for obj in bpy.context.selected_objects:
            if obj.type == 'CURVE':
                print(f"\n--- Curve: {obj.name} ---")
                curve_data = obj.data
                
                for spline_idx, spline in enumerate(curve_data.splines):
                    # Detect optimal plane
                    optimal_plane, confidence, analysis = CoordinatePlaneConfig.detect_optimal_plane_for_spline(spline)
                    print(f"  Spline {spline_idx}: {optimal_plane} (confidence: {confidence:.2f})")
                    
                    # Convert with optimal plane
                    svg_path_data = _convert_spline_to_svg_path(spline, optimal_plane)
                    if svg_path_data:
                        print(f"    Converted successfully with {optimal_plane} plane")
                        print(f"    Path commands: {len(svg_path_data)}")
                    else:
                        print(f"    Conversion failed")

#--------------------------------------------------------------------------------------------------------------
# Context menu integration
def create_buttons_from_blender_curves_context_menu(self):
    """Context menu action to create buttons from selected Blender curves"""
    scene_pos = self.get_center_position()  # Use canvas center
    create_buttons_from_blender_curves(self, scene_pos)

def create_buttons_from_blender_curves_with_plane_selector(self):
    """Context menu action to create buttons with plane selector dialog"""
    scene_pos = self.get_center_position()
    create_buttons_from_blender_curves(self, scene_pos, show_plane_selector=True)
#--------------------------------------------------------------------------------------------------------------
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
#--------------------------------------------------------------------------------------------------------------
# Blender operator for easy integration
class CURVE_OT_to_picker_buttons(bpy.types.Operator):
    """Convert selected curves and meshes to picker buttons"""
    bl_idname = "curve.to_picker_buttons"
    bl_label = "Curves/Meshes to Picker Buttons"
    bl_description = "Convert selected curve objects and mesh objects (vertices only) to picker buttons"
    bl_options = {'REGISTER', 'UNDO'}
    
    show_plane_selector: bpy.props.BoolProperty(
        name="Show Plane Selector",
        description="Show coordinate plane selector dialog",
        default=False
    )
    
    @classmethod
    def poll(cls, context):
        valid_objects = []
        
        # Check for curve and mesh objects
        for obj in context.selected_objects:
            if obj.type == 'CURVE':
                valid_objects.append(obj)
            elif obj.type == 'MESH' and not obj.data.polygons:  # Mesh without faces
                valid_objects.append(obj)
        
        # Check for bones with custom shapes
        bones_with_shapes = _get_selected_bones_with_shapes()
        if bones_with_shapes:
            valid_objects.extend(bones_with_shapes)
        
        return len(valid_objects) > 0
    
    def execute(self, context):
        print("Converting curves and meshes to picker buttons...")
        
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
#--------------------------------------------------------------------------------------------------------------
# Registration for Blender
def register():
    bpy.utils.register_class(CURVE_OT_to_picker_buttons)
    bpy.utils.register_class(CURVE_OT_set_coordinate_plane)

def unregister():
    bpy.utils.unregister_class(CURVE_OT_to_picker_buttons)
    bpy.utils.unregister_class(CURVE_OT_set_coordinate_plane)

def test_mesh_plane_detection_comparison():
    """Test and compare old vs new mesh plane detection methods."""
    print("=== Testing Mesh Plane Detection: Object Bounds vs Vertex Analysis ===")
    
    selected_meshes = []
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        for obj in bpy.context.selected_objects:
            if obj.type == 'MESH':
                mesh_data = obj.data
                if not mesh_data.polygons:  # No faces
                    selected_meshes.append(obj)
    
    if not selected_meshes:
        print("No valid mesh objects selected for testing")
        return
    
    for mesh_obj in selected_meshes:
        print(f"\n--- Mesh: {mesh_obj.name} ---")
        
        # Old method: Using object bounding box
        print("OLD METHOD (Object Bounds):")
        try:
            old_plane, old_confidence, old_analysis = CoordinatePlaneConfig.detect_optimal_plane_for_object(mesh_obj)
            print(f"  Detected plane: {old_plane} (confidence: {old_confidence:.2f})")
            if old_analysis:
                print(f"  Analysis: {old_analysis['description']}")
        except Exception as e:
            print(f"  Error: {e}")
        
        # New method: Using detailed vertex analysis
        print("NEW METHOD (Vertex Analysis):")
        try:
            new_plane, new_confidence, new_analysis = CoordinatePlaneConfig.detect_optimal_plane_for_mesh(mesh_obj)
            print(f"  Detected plane: {new_plane} (confidence: {new_confidence:.2f})")
            if new_analysis:
                print(f"  Analysis: {new_analysis['description']}")
        except Exception as e:
            print(f"  Error: {e}")
        
        # Compare results
        if old_plane == new_plane:
            print(f"  RESULT: Both methods agree on {old_plane}")
        else:
            print(f"  RESULT: Methods disagree! Old: {old_plane}, New: {new_plane}")
            confidence_diff = new_confidence - old_confidence
            if confidence_diff > 0.1:
                print(f"  New method has {confidence_diff:.2f} higher confidence - likely more accurate")
            elif confidence_diff < -0.1:
                print(f"  Old method has {-confidence_diff:.2f} higher confidence")
            else:
                print(f"  Similar confidence levels (diff: {confidence_diff:.2f})")

def test_detailed_vertex_bounds_vs_object_bounds():
    """Compare bounds calculation between object bounding box and actual vertex analysis."""
    print("=== Testing Bounds Calculation: Object Bounds vs Vertex Bounds ===")
    
    selected_meshes = []
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        for obj in bpy.context.selected_objects:
            if obj.type == 'MESH':
                mesh_data = obj.data
                if not mesh_data.polygons:  # No faces
                    selected_meshes.append(obj)
    
    if not selected_meshes:
        print("No valid mesh objects selected for testing")
        return
    
    for mesh_obj in selected_meshes:
        print(f"\n--- Mesh: {mesh_obj.name} ---")
        
        # Object bounds method
        print("OBJECT BOUNDS:")
        obj_bounds = _get_object_bounds_3d(mesh_obj)
        print(f"  X: {obj_bounds['min_x']:.3f} to {obj_bounds['max_x']:.3f} (width: {obj_bounds['width']:.3f})")
        print(f"  Y: {obj_bounds['min_y']:.3f} to {obj_bounds['max_y']:.3f} (height: {obj_bounds['height']:.3f})")
        print(f"  Z: {obj_bounds['min_z']:.3f} to {obj_bounds['max_z']:.3f} (depth: {obj_bounds['depth']:.3f})")
        
        # Vertex bounds method
        print("VERTEX BOUNDS:")
        mesh_data = mesh_obj.data
        if mesh_data.vertices:
            points_3d = [vertex.co for vertex in mesh_data.vertices]
            
            min_x = min(point.x for point in points_3d)
            max_x = max(point.x for point in points_3d)
            min_y = min(point.y for point in points_3d)
            max_y = max(point.y for point in points_3d)
            min_z = min(point.z for point in points_3d)
            max_z = max(point.z for point in points_3d)
            
            width = max_x - min_x
            height = max_y - min_y
            depth = max_z - min_z
            
            print(f"  X: {min_x:.3f} to {max_x:.3f} (width: {width:.3f})")
            print(f"  Y: {min_y:.3f} to {max_y:.3f} (height: {height:.3f})")
            print(f"  Z: {min_z:.3f} to {max_z:.3f} (depth: {depth:.3f})")
            
            # Compare differences
            width_diff = abs(width - obj_bounds['width'])
            height_diff = abs(height - obj_bounds['height'])
            depth_diff = abs(depth - obj_bounds['depth'])
            
            print("DIFFERENCES:")
            print(f"  Width diff: {width_diff:.3f}")
            print(f"  Height diff: {height_diff:.3f}")
            print(f"  Depth diff: {depth_diff:.3f}")
            
            if width_diff > 0.001 or height_diff > 0.001 or depth_diff > 0.001:
                print("  SIGNIFICANT DIFFERENCE DETECTED - Object bounds may be misleading!")
            else:
                print("  Bounds are very similar - both methods should work equally well")
        else:
            print("  No vertices found")

def _calculate_smart_layout_positions(button_bounds_list, drop_position, canvas_size=None, padding=20):
    """
    Calculate smart layout positions for multiple buttons to avoid overlapping.
    
    Args:
        button_bounds_list: List of dicts with 'width', 'height', 'center_x', 'center_y' for each button
        drop_position: QPointF where the layout should be centered
        canvas_size: Optional QSizeF of canvas for boundary checking
        padding: Padding between buttons
        
    Returns:
        List of QPointF positions for each button
    """
    if not button_bounds_list:
        return []
    
    if len(button_bounds_list) == 1:
        # Single button - center it at drop position
        bounds = button_bounds_list[0]
        return [QtCore.QPointF(
            drop_position.x() - bounds['width'] / 2,
            drop_position.y() - bounds['height'] / 2
        )]
    
    # Calculate total area needed
    total_width = sum(bounds['width'] for bounds in button_bounds_list) + padding * (len(button_bounds_list) - 1)
    max_height = max(bounds['height'] for bounds in button_bounds_list)
    
    # Try to arrange in a grid
    import math
    cols = math.ceil(math.sqrt(len(button_bounds_list)))
    rows = math.ceil(len(button_bounds_list) / cols)
    
    # Calculate grid dimensions
    col_widths = []
    for col in range(cols):
        col_start = col * rows
        col_end = min(col_start + rows, len(button_bounds_list))
        col_width = max(bounds['width'] for bounds in button_bounds_list[col_start:col_end])
        col_widths.append(col_width)
    
    grid_width = sum(col_widths) + padding * (cols - 1)
    grid_height = max_height * rows + padding * (rows - 1)
    
    # If grid is too wide, try single column
    if canvas_size and grid_width > canvas_size.width() * 0.8:
        cols = 1
        rows = len(button_bounds_list)
        grid_width = max(bounds['width'] for bounds in button_bounds_list)
        grid_height = sum(bounds['height'] for bounds in button_bounds_list) + padding * (rows - 1)
    
    # Calculate starting position to center the grid
    start_x = drop_position.x() - grid_width / 2
    start_y = drop_position.y() - grid_height / 2
    
    # Generate positions
    positions = []
    button_index = 0
    
    for row in range(rows):
        for col in range(cols):
            if button_index >= len(button_bounds_list):
                break
                
            bounds = button_bounds_list[button_index]
            
            # Calculate position for this button
            if cols == 1:
                # Single column layout
                x = start_x + (grid_width - bounds['width']) / 2
                y = start_y + sum(bounds['height'] + padding for bounds in button_bounds_list[:button_index])
            else:
                # Grid layout
                col_x = start_x + sum(col_widths[:col]) + padding * col
                x = col_x + (col_widths[col] - bounds['width']) / 2
                y = start_y + row * (max_height + padding)
            
            positions.append(QtCore.QPointF(x, y))
            button_index += 1
    
    return positions

def _get_button_bounds_for_layout(button_data):
    """
    Extract bounds information from button data for layout calculation.
    
    Args:
        button_data: Dict with button information including bounds
        
    Returns:
        Dict with 'width', 'height', 'center_x', 'center_y'
    """
    return {
        'width': button_data.get('width', 100),
        'height': button_data.get('height', 100),
        'center_x': button_data.get('center_x', 0),
        'center_y': button_data.get('center_y', 0)
    }

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

def test_smart_layout_feature():
    """Test the smart layout feature with multiple objects."""
    print("=== Testing Smart Layout Feature ===")
    
    # Get selected objects
    selected_curves = []
    selected_meshes = []
    
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        for obj in bpy.context.selected_objects:
            if obj.type == 'CURVE':
                selected_curves.append(obj)
            elif obj.type == 'MESH':
                mesh_data = obj.data
                if not mesh_data.polygons:  # No faces
                    selected_meshes.append(obj)
    
    total_objects = len(selected_curves) + len(selected_meshes)
    
    if total_objects < 2:
        print("Please select at least 2 curve or mesh objects to test smart layout")
        return
    
    print(f"Found {len(selected_curves)} curves and {len(selected_meshes)} meshes")
    print("Smart layout will arrange these in a grid instead of overlapping")
    
    # Show what would happen with and without smart layout
    print("\nWITHOUT smart layout:")
    print("  - All buttons would overlap at the same position")
    print("  - Only the last button would be visible")
    
    print("\nWITH smart layout:")
    print("  - Buttons arranged in a grid pattern")
    print("  - Each button visible and accessible")
    print("  - Automatic spacing and centering")
    
    print(f"\nExpected grid: {total_objects} buttons in a grid layout")