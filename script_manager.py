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
import math
import re
from . import utils as UT
from . import custom_button as CB
from . import data_management as DM
from . import ui as UI
#-----------------------------------------------------------------------------------------------------------

class HighlightRule:
    def __init__(self, pattern, format_config, editors=None):
        """
        Initialize a highlighting rule
        
        Args:
            pattern (str): Regular expression pattern to match
            format_config (dict): Configuration for text formatting {
                'color': str (hex color),
                'bold': bool,
                'italic': bool
            }
            editors (list): List of editor types where this rule applies ('python', 'mel', or both)
        """
        self.pattern = pattern
        self.format = QtGui.QTextCharFormat()
        
        # Apply formatting based on config
        if 'color' in format_config:
            self.format.setForeground(QtGui.QColor(format_config['color']))
        if format_config.get('bold', False):
            self.format.setFontWeight(QtGui.QFont.Bold)
        if format_config.get('italic', False):
            self.format.setFontItalic(True)
            
        self.editors = editors if editors else ['python', 'mel']

class ScriptSyntaxHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, parent=None, editor_type='python'):
        """
        Initialize the syntax highlighter
        
        Args:
            parent: Parent QTextDocument
            editor_type (str): Type of editor ('python' or 'mel')
        """
        super(ScriptSyntaxHighlighter, self).__init__(parent)
        self.editor_type = editor_type
        self.highlight_rules = []
        self.special_commands = {}
        self.script_manager = None
        
        # Initialize with default rules
        self.setup_default_rules()
    
    def set_script_manager(self, manager):
        """Set the reference to the script manager widget"""
        self.script_manager = manager

    def setup_default_rules(self):
        """Set up default highlighting rules"""
        #-----------------------------------------------------------------------------------------------------------
        # Python keywords 1 (only for Python editor)
        python_keywords_1 = ['def', 'True', 'False', 'None','is','not']
        
        self.add_highlight_rule(
            pattern=r'\b(' + '|'.join(python_keywords_1) + r')\b',
            format_config={
                'color': '#569cd6',
                'bold': True
            },
            editors=['python']
        )
        #-----------------------------------------------------------------------------------------------------------
        # Python keywords 2 (only for Python editor)
        python_keywords_2 = ['class', 'for', 'while', 'if', 'else', 'elif', 
                         'try', 'except', 'finally', 'with', 'import', 'from', 
                         'as', 'return', 'yield', 'break', 'continue', 'pass',
                         'raise']
        
        self.add_highlight_rule(
            pattern=r'\b(' + '|'.join(python_keywords_2) + r')\b',
            format_config={
                'color': '#c586c0',
                'bold': True
            },
            editors=['python']
        )
        #-----------------------------------------------------------------------------------------------------------
        # Python keywords 3 (only for Python editor)
        python_keywords_3 = ['cmds','mel']
        
        self.add_highlight_rule(
            pattern=r'\b(' + '|'.join(python_keywords_3) + r')\b',
            format_config={
                'color': '#4ec995',
                'bold': True
            },
            editors=['python']
        )
        #-----------------------------------------------------------------------------------------------------------
        # MEL keywords 1 (only for MEL editor)
        mel_keywords_1 = ['proc', 'global', 'string', 'int', 'float', 'vector',
                       'matrix', 'if', 'else', 'for', 'while', 'switch', 'case',
                       'default', 'break', 'continue', 'return']
        
        self.add_highlight_rule(
            pattern=r'\b(' + '|'.join(mel_keywords_1) + r')\b',
            format_config={
                'color': '#c586c0',
                'bold': True
            },
            editors=['mel']
        )
        #-----------------------------------------------------------------------------------------------------------
        # MEL keywords 2 (only for MEL editor)
        mel_keywords_2 = ['setAttr', 'getAttr', 'addAttr', 'connectAttr', 'disconnectAttr',
                       'createNode', 'delete', 'file', 'eval', 'source', 'python',
                       'select', 'ls', 'fileDialog', 'confirmDialog', 'progressWindow',
                       'optionVar', 'intField', 'floatField', 'textField', 'button',
                       'checkBox', 'radioButtonGrp', 'columnLayout', 'rowLayout',
                       'text', 'scrollLayout']
        
        self.add_highlight_rule(
            pattern=r'\b(' + '|'.join(mel_keywords_2) + r')\b',
            format_config={
                'color': '#14deff',
                'bold': True
            },
            editors=['mel']
        )
        #-----------------------------------------------------------------------------------------------------------
        
        # Numbers (both editors)
        self.add_highlight_rule(
            pattern=r'\b\d+\b',
            format_config={
                'color': '#b5cea8'
            }
        )
        
        # String literals (both editors)
        self.add_highlight_rule(
            pattern=r'\".*?\"',
            format_config={
                'color': '#c3915b'
            }
        )
        
        # Comments (both editors)
        self.add_highlight_rule(
            pattern=r'#.*$',
            format_config={
                'color': '#99968B',
                'italic': True
            },
            editors=['python']
        )
        
        self.add_highlight_rule(
            pattern=r'//.*$',
            format_config={
                'color': '#99968B',
                'italic': True
            },
            editors=['mel']
        )
        
        # Default namespace token (both editors)
        self.add_special_command(
            command='@ns',
            format_config={
                'color': '#ff0100',
                'bold': True
            },
            editors=['python', 'mel'],
            function=self.handle_namespace
        )
    
    def add_highlight_rule(self, pattern, format_config, editors=None):
        """
        Add a new highlighting rule
        
        Args:
            pattern (str): Regular expression pattern to match
            format_config (dict): Configuration for text formatting
            editors (list): List of editor types where this rule applies
        """
        rule = HighlightRule(pattern, format_config, editors)
        self.highlight_rules.append(rule)
    
    def add_special_command(self, command, format_config, function=None, editors=None):
        """
        Add a special command with custom handling
        
        Args:
            command (str): The command to match (e.g., '@ns')
            format_config (dict): Configuration for text formatting
            function (callable): Optional function to handle the command
            editors (list): List of editor types where this command applies
        """
        # Create pattern that matches the command when it's alone or followed by text
        pattern = f'{re.escape(command)}(?![a-zA-Z0-9_])|{re.escape(command)}(?=[a-zA-Z0-9_])'
        rule = HighlightRule(pattern, format_config, editors)
        
        self.special_commands[command] = {
            'rule': rule,
            'handler': function
        }
        
    def handle_namespace(self, text, match): #@ns
        """
        Handle @ns token for namespace substitution
        
        Args:
            text (str): The full text being processed
            match (re.Match): The match object for the command
        """
        # Get the current namespace through the script manager
        if self.script_manager:
            main_window = self.script_manager.window()
            if isinstance(main_window, UI.AnimPickerWindow):
                current_ns = main_window.namespace_dropdown.currentText()
                ns_prefix = f"{current_ns}:" if current_ns and current_ns != 'None' else ""
                
                # Get the matched position
                start = match.start()
                end = match.end()
                
                # Check if @ns is followed by an identifier
                following_text = text[end:end+1] if end < len(text) else ''
                if following_text and following_text.isalnum():
                    # Replace @ns followed by identifier (e.g., @nscontrol -> namespace:control)
                    text = text[:start] + ns_prefix + text[end:]
                else:
                    # Replace standalone @ns with quoted namespace
                    text = text[:start] + f'"{ns_prefix}"' + text[end:]
                    
        return text
    
    def highlightBlock(self, text):
        """Apply highlighting to the given block of text"""
        # Apply regular highlighting rules
        for rule in self.highlight_rules:
            if self.editor_type in rule.editors:
                for match in re.finditer(rule.pattern, text):
                    self.setFormat(match.start(), match.end() - match.start(), rule.format)
        
        # Apply special commands
        for command, data in self.special_commands.items():
            if self.editor_type in data['rule'].editors:
                for match in re.finditer(data['rule'].pattern, text):
                    self.setFormat(match.start(), len(command), data['rule'].format)
                    if data['handler']:
                        text = data['handler'](text, match)

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
        self.setMinimumSize(300, 300)  # Set minimum size
        
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
        self.language_layout.addWidget(self.python_button)
        self.language_layout.addWidget(self.mel_button)

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
        
        # Create stacked widget for editors
        self.editor_stack = QtWidgets.QStackedWidget()
        self.editor_stack.setMinimumHeight(200)
        
        # Python editor with syntax highlighting
        self.python_editor = QtWidgets.QPlainTextEdit()
        self.python_editor.setStyleSheet(editor_style)
        self.python_highlighter = ScriptSyntaxHighlighter(self.python_editor.document(), 'python')
        self.python_highlighter.set_script_manager(self)  # Set script manager reference
        
        # MEL editor with syntax highlighting
        self.mel_editor = QtWidgets.QPlainTextEdit()
        self.mel_editor.setStyleSheet(editor_style)
        self.mel_highlighter = ScriptSyntaxHighlighter(self.mel_editor.document(), 'mel')
        self.mel_highlighter.set_script_manager(self)  # Set script manager reference
        
        # Add editors to stack
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

        self.python_highlighter = ScriptSyntaxHighlighter(self.python_editor.document(), 'python')
        self.mel_highlighter = ScriptSyntaxHighlighter(self.mel_editor.document(), 'mel')
        
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
                self.move(global_pos + QtCore.QPoint(button_geometry.width() + 10, 0))

    def update_language_selection(self, checked):
        if checked:  # Only respond to the button being checked
            is_python = self.python_button.isChecked()
            self.title_label.setText("Script Manager (Python)" if is_python else "Script Manager (MEL)")
            self.editor_stack.setCurrentIndex(0 if is_python else 1)
            
    def execute_code(self):
        """Handle code execution with special command processing"""
        if self.picker_button:
            try:
                # Get current namespace
                main_window = self.window()
                current_ns = ""
                if isinstance(main_window, UI.AnimPickerWindow):
                    current_ns = main_window.namespace_dropdown.currentText()
                    ns_prefix = f"{current_ns}:" if current_ns and current_ns != 'None' else ""
                
                # Get the code and type
                is_python = self.python_button.isChecked()
                code = self.python_editor.toPlainText() if is_python else self.mel_editor.toPlainText()

                # Process the code
                if is_python:
                    # For Python scripts
                    processed_code = code.replace('@ns', ns_prefix)  # Simple replacement
                else:
                    # For MEL scripts, replace @ns before any dot with string concatenation
                    def mel_replace(match):
                        full_match = match.group(0)  # The entire match
                        if '.' in full_match:
                            # If there's a dot, split and process
                            parts = full_match.split('.')
                            node = parts[0].replace('@ns', '')
                            attr = parts[1]
                            return f'("{ns_prefix}{node}").{attr}'
                        else:
                            # No dot, just replace @ns
                            return f'"{ns_prefix}{full_match.replace("@ns", "")}"'
                    
                    # Apply the MEL replacement
                    processed_code = re.sub(r'@ns\w+(?:\.\w+)?', mel_replace, code)
                
                # Store both original and processed code
                script_data = {
                    'type': 'python' if is_python else 'mel',
                    'python_code': self.python_editor.toPlainText(),
                    'mel_code': self.mel_editor.toPlainText(),
                    'code': processed_code
                }

                # Debug output
                print(f"Original code: {code}")
                print(f"Processed code: {processed_code}")
                
                # Update the button's script data
                self.picker_button.script_data = script_data
                self.picker_button.changed.emit(self.picker_button)
                self.close()
                
            except Exception as e:
                cmds.warning(f"Error processing code: {str(e)}")
                import traceback
                traceback.print_exc()
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
