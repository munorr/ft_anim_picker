from functools import partial
import maya.cmds as cmds
import maya.mel as mel
import os
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtGui import QColor, QAction, QActionGroup
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal
    from shiboken6 import wrapInstance
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtWidgets import QAction, QActionGroup
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
from . import tool_functions as TF
from . import custom_dialog as CD
from . import main as MAIN
from . import custom_color_picker as CCP

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

        # Create format for variable names
        self.variable_format = QtGui.QTextCharFormat()
        self.variable_format.setForeground(QtGui.QColor("#9CDCFE"))  # Light blue color
        self.variable_format.setFontWeight(QtGui.QFont.Bold)
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
        ]
        #--------------------------------------------------------------------------------------------------------
        # First, collect all quoted string ranges to avoid highlighting comments inside them
        quoted_ranges = []
        
        # Find double quoted strings
        double_quote_pattern = r'"[^"\\]*(?:\\.[^"\\]*)*"'
        for match in re.finditer(double_quote_pattern, text):
            quoted_ranges.append((match.start(), match.end()))
        
        # Find single quoted strings
        single_quote_pattern = r'\'[^\'\\]*(?:\\.[^\'\\]*)*\''
        for match in re.finditer(single_quote_pattern, text):
            quoted_ranges.append((match.start(), match.end()))
        
        # Helper function to check if a position is inside a quoted string
        def is_in_quoted_string(pos):
            for start, end in quoted_ranges:
                if start <= pos < end:
                    return True
            return False
        
        # Highlight quoted text (both single and double quotes) first
        for match in re.finditer(double_quote_pattern, text):
            self.setFormat(match.start(), len(match.group()), self.quoted_text_format)

        for match in re.finditer(single_quote_pattern, text):
            self.setFormat(match.start(), len(match.group()), self.quoted_text_format)
        #--------------------------------------------------------------------------------------------------------
        # Apply highlighting for @TF.functionName pattern (without brackets) Only highlight if the function exists in tool_functions
        tool_functions = ['tool_tip','button_appearance','reset_move','reset_scale','reset_rotate','reset_all']
        tf_pattern = r'(@TF\.)(\w+)'
        for match in re.finditer(tf_pattern, text, re.IGNORECASE):
            function_name = match.group(2)
            if function_name in tool_functions:
                # Apply bright green to @TF.
                self.setFormat(match.start(1), len(match.group(1)), self.special_format)
                # Apply sky blue to the function name
                self.setFormat(match.start(2), len(match.group(2)), self.tf_function_format)
        #--------------------------------------------------------------------------------------------------------
        tool_function_patterns = [
            r'(@TF\.)(\w+)',
            r'(@pb\s*\(([^)]+)\))',
            r'(@picker_button\s*\(([^)]+)\))',
            r'(@ba\s*\(([^)]+)\))',
            r'(@button_appearance\s*\(([^)]+)\))',
            r'(@tt\s*\(([^)]+)\))',
            r'(@tool_tip\s*\(([^)]+)\))',
            r'(@tool_tip\s*\(([^)]+)\))',
            
        ]
        tool_function_patterns_02 = [
            r'(@reset_all\b)',
            r'(@reset_move\b)',
            r'(@reset_scale\b)',
            r'(@reset_rotate\b)',
        ]
        #--------------------------------------------------------------------------------------------------------
        for pattern in tool_function_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Apply bright green to @pb
                self.setFormat(match.start(1), len(match.group(1)), self.special_format)
                # Apply sky blue to the function name
                self.setFormat(match.start(2), len(match.group(2)), self.tf_function_format)
        #--------------------------------------------------------------------------------------------------------
        for pattern in tool_function_patterns_02:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Apply bright green to the function name
                self.setFormat(match.start(1), len(match.group(1)), self.special_format)
        #--------------------------------------------------------------------------------------------------------
        # Apply highlighting for @ns.qualifier pattern (handles both direct and quoted contexts)
        # This comes AFTER quoted text highlighting so it can override the quote formatting
        ns_pattern = r'(@ns\.)([a-zA-Z0-9_-]+)'
        for match in re.finditer(ns_pattern, text, re.IGNORECASE):
            # Apply special_format_02 to @ns.
            self.setFormat(match.start(1), len(match.group(1)), self.special_format)
            # Apply tf_function_format to the qualifier
            #self.setFormat(match.start(2), len(match.group(2)), self.tf_function_format)
        
        # Also handle @ns. when it appears alone (like in strings)
        standalone_ns_pattern = r'@ns\.?'
        for match in re.finditer(standalone_ns_pattern, text, re.IGNORECASE):
            # Check if this @ns. is not already part of a @ns.qualifier match
            is_standalone = True
            for qual_match in re.finditer(ns_pattern, text, re.IGNORECASE):
                if match.start() == qual_match.start(1):
                    is_standalone = False
                    break
            
            if is_standalone:
                self.setFormat(match.start(), len(match.group()), self.special_format)
        #--------------------------------------------------------------------------------------------------------
        # Apply highlighting for other special patterns
        for pattern in special_patterns:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), len(match.group()), self.special_format)
        
        # Highlight Python keywords
        for match in re.finditer(r'\b(' + '|'.join(self.python_keywords) + r')\b', text):
            self.setFormat(match.start(), len(match.group()), self.keyword_format)

        # Highlight (), {}, [] in yellow
        for match in re.finditer(r'[\(\)\{\}\[\]]', text):
            self.setFormat(match.start(), 1, self.bracket_format)
        #--------------------------------------------------------------------------------------------------------
        # Highlight variable assignments (variable names on the left side of =)
        # Pattern matches: variable_name = (with optional whitespace)
        variable_pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*='
        for match in re.finditer(variable_pattern, text, re.MULTILINE):
            var_name = match.group(1)
            var_start = match.start(1)
            var_length = len(var_name)
            # Don't highlight if it's inside a quoted string or comment
            if not is_in_quoted_string(var_start):
                self.setFormat(var_start, var_length, self.variable_format)
        
        # Also highlight variables in multiple assignment: a, b, c = values
        multi_var_pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\s*,\s*[a-zA-Z_][a-zA-Z0-9_]*)*)\s*='
        for match in re.finditer(multi_var_pattern, text, re.MULTILINE):
            var_section = match.group(1)
            var_start_offset = match.start(1)
            
            # Extract individual variable names from the comma-separated list
            individual_vars = re.finditer(r'[a-zA-Z_][a-zA-Z0-9_]*', var_section)
            for var_match in individual_vars:
                var_start = var_start_offset + var_match.start()
                var_length = len(var_match.group())
                if not is_in_quoted_string(var_start):
                    self.setFormat(var_start, var_length, self.variable_format)
        
        # Highlight parameter names in function calls: function(param_name = value)
        # This pattern looks for parameter names inside function calls
        param_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)\s*='
        for match in re.finditer(param_pattern, text):
            param_name = match.group(1)
            param_start = match.start(1)
            param_length = len(param_name)
            
            # Don't highlight if it's inside a quoted string or comment
            if not is_in_quoted_string(param_start):
                # Additional check: make sure this isn't a line-start variable assignment
                # (which we already handled above)
                line_start = text.rfind('\n', 0, param_start) + 1
                text_before_param = text[line_start:param_start].strip()
                
                # If there's something before the parameter name on the same line,
                # it's likely a function parameter, not a variable assignment
                if text_before_param:
                    self.setFormat(param_start, param_length, self.variable_format)
        #--------------------------------------------------------------------------------------------------------
        # Highlight comments (lines starting with #) but only if not inside strings
        # Comments should override quoted text formatting when the # is not inside a string
        comment_pattern = r'#.*'
        for match in re.finditer(comment_pattern, text):
            comment_start = match.start()
            if not is_in_quoted_string(comment_start):
                # Apply comment formatting to the entire comment, overriding any previous formatting
                self.setFormat(comment_start, len(match.group()), self.comment_format)

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
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.NoWrap)
        
        # Connect signals for updating line number area
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        
        # Initialize the line number area width
        self.update_line_number_area_width(0)
        
        # Highlight the current line
        self.highlight_current_line()

        # Enable context menu
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)
    
    def show_context_menu(self, position):
        """Show custom context menu at the given position"""
        context_menu = QtWidgets.QMenu(self)
        context_menu.setStyleSheet("""
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
            }
        """)
        # Add placeholder menu items
        button_ids_action = context_menu.addAction("Selected Button IDs")
        button_appearance_action = context_menu.addAction("Button Appearance")

        color_sample_action = QtWidgets.QWidgetAction(context_menu)
        color_sample_widget = QtWidgets.QWidget()
        color_sample = CCP.ColorPicker(mode='hex')
        color_sample_widget.setLayout(QtWidgets.QHBoxLayout())
        color_sample_widget.layout().setContentsMargins(0, 0, 0, 0)
        color_sample_widget.layout().addWidget(color_sample)
        color_sample_action.setDefaultWidget(color_sample_widget)

        context_menu.addAction(color_sample_action)
        
        # Connect actions to placeholder methods
        script_manager = self.get_script_manager()
        if script_manager:
            button_ids_action.triggered.connect(script_manager.ppf_get_selected_button_ids)
            button_appearance_action.triggered.connect(script_manager.ppf_button_appearance)
            
        
        # Show the context menu at the cursor position
        context_menu.exec_(self.mapToGlobal(position))
    
    def get_script_manager(self):
        """Find the ScriptManagerWidget in the parent hierarchy"""
        widget = self.parent()
        while widget:
            if isinstance(widget, ScriptManagerWidget):
                return widget
            widget = widget.parent()
        return None
    
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
        self.setAttribute(QtCore.Qt.WA_AlwaysShowToolTips, True)
        # Setup resizing parameters
        self.resizing = False
        self.resize_edge = None
        self.resize_range = 8  # Pixels from edge where resizing is active
          # Set minimum size
        self.setGeometry(0,0,500,300)
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
                border: 0px solid #444444;
                border-radius: 4px;
            }
        """)
        self.frame_layout = QtWidgets.QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(6, 6, 6, 6)
        self.frame_layout.setSpacing(6)
        #--------------------------------------------------------------------------------------------------------------------------
        # Title bar with draggable area and close button
        self.title_bar = QtWidgets.QWidget()
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet("background: rgba(30, 30, 30, .9); border: none; border-radius: 3px;")
        title_layout = QtWidgets.QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(6, 6, 6, 6)
        title_layout.setSpacing(6)
        
        self.title_label_layout = QtWidgets.QHBoxLayout()
        self.title_label_layout.setContentsMargins(0, 0, 0, 0)
        self.title_label_layout.setSpacing(0)

        self.title_label = QtWidgets.QLabel("Button - ")
        self.title_label.setStyleSheet("color: #dddddd; background: transparent; border: none;")
        self.title_label_layout.addWidget(self.title_label)
        
        self.button_id_label = QtWidgets.QLabel("")
        self.button_id_label.setStyleSheet("color: #4ca3fe; background: transparent; font-weight: bold; border: none;")
        self.title_label_layout.addWidget(self.button_id_label)
        
        title_layout.addSpacing(4)
        #title_layout.addLayout(self.title_label_layout)
        #--------------------------------------------------------------------------------------------------------------------------
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
        title_layout.addStretch(1)
        #title_layout.addWidget(self.close_button)
        #--------------------------------------------------------------------------------------------------------------------------
        # Language selection
        self.language_layout = QtWidgets.QHBoxLayout()
        self.language_layout.setAlignment(QtCore.Qt.AlignLeft)

        self.language_toggle_frame = QtWidgets.QFrame()
        self.language_toggle_frame.setStyleSheet("QFrame {background-color: #1e1e1e; border: 1px solid #444444; border-radius: 3px; padding: 2px;}")
        self.language_toggle_layout = QtWidgets.QHBoxLayout(self.language_toggle_frame)
        self.language_toggle_layout.setContentsMargins(0, 0, 0, 0)
        self.language_toggle_layout.setSpacing(0)

        self.python_button = CB.CustomRadioButton("Python", fill=False, width=60, height=14, group=True)
        self.mel_button = CB.CustomRadioButton("MEL", fill=False, width=40, height=14, group=True)
        self.python_button.group('script_language')
        self.mel_button.group('script_language')
        self.language_toggle_layout.addWidget(self.python_button)
        self.language_toggle_layout.addWidget(self.mel_button)

        self.function_preset_stack = QtWidgets.QStackedWidget()
        fps = 22
        self.function_preset_stack.setFixedSize(fps, fps)
        self.function_preset_stack.setStyleSheet("background: #1e1e1e; border: none; border-radius: 11px;")
        self.python_function_preset_button = CB.CustomButton(text='', icon=UT.get_icon('add.png',opacity=.8, size=14), height=fps, width=fps, radius=3,color='#222222',alpha=0,textColor='#aaaaaa', 
                                                             ContextMenu=True, onlyContext= True, cmHeight=fps, cmColor='#333333',tooltip='Python function presets',flat=True)
        
        self.python_function_preset_button.addMenuLabel('Presets Commands',position=(0,0))
        self.python_function_preset_button.addToMenu('Set Attribute', self.ppf_set_attribute, position=(1,0))
        #self.python_function_preset_button.addToMenu('Match IK to FK', self.ppf_match_ik_to_fk, position=(2,0))
        #self.python_function_preset_button.addToMenu('Match FK to IK', self.ppf_match_fk_to_ik, position=(3,0))
        self.python_function_preset_button.addToMenu('Button Appearance', self.ppf_button_appearance, position=(2,0))
        self.python_function_preset_button.addToMenu('Add Selected Button IDs', self.ppf_get_selected_button_ids, position=(3,0))

        self.color_sample = CCP.ColorPicker(mode='hex')
        
        self.mel_function_preset_button = CB.CustomButton(text='', icon=UT.get_icon('add.png', size=14), height=fps, width=fps, radius=3,color='#222222',alpha=0,textColor='#aaaaaa', 
                                                          ContextMenu=True, onlyContext= True, cmColor='#333333',cmHeight=fps, tooltip='Mel function presets',flat=True)
        
        self.mel_function_preset_button.addMenuLabel('Presets Commands',position=(0,0))
        self.mel_function_preset_button.addToMenu('Set Attribute', self.mpf_set_attribute, position=(1,0))

        self.function_preset_stack.addWidget(self.python_function_preset_button)
        self.function_preset_stack.addWidget(self.mel_function_preset_button)

        self.language_layout.addWidget(self.language_toggle_frame)
        self.language_layout.addLayout(self.title_label_layout)
        self.language_layout.addStretch(1)
        #self.language_layout.addWidget(self.color_sample)
        #self.language_layout.addWidget(self.function_preset_stack)
        self.language_layout.addWidget(self.close_button)
        self.language_layout.addSpacing(2)

        #--------------------------------------------------------------------------------------------------------------------------
        # Create custom QPlainTextEdit subclass with line numbers and tab handling
        
        # Editor style
        editor_style = f"""
            QPlainTextEdit {{
                background-color: #1b1b1b;
                color: #dddddd;
                border: None;
                border-radius: 3px;
                padding: 5px 5px 5px 15px; /* Added significant left padding to prevent text from being under line numbers */
                font-family: Consolas, Monaco, monospace;
                selection-background-color: #264f78;
            }}
            QScrollBar:vertical {{
                border: none;
                background: transparent;
                width: 8px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(100, 100, 100, 0.5);
                min-height: 20px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(120, 120, 120, 0.7);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
            QScrollBar:horizontal {{
                border: none;
                background: transparent;
                height: 8px;
                margin: 0px;
            }}
            QScrollBar::handle:horizontal {{
                background: rgba(100, 100, 100, 0.5);
                min-width: 20px;
                border-radius: 4px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: rgba(120, 120, 120, 0.7);
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: transparent;
            }}

        """
        #--------------------------------------------------------------------------------------------------------------------------
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
        self.mel_editor.document().setDocumentMargin(5)
        
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
        self.apply_button = QtWidgets.QPushButton("Save Code")
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
        #self.frame_layout.addWidget(self.title_bar)
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
        #self.title_bar.mousePressEvent = self.title_bar_mouse_press
        #self.title_bar.mouseMoveEvent = self.title_bar_mouse_move
        #self.title_bar.mouseReleaseEvent = self.title_bar_mouse_release
        
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
        preset_code = '''@ba(t=None, o=1, s=1, tb=None, c="")'''
        
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
            
            # Create the preset code with proper formatting
            if len(button_ids) > 5:
                # Arrange in rows of 5
                formatted_ids = "[\n"
                for i in range(0, len(button_ids), 5):
                    row = button_ids[i:i+5]
                    # Format each row with proper indentation
                    row_str = "    " + ", ".join(repr(id) for id in row)
                    if i + 5 < len(button_ids):  # Not the last row
                        row_str += ","
                    formatted_ids += row_str + "\n"
                formatted_ids += "]"
                preset_code = formatted_ids
            else:
                # Use single line format for 5 or fewer items
                preset_code = f'''{button_ids}'''
            
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
        self.button_id_label.setText(f"[{self.picker_button.unique_id}]")
        self.position_window()

    def position_window(self):
        if self.picker_button:
            button_geometry = self.picker_button.geometry()
            scene_pos = self.picker_button.scene_position
            canvas = self.picker_button.parent()
            
            if canvas:
                canvas_pos = canvas.scene_to_canvas_coords(scene_pos)
                global_pos = canvas.mapToGlobal(canvas_pos.toPoint())
                # move to center of button
                global_pos.setX(global_pos.x() - self.width() / 2)
                global_pos.setY(global_pos.y() - self.height() / 2)
                self.move(global_pos) 

    def update_language_selection(self, checked):
        if checked:  # Only respond to the button being checked
            is_python = self.python_button.isChecked()
            #self.title_label.setText("Script Manager (Python)" if is_python else "Script Manager (MEL)")
            self.editor_stack.setCurrentIndex(0 if is_python else 1)
            self.function_preset_stack.setCurrentIndex(0 if is_python else 1)
            
    def execute_code(self):
        """Modified to ensure each button gets its own script data and extract tooltip information"""
        if self.picker_button:
            # Get the current code based on selected language
            current_code = self.python_editor.toPlainText() if self.python_button.isChecked() else self.mel_editor.toPlainText()
            
            # Extract tooltip from the code if present
            custom_tooltip = None
            tooltip_patterns = [
                r'@TF\.tool_tip\s*\(\s*["\'](.+?)["\']s*\)',
                r'@tool_tip\s*\(\s*["\'](.+?)["\']s*\)',
                r'@tt\s*\(\s*["\'](.+?)["\']s*\)',
            ]
            for pattern in tooltip_patterns:
                tooltip_match = re.search(pattern, current_code, flags=re.IGNORECASE)
                if tooltip_match:
                    custom_tooltip = tooltip_match.group(1)
                    break
            
            # Create fresh script data for this button
            script_data = {
                'type': 'python' if self.python_button.isChecked() else 'mel',
                'python_code': self.python_editor.toPlainText(),
                'mel_code': self.mel_editor.toPlainText(),
                'code': current_code
            }
            
            # Add custom tooltip to script data if found
            if custom_tooltip:
                script_data['custom_tooltip'] = custom_tooltip
            
            # Update the button's script data
            self.picker_button.script_data = script_data
            
            # Update the tooltip immediately
            self.picker_button.update_tooltip()
            
            # Emit changed signal and close
            self.picker_button.changed.emit(self.picker_button)
            self.close()
    #--------------------------------------------------------------------------------------------------------------------
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
                self.dragging = True
                self.offset = event.globalPos() - self.pos()
        
        if event.type() == QtCore.QEvent.MouseButtonDblClick:
            self.resize(500, 300)
            return True
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
        
        if self.dragging and event.buttons() == QtCore.Qt.LeftButton:
            self.move(event.globalPos() - self.offset)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.resizing = False
            self.resize_edge = None
            self.unsetCursor()
        
        if event.button() == QtCore.Qt.LeftButton:
            self.dragging = False

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
    #--------------------------------------------------------------------------------------------------------------------
