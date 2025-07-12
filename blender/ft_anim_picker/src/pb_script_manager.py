from functools import partial
import bpy
import os

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtGui import QColor
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Signal, QPoint
from PySide6.QtWidgets import QLabel, QToolTip
from PySide6.QtCore import Qt

import re

from . import utils as UT
from . import custom_line_edit as CLE
from . import custom_button as CB
from . import data_management as DM
from . import blender_ui as UI
from . import tool_functions as TF
from . import custom_dialog as CD
from . import blender_main as MAIN
from . import custom_color_picker as CCP
from . utils import undoable

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
            'raise', 'and', 'or', 'not', 'in', 'is', 'True', 'False', 'None', 'bpy'
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
        
        # Store quoted text positions but don't apply formatting yet
        # We'll apply quoted text formatting after variable highlighting
        quoted_text_matches = []
        
        for match in re.finditer(double_quote_pattern, text):
            quoted_text_matches.append((match.start(), len(match.group())))

        for match in re.finditer(single_quote_pattern, text):
            quoted_text_matches.append((match.start(), len(match.group())))
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
        # FIXED: Highlight variable assignments - consolidated and improved logic
        
        # 1. Handle line-start variable assignments (including multiple assignments)
        line_assignment_pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\s*,\s*[a-zA-Z_][a-zA-Z0-9_]*)*)\s*=(?!=)'
        processed_assignments = set()  # Track processed assignments to avoid duplicates
        
        for match in re.finditer(line_assignment_pattern, text, re.MULTILINE):
            var_section = match.group(1)
            var_start_offset = match.start(1)
            
            # Don't highlight if inside a quoted string
            if not is_in_quoted_string(var_start_offset):
                # Extract individual variable names from the comma-separated list
                individual_vars = re.finditer(r'[a-zA-Z_][a-zA-Z0-9_]*', var_section)
                for var_match in individual_vars:
                    var_start = var_start_offset + var_match.start()
                    var_length = len(var_match.group())
                    
                    # Double-check each variable position
                    if not is_in_quoted_string(var_start):
                        self.setFormat(var_start, var_length, self.variable_format)
                        processed_assignments.add(var_start)  # Mark as processed
        
        # 2. Handle function parameters and keyword arguments (but not line-start assignments)
        param_pattern = r'([a-zA-Z_][a-zA-Z0-9_]*)\s*=(?!=)'
        for match in re.finditer(param_pattern, text):
            param_start = match.start(1)
            param_length = len(match.group(1))
            
            # Skip if already processed as a line-start assignment
            if param_start in processed_assignments:
                continue
            
            # Don't highlight if inside a quoted string
            if not is_in_quoted_string(param_start):
                # Check if this is NOT a line-start assignment
                line_start = text.rfind('\n', 0, param_start) + 1
                text_before_param = text[line_start:param_start].strip()
                
                # Only highlight if there's something before it on the same line
                # (indicating it's a function parameter, not a variable assignment)
                if text_before_param:
                    self.setFormat(param_start, param_length, self.variable_format)
        
        #--------------------------------------------------------------------------------------------------------
        # Apply quoted text formatting AFTER most highlighting but BEFORE @ns patterns
        # This ensures strings get their formatting, but special patterns can override
        for start_pos, length in quoted_text_matches:
            self.setFormat(start_pos, length, self.quoted_text_format)
        
        #--------------------------------------------------------------------------------------------------------
        # Re-apply @ns patterns AFTER quoted text to ensure they override string formatting
        # Apply highlighting for @ns.qualifier pattern (handles both direct and quoted contexts)
        ns_pattern = r'(@ns\.)([a-zA-Z0-9_-]+)'
        for match in re.finditer(ns_pattern, text, re.IGNORECASE):
            # Apply special_format to @ns. (always, even inside quotes)
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
        #----------------------------------------------------------------------------------------------
        # Enable mouse tracking for tooltips
        self.setMouseTracking(True)
        
        # Tooltip delay timer
        self._tooltip_timer = QtCore.QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_delayed_tooltip)
        self._pending_tooltip = None

        self.installEventFilter(self)
        # Tooltip definitions for highlighted tokens
        self.tooltip_definitions = {
            '@ba': 'Control button appearance properties<br><font color="#555555">t=text, c=color, o=opacity, s=selectable, tb=target_buttons</font>',
            '@pb': 'Gives access to picker button properties<br><font color="#555555">.color  .text  .opacity  .selectable</font>',
            '@tt': 'Adds custom tooltips for script buttons<br><font color="#555555">@tt("header text", "body text")</font>',
            '@reset_all': 'Reset all transforms (move, scale, rotate)',
            '@reset_move': 'Reset object translation/position',
            '@reset_scale': 'Reset object scale',
            '@reset_rotate': 'Reset object rotation',
            '@ns.': 'Reference to object namespace for selection operations',
            '@ns': 'Reference to object namespace for selection operations'
        }
        #----------------------------------------------------------------------------------------------

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
    #---------------------------------------------------------------------------------------------
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
                cursor.movePosition(QtGui.QTextCursor.Right, QtGui.QTextCursor.MoveAnchor, len(indent))
        
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        return True
    #---------------------------------------------------------------------------------------------
    def get_token_at_position(self, position):
        """Get the highlighted token at the given text position"""
        # Get the current document
        document = self.document()
        
        # Find the block containing this position
        block = document.findBlock(position)
        if not block.isValid():
            return None
        
        # Get the text of the block and position within block
        block_text = block.text()
        position_in_block = position - block.position()
        
        # Define patterns for tokens we want to detect
        import re
        token_patterns = [
            # @TF.function patterns
            (r'(@TF\.[a-zA-Z_][a-zA-Z0-9_]*)', r'@TF\.\w+'),
            # Function call patterns with parentheses
            (r'(@ba)\s*\([^)]*\)', r'@ba'),
            (r'(@button_appearance)\s*\([^)]*\)', r'@button_appearance'),
            (r'(@pb)\s*\([^)]*\)', r'@pb'),
            (r'(@picker_button)\s*\([^)]*\)', r'@picker_button'),
            (r'(@tt)\s*\([^)]*\)', r'@tt'),
            (r'(@tool_tip)\s*\([^)]*\)', r'@tool_tip'),
            # Standalone function patterns
            (r'(@reset_all)\b', r'@reset_all'),
            (r'(@reset_move)\b', r'@reset_move'),
            (r'(@reset_scale)\b', r'@reset_scale'),
            (r'(@reset_rotate)\b', r'@reset_rotate'),
            # Namespace patterns - detect both @ns and @ns.
            (r'(@ns\.)([a-zA-Z0-9_-]*)', r'@ns\.'),
            (r'(@ns)\b', r'@ns'),
        ]
        
        # Check each pattern to see if the position falls within a match
        for full_pattern, token_pattern in token_patterns:
            for match in re.finditer(full_pattern, block_text, re.IGNORECASE):
                if match.start() <= position_in_block < match.end():
                    # Extract the specific token part
                    token_match = re.search(token_pattern, match.group(), re.IGNORECASE)
                    if token_match:
                        token = token_match.group()
                        # Handle @TF.function case
                        if token.startswith('@TF.'):
                            return token
                        # Handle @ns. and @ns case
                        elif token == '@ns.' or token == '@ns':
                            return token
                        # Handle other cases
                        else:
                            return token
        
        return None
    
    def show_custom_tooltip(self, global_pos, text=None, content=None, widget=None):
        """Show a custom tooltip without width restrictions
        
        Args:
            global_pos: Global position for the tooltip
            text: Simple text to display (legacy mode)
            content: Function to build tooltip content
            widget: Pre-built tooltip widget
        """
        # Hide any existing tooltip first
        self.hide_custom_tooltip()
        
        # Use pre-built widget if provided
        if widget:
            tooltip_widget = widget
        else:
            # Create the custom tooltip widget
            tooltip_widget = CB.CustomTooltipWidget(bg_color="#1f1f1f", border_color="#333333")
            
            if content and callable(content):
                # Use content function to build the tooltip
                content(tooltip_widget)
            elif text:
                # Simple text mode for backward compatibility
                tooltip_widget.add_text(text)
            else:
                # Default tooltip content
                tooltip_widget.add_text("")
        
        # Finalize the tooltip (resize it)
        tooltip_widget.finalize()
        
        # Position tooltip with screen boundary checking
        screen = QtWidgets.QApplication.screenAt(global_pos)
        if screen:
            screen_rect = screen.availableGeometry()
            tooltip_pos = global_pos + QPoint(10, 10)
            
            # Adjust if tooltip would go off screen
            if tooltip_pos.x() + tooltip_widget.width() > screen_rect.right():
                tooltip_pos.setX(global_pos.x() - tooltip_widget.width() - 10)
            if tooltip_pos.y() + tooltip_widget.height() > screen_rect.bottom():
                tooltip_pos.setY(global_pos.y() - tooltip_widget.height() - 10)
                
            tooltip_widget.move(tooltip_pos)
        else:
            tooltip_widget.move(global_pos + QPoint(10, 10))
        
        tooltip_widget.show()
        
        # Store reference to prevent garbage collection
        self._custom_tooltip = tooltip_widget
        
        # Auto-hide after 10 seconds as a safety measure
        if hasattr(self, '_tooltip_hide_timer'):
            self._tooltip_hide_timer.stop()
        else:
            self._tooltip_hide_timer = QtCore.QTimer(self)
            self._tooltip_hide_timer.setSingleShot(True)
            self._tooltip_hide_timer.timeout.connect(self.hide_custom_tooltip)
        
        self._tooltip_hide_timer.start(10000)  # 10 second auto-hide
    
    def _show_delayed_tooltip(self):
        """Show the tooltip after the delay has elapsed"""
        if self._pending_tooltip:
            # Create a custom tooltip with enhanced styling
            tooltip_widget = CB.CustomTooltipWidget(bg_color="#1f1f1f", border_color="#333333")
            
            # Get token information
            token = self._pending_tooltip.get('token', '')
            tooltip_text = self._pending_tooltip.get('text', '')
            
            # Create header with token name
            header_layout = QtWidgets.QHBoxLayout()
            
            # Add colored indicator based on token type
            color = "#91CB08"  # Default green for most tokens
            token_name = ""
            if token.startswith('@ba') or token.startswith('@button_appearance'):
                token_name = "Button Appearance"
            elif token.startswith('@tt') or token.startswith('@tool_tip'):
                token_name = "Tooltip"
            elif token.startswith('@pb') or token.startswith('@picker_button'):
                token_name = "Picker Button"
            elif token.startswith('@reset'):
                token_name = "Reset Function"
            elif token.startswith('@ns.') or token.startswith('@ns'):
                token_name = "Namespace"
            
            # Add token name
            token_label = QtWidgets.QLabel(f"<b>{token} <font color=#aaaaaa>({token_name})</font></b> ")
            token_label.setStyleSheet(f"color: {color}; font-size: 12px;")
            header_layout.addWidget(token_label)
            header_layout.addStretch()
            
            # Add the header to the tooltip
            tooltip_widget.add_layout(header_layout)
            
            # Text frame
            text_frame = QtWidgets.QFrame()
            text_frame.setStyleSheet("background-color: #1b1b1b; border: 1px solid #333333; border-radius: 3px; padding: 2px;")

            text_layout = QtWidgets.QVBoxLayout(text_frame)
            text_layout.setContentsMargins(2, 2, 2, 2)
            text_layout.setSpacing(2)
            
            # Add description text
            tooltip_label = QtWidgets.QLabel(tooltip_text)
            tooltip_label.setStyleSheet("color: #ffffff; font-size: 12px; border: none; background-color: transparent;")
            text_layout.addWidget(tooltip_label)
            
            # Add the text frame to the tooltip
            tooltip_widget.add_widget(text_frame)
            
            # Show the tooltip at the pending position
            self.show_custom_tooltip(
                self._pending_tooltip['position'],
                widget=tooltip_widget
            )
    
    def hide_custom_tooltip(self):
        """Hide the custom tooltip"""
        if hasattr(self, '_custom_tooltip') and self._custom_tooltip:
            self._custom_tooltip.hide()
            self._custom_tooltip.deleteLater()
            self._custom_tooltip = None
            
        if hasattr(self, '_tooltip_hide_timer'):
            self._tooltip_hide_timer.stop()
            
        # Also hide Qt's default tooltip as backup
        QToolTip.hideText()
    #---------------------------------------------------------------------------------------------
    def mouseMoveEvent(self, event):
        """Handle mouse move events to show tooltips for highlighted tokens"""
        # Get the cursor position at the mouse location
        cursor = self.cursorForPosition(event.pos())
        position = cursor.position()
        
        # Get the token at this position
        token = self.get_token_at_position(position)
        
        if token and token in self.tooltip_definitions:
            # Only set new tooltip if it's different from current
            new_tooltip = {
                'position': event.globalPos(),
                'text': self.tooltip_definitions[token],
                'token': token
            }
            
            # Check if this is a different tooltip or position has changed significantly
            if (not self._pending_tooltip or 
                self._pending_tooltip.get('token') != new_tooltip['token'] or
                (self._pending_tooltip.get('position') - new_tooltip['position']).manhattanLength() > 5):
                
                self._pending_tooltip = new_tooltip
                self._tooltip_timer.stop()  # Stop any existing timer
                self._tooltip_timer.start(500)  # Reduced delay for better responsiveness
        else:
            # Immediately clear when not over a token
            self._tooltip_timer.stop()
            self._pending_tooltip = None
            self.hide_custom_tooltip()
        
        super().mouseMoveEvent(event)
        
    def leaveEvent(self, event):
        """Hide tooltip when mouse leaves the editor"""
        self._tooltip_timer.stop()
        self._pending_tooltip = None
        self.hide_custom_tooltip()
        super().leaveEvent(event)

    def enterEvent(self, event):
        """Handle mouse entering the editor"""
        super().enterEvent(event)

    def eventFilter(self, obj, event):
        """Event filter to handle various tooltip-related events"""
        if obj == self:
            if event.type() == QtCore.QEvent.FocusOut:
                # Hide tooltip when editor loses focus
                self.hide_custom_tooltip()
            elif event.type() == QtCore.QEvent.WindowDeactivate:
                # Hide tooltip when window is deactivated
                self.hide_custom_tooltip()
            elif event.type() == QtCore.QEvent.KeyPress:
                # Hide tooltip when user starts typing
                self.hide_custom_tooltip()
        
        return super().eventFilter(obj, event)

class ScriptManagerWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        if parent is None:
            # Lazy import MAIN to avoid circular dependency
            from . import blender_main as MAIN
            manager = MAIN.PickerWindowManager.get_instance()
            parent = manager._picker_widgets[0] if manager._picker_widgets else None
        super(ScriptManagerWidget, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_AlwaysShowToolTips, True)
        # Setup resizing parameters
        self.resizing = False
        self.resize_edge = None
        self.resize_range = 8  # Pixels from edge where resizing is active
        
        self.br = 4
        # Set minimum size
        self.setGeometry(0,0,500,300)
        self.setMinimumSize(305, 300)

        # Track our visibility state
        self._was_visible = True
        
        # Store reference to parent picker window and register with visibility manager
        self.parent_picker = self._find_parent_picker()
        if self.parent_picker:
            from . import blender_main
            visibility_manager = blender_main.PickerVisibilityManager.get_instance()
            visibility_manager.register_child_widget(self.parent_picker, self)
        #--------------------------------------------------------------------------------------------------------------------------
        # Setup main layout
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(4, 4, 4, 4)
        self.main_layout.setSpacing(4)
        
        # Create main frame
        self.frame = QtWidgets.QFrame()
        self.frame.setMinimumWidth(300)
        self.frame.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(36, 36, 36, .95);
                border: 1px solid #444444;
                border-radius: {self.br}px;
            }}
            QToolTip {{
                background-color: #1b1b1b;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 0px;
                padding: 4px;
            }}""")
        self.frame_layout = QtWidgets.QVBoxLayout(self.frame)
        self.frame_layout.setContentsMargins(6, 6, 6, 6)
        self.frame_layout.setSpacing(6)
        #--------------------------------------------------------------------------------------------------------------------------
        # Title bar with draggable area and close button
        self.title_bar = QtWidgets.QWidget()
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet(f"background: rgba(30, 30, 30, .9); border: none; border-radius: {self.br}px;")
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
        # Function preset section
        self.preset_layout = QtWidgets.QHBoxLayout()
        self.preset_layout.setAlignment(QtCore.Qt.AlignLeft)
        #--------------------------------------------------------------------------------------------------------------------------
        self.python_label = QtWidgets.QLabel("Python")
        self.python_label.setStyleSheet(f"color: #eeeeee; padding: 4px; font-size: 12px; border-radius: {self.br}px; background-color: #222222;")

        self.color_sample = CCP.ColorPicker(mode='hex')

        self.function_preset_button = CB.CustomButton(
            text='', 
            icon=UT.get_icon('add.png', opacity=.8, size=14), 
            height=22, 
            width=22, 
            radius=11,
            color='#1e1e1e',
            alpha=1,
            textColor='#aaaaaa', 
            ContextMenu=True, 
            onlyContext=True, 
            cmColor='#333333',
            cmHeight=22,
            tooltip='Python function presets', 
        )
        
        self.function_preset_button.addMenuLabel('Preset Commands', position=(0,0))
        self.function_preset_button.addToMenu('Button Appearance', self.ppf_button_appearance, position=(1,0))
        self.function_preset_button.addToMenu('Add Selected Button IDs', self.ppf_get_selected_button_ids, position=(2,0))

        self.preset_layout.addWidget(self.python_label)
        self.preset_layout.addLayout(self.title_label_layout)
        self.preset_layout.addStretch(1)
        #self.preset_layout.addWidget(self.color_sample)
        #self.preset_layout.addWidget(self.function_preset_button)
        self.preset_layout.addWidget(self.close_button)
        self.preset_layout.addSpacing(2)
        #--------------------------------------------------------------------------------------------------------------------------
        editor_style = f"""
            QPlainTextEdit {{
                background-color: #1b1b1b;
                color: #dddddd;
                border: None;
                border-radius: {self.br}px;
                padding: 5px 5px 5px 15px;
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
        # Create single editor for Python code
        self.code_editor = CodeEditor()
        self.code_editor.setStyleSheet(editor_style)
        self.python_highlighter = ScriptSyntaxHighlighter(self.code_editor.document())
        # Force document margin to create space for line numbers
        self.code_editor.document().setDocumentMargin(5)
        
        # Set tab width for the editor
        font = self.code_editor.font()
        font_metrics = QtGui.QFontMetrics(font)
        space_width = font_metrics.horizontalAdvance(' ')
        self.code_editor.setTabStopDistance(space_width * 4)

        # Apply Button
        self.apply_button = QtWidgets.QPushButton("Save Code")
        self.apply_button.setFixedHeight(24)
        self.apply_button.setStyleSheet(f"""
            QPushButton {{
                background-color: #5285a6;
                color: white;
                border: none;
                border-radius: {self.br}px;
                padding: 2px 10px;
            }}
            QPushButton:hover {{
                background-color: #67c2f2;
            }}
        """)
        
        # Add widgets to layout
        #self.frame_layout.addWidget(self.title_bar)
        self.frame_layout.addLayout(self.preset_layout)
        self.frame_layout.addWidget(self.code_editor)
        self.frame_layout.addWidget(self.apply_button)
        self.main_layout.addWidget(self.frame)
        
        # Connect signals
        self.close_button.clicked.connect(self.close)
        self.apply_button.clicked.connect(self.execute_code)
        
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
    def ppf_button_appearance(self): # Button Appearance
        preset_code = '''@ba(t=None, o=1, s=1, tb=None, c="")'''
        
        # Insert code at the current cursor position
        cursor = self.code_editor.textCursor()
        cursor.insertText(preset_code)
        self.code_editor.setFocus()
        
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

            elif len(button_ids) == 1:
                preset_code = f"'{button_ids[0]}'"

            else:
                # Use single line format for 5 or fewer items
                preset_code = f'''{button_ids}'''
            
            # Insert code at the current cursor position
            cursor = self.code_editor.textCursor()
            cursor.insertText(preset_code)
            self.code_editor.setFocus()
    #--------------------------------------------------------------------------------------------------------------------
    def set_picker_button(self, button):
        """Initialize the script manager with data from the picker button"""
        self.picker_button = button
        script_data = button.script_data if isinstance(button.script_data, dict) else {}
        
        # Create default script data if not properly formatted
        if not script_data:
            script_data = {
                'type': 'python',
                'python_code': '',
                'code': ''  # For backwards compatibility
            }
            
        # Set the editor's content from button-specific data
        python_code = script_data.get('python_code', script_data.get('code', ''))
        self.code_editor.setPlainText(python_code)
        
        # Make sure to update the button's script data
        button.script_data = script_data
        self.button_id_label.setText(f"[{self.picker_button.unique_id}]")
        self.position_window()

    def _find_parent_picker(self):
        """Find the parent BlenderAnimPickerWindow"""
        parent = self.parent()
        while parent:
            if parent.__class__.__name__ == 'BlenderAnimPickerWindow':
                return parent
            parent = parent.parent()
        return None

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
            
    def execute_code(self):
        """Save the script data to the button and close the manager"""
        if self.picker_button:
            # Get the current code
            current_code = self.code_editor.toPlainText()
            
            # Extract tooltip from the code if present
            custom_tooltip_header = None
            custom_tooltip = None
            tooltip_patterns = [
                r'@TF\.tool_tip\s*\(\s*["\'](.+?)["\']\s*(?:,\s*["\'](.+?)["\'])?\s*\)',
                r'@tool_tip\s*\(\s*["\'](.+?)["\']\s*(?:,\s*["\'](.+?)["\'])?\s*\)',
                r'@tt\s*\(\s*["\'](.+?)["\']\s*(?:,\s*["\'](.+?)["\'])?\s*\)',
            ]
            for pattern in tooltip_patterns:
                tooltip_match = re.search(pattern, current_code, flags=re.IGNORECASE)
                if tooltip_match:
                    custom_tooltip_header = tooltip_match.group(1)
                    custom_tooltip = tooltip_match.group(2) if tooltip_match.lastindex >= 2 else None
                    break
            
            # Create script data
            script_data = {
                'type': 'python',
                'python_code': current_code,
                'code': current_code  # For backwards compatibility
            }
            
            # Add custom tooltip to script data if found
            if custom_tooltip_header:
                script_data['custom_tooltip_header'] = custom_tooltip_header
            if custom_tooltip:
                script_data['custom_tooltip'] = custom_tooltip
            
            # Update the button's script data
            self.picker_button.script_data = script_data
            
            # Update the tooltip immediately
            self.picker_button.update_tooltip()
            
            # Emit changed signal and close
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
                self.dragging = True
                self.offset = event.globalPos() - self.pos()
        
        if event.type() == QtCore.QEvent.MouseButtonDblClick:
            self.resize(500, 300)
            return True
        UT.blender_main_window() 
    
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
        # Unregister from visibility manager
        if self.parent_picker:
            from . import blender_main
            visibility_manager = blender_main.PickerVisibilityManager.get_instance()
            visibility_manager.unregister_child_widget(self.parent_picker, self)
        
        super().closeEvent(event)
        UT.blender_main_window()

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

