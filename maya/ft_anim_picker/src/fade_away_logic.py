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

                # Handle canvas_stack reparenting
                if self.minimal_mode_enabled:
                    # Store original layout for restoration
                    self.parent.canvas_stack.original_parent = self.parent.canvas_stack.parent()
                    self.parent.canvas_stack.original_layout = self.parent.canvas_frame_layout

                    # Remove canvas_stack from the canvas frame layout
                    self.parent.canvas_frame_layout.removeWidget(self.parent.canvas_stack)

                    # Add the canvas_stack to the main_frame_col after top_col
                    self.parent.main_frame_col.insertWidget(1, self.parent.canvas_stack)

                    # Make sure the canvas is in minimal mode
                    canvas.set_minimal_mode(True)

                    # Hide the canvas frame and page_stack so canvas_stack fills the body
                    self.parent.canvas_frame.hide()
                    self.parent.page_stack.hide()

                    # Hide page segment control (no page switching in minimal mode)
                    self.parent.page_segment_frame.hide()

                    # Reparent tools_row_frame to main_frame_col before bottom_col
                    if hasattr(self.parent, 'tools_row_frame'):
                        self.parent.main_frame_col.insertWidget(2, self.parent.tools_row_frame)
                        self.parent.tools_row_frame.show()

                    # Reparent edit panel to main_frame so it stays visible
                    if hasattr(self.parent, 'canvas_edit_panel'):
                        panel = self.parent.canvas_edit_panel
                        panel.setParent(self.parent.main_frame)
                        # Defer position update so canvas_stack's new geometry settles first
                        QTimer.singleShot(0, panel._update_position)
                        if panel.isVisible():
                            panel.raise_()
                else:
                    # Reparent edit panel back to canvas_frame before restoring layout
                    if hasattr(self.parent, 'canvas_edit_panel'):
                        self.parent.canvas_edit_panel.setParent(self.parent.canvas_frame)

                    # Restore canvas_stack to original layout
                    # First remove from main_frame_col
                    self.parent.main_frame_col.removeWidget(self.parent.canvas_stack)

                    # Then add back to its original location
                    if hasattr(self.parent.canvas_stack, 'original_layout'):
                        self.parent.canvas_stack.original_layout.addWidget(self.parent.canvas_stack)

                    # Make sure the canvas is not in minimal mode
                    canvas.set_minimal_mode(False)

                    # Restore tools_row_frame back to editor_page_layout
                    if hasattr(self.parent, 'tools_row_frame'):
                        self.parent.main_frame_col.removeWidget(self.parent.tools_row_frame)
                        self.parent.editor_page_layout.insertWidget(1, self.parent.tools_row_frame)

                    # Show the canvas frame, page_stack and page segment again
                    self.parent.canvas_frame.show()
                    self.parent.page_stack.show()
                    self.parent.page_segment_frame.show()

                    # Reposition edit panel in restored canvas_frame
                    if hasattr(self.parent, 'canvas_edit_panel'):
                        panel = self.parent.canvas_edit_panel
                        QTimer.singleShot(0, panel._update_position)
                        if panel.isVisible():
                            panel.raise_()

        for widget in self.minimal_affected_widgets:
            if isinstance(widget, dict):
                # Handle widget dictionary with 'widget' and 'exclude' keys
                target_widget = widget['widget']
                exclude_elements = widget.get('exclude', [])

                # Skip if the widget should be completely hidden in minimal mode
                if widget.get('hide_in_minimal', False):
                    target_widget.setVisible(not self.minimal_mode_enabled)
                    continue

                # Keep widget visible in minimal mode with reduced opacity
                if widget.get('show_in_minimal', False):
                    target_widget.setVisible(True)
                    if self.minimal_mode_enabled:
                        effect = QtWidgets.QGraphicsOpacityEffect(target_widget)
                        effect.setOpacity(0.4)
                        target_widget.setGraphicsEffect(effect)
                    else:
                        target_widget.setGraphicsEffect(None)
                    target_widget.raise_()
                    continue

                # Handle special case for canvas frame
                if target_widget == self.parent.canvas_frame:
                    if self.minimal_mode_enabled:
                        target_widget.setStyleSheet('''
                            QFrame {
                                border: 0px solid transparent;
                                border-radius: 4px;
                                background-color: rgba(40, 40, 40, 0);
                            }
                        ''')
                    else:
                        target_widget.setStyleSheet('''
                            QFrame {
                                border: 0px solid gray;
                                border-radius: 4px;
                                background-color: rgba(40, 40, 40, 0);
                            }
                        ''')
                    continue

                # Handle special case for main frame
                if target_widget == self.parent.main_frame:
                    if self.minimal_mode_enabled:
                        target_widget.setStyleSheet('''
                            QFrame {
                                border: 0px solid transparent;
                                border-radius: 8px;
                                background-color: rgba(29, 29, 29, 0.01);
                            }
                        ''')
                    else:
                        target_widget.setStyleSheet('''
                            QFrame {
                                border: 0px solid gray;
                                border-radius: 8px;
                                background-color: #1D1D1D;
                            }
                        ''')
                    continue

                # Handle special case for util frame
                if target_widget == self.parent.util_frame:
                    if self.minimal_mode_enabled:
                        target_widget.setStyleSheet('''
                            QFrame {
                                border: 0px solid transparent;
                                border-radius: 4px;
                                background-color: rgba(40, 40, 40, 0);
                                padding: 0px;
                            }
                        ''')
                    else:
                        target_widget.setStyleSheet('''
                            QFrame {
                                border: 0px solid gray;
                                border-radius: 4px;
                                background-color: rgba(40, 40, 40, 0);
                                padding: 0px;
                            }
                        ''')

                # Handle special case for tools EF
                if target_widget == self.parent.tools_EF:
                    target_widget.set_alpha(0.0 if self.minimal_mode_enabled else 0.8)

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

        # Add separator
        menu.addSeparator()

        # Create window size buttons widget
        size_buttons_widget = QtWidgets.QWidget()
        size_buttons_layout = QtWidgets.QHBoxLayout(size_buttons_widget)
        size_buttons_layout.setContentsMargins(3, 3, 3, 3)
        size_buttons_layout.setSpacing(4)

        # Common button style
        button_style = '''
            QPushButton {
                background-color: #333333;
                border: 1px solid #555555;
                border-radius: 3px;
                color: #cccccc;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #444444;
                border: 1px solid #00749a;
            }
            QPushButton:pressed {
                background-color: #222222;
            }
        '''

        # Minimum size button
        min_btn = QtWidgets.QPushButton("Min")
        min_btn.setFixedSize(36, 24)
        min_btn.setStyleSheet(button_style)
        min_btn.setToolTip("Minimum window size (200x200)")
        min_btn.clicked.connect(lambda: self._resize_and_close_menu(menu, 'min'))

        # Default/Medium size button
        mid_btn = QtWidgets.QPushButton("Def")
        mid_btn.setFixedSize(36, 24)
        mid_btn.setStyleSheet(button_style)
        mid_btn.setToolTip("Default window size (350x450)")
        mid_btn.clicked.connect(lambda: self._resize_and_close_menu(menu, 'mid'))

        # Full screen button
        full_btn = QtWidgets.QPushButton("Full")
        full_btn.setFixedSize(36, 24)
        full_btn.setStyleSheet(button_style)
        full_btn.setToolTip("Toggle full screen")
        full_btn.clicked.connect(lambda: self._resize_and_close_menu(menu, 'full'))

        size_buttons_layout.addWidget(min_btn)
        size_buttons_layout.addWidget(mid_btn)
        size_buttons_layout.addWidget(full_btn)

        # Create QWidgetAction for size buttons
        size_buttons_action = QtWidgets.QWidgetAction(menu)
        size_buttons_action.setDefaultWidget(size_buttons_widget)
        menu.addAction(size_buttons_action)

        # Use the parent's mapToGlobal method
        action = menu.exec_(self.parent.mapToGlobal(pos))

        self.context_menu_open = False
        if self.fade_away_enabled:
            self.fade_timer.start(10)
        if action == toggle_fade_action:
            self.toggle_fade_away()
        elif action == toggle_minimal_action:
            self.toggle_minimal_mode()

    def _resize_and_close_menu(self, menu, size_type):
        """Helper to resize window and close the context menu"""
        menu.close()
        self.context_menu_open = False

        if size_type == 'min':
            self.parent.resize_window_min()
        elif size_type == 'mid':
            self.parent.resize_window_mid()
        elif size_type == 'full':
            self.parent.resize_window_full()

        if self.fade_away_enabled:
            self.fade_timer.start(10)