try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, QObject
    from PySide6.QtGui import QColor
    from shiboken6 import wrapInstance
    from PySide6.QtGui import QColor, QShortcut
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, QObject
    from PySide2.QtGui import QColor
    from shiboken2 import wrapInstance

class FadeAway(QObject):
    def __init__(self, parent):
        super(FadeAway, self).__init__(parent)
        self.parent = parent
        self.fade_away_enabled = False
        self.minimal_mode_enabled = False
        self.context_menu_open = False

        self.fade_timer = QTimer(self)
        self.fade_timer.setSingleShot(True)
        self.fade_timer.timeout.connect(self.start_fade_animation)

        self.fade_animation = QPropertyAnimation(self.parent, b"windowOpacity")
        self.fade_animation.setDuration(1000)
        self.fade_animation.setEasingCurve(QEasingCurve.InOutQuad)

        self.parent = parent
        self.parent.installEventFilter(self)

        # Store widgets that should be affected by minimal mode
        self.minimal_affected_widgets = []

    def set_minimal_affected_widgets(self, widgets):
        """Set the widgets that should be affected by minimal mode"""
        self.minimal_affected_widgets = widgets

    def handle_enter_event(self):
        if self.fade_away_enabled:
            self.fade_timer.stop()
            self.fade_animation.stop()
            self.fade_animation.setDuration(100)
            self.fade_animation.setStartValue(self.parent.windowOpacity())
            self.fade_animation.setEndValue(1.0)
            self.fade_animation.start()

    def handle_leave_event(self):
        if self.fade_away_enabled and not self.context_menu_open:
            self.fade_timer.start(10)

    def start_fade_animation(self):
        if self.fade_away_enabled and not self.context_menu_open:
            self.fade_animation.setDuration(400)
            self.fade_animation.setStartValue(self.parent.windowOpacity())
            self.fade_animation.setEndValue(0.05)
            self.fade_animation.start()

    def toggle_fade_away(self):
        self.fade_away_enabled = not self.fade_away_enabled
        if not self.fade_away_enabled:
            self.fade_timer.stop()
            self.fade_animation.stop()
            self.parent.setWindowOpacity(1.0)

    def toggle_minimal_mode(self):
        self.minimal_mode_enabled = not self.minimal_mode_enabled
        opacity = 0.05 if self.minimal_mode_enabled else 1.0
        
        # Set canvas minimal mode
        if hasattr(self.parent, 'tab_system'):
            current_tab = self.parent.tab_system.current_tab
            if current_tab:
                canvas = self.parent.tab_system.tabs[current_tab]['canvas']
                canvas.set_minimal_mode(self.minimal_mode_enabled)
                
                # Handle canvas frame and canvas reparenting
                if self.minimal_mode_enabled:
                    # Store the original parent and layout for restoration
                    canvas.original_parent = canvas.parent()
                    canvas.original_layout = self.parent.canvas_frame_row
                    
                    # Remove from canvas frame and add directly to area_01_col layout
                    self.parent.canvas_frame_row.removeWidget(canvas)
                    self.parent.area_01_col.insertWidget(0, canvas)  # Insert at the beginning of area_01_col
                    
                    # Hide the canvas frame
                    self.parent.canvas_frame.hide()
                else:
                    # Restore canvas to original layout
                    if hasattr(canvas, 'original_parent') and hasattr(canvas, 'original_layout'):
                        # First remove from area_01_col
                        self.parent.area_01_col.removeWidget(canvas)
                        # Then add back to canvas frame row
                        canvas.original_layout.addWidget(canvas)
                        self.parent.canvas_frame.show()
        
        for widget in self.minimal_affected_widgets:
            if isinstance(widget, dict):
                # Handle widget dictionary with 'widget' and 'exclude' keys
                target_widget = widget['widget']
                exclude_elements = widget.get('exclude', [])
                
                # Skip if the widget should be completely hidden in minimal mode
                if widget.get('hide_in_minimal', False):
                    target_widget.setVisible(not self.minimal_mode_enabled)
                    continue

                # Handle special case for canvas frame
                if target_widget == self.parent.canvas_frame:
                    # Make the canvas frame completely transparent in minimal mode
                    target_widget.setStyleSheet(f'''
                        QFrame {{
                            border: 0px solid transparent; 
                            border-radius: 3px; 
                            background-color: {'rgba(40, 40, 40, 0)' if self.minimal_mode_enabled else 'rgba(40, 40, 40, .8)'};
                        }}
                    ''')
                    continue

                # Handle special case for main frame
                if target_widget == self.parent.main_frame:
                    # Make the main frame completely transparent in minimal mode
                    target_widget.setStyleSheet(f'''
                        QFrame {{
                            border: 0px solid transparent; 
                            border-radius: 4px; 
                            background-color: {'rgba(36, 36, 36, 0.01)' if self.minimal_mode_enabled else 'rgba(36, 36, 36, .6)'};
                        }}
                    ''')
                    continue


                # Handle special case for util frame
                if target_widget == self.parent.util_frame:
                    # Make the util frame partialy transparent in minimal mode
                    target_widget.setStyleSheet(f'''
                        QFrame {{
                            border: 0px solid transparent; 
                            border-radius: 4px; 
                            background-color: {'rgba(40, 40, 40, 0)' if self.minimal_mode_enabled else 'rgba(40, 40, 40, .8)'};
                        }}
                    ''')
                
                # Handle special case for tools EF
                if target_widget == self.parent.tools_EF:
                    # Make the util frame partialy transparent in minimal mode
                    target_widget.set_alpha(0 if self.minimal_mode_enabled else 0.8)


                # Set opacity for the main widget
                if hasattr(target_widget, 'setWindowOpacity'):
                    target_widget.setWindowOpacity(opacity)
                
                # Handle excluded elements
                for element in exclude_elements:
                    if hasattr(element, 'setWindowOpacity'):
                        element.setWindowOpacity(1.0)
                    element.setVisible(True)
                    
            else:
                # Handle simple widget
                if hasattr(widget, 'setWindowOpacity'):
                    widget.setWindowOpacity(opacity)

        # If in minimal mode, set a completely transparent window background
        if self.minimal_mode_enabled:
            self.parent.setStyleSheet('QWidget {background-color: transparent; border-radius: 4px;}')
        else:
            self.parent.setStyleSheet('QWidget {background-color: rgba(40, 40, 40, 0.5); border-radius: 4px;}')

    def set_context_menu_open(self, is_open):
        self.context_menu_open = is_open

    def eventFilter(self, obj, event):
        if obj == self.parent:
            if event.type() == QtCore.QEvent.Enter:
                self.handle_enter_event()
            elif event.type() == QtCore.QEvent.Leave:
                self.handle_leave_event()
        return False
    
    def show_frame_context_menu(self, pos):
        self.context_menu_open = True
        menu = QtWidgets.QMenu(self.parent)
        
        # Remove background and shadow
        menu.setWindowFlags(menu.windowFlags() | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint)
        menu.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        menu.setStyleSheet('''
        QMenu {
            background-color: rgba(40, 40, 40, 1);
            border-radius: 3px;
            padding: 5px;
            border: 1px solid rgba(255,255,255,.2);
        }
        QMenu::item {
            background-color: #222222;
            padding: 6px;
            border: 1px solid #00749a;
            border-radius: 3px;
            margin: 3px 0px;
        }
        QMenu::item:selected {
            background-color: #111111;
        }
        ''')
        
        # Add label using QWidgetAction
        label = QtWidgets.QLabel("Picker Frame")
        
        # Create a QWidgetAction to hold the label
        label_action = QtWidgets.QWidgetAction(menu)
        
        label_action.setDefaultWidget(label)
        menu.addAction(label_action)

        toggle_fade_action = menu.addAction("Toggle Fade Away")
        toggle_fade_action.setCheckable(True)
        toggle_fade_action.setChecked(self.fade_away_enabled)

        toggle_minimal_action = menu.addAction("Toggle Minimal")
        toggle_minimal_action.setCheckable(True)
        toggle_minimal_action.setChecked(self.minimal_mode_enabled)
        
        # Use the parent's mapToGlobal method
        action = menu.exec_(self.parent.mapToGlobal(pos))
        
        self.context_menu_open = False
        if self.fade_away_enabled:
            self.fade_timer.start(10)
        if action == toggle_fade_action:
            self.toggle_fade_away()
        elif action == toggle_minimal_action:
            self.toggle_minimal_mode()