try:
    # For Maya 2024 (PySide2)
    from PySide2.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                                   QLabel, QFrame)
    from PySide2 import QtGui
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import Qt, Signal
except ImportError:
    # For Maya 2025 (PySide6)
    from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
                                   QLabel, QFrame)
    from PySide6 import QtGui
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import Qt, Signal
from . import utils as UT
from . import utils as UT

class ClickableWidget(QWidget):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super(ClickableWidget, self).mousePressEvent(event)

class ExpandableFrame(QFrame):
    expandedSignal = Signal() 
    collapsedSignal = Signal()
    def __init__(self, title, parent=None, height=None, margin=4,color='#2a2a2a',border=1, border_color='#555555', alpha=1):
        super(ExpandableFrame, self).__init__(parent)
        #self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.color = color
        self.border = str(border)+'px'
        self.border_color = border_color
        self.alpha = alpha
        self.setStyleSheet(f'''
                            QFrame {{ border: {self.border} solid {UT.rgba_value(self.border_color,1,self.alpha)}; border-radius: 4px; background-color: {UT.rgba_value(self.color,1,self.alpha)}; }}
                           ''')



        self.main_layout = QVBoxLayout(self)
        cm = 5
        self.main_layout.setSpacing(cm)
        self.main_layout.setContentsMargins(cm, cm,cm, cm)
        
        # Create a clickable header widget
        self.header_widget = ClickableWidget()
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(margin, margin, margin, margin)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: #eeeeee;border:None; background-color:transparent;")
        self.expand_button = QPushButton("")
        self.expand_button.setFixedSize(12, 12)
        
        
        self.header_layout.addWidget(self.title_label)
        self.header_layout.addStretch()
        self.header_layout.addWidget(self.expand_button)
        
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet(f'''
                                          QWidget {{border:0px solid {UT.rgba_value(self.color,1.2,self.alpha)};background-color:{UT.rgba_value(self.color,1.2,self.alpha)};}}
                                          QLabel {{border:None;background-color:transparent;}}
                                          QLineEdit {{border:1px solid #333333;background-color:#222222; margin: 0px; padding: 3px;}}''')
        self.content_layout = QVBoxLayout(self.content_widget)
        
        clm = 4 # content layout margin
        self.content_layout.setContentsMargins(clm, clm, clm, clm)
        self.content_layout.setSpacing(clm)
        
        self.main_layout.addWidget(self.header_widget)
        self.main_layout.addWidget(self.content_widget)
        
        self.is_expanded = False
        self.toggle_expand()

        self.expand_button_style(self.expand_button)
        
        self.expand_button.clicked.connect(self.toggle_expand)
        self.header_widget.clicked.connect(self.toggle_expand)
    
    def expand_button_style(self, button):
        bc = '#cccccc'
        button.setStyleSheet(f'''QPushButton {{ background-color: {bc if self.is_expanded else 'transparent'}; 
                                         color: white; border: {'0px solid #ffffff' if self.is_expanded else f'1px solid {bc}'}; border-radius: 3px }}''')
    
    def set_alpha(self, alpha):
        """Set the alpha value and update all styles."""
        self.alpha = alpha
        self.update_styles()
    
    def update_styles(self):
        self.setStyleSheet(f'''
                            QFrame {{ border: {self.border} solid {UT.rgba_value(self.border_color,1,self.alpha)}; border-radius: 4px; background-color: {UT.rgba_value(self.color,1,self.alpha)}; }}
                           ''')
        self.content_widget.setStyleSheet(f'''
                                          QWidget {{border:0px solid {UT.rgba_value(self.color,1.2,self.alpha)};background-color:{UT.rgba_value(self.color,1.2,self.alpha)};}}
                                          QLabel {{border:None;background-color:transparent;}}
                                          QLineEdit {{border:1px solid #333333;background-color:#222222; margin: 0px; padding: 3px;}}''')

    def toggle_expand(self):
        self.is_expanded = not self.is_expanded  # Use is_expanded instead of expanded
        self.expand_button_style(self.expand_button)
        self.content_widget.setVisible(self.is_expanded)
        
        if self.is_expanded:
            self.expandedSignal.emit()
        else:
            self.collapsedSignal.emit()
    
    def addWidget(self, widget):
        self.content_layout.addWidget(widget)
    
    def addLayout(self, widget):
        self.content_layout.addLayout(widget)

    def hex_value(self,hex_color, factor):
        color = QtGui.QColor(hex_color)
        h, s, v, a = color.getHsvF()
        v = min(max(v * factor, 0), 1)
        color.setHsvF(h, s, v, a)
        return color.name()

