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
        
        # Initialize with default rules
        self.setup_default_rules()
    
    def setup_default_rules(self):
        """Set up default highlighting rules"""
        # Python keywords (only for Python editor)
        python_keywords = ['def', 'class', 'for', 'while', 'if', 'else', 'elif', 
                         'try', 'except', 'finally', 'with', 'import', 'from', 
                         'as', 'return', 'yield', 'break', 'continue', 'pass',
                         'raise', 'True', 'False', 'None']
        
        self.add_highlight_rule(
            pattern=r'\b(' + '|'.join(python_keywords) + r')\b',
            format_config={
                'color': '#FF8080',
                'bold': True
            },
            editors=['python']
        )
        
        # MEL keywords (only for MEL editor)
        mel_keywords = ['proc', 'global', 'string', 'int', 'float', 'vector',
                       'matrix', 'if', 'else', 'for', 'while', 'switch', 'case',
                       'default', 'break', 'continue', 'return']
        
        self.add_highlight_rule(
            pattern=r'\b(' + '|'.join(mel_keywords) + r')\b',
            format_config={
                'color': '#FF8080',
                'bold': True
            },
            editors=['mel']
        )
        
        # Numbers (both editors)
        self.add_highlight_rule(
            pattern=r'\b\d+\b',
            format_config={
                'color': '#AD7FA8'
            }
        )
        
        # String literals (both editors)
        self.add_highlight_rule(
            pattern=r'\".*?\"',
            format_config={
                'color': '#95E454'
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
                'color': '#91CB08',
                'bold': True
            },
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
        
    def handle_namespace(self, text, match):
        """
        Default namespace handler
        
        Args:
            text (str): The full text being processed
            match (re.Match): The match object for the command
        
        Returns:
            str: The processed text with namespace handling
        """
        # Default implementation - can be overridden
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