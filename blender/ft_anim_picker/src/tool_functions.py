#import maya.cmds as cmds
#import maya.mel as mel
#import maya.api.OpenMaya as om
#from maya import OpenMayaUI as omui
import bpy
from functools import wraps
import re
import json
from typing import List, Dict, Optional, Tuple, Any

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
from shiboken6 import wrapInstance

from . utils import undoable, shortcuts, get_icon
from . import custom_button as CB
from . import custom_slider as CS
from . import custom_dialog as CD
from . import blender_ui as UI
from . import blender_main as MAIN

class animation_tool_layout:
    def show_mirror_pose_dialog(self):
        """
        Shows a dialog to input custom naming conventions for left and right sides.
        This allows users to specify custom prefixes or suffixes for mirroring poses.
        """

        # Create custom dialog for mirror pose options
        manager = MAIN.PickerWindowManager.get_instance()
        parent = manager._picker_widgets[0] if manager._picker_widgets else None
        dialog = CD.CustomDialog(parent=parent, title="Mirror Pose Options", size=(250, 180))
        
        # Create form layout for the inputs
        form_layout = QtWidgets.QFormLayout()
        
        # Create input fields for left and right naming conventions
        left_input = QtWidgets.QLineEdit()
        left_input.setPlaceholderText("e.g., L_, left_, _L, _left")
        
        right_input = QtWidgets.QLineEdit()
        right_input.setPlaceholderText("e.g., R_, right_, _R, _right")
        
        # Add fields to form layout
        form_layout.addRow("Left Side Identifier:", left_input)
        form_layout.addRow("Right Side Identifier:", right_input)
        
        # Add explanation text
        explanation = QtWidgets.QLabel("Enter custom naming conventions for left and right sides. "
                                   "These will be used to identify and mirror objects between sides.")
        explanation.setWordWrap(True)
        
        # Create layout for the dialog
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addWidget(explanation)
        main_layout.addLayout(form_layout)
        
        # Add the layout to the dialog
        dialog.add_layout(main_layout)
        
        # Add buttons
        def apply_custom_mirror():
            # Get the values from the input fields
            left_value = left_input.text().strip()
            right_value = right_input.text().strip()
            
            # Validate inputs
            if not left_value or not right_value:
                manager = MAIN.PickerWindowManager.get_instance()
                parent = manager._picker_widgets[0] if manager._picker_widgets else None
                error_dialog = CD.CustomDialog(parent=parent, title="Error", size=(250, 100), info_box=True)
                error_label = QtWidgets.QLabel("Both left and right identifiers must be specified.")
                error_label.setWordWrap(True)
                error_dialog.add_widget(error_label)
                error_dialog.add_button_box()
                error_dialog.exec_()
                return
            
            # Call the apply_mirror_pose function with custom naming conventions
            apply_mirror_pose(L=left_value, R=right_value)
            
            # Close the dialog
            dialog.accept()
        
        # Add apply and cancel buttons
        button_box = QtWidgets.QDialogButtonBox()
        apply_button = button_box.addButton("Apply", QtWidgets.QDialogButtonBox.AcceptRole)
        cancel_button = button_box.addButton("Cancel", QtWidgets.QDialogButtonBox.RejectRole)
        
        # Connect button signals
        apply_button.clicked.connect(apply_custom_mirror)
        cancel_button.clicked.connect(dialog.reject)
        
        # Add button box to dialog
        dialog.add_widget(button_box)
        
        # Show the dialog
        dialog.exec_()
    
    def __init__(self):
        self.layout = QtWidgets.QVBoxLayout()
        lm = 1 # layout margin
        self.layout.setContentsMargins(lm, lm, lm, lm)
        self.layout.setSpacing(lm)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        self.tools_scroll_frame = QtWidgets.QFrame()
        self.tools_scroll_frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.tools_scroll_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray; border-radius: 3px; background-color: rgba(36, 36, 36, 0);}}''')
        #self.tools_scroll_frame.setFixedHeight(24)
        self.tools_scroll_frame_layout = QtWidgets.QVBoxLayout(self.tools_scroll_frame)
        self.tools_scroll_frame_layout.setContentsMargins(0, 0, 0, 0)
        self.tools_scroll_frame_layout.setSpacing(0)

        self.tools_scroll_area = CS.HorizontalScrollArea()
        self.tools_scroll_area.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.tools_scroll_area.setFixedHeight(22)
        self.tools_scroll_area.setWidgetResizable(True)
        
        self.tools_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tools_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.tools_scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:horizontal {
                border: none;
                background: transparent;
                height: 8px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(100, 100, 100, 0.5);
                min-width: 20px;
                border-radius: 0px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """)
        self.tools_scroll_area.setWidget(self.tools_scroll_frame)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        self.col1 = QtWidgets.QHBoxLayout()
        self.col1.setSpacing(5)
        self.col2 = QtWidgets.QHBoxLayout()
        self.col2.setSpacing(4)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        ts = 11 # text size
        bh = 20 # button height
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        reset_transform_button = CB.CustomButton(text='Reset', icon=':delete.png', color='#222222', size=14, tooltip="Resets the object transform to Origin.",
                                                 text_size=ts, height=bh,ContextMenu=True, onlyContext=False)
        reset_transform_button.addToMenu("Move", reset_move, icon='delete.png', position=(0,0))
        reset_transform_button.addToMenu("Rotate", reset_rotate, icon='delete.png', position=(1,0))
        reset_transform_button.addToMenu("Scale", reset_scale, icon='delete.png', position=(2,0))
        
        timeLine_key_button = CB.CustomButton(text='Key', color='#d62e22', tooltip="Sets key frame.",text_size=ts, height=bh)
        timeLine_delete_key_button = CB.CustomButton(text='Key', icon=get_icon('delete_white.png',opacity=0.8,size=12), color='#222222', size=14, tooltip="Deletes keys from the given start frame to the current frame.",text_size=ts, height=bh)
        timeLine_copy_key_button = CB.CustomButton(text='Copy', color='#293F64', tooltip="Copy selected key(s).",text_size=ts, height=bh)
        timeLine_paste_key_button = CB.CustomButton(text='Paste', color='#1699CA', tooltip="Paste copied key(s).",text_size=ts, height=bh)
        timeLine_pasteInverse_key_button = CB.CustomButton(text='Paste Inverse', color='#9416CA', tooltip="Paste Inverted copied keys(s).",text_size=ts, height=bh)
        
        mirror_pose_button = CB.CustomButton(text='Mirror Pose', color='#8A2BE2', tooltip="Mirror Pose: Apply the pose of selected objects to their mirrored counterparts.",
                                           text_size=ts, height=bh, ContextMenu=True)
        mirror_pose_button.addToMenu("Select Mirror", select_mirror_pose, icon=get_icon('select.png',size=16), position=(0,0))
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        reset_transform_button.singleClicked.connect(reset_all)

        timeLine_key_button.singleClicked.connect(set_key)
        timeLine_delete_key_button.singleClicked.connect(delete_keys)
        timeLine_copy_key_button.singleClicked.connect(copy_pose)
        timeLine_paste_key_button.singleClicked.connect(paste_pose)
        timeLine_pasteInverse_key_button.singleClicked.connect(paste_inverse_pose)
        
        mirror_pose_button.singleClicked.connect(mirror_selected_pose)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        self.col1.addWidget(reset_transform_button)

        self.col1.addSpacing(4)

        self.col1.addWidget(timeLine_key_button)
        self.col1.addWidget(timeLine_delete_key_button)
        self.col1.addWidget(timeLine_copy_key_button)
        self.col1.addWidget(timeLine_paste_key_button)
        self.col1.addWidget(timeLine_pasteInverse_key_button)
        self.col1.addWidget(mirror_pose_button)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
        self.tools_scroll_frame_layout.addLayout(self.col1)
        self.tools_scroll_frame_layout.addSpacing(2)
        self.tools_scroll_frame_layout.addLayout(self.col2)
        self.layout.addWidget(self.tools_scroll_area)
        #---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
#---------------------------------------------------------------------------------------------------------------
def reset_move():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        if bpy.context.mode == 'POSE':
            bpy.ops.pose.loc_clear()
        elif bpy.context.mode == 'OBJECT':
            bpy.ops.object.location_clear(clear_delta=False)

def reset_rotate():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        if bpy.context.mode == 'POSE':
            bpy.ops.pose.rot_clear()
        elif bpy.context.mode == 'OBJECT':
            bpy.ops.object.rotation_clear(clear_delta=False)

def reset_scale():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        if bpy.context.mode == 'POSE':
            bpy.ops.pose.scale_clear()
        elif bpy.context.mode == 'OBJECT':
            bpy.ops.object.scale_clear(clear_delta=False)

@undoable
def reset_all():
    '''with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        if bpy.context.mode == 'POSE':
            bpy.ops.pose.loc_clear()
            bpy.ops.pose.rot_clear()
            bpy.ops.pose.scale_clear()
        elif bpy.context.mode == 'OBJECT':
            bpy.ops.object.location_clear(clear_delta=False)
            bpy.ops.object.rotation_clear(clear_delta=False)
            bpy.ops.object.scale_clear(clear_delta=False)'''
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        active_object = bpy.context.view_layer.objects.active
        if bpy.context.mode == 'POSE':
            for bone in selected_bones():
                active_object.pose.bones[bone].location = (0, 0, 0)
                # Try different rotation methods
                try:
                    active_object.pose.bones[bone].rotation_euler = (0, 0, 0)
                except:
                    active_object.pose.bones[bone].rotation_quaternion = (1, 0, 0, 0)
                finally:
                    pass
                active_object.pose.bones[bone].scale = (1, 1, 1)
        elif bpy.context.mode == 'OBJECT':
            for obj in selected_objects():
                bpy.data.objects[obj].location = (0, 0, 0)
                # Try different rotation methods
                try:
                    bpy.data.objects[obj].rotation_euler = (0, 0, 0)
                except:
                    bpy.data.objects[obj].rotation_quaternion = (1, 0, 0, 0)
                finally:
                    pass
                bpy.data.objects[obj].scale = (1, 1, 1)
#---------------------------------------------------------------------------------------------------------------
def selected_objects():
    object_list = []
    selected_objects = []
    vl_objects = bpy.context.view_layer.objects.items()
    for object in vl_objects:
        object_list.append(object[0])

    for obj in object_list:
        if bpy.context.view_layer.objects[obj].select_get():
            selected_objects.append(obj)
    #print(selected_objects)
    return selected_objects

def selcected_bones_in_pose_mode():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        objects_in_pose_mode = []
        for obj in bpy.data.objects:
            if obj.type == 'ARMATURE' and obj.mode == 'POSE':
                objects_in_pose_mode.append(obj)
        
        selected_bones = []
        for obj in objects_in_pose_mode:
            for bone in obj.data.bones:
                if bone.select:
                    selected_bones.append(bone.name)
        return selected_bones

def deselect_all_selected_bones_in_pose_mode():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        selected_bones = selcected_bones_in_pose_mode()
        for bone in selected_bones:
            bpy.data.objects[bone].select_set(False)

def selected_bones():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        active_object = bpy.context.view_layer.objects.active
        if active_object.type == 'ARMATURE':
            selected_bones = [bone.name for bone in active_object.data.bones if bone.select]
            #print(selected_bones)
            return selected_bones
        else:
            #print("No active armature object.")
            return []

def active_object():
    return bpy.context.view_layer.objects.active
#---------------------------------------------------------------------------------------------------------------
def context_override(function, *args, **kwargs):
    """
    Universal context override that handles different operator requirements
    """
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        # Get the base window
        if not bpy.context.window_manager.windows:
            return
        
        window = bpy.context.window_manager.windows[0]
        
        # Find required areas
        view3d_area = None
        action_area = None
        
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                view3d_area = area
            elif area.type in ['DOPESHEET_EDITOR', 'GRAPH_EDITOR']:
                action_area = area
        
        # Determine which context is needed based on the operator
        operator_name = getattr(function, '__name__', str(function))
        
        # Check if it's an action operator
        if hasattr(function, '__self__') and hasattr(function.__self__, '__module__'):
            module_path = str(function.__self__.__module__) if hasattr(function.__self__, '__module__') else ""
            if 'action' in module_path.lower() or 'action' in operator_name.lower():
                use_action_context = True
            else:
                use_action_context = False
        else:
            # Fallback: check operator string representation
            op_str = str(function).lower()
            use_action_context = 'action' in op_str
        
        # Set up the appropriate context
        if use_action_context and action_area:
            # Use action editor context for action operators
            target_area = action_area
            region = None
            for r in target_area.regions:
                if r.type == 'WINDOW':
                    region = r
                    break
            if not region:
                region = target_area.regions[-1]
            
            context_dict = {
                'window': window,
                'area': target_area,
                'region': region,
                'screen': window.screen
            }
            
            # Add animation-specific context if available
            if bpy.context.active_object:
                context_dict['active_object'] = bpy.context.active_object
                if bpy.context.active_object.animation_data:
                    context_dict['active_action'] = bpy.context.active_object.animation_data.action
            
            if bpy.context.selected_objects:
                context_dict['selected_objects'] = bpy.context.selected_objects
                
        else:
            # Use 3D viewport context for other operators
            if not view3d_area:
                return
                
            target_area = view3d_area
            region = None
            for r in target_area.regions:
                if r.type == 'WINDOW':
                    region = r
                    break
            if not region:
                region = target_area.regions[-1]
            
            context_dict = {
                'window': window,
                'area': target_area,
                'region': region,
                'screen': window.screen
            }
            
            # Add object context
            
            if bpy.context.active_object:
                context_dict['active_object'] = bpy.context.active_object
            if bpy.context.selected_objects:
                context_dict['selected_objects'] = bpy.context.selected_objects
        
        # Execute with context override
        try:
            with bpy.context.temp_override(**context_dict):
                if args or kwargs:
                    return function(*args, **kwargs)
                else:
                    return function()
        except Exception as e:
            print(f"Context override failed: {e}")
            # Fallback: try without context override
            try:
                if args or kwargs:
                    return function(*args, **kwargs)
                else:
                    return function()
            except Exception as e2:
                print(f"Fallback execution also failed: {e2}")

def set_key():
    context_override(bpy.ops.anim.keyframe_insert)

def delete_keys():
    context_override(bpy.ops.action.delete)

def copy_pose():
    context_override(bpy.ops.action.copy)

def paste_pose():
    context_override(bpy.ops.action.paste)

def paste_inverse_pose():
    context_override(bpy.ops.action.paste, flipped=True)

def select_mirror_pose():
    context_override(bpy.ops.pose.select_mirror)
   
#---------------------------------------------------------------------------------------------------------------
def mirror_selected_pose(mirror_mode: str = 'auto',
                        axis: str = 'x',
                        select_mirrored: bool = True,
                        force_in_place: bool = False) -> Dict[str, Any]:
    """
    Mirror the pose of selected objects/bones to their counterparts.
    
    Args:
        mirror_mode: 'auto', 'objects', or 'bones' - determines what to mirror
        axis: 'x', 'y', or 'z' - axis to mirror across (default: 'x')
        select_mirrored: Whether to select the mirrored objects/bones after mirroring
        force_in_place: If True, always mirror in-place instead of to counterparts
        
    Returns:
        Dictionary containing results and statistics
    """
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        
        # Initialize results
        results = {
            'mirrored_objects': [],
            'mirrored_bones': [],
            'failed_objects': [],
            'failed_bones': [],
            'total_processed': 0,
            'success_count': 0,
            'error_count': 0,
            'messages': []
        }
        
        try:
            # Get current namespace from picker window
            namespace = _get_current_namespace()
            
            # Build object and mirror caches
            object_cache = _build_object_cache(namespace)
            mirror_cache = _build_mirror_cache(object_cache, namespace)
            
            # Get active object and context
            active_obj = bpy.context.view_layer.objects.active
            current_mode = getattr(bpy.context, 'mode', 'OBJECT')
            
            # Determine what to mirror based on mode and selection
            if mirror_mode == 'auto':
                if active_obj and active_obj.type == 'ARMATURE' and 'POSE' in current_mode:
                    mirror_mode = 'bones'
                else:
                    mirror_mode = 'objects'
            
            if mirror_mode == 'bones':
                # Mirror selected bones
                _mirror_selected_bones(active_obj, mirror_cache, axis, results, force_in_place)
            else:
                # Mirror selected objects
                _mirror_selected_objects(mirror_cache, axis, results, force_in_place)
            
            # Select mirrored items if requested
            if select_mirrored:
                _select_mirrored_items(results, mirror_mode)
                
            # Update results summary
            results['total_processed'] = len(results['mirrored_objects']) + len(results['mirrored_bones']) + len(results['failed_objects']) + len(results['failed_bones'])
            results['success_count'] = len(results['mirrored_objects']) + len(results['mirrored_bones'])
            results['error_count'] = len(results['failed_objects']) + len(results['failed_bones'])
            
            # Add summary message
            if results['success_count'] > 0:
                results['messages'].append(f"Successfully mirrored {results['success_count']} items")
            if results['error_count'] > 0:
                results['messages'].append(f"Failed to mirror {results['error_count']} items")
                
        except Exception as e:
            results['messages'].append(f"Error during mirror operation: {str(e)}")
            results['error_count'] += 1
        
        return results


def _get_current_namespace():
    """
    Get current namespace from the BlenderAnimPickerWindow.
    """
    try:
        from PySide6 import QtWidgets
        from . import blender_ui
        
        # Find the BlenderAnimPickerWindow instance
        for widget in QtWidgets.QApplication.allWidgets():
            if isinstance(widget, blender_ui.BlenderAnimPickerWindow):
                if hasattr(widget, 'namespace_dropdown'):
                    namespace = widget.namespace_dropdown.currentText()
                    return namespace if namespace != 'None' else None
                break
        
        # Fallback: try to find any widget with namespace_dropdown
        for widget in QtWidgets.QApplication.allWidgets():
            if hasattr(widget, 'namespace_dropdown'):
                namespace = widget.namespace_dropdown.currentText()
                return namespace if namespace != 'None' else None
                
    except Exception as e:
        print(f"Warning: Could not get namespace from picker window: {e}")
    
    # Default to None if no namespace found
    return None


def _build_object_cache(namespace: Optional[str]) -> Dict[str, Any]:
    """Build optimized object lookup cache with namespace support."""
    cache = {
        'exact': {},
        'namespace_prefix': {},
        'namespace_suffix': {},
        'partial': {},
        'by_type': {'ARMATURE': [], 'MESH': [], 'OTHER': []}
    }
    
    separators = ['_', '.']
    
    for obj in bpy.data.objects:
        name = obj.name
        
        # Store exact name
        cache['exact'][name] = obj
        
        # Store by type
        obj_type = 'ARMATURE' if obj.type == 'ARMATURE' else ('MESH' if obj.type == 'MESH' else 'OTHER')
        cache['by_type'][obj_type].append(obj)
        
        # Build namespace-aware cache
        if namespace:
            for sep in separators:
                prefix_pattern = f"{namespace}{sep}"
                if name.startswith(prefix_pattern):
                    base_name = name[len(prefix_pattern):]
                    cache['namespace_prefix'][base_name] = obj
                
                suffix_pattern = f"{sep}{namespace}"
                if name.endswith(suffix_pattern):
                    base_name = name[:-len(suffix_pattern)]
                    cache['namespace_suffix'][base_name] = obj
            
            if name == namespace:
                cache['namespace_prefix'][namespace] = obj
                cache['namespace_suffix'][namespace] = obj
        
        # Build partial match cache
        name_parts = name.lower().split('_') + name.lower().split('.')
        for part in name_parts:
            if part and len(part) > 2:
                if part not in cache['partial']:
                    cache['partial'][part] = []
                cache['partial'][part].append(obj)
    
    return cache


def _build_mirror_cache(object_cache: Dict[str, Any], namespace: Optional[str]) -> Dict[str, Any]:
    """Build mirror object lookup cache with namespace awareness."""
    mirror_cache = {}
    
    # Enhanced mirror patterns
    mirror_patterns = [
        # Suffix patterns
        ('_L', '_R'), ('_l', '_r'), ('.L', '.R'), ('.l', '.r'),
        ('Left', 'Right'), ('left', 'right'),
        ('_Left', '_Right'), ('_left', '_right'),
        ('.Left', '.Right'), ('.left', '.right'),
        # Prefix patterns
        ('L_', 'R_'), ('l_', 'r_'), ('L.', 'R.'), ('l.', 'r.'),
        ('Left_', 'Right_'), ('left_', 'right_'),
        ('Left.', 'Right.'), ('left.', 'right.')
    ]
    
    # Check exact matches first
    for obj_name, obj in object_cache['exact'].items():
        for left_pat, right_pat in mirror_patterns:
            mirror_name = None
            
            # Check suffix patterns
            if obj_name.endswith(left_pat):
                mirror_name = obj_name[:-len(left_pat)] + right_pat
            elif obj_name.endswith(right_pat):
                mirror_name = obj_name[:-len(right_pat)] + left_pat
            # Check prefix patterns
            elif obj_name.startswith(left_pat):
                mirror_name = right_pat + obj_name[len(left_pat):]
            elif obj_name.startswith(right_pat):
                mirror_name = left_pat + obj_name[len(right_pat):]
            # Check anywhere in name
            elif left_pat in obj_name:
                mirror_name = obj_name.replace(left_pat, right_pat)
            elif right_pat in obj_name:
                mirror_name = obj_name.replace(right_pat, left_pat)
            
            if mirror_name and mirror_name in object_cache['exact']:
                mirror_cache[obj_name] = object_cache['exact'][mirror_name]
                break
    
    # Check namespace-aware matches
    if namespace:
        for base_name, obj in object_cache['namespace_prefix'].items():
            for left_pat, right_pat in mirror_patterns:
                if left_pat in base_name:
                    mirror_base = base_name.replace(left_pat, right_pat)
                    if mirror_base in object_cache['namespace_prefix']:
                        mirror_cache[base_name] = object_cache['namespace_prefix'][mirror_base]
                        break
                elif right_pat in base_name:
                    mirror_base = base_name.replace(right_pat, left_pat)
                    if mirror_base in object_cache['namespace_prefix']:
                        mirror_cache[base_name] = object_cache['namespace_prefix'][mirror_base]
                        break
    
    return mirror_cache


def _mirror_selected_objects(mirror_cache: Dict[str, Any], 
                           axis: str, 
                           results: Dict[str, Any],
                           force_in_place: bool = False) -> None:
    """Mirror selected objects to their counterparts or in-place."""
    # Get namespace from picker window
    namespace = _get_current_namespace()
    selected_objects = bpy.context.view_layer.objects.selected
    
    for obj in selected_objects:
        try:
            mirror_obj = None
            
            # Only look for counterpart if not forcing in-place
            if not force_in_place:
                mirror_obj = _find_mirrored_object(obj.name, mirror_cache)
            
            if mirror_obj:
                # Capture current transform
                transform_data = _capture_object_transform(obj)
                
                # Mirror the transform
                mirrored_transform = _mirror_transform_data(transform_data, axis)
                
                # Apply mirrored transform
                _apply_object_transform(mirror_obj, mirrored_transform)
                
                results['mirrored_objects'].append({
                    'original': obj.name,
                    'mirrored': mirror_obj.name
                })
            else:
                # No counterpart found or forcing in-place, mirror the object in place
                transform_data = _capture_object_transform(obj)
                mirrored_transform = _mirror_transform_data(transform_data, axis)
                _apply_object_transform(obj, mirrored_transform)
                
                results['mirrored_objects'].append({
                    'original': obj.name,
                    'mirrored': obj.name + ' (in-place)'
                })
                
        except Exception as e:
            results['failed_objects'].append({
                'name': obj.name,
                'reason': str(e)
            })


def _mirror_selected_bones(armature_obj: bpy.types.Object,
                          mirror_cache: Dict[str, Any],
                          axis: str,
                          results: Dict[str, Any],
                          force_in_place: bool = False) -> None:
    """Mirror selected bones to their counterparts or in-place."""
    if not armature_obj or armature_obj.type != 'ARMATURE':
        return
    
    # Get namespace from picker window
    namespace = _get_current_namespace()
    
    try:
        # Get selected pose bones
        selected_pose_bones = []
        context_bones = getattr(bpy.context, 'selected_pose_bones', None)
        if context_bones:
            selected_pose_bones = list(context_bones)
        
        # Fallback: check bone selection manually
        if not selected_pose_bones and armature_obj.pose:
            for pose_bone in armature_obj.pose.bones:
                if pose_bone.bone.select:
                    selected_pose_bones.append(pose_bone)
        
        # Build bone mirror cache for this armature (only if not forcing in-place)
        bone_mirror_cache = {}
        if not force_in_place:
            for bone in armature_obj.pose.bones:
                mirrored_name = _get_mirrored_bone_name(bone.name)
                if mirrored_name and mirrored_name in armature_obj.pose.bones:
                    bone_mirror_cache[bone.name] = armature_obj.pose.bones[mirrored_name]
        
        # Mirror each selected bone
        for bone in selected_pose_bones:
            try:
                mirror_bone = None
                
                # Only look for counterpart if not forcing in-place
                if not force_in_place:
                    mirror_bone = bone_mirror_cache.get(bone.name)
                
                if mirror_bone:
                    # Capture current transform
                    transform_data = _capture_bone_transform(bone)
                    
                    # Mirror the transform
                    mirrored_transform = _mirror_transform_data(transform_data, axis)
                    
                    # Apply mirrored transform
                    _apply_bone_transform(mirror_bone, mirrored_transform)
                    
                    results['mirrored_bones'].append({
                        'original': bone.name,
                        'mirrored': mirror_bone.name,
                        'armature': armature_obj.name
                    })
                else:
                    # No counterpart found or forcing in-place, mirror the bone in place
                    transform_data = _capture_bone_transform(bone)
                    mirrored_transform = _mirror_transform_data(transform_data, axis)
                    _apply_bone_transform(bone, mirrored_transform)
                    
                    results['mirrored_bones'].append({
                        'original': bone.name,
                        'mirrored': bone.name + ' (in-place)',
                        'armature': armature_obj.name
                    })
                    
            except Exception as e:
                results['failed_bones'].append({
                    'name': bone.name,
                    'armature': armature_obj.name,
                    'reason': str(e)
                })
                
    except Exception as e:
        results['failed_bones'].append({
            'name': 'Unknown',
            'armature': armature_obj.name if armature_obj else 'Unknown',
            'reason': f"Error processing armature: {str(e)}"
        })


def _find_mirrored_object(obj_name: str, mirror_cache: Dict[str, Any]) -> Optional[bpy.types.Object]:
    """Find mirrored object using cache."""
    # Get namespace from picker window
    namespace = _get_current_namespace()
    
    if obj_name in mirror_cache:
        return mirror_cache[obj_name]
    
    # Try namespace-aware matching
    if namespace:
        for cached_name, mirror_obj in mirror_cache.items():
            if (obj_name in cached_name or cached_name in obj_name or
                cached_name == f"{namespace}_{obj_name}" or
                cached_name == f"{obj_name}_{namespace}" or
                cached_name == f"{namespace}.{obj_name}" or
                cached_name == f"{obj_name}.{namespace}"):
                return mirror_obj
    
    return None


def _get_mirrored_bone_name(bone_name: str) -> Optional[str]:
    """Get mirrored bone name using enhanced patterns."""
    patterns = [
        # Suffix patterns
        ('_L', '_R'), ('_l', '_r'), ('.L', '.R'), ('.l', '.r'),
        ('Left', 'Right'), ('left', 'right'),
        ('_Left', '_Right'), ('_left', '_right'),
        ('.Left', '.Right'), ('.left', '.right'),
        # Prefix patterns
        ('L_', 'R_'), ('l_', 'r_'), ('L.', 'R.'), ('l.', 'r.'),
        ('Left_', 'Right_'), ('left_', 'right_'),
        ('Left.', 'Right.'), ('left.', 'right.')
    ]
    
    # Try exact suffix/prefix matches first
    for left_pat, right_pat in patterns:
        if bone_name.endswith(left_pat):
            return bone_name[:-len(left_pat)] + right_pat
        elif bone_name.endswith(right_pat):
            return bone_name[:-len(right_pat)] + left_pat
        elif bone_name.startswith(left_pat):
            return right_pat + bone_name[len(left_pat):]
        elif bone_name.startswith(right_pat):
            return left_pat + bone_name[len(right_pat):]
    
    # Fallback to anywhere in name
    for left_pat, right_pat in patterns:
        if left_pat in bone_name:
            return bone_name.replace(left_pat, right_pat)
        elif right_pat in bone_name:
            return bone_name.replace(right_pat, left_pat)
    
    return None


def _capture_object_transform(obj: bpy.types.Object) -> Dict[str, Any]:
    """Capture transform data from object."""
    transform_data = {
        'location': list(obj.location),
        'scale': list(obj.scale)
    }
    
    # Add rotation based on mode
    if obj.rotation_mode == 'QUATERNION':
        transform_data['rotation_quaternion'] = list(obj.rotation_quaternion)
    elif obj.rotation_mode == 'AXIS_ANGLE':
        transform_data['rotation_axis_angle'] = list(obj.rotation_axis_angle)
    else:
        transform_data['rotation_euler'] = list(obj.rotation_euler)
    
    return transform_data


def _capture_bone_transform(bone: bpy.types.PoseBone) -> Dict[str, Any]:
    """Capture transform data from pose bone."""
    transform_data = {
        'location': list(bone.location),
        'scale': list(bone.scale)
    }
    
    # Add rotation based on mode
    if bone.rotation_mode == 'QUATERNION':
        transform_data['rotation_quaternion'] = list(bone.rotation_quaternion)
    elif bone.rotation_mode == 'AXIS_ANGLE':
        transform_data['rotation_axis_angle'] = list(bone.rotation_axis_angle)
    else:
        transform_data['rotation_euler'] = list(bone.rotation_euler)
    
    return transform_data


def _mirror_transform_data(transform_data: Dict[str, Any], axis: str = 'x') -> Dict[str, Any]:
    """Mirror transform data across specified axis."""
    mirrored_data = transform_data.copy()
    
    # Default to X-axis mirroring (most common)
    if axis.lower() == 'x':
        # Mirror location
        if 'location' in transform_data and len(transform_data['location']) >= 3:
            mirrored_data['location'] = [-transform_data['location'][0],
                                       transform_data['location'][1],
                                       transform_data['location'][2]]
        
        # Mirror euler rotation
        if 'rotation_euler' in transform_data and len(transform_data['rotation_euler']) >= 3:
            mirrored_data['rotation_euler'] = [transform_data['rotation_euler'][0],
                                             -transform_data['rotation_euler'][1],
                                             -transform_data['rotation_euler'][2]]
        
        # Mirror quaternion rotation
        if 'rotation_quaternion' in transform_data and len(transform_data['rotation_quaternion']) >= 4:
            mirrored_data['rotation_quaternion'] = [transform_data['rotation_quaternion'][0],
                                                   transform_data['rotation_quaternion'][1],
                                                   -transform_data['rotation_quaternion'][2],
                                                   -transform_data['rotation_quaternion'][3]]
        
        # Mirror axis-angle rotation
        if 'rotation_axis_angle' in transform_data and len(transform_data['rotation_axis_angle']) >= 4:
            mirrored_data['rotation_axis_angle'] = [-transform_data['rotation_axis_angle'][0],
                                                   transform_data['rotation_axis_angle'][1],
                                                   -transform_data['rotation_axis_angle'][2],
                                                   -transform_data['rotation_axis_angle'][3]]
    
    # Y and Z axis mirroring can be added here if needed
    elif axis.lower() == 'y':
        # Mirror Y-axis (flip up/down)
        if 'location' in transform_data and len(transform_data['location']) >= 3:
            mirrored_data['location'] = [transform_data['location'][0],
                                       -transform_data['location'][1],
                                       transform_data['location'][2]]
        # Add Y-axis rotation mirroring logic here
        
    elif axis.lower() == 'z':
        # Mirror Z-axis (flip front/back)
        if 'location' in transform_data and len(transform_data['location']) >= 3:
            mirrored_data['location'] = [transform_data['location'][0],
                                       transform_data['location'][1],
                                       -transform_data['location'][2]]
        # Add Z-axis rotation mirroring logic here
    
    return mirrored_data


def _apply_object_transform(obj: bpy.types.Object, transform_data: Dict[str, Any]) -> None:
    """Apply transform data to object."""
    if 'location' in transform_data and len(transform_data['location']) == 3:
        obj.location[:] = transform_data['location']
    
    if 'scale' in transform_data and len(transform_data['scale']) == 3:
        obj.scale[:] = transform_data['scale']
    
    # Apply rotation based on object's rotation mode
    if obj.rotation_mode == 'QUATERNION' and 'rotation_quaternion' in transform_data:
        obj.rotation_quaternion[:] = transform_data['rotation_quaternion'][:4]
    elif obj.rotation_mode == 'AXIS_ANGLE' and 'rotation_axis_angle' in transform_data:
        obj.rotation_axis_angle[:] = transform_data['rotation_axis_angle'][:4]
    elif 'rotation_euler' in transform_data:
        obj.rotation_euler[:] = transform_data['rotation_euler'][:3]


def _apply_bone_transform(bone: bpy.types.PoseBone, transform_data: Dict[str, Any]) -> None:
    """Apply transform data to pose bone."""
    if 'location' in transform_data and len(transform_data['location']) == 3:
        bone.location[:] = transform_data['location']
    
    if 'scale' in transform_data and len(transform_data['scale']) == 3:
        bone.scale[:] = transform_data['scale']
    
    # Apply rotation based on bone's rotation mode
    if bone.rotation_mode == 'QUATERNION' and 'rotation_quaternion' in transform_data:
        bone.rotation_quaternion[:] = transform_data['rotation_quaternion'][:4]
    elif bone.rotation_mode == 'AXIS_ANGLE' and 'rotation_axis_angle' in transform_data:
        bone.rotation_axis_angle[:] = transform_data['rotation_axis_angle'][:4]
    elif 'rotation_euler' in transform_data:
        bone.rotation_euler[:] = transform_data['rotation_euler'][:3]


def _select_mirrored_items(results: Dict[str, Any], mirror_mode: str) -> None:
    """Select the mirrored objects/bones after mirroring."""
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        try:
            if mirror_mode == 'bones' and results['mirrored_bones']:
                # Handle bone selection
                armature_name = results['mirrored_bones'][0]['armature']
                if armature_name in bpy.data.objects:
                    armature_obj = bpy.data.objects[armature_name]
                    bpy.context.view_layer.objects.active = armature_obj
                    
                    # Switch to pose mode if needed
                    if bpy.context.mode != 'POSE':
                        bpy.ops.object.mode_set(mode='POSE')
                    
                    # Clear selection and select only the result bones
                    bpy.ops.pose.select_all(action='DESELECT')
                    
                    for bone_info in results['mirrored_bones']:
                        mirrored_name = bone_info['mirrored']
                        
                        # If it's an in-place mirror, select the original bone
                        if mirrored_name.endswith(' (in-place)'):
                            original_name = bone_info['original']
                            if original_name in armature_obj.pose.bones:
                                armature_obj.pose.bones[original_name].bone.select = True
                        else:
                            # If it has a counterpart, select the counterpart
                            if mirrored_name in armature_obj.pose.bones:
                                armature_obj.pose.bones[mirrored_name].bone.select = True
                    bpy.context.object.data.bones.active = bpy.context.object.data.bones[mirrored_name]
                            
            elif mirror_mode == 'objects' and results['mirrored_objects']:
                # Handle object selection
                bpy.ops.object.select_all(action='DESELECT')
                
                for obj_info in results['mirrored_objects']:
                    mirrored_name = obj_info['mirrored']
                    
                    # If it's an in-place mirror, select the original object
                    if mirrored_name.endswith(' (in-place)'):
                        original_name = obj_info['original']
                        if original_name in bpy.data.objects:
                            bpy.data.objects[original_name].select_set(True)
                            bpy.context.view_layer.objects.active = bpy.data.objects[original_name]
                    else:
                        # If it has a counterpart, select the counterpart
                        if mirrored_name in bpy.data.objects:
                            bpy.data.objects[mirrored_name].select_set(True)
                            bpy.context.view_layer.objects.active = bpy.data.objects[mirrored_name]
                        
        except Exception as e:
            results['messages'].append(f"Error selecting mirrored items: {str(e)}")
#---------------------------------------------------------------------------------------------------------------
@shortcuts(t='text', c='color', o='opacity', s='selectable', sb='source_button', tb='target_buttons')
def button_appearance(text="", color="", opacity="", selectable="", source_button=None, target_buttons=None):
    """
    Changes the appearance of buttons in the animation picker.
    
    This function allows modifying the text, color, and opacity of buttons.
    If a parameter is left empty, that property will remain unchanged.
    
    When called from a script attached to a button, it will modify that specific button.
    When called directly, it will modify all selected buttons.
    
    Can be used in button scripts with the @TF.button_appearance() qualifier syntax:
    @TF.button_appearance(text="New Label", color="#FF0000")
    
    Args:
        text (str, optional): New text/label for the button(s). Default is "".
        color (str, optional): New color for the button(s) in hex format (e.g., "#FF0000"). Default is "".
        opacity (str, optional): New opacity value for the button(s) between 0 and 1. Default is "".
        selectable (str, optional): Whether the button can be selected in select mode (not edit mode). 
            Values can be "True"/"False" or "1"/"0". Default is "" (no change).
        source_button (PickerButton, optional): The button that executed the script. Default is None.
            This is automatically set when the function is called from a button's script.
        target_buttons (list or str, optional): Specific buttons to modify. Can be:
            - A list of button objects
            - A list of button unique IDs as strings
            - A single button unique ID as a string
            - None (default): Uses source_button if called from a script, or selected buttons otherwise
    
    Example:
        button_appearance(text="New Label")  # Only changes the text
        button_appearance(color="#FF0000")  # Only changes the color to red
        button_appearance(opacity="0.5")    # Only changes the opacity to 50%
        button_appearance(selectable="False")  # Makes the button not selectable in select mode
        button_appearance(text="New Label", color="#FF0000", opacity="0.8")  # Changes all properties
        
        # In button scripts with qualifier syntax:
        @TF.button_appearance(text="IK")
        @TF.button_appearance(text="FK", color="#FF0000")
    """
    # Discover the execution context (source button, picker widget, all buttons)
    context = _discover_execution_context(source_button)
    if not context:
        print("No picker widgets found.")
        return
    
    # Resolve which buttons to modify
    buttons_to_modify = _resolve_target_buttons(target_buttons, context)
    if not buttons_to_modify:
        print("No buttons to modify in the target picker widget. Please select at least one button or call this function from a button's script.")
        return
    
    # Process and validate appearance parameters
    validated_params = _process_appearance_parameters(text, color, opacity, selectable)
    if not any(validated_params.values()):
        print("No changes were made. Please provide at least one parameter (text, color, opacity, or selectable).")
        return
    
    # Apply appearance changes to buttons
    modified_buttons = _apply_appearance_changes(buttons_to_modify, validated_params)
    
    # Persist changes to database and update UI
    if modified_buttons:
        _persist_appearance_changes(modified_buttons, context, validated_params)

def _discover_execution_context(source_button):
    """
    Discover the execution context including source button, picker widget, and all available buttons.
    
    Returns:
        dict: Context containing 'source_button', 'picker_widget', 'all_buttons', and 'canvas'
        None: If no valid context could be established
    """
    # Import needed modules
    from . import blender_main as MAIN
    import inspect
    
    # Detect source button from call stack if not provided
    if source_button is None:
        for frame_info in inspect.stack():
            if frame_info.function == 'execute_script_command':
                if hasattr(frame_info, 'frame') and 'self' in frame_info.frame.f_locals:
                    potential_button = frame_info.frame.f_locals['self']
                    if hasattr(potential_button, 'mode') and hasattr(potential_button, 'script_data'):
                        source_button = potential_button
                        break
    
    # Find the target picker widget
    picker_widget = None
    if source_button:
        # Walk up the widget hierarchy to find the picker window
        current_widget = source_button
        while current_widget:
            if current_widget.__class__.__name__ == 'BlenderAnimPickerWindow':
                picker_widget = current_widget
                break
            current_widget = current_widget.parent()
    
    # Fallback to manager approach if no picker widget found
    if not picker_widget:
        manager = MAIN.PickerWindowManager.get_instance()
        if manager and manager._picker_widgets:
            picker_widget = manager._picker_widgets[0]
    
    if not picker_widget:
        return None
    
    # Get canvas from picker widget
    canvas = None
    if hasattr(picker_widget, 'canvas'):
        canvas = picker_widget.canvas
    elif hasattr(picker_widget, 'tab_system') and picker_widget.tab_system.current_tab:
        current_tab = picker_widget.tab_system.current_tab
        if current_tab in picker_widget.tab_system.tabs:
            canvas = picker_widget.tab_system.tabs[current_tab]['canvas']
    
    if not canvas:
        for child in picker_widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'buttons') and isinstance(child.buttons, list):
                canvas = child
                break
    
    # Get all buttons from the picker widget
    all_buttons = []
    if canvas and hasattr(canvas, 'buttons'):
        all_buttons.extend(canvas.buttons)
    
    # Fallback: search for buttons in all child widgets
    if not all_buttons:
        for child in picker_widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'mode') and hasattr(child, 'label') and hasattr(child, 'unique_id'):
                all_buttons.append(child)
    
    return {
        'source_button': source_button,
        'picker_widget': picker_widget,
        'all_buttons': all_buttons,
        'canvas': canvas
    }

def _resolve_target_buttons(target_buttons, context):
    """
    Resolve which buttons should be modified based on the target_buttons parameter and context.
    
    Args:
        target_buttons: User-specified target buttons (None, string, or list)
        context (dict): Execution context from _discover_execution_context
    
    Returns:
        list: List of button objects to modify
    """
    all_buttons = context['all_buttons']
    source_button = context['source_button']
    
    # Case 1: Specific target buttons provided
    if target_buttons is not None:
        buttons_to_modify = []
        
        # Convert single string to list
        if isinstance(target_buttons, str):
            target_buttons = [target_buttons]
        
        # Process each target
        for target in target_buttons:
            if isinstance(target, str):
                # Find buttons by unique ID
                for btn in all_buttons:
                    if hasattr(btn, 'unique_id') and btn.unique_id == target:
                        buttons_to_modify.append(btn)
                        break
            else:
                # Assume it's a button object - verify it belongs to the target widget
                if target in all_buttons:
                    buttons_to_modify.append(target)
        
        return buttons_to_modify
    
    # Case 2: Source button provided or detected from script execution
    if source_button is not None:
        if source_button in all_buttons:
            return [source_button]
        else:
            print("Source button not found in the target picker widget.")
            return []
    
    # Case 3: Default to selected buttons in the target widget
    return [btn for btn in all_buttons if hasattr(btn, 'is_selected') and btn.is_selected]

def _process_appearance_parameters(text, color, opacity, selectable):
    """
    Process and validate all appearance parameters.
    
    Args:
        text (str): Button text/label
        color (str): Button color in hex format
        opacity (str): Button opacity (0-1)
        selectable (str): Whether button is selectable ("True"/"False" or "1"/"0")
    
    Returns:
        dict: Validated parameters with None values for invalid/empty parameters
    """
    validated = {}
    
    # Process text
    validated['text'] = text if text else None
    
    # Process and validate color
    if color and color.startswith('#') and (len(color) == 7 or len(color) == 9):
        validated['color'] = color
    elif color:
        print(f"Invalid color format: {color}. Color should be in hex format (e.g., #FF0000).")
        validated['color'] = None
    else:
        validated['color'] = None
    
    # Process and validate opacity
    if opacity == 0:
        validated['opacity'] = 0.001
    elif opacity:
        try:
            opacity_value = float(opacity)
            if 0 <= opacity_value <= 1:
                validated['opacity'] = opacity_value
            else:
                print("Opacity must be between 0 and 1. Using current opacity.")
                validated['opacity'] = None
        except ValueError:
            print(f"Invalid opacity value: {opacity}. Using current opacity.")
            validated['opacity'] = None
    else:
        validated['opacity'] = None
    
    # Process and validate selectable
    selectable_str = str(selectable)  # Convert to string first
    if selectable_str:  # Check if the string is not empty
        if selectable_str.lower() in ["true", "1"]:
            validated['selectable'] = True
        elif selectable_str.lower() in ["false", "0"]:
            validated['selectable'] = False
        else:
            print(f"Invalid selectable value: {selectable}. Use 'True'/'False' or '1'/'0'. Using current setting.")
            validated['selectable'] = None
    else:
        validated['selectable'] = None
    
    return validated

def _apply_appearance_changes(buttons_to_modify, validated_params):
    """
    Apply appearance changes to the specified buttons.
    
    Args:
        buttons_to_modify (list): List of button objects to modify
        validated_params (dict): Validated parameters from _process_appearance_parameters
    
    Returns:
        list: List of buttons that were actually modified
    """
    modified_buttons = []
    
    for button in buttons_to_modify:
        button_changed = False
        
        # Update text if provided
        if validated_params['text']:
            button.label = validated_params['text']
            # Reset text pixmap cache to force redraw
            button.text_pixmap = None
            button.pose_pixmap = None
            button.last_zoom_factor = 0
            button_changed = True
        
        # Update color if provided
        if validated_params['color']:
            button.color = validated_params['color']
            button_changed = True
        
        # Update opacity if provided
        if validated_params['opacity'] is not None:
            button.opacity = validated_params['opacity']
            button_changed = True
        
        # Update selectable state if provided
        if validated_params['selectable'] is not None:
            # Add selectable attribute if it doesn't exist
            if not hasattr(button, 'selectable'):
                button.selectable = True  # Default to True for backward compatibility
            button.selectable = validated_params['selectable']
            button_changed = True
        
        # If any changes were made, update UI elements and track the button
        if button_changed:
            button.update_tooltip()
            button.update()
            modified_buttons.append(button)
    
    return modified_buttons

def _persist_appearance_changes(modified_buttons, context, validated_params):
    """
    Persist appearance changes to database and update UI.
    
    Args:
        modified_buttons (list): List of buttons that were modified
        context (dict): Execution context from _discover_execution_context
        validated_params (dict): Validated parameters that were applied
    """
    picker_widget = context['picker_widget']
    canvas = context['canvas']
    
    # Get current tab for database operations
    current_tab = None
    if hasattr(picker_widget, 'tab_system') and picker_widget.tab_system.current_tab:
        current_tab = picker_widget.tab_system.current_tab
    
    # Update database if we have a current tab
    if current_tab and canvas:
        from . import data_management as DM
        
        # Initialize tab data if needed
        if hasattr(picker_widget, 'initialize_tab_data'):
            picker_widget.initialize_tab_data(current_tab)
        
        # Temporarily disable batch updates to prevent conflicts
        original_batch_active = getattr(picker_widget, 'batch_update_active', False)
        picker_widget.batch_update_active = True
        
        try:
            # Get current tab data and create button lookup map
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            button_map = {btn['id']: i for i, btn in enumerate(tab_data['buttons'])}
            
            # Update database with modified button data
            for button in modified_buttons:
                button_data = {
                    "id": button.unique_id,
                    "label": button.label,
                    "color": button.color,
                    "opacity": button.opacity,
                    "position": (button.scene_position.x(), button.scene_position.y()),
                    "width": getattr(button, 'width', 80),
                    "height": getattr(button, 'height', 30),
                    "radius": getattr(button, 'radius', [3, 3, 3, 3]),
                    "assigned_objects": getattr(button, 'assigned_objects', []),
                    "mode": getattr(button, 'mode', 'select'),
                    "script_data": getattr(button, 'script_data', {'code': '', 'type': 'python'}),
                    "pose_data": getattr(button, 'pose_data', {}),
                    "thumbnail_path": getattr(button, 'thumbnail_path', ''),
                }
                
                # Update existing button data or add new one
                if button.unique_id in button_map:
                    index = button_map[button.unique_id]
                    tab_data['buttons'][index] = button_data
                else:
                    tab_data['buttons'].append(button_data)
            
            # Save updated tab data
            DM.PickerDataManager.update_tab_data(current_tab, tab_data)
            DM.PickerDataManager.save_data(DM.PickerDataManager.get_data(), force_immediate=True)
            
            # Emit changed signals for UI consistency
            for button in modified_buttons:
                if hasattr(button, 'changed'):
                    try:
                        button.changed.blockSignals(True)
                        button.changed.emit(button)
                        button.changed.blockSignals(False)
                    except:
                        button.changed.emit(button)
        
        finally:
            # Restore original batch update state
            picker_widget.batch_update_active = original_batch_active
    
    # Update UI elements
    if canvas:
        canvas.update()
        if hasattr(canvas, 'update_button_positions'):
            canvas.update_button_positions()
    
    if hasattr(picker_widget, 'update_buttons_for_current_tab'):
        picker_widget.update_buttons_for_current_tab()
    
    # Report changes (optional - uncomment if needed)
    # changes = []
    # if validated_params['text']: changes.append(f"text to '{validated_params['text']}'")
    # if validated_params['color']: changes.append(f"color to '{validated_params['color']}'")
    # if validated_params['opacity'] is not None: changes.append(f"opacity to {validated_params['opacity']}")
    # if validated_params['selectable'] is not None: changes.append(f"selectable to {validated_params['selectable']}")
    # 
    # widget_name = getattr(picker_widget, 'objectName', lambda: 'Unknown')()
    # print(f"Updated {len(modified_buttons)} button(s) in widget '{widget_name}': {', '.join(changes)}")
    # print("Changes have been saved to the database.")
#---------------------------------------------------------------------------------------------------------------
def tool_tip(tooltip_text=""):
    """
    Sets a custom tooltip for a button in the animation picker.
    
    This function allows setting a custom tooltip for a button.
    When called from a script attached to a button, it will modify that specific button's tooltip.
    
    Can be used in button scripts with the @TF.tool_tip() qualifier syntax:
    @TF.tool_tip("My custom tooltip")
    
    Args:
        tooltip_text (str): The custom tooltip text to display when hovering over the button.
        
    Returns:
        None: This function is meant to be used as a decorator in button scripts.
        
    Example:
        @TF.tool_tip("This button resets the character pose")
        
        # Can be combined with other decorators:
        @TF.tool_tip("Switch to FK mode")
        @TF.button_appearance(text="FK", color="#FF0000")
    """
    # This function is meant to be used as a decorator in button scripts
    # The actual implementation is handled in the PickerButton.execute_script_command method
    pass
#---------------------------------------------------------------------------------------------------------------
def pb(button_ids):
    """
    Access picker button parameters by button ID(s).
    
    Returns a PickerButtonProxy object for single IDs or PickerButtonCollection 
    for multiple IDs that allows easy access to button properties like color, opacity, text, etc.
    
    Args:
        button_ids (str or list): The unique ID(s) of the button(s) to access
        
    Returns:
        PickerButtonProxy: For single button ID - an object with properties matching the button's attributes
        PickerButtonCollection: For multiple button IDs - a collection object that provides list-like access
        None: If no buttons are found
    
    Example:
        # Single button access
        print(pb("button_id").color)     # Prints the button's color
        print(pb("button_id").opacity)   # Prints the button's opacity
        print(pb("button_id").label)     # Prints the button's text/label
        
        # Multiple button access
        buttons = pb(["btn1", "btn2", "btn3"])
        print(buttons.color)             # Prints list of colors for all buttons
        print(buttons[0].color)          # Prints color of first button
        print(len(buttons))              # Prints number of found buttons
        
        # Check if button exists
        button = pb("my_button")
        if button:
            print(f"Button color: {button.color}")
            print(f"Button opacity: {button.opacity}")
        else:
            print("Button not found")
    """
    # Import needed modules
    from . import blender_main as MAIN
    import inspect
    
    class PickerButtonCollection:
        """
        Collection object that provides access to multiple picker buttons.
        Supports both list-like access and collective property access.
        """
        def __init__(self, buttons):
            self._buttons = buttons
            self._proxies = [PickerButtonProxy(btn) for btn in buttons]
            
        def __len__(self):
            """Return the number of buttons in the collection."""
            return len(self._proxies)
            
        def __getitem__(self, index):
            """Get a specific button by index."""
            return self._proxies[index]
            
        def __iter__(self):
            """Iterate over the buttons."""
            return iter(self._proxies)
            
        def __bool__(self):
            """Return True if collection is not empty."""
            return len(self._proxies) > 0
            
        @property
        def color(self):
            """Get list of colors for all buttons."""
            return [proxy.color for proxy in self._proxies]
            
        @property
        def opacity(self):
            """Get list of opacities for all buttons."""
            return [proxy.opacity for proxy in self._proxies]
            
        @property
        def label(self):
            """Get list of labels for all buttons."""
            return [proxy.label for proxy in self._proxies]
            
        @property
        def text(self):
            """Alias for label - get list of text for all buttons."""
            return self.label
            
        @property
        def position(self):
            """Get list of positions for all buttons."""
            return [proxy.position for proxy in self._proxies]
            
        @property
        def width(self):
            """Get list of widths for all buttons."""
            return [proxy.width for proxy in self._proxies]
            
        @property
        def height(self):
            """Get list of heights for all buttons."""
            return [proxy.height for proxy in self._proxies]
            
        @property
        def radius(self):
            """Get list of corner radii for all buttons."""
            return [proxy.radius for proxy in self._proxies]
            
        @property
        def mode(self):
            """Get list of modes for all buttons."""
            return [proxy.mode for proxy in self._proxies]
            
        @property
        def selectable(self):
            """Get list of selectable states for all buttons."""
            return [proxy.selectable for proxy in self._proxies]
            
        @property
        def is_selected(self):
            """Get list of selection states for all buttons."""
            return [proxy.is_selected for proxy in self._proxies]
            
        @property
        def unique_id(self):
            """Get list of unique IDs for all buttons."""
            return [proxy.unique_id for proxy in self._proxies]
            
        @property
        def assigned_objects(self):
            """Get flattened list of all assigned object names from all buttons."""
            all_objects = []
            for proxy in self._proxies:
                all_objects.extend(proxy.assigned_objects)
            return all_objects
            
        @property
        def script_data(self):
            """Get list of script data for all buttons."""
            return [proxy.script_data for proxy in self._proxies]
            
        @property
        def pose_data(self):
            """Get list of pose data for all buttons."""
            return [proxy.pose_data for proxy in self._proxies]
            
        @property
        def thumbnail_path(self):
            """Get list of thumbnail paths for all buttons."""
            return [proxy.thumbnail_path for proxy in self._proxies]
            
        def __str__(self):
            """String representation of the collection."""
            if not self._proxies:
                return "PickerButtonCollection(empty)"
            return f"PickerButtonCollection({len(self._proxies)} buttons)"
            
        def __repr__(self):
            """Detailed representation of the collection."""
            if not self._proxies:
                return "PickerButtonCollection([])"
            ids = [proxy.unique_id for proxy in self._proxies]
            return f"PickerButtonCollection({ids})"

    class PickerButtonProxy:
        """
        Proxy object that provides easy access to picker button properties.
        """
        def __init__(self, button):
            self._button = button
            
        @property
        def color(self):
            """Get the button's color."""
            return getattr(self._button, 'color', None)
            
        @property
        def opacity(self):
            """Get the button's opacity."""
            return getattr(self._button, 'opacity', None)
            
        @property
        def label(self):
            """Get the button's text/label."""
            return getattr(self._button, 'label', None)
            
        @property
        def text(self):
            """Alias for label - get the button's text."""
            return self.label
            
        @property
        def position(self):
            """Get the button's position as (x, y) tuple."""
            if hasattr(self._button, 'scene_position'):
                pos = self._button.scene_position
                return (pos.x(), pos.y())
            return None
            
        @property
        def width(self):
            """Get the button's width."""
            return getattr(self._button, 'width', None)
            
        @property
        def height(self):
            """Get the button's height."""
            return getattr(self._button, 'height', None)
            
        @property
        def radius(self):
            """Get the button's corner radius."""
            return getattr(self._button, 'radius', None)
            
        @property
        def mode(self):
            """Get the button's mode (e.g., 'select', 'pose', 'script')."""
            return getattr(self._button, 'mode', None)
            
        @property
        def selectable(self):
            """Get whether the button is selectable."""
            return getattr(self._button, 'selectable', True)
            
        @property
        def is_selected(self):
            """Get whether the button is currently selected."""
            return getattr(self._button, 'is_selected', False)
            
        @property
        def unique_id(self):
            """Get the button's unique ID."""
            return getattr(self._button, 'unique_id', None)
            
        @property
        def assigned_objects(self):
            """Get the list of object names assigned to this button."""
            raw_objects = getattr(self._button, 'assigned_objects', [])
            # Extract just the names from the objects
            object_names = []
            for obj in raw_objects:
                if hasattr(obj, 'name'):
                    # Blender object with .name attribute
                    object_names.append(obj.name)
                elif isinstance(obj, str):
                    # Already a string (object name)
                    object_names.append(obj)
                elif isinstance(obj, dict) and 'name' in obj:
                    # Dictionary with name key
                    object_names.append(obj['name'])
                else:
                    # Fallback - convert to string
                    object_names.append(str(obj))
            return object_names
            
        @property
        def script_data(self):
            """Get the button's script data."""
            return getattr(self._button, 'script_data', {})
            
        @property
        def pose_data(self):
            """Get the button's pose data."""
            return getattr(self._button, 'pose_data', {})
            
        @property
        def thumbnail_path(self):
            """Get the button's thumbnail path."""
            return getattr(self._button, 'thumbnail_path', '')
            
        def __str__(self):
            """String representation of the button."""
            return f"PickerButton(id='{self.unique_id}', label='{self.label}', color='{self.color}')"
            
        def __repr__(self):
            """Detailed representation of the button."""
            return (f"PickerButton(id='{self.unique_id}', label='{self.label}', "
                   f"color='{self.color}', opacity={self.opacity}, mode='{self.mode}')")
    
    # Convert single string to list for uniform processing
    if isinstance(button_ids, str):
        button_ids = [button_ids]
        single_button = True
    else:
        single_button = False
    
    # Get the correct picker window instance
    target_picker_widget = None
    
    # Try to find the picker widget from the current context
    # First, check if we're being called from a script and can find the source button
    script_source_button = None
    for frame_info in inspect.stack():
        if frame_info.function == 'execute_script_command':
            if hasattr(frame_info, 'frame') and 'self' in frame_info.frame.f_locals:
                potential_button = frame_info.frame.f_locals['self']
                if hasattr(potential_button, 'mode') and hasattr(potential_button, 'script_data'):
                    script_source_button = potential_button
                    break
    
    if script_source_button:
        # Find the picker widget that contains this button
        current_widget = script_source_button
        while current_widget:
            if current_widget.__class__.__name__ == 'BlenderAnimPickerWindow':
                target_picker_widget = current_widget
                break
            current_widget = current_widget.parent()
    
    # If we couldn't find the specific window, fall back to manager approach
    if not target_picker_widget:
        manager = MAIN.PickerWindowManager.get_instance()
        if not manager or not manager._picker_widgets:
            print("No picker widgets found.")
            return None
        # Use the first available picker widget as fallback
        target_picker_widget = manager._picker_widgets[0]
    
    # Get all buttons from the correct picker widget instance
    all_buttons = []
    
    # Try different ways to access the canvas from the target picker widget
    canvas = None
    
    # Method 1: Direct canvas attribute
    if hasattr(target_picker_widget, 'canvas'):
        canvas = target_picker_widget.canvas
    
    # Method 2: Look for canvas in tab system
    elif hasattr(target_picker_widget, 'tab_system'):
        if target_picker_widget.tab_system.current_tab:
            current_tab = target_picker_widget.tab_system.current_tab
            if current_tab in target_picker_widget.tab_system.tabs:
                canvas = target_picker_widget.tab_system.tabs[current_tab]['canvas']
    
    # Method 3: Search for canvas in children of the target widget only
    if not canvas:
        for child in target_picker_widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'buttons') and isinstance(child.buttons, list):
                canvas = child
                break
    
    # If we found a canvas, get its buttons
    if canvas and hasattr(canvas, 'buttons'):
        all_buttons.extend(canvas.buttons)
    
    # If we still don't have any buttons from the target widget, search more thoroughly
    if not all_buttons:
        for child in target_picker_widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'mode') and hasattr(child, 'label') and hasattr(child, 'unique_id'):
                all_buttons.append(child)
    
    # Find buttons with matching IDs
    found_buttons = []
    for button_id in button_ids:
        for button in all_buttons:
            if hasattr(button, 'unique_id') and button.unique_id == button_id:
                found_buttons.append(button)
                break
    
    # Handle results based on input type
    if single_button:
        # Original single button behavior
        if found_buttons:
            return PickerButtonProxy(found_buttons[0])
        else:
            print(f"Button with ID '{button_ids[0]}' not found.")
            return None
    else:
        # Multiple buttons - return collection
        if found_buttons:
            return PickerButtonCollection(found_buttons)
        else:
            print(f"No buttons found for IDs: {button_ids}")
            return None

def list_buttons():
    """
    List all available buttons with their IDs and basic info.
    
    Returns:
        list: List of dictionaries containing button information
    """
    from . import blender_main as MAIN
    import inspect
    
    # Get picker widget (reusing logic from pb function)
    target_picker_widget = None
    script_source_button = None
    
    for frame_info in inspect.stack():
        if frame_info.function == 'execute_script_command':
            if hasattr(frame_info, 'frame') and 'self' in frame_info.frame.f_locals:
                potential_button = frame_info.frame.f_locals['self']
                if hasattr(potential_button, 'mode') and hasattr(potential_button, 'script_data'):
                    script_source_button = potential_button
                    break
    
    if script_source_button:
        current_widget = script_source_button
        while current_widget:
            if current_widget.__class__.__name__ == 'BlenderAnimPickerWindow':
                target_picker_widget = current_widget
                break
            current_widget = current_widget.parent()
    
    if not target_picker_widget:
        manager = MAIN.PickerWindowManager.get_instance()
        if not manager or not manager._picker_widgets:
            return []
        target_picker_widget = manager._picker_widgets[0]
    
    # Get all buttons
    all_buttons = []
    canvas = None
    
    if hasattr(target_picker_widget, 'canvas'):
        canvas = target_picker_widget.canvas
    elif hasattr(target_picker_widget, 'tab_system'):
        if target_picker_widget.tab_system.current_tab:
            current_tab = target_picker_widget.tab_system.current_tab
            if current_tab in target_picker_widget.tab_system.tabs:
                canvas = target_picker_widget.tab_system.tabs[current_tab]['canvas']
    
    if not canvas:
        for child in target_picker_widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'buttons') and isinstance(child.buttons, list):
                canvas = child
                break
    
    if canvas and hasattr(canvas, 'buttons'):
        all_buttons.extend(canvas.buttons)
    
    if not all_buttons:
        for child in target_picker_widget.findChildren(QtWidgets.QWidget):
            if hasattr(child, 'mode') and hasattr(child, 'label') and hasattr(child, 'unique_id'):
                all_buttons.append(child)
    
    # Return button info
    button_info = []
    for button in all_buttons:
        if hasattr(button, 'unique_id'):
            info = {
                'id': getattr(button, 'unique_id', 'Unknown'),
                'label': getattr(button, 'label', ''),
                'color': getattr(button, 'color', ''),
                'opacity': getattr(button, 'opacity', 1.0),
                'mode': getattr(button, 'mode', 'select')
            }
            button_info.append(info)
    
    return button_info

def print_buttons():
    """
    Print all available buttons in a formatted way.
    """
    buttons = list_buttons()
    if not buttons:
        print("No buttons found.")
        return
    
    print(f"Found {len(buttons)} button(s):")
    print("-" * 60)
    for button in buttons:
        print(f"ID: {button['id']:<20} | Label: {button['label']:<15} | Color: {button['color']:<8} | Opacity: {button['opacity']:<4} | Mode: {button['mode']}")
