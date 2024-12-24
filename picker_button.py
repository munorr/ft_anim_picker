from functools import partial
import maya.cmds as cmds
import maya.mel as mel
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
from . import script_manager as SM
from . import tool_functions as TF

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
                self.copied_buttons.append({
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
                })

    def get_last_attributes(self):
        if self.copied_buttons:
            return self.copied_buttons[-1]
        return None

    def get_all_buttons(self):
        return self.copied_buttons

class SelectionManagerWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(SelectionManagerWidget, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool)
        # Always stay on top of the parent window
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
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
        """Refresh the list with human-readable object names, stripping namespaces"""
        self.selection_list.clear()
        if self.picker_button:
            for uuid in self.picker_button.assigned_objects:
                try:
                    # Get current node name from UUID
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
        if self.picker_button:
            self.picker_button.add_selected_objects()
            self.refresh_list()
            
    def remove_selection(self):
        """Remove selected objects using stored UUIDs"""
        if self.picker_button:
            selected_items = self.selection_list.selectedItems()
            selected_uuids = [item.data(QtCore.Qt.UserRole) for item in selected_items]
            
            # Remove selected objects from picker button using UUIDs
            self.picker_button.assigned_objects = [
                uuid for uuid in self.picker_button.assigned_objects 
                if uuid not in selected_uuids
            ]
            
            self.picker_button.update_tooltip()
            self.picker_button.changed.emit(self.picker_button)
            self.refresh_list()

    # Window dragging methods
    def title_bar_mouse_press(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = True
            self.offset = event.globalPos() - self.pos()
            
    def title_bar_mouse_move(self, event):
        if self.dragging and event.buttons() == QtCore.Qt.LeftButton:
            self.move(event.globalPos() - self.offset)
            
    def title_bar_mouse_release(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = False
#--------------------------------------------------------------------------------------------------------------------
class ScriptSyntaxHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, parent=None):
        super(ScriptSyntaxHighlighter, self).__init__(parent)
        
        # Create format for special tokens
        self.special_format = QtGui.QTextCharFormat()
        self.special_format.setForeground(QtGui.QColor("#91CB08"))  # Bright green color
        self.special_format.setFontWeight(QtGui.QFont.Bold)

        # Create format for special tokens 2
        self.special_format_02 = QtGui.QTextCharFormat()
        self.special_format_02.setForeground(QtGui.QColor("#10b1cc"))  
        self.special_format_02.setFontWeight(QtGui.QFont.Bold)
   
        # Create format for comments
        self.comment_format = QtGui.QTextCharFormat()
        self.comment_format.setForeground(QtGui.QColor("#555555"))  # Gray color for comments

        # Create format for quoted text in comments
        self.quoted_text_format = QtGui.QTextCharFormat()
        self.quoted_text_format.setForeground(QtGui.QColor("#ce9178"))
        
    def highlightBlock(self, text):
        # Define all special tokens to highlight
        special_patterns = [
            r'@match_ik_to_fk\s*\([^)]*\)',  # Match @match_ik_to_fk() with any parameters
            r'@match_fk_to_ik\s*\([^)]*\)',   # Match @match_fk_to_ik() with any parameters
        ]
        special_patterns_02 = [r'@ns\.'] # Original @ns pattern
        
        # Apply highlighting for special patterns
        for pattern in special_patterns:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), len(match.group()), self.special_format)
        
        for pattern in special_patterns_02:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), len(match.group()), self.special_format_02)
        
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

                for pattern in special_patterns_02:
                    for match in re.finditer(pattern, text):
                        self.setFormat(match.start(), len(match.group()), self.special_format_02)
        
        # Handle single quotes
        single_quote_pattern = r'\'[^\'\\]*(?:\\.[^\'\\]*)*\''
        for match in re.finditer(single_quote_pattern, text):
            # Don't highlight quotes in comments
            start_pos = match.start()
            if not self.format(start_pos) == self.comment_format:
                self.setFormat(start_pos, len(match.group()), self.quoted_text_format)

                for pattern in special_patterns_02:
                    for match in re.finditer(pattern, text):
                        self.setFormat(match.start(), len(match.group()), self.special_format_02)
        
class ScriptManagerWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(ScriptManagerWidget, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool)
        self.setWindowFlag(QtCore.Qt.WindowStaysOnTopHint)
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

        # Create custom QPlainTextEdit subclass for tab handling
        class CodeEditor(QtWidgets.QPlainTextEdit):
            def keyPressEvent(self, event):
                if event.key() == QtCore.Qt.Key_Tab:
                    cursor = self.textCursor()
                    if cursor.hasSelection():
                        # Get start and end positions
                        start = cursor.selectionStart()
                        end = cursor.selectionEnd()
                        
                        # Ensure we have the correct cursor positions
                        cursor.setPosition(start)
                        start_block = cursor.blockNumber()
                        cursor.setPosition(end)
                        end_block = cursor.blockNumber()
                        
                        # Handle shift+tab (unindent)
                        if event.modifiers() & QtCore.Qt.ShiftModifier:
                            cursor.beginEditBlock()
                            for _ in range(end_block - start_block + 1):
                                cursor.movePosition(QtGui.QTextCursor.StartOfLine)
                                # Check if line starts with spaces
                                line_text = cursor.block().text()
                                if line_text.startswith("    "):
                                    cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor, 4)
                                    cursor.removeSelectedText()
                                elif line_text.startswith(" "):
                                    # Remove any remaining spaces less than 4
                                    spaces = len(line_text) - len(line_text.lstrip())
                                    cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor, min(4, spaces))
                                    cursor.removeSelectedText()
                                cursor.movePosition(QtGui.QTextCursor.NextBlock)
                            cursor.endEditBlock()
                        else:
                            # Normal tab (indent)
                            cursor.beginEditBlock()
                            for _ in range(end_block - start_block + 1):
                                cursor.movePosition(QtGui.QTextCursor.StartOfLine)
                                # Only add indent if not doing Shift+Tab
                                if not event.modifiers() & QtCore.Qt.ShiftModifier:
                                    cursor.insertText("    ")
                                else:
                                    # Remove indent on Shift+Tab
                                    line_text = cursor.block().text()
                                    if line_text.startswith("    "):
                                        cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor, 4)
                                        cursor.removeSelectedText()
                                    elif line_text.startswith(" "):
                                        spaces = len(line_text) - len(line_text.lstrip())
                                        cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor, min(4, spaces))
                                        cursor.removeSelectedText()
                                cursor.movePosition(QtGui.QTextCursor.NextBlock)
                            cursor.endEditBlock()
                    else:
                        # No selection, just handle single line
                        if event.modifiers() & QtCore.Qt.ShiftModifier:
                            # Remove indent on Shift+Tab
                            cursor.movePosition(QtGui.QTextCursor.StartOfLine)
                            line_text = cursor.block().text()
                            if line_text.startswith("    "):
                                cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor, 4)
                                cursor.removeSelectedText()
                            elif line_text.startswith(" "):
                                spaces = len(line_text) - len(line_text.lstrip())
                                cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.KeepAnchor, min(4, spaces))
                                cursor.removeSelectedText()
                        else:
                            # Add indent on normal Tab
                            cursor.insertText("    ")
                else:
                    super().keyPressEvent(event)

        # Editor style
        editor_style = """
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #dddddd;
                border: 0px solid #444444;
                border-radius: 3px;
                padding: 5px;
                font-family: Consolas, Monaco, monospace;
                selection-background-color: #264f78;
            }
        """
        
        # Create editors using the custom CodeEditor class
        self.python_editor = CodeEditor()
        self.python_editor.setStyleSheet(editor_style)
        self.python_highlighter = ScriptSyntaxHighlighter(self.python_editor.document())
        
        self.mel_editor = CodeEditor()
        self.mel_editor.setStyleSheet(editor_style)
        self.mel_highlighter = ScriptSyntaxHighlighter(self.mel_editor.document())
        
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
        
        # Get current text and append new code with a newline if there's existing content
        current_text = self.python_editor.toPlainText()
        if current_text:
            self.python_editor.setPlainText(current_text + '\n' + preset_code)
        else:
            self.python_editor.setPlainText(preset_code)

    def ppf_match_fk_to_ik(self): # Match FK to IK
        preset_code = '''#Replace the fk_controls and ik_joints with your own names
fk_controls = ['@ns.fk_upper_arm_or_leg_ctrl', '@ns.fk_elbow_or_knee_ctrl', '@ns.fk_wrist_or_ankle_ctrl'] 
ik_joints = ['@ns.ik_upper_arm_or_leg_jnt', '@ns.ik_elbow_or_knee_jnt', '@ns.ik_wrist_or_ankle_jnt'] 
@match_fk_to_ik(fk_controls, ik_joints)'''
        
        # Get current text and append new code with a newline if there's existing content
        current_text = self.python_editor.toPlainText()
        if current_text:
            self.python_editor.setPlainText(current_text + '\n' + preset_code)
        else:
            self.python_editor.setPlainText(preset_code)
    
    def ppf_set_attribute(self): # Match FK to IK
        preset_code = '''#Replace the Object, Attribute and Attribute Value with your own names
cmds.setAttr("@ns.Object.Attribute", AttributeValue)'''
        
        # Get current text and append new code with a newline if there's existing content
        current_text = self.python_editor.toPlainText()
        if current_text:
            self.python_editor.setPlainText(current_text + '\n' + preset_code)
        else:
            self.python_editor.setPlainText(preset_code)
    #--------------------------------------------------------------------------------------------------------------------
    def mel_preset_function_01(self):
        print('Mel Preset Function 01')

    def mpf_set_attribute(self): # Match FK to IK
        preset_code = '''#Replace the Object, Attribute and Attribute Value with your own names
setAttr "@ns.Object.Attribute" Attribute Value;'''
        
        # Get current text and append new code with a newline if there's existing content
        current_text = self.mel_editor.toPlainText()
        if current_text:
            self.mel_editor.setPlainText(current_text + '\n' + preset_code)
        else:
            self.mel_editor.setPlainText(preset_code)
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
            
    def title_bar_mouse_move(self, event):
        if self.dragging and event.buttons() == QtCore.Qt.LeftButton:
            self.move(event.globalPos() - self.offset)
            
    def title_bar_mouse_release(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = False
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
    

        self.setStyleSheet(f"QToolTip {{background-color: {UT.rgba_value(color,.8,alpha=1)}; color: #eeeeee ; border: none; border-radius: 3px;}}")
        
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        #self.setToolTip(f"Label: {self.label}\nSelect Set\nID: {self.unique_id}")
        self.setToolTip(f"Select Set\nID: [{self.unique_id}]")

        self.edit_mode = False
        self.update_cursor()
        self.assigned_objects = []  

        self.mode = 'select'  # 'select' or 'script'
        self.script_data = {}  # Store script data

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
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        # Get the current zoom factor from the parent canvas
        zoom_factor = self.parent().zoom_factor  if self.parent() else 1.0

        # Draw button background
        if not self.is_selected:
            painter.setBrush(QtGui.QColor(self.color))
        else:
            painter.setBrush(QtGui.QColor(255, 255, 255, 120))
            
        painter.setOpacity(self.opacity)
        painter.setPen(QtCore.Qt.NoPen)

        # Create a path with individual corner radii adjusted for zoom
        path = QtGui.QPainterPath()
        rect = self.rect().adjusted(zoom_factor, zoom_factor, -zoom_factor, -zoom_factor)
        
        # Adjust radii for zoom
        transition = 1 / (1 + math.exp(-6 * (zoom_factor - .3)))
        scale_factor = 0.2* (1 - transition) + 0.96 * transition
        #zf = zoom_factor * .7 if zoom_factor <= 1 else zoom_factor *.96
        zf = zoom_factor *.95#* scale_factor

        tl = self.radius[0] * zf 
        tr = self.radius[1] * zf
        br = self.radius[2] * zf
        bl = self.radius[3] * zf

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

        painter.drawPath(path)

        # Draw selection border if selected
        if self.is_selected:
            if self.edit_mode:
                painter.setBrush(QtGui.QColor(self.color))
                pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 2)
                #pen.setWidth(2)  # Increased border width
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
        font_size = (self.height * 0.5) * zoom_factor
        font.setPixelSize(int(font_size))
        painter.setFont(font)

        # Calculate text rect with padding
        text_rect = self.rect()
        bottom_padding = (self.height * 0.1) * zoom_factor  # 10% of height for bottom padding
        text_rect.adjust(0, 0, 0, -int(bottom_padding))

        painter.drawText(text_rect, QtCore.Qt.AlignCenter, self.label)
    
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
                        # Existing selection behavior
                        canvas.buttons_in_current_drag.clear()
                        canvas.buttons_in_current_drag.add(self)
                        
                        if not event.modifiers() & QtCore.Qt.ShiftModifier:
                            canvas.clear_selection()
                        self.is_selected = not self.is_selected if event.modifiers() & QtCore.Qt.ShiftModifier else True
                        self.update()
                        
                        canvas.apply_final_selection(event.modifiers() & QtCore.Qt.ShiftModifier)
                    else:
                        # script mode behavior
                        self.execute_script_command()
                
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
    #---------------------------------------------------------------------------------------
    def set_mode(self, mode):
        canvas = self.parent()
        if canvas:
            # Apply mode change to all selected buttons
            selected_buttons = canvas.get_selected_buttons()
            for button in selected_buttons:
                button.mode = mode
                button.update()
                button.changed.emit(button)
        else:
            # Fallback for single button if no canvas parent
            self.mode = mode
            self.update()
            self.changed.emit(self)

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
    def update_tooltip(self):
        """Update tooltip using node names resolved from UUIDs, stripping namespaces"""
        base_tooltip = f"(Assigned Objects):"
        if self.assigned_objects:
            try:
                object_names = []
                for uuid in self.assigned_objects:
                    try:
                        node = cmds.ls(uuid, long=True)[0]
                        # Strip namespace by taking the last part after any ':'
                        short_name = node.split('|')[-1].split(':')[-1]
                        object_names.append(short_name)
                    except:
                        # Handle case where object no longer exists
                        continue
                objects_str = "\n- " + "\n- ".join(object_names)
                base_tooltip += objects_str
            except:
                base_tooltip += "\nError resolving object names"
        self.setToolTip(base_tooltip)

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
                padding: 3px 15px 3px 3px; ;
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
        
        mode_group = QtWidgets.QActionGroup(self)
        mode_group.addAction(select_action)
        mode_group.addAction(script_action)
        
        mode_menu.addAction(select_action)
        mode_menu.addAction(script_action)
        
        
        # Copy, Paste and Delete Actions
        #---------------------------------------------------------------------------------------
        if self.edit_mode:
            copy_action = menu.addAction(QtGui.QIcon(":/copyUV.png"), "Copy Button")
            copy_action.triggered.connect(self.copy_selected_buttons)
            
            # Create Paste submenu
            paste_menu = QtWidgets.QMenu("Paste Options", menu)
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
            else:
                # Script Mode menu items
                script_manager_action = menu.addAction("Script Manager")
                script_manager_action.triggered.connect(self.show_script_manager)
        
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
                        
                        # Execute the modified code
                        if script_type == 'python':
                            exec(modified_code)
                        else:
                            import maya.mel as mel
                            mel.eval(modified_code)
                except Exception as e:
                    cmds.warning(f"Error executing {script_type} code: {str(e)}")
    #---------------------------------------------------------------------------------------
    def set_size(self, width, height):
        self.width = width
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
        """Store UUIDs of selected objects instead of long names"""
        selected = cmds.ls(selection=True, uuid=True)
        if selected:
            self.assigned_objects = list(set(self.assigned_objects + selected))
            self.update_tooltip()
            self.changed.emit(self)

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