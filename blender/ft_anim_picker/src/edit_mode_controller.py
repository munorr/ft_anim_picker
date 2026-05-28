# Edit Mode Controller - Consolidated edit mode logic for the Blender Anim Picker
# Owns all edit-mode UI creation, queue/batch processing, button mutations, and widget sync.

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import QTimer, QObject, Signal
from PySide6.QtGui import QColor
from functools import partial

from . import custom_line_edit as CLE
from . import custom_button as CB
from . import custom_slider as CS
from . import custom_color_picker as CCP
from . import expandable_frame as EF
from . import utils as UT
from . import data_management as DM


class EditModeController(QObject):
    """
    Owns the entire edit mode lifecycle:
    - UI widget creation (rename, color, transform, radius, opacity, placement, etc.)
    - Queue/batch system for debounced property changes
    - Button mutation methods (rename, recolor, resize, etc.)
    - Widget sync with button selection
    """

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self._active = False

        # Queue / batch state
        self.pending_widget_changes = {}
        self.widget_update_timer = QTimer()
        self.widget_update_timer.setSingleShot(True)
        self.widget_update_timer.timeout.connect(self._apply_widget_changes)
        self.widget_update_delay = 10  # ms

        self.is_updating_widgets = False
        self._drag_dirty = False  # Set True when visual-only changes need a DB commit

        # Edit update debounce timer
        self._edit_update_timer = QTimer()
        self._edit_update_timer.setSingleShot(True)
        self._edit_update_timer.timeout.connect(self._sync_widgets)

        # Build all edit widgets
        self.widgets = {}
        self._build_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def is_active(self):
        return self._active

    def activate(self):
        """Enter edit mode — update all canvases and show edit panel."""
        self._active = True
        mw = self.main_window
        mw.edit_mode = True

        # Make panel visible but start transparent; animated entrance follows
        mw.canvas_edit_panel.setVisible(True)
        mw.canvas_edit_panel._update_position()
        mw.canvas_edit_panel.raise_()
        # Delay the panel slide-in so it doesn't clash with the window resize
        mw.canvas_edit_panel.animate_show(delay_ms=100)

        for tab_name, tab_data in mw.tab_system.tabs.items():
            canvas = tab_data['canvas']
            canvas.set_edit_mode(True)
            for button in canvas.buttons:
                button.update_cursor()

        if hasattr(mw, 'edit_button'):
            mw.edit_button.setChecked(True)

        mw._animate_edit_mode_width()
        mw.update()
        self.on_selection_changed()
        QtCore.QTimer.singleShot(0, mw.update_buttons_for_current_tab)

    def deactivate(self):
        """Exit edit mode — hide edit panel and restore canvases."""
        # Commit any pending changes before exiting edit mode
        if self.pending_widget_changes:
            self._apply_widget_changes()
        self._commit_drag_to_database()

        # Flush any debounced saves from the last drag/resize so the
        # scene property reflects the final edit state before we leave
        # edit mode.
        try:
            from . import data_management as DM
            DM.PickerDataManager.flush_pending_saves()
        except Exception:
            pass

        self._active = False
        mw = self.main_window
        mw.edit_mode = False

        # Animate the panel out; it hides itself on completion
        mw.canvas_edit_panel.animate_hide()

        for tab_name, tab_data in mw.tab_system.tabs.items():
            canvas = tab_data['canvas']
            canvas.set_edit_mode(False)
            for button in canvas.buttons:
                button.update_cursor()

        if hasattr(mw, 'edit_button'):
            mw.edit_button.setChecked(False)

        # Delay the window shrink so the panel starts sliding out first
        QtCore.QTimer.singleShot(80, mw._animate_edit_mode_width)
        mw.update()
        QtCore.QTimer.singleShot(0, mw.update_buttons_for_current_tab)

        # Return keyboard focus to Blender after exiting edit mode
        QtCore.QTimer.singleShot(100, UT.blender_main_window)

    def toggle(self):
        """Toggle edit mode on/off."""
        if self._active:
            self.deactivate()
        else:
            self.activate()

    def on_tab_changed(self, canvas):
        """Re-bind to a new canvas when the active tab changes."""
        if self._active:
            self.on_selection_changed()

    def get_button_page_widget(self):
        """Return the top-level widget containing all button-edit controls.
        The caller adds this to its layout (e.g. edit_value_layout)."""
        return self._container

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_canvas(self):
        ts = self.main_window.tab_system
        if ts.current_tab and ts.current_tab in ts.tabs:
            return ts.tabs[ts.current_tab]['canvas']
        return None

    def _get_selected_buttons(self):
        canvas = self._get_canvas()
        return canvas.get_selected_buttons() if canvas else []

    # ------------------------------------------------------------------
    # UI Creation  (previously in button_edit_widgets.py)
    # ------------------------------------------------------------------
    def _build_ui(self):
        """Build all edit-mode widgets and store in self.widgets dict."""
        w = self.widgets
        label_color = "#666666"
        widget_color = "#1d1d1d"
        le_height = 22 # Line edit height

        def set_margin_space(layout, margin, space):
            layout.setContentsMargins(margin, margin, margin, margin)
            layout.setSpacing(space)

        def set_widget_style(widget, color):
            widget.setStyleSheet(
                f"QWidget {{background-color: transparent; padding: 0px; border-radius: 3px; border: 0px solid #666666;}}"
                f"QLabel {{color: {label_color}; border: none; font-size: 11px;}}"
            )
        def add_divider(layout,spacing=8):
            divider = QtWidgets.QFrame()
            divider.setFixedHeight(1)
            divider.setStyleSheet("background-color: rgba(255, 255, 255, 0.1);")
            layout.addSpacing(spacing)
            layout.addWidget(divider)

        _SECTION_LABEL = "color: #999999; font-size: 11px; font-weight: bold;"
        _SUB_LABEL = "color: #777777; font-size: 10px;"

        # Container for all button-edit widgets
        self._container = QtWidgets.QWidget()
        self._container.setStyleSheet("background: transparent;")
        container_layout = QtWidgets.QVBoxLayout(self._container)
        container_layout.setAlignment(QtCore.Qt.AlignTop)
        set_margin_space(container_layout, 0, 0)

        # ===================================================================
        # Rename widget
        # ===================================================================
        rename_widget = QtWidgets.QWidget()
        rename_widget.setStyleSheet(f"border: 1px solid #435813; background-color: {widget_color};")
        rename_widget.setFixedHeight(30)
        rename_layout = QtWidgets.QHBoxLayout(rename_widget)
        set_margin_space(rename_layout, 0, 0)

        rename_edit = QtWidgets.QLineEdit()
        rename_edit.setPlaceholderText("Rename Button")
        rename_edit.setStyleSheet(
            "QLineEdit {"
            "  background-color: transparent; color: #dddddd;"
            "  border: 0px solid #5c7918; border-radius: 3px;"
            "  padding: 2px; padding-left: 4px;"
            "}"
        )
        rename_edit.setFixedHeight(28)

        clear_button = QtWidgets.QPushButton()
        clear_button.setFixedSize(28, 28)
        clear_button.setIcon(QtGui.QIcon(UT.get_icon("close_01.png", size=13, opacity=0.4)))
        clear_button.setStyleSheet(
            "QPushButton { background-color: transparent; color: #dddddd;"
            "  border-radius: 3px; border: 0px solid #5c7918; font-weight: bold; font-size: 12px; }"
        )
        rename_edit.returnPressed.connect(partial(UT.blender_main_window))
        clear_button.clicked.connect(lambda: rename_edit.setText(" "))

        rename_layout.addWidget(rename_edit)
        rename_layout.addWidget(clear_button)

        w['rename_widget'] = rename_widget
        w['rename_edit'] = rename_edit
        w['clear_button'] = clear_button

        # ===================================================================
        # Text Format drawer
        # ===================================================================
        text_format_widget = QtWidgets.QWidget()
        set_widget_style(text_format_widget, widget_color)
        text_format_layout = QtWidgets.QVBoxLayout(text_format_widget)

        biu_widget = QtWidgets.QWidget()
        biu_layout = QtWidgets.QHBoxLayout(biu_widget)
        set_margin_space(biu_layout, 0, 4)

        text_format_label = QtWidgets.QLabel("Text Format")
        text_format_label.setStyleSheet(_SECTION_LABEL)

        
        text_format_layout.addWidget(text_format_label)
        set_margin_space(text_format_layout, 6, 4)

        TFS = 22
        text_color_picker = CCP.ColorPicker(mode='color-popup', size=le_height)
        biu_layout.addWidget(text_color_picker)

        text_btn_style = (
            "QPushButton {{ background-color: #333333; color: #ffffff; {extra}"
            "  border-radius: 3px; border: 1px solid #555555; }}"
            "QPushButton:hover {{ background-color: #444444; }}"
            "QPushButton:checked {{ background-color: #5c7918; border: 1px solid #6c9809; }}"
        )

        text_bold_btn = QtWidgets.QPushButton("B")
        text_bold_btn.setCheckable(True)
        text_bold_btn.setFixedSize(TFS, TFS)
        text_bold_btn.setStyleSheet(text_btn_style.format(extra="font-weight: bold;"))
        biu_layout.addWidget(text_bold_btn)

        text_italic_btn = QtWidgets.QPushButton("I")
        text_italic_btn.setCheckable(True)
        text_italic_btn.setFixedSize(TFS, TFS)
        text_italic_btn.setStyleSheet(text_btn_style.format(extra="font-style: italic;"))
        biu_layout.addWidget(text_italic_btn)

        text_underline_btn = QtWidgets.QPushButton("U")
        text_underline_btn.setCheckable(True)
        text_underline_btn.setFixedSize(TFS, TFS)
        text_underline_btn.setStyleSheet(text_btn_style.format(extra="text-decoration: underline;"))
        biu_layout.addWidget(text_underline_btn)

        biu_layout.addStretch()
        text_format_layout.addWidget(biu_widget)
        add_divider(text_format_layout)

        w['text_format_widget'] = text_format_widget
        w['text_color_picker'] = text_color_picker
        w['text_bold_btn'] = text_bold_btn
        w['text_italic_btn'] = text_italic_btn
        w['text_underline_btn'] = text_underline_btn

        # Text format signal connections
        text_color_picker.colorChanged.connect(lambda qcolor: self.set_text_color(qcolor.name()))
        text_bold_btn.toggled.connect(lambda checked: self._queue_text_format_change('bold', checked))
        text_italic_btn.toggled.connect(lambda checked: self._queue_text_format_change('italic', checked))
        text_underline_btn.toggled.connect(lambda checked: self._queue_text_format_change('underline', checked))

        # ===================================================================
        # Transform widget (Width / Height)
        # ===================================================================
        transform_widget = QtWidgets.QWidget()
        set_widget_style(transform_widget, widget_color)
        transform_main_layout = QtWidgets.QVBoxLayout(transform_widget)
        set_margin_space(transform_main_layout, 6, 4)

        transform_layout = QtWidgets.QHBoxLayout()
        set_margin_space(transform_layout, 0, 4)

        transform_label = QtWidgets.QLabel("Dimensions")
        transform_label.setStyleSheet(_SECTION_LABEL)

        transform_prop = CB.CustomRadioButton("", fill=True, width=18, height=18, color="#1D65CA")
        transform_w_edit = CLE.IntegerLineEdit(min_value=0, max_value=2000, increment=1, precision=0, width=None, height=le_height, label="W")
        transform_h_edit = CLE.IntegerLineEdit(min_value=0, max_value=2000, increment=1, precision=0, width=None, height=le_height, label="H")
        transform_match = CB.CustomButton("", width=6, height=le_height, color="#1D65CA", tooltip="Match Width to Height")

        transform_main_layout.addWidget(transform_label)
        transform_main_layout.addLayout(transform_layout)

        transform_layout.addWidget(transform_w_edit)
        transform_layout.addWidget(transform_h_edit)
        transform_layout.addWidget(transform_prop)
        #transform_layout.addWidget(transform_match)

        # --- Rotation row ---
        rotation_label = QtWidgets.QLabel("Rotation")
        rotation_label.setStyleSheet(_SECTION_LABEL)
        transform_main_layout.addWidget(rotation_label)

        rotation_layout = QtWidgets.QHBoxLayout()
        set_margin_space(rotation_layout, 0, 4)

        rotation_edit = CLE.IntegerLineEdit(min_value=-180, max_value=180, increment=1, width=None, height=le_height, label="°")

        _rot_btn_style = (
            "QPushButton { background-color: #333333; color: #cccccc; "
            "border: 1px solid #444444; border-radius: 3px; "
            "padding: 2px; }"
            "QPushButton:hover { background-color: #444444; }"
            "QPushButton:pressed { background-color: #555555; }"
        )
        reset_rotation_btn = QtWidgets.QPushButton()
        reset_rotation_btn.setFixedSize(le_height, le_height)
        reset_rotation_btn.setStyleSheet(_rot_btn_style)
        reset_rotation_btn.setIcon(UT.get_icon("refresh_icon.png", opacity=0.9))
        reset_rotation_btn.setIconSize(QtCore.QSize(14, 14))
        reset_rotation_btn.setToolTip("Reset Rotation to 0°")
        reset_rotation_btn.clicked.connect(self.reset_rotation)

        rotation_layout.addWidget(rotation_edit)
        rotation_layout.addWidget(reset_rotation_btn)
        transform_main_layout.addLayout(rotation_layout)

        w['transform_widget'] = transform_widget
        w['transform_prop'] = transform_prop
        w['transform_w_edit'] = transform_w_edit
        w['transform_h_edit'] = transform_h_edit
        w['transform_match'] = transform_match
        w['rotation_edit'] = rotation_edit

        transform_match.clicked.connect(self.match_size)

        # ===================================================================
        # Radius widget
        # ===================================================================
        radius_widget = QtWidgets.QWidget()
        set_widget_style(radius_widget, widget_color)
        radius_main_layout = QtWidgets.QVBoxLayout(radius_widget)
        set_margin_space(radius_main_layout, 6, 4)

        # Header: label 
        radius_label = QtWidgets.QLabel("Radius")
        radius_label.setStyleSheet(_SECTION_LABEL)
        single_radius = CB.CustomRadioButton("", fill=True, width=18, height=18, color="#1D65CA")
        radius_main_layout.addWidget(radius_label)

        radius_layout = QtWidgets.QHBoxLayout()
        radius_layout.setAlignment(QtCore.Qt.AlignTop)
        radius_layout.setContentsMargins(0, 0, 0, 0)
        radius_layout.setSpacing(4)
        radius_main_layout.addLayout(radius_layout)

        bh = 2000

        # Uniform radius field (default: visible — single mode active by default)
        uniform_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=le_height, label="R")
        radius_layout.addWidget(uniform_radius)
        
        

        # Per-corner radius fields (default: hidden — single mode active by default)
        corners_widget = QtWidgets.QWidget()
        corners_widget.setVisible(False)
        corners_layout = QtWidgets.QVBoxLayout(corners_widget)
        set_margin_space(corners_layout, 0, 4)
        top_row = QtWidgets.QHBoxLayout()
        set_margin_space(top_row, 0, 4)
        bottom_row = QtWidgets.QHBoxLayout()
        set_margin_space(bottom_row, 0, 4)

        top_left_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=le_height, label="╭")
        top_right_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=le_height, label="╮")
        bottom_left_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=le_height, label="╰")
        bottom_right_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=le_height, label="╯")

        top_row.addWidget(top_left_radius)
        top_row.addWidget(top_right_radius)
        bottom_row.addWidget(bottom_left_radius)
        bottom_row.addWidget(bottom_right_radius)
        corners_layout.addLayout(top_row)
        corners_layout.addLayout(bottom_row)
        radius_layout.addWidget(corners_widget)

        single_radius_layout = QtWidgets.QVBoxLayout()
        single_radius_layout.setAlignment(QtCore.Qt.AlignTop)

        single_radius_layout.addWidget(single_radius)
        radius_layout.addLayout(single_radius_layout)

        add_divider(radius_main_layout)

        w['radius_widget'] = radius_widget
        w['single_radius'] = single_radius
        w['uniform_radius'] = uniform_radius
        w['corners_widget'] = corners_widget
        w['top_left_radius'] = top_left_radius
        w['top_right_radius'] = top_right_radius
        w['bottom_left_radius'] = bottom_left_radius
        w['bottom_right_radius'] = bottom_right_radius

        # ===================================================================
        # Fill color
        # ===================================================================
        
        fill_color_widget = QtWidgets.QWidget()

        fill_color_main_layout = QtWidgets.QVBoxLayout(fill_color_widget)
        set_margin_space(fill_color_main_layout, 6, 4)

        fill_color_layout = QtWidgets.QHBoxLayout(fill_color_widget)
        set_margin_space(fill_color_layout, 0, 4)
        

        fill_color_label = QtWidgets.QLabel("Button Color")
        fill_color_label.setStyleSheet(_SECTION_LABEL)
        fill_color_main_layout.addWidget(fill_color_label)

        color_picker = CCP.ColorPicker(mode='color-popup', size=le_height)
        color_picker.colorChanged.connect(self._queue_color_change)
        w['color_picker'] = color_picker

        opacity_edit = CLE.IntegerLineEdit(min_value=0, max_value=100, increment=1, height=le_height, label="%",precision=0)
        opacity_edit.setValue(100)
        w['opacity_edit'] = opacity_edit

        fill_color_layout.addWidget(color_picker)
        fill_color_layout.addWidget(opacity_edit)
        fill_color_main_layout.addLayout(fill_color_layout)
        w['fill_color'] = fill_color_widget

        add_divider(fill_color_main_layout)

        # ===================================================================
        # Placement widget (alignment, z-order, mirror, distribute)
        # ===================================================================
        placement_widget = QtWidgets.QWidget()
        set_widget_style(placement_widget, widget_color)
        placement_layout = QtWidgets.QVBoxLayout(placement_widget)
        set_margin_space(placement_layout, 6, 4)

        placement_label = QtWidgets.QLabel("Alignment")
        placement_label.setStyleSheet(_SECTION_LABEL)
        placement_layout.addWidget(placement_label)

        placement_btn_style = (
            "QPushButton { background-color: #333333; color: #ffffff; }"
            "QPushButton:hover { background-color: #444444; }"
            "QPushButton:pressed { background-color: #555555; }"
            "QToolTip { background-color: #333333; color: #FFFFFF; border: 1px solid #222222; }"
        )

        def make_btn(text, tooltip, callback):
            btn = QtWidgets.QPushButton(text)
            btn.setStyleSheet(placement_btn_style)
            btn.setToolTip(tooltip)
            btn.setFixedHeight(24)
            btn.clicked.connect(callback)
            return btn

        # Alignment grid
        grid_widget = QtWidgets.QWidget()
        grid_layout = QtWidgets.QGridLayout(grid_widget)
        set_margin_space(grid_layout, 0, 4)

        def alignment_btn(icon_path, tooltip, callback):
            btn = QtWidgets.QPushButton()
            btn.setStyleSheet(placement_btn_style)
            btn.setFixedHeight(24)
            btn.setIcon(UT.get_icon(icon_path, opacity=0.9))
            btn.setIconSize(QtCore.QSize(20, 20))
            btn.setToolTip(tooltip)
            btn.clicked.connect(callback)
            return btn

        grid_layout.addWidget(alignment_btn("align_left.png", "Align Left", self.align_left), 0, 0)
        grid_layout.addWidget(alignment_btn("align_vCenter.png", "Align Vertical Center", self.align_vcenter), 0, 1)
        grid_layout.addWidget(alignment_btn("align_right.png", "Align Right", self.align_right), 0, 2)
        grid_layout.addWidget(alignment_btn("v_spacing.png", "Distribute Evenly (Vertical)", self.distribute_vertical), 0, 3)

        grid_layout.addWidget(alignment_btn("align_top.png", "Align Top", self.align_top), 1, 0)
        grid_layout.addWidget(alignment_btn("align_hCenter.png", "Align Horizontal Center", self.align_hcenter), 1, 1)
        grid_layout.addWidget(alignment_btn("align_bottom.png", "Align Bottom", self.align_bottom), 1, 2)
        grid_layout.addWidget(alignment_btn("h_spacing.png", "Distribute Evenly (Horizontal)", self.distribute_horizontal), 1, 3)

        # Z-order / mirror buttons
        zorder_layout = QtWidgets.QVBoxLayout()
        set_margin_space(zorder_layout, 0, 4)
        zorder_layout.addWidget(make_btn("Move Behind", "Move selected button behind", self.move_behind))
        zorder_layout.addWidget(make_btn("Bring Forward", "Bring selected button forward", self.bring_forward))
        zorder_layout.addWidget(make_btn("Horizontal Mirror", "Mirror selected button positions horizontally", self.mirror_horizontal))
        zorder_layout.addWidget(make_btn("Horizontal Mirror (WC)", "Mirror and assign counterpart objects", self.mirror_horizontal_wc))
        zorder_layout.addWidget(make_btn("Vertical Mirror", "Mirror selected button positions vertically", self.mirror_vertical))

        placement_layout.addWidget(grid_widget)

        distribution_label = QtWidgets.QLabel("Distribution & Z-Order")
        distribution_label.setStyleSheet(_SECTION_LABEL)
        placement_layout.addWidget(distribution_label)

        placement_layout.addLayout(zorder_layout)
        add_divider(placement_layout)

        w['placement_widget'] = placement_widget

        # ===================================================================
        # Controller mode section (visible only when mode == 'controller')
        # ===================================================================
        controller_section = QtWidgets.QWidget()
        controller_section.setStyleSheet("background: transparent;")
        controller_section.setVisible(False)
        ctrl_layout = QtWidgets.QVBoxLayout(controller_section)
        set_margin_space(ctrl_layout, 0, 4)

        ctrl_header = QtWidgets.QLabel("Controller")
        ctrl_header.setStyleSheet(_SECTION_LABEL)
        ctrl_layout.addWidget(ctrl_header)

        # Summary labels (read-only display of current config)
        ctrl_info_widget = QtWidgets.QWidget()
        ctrl_info_widget.setMinimumWidth(0)
        ctrl_info_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Preferred
        )
        ctrl_info_widget.setStyleSheet(
            f"QWidget {{ background-color: {widget_color}; border-radius: 3px; }}"
            f"QLabel {{ color: #999; border: none; font-size: 10px; }}"
        )
        ctrl_info_layout = QtWidgets.QVBoxLayout(ctrl_info_widget)
        set_margin_space(ctrl_info_layout, 6, 3)

        ctrl_path_label = QtWidgets.QLabel("Path: —")
        ctrl_path_label.setWordWrap(True)
        ctrl_range_label = QtWidgets.QLabel("Range: —")
        ctrl_range_label.setWordWrap(True)
        ctrl_info_layout.addWidget(ctrl_path_label)
        ctrl_info_layout.addWidget(ctrl_range_label)
        ctrl_layout.addWidget(ctrl_info_widget)

        # Open Controller Manager button
        ctrl_manager_btn = QtWidgets.QPushButton("Open Controller Manager")
        ctrl_manager_btn.setFixedHeight(26)
        ctrl_manager_btn.setStyleSheet(
            "QPushButton { background-color: #2a2a2a; color: #ccc; border: 1px solid #444;"
            " border-radius: 4px; font-size: 11px; }"
            "QPushButton:hover { background-color: #353535; border: 1px solid #666; }"
        )
        ctrl_manager_btn.clicked.connect(self._open_controller_manager)
        ctrl_layout.addWidget(ctrl_manager_btn)

        add_divider(ctrl_layout)

        w['controller_section'] = controller_section
        w['ctrl_path_label'] = ctrl_path_label
        w['ctrl_range_label'] = ctrl_range_label
        w['ctrl_manager_btn'] = ctrl_manager_btn

        # ===================================================================
        # Assemble into container layout
        # ===================================================================
        container_layout.addWidget(w['fill_color'])
        container_layout.addWidget(w['text_format_widget'])
        container_layout.addWidget(w['transform_widget'])
        container_layout.addWidget(w['radius_widget'])
        container_layout.addWidget(w['controller_section'])
        container_layout.addWidget(w['placement_widget'])

        # ===================================================================
        # Wire signals for queue-based edits
        # ===================================================================
        rename_edit.textChanged.connect(self._queue_rename_change)
        rename_edit.returnPressed.connect(self._immediate_rename_apply)
        opacity_edit.valueChanged.connect(self._queue_opacity_change)
        transform_w_edit.valueChanged.connect(self._queue_transform_change)
        transform_h_edit.valueChanged.connect(self._queue_transform_change)
        rotation_edit.valueChanged.connect(self._queue_rotation_change)

        # Enable apply-to-all for transform controls
        transform_w_edit.setApplyToAllMode(True)
        transform_h_edit.setApplyToAllMode(True)
        transform_w_edit.applyToAllRequested.connect(self._apply_width_to_all)
        transform_h_edit.applyToAllRequested.connect(self._apply_height_to_all)

        # Radius
        uniform_radius.valueChanged.connect(self._queue_radius_change)
        top_left_radius.valueChanged.connect(self._queue_radius_change)
        top_right_radius.valueChanged.connect(self._queue_radius_change)
        bottom_right_radius.valueChanged.connect(self._queue_radius_change)
        bottom_left_radius.valueChanged.connect(self._queue_radius_change)
        single_radius.toggled.connect(self._handle_single_radius_toggle)

        # Color grid buttons (already connected above via partial)
        # Color picker (already connected above via colorChanged)

        # Deferred DB commit on drag release
        opacity_edit.dragFinished.connect(self._commit_drag_to_database)
        transform_w_edit.dragFinished.connect(self._commit_drag_to_database)
        transform_h_edit.dragFinished.connect(self._commit_drag_to_database)
        rotation_edit.dragFinished.connect(self._commit_drag_to_database)
        uniform_radius.dragFinished.connect(self._commit_drag_to_database)
        top_left_radius.dragFinished.connect(self._commit_drag_to_database)
        top_right_radius.dragFinished.connect(self._commit_drag_to_database)
        bottom_right_radius.dragFinished.connect(self._commit_drag_to_database)
        bottom_left_radius.dragFinished.connect(self._commit_drag_to_database)
        color_picker.dragFinished.connect(self._commit_drag_to_database)

    # ------------------------------------------------------------------
    # Queue methods
    # ------------------------------------------------------------------
    def _queue_rename_change(self):
        if not self.is_updating_widgets:
            self.pending_widget_changes['rename'] = self.widgets['rename_edit'].text()
            self.widget_update_timer.start(self.widget_update_delay)

    def _immediate_rename_apply(self):
        if not self.is_updating_widgets:
            self.rename(self.widgets['rename_edit'].text())

    def _queue_opacity_change(self, value):
        if not self.is_updating_widgets:
            self.pending_widget_changes['opacity'] = value
            self.widget_update_timer.start(50)

    def _queue_transform_change(self):
        if not self.is_updating_widgets:
            w_edit = self.widgets['transform_w_edit']
            h_edit = self.widgets['transform_h_edit']

            # Proportional scaling
            if self.widgets['transform_prop'].isChecked():
                sender = self.sender()
                canvas = self._get_canvas()
                if canvas:
                    selected_buttons = canvas.get_selected_buttons()
                    if selected_buttons:
                        ref = (canvas.last_selected_button
                               if canvas.last_selected_button and canvas.last_selected_button.is_selected
                               else selected_buttons[-1])
                        aspect = ref.width / ref.height if ref.height > 0 else 1.0

                        self.is_updating_widgets = True
                        if sender == w_edit:
                            h_edit.setValue(round(w_edit.value() / aspect))
                        elif sender == h_edit:
                            w_edit.setValue(round(h_edit.value() * aspect))
                        self.is_updating_widgets = False

            # Capture current reference dimensions
            canvas = self._get_canvas()
            if canvas:
                selected_buttons = canvas.get_selected_buttons()
                if selected_buttons:
                    ref = (canvas.last_selected_button
                           if canvas.last_selected_button and canvas.last_selected_button.is_selected
                           else selected_buttons[-1])
                    self.pending_widget_changes['transform'] = {
                        'target_width': w_edit.value(),
                        'target_height': h_edit.value(),
                        'ref_width': ref.width,
                        'ref_height': ref.height
                    }

            self.widget_update_timer.start(self.widget_update_delay)

    def _queue_rotation_change(self, value):
        if not self.is_updating_widgets:
            self.pending_widget_changes['rotation'] = value
            self.widget_update_timer.start(self.widget_update_delay)

    def reset_rotation(self):
        """Reset rotation to 0° for all selected buttons."""
        canvas = self._get_canvas()
        if not canvas:
            return
        selected = canvas.get_selected_buttons()
        if not selected:
            return
        mw = self.main_window
        for button in selected:
            button.rotation = 0
            button._invalidate_mask_cache()
            button.text_pixmap = None
            button.pose_pixmap = None
            button.update()
            mw.pending_button_updates.add(button.unique_id)
        canvas.update_button_positions()
        mw.batch_update_buttons_to_database(selected)
        self._sync_widgets()

    def _queue_radius_change(self):
        if not self.is_updating_widgets:
            w = self.widgets
            if w['single_radius'].isChecked():
                val = w['uniform_radius'].value()
                self.pending_widget_changes['radius'] = (val, val, val, val)
            else:
                self.pending_widget_changes['radius'] = (
                    w['top_left_radius'].value(),
                    w['top_right_radius'].value(),
                    w['bottom_right_radius'].value(),
                    w['bottom_left_radius'].value()
                )
            self.widget_update_timer.start(self.widget_update_delay)

    def _queue_color_change(self, color):
        if not self.is_updating_widgets:
            if hasattr(color, 'name'):
                color_str = color.name()
            elif isinstance(color, str):
                color_str = color
            else:
                color_str = str(color)

            if not (color_str.startswith('#') and len(color_str) == 7):
                return

            self.pending_widget_changes['color'] = color_str
            self.widget_update_timer.start(50)

    def _queue_text_format_change(self, format_type, value):
        if not self.is_updating_widgets:
            self.pending_widget_changes[f'text_{format_type}'] = value
            self.widget_update_timer.start(self.widget_update_delay)

    # ------------------------------------------------------------------
    # Apply queued changes
    # ------------------------------------------------------------------
    def _apply_widget_changes(self):
        if not self.pending_widget_changes:
            return
        canvas = self._get_canvas()
        if not canvas:
            self.pending_widget_changes.clear()
            return
        selected_buttons = canvas.get_selected_buttons()
        if not selected_buttons:
            self.pending_widget_changes.clear()
            return

        mw = self.main_window
        mw.setUpdatesEnabled(False)
        canvas.setUpdatesEnabled(False)

        try:
            for change_type, value in self.pending_widget_changes.items():
                if change_type == 'transform':
                    self.resize(value)
                    continue

                for button in selected_buttons:
                    if change_type == 'rename':
                        button.label = value
                        button.text_pixmap = None
                    elif change_type == 'opacity':
                        button.opacity = value / 100.0
                    elif change_type == 'radius':
                        tl, tr, br, bl = value
                        max_r = min(button.width, button.height) / 2
                        button.radius = [min(r, max_r) for r in (tl, tr, br, bl)]
                    elif change_type == 'color':
                        if isinstance(value, str) and value.startswith('#') and len(value) == 7:
                            button.color = value
                            button.controller_pixmap = None
                        else:
                            continue
                    elif change_type == 'text_color':
                        if isinstance(value, str) and value.startswith('#'):
                            button.text_color = value
                            button.text_pixmap = None
                            button.pose_pixmap = None
                    elif change_type == 'text_bold':
                        button.text_bold = value
                        button.text_pixmap = None
                        button.pose_pixmap = None
                    elif change_type == 'text_italic':
                        button.text_italic = value
                        button.text_pixmap = None
                        button.pose_pixmap = None
                    elif change_type == 'text_underline':
                        button.text_underline = value
                        button.text_pixmap = None
                        button.pose_pixmap = None
                    elif change_type == 'rotation':
                        button.rotation = value
                        button._invalidate_mask_cache()
                        button.text_pixmap = None
                        button.pose_pixmap = None

                    button.update()
                    mw.pending_button_updates.add(button.unique_id)

            if 'transform' in self.pending_widget_changes or 'rotation' in self.pending_widget_changes:
                canvas.update_button_positions()
        finally:
            canvas.setUpdatesEnabled(True)
            mw.setUpdatesEnabled(True)
            canvas.update()

        self.pending_widget_changes.clear()
        # Commit to DB now. The widget_update_timer (10-50 ms) already debounces
        # rapid edits, so this is safe for drag too. The dragFinished → _commit_drag_to_database
        # path becomes a no-op second call (guarded by _drag_dirty), which is harmless.
        self._drag_dirty = False
        if mw.pending_button_updates:
            mw.batch_update_buttons_to_database(selected_buttons)

    # ------------------------------------------------------------------
    # Deferred DB commit (called on drag release)
    # ------------------------------------------------------------------
    def _commit_drag_to_database(self):
        """Write pending visual changes to database. Called on dragFinished.

        Flush any still-pending widget-update timer first: dragFinished can
        fire in the same event loop tick as colorChanged (palette-click case),
        before the 10-50 ms widget_update_timer has had a chance to run. If
        we didn't flush here, _drag_dirty would still be False and the edit
        would be lost.
        """
        if self.widget_update_timer.isActive():
            self.widget_update_timer.stop()
            self._apply_widget_changes()
        if not self._drag_dirty:
            return
        self._drag_dirty = False
        canvas = self._get_canvas()
        if not canvas:
            return
        selected = canvas.get_selected_buttons()
        if selected:
            self.main_window.batch_update_buttons_to_database(selected)

    # ------------------------------------------------------------------
    # Button mutation methods
    # ------------------------------------------------------------------
    def _batch_operation(self, operation_func, *args, **kwargs):
        """Execute an operation on every selected button with batched updates."""
        mw = self.main_window
        if not mw.tab_system.current_tab:
            return
        canvas = mw.tab_system.tabs[mw.tab_system.current_tab]['canvas']
        selected_buttons = canvas.get_selected_buttons()
        tab_data = DM.PickerDataManager.get_tab_data(mw.tab_system.current_tab)
        if not selected_buttons:
            return

        operation_name = getattr(operation_func, '__name__', str(operation_func))
        if 'delete' in operation_name.lower():
            operation_func(*args, **kwargs)
            return

        mw.batch_update_active = True
        mw.edit_widgets_update_enabled = False
        canvas.setUpdatesEnabled(False)
        try:
            for button in selected_buttons:
                operation_func(button, *args, **kwargs)
                mw.pending_button_updates.add(button.unique_id)
            mw._flush_pending_updates()
        finally:
            canvas.setUpdatesEnabled(True)
            mw.edit_widgets_update_enabled = True
            mw.batch_update_active = False
            canvas.update()

    def rename(self, label):
        def op(button, lbl):
            button.label = lbl
            button.text_pixmap = None
            button.update()
        self._batch_operation(op, label)

    def set_opacity(self, value):
        canvas = self._get_canvas()
        selected_buttons = canvas.get_selected_buttons() if canvas else []
        ids = [b.unique_id for b in selected_buttons]
        DM.PickerDataManager.save_undo_state("Opacity Change", ids)

        def op(button, v):
            button.opacity = v / 100.0
            button.update()
        self._batch_operation(op, value)

    def resize(self, transform_data):
        canvas = self._get_canvas()
        if not canvas:
            return
        selected_buttons = canvas.get_selected_buttons()
        if not selected_buttons:
            return

        if isinstance(transform_data, dict):
            target_w = transform_data['target_width']
            target_h = transform_data['target_height']
            ref_w = transform_data['ref_width']
            ref_h = transform_data['ref_height']
        else:
            target_w, target_h = transform_data
            ref_w = selected_buttons[0].width
            ref_h = selected_buttons[0].height

        if ref_w > 0 and ref_h > 0:
            w_scale = target_w / ref_w
            h_scale = target_h / ref_h
            for button in selected_buttons:
                new_w = max(1, round(button.width * w_scale))
                new_h = max(1, round(button.height * h_scale))
                button.width = new_w
                if button.mode == 'pose':
                    button._original_height = new_h
                    button.height = new_w * 1.25
                else:
                    button.height = new_h
                button.text_pixmap = None
                button.pose_pixmap = None
                button.last_zoom_factor = 0
                button.update()
        else:
            for button in selected_buttons:
                button.width = max(1, round(target_w))
                button.height = max(1, round(target_h))
                button.update()

    def recolor(self, color):
        def op(button, c):
            button.color = c
            button.update()
        self._batch_operation(op, color)

    def set_text_color(self, color):
        def op(button, c):
            button.text_color = c
            button.text_pixmap = None
            button.pose_pixmap = None
            button.update()
        self._batch_operation(op, color)

    def set_radius(self, tl, tr, br, bl):
        def op(button, tl, tr, br, bl):
            button.set_radius(tl, tr, br, bl)
            button.update()
        self._batch_operation(op, tl, tr, br, bl)

    def match_size(self):
        canvas = self._get_canvas()
        if not canvas:
            return
        selected_buttons = canvas.get_selected_buttons()
        if not selected_buttons:
            return
        mw = self.main_window
        for button in selected_buttons:
            if button.mode != 'pose':
                button.width = button.height
                mw.update_button_data(button)
            button.update()
            mw.pending_button_updates.add(button.unique_id)
        canvas.update_button_positions()
        mw.batch_update_buttons_to_database(selected_buttons)
        self.on_selection_changed()

    def _apply_width_to_all(self, width):
        if self.is_updating_widgets:
            return
        canvas = self._get_canvas()
        if not canvas:
            return
        selected_buttons = canvas.get_selected_buttons()
        if not selected_buttons:
            return
        mw = self.main_window
        for button in selected_buttons:
            button.width = round(width)
            if button.mode == 'pose':
                button.height = button.width * 1.25
            button.update()
            mw.pending_button_updates.add(button.unique_id)
        canvas.update_button_positions()
        mw._process_batch_updates()
        self.on_selection_changed()

    def _apply_height_to_all(self, height):
        if self.is_updating_widgets:
            return
        canvas = self._get_canvas()
        if not canvas:
            return
        selected_buttons = canvas.get_selected_buttons()
        if not selected_buttons:
            return
        mw = self.main_window
        for button in selected_buttons:
            if button.mode != 'pose':
                button.height = round(height)
            button.update()
            mw.pending_button_updates.add(button.unique_id)
        canvas.update_button_positions()
        mw._process_batch_updates()
        self.on_selection_changed()

    # ------------------------------------------------------------------
    # Layout / placement delegates  (call through to canvas)
    # ------------------------------------------------------------------
    def _get_buttons_and_canvas(self):
        canvas = self._get_canvas()
        if not canvas:
            return None, []
        return canvas, canvas.get_selected_buttons()

    def align_left(self):
        c = self._get_canvas()
        if c: c.align_button_left()

    def align_right(self):
        c = self._get_canvas()
        if c: c.align_button_right()

    def align_top(self):
        c = self._get_canvas()
        if c: c.align_button_top()

    def align_bottom(self):
        c = self._get_canvas()
        if c: c.align_button_bottom()

    def align_vcenter(self):
        c = self._get_canvas()
        if c: c.align_button_center()

    def align_hcenter(self):
        c = self._get_canvas()
        if c: c.align_button_middle()

    def distribute_horizontal(self):
        c = self._get_canvas()
        if c: c.evenly_space_horizontal()

    def distribute_vertical(self):
        c = self._get_canvas()
        if c: c.evenly_space_vertical()

    def move_behind(self):
        buttons = self._get_selected_buttons()
        if buttons:
            buttons[-1].move_button_behind()

    def bring_forward(self):
        buttons = self._get_selected_buttons()
        if buttons:
            buttons[-1].bring_button_forward()

    def mirror_horizontal(self):
        buttons = self._get_selected_buttons()
        if buttons:
            buttons[-1].parent().horizontal_mirror_button_positions()

    def mirror_horizontal_wc(self):
        buttons = self._get_selected_buttons()
        if buttons:
            buttons[-1].parent().horizontal_mirror_button_positions(apply_counterparts=True)

    def mirror_vertical(self):
        buttons = self._get_selected_buttons()
        if buttons:
            buttons[-1].parent().vertical_mirror_button_positions()

    # ------------------------------------------------------------------
    # Widget sync  (selection changed → update widgets)
    # ------------------------------------------------------------------
    def on_selection_changed(self):
        """Called when button selection changes. Debounced 50ms."""
        if not self._active:
            return
        self.pending_widget_changes.clear()
        self._edit_update_timer.start(50)

    def _sync_widgets(self):
        """Update edit widgets to reflect the current selection."""
        if not self._active:
            return
        canvas = self._get_canvas()
        if not canvas:
            return
        selected_buttons = canvas.get_selected_buttons()

        if not selected_buttons:
            self._clear_widgets()
            return
        self._populate_widgets(selected_buttons, canvas)

    def _clear_widgets(self):
        """Reset all edit widgets when nothing is selected."""
        self.is_updating_widgets = True
        w = self.widgets

        updates = [
            ('rename_edit', ''),
            ('transform_w_edit', 0),
            ('transform_h_edit', 0),
            ('rotation_edit', 0),
            ('uniform_radius', 0),
            ('top_left_radius', 0),
            ('top_right_radius', 0),
            ('bottom_right_radius', 0),
            ('bottom_left_radius', 0),
            ('opacity_edit', 100)
        ]

        for name, val in updates:
            widget = w[name]
            widget.blockSignals(True)
            if isinstance(widget, CLE.IntegerLineEdit):
                widget.setValue(val)
            elif hasattr(widget, 'setText'):
                widget.setText(str(val))
            elif hasattr(widget, 'setValue'):
                widget.setValue(val)
            widget.blockSignals(False)

        w['transform_prop'].blockSignals(True)
        w['transform_prop'].setChecked(False)
        w['transform_prop'].blockSignals(False)

        w['single_radius'].blockSignals(True)
        w['single_radius'].setChecked(True)
        w['single_radius'].blockSignals(False)

        # Default: single radius active
        w['uniform_radius'].setVisible(True)
        w['corners_widget'].setVisible(False)

        # Hide controller section
        w['controller_section'].setVisible(False)

        self._update_container_style(enabled=False)
        self.is_updating_widgets = False

    def _populate_widgets(self, selected_buttons, canvas):
        """Populate edit widgets from the current selection."""
        button = (canvas.last_selected_button
                  if canvas.last_selected_button and canvas.last_selected_button.is_selected
                  else selected_buttons[-1])

        self.is_updating_widgets = True
        w = self.widgets

        try:
            w['transform_w_edit'].setProperty('current_value', button.width)
            w['transform_h_edit'].setProperty('current_value', button.height)

            # Cap radius widget max to pill shape (half the shorter side)
            max_r = int(min(button.width, button.height) / 2)
            for rw in ('uniform_radius', 'top_left_radius', 'top_right_radius',
                        'bottom_right_radius', 'bottom_left_radius'):
                w[rw].setRange(0, max_r)

            updates = [
                ('rename_edit', button.label),
                ('opacity_edit', int(button.opacity * 100)),
                ('transform_w_edit', button.width),
                ('transform_h_edit', button.height),
                ('rotation_edit', round(button.rotation)),
                ('uniform_radius', button.radius[0]),
                ('top_left_radius', button.radius[0]),
                ('top_right_radius', button.radius[1]),
                ('bottom_right_radius', button.radius[2]),
                ('bottom_left_radius', button.radius[3])
            ]

            for name, val in updates:
                widget = w[name]
                # Skip updating a widget that currently has keyboard focus
                # to avoid disrupting user input
                if widget.hasFocus():
                    continue
                widget.blockSignals(True)
                if isinstance(widget, CLE.IntegerLineEdit):
                    # Use setValue to respect precision formatting
                    widget.setValue(val)
                elif hasattr(widget, 'setText'):
                    widget.setText(str(val))
                elif hasattr(widget, 'setValue'):
                    widget.setValue(val)
                widget.blockSignals(False)

            # Text formatting
            if 'text_color_picker' in w:
                w['text_color_picker'].blockSignals(True)
                tc = getattr(button, 'text_color', '#ffffff')
                if isinstance(tc, str) and tc.startswith('#'):
                    w['text_color_picker'].current_color = QtGui.QColor(tc)
                    w['text_color_picker'].update_all_from_color()
                w['text_color_picker'].blockSignals(False)

            for attr, key in [('text_bold', 'text_bold_btn'), ('text_italic', 'text_italic_btn'), ('text_underline', 'text_underline_btn')]:
                if key in w:
                    w[key].blockSignals(True)
                    w[key].setChecked(getattr(button, attr, False))
                    w[key].blockSignals(False)

            # Single radius state
            is_single = len(set(button.radius)) == 1
            w['single_radius'].blockSignals(True)
            w['single_radius'].setChecked(is_single)
            w['single_radius'].blockSignals(False)
            self._handle_single_radius_toggle(is_single)

            # Color picker
            if 'color_picker' in w:
                w['color_picker'].blockSignals(True)
                if isinstance(button.color, str) and button.color.startswith('#'):
                    w['color_picker'].current_color = QtGui.QColor(button.color)
                    w['color_picker'].update_all_from_color()
                w['color_picker'].blockSignals(False)

            # Controller section visibility & info
            is_controller = button.mode == 'controller'
            w['controller_section'].setVisible(is_controller)
            if is_controller:
                cd = getattr(button, 'controller_data', {})
                dp = cd.get('data_path', '—') or '—'
                min_v = cd.get('min_value', 0.0)
                max_v = cd.get('max_value', 1.0)
                w['ctrl_path_label'].setText(f"Path: {dp}")
                w['ctrl_range_label'].setText(f"Range: {min_v} – {max_v}")

            self._update_container_style(enabled=True)
        finally:
            self.is_updating_widgets = False

    def _open_controller_manager(self):
        """Open the Controller Manager dialog for the currently selected button."""
        canvas = self._get_canvas()
        if not canvas:
            return
        selected = canvas.get_selected_buttons()
        if not selected:
            return
        button = selected[-1]
        if button.mode == 'controller':
            button.show_controller_manager()

    def _handle_single_radius_toggle(self, checked):
        w = self.widgets
        if checked:
            # Entering single mode: take current top-left value as the uniform value
            val = w['top_left_radius'].value()
            w['uniform_radius'].blockSignals(True)
            w['uniform_radius'].setValue(val)
            w['uniform_radius'].blockSignals(False)
            w['uniform_radius'].setVisible(True)
            w['corners_widget'].setVisible(False)
        else:
            # Leaving single mode: spread uniform value to all corners
            val = w['uniform_radius'].value()
            for name in ['top_left_radius', 'top_right_radius', 'bottom_right_radius', 'bottom_left_radius']:
                w[name].blockSignals(True)
                w[name].setValue(val)
                w[name].blockSignals(False)
            w['uniform_radius'].setVisible(False)
            w['corners_widget'].setVisible(True)

        self._queue_radius_change()

    def _update_container_style(self, enabled=True):
        """Update widget group enabled/disabled styling."""
        w = self.widgets

        if enabled:
            style = (
                "QWidget {border:0px solid #617e1c;background-color:transparent;}"
                "QLabel {border:None;background-color:transparent;}"
                "QLineEdit {border:1px solid #333333;background-color:#222222; margin: 0px; padding: 3px;}"
            )
            groups = ['rename_widget', 'transform_widget', 'radius_widget', 'color_widget', 'text_format_widget']
            for name in groups:
                if name in w:
                    w[name].setEnabled(True)
            if 'color_widget' in w:
                w['color_widget'].setStyleSheet('border: 0px solid #444444; background-color: #222222;')
        else:
            # Disabled-state styling — gray out labels + inputs so the panel
            # reads as inactive without resorting to a graphics opacity effect
            # (those collide with the canvas-painted buttons' QPainter).
            style = (
                "QWidget {border:0px solid #eeeeee;background-color:transparent;}"
                "QLabel {border:None;background-color:transparent;color:#5a5a5a;}"
                "QLineEdit {border:1px solid #2a2a2a;background-color:#1a1a1a; "
                "color:#5a5a5a; margin: 0px; padding: 3px;}"
                "QPushButton {color:#5a5a5a;}"
            )
            groups = ['rename_widget', 'transform_widget', 'radius_widget', 'color_widget', 'text_format_widget']
            for name in groups:
                if name in w:
                    w[name].setEnabled(False)

        # Apply to the edit_button_page if available
        mw = self.main_window
        if hasattr(mw, 'edit_button_page'):
            mw.edit_button_page.setStyleSheet(style)
