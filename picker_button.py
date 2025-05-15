from functools import partial
import maya.cmds as cmds
import maya.mel as mel
import os
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
import re

from . import utils as UT
from . import custom_line_edit as CLE
from . import custom_button as CB
from . import data_management as DM
from . import ui as UI
# Lazy import main to avoid circular dependency
from . import script_manager as SM
from . import tool_functions as TF
from . import custom_dialog as CD


class ButtonClipboard:
    _instance = None
    
    def __init__(self):
        self.copied_buttons = []
        self.copy_position = None
    
    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = ButtonClipboard()
        return cls._instance
    
    def copy_buttons(self, buttons, position=None):
        self.copied_buttons = []
        self.copy_position = position
        
        # Calculate center of selected buttons
        if buttons:
            min_x = min(button.scene_position.x() for button in buttons)
            max_x = max(button.scene_position.x() for button in buttons)
            min_y = min(button.scene_position.y() for button in buttons)
            max_y = max(button.scene_position.y() for button in buttons)
            center = QtCore.QPointF((min_x + max_x) / 2, (min_y + max_y) / 2)
            
            # Store positions relative to center
            for button in buttons:
                # Create a dictionary with all button properties
                button_data = {
                    'label': button.label,
                    'color': button.color,
                    'opacity': button.opacity,
                    'width': button.width,
                    'height': button.height,
                    'radius': button.radius.copy(),
                    'relative_position': button.scene_position - center,
                    'assigned_objects': button.assigned_objects.copy(),
                    'mode': button.mode,
                    'script_data': button.script_data.copy()
                }
                
                # Add pose-specific data if this is a pose button
                if button.mode == 'pose':
                    button_data['thumbnail_path'] = button.thumbnail_path
                    button_data['pose_data'] = button.pose_data.copy()  # Copy the pose data
                
                self.copied_buttons.append(button_data)

    def get_last_attributes(self):
        if self.copied_buttons:
            return self.copied_buttons[-1]
        return None

    def get_all_buttons(self):
        return self.copied_buttons

class SelectionManagerWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        if parent is None:
            manager = MAIN.PickerWindowManager.get_instance()
            parent = manager._picker_widgets[0] if manager._picker_widgets else None
        super(SelectionManagerWidget, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        
        # Setup main layout
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(4)
        
        # Create main frame
        self.frame = QtWidgets.QFrame()
        self.frame.setFixedWidth(200)
        self.frame.setStyleSheet("""
            QFrame {
                background-color: rgba(36, 36, 36, .9);
                border: 1px solid #444444;
                border-radius: 4px;
            }
        """)
        self.frame_layout = QtWidgets.QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(6, 6, 6, 6)
        self.frame_layout.setSpacing(6)
        
        # Title bar with draggable area and close button
        self.title_bar = QtWidgets.QWidget()
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet("background: rgba(30, 30, 30, .9); border: none; border-radius: 3px;")
        title_layout = QtWidgets.QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(6, 6, 6, 6)
        title_layout.setSpacing(6)
        
        self.title_label = QtWidgets.QLabel("Selection Manager")
        self.title_label.setStyleSheet("color: #dddddd; background: transparent;")
        title_layout.addWidget(self.title_label)
        
        self.close_button = QtWidgets.QPushButton("✕")
        self.close_button.setFixedSize(16, 16)
        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(200, 0, 0, 0.6);
                color: #ff9393;
                border: none;
                border-radius: 2px;
                padding: 0px 0px 2px 0px;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 0.6);
            }
        """)
        title_layout.addWidget(self.close_button)
        
        # Selection buttons
        self.button_layout = QtWidgets.QHBoxLayout()
        self.add_selection_btn = QtWidgets.QPushButton("Add")
        self.add_selection_btn.setFixedHeight(20)
        self.add_selection_btn.setStyleSheet("""
            QPushButton {
                background-color: #5285a6;
                color: white;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #619ac2;
            }
        """)
        
        self.remove_selection_btn = QtWidgets.QPushButton("Remove")
        self.remove_selection_btn.setFixedHeight(20)
        self.remove_selection_btn.setStyleSheet("""
            QPushButton {
                background-color: #494949;
                color: white;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
        """)
        
        self.button_layout.addWidget(self.add_selection_btn)
        self.button_layout.addWidget(self.remove_selection_btn)
        
        # Selection list
        self.list_frame = QtWidgets.QFrame()
        self.list_frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border-radius: 2px;
            }
        """)
        self.list_layout = QtWidgets.QVBoxLayout(self.list_frame)
        self.list_layout.setContentsMargins(2, 2, 2, 2)
        
        self.selection_list = QtWidgets.QListWidget()
        self.selection_list.setFixedHeight(200)
        self.selection_list.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.selection_list.setStyleSheet("""
            QListWidget {
                background-color: transparent;
                border: none;
                color: #dddddd;
                outline: 0;
            }
                QListWidget::item:focus {
                border: none;  /* Remove focus border */
                outline: none;  /* Remove focus outline */
            }
            QListWidget::item {
                padding: 3px;
                border-radius: 0px;
            }
            QListWidget::item:selected {
                background-color: #2c4759;
            }
            QListWidget::item:hover {
                background-color: rgba(44, 71, 89, 0.5);
            }
        """)
        self.list_layout.addWidget(self.selection_list)
        
        # Add all layouts to main layout
        self.frame_layout.addWidget(self.title_bar)
        self.frame_layout.addLayout(self.button_layout)
        self.frame_layout.addWidget(self.list_frame)
        self.main_layout.addWidget(self.frame)
        
        # Connect signals
        self.close_button.clicked.connect(self.close)
        self.add_selection_btn.clicked.connect(self.add_selection)
        self.remove_selection_btn.clicked.connect(self.remove_selection)
        
        # Window dragging
        self.dragging = False
        self.offset = None
        self.title_bar.mousePressEvent = self.title_bar_mouse_press
        self.title_bar.mouseMoveEvent = self.title_bar_mouse_move
        self.title_bar.mouseReleaseEvent = self.title_bar_mouse_release
        
        self.picker_button = None

    def set_picker_button(self, button):
        self.picker_button = button
        self.refresh_list()
        self.position_window()
        
    def position_window(self):
        if self.picker_button:
            button_geometry = self.picker_button.geometry()
            global_pos = self.picker_button.mapToGlobal(button_geometry.topRight())
            # Add some offset to position it slightly to the right
            self.move(global_pos + QtCore.QPoint(10, 0))
    
    def refresh_list(self):
        """Refresh the list with human-readable object names, compatible with new object structure"""
        self.selection_list.clear()
        if self.picker_button:
            for obj_data in self.picker_button.assigned_objects:
                try:
                    # Handle both old format (just UUID) and new format (dict with UUID and long_name)
                    if isinstance(obj_data, dict):
                        uuid = obj_data['uuid']
                        long_name = obj_data['long_name']
                        
                        # Try to resolve current name from UUID first
                        nodes = cmds.ls(uuid, long=True)
                        node_name = ""
                        
                        if nodes:
                            # Use UUID resolution if available
                            node_name = nodes[0]
                        elif cmds.objExists(long_name):
                            # Fallback to long name if UUID fails
                            node_name = long_name
                        
                        if node_name:
                            # Strip namespace by taking the last part after any ':'
                            short_name = node_name.split('|')[-1].split(':')[-1]
                            item = QtWidgets.QListWidgetItem(short_name)
                            # Store the complete object data for removal
                            item.setData(QtCore.Qt.UserRole, obj_data)
                            self.selection_list.addItem(item)
                    else:
                        # Legacy format - just UUID
                        uuid = obj_data
                        nodes = cmds.ls(uuid, long=True)
                        if nodes:
                            # Strip namespace by taking the last part after any ':'
                            short_name = nodes[0].split('|')[-1].split(':')[-1]
                            item = QtWidgets.QListWidgetItem(short_name)
                            # Store the UUID as item data for removal
                            item.setData(QtCore.Qt.UserRole, uuid)
                            self.selection_list.addItem(item)
                except Exception as e:
                    # Handle case where object no longer exists
                    continue
                
    def add_selection(self):
        """Add selected objects using new object structure"""
        if self.picker_button:
            self.picker_button.add_selected_objects()
            self.refresh_list()
        UT.maya_main_window().activateWindow()
            
    def remove_selection(self):
        """Remove selected objects using new object structure"""
        if self.picker_button:
            selected_items = self.selection_list.selectedItems()
            
            # Extract objects to remove
            objects_to_remove = []
            for item in selected_items:
                item_data = item.data(QtCore.Qt.UserRole)
                objects_to_remove.append(item_data)
            
            # Filter out selected objects
            new_assigned_objects = []
            for obj_data in self.picker_button.assigned_objects:
                # Check if this object should be removed
                should_remove = False
                
                for remove_data in objects_to_remove:
                    if isinstance(obj_data, dict) and isinstance(remove_data, dict):
                        # Both are dictionaries - new format
                        if obj_data['uuid'] == remove_data['uuid']:
                            should_remove = True
                            break
                    elif isinstance(obj_data, dict) and not isinstance(remove_data, dict):
                        # Mixed format - compare UUID only
                        if obj_data['uuid'] == remove_data:
                            should_remove = True
                            break
                    elif not isinstance(obj_data, dict) and not isinstance(remove_data, dict):
                        # Both are old format - direct comparison
                        if obj_data == remove_data:
                            should_remove = True
                            break
                
                if not should_remove:
                    new_assigned_objects.append(obj_data)
            
            self.picker_button.assigned_objects = new_assigned_objects
            self.picker_button.update_tooltip()
            self.picker_button.changed.emit(self.picker_button)
            self.refresh_list()
        UT.maya_main_window().activateWindow()

    # Window dragging methods
    def title_bar_mouse_press(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = True
            self.offset = event.globalPos() - self.pos()
        UT.maya_main_window().activateWindow()
            
    def title_bar_mouse_move(self, event):
        if self.dragging and event.buttons() == QtCore.Qt.LeftButton:
            self.move(event.globalPos() - self.offset)
            
    def title_bar_mouse_release(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = False

    def closeEvent(self, event):
        super().closeEvent(event)
        UT.maya_main_window().activateWindow()
#--------------------------------------------------------------------------------------------------------------------
class ScriptSyntaxHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, parent=None):
        super(ScriptSyntaxHighlighter, self).__init__(parent)
        
        # Create format for special tokens
        self.special_format = QtGui.QTextCharFormat()
        self.special_format.setForeground(QtGui.QColor("#91CB08"))  # Bright green color
        self.special_format.setFontWeight(QtGui.QFont.Bold)

        # Create format for @TF. function call (darker green)
        self.tf_function_format = QtGui.QTextCharFormat()
        self.tf_function_format.setForeground(QtGui.QColor("#399dcd"))  # sky blue
        self.tf_function_format.setFontWeight(QtGui.QFont.Bold)

        # Create format for special tokens 2
        self.special_format_02 = QtGui.QTextCharFormat()
        self.special_format_02.setForeground(QtGui.QColor("#10b1cc"))  
        self.special_format_02.setFontWeight(QtGui.QFont.Bold)

        # Create format for brackets/parens/braces (yellow)
        self.bracket_format = QtGui.QTextCharFormat()
        self.bracket_format.setForeground(QtGui.QColor("#FFD700"))  # Yellow (Gold)
        self.bracket_format.setFontWeight(QtGui.QFont.Bold)
   
        # Create format for comments
        self.comment_format = QtGui.QTextCharFormat()
        self.comment_format.setForeground(QtGui.QColor("#555555"))  # Gray color for comments

        # Create format for quoted text in comments
        self.quoted_text_format = QtGui.QTextCharFormat()
        self.quoted_text_format.setForeground(QtGui.QColor("#ce9178"))

        # Create format for Python keywords
        self.keyword_format = QtGui.QTextCharFormat()
        self.keyword_format.setForeground(QtGui.QColor("#2666cb"))  # Slate blue
        self.keyword_format.setFontWeight(QtGui.QFont.Bold)

        # List of Python keywords
        self.python_keywords = [
            'def', 'class', 'if', 'else', 'elif', 'for', 'while', 'return', 'import', 'from', 'as', 'pass', 'break',
            'continue', 'try', 'except', 'finally', 'with', 'lambda', 'yield', 'global', 'nonlocal', 'assert', 'del',
            'raise', 'and', 'or', 'not', 'in', 'is', 'True', 'False', 'None'
        ]
        self.keyword_pattern = r'\\b(' + '|'.join(self.python_keywords) + r')\\b'

        
    def highlightBlock(self, text):
        # Define all special tokens to highlight
        special_patterns = [
            r'@match_ik_to_fk\s*\([^)]*\)',  # Match @match_ik_to_fk() with any parameters
            r'@match_fk_to_ik\s*\([^)]*\)',   # Match @match_fk_to_ik() with any parameters
            r'@TF\.\w+\s*\([^)]*\)',    # Match @TF.function_name() with any parameters
        ]
        special_patterns_02 = [r'@ns\.'] # Original @ns pattern
        
        # Apply highlighting for @TF.functionName() pattern with split colors
        tf_pattern = r'(@TF\.)(\w+\s*\([^)]*\))'
        for match in re.finditer(tf_pattern, text):
            # Apply bright green to @TF.
            self.setFormat(match.start(1), len(match.group(1)), self.special_format)
            # Apply darker green to the function part
            self.setFormat(match.start(2), len(match.group(2)), self.tf_function_format)

        # Apply highlighting for other special patterns
        for pattern in special_patterns:
            if pattern == r'@TF\.\w+\s*\([^)]*\)':
                continue  # Already handled above
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), len(match.group()), self.special_format)
        
        for pattern in special_patterns_02:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), len(match.group()), self.special_format_02)
        
        # Highlight Python keywords
        for match in re.finditer(r'\b(' + '|'.join(self.python_keywords) + r')\b', text):
            self.setFormat(match.start(), len(match.group()), self.keyword_format)

        # Highlight (), {}, [] in yellow
        for match in re.finditer(r'[\(\)\{\}\[\]]', text):
            self.setFormat(match.start(), 1, self.bracket_format)
        
        # Highlight comments (lines starting with #)
        comment_pattern = r'#.*$'
        for match in re.finditer(comment_pattern, text):
            self.setFormat(match.start(), len(match.group()), self.comment_format)
        
        # Highlight quoted text (both single and double quotes)
        # Handle double quotes
        double_quote_pattern = r'"[^"\\]*(?:\\.[^"\\]*)*"'
        for match in re.finditer(double_quote_pattern, text):
            # Don't highlight quotes in comments
            start_pos = match.start()
            if not self.format(start_pos) == self.comment_format:
                self.setFormat(start_pos, len(match.group()), self.quoted_text_format)

        # Handle single quotes
        single_quote_pattern = r'\'[^\'\\]*(?:\\.[^\'\\]*)*\''
        for match in re.finditer(single_quote_pattern, text):
            # Don't highlight quotes in comments
            start_pos = match.start()
            if not self.format(start_pos) == self.comment_format:
                self.setFormat(start_pos, len(match.group()), self.quoted_text_format)

class ScriptManagerWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        if parent is None:
            # Lazy import MAIN to avoid circular dependency
            from . import main as MAIN
            manager = MAIN.PickerWindowManager.get_instance()
            parent = manager._picker_widgets[0] if manager._picker_widgets else None
        super(ScriptManagerWidget, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        
        # Setup resizing parameters
        self.resizing = False
        self.resize_edge = None
        self.resize_range = 8  # Pixels from edge where resizing is active
          # Set minimum size
        self.setGeometry(0,0,400,300)
        self.setMinimumSize(305, 300)
        # Setup main layout
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(4)
        
        # Create main frame
        self.frame = QtWidgets.QFrame()
        self.frame.setMinimumWidth(300)
        self.frame.setStyleSheet("""
            QFrame {
                background-color: rgba(36, 36, 36, .9);
                border: 1px solid #444444;
                border-radius: 4px;
            }
        """)
        self.frame_layout = QtWidgets.QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(6, 6, 6, 6)
        self.frame_layout.setSpacing(6)
        
        # Title bar with draggable area and close button
        self.title_bar = QtWidgets.QWidget()
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet("background: rgba(30, 30, 30, .9); border: none; border-radius: 3px;")
        title_layout = QtWidgets.QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(6, 6, 6, 6)
        title_layout.setSpacing(6)
        
        self.title_label = QtWidgets.QLabel("Script Manager (Python)")
        self.title_label.setStyleSheet("color: #dddddd; background: transparent;")
        title_layout.addSpacing(4)
        title_layout.addWidget(self.title_label)
        
        self.close_button = QtWidgets.QPushButton("✕")
        self.close_button.setFixedSize(16, 16)
        self.close_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(200, 0, 0, 0.6);
                color: #ff9393;
                border: none;
                border-radius: 2px;
                padding: 0px 0px 2px 0px;
            }
            QPushButton:hover {
                background-color: rgba(255, 0, 0, 0.6);
            }
        """)
        title_layout.addWidget(self.close_button)
        
        # Language selection
        self.language_layout = QtWidgets.QHBoxLayout()
        self.language_layout.setAlignment(QtCore.Qt.AlignLeft)

        self.python_button = CB.CustomRadioButton("Python", fill=False, width=60, height=16, group=True)
        self.mel_button = CB.CustomRadioButton("MEL", fill=False, width=40, height=16, group=True)
        self.python_button.group('script_language')
        self.mel_button.group('script_language')

        self.function_preset_stack = QtWidgets.QStackedWidget()
        self.function_preset_stack.setFixedSize(20, 20)
        self.function_preset_stack.setStyleSheet("background: rgba(30, 30, 30, .9); border: none; border-radius: 3px;")
        self.python_function_preset_button = CB.CustomButton(text='', icon=':addClip.png', size=14, height=20, width=20, radius=3,color='#385c73',alpha=0,textColor='#aaaaaa', 
                                                             ContextMenu=True, onlyContext= True, cmColor='#333333',tooltip='Python function presets', flat=True)
        
        self.python_function_preset_button.addMenuLabel('Presets Commands',position=(0,0))
        self.python_function_preset_button.addToMenu('Set Attribute', self.ppf_set_attribute, position=(1,0))
        self.python_function_preset_button.addToMenu('Match IK to FK', self.ppf_match_ik_to_fk, position=(2,0))
        self.python_function_preset_button.addToMenu('Match FK to IK', self.ppf_match_fk_to_ik, position=(3,0))
        self.python_function_preset_button.addToMenu('Button Appearance', self.ppf_button_appearance, position=(4,0))
        self.python_function_preset_button.addToMenu('Get Selected Button IDs', self.ppf_get_selected_button_ids, position=(5,0))

        self.mel_function_preset_button = CB.CustomButton(text='', icon=':addClip.png', size=14, height=20, width=20, radius=3,color='#385c73',alpha=0,textColor='#aaaaaa', 
                                                          ContextMenu=True, onlyContext= True, cmColor='#333333',tooltip='Python function presets', flat=True)
        
        self.mel_function_preset_button.addMenuLabel('Presets Commands',position=(0,0))
        self.mel_function_preset_button.addToMenu('Set Attribute', self.mpf_set_attribute, position=(1,0))

        self.function_preset_stack.addWidget(self.python_function_preset_button)
        self.function_preset_stack.addWidget(self.mel_function_preset_button)

        self.language_layout.addWidget(self.python_button)
        self.language_layout.addWidget(self.mel_button)
        self.language_layout.addStretch()
        self.language_layout.addWidget(self.function_preset_stack)

        # Create custom QPlainTextEdit subclass with line numbers and tab handling
        class LineNumberArea(QtWidgets.QWidget):
            def __init__(self, editor):
                super(LineNumberArea, self).__init__(editor)
                self.editor = editor
                self.setFixedWidth(15)  # Initial width for line numbers - reduced to save space
            
            def sizeHint(self):
                return QtCore.QSize(self.editor.line_number_area_width(), 0)
            
            def paintEvent(self, event):
                self.editor.line_number_area_paint_event(event)
        
        class CodeEditor(QtWidgets.QPlainTextEdit):
            def __init__(self, parent=None):
                super(CodeEditor, self).__init__(parent)
                self.line_number_area = LineNumberArea(self)
                
                # Connect signals for updating line number area
                self.blockCountChanged.connect(self.update_line_number_area_width)
                self.updateRequest.connect(self.update_line_number_area)
                self.cursorPositionChanged.connect(self.highlight_current_line)
                
                # Initialize the line number area width
                self.update_line_number_area_width(0)
                
                # Highlight the current line
                self.highlight_current_line()
            
            def line_number_area_width(self):
                digits = 1
                max_num = max(1, self.blockCount())
                while max_num >= 10:
                    max_num //= 10
                    digits += 1
                
                space = 8 + self.fontMetrics().horizontalAdvance('9') * digits  # Reduced padding
                return space
            
            def update_line_number_area_width(self, _):
                # Set viewport margins to make room for line numbers
                width = self.line_number_area_width()
                # Add 15 pixels of extra margin to prevent text from touching the gutter
                self.setViewportMargins(width + 0, 0, 0, 0)
            
            def update_line_number_area(self, rect, dy):
                if dy:
                    self.line_number_area.scroll(0, dy)
                else:
                    self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
                
                if rect.contains(self.viewport().rect()):
                    self.update_line_number_area_width(0)
            
            def resizeEvent(self, event):
                super(CodeEditor, self).resizeEvent(event)
                
                cr = self.contentsRect()
                self.line_number_area.setGeometry(QtCore.QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))
            
            def line_number_area_paint_event(self, event):
                painter = QtGui.QPainter(self.line_number_area)
                # Use a color that matches the editor background but is slightly different
                painter.fillRect(event.rect(), QtGui.QColor('#1e1e1e'))  # Match editor background
                
                # Draw a subtle separator line
                painter.setPen(QtGui.QColor('#2d2d2d'))
                painter.drawLine(event.rect().topRight(), event.rect().bottomRight())
                
                block = self.firstVisibleBlock()
                block_number = block.blockNumber()
                top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
                bottom = top + self.blockBoundingRect(block).height()
                
                while block.isValid() and top <= event.rect().bottom():
                    if block.isVisible() and bottom >= event.rect().top():
                        number = str(block_number + 1)
                        # Use a more subtle color for line numbers
                        painter.setPen(QtGui.QColor('#6d6d6d'))  # Line number color
                        painter.drawText(0, top, self.line_number_area.width() - 3, self.fontMetrics().height(),
                                        QtCore.Qt.AlignRight, number)
                    
                    block = block.next()
                    top = bottom
                    bottom = top + self.blockBoundingRect(block).height()
                    block_number += 1
            
            def highlight_current_line(self):
                extra_selections = []
                
                if not self.isReadOnly():
                    selection = QtWidgets.QTextEdit.ExtraSelection()
                    line_color = QtGui.QColor('#222222')  # Current line highlight color
                    
                    selection.format.setBackground(line_color)
                    selection.format.setProperty(QtGui.QTextFormat.FullWidthSelection, True)
                    selection.cursor = self.textCursor()
                    selection.cursor.clearSelection()
                    extra_selections.append(selection)
                
                self.setExtraSelections(extra_selections)
            
            def keyPressEvent(self, event):
                # Explicitly check for Shift+Tab and handle it first
                if event.key() == QtCore.Qt.Key_Backtab:
                    # Qt sends Key_Backtab for Shift+Tab
                    event.accept()  # Prevent event propagation
                    self._handle_shift_tab()
                    return
                elif event.key() == QtCore.Qt.Key_Tab:
                    if event.modifiers() & QtCore.Qt.ShiftModifier:
                        event.accept()  # Prevent event propagation
                        self._handle_shift_tab()
                        return
                    else:
                        handled = self._handle_tab()
                        if handled:
                            event.accept()  # Prevent event propagation
                            return
                elif event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
                    if self._handle_enter():
                        event.accept()  # Prevent event propagation
                        return
                # Pass unhandled events to parent
                super().keyPressEvent(event)

            def _handle_tab(self):
                cursor = self.textCursor()
                if cursor.hasSelection():
                    start = cursor.selectionStart()
                    end = cursor.selectionEnd()
                    cursor.setPosition(start)
                    start_block = cursor.blockNumber()
                    cursor.setPosition(end)
                    end_block = cursor.blockNumber()
                    cursor.beginEditBlock()
                    for _ in range(end_block - start_block + 1):
                        cursor.movePosition(QtGui.QTextCursor.StartOfLine)
                        cursor.insertText("    ")
                        cursor.movePosition(QtGui.QTextCursor.NextBlock)
                    cursor.endEditBlock()
                    # Restore selection
                    cursor.setPosition(start + 4)  # +4 for the added spaces
                    cursor.setPosition(end + 4 * (end_block - start_block + 1), QtGui.QTextCursor.KeepAnchor)
                    self.setTextCursor(cursor)
                    return True
                else:
                    # Store current position
                    pos = cursor.position()
                    line_pos = cursor.positionInBlock()
                    cursor.beginEditBlock()
                    cursor.movePosition(QtGui.QTextCursor.StartOfLine)
                    cursor.insertText("    ")
                    cursor.endEditBlock()
                    # Move cursor to after the inserted spaces
                    cursor.setPosition(pos + 4)  # +4 for the added spaces
                    self.setTextCursor(cursor)
                    return True

            def _handle_shift_tab(self):
                cursor = self.textCursor()
                if cursor.hasSelection():
                    # Store selection info
                    start = cursor.selectionStart()
                    end = cursor.selectionEnd()
                    cursor.setPosition(start)
                    start_block = cursor.blockNumber()
                    start_pos_in_block = cursor.positionInBlock()
                    cursor.setPosition(end)
                    end_block = cursor.blockNumber()
                    end_pos_in_block = cursor.positionInBlock()
                    
                    # Track how many spaces were removed from each line
                    spaces_removed = []
                    
                    cursor.beginEditBlock()
                    # Process each line in the selection
                    for i in range(end_block - start_block + 1):
                        cursor.movePosition(QtGui.QTextCursor.StartOfLine)
                        line_text = cursor.block().text()
                        
                        # Count leading spaces/tabs
                        spaces_to_remove = 0
                        if line_text.startswith("    "):  # 4 spaces
                            spaces_to_remove = 4
                        elif line_text.startswith(" "):  # 1-3 spaces
                            for j, char in enumerate(line_text):
                                if char == ' ' and j < 4:
                                    spaces_to_remove += 1
                                else:
                                    break
                        elif line_text.startswith("\t"):  # Tab
                            spaces_to_remove = 1  # Count tab as 1 character
                        
                        # Remove the spaces/tab if any
                        if spaces_to_remove > 0:
                            cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor, spaces_to_remove)
                            cursor.removeSelectedText()
                        
                        spaces_removed.append(spaces_to_remove)
                        cursor.movePosition(QtGui.QTextCursor.NextBlock)
                    cursor.endEditBlock()
                    
                    # Adjust selection start/end based on removed spaces
                    new_start = start - (spaces_removed[0] if start_pos_in_block >= spaces_removed[0] else start_pos_in_block)
                    
                    # Calculate total spaces removed before end position
                    total_spaces_before_end = sum(spaces_removed[:end_block - start_block])
                    # Add spaces removed from the last line if cursor is past them
                    if end_pos_in_block >= spaces_removed[end_block - start_block]:
                        total_spaces_before_end += spaces_removed[end_block - start_block]
                    else:
                        total_spaces_before_end += end_pos_in_block
                    
                    new_end = end - total_spaces_before_end
                    
                    # Restore adjusted selection
                    cursor.setPosition(new_start)
                    cursor.setPosition(new_end, QtGui.QTextCursor.KeepAnchor)
                    self.setTextCursor(cursor)
                    return True
                else:
                    # Store cursor position
                    original_pos = cursor.position()
                    pos_in_block = cursor.positionInBlock()
                    
                    cursor.beginEditBlock()
                    cursor.movePosition(QtGui.QTextCursor.StartOfLine)
                    line_text = cursor.block().text()
                    
                    # Count leading spaces/tabs
                    spaces_to_remove = 0
                    if line_text.startswith("    "):  # 4 spaces
                        spaces_to_remove = 4
                    elif line_text.startswith(" "):  # 1-3 spaces
                        for i, char in enumerate(line_text):
                            if char == ' ' and i < 4:
                                spaces_to_remove += 1
                            else:
                                break
                    elif line_text.startswith("\t"):  # Tab
                        spaces_to_remove = 1  # Count tab as 1 character
                    
                    # Remove the spaces/tab if any
                    if spaces_to_remove > 0:
                        cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor, spaces_to_remove)
                        cursor.removeSelectedText()
                    
                    # Adjust cursor position
                    new_pos = original_pos - (spaces_to_remove if pos_in_block >= spaces_to_remove else pos_in_block)
                    cursor.setPosition(new_pos)
                    cursor.endEditBlock()
                    
                    self.setTextCursor(cursor)
                    return True

            def _handle_enter(self):
                cursor = self.textCursor()
                cursor.beginEditBlock()
                
                # Get current line and position within line
                current_line = cursor.block().text()
                position_in_line = cursor.positionInBlock()
                
                # Extract text before and after cursor on current line
                text_before_cursor = current_line[:position_in_line]
                text_after_cursor = current_line[position_in_line:]
                
                # Get indentation of current line
                indent = ''
                for char in current_line:
                    if char in (' ', '\t'):
                        indent += char
                    else:
                        break
                
                # Check if current line ends with ':' (before the cursor)
                add_extra_indent = text_before_cursor.rstrip().endswith(':')
                
                # Check if cursor is at the end of the line
                at_end_of_line = position_in_line == len(current_line)
                
                # Insert newline with appropriate indentation
                if add_extra_indent:
                    # Add one level of indentation
                    cursor.insertText("\n" + indent + "    " + text_after_cursor)
                    # Only move cursor up if not at the end of the line
                    if not at_end_of_line:
                        cursor.movePosition(QtGui.QTextCursor.Up)
                        cursor.movePosition(QtGui.QTextCursor.EndOfLine)
                    else:
                        # Position cursor after the indentation on the new line
                        cursor.movePosition(QtGui.QTextCursor.StartOfLine)
                        cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.MoveAnchor, len(indent) + 4)
                else:
                    # Maintain same indentation level
                    cursor.insertText("\n" + indent + text_after_cursor)
                    # Only handle text removal if not at the end of the line
                    if not at_end_of_line:
                        # Remove the duplicated text after cursor
                        end_pos = cursor.position()
                        cursor.setPosition(end_pos - len(text_after_cursor))
                        cursor.setPosition(end_pos, QtGui.QTextCursor.KeepAnchor)
                        cursor.removeSelectedText()
                    else:
                        # Position cursor after the indentation on the new line
                        cursor.movePosition(QtGui.QTextCursor.StartOfLine)
                        cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.MoveAnchor, len(indent))
                
                cursor.endEditBlock()
                self.setTextCursor(cursor)
                return True

        # Editor style
        editor_style = """
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #dddddd;
                border: 0px solid #444444;
                border-radius: 3px;
                padding: 5px 5px 5px 15px; /* Added significant left padding to prevent text from being under line numbers */
                font-family: Consolas, Monaco, monospace;
                selection-background-color: #264f78;
            }
        """
        
        # Create editors using the custom CodeEditor class
        self.python_editor = CodeEditor()
        self.python_editor.setStyleSheet(editor_style)
        self.python_highlighter = ScriptSyntaxHighlighter(self.python_editor.document())
        # Force document margin to create space for line numbers
        self.python_editor.document().setDocumentMargin(5)
        
        self.mel_editor = CodeEditor()
        self.mel_editor.setStyleSheet(editor_style)
        self.mel_highlighter = ScriptSyntaxHighlighter(self.mel_editor.document())
        # Force document margin to create space for line numbers
        self.mel_editor.document().setDocumentMargin(15)
        
        # Set tab width for both editors
        font = self.python_editor.font()
        font_metrics = QtGui.QFontMetrics(font)
        space_width = font_metrics.horizontalAdvance(' ')
        self.python_editor.setTabStopDistance(space_width * 4)
        self.mel_editor.setTabStopDistance(space_width * 4)
        
        # Create stacked widget for editors
        self.editor_stack = QtWidgets.QStackedWidget()
        self.editor_stack.setMinimumSize(100, 100)
        #self.editor_stack.setMinimumHeight(100)
        self.editor_stack.addWidget(self.python_editor)
        self.editor_stack.addWidget(self.mel_editor)

        # Apply Button
        self.apply_button = QtWidgets.QPushButton("Apply")
        self.apply_button.setFixedHeight(24)
        self.apply_button.setStyleSheet("""
            QPushButton {
                background-color: #5285a6;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 2px 10px;
            }
            QPushButton:hover {
                background-color: #77c2f2;
            }
        """)
        
        # Add widgets to layout
        self.frame_layout.addWidget(self.title_bar)
        self.frame_layout.addLayout(self.language_layout)
        self.frame_layout.addWidget(self.editor_stack)
        self.frame_layout.addWidget(self.apply_button)
        self.main_layout.addWidget(self.frame)
        
        # Connect signals
        self.close_button.clicked.connect(self.close)
        self.apply_button.clicked.connect(self.execute_code)
        self.python_button.toggled.connect(self.update_language_selection)
        self.mel_button.toggled.connect(self.update_language_selection)
        
        # Setup event handling for dragging and resizing
        self.dragging = False
        self.offset = None
        self.title_bar.mousePressEvent = self.title_bar_mouse_press
        self.title_bar.mouseMoveEvent = self.title_bar_mouse_move
        self.title_bar.mouseReleaseEvent = self.title_bar_mouse_release
        
        # Install event filter for the frame
        self.frame.setMouseTracking(True)
        self.frame.installEventFilter(self)
        
        self.picker_button = None
    #--------------------------------------------------------------------------------------------------------------------
    # Preset Functions
    #--------------------------------------------------------------------------------------------------------------------
    def ppf_match_ik_to_fk(self): # Match IK to FK
        preset_code = '''#Replace the ik_controls and fk_joints with your own names
ik_controls = ['@ns.ik_pole_ctrl', '@ns.ik_arm_or_leg_ctrl'] 
fk_joints = ['@ns.fk_upper_arm_or_leg_jnt', '@ns.fk_elbow_or_knee_jnt', '@ns.fk_wrist_or_ankle_jnt'] 
@match_ik_to_fk(ik_controls, fk_joints)'''
        
        # Insert code at the current cursor position
        cursor = self.python_editor.textCursor()
        cursor.insertText(preset_code)
        self.python_editor.setFocus()

    def ppf_match_fk_to_ik(self): # Match FK to IK
        preset_code = '''#Replace the fk_controls and ik_joints with your own names
fk_controls = ['@ns.fk_upper_arm_or_leg_ctrl', '@ns.fk_elbow_or_knee_ctrl', '@ns.fk_wrist_or_ankle_ctrl'] 
ik_joints = ['@ns.ik_upper_arm_or_leg_jnt', '@ns.ik_elbow_or_knee_jnt', '@ns.ik_wrist_or_ankle_jnt'] 
@match_fk_to_ik(fk_controls, ik_joints)'''
        
        # Insert code at the current cursor position
        cursor = self.python_editor.textCursor()
        cursor.insertText(preset_code)
        self.python_editor.setFocus()
    
    def ppf_set_attribute(self): # Match FK to IK
        preset_code = '''#Replace the Object, Attribute and Attribute Value with your own names
cmds.setAttr("@ns.Object.Attribute", AttributeValue)'''
        
        # Insert code at the current cursor position
        cursor = self.python_editor.textCursor()
        cursor.insertText(preset_code)
        self.python_editor.setFocus()

    def ppf_button_appearance(self): # Button Appearance
        preset_code = '''@TF.button_appearance(text=" ", opacity=1, selectable=1, target_buttons=None)'''
        
        # Insert code at the current cursor position
        cursor = self.python_editor.textCursor()
        cursor.insertText(preset_code)
        self.python_editor.setFocus()
        
    def ppf_get_selected_button_ids(self): # Get Selected Button IDs
        # Get the canvas from the picker button
        canvas = None
        if self.picker_button:
            canvas = self.picker_button.parent()
            
        if canvas:
            # Get all selected buttons
            selected_buttons = canvas.get_selected_buttons()
            
            # Extract button IDs
            button_ids = [button.unique_id for button in selected_buttons]
            
            # Create the preset code
            preset_code = f'''button_ids = {button_ids}'''
            
            # Insert code at the current cursor position
            cursor = self.python_editor.textCursor()
            cursor.insertText(preset_code)
            self.python_editor.setFocus()
    #--------------------------------------------------------------------------------------------------------------------
    def mel_preset_function_01(self):
        print('Mel Preset Function 01')

    def mpf_set_attribute(self): # Match FK to IK
        preset_code = '''#Replace the Object, Attribute and Attribute Value with your own names
setAttr "@ns.Object.Attribute" Attribute Value;'''
        
        # Insert code at the current cursor position
        cursor = self.mel_editor.textCursor()
        cursor.insertText(preset_code)
        self.mel_editor.setFocus()  
    #--------------------------------------------------------------------------------------------------------------------
    def set_picker_button(self, button):
        """Modified to ensure proper initialization of script data for individual buttons"""
        self.picker_button = button
        script_data = button.script_data if isinstance(button.script_data, dict) else {}
        
        # Create default script data if not properly formatted
        if not script_data:
            script_data = {
                'type': 'python',
                'python_code': '',
                'mel_code': '',
                'code': ''  # For backwards compatibility
            }
            
        # Set the editors' content from button-specific data
        self.python_editor.setPlainText(script_data.get('python_code', ''))
        self.mel_editor.setPlainText(script_data.get('mel_code', ''))
        
        # Set the correct language button based on stored type
        script_type = script_data.get('type', 'python')
        if script_type == 'python':
            self.python_button.setChecked(True)
        else:
            self.mel_button.setChecked(True)
        
        # Make sure to update the button's script data
        button.script_data = script_data
        
        self.position_window()

    def position_window(self):
        if self.picker_button:
            button_geometry = self.picker_button.geometry()
            scene_pos = self.picker_button.scene_position
            canvas = self.picker_button.parent()
            
            if canvas:
                canvas_pos = canvas.scene_to_canvas_coords(scene_pos)
                global_pos = canvas.mapToGlobal(canvas_pos.toPoint())
                self.move(global_pos) #+ QtCore.QPoint(button_geometry.width() + 10, 0))

    def update_language_selection(self, checked):
        if checked:  # Only respond to the button being checked
            is_python = self.python_button.isChecked()
            self.title_label.setText("Script Manager (Python)" if is_python else "Script Manager (MEL)")
            self.editor_stack.setCurrentIndex(0 if is_python else 1)
            self.function_preset_stack.setCurrentIndex(0 if is_python else 1)
            
    def execute_code(self):
        """Modified to ensure each button gets its own script data"""
        if self.picker_button:
            # Create fresh script data for this button
            script_data = {
                'type': 'python' if self.python_button.isChecked() else 'mel',
                'python_code': self.python_editor.toPlainText(),
                'mel_code': self.mel_editor.toPlainText(),
                'code': self.python_editor.toPlainText() if self.python_button.isChecked() else self.mel_editor.toPlainText()
            }
            
            # Update the button's script data
            self.picker_button.script_data = script_data
            self.picker_button.changed.emit(self.picker_button)
            self.close()
    #---------------------------------------------------------------------------------------
    def eventFilter(self, obj, event):
        if obj == self.frame:
            if event.type() == QtCore.QEvent.MouseMove:
                if not self.resizing:
                    pos = self.mapFromGlobal(self.frame.mapToGlobal(event.pos()))
                    if self.is_in_resize_range(pos):
                        self.update_cursor(pos)
                    else:
                        self.unsetCursor()
                return False
            elif event.type() == QtCore.QEvent.Leave:
                if not self.resizing:
                    self.unsetCursor()
                return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.resize_edge = self.get_resize_edge(event.pos())
            if self.resize_edge:
                self.resizing = True
                self.resize_start_pos = event.globalPos()
                self.initial_size = self.size()
                self.initial_pos = self.pos()
            else:
                self.resizing = False
        UT.maya_main_window().activateWindow()
    
    def mouseMoveEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton and self.resizing and self.resize_edge:
            delta = event.globalPos() - self.resize_start_pos
            new_geometry = self.geometry()
            
            if 'left' in self.resize_edge:
                new_width = max(self.minimumWidth(), self.initial_size.width() - delta.x())
                new_x = self.initial_pos.x() + delta.x()
                if new_width >= self.minimumWidth():
                    new_geometry.setLeft(new_x)
                
            if 'right' in self.resize_edge:
                new_width = max(self.minimumWidth(), self.initial_size.width() + delta.x())
                new_geometry.setWidth(new_width)
                
            if 'top' in self.resize_edge:
                new_height = max(self.minimumHeight(), self.initial_size.height() - delta.y())
                new_y = self.initial_pos.y() + delta.y()
                if new_height >= self.minimumHeight():
                    new_geometry.setTop(new_y)
                
            if 'bottom' in self.resize_edge:
                new_height = max(self.minimumHeight(), self.initial_size.height() + delta.y())
                new_geometry.setHeight(new_height)
            
            self.setGeometry(new_geometry)
        
        elif not self.resizing:
            if self.is_in_resize_range(event.pos()):
                self.update_cursor(event.pos())
            else:
                self.unsetCursor()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.resizing = False
            self.resize_edge = None
            self.unsetCursor()

    def closeEvent(self, event):
        super().closeEvent(event)
        UT.maya_main_window().activateWindow()

    def is_in_resize_range(self, pos):
        width = self.width()
        height = self.height()
        edge_size = self.resize_range

        return (pos.x() <= edge_size or 
                pos.x() >= width - edge_size or 
                pos.y() <= edge_size or 
                pos.y() >= height - edge_size)
    
    def get_resize_edge(self, pos):
        width = self.width()
        height = self.height()
        edge_size = self.resize_range
        
        is_top = pos.y() <= edge_size
        is_bottom = pos.y() >= height - edge_size
        is_left = pos.x() <= edge_size
        is_right = pos.x() >= width - edge_size
        
        if is_top and is_left: return 'top_left'
        if is_top and is_right: return 'top_right'
        if is_bottom and is_left: return 'bottom_left'
        if is_bottom and is_right: return 'bottom_right'
        if is_top: return 'top'
        if is_bottom: return 'bottom'
        if is_left: return 'left'
        if is_right: return 'right'
        return None

    def update_cursor(self, pos):
        edge = self.get_resize_edge(pos)
        cursor = QtCore.Qt.ArrowCursor
        
        if edge:
            cursor_map = {
                'top': QtCore.Qt.SizeVerCursor,
                'bottom': QtCore.Qt.SizeVerCursor,
                'left': QtCore.Qt.SizeHorCursor,
                'right': QtCore.Qt.SizeHorCursor,
                'top_left': QtCore.Qt.SizeFDiagCursor,
                'bottom_right': QtCore.Qt.SizeFDiagCursor,
                'top_right': QtCore.Qt.SizeBDiagCursor,
                'bottom_left': QtCore.Qt.SizeBDiagCursor
            }
            cursor = cursor_map.get(edge, QtCore.Qt.ArrowCursor)
        
        self.setCursor(cursor)
    #---------------------------------------------------------------------------------------
    # Window dragging methods
    def title_bar_mouse_press(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = True
            self.offset = event.globalPos() - self.pos()
        UT.maya_main_window().activateWindow()
            
    def title_bar_mouse_move(self, event):
        if self.dragging and event.buttons() == QtCore.Qt.LeftButton:
            self.move(event.globalPos() - self.offset)
            
    def title_bar_mouse_release(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = False
#--------------------------------------------------------------------------------------------------------------------
#--------------------------------------------------------------------------------------------------------------------
class PickerButton(QtWidgets.QWidget):
    deleted = Signal(object)
    selected = Signal(object, bool)
    changed = Signal(object)

    def __init__(self, label, parent=None, unique_id=None, color='#444444', opacity=1, width=80, height=30):
        super(PickerButton, self).__init__(parent)
        self.label = label
        self.unique_id = unique_id
        self.color = color
        self.opacity = opacity
        self.width = width
        self.height = height
        self.original_size = QtCore.QSize(self.width, self.height)
        self.setCursor(QtCore.Qt.OpenHandCursor)
        self.dragging = False
        self._scene_position = QtCore.QPointF(0, 0)
        self.border_radius = 3
        self.radius = [3, 3, 3, 3]  # [top_left, top_right, bottom_right, bottom_left]
        self.is_selected = False
        self.selectable = True  # Whether the button can be selected in select mode (not edit mode)
    
        self.setStyleSheet(f"QToolTip {{background-color: {UT.rgba_value(color,.8,alpha=1)}; color: #eeeeee ; border: none; border-radius: 3px;}}")
        
        self.edit_mode = False
        self.update_cursor()
        self.assigned_objects = []  

        self.mode = 'select'  # 'select', 'script', or 'pose'
        self.script_data = {}  # Store script data
        self.pose_data = {}  # Store pose data
        
        # Thumbnail image for pose mode
        self.thumbnail_path = ''  # Path to the thumbnail image
        self.thumbnail_pixmap = None  # Cached pixmap of the thumbnail
        
        # Cache for pose mode rendering
        self.pose_pixmap = None  # Cached pixmap for pose mode (thumbnail + text)

        # Pre-render text to pixmap for better performance
        self.text_pixmap = None
        self.last_zoom_factor = 0  # Track zoom factor to know when to regenerate the pixmap
        self.last_size = None      # Track size to know when to regenerate the pixmap

        self.update_tooltip()
    
    @property
    def scene_position(self):
        return self._scene_position

    @scene_position.setter
    def scene_position(self, pos):
        self._scene_position = pos
        if self.parent():
            self.parent().update_button_positions()    
    #---------------------------------------------------------------------------------------
    def _create_rounded_rect_path(self, rect, radii, zoom_factor):
        """Create a rounded rectangle path with the given corner radii.
        
        Args:
            rect (QRectF): Rectangle to create path for
            radii (list): List of 4 corner radii values [tl, tr, br, bl]
            zoom_factor (float): Current zoom factor
            
        Returns:
            QPainterPath: Path with rounded corners
        """
        path = QtGui.QPainterPath()
        
        # Apply zoom factor to radii
        zf = zoom_factor * 0.95
        tl, tr, br, bl = [radius * zf for radius in radii]
        
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
        
        return path
    
    def _calculate_thumbnail_rect(self, zoom_factor):
        """Calculate the rectangle for the thumbnail or placeholder.
        
        Args:
            zoom_factor (float): Current zoom factor
            
        Returns:
            QRectF: Rectangle for the thumbnail area
        """
        # Limit thumbnail size to ensure it doesn't overlap with text area
        max_thumbnail_height = self.height * 0.7  # Limit to 70% of button height
        thumbnail_width = self.width * 0.9  # 90% of button width
        thumbnail_size = min(thumbnail_width, max_thumbnail_height)
        
        # Position thumbnail in the upper part of the button, centered horizontally
        rect = QtCore.QRectF(
            (self.width - thumbnail_size) / 2.4,  # Center horizontally
            self.height * 0.04,  # Fixed position from top (4% of height)
            thumbnail_size,
            thumbnail_size
        )
        
        # Adjust for zoom factor
        return QtCore.QRectF(
            rect.x() * zoom_factor,
            rect.y() * zoom_factor,
            rect.width() * zoom_factor,
            rect.height() * zoom_factor
        )
    
    def _render_pose_pixmap(self, current_size, zoom_factor):
        """Render the pixmap for pose mode with thumbnail and text.
        
        Args:
            current_size (QSize): Current button size
            zoom_factor (float): Current zoom factor
            
        Returns:
            QPixmap: The rendered pose pixmap
        """
        # Create a new pixmap for pose mode
        pose_pixmap = QtGui.QPixmap(current_size)
        pose_pixmap.fill(QtCore.Qt.transparent)
        
        pose_painter = QtGui.QPainter(pose_pixmap)
        pose_painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pose_painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
        
        # Set up font for pose mode
        pose_painter.setPen(QtGui.QColor('white'))
        pose_font = pose_painter.font()
        font_size = (self.width * 0.15) * zoom_factor  # Smaller font based on width
        pose_font.setPixelSize(int(font_size))
        pose_painter.setFont(pose_font)
        
        # Calculate text area at bottom of button
        min_text_height = 12  # Minimum height in pixels
        text_height = max(int(self.height * 0.2), min_text_height)
        fixed_position_from_top = self.height * 0.75  # Bottom 20% of button
        
        text_rect = QtCore.QRectF(
            0,  # Start at left edge
            fixed_position_from_top * zoom_factor,  # Fixed position from top
            self.width * zoom_factor,  # Full width
            text_height * zoom_factor  # Height scaled with zoom
        )
        
        # Draw text at bottom
        pose_painter.drawText(text_rect, QtCore.Qt.AlignHCenter | QtCore.Qt.AlignBottom, self.label)
        
        # Get thumbnail area
        thumbnail_rect = self._calculate_thumbnail_rect(zoom_factor)
        
        # Create thumbnail path with same corner radius as button
        thumbnail_path = self._create_rounded_rect_path(
            thumbnail_rect, 
            [self.radius[0]] * 4,  # Same radius for all corners
            zoom_factor
        )
        
        # Draw tinted background for thumbnail area
        tinted_color = UT.rgba_value(self.color, 0.4, 0.8)  # 40% tint, 80% opacity
        pose_painter.setBrush(QtGui.QColor(tinted_color))
        pose_painter.setPen(QtCore.Qt.NoPen)
        pose_painter.drawPath(thumbnail_path)
        
        # Draw thumbnail or placeholder
        if self.thumbnail_path and (self.thumbnail_pixmap is not None) and not self.thumbnail_pixmap.isNull():
            # Set clipping path for the thumbnail
            pose_painter.setClipPath(thumbnail_path)
            
            # Scale the pixmap to fit within the thumbnail area
            scaled_pixmap = self.thumbnail_pixmap.scaled(
                int(thumbnail_rect.width()),
                int(thumbnail_rect.height()),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            
            # Center the image in the thumbnail area
            pixmap_rect = QtCore.QRectF(
                thumbnail_rect.x() + (thumbnail_rect.width() - scaled_pixmap.width()) / 2,
                thumbnail_rect.y() + (thumbnail_rect.height() - scaled_pixmap.height()) / 2,
                scaled_pixmap.width(),
                scaled_pixmap.height()
            )
            
            # Draw the thumbnail
            pose_painter.drawPixmap(pixmap_rect.toRect(), scaled_pixmap)
            pose_painter.setClipping(False)
        else:
            # Draw placeholder text
            pose_painter.setPen(QtGui.QColor(255, 255, 255, 120))
            pose_painter.drawText(thumbnail_rect, QtCore.Qt.AlignCenter, "Thumbnail")
            pose_painter.setPen(QtGui.QColor('white'))  # Reset pen color
        
        pose_painter.end()
        return pose_pixmap
    
    def _render_text_pixmap(self, current_size, zoom_factor):
        """Render the pixmap for regular mode with centered text.
        
        Args:
            current_size (QSize): Current button size
            zoom_factor (float): Current zoom factor
            
        Returns:
            QPixmap: The rendered text pixmap
        """
        text_pixmap = QtGui.QPixmap(current_size)
        text_pixmap.fill(QtCore.Qt.transparent)
        
        text_painter = QtGui.QPainter(text_pixmap)
        text_painter.setRenderHint(QtGui.QPainter.Antialiasing)
        text_painter.setRenderHint(QtGui.QPainter.TextAntialiasing)
        
        # Set up font
        text_painter.setPen(QtGui.QColor('white'))
        font = text_painter.font()
        font_size = (self.height * 0.5) * zoom_factor
        font.setPixelSize(int(font_size))
        text_painter.setFont(font)
        
        # Calculate text rect with padding
        text_rect = self.rect()
        bottom_padding = (self.height * 0.1) * zoom_factor
        text_rect.adjust(0, 0, 0, -int(bottom_padding))
        
        # Draw text centered
        text_painter.drawText(text_rect, QtCore.Qt.AlignCenter, self.label)
        text_painter.end()
        
        return text_pixmap
    
    def _should_update_pixmaps(self, zoom_factor, current_size):
        """Determine if pixmaps need to be updated.
        
        Args:
            zoom_factor (float): Current zoom factor
            current_size (QSize): Current button size
            
        Returns:
            bool: True if pixmaps need to be updated
        """
        # Check if pixmaps are missing or if zoom/size has changed significantly
        if self.mode == 'pose':
            pixmap_missing = self.pose_pixmap is None
        else:
            pixmap_missing = self.text_pixmap is None
            
        zoom_changed = abs(self.last_zoom_factor - zoom_factor) > 0.1
        size_changed = self.last_size != current_size
        
        return pixmap_missing or zoom_changed or size_changed
    
    def paintEvent(self, event):
        """Paint the button with background, selection border, and text/thumbnail.
        
        Args:
            event (QPaintEvent): The paint event
        """
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Get the current zoom factor from the parent canvas
        zoom_factor = self.parent().zoom_factor if self.parent() else 1.0

        # Draw button background
        if not self.is_selected:
            painter.setBrush(QtGui.QColor(self.color))
        else:
            painter.setBrush(QtGui.QColor(255, 255, 255, 120))
        
        # Apply the button's opacity
        painter.setOpacity(self.opacity)
        painter.setPen(QtCore.Qt.NoPen)

        # Create button path with rounded corners
        rect = self.rect().adjusted(zoom_factor, zoom_factor, -zoom_factor, -zoom_factor)
        path = self._create_rounded_rect_path(rect, self.radius, zoom_factor)
        painter.drawPath(path)

        # Draw selection border if selected
        if self.is_selected:
            if self.edit_mode:
                painter.setBrush(QtGui.QColor(self.color))
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 2)
                pen.setCosmetic(True)  # Fixed width regardless of zoom
                painter.setPen(pen)
                painter.drawPath(path)
            else:   
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 120), 1)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.drawPath(path)

        # Reset opacity for text/thumbnail rendering
        painter.setOpacity(1.0)
        
        # Check if pixmaps need to be updated
        current_size = self.size()
        if self._should_update_pixmaps(zoom_factor, current_size):
            self.last_zoom_factor = zoom_factor
            self.last_size = current_size
            
            # Render appropriate pixmap based on mode
            if self.mode == 'pose':
                self.pose_pixmap = self._render_pose_pixmap(current_size, zoom_factor)
                # Create an empty text_pixmap to avoid None checks
                self.text_pixmap = QtGui.QPixmap(current_size)
                self.text_pixmap.fill(QtCore.Qt.transparent)
            else:
                self.text_pixmap = self._render_text_pixmap(current_size, zoom_factor)
        
        # Draw the appropriate pixmap
        if self.mode == 'pose':
            if self.pose_pixmap and not self.pose_pixmap.isNull():
                painter.drawPixmap(0, 0, self.pose_pixmap)
        else:
            if self.text_pixmap and not self.text_pixmap.isNull():
                painter.drawPixmap(0, 0, self.text_pixmap)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            canvas = self.parent()
            if canvas:
                # Allow dragging only in edit mode
                if self.edit_mode:
                    self.dragging = True
                    self.drag_start_pos = event.globalPos()
                    self.button_start_pos = self.scene_position
                    self.setCursor(QtCore.Qt.ClosedHandCursor)
                    
                    selected_buttons = canvas.get_selected_buttons()
                    
                    if not self.is_selected and not (event.modifiers() & QtCore.Qt.ShiftModifier):
                        canvas.clear_selection()
                        canvas.buttons_in_current_drag.add(self)
                        self.is_selected = True
                        self.selected.emit(self, True)
                        canvas.last_selected_button = self  # Set as last selected
                        self.update()
                    elif event.modifiers() & QtCore.Qt.ShiftModifier:
                        canvas.buttons_in_current_drag.add(self)
                        self.is_selected = not self.is_selected
                        if self.is_selected:
                            canvas.last_selected_button = self  # Set as last selected if being selected
                        self.selected.emit(self, self.is_selected)
                        self.update()
                    
                    for button in selected_buttons:
                        button.button_start_pos = button.scene_position
                else:
                    if self.mode == 'select':
                        # Only allow selection if the button is selectable
                        if hasattr(self, 'selectable') and self.selectable:
                            # Existing selection behavior
                            canvas.buttons_in_current_drag.clear()
                            canvas.buttons_in_current_drag.add(self)
                            
                            if not event.modifiers() & QtCore.Qt.ShiftModifier:
                                canvas.clear_selection()
                            self.is_selected = not self.is_selected if event.modifiers() & QtCore.Qt.ShiftModifier else True
                            self.update()
                            
                            canvas.apply_final_selection(event.modifiers() & QtCore.Qt.ShiftModifier)
                    elif self.mode == 'script':
                        # script mode behavior
                        self.execute_script_command()
                    elif self.mode == 'pose':
                        # pose mode behavior
                        self.apply_pose()
                        
                
                event.accept()
        elif event.button() == QtCore.Qt.RightButton:
            if not self.is_selected:
                self.parent().clear_selection()
                self.toggle_selection()
            self.show_context_menu(event.pos())
            event.accept()
        else:
            super().mousePressEvent(event)
        UT.maya_main_window().activateWindow()

    def mouseMoveEvent(self, event):
        if self.dragging and event.buttons() & QtCore.Qt.LeftButton:
            canvas = self.parent()
            if not canvas:
                return

            delta = event.globalPos() - self.drag_start_pos
            scene_delta = QtCore.QPointF(delta.x(), delta.y()) / canvas.zoom_factor
            
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.scene_position = button.button_start_pos + scene_delta
            
            canvas.update_button_positions()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.dragging:
            self.dragging = False
            self.update_cursor()
            canvas = self.parent()
            if canvas:
                for button in canvas.get_selected_buttons():
                    canvas.update_button_data(button)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
        UT.maya_main_window().activateWindow()
    #---------------------------------------------------------------------------------------
    def update_cursor(self):
        if self.edit_mode:
            self.setCursor(QtCore.Qt.OpenHandCursor)
        else:
            self.setCursor(QtCore.Qt.ArrowCursor)
            
    def update_tooltip(self):
        """Update the tooltip with button information"""

        tooltip = f"<b><span style='font-size: 12px;'>Assigned Objects <span style='color: rgba(255, 255, 255, 0.6);'>({len(self.assigned_objects)})</span>:</b></span>"
        tooltip += f"<i><div style='text-align: left; font-size: 10px; color: rgba(255, 255, 255, 0.8); '> ID: [{self.unique_id}]</div></i>"

        if self.thumbnail_path:
            tooltip += f"<br><span style='font-size: 10px; color: rgba(255, 255, 255, 0.6);'>[{os.path.basename(self.thumbnail_path).split('.')[0]}]</span>"
        else:
            tooltip += f"<br><i><span style='font-size: 9px; color: rgba(255, 255, 255, 0.6);'>No thumbnail</span></i>"
        
        if self.assigned_objects:
            object_names = []
            
            # Use already resolved names from the database instead of resolving again
            for obj_data in self.assigned_objects:
                # Extract the short name directly from the long_name in the database
                long_name = obj_data['long_name']
                # Strip namespace for display
                short_name = long_name.split('|')[-1].split(':')[-1]
                object_names.append(short_name)
                
            
            if object_names:
                # Limit to first 10 objects and indicate if there are more
                if len(object_names) > 10:
                    displayed_objects = object_names[:10]
                    remaining_count = len(object_names) - 10
                    objects_str = "<br>- " + "<br>- ".join(displayed_objects)
                    objects_str += f"<br><span style='color: rgba(255, 255, 255, 0.5); font-size: 9px;'><i>...and {remaining_count} more object{'s' if remaining_count > 1 else ''}</i></span>"
                else:
                    objects_str = "<br>- " + "<br>- ".join(object_names)
                tooltip += objects_str
            else:
                tooltip += "<br>(No valid objects found)"
        else:
            tooltip += f"<br><i><span style='font-size: 9px; color: rgba(255, 255, 255, 0.6);'>No objects assigned</span></i>"
       
        # Button ID and mode
        
        tooltip += f"<div style='text-align: center; font-size: 10px; color: rgba(255, 255, 255, 0.5); '>({self.mode.capitalize()} mode)</div>"
        self.setToolTip(tooltip)   
    #---------------------------------------------------------------------------------------
    def set_mode(self, mode):
        canvas = self.parent()
        if canvas:
            # Apply mode change to all selected buttons
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                # Store original height before changing to pose mode
                if mode == 'pose' and button.mode != 'pose':
                    button._original_height = button.height
                    # Set height to 1.25 times width for pose mode
                    button.height = button.width * 1.25
                # Restore original height when changing from pose mode to another mode
                elif button.mode == 'pose' and mode != 'pose' and hasattr(button, '_original_height'):
                    button.height = button._original_height
                
                button.mode = mode
                button.update()
                button.changed.emit(button)
        else:
            # Fallback for single button if no canvas parent
            # Store original height before changing to pose mode
            if mode == 'pose' and self.mode != 'pose':
                self._original_height = self.height
                # Set height to 1.25 times width for pose mode
                self.height = self.width * 1.25
            # Restore original height when changing from pose mode to another mode
            elif self.mode == 'pose' and mode != 'pose' and hasattr(self, '_original_height'):
                self.height = self._original_height
                
            self.mode = mode

            
            self.update()
            self.changed.emit(self)

        self.pose_pixmap = None
        self.last_zoom_factor = 0
        self.last_size = None

    def toggle_selection(self):
        self.set_selected(not self.is_selected)
        if self.parent():
            self.parent().button_selection_changed.emit()

    def set_selected(self, selected):
        """Update selection state without triggering Maya selection"""
        if self.is_selected != selected:
            self.is_selected = selected
            self.selected.emit(self, self.is_selected)
            self.update()

    def update_visual_state(self, selected):
        """Update only the visual selection state"""
        if self.is_selected != selected:
            self.is_selected = selected
            self.update()
    #---------------------------------------------------------------------------------------
    def show_selection_manager(self):
        if not hasattr(self, 'selection_manager'):
            self.selection_manager = SelectionManagerWidget()
        
        self.selection_manager.set_picker_button(self)
        
        # Position widget to the right of the button
        pos = self.mapToGlobal(self.rect().topRight())
        self.selection_manager.move(pos + QtCore.QPoint(10, 0))
        self.selection_manager.show()

    def show_script_manager(self):
        if not hasattr(self, 'script_manager'):
            self.script_manager = ScriptManagerWidget()
        
        self.script_manager.set_picker_button(self)
        self.script_manager.show()

    def move_button_behind(self):
        """Move the selected buttons behind other buttons in the z-order"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if selected_buttons:
                # For each selected button, move it to the beginning of the buttons list
                for button in selected_buttons:
                    if button in canvas.buttons:
                        canvas.buttons.remove(button)
                        canvas.buttons.insert(0, button)  # Insert at the beginning (bottom of z-order)
                        # Ensure button is visually at the bottom of the stack
                        button.lower()
                        # Trigger data update
                        canvas.update_button_data(button)
                
                # Update the button positions and z-order
                canvas.update_button_positions()
                # Force a repaint
                canvas.update()
                
                # Update the main window data
                main_window = canvas.window()
                if hasattr(main_window, 'update_buttons_for_current_tab'):
                    main_window.update_buttons_for_current_tab()
    
    def bring_button_forward(self):
        """Bring the selected buttons forward in the z-order"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if selected_buttons:
                # For each selected button, move it to the end of the buttons list
                for button in selected_buttons:
                    if button in canvas.buttons:
                        canvas.buttons.remove(button)
                        canvas.buttons.append(button)  # Append to the end (top of z-order)
                        # Ensure button is visually at the top of the stack
                        button.raise_()
                        # Trigger data update
                        canvas.update_button_data(button)
                
                # Update the button positions and z-order
                canvas.update_button_positions()
                # Force a repaint
                canvas.update()
                
                # Update the main window data
                main_window = canvas.window()
                if hasattr(main_window, 'update_buttons_for_current_tab'):
                    main_window.update_buttons_for_current_tab()

    def show_context_menu(self, pos):
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
                padding: 3px 25px 3px 3px; ;
                margin: 3px 0px  ;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #2c4759;
            }''')

        # Mode selection
        mode_menu = QtWidgets.QMenu("Mode")
        mode_menu.setStyleSheet(menu.styleSheet())
        
        select_action = QtWidgets.QAction("Select Mode", self)
        select_action.setCheckable(True)
        select_action.setChecked(self.mode == 'select')
        select_action.triggered.connect(lambda: self.set_mode('select'))
        
        script_action = QtWidgets.QAction("Script Mode", self)
        script_action.setCheckable(True)
        script_action.setChecked(self.mode == 'script')
        script_action.triggered.connect(lambda: self.set_mode('script'))
        
        pose_action = QtWidgets.QAction("Pose Mode", self)
        pose_action.setCheckable(True)
        pose_action.setChecked(self.mode == 'pose')
        pose_action.triggered.connect(lambda: self.set_mode('pose'))
        
        mode_group = QtWidgets.QActionGroup(self)
        mode_group.addAction(select_action)
        mode_group.addAction(script_action)
        mode_group.addAction(pose_action)
        
        mode_menu.addAction(select_action)
        mode_menu.addAction(script_action)
        mode_menu.addAction(pose_action)
        
        
        # Copy, Paste and Delete Actions
        #---------------------------------------------------------------------------------------
        if self.edit_mode:
            # Add thumbnail options for pose mode buttons
            if self.mode == 'pose':
                thumbnail_menu = QtWidgets.QMenu("Thumbnail", menu)
                thumbnail_menu.setStyleSheet(menu.styleSheet())
                
                add_thumbnail_action = thumbnail_menu.addAction("Add Thumbnail")
                add_thumbnail_action.triggered.connect(self.add_thumbnail)

                select_thumbnail_action = thumbnail_menu.addAction("Select Thumbnail")
                select_thumbnail_action.triggered.connect(self.select_thumbnail)
                
                remove_thumbnail_action = thumbnail_menu.addAction("Remove Thumbnail")
                remove_thumbnail_action.triggered.connect(self.remove_thumbnail)
                remove_thumbnail_action.setEnabled(bool(self.thumbnail_path))
                
                menu.addMenu(thumbnail_menu)
            
            #---------------------------------------------------------------------------------------
            # Button placement submenu
            placement_menu = QtWidgets.QMenu("Placement", menu)
            placement_menu.setStyleSheet(menu.styleSheet())
            
            move_behind_action = placement_menu.addAction("Move Behind")
            move_behind_action.triggered.connect(self.move_button_behind)
            
            bring_forward_action = placement_menu.addAction("Bring Forward")
            bring_forward_action.triggered.connect(self.bring_button_forward)
            
            menu.addMenu(placement_menu)
            #---------------------------------------------------------------------------------------
            # Copy Action
            copy_action = menu.addAction(QtGui.QIcon(":/copyUV.png"), "Copy Button")
            copy_action.triggered.connect(self.copy_selected_buttons)
            
            #---------------------------------------------------------------------------------------
            # Create Paste submenu
            paste_menu = QtWidgets.QMenu("Paste Options", menu)
            paste_menu.setIcon(QtGui.QIcon(":/pasteUV.png"))
            paste_menu.setStyleSheet(menu.styleSheet())
            
            paste_all_action = paste_menu.addAction("Paste All")
            paste_all_action.triggered.connect(lambda: self.paste_attributes('all'))
            
            paste_dimension_action = paste_menu.addAction("Paste Dimension")
            paste_dimension_action.triggered.connect(lambda: self.paste_attributes('dimension'))
            
            paste_function_action = paste_menu.addAction("Paste Function")
            paste_function_action.triggered.connect(lambda: self.paste_attributes('function'))
            
            paste_text_action = paste_menu.addAction("Paste Text")
            paste_text_action.triggered.connect(lambda: self.paste_attributes('text'))
            
            # Enable/disable paste actions based on clipboard content
            has_clipboard = bool(ButtonClipboard.instance().get_last_attributes())
            paste_all_action.setEnabled(has_clipboard)
            paste_dimension_action.setEnabled(has_clipboard)
            paste_function_action.setEnabled(has_clipboard)
            paste_text_action.setEnabled(has_clipboard)
            
            menu.addMenu(paste_menu)
            #---------------------------------------------------------------------------------------
            # Delete Action
            delete_action = menu.addAction(QtGui.QIcon(":/delete.png"), "Delete Button")
            delete_action.triggered.connect(self.delete_selected_buttons)
        
        else:
            # Selection 
            #---------------------------------------------------------------------------------------
            if self.mode == 'select':
                # Selection Mode menu items
                add_to_selection_action = menu.addAction(QtGui.QIcon(":/addClip.png"), "Add Selection")
                add_to_selection_action.triggered.connect(self.add_selected_objects)

                remove_all_from_selection_action = menu.addAction(QtGui.QIcon(":/Mute_OFF.png"), "Remove all Selection")
                remove_all_from_selection_action.triggered.connect(self.remove_all_objects_for_selected_buttons)

                selection_manager_action = menu.addAction("Selection Manager")
                selection_manager_action.triggered.connect(self.show_selection_manager)
                selection_manager_action.setEnabled(
                    len(self.parent().get_selected_buttons()) == 1
                )
            elif self.mode == 'script':
                # Script Mode menu items
                script_manager_action = menu.addAction("Script Manager")
                script_manager_action.triggered.connect(self.show_script_manager)
            elif self.mode == 'pose':
                # Pose Mode menu items
                add_pose_action = menu.addAction("Add Pose")
                add_pose_action.triggered.connect(self.add_pose)
                
                remove_pose_action = menu.addAction("Remove Pose")
                remove_pose_action.triggered.connect(self.remove_pose)

                thumbnail_menu = QtWidgets.QMenu("Thumbnail")
                thumbnail_menu.setStyleSheet(menu.styleSheet())
                
                add_thumbnail_action = thumbnail_menu.addAction("Add Thumbnail")
                add_thumbnail_action.triggered.connect(self.add_thumbnail)

                select_thumbnail_action = thumbnail_menu.addAction("Select Thumbnail")
                select_thumbnail_action.triggered.connect(self.select_thumbnail)
                
                remove_thumbnail_action = thumbnail_menu.addAction("Remove Thumbnail")
                remove_thumbnail_action.triggered.connect(self.remove_thumbnail)
                remove_thumbnail_action.setEnabled(bool(self.thumbnail_path))
                
                menu.addMenu(thumbnail_menu)    
        
        menu.addMenu(mode_menu)
        menu.addSeparator()

        menu.exec_(self.mapToGlobal(pos))

    def color_button_clicked(self, color):
        self.change_color_for_selected_buttons(color)
    #---------------------------------------------------------------------------------------
    def copy_selected_buttons(self):
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            selected_buttons = canvas.get_selected_buttons()
            if selected_buttons:
                ButtonClipboard.instance().copy_buttons(selected_buttons)

    def paste_attributes(self, paste_type='all'):
        """Enhanced paste method that handles different types of paste operations"""
        canvas = self.parent()
        if canvas and canvas.edit_mode:
            attributes = ButtonClipboard.instance().get_last_attributes()
            if attributes:
                selected_buttons = canvas.get_selected_buttons()
                for button in selected_buttons:
                    if paste_type == 'all':
                        # Paste everything
                        button.label = attributes['label']
                        button.color = attributes['color']
                        button.opacity = attributes['opacity']
                        button.width = attributes['width']
                        button.height = attributes['height']
                        button.radius = attributes['radius'].copy()
                        button.assigned_objects = attributes.get('assigned_objects', []).copy()
                        button.mode = attributes.get('mode', 'select')
                        button.script_data = attributes.get('script_data', {}).copy()
                    elif paste_type == 'dimension':
                        # Paste only dimensions
                        button.width = attributes['width']
                        button.height = attributes['height']
                        button.radius = attributes['radius'].copy()
                    elif paste_type == 'function':
                        # Paste only functionality
                        button.assigned_objects = attributes.get('assigned_objects', []).copy()
                        button.mode = attributes.get('mode', 'select')
                        button.script_data = attributes.get('script_data', {}).copy()
                    elif paste_type == 'text':
                        # Paste only the label text
                        button.label = attributes['label']
                    
                    button.update()
                    button.update_tooltip()
                    button.changed.emit(button)
    #---------------------------------------------------------------------------------------
    def set_script_data(self, data):
        self.script_data = data
        self.changed.emit(self)
        self.update_tooltip()
        
    def add_pose(self):
        """Add current pose of selected objects to the pose data"""
        import maya.cmds as cmds
        
        # Get currently selected objects in Maya
        selected_objects = cmds.ls(selection=True, long=True)
        if not selected_objects:
            # Use custom dialog instead of QMessageBox
            dialog = CD.CustomDialog(self, title="No Selection", size=(200, 80), info_box=True)
            message_label = QtWidgets.QLabel("Please select objects in Maya before adding a pose.")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            dialog.exec_()
            return
        
        # First, add the selected objects to the button's assigned objects
        self.assigned_objects = []  # Clear existing assignments
        for obj in selected_objects:
            try:
                # Get the UUID for the object
                uuid = cmds.ls(obj, uuid=True)[0]
                # Add to assigned objects
                self.assigned_objects.append({
                    'uuid': uuid,
                    'long_name': obj
                })
            except:
                continue
        
        # Store the current attribute values for all assigned objects
        pose_data = {}
        
        for obj_data in self.assigned_objects:
            try:
                # Get the object from the data
                obj = obj_data['long_name']
                
                if cmds.objExists(obj):
                    # Extract the base name without namespace for storage
                    # This makes poses reusable across different namespaces
                    base_name = obj.split('|')[-1].split(':')[-1]
                    
                    # Get all keyable attributes
                    attrs = cmds.listAttr(obj, keyable=True) or []
                    attr_values = {}
                    
                    for attr in attrs:
                        try:
                            full_attr = f"{obj}.{attr}"
                            if cmds.objExists(full_attr):
                                attr_values[attr] = cmds.getAttr(full_attr)
                        except:
                            continue
                            
                    if attr_values:
                        # Store with base name for namespace compatibility
                        pose_data[base_name] = attr_values
            except:
                continue
        
        # Update the tooltip with the new assigned objects
        self.update_tooltip()
        
        if pose_data:
            # Use a simple default name - the button itself represents the pose
            self.pose_data = {"default": pose_data}  # Replace any existing poses with this one
            self.changed.emit(self)
            dialog = CD.CustomDialog(self, title="Pose Added", size=(200, 80), info_box=True)
            message_label = QtWidgets.QLabel("Pose has been added successfully.")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            #dialog.exec_()
        else:
            dialog = CD.CustomDialog(self, title="No Data", size=(200, 80), info_box=True)
            message_label = QtWidgets.QLabel("Could not capture any attribute data for the selected objects.")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            dialog.exec_()
    
    def remove_pose(self):
        """Remove the pose from the pose data and clear assigned objects"""
        if not self.pose_data:
            # Use custom dialog instead of QMessageBox
            dialog = CD.CustomDialog(self, title="No Pose", size=(200, 80), info_box=True)
            message_label = QtWidgets.QLabel("There is no pose to remove.")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            dialog.exec_()
            return
            
        # Clear the pose data
        self.pose_data = {}
        
        # Also clear assigned objects
        self.assigned_objects = []
        
        # Update the tooltip to reflect the changes
        self.update_tooltip()
        
        # Emit the changed signal
        self.changed.emit(self)
        
        dialog = CD.CustomDialog(self, title="Pose Removed", size=(200, 80), info_box=True)
        message_label = QtWidgets.QLabel("Pose and assigned objects have been removed.")
        message_label.setWordWrap(True)
        dialog.add_widget(message_label)
        dialog.add_button_box()
        dialog.exec_()
        
    def select_thumbnail(self):
        """Add a thumbnail image to selected pose buttons"""
        # Get the parent canvas and selected buttons
        canvas = self.parent()
        if not canvas:
            return
            
        selected_buttons = canvas.get_selected_buttons()
        # Filter to only include pose mode buttons
        pose_buttons = [button for button in selected_buttons if button.mode == 'pose']
        
        if not pose_buttons:
            # If no pose buttons are selected, just use this button if it's in pose mode
            if self.mode == 'pose':
                pose_buttons = [self]
            else:
                dialog = CD.CustomDialog(self, title="No Pose Buttons", size=(250, 100), info_box=True)
                message_label = QtWidgets.QLabel("No pose buttons selected. Please select at least one button in pose mode.")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
                return
        
        # Open file dialog to select an image
        # Get the thumbnail directory from data management
        data = DM.PickerDataManager.get_data()
        thumbnail_dir = data.get('thumbnail_directory', '')
        
        # If no thumbnail directory is set, use a dedicated directory in the ft_anim_picker environment
        if not thumbnail_dir:
            # Create a thumbnails directory in the ft_anim_picker environment
            script_dir = os.path.dirname(os.path.abspath(__file__))
            thumbnail_dir = os.path.join(script_dir, 'picker_thumbnails')
        
        # Make sure the directory exists
        if not os.path.exists(thumbnail_dir):
            try:
                os.makedirs(thumbnail_dir)
            except:
                thumbnail_dir = tempfile.gettempdir()

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Thumbnail Image", thumbnail_dir,
            "Image Files (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_path:
            # Load the image into a pixmap to verify it's valid
            test_pixmap = QtGui.QPixmap(file_path)
            if test_pixmap.isNull():
                dialog = CD.CustomDialog(self, title="Error", size=(200, 80), info_box=True)
                message_label = QtWidgets.QLabel("Failed to load the selected image.")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
                return
            
            # Apply the thumbnail to all selected pose buttons
            for button in pose_buttons:
                # Store the image path
                button.thumbnail_path = file_path
                
                # Load the image into a pixmap
                button.thumbnail_pixmap = QtGui.QPixmap(file_path)
                
                # Force regeneration of the pose_pixmap by invalidating cache parameters
                button.pose_pixmap = None
                button.last_zoom_factor = 0
                button.last_size = None
                
                # Update the button
                button.update()
                button.update_tooltip()
                button.changed.emit(button)
    
    def add_thumbnail(self):
        """Take a playblast of the current Maya viewport and use it as a thumbnail"""
        import maya.cmds as cmds
        import tempfile
        import os
        
        # Get the parent canvas and selected buttons
        canvas = self.parent()
        if not canvas:
            return
            
        selected_buttons = canvas.get_selected_buttons()
        # Filter to only include pose mode buttons
        pose_buttons = [button for button in selected_buttons if button.mode == 'pose']
        
        if not pose_buttons:
            # If no pose buttons are selected, just use this button if it's in pose mode
            if self.mode == 'pose':
                pose_buttons = [self]
            else:
                dialog = CD.CustomDialog(self, title="No Pose Buttons", size=(250, 100), info_box=True)
                message_label = QtWidgets.QLabel("No pose buttons selected. Please select at least one button in pose mode.")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
                return
        
        # Get the thumbnail directory from the main window
        main_window = None
        for widget in QtWidgets.QApplication.topLevelWidgets():
            if widget.__class__.__name__ == 'AnimPickerWindow':
                main_window = widget
                break
        
        # Get the thumbnail directory from data management
        data = DM.PickerDataManager.get_data()
        thumbnail_dir = data.get('thumbnail_directory', '')
        
        # If no thumbnail directory is set, use a dedicated directory in the ft_anim_picker environment
        if not thumbnail_dir:
            # Create a thumbnails directory in the ft_anim_picker environment
            script_dir = os.path.dirname(os.path.abspath(__file__))
            thumbnail_dir = os.path.join(script_dir, 'picker_thumbnails')
        
        # Make sure the directory exists
        if not os.path.exists(thumbnail_dir):
            try:
                os.makedirs(thumbnail_dir)
            except:
                thumbnail_dir = tempfile.gettempdir()
        
        # Generate a unique filename with sequential numbering
        # Find the highest existing thumbnail number
        highest_num = 0
        if os.path.exists(thumbnail_dir):
            for existing_file in os.listdir(thumbnail_dir):
                if existing_file.startswith('thumbnail_') and existing_file.endswith('.jpg'):
                    try:
                        # Extract the number part from the filename
                        num_part = existing_file.replace('thumbnail_', '').replace('.jpg', '')
                        if num_part.isdigit():
                            num = int(num_part)
                            highest_num = max(highest_num, num)
                    except:
                        pass
        
        # Create new filename with incremented number (3 digits format)
        next_num = highest_num + 1
        # Use just the base name without extension for playblast - Maya will add its own extension
        base_filename = f"thumbnail_{next_num:03d}"
        filepath = os.path.join(thumbnail_dir, base_filename)
        
        # Take the playblast using Maya's playblast command
        try:
            # Get the active panel
            panel = cmds.getPanel(withFocus=True)
            if not panel or 'modelPanel' not in cmds.getPanel(typeOf=panel):
                panel = cmds.getPanel(type="modelPanel")[0]
            
            # Get the active viewport dimensions to maintain aspect ratio
            active_view = None
            if panel and 'modelPanel' in cmds.getPanel(typeOf=panel):
                active_view = cmds.playblast(activeEditor=True)
            
            # Get viewport width and height
            viewport_width = cmds.control(active_view, query=True, width=True)
            viewport_height = cmds.control(active_view, query=True, height=True)
            
            # Calculate aspect ratio and adjust dimensions while keeping max dimension at 200px
            aspect_ratio = float(viewport_width) / float(viewport_height)
            img_size = 500
            if aspect_ratio >= 1.0:  # Wider than tall
                width = img_size
                height = int(img_size / aspect_ratio)
            else:  # Taller than wide
                height = img_size
                width = int(500 * aspect_ratio)
            
            cmds.playblast(
                frame=cmds.currentTime(query=True),
                format="image",
                compression="jpg",
                quality=100,
                width=width,
                height=height,
                percent=100,
                viewer=False,
                showOrnaments=False,
                filename=filepath,
                clearCache=True,
                framePadding=0
            )
            
            # Maya adds a frame number and extension to the filename, so we need to find the actual file
            dirname = os.path.dirname(filepath)
            basename = os.path.basename(filepath)
            
            # Find the generated file - Maya adds frame number and extension
            actual_filepath = None
            for f in os.listdir(dirname):
                # Look for files that start with our base filename and have an image extension
                if f.startswith(basename) and (f.endswith('.jpg') or f.endswith('.jpeg')):
                    actual_filepath = os.path.join(dirname, f)
                    break
                    
            if not actual_filepath:
                raise Exception("Could not find generated thumbnail image")
            
            # Load the original image into a pixmap
            original_pixmap = QtGui.QPixmap(actual_filepath)
            
            # Crop the image to a 1:1 aspect ratio (square)
            # Calculate the center and the size of the crop
            orig_width = original_pixmap.width()
            orig_height = original_pixmap.height()
            crop_size = min(orig_width, orig_height)
            
            # Calculate the crop rectangle centered in the image
            x_offset = (orig_width - crop_size) // 2
            y_offset = (orig_height - crop_size) // 2
            crop_rect = QtCore.QRect(x_offset, y_offset, crop_size, crop_size)
            
            # Crop the pixmap to a square
            cropped_pixmap = original_pixmap.copy(crop_rect)
            
            # Save the cropped square image with our intended filename format
            final_filename = f"thumbnail_{next_num:03d}.jpg"  # Use our sequential naming format
            final_filepath = os.path.join(thumbnail_dir, final_filename)
            cropped_pixmap.save(final_filepath, 'JPG', 100)
            
            # Remove the original playblast file to avoid clutter
            try:
                if os.path.exists(actual_filepath) and actual_filepath != final_filepath:
                    os.remove(actual_filepath)
            except Exception as e:
                print(f"Warning: Could not remove original playblast file: {e}")
            
            # Apply the thumbnail to all selected pose buttons
            for button in pose_buttons:
                # Store the image path with our clean naming format
                button.thumbnail_path = final_filepath
                
                # Set the thumbnail pixmap
                button.thumbnail_pixmap = cropped_pixmap
                
                # Force regeneration of the pose_pixmap by invalidating cache parameters
                button.pose_pixmap = None
                button.last_zoom_factor = 0
                button.last_size = None
                
                # Update the button
                button.update()
                button.update_tooltip()
                button.changed.emit(button)
                
            # No need to remove the original image as we've overwritten it with the square version
                
            
            
        except Exception as e:
            # Show error message
            dialog = CD.CustomDialog(self, title="Error", size=(250, 100), info_box=True)
            message_label = QtWidgets.QLabel(f"Failed to take playblast: {str(e)}")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            dialog.exec_()
    
    def remove_thumbnail(self):
        """Remove the thumbnail image from selected pose buttons"""
        # Get the parent canvas and selected buttons
        canvas = self.parent()
        if not canvas:
            return
            
        selected_buttons = canvas.get_selected_buttons()
        # Filter to only include pose mode buttons with thumbnails
        pose_buttons_with_thumbnails = [button for button in selected_buttons 
                                      if button.mode == 'pose' and button.thumbnail_path]
        
        if not pose_buttons_with_thumbnails:
            # If no pose buttons with thumbnails are selected, just use this button if applicable
            if self.mode == 'pose' and self.thumbnail_path:
                pose_buttons_with_thumbnails = [self]
            else:
                dialog = CD.CustomDialog(self, title="No Thumbnails", size=(250, 100), info_box=True)
                message_label = QtWidgets.QLabel("No pose buttons with thumbnails selected.")
                message_label.setWordWrap(True)
                dialog.add_widget(message_label)
                dialog.add_button_box()
                dialog.exec_()
                return
        
        # Remove thumbnails from all selected pose buttons
        for button in pose_buttons_with_thumbnails:
            # Clear the thumbnail data
            button.thumbnail_path = ''
            button.thumbnail_pixmap = None
            
            # Force regeneration of the pose_pixmap by invalidating cache parameters
            button.pose_pixmap = None
            button.last_zoom_factor = 0
            button.last_size = None
            
            # Update the button
            button.update()
            button.changed.emit(button)
            
    def apply_pose(self):
        """Apply the stored pose to the assigned objects"""
        # Import custom dialog
        
        
        if not self.pose_data:
            # Use custom dialog instead of QMessageBox
            dialog = CD.CustomDialog(self, title="No Pose", size=(200, 80), info_box=True)
            message_label = QtWidgets.QLabel("There is no pose to apply. Please add a pose first.")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            dialog.exec_()
            return
        
        # Get the pose data (we're only using the 'default' pose now)
        pose_data = self.pose_data.get("default", {})
        if not pose_data:
            # Use custom dialog instead of QMessageBox
            dialog = CD.CustomDialog(self, title="Empty Pose", size=(200, 80), info_box=True)
            message_label = QtWidgets.QLabel("Pose does not contain any data.")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            dialog.exec_()
            return
            
        # Apply the pose
        import maya.cmds as cmds
        
        # Get the current namespace from the main window
        current_namespace = None
        main_window = self.window()
        if hasattr(main_window, 'namespace_dropdown'):
            current_namespace = main_window.namespace_dropdown.currentText()
        
        # Start an undo chunk
        cmds.undoInfo(openChunk=True, chunkName="Apply Pose")
        
        # Keep track of successfully resolved objects for selection
        successfully_posed_objects = []
        
        try:
            # For each object in the pose data
            for obj, attr_values in pose_data.items():
                # Get the base name without namespace
                base_name = obj.split('|')[-1].split(':')[-1]
                resolved_obj = None
                
                # First try original object
                if cmds.objExists(obj):
                    resolved_obj = obj
                    
                # If that fails and we have a namespace, try with current namespace
                elif current_namespace and current_namespace != 'None':
                    namespaced_obj = f"{current_namespace}:{base_name}"
                    if cmds.objExists(namespaced_obj):
                        resolved_obj = namespaced_obj
                
                # Finally try just the base name
                elif cmds.objExists(base_name):
                    # Get the full path to avoid ambiguity when multiple objects have the same name
                    try:
                        # Get the full path with namespace to avoid ambiguity
                        full_paths = cmds.ls(base_name, long=True)
                        if full_paths:
                            resolved_obj = full_paths[0]  # Use the first match if multiple exist
                    except Exception:
                        resolved_obj = base_name  # Fallback to short name if ls fails
                    
                # If we found a valid object, apply the attributes
                if resolved_obj:
                    # Track this object for selection later - store the full path
                    try:
                        # Get the full path to ensure unique selection
                        full_path = cmds.ls(resolved_obj, long=True)[0]
                        successfully_posed_objects.append(full_path)
                    except Exception:
                        # Fallback to the resolved name if we can't get the full path
                        successfully_posed_objects.append(resolved_obj)
                    
                    # Set each attribute
                    for attr, value in attr_values.items():
                        try:
                            full_attr = f"{resolved_obj}.{attr}"
                            if cmds.objExists(full_attr):
                                # Check if the attribute is locked or connected
                                if not cmds.getAttr(full_attr, lock=True):
                                    # Check if it's a multi attribute (array)
                                    if isinstance(value, list):
                                        for i, val in enumerate(value):
                                            cmds.setAttr(f"{full_attr}[{i}]", val)
                                    else:
                                        cmds.setAttr(full_attr, value)
                        except Exception as e:
                            print(f"Error setting attribute {full_attr}: {e}")
                            continue
        except Exception as e:
            dialog = CD.CustomDialog(self, title="Error", size=(200, 80), info_box=True)
            message_label = QtWidgets.QLabel(f"Error applying pose: {e}")
            message_label.setWordWrap(True)
            dialog.add_widget(message_label)
            dialog.add_button_box()
            dialog.exec_()
        finally:
            # Close the undo chunk
            cmds.undoInfo(closeChunk=True)
            
            # Select all the objects that were successfully posed
            if successfully_posed_objects:
                try:
                    # Select all the objects that were actually modified by the pose
                    # This ensures we're selecting the exact objects in the correct namespace
                    cmds.select(successfully_posed_objects, replace=True)
                except Exception as e:
                    print(f"Error selecting posed objects: {e}")
    
    def execute_script_command(self):
        """Execute the script with namespace and match function token handling"""
        if self.mode == 'script' and self.script_data:
            script_type = self.script_data.get('type', 'python')
            
            # Get the appropriate code based on type
            if script_type == 'python':
                code = self.script_data.get('python_code', self.script_data.get('code', ''))
            else:
                code = self.script_data.get('mel_code', self.script_data.get('code', ''))
            
            if code:
                try:
                    # Get current namespace from picker window
                    main_window = self.window()
                    if isinstance(main_window, UI.AnimPickerWindow):
                        current_ns = main_window.namespace_dropdown.currentText()
                        ns_prefix = f"{current_ns}:" if current_ns and current_ns != 'None' else ""
                        
                        # Replace '@ns' tokens
                        modified_code = re.sub(r'@ns\.([a-zA-Z0-9_])', fr'{ns_prefix}\1', code)  # Replace @ns. followed by identifier
                        modified_code = re.sub(r'@ns\.(?!\w)', f'"{ns_prefix}"', modified_code)
                        
                        # Replace match function tokens with actual function calls
                        modified_code = re.sub(
                            r'@match_ik_to_fk\s*\((.*?)\)',
                            r'import ft_anim_picker.tool_functions as TF\nTF.match_ik_to_fk(\1)',
                            modified_code
                        )
                        modified_code = re.sub(
                            r'@match_fk_to_ik\s*\((.*?)\)',
                            r'import ft_anim_picker.tool_functions as TF\nTF.match_fk_to_ik(\1)',
                            modified_code
                        )
                        # Handle @TF.function_name(arguments) syntax with indentation preservation
                        modified_code = re.sub(
                            r'^(\s*)@TF\.([\w_]+)\s*\((.*?)\)',
                            r'\1import ft_anim_picker.tool_functions as TF\n\1TF.\2(\3)',
                            modified_code,
                            flags=re.MULTILINE  # Enable multiline mode to match at the start of each line
                        )
                        
                        # Execute the modified code
                        if script_type == 'python':
                            print(modified_code)
                            exec(modified_code)
                        else:
                            import maya.mel as mel
                            mel.eval(modified_code)
                except Exception as e:
                    cmds.warning(f"Error executing {script_type} code: {str(e)}")
    #---------------------------------------------------------------------------------------
    def set_size(self, width, height):
        self.width = width
        
        # In pose mode, height is always 1.25 times the width
        if self.mode == 'pose':
            # Store the provided height as original height for later use
            self._original_height = height
            # Force height to be 1.25 times width in pose mode
            self.height = width * 1.25
        else:
            self.height = height
            
        self.original_size = QtCore.QSize(self.width, self.height)
        self.update()
        self.changed.emit(self)
    
    def set_radius(self, top_left, top_right, bottom_right, bottom_left):
        self.radius = [top_left, top_right, bottom_right, bottom_left]
        self.update()
        self.changed.emit(self)

    def change_color(self, color):
        self.color = color
        self.update()
        self.changed.emit(self)  # Emit changed signal

    def change_opacity(self, value):
        self.opacity = value / 100.0
        self.update()
        self.changed.emit(self)  # Emit changed signal

    def rename_button(self, new_label):
        #if new_label and new_label != self.label:
        self.label = new_label
        self.setToolTip(f"Label: {self.label}\nSelect Set\nID: {self.unique_id}")
        # Force regeneration of text pixmap
        self.text_pixmap = None
        self.update()
        self.changed.emit(self)
    
    def delete_button(self):
        '''reply = QtWidgets.QMessageBox.question(self, "Delete Button", 
                                               "Are you sure you want to delete this button?",
                                               QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                               QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:'''
        self.deleted.emit(self)
        self.deleteLater()
    #---------------------------------------------------------------------------------------
    def rename_selected_buttons(self, new_label):
        canvas = self.parent()
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.rename_button(new_label)
            
            # Update the main window
            main_window = canvas.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                main_window.update_buttons_for_current_tab()
        
    def change_color_for_selected_buttons(self, new_color):
        canvas = self.parent()
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.change_color(new_color)
            
            # Update the main window
            main_window = canvas.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                main_window.update_buttons_for_current_tab()
    
    def change_opacity_for_selected_buttons(self, value):
        canvas = self.parent()
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            opacity = value #/ 100.0
            for button in selected_buttons:
                button.change_opacity(opacity)
            
            # Update the main window
            main_window = canvas.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                main_window.update_buttons_for_current_tab()

    def delete_selected_buttons(self):
        canvas = self.parent()
        if canvas:
            
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.delete_button()
                #canvas.remove_button(button)
            
            # Update the main window
            main_window = canvas.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                main_window.update_buttons_for_current_tab()
    #---------------------------------------------------------------------------------------
    def add_selected_objects(self):
        """Store both UUID and long name for selected objects"""
        selected = cmds.ls(selection=True, long=True)
        if selected:
            # Create a list of {uuid, long_name} pairs for selected objects
            new_objects = []
            for obj in selected:
                try:
                    uuid = cmds.ls(obj, uuid=True)[0]
                    new_objects.append({
                        'uuid': uuid,
                        'long_name': obj
                    })
                except:
                    continue
                    
            # Add new objects to existing list, avoiding duplicates by UUID
            existing_uuids = {obj['uuid'] for obj in self.assigned_objects}
            self.assigned_objects.extend([obj for obj in new_objects if obj['uuid'] not in existing_uuids])
            self.update_tooltip()
            self.changed.emit(self)
    
    def convert_assigned_objects(self, objects):
        """Convert old format (UUID only) to new format (UUID + long name)"""
        converted_objects = []
        for obj in objects:
            # Check if object is already in new format
            if isinstance(obj, dict) and 'uuid' in obj and 'long_name' in obj:
                converted_objects.append(obj)
            else:
                # Old format - only UUID
                try:
                    nodes = cmds.ls(obj, long=True)
                    if nodes:
                        converted_objects.append({
                            'uuid': obj,
                            'long_name': nodes[0]
                        })
                    else:
                        # If can't resolve UUID, still store it with empty long name
                        converted_objects.append({
                            'uuid': obj,
                            'long_name': ''
                        })
                except:
                    continue
        return converted_objects

    def remove_all_objects(self):
        self.assigned_objects = []
        self.update_tooltip()
        self.changed.emit(self)  # Notify about the change to update data
    
    def remove_all_objects_for_selected_buttons(self):
        canvas = self.parent()
        if canvas:
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.assigned_objects = []
                button.update_tooltip()
                button.changed.emit(button)  # Notify about the change to update data