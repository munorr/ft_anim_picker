"""Controller Manager Dialog for configuring picker button controller mode.

Allows setting Blender data path, value range, precision, and label
visibility for controller-mode picker buttons.
"""

import bpy
from PySide6 import QtWidgets, QtCore, QtGui

from . import utils as UT
from . import custom_button as CB
from .custom_segment_control import TextSegmentControl
from . import custom_button as CB

# -- Colour tokens (matches LaunchDialog / settings_page) -------------------
_BG         = "#1d1d1d"
_BORDER     = "rgba(255,255,255,0.06)"
_TEXT_MAIN  = "#e0e0e0"
_TEXT_SUB   = "#808080"
_TEXT_MUTED = "#666666"
_ACCENT     = "#1D65CA"
_SURFACE    = "rgba(255,255,255,{a})"
_CARD_BG    = "rgba(50,50,50,0.2)"
_INPUT_BG   = "rgba(50, 50, 50, 0.8)"
_INPUT_BORDER = "#3a3a3a"


def _make_btn(text, bg_tpl, text_color, *, border=False, height=32):
    """Create a styled button matching the codebase pattern."""
    btn = QtWidgets.QPushButton(text)
    btn.setFixedHeight(height)
    btn.setCursor(QtCore.Qt.PointingHandCursor)
    border_css = (
        f"border: 1px solid {_SURFACE.format(a='0.10')};"
        if border else "border: none;"
    )
    btn.setStyleSheet(f"""
        QPushButton {{
            background: {bg_tpl.format(a='0.55')};
            color: {text_color};
            {border_css}
            border-radius: 6px;
            font-size: 12px;
            font-weight: 500;
            padding: 0 14px;
        }}
        QPushButton:hover {{
            background: {bg_tpl.format(a='0.80')};
        }}
        QPushButton:pressed {{
            background: {bg_tpl.format(a='0.95')};
        }}
    """)
    return btn


class ControllerManagerDialog(QtWidgets.QWidget):
    """Popup dialog for configuring a controller-mode picker button."""

    def __init__(self, button, parent=None):
        if parent is None:
            from . import blender_main as MAIN
            manager = MAIN.PickerWindowManager.get_instance()
            parent = manager._picker_widgets[0] if manager._picker_widgets else None
        super().__init__(parent)
        from . import utils as UT
        self.setWindowFlags(UT.picker_window_flags())
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.button = button

        self.setFixedWidth(300)

        # Register with visibility manager
        self.parent_picker = parent
        if self.parent_picker:
            from . import blender_main
            visibility_manager = blender_main.PickerVisibilityManager.get_instance()
            visibility_manager.register_child_widget(self.parent_picker, self)

        # Dragging support
        self._drag_pos = None

        self._build_ui()
        self._populate_from_button()
        self._position_center()
        self.show()

    # ── UI Construction ───────────────────────────────────────────────────

    def _build_ui(self):
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Main styled card frame
        self.frame = QtWidgets.QFrame()
        self.frame.setStyleSheet(f"""
            QFrame {{
                background-color: {_BG};
                border-radius: 8px;
                border: 1px solid {_BORDER};
            }}
        """)
        root = QtWidgets.QVBoxLayout(self.frame)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(0)

        # ── Title row ──
        title_row = QtWidgets.QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title = QtWidgets.QLabel("Controller Manager")
        title.setStyleSheet(
            f"color: {_TEXT_MAIN}; font-size: 14px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        title_row.addWidget(title)
        title_row.addStretch()

        self.close_button = CB.CustomButton(icon=UT.get_icon('close_01.png',size=16,opacity=1), height=26, width=26, radius=26/2,color='#db2525',tooltip='Close')
        self.close_button.clicked.connect(self._close)
        title_row.addWidget(self.close_button)
        root.addLayout(title_row)
        root.addSpacing(14)

        # ── Field Type selector (Slider vs Omni 2D pad) ──
        ft_row = QtWidgets.QHBoxLayout()
        ft_label = self._section_label("Field Type")
        ft_row.addWidget(ft_label)
        ft_row.addStretch()
        self.field_type_segment = TextSegmentControl(
            ["Slider", "Omni"],
            height=24,
            font_size=11,
            radius=6,
            frame_radius=6,
            use_frame=True,
            frame_bg="rgba(255, 255, 255, 0.06)",
            selected_color="#1D65CA",
            expand=False,
        )
        self.field_type_segment.segment_changed.connect(self._on_field_type_changed)
        ft_row.addWidget(self.field_type_segment)
        root.addLayout(ft_row)
        root.addSpacing(8)

        # ── Data Path card ──
        dp_card = self._card()
        dp_lay = QtWidgets.QVBoxLayout(dp_card)
        dp_lay.setContentsMargins(12, 10, 12, 12)
        dp_lay.setSpacing(8)

        # Path type row
        pt_row = QtWidgets.QHBoxLayout()
        pt_label = self._section_label("Path Type")
        pt_row.addWidget(pt_label)
        pt_row.addStretch()

        self.path_type_segment = TextSegmentControl(
            ["Absolute", "Relative"],
            height=24,
            font_size=11,
            radius=6,
            frame_radius=6,
            use_frame=True,
            frame_bg="rgba(255, 255, 255, 0.06)",
            selected_color="#1D65CA",
            expand=False,
        )
        pt_row.addWidget(self.path_type_segment)
        dp_lay.addLayout(pt_row)
        self.path_type_segment.segment_changed.connect(self._on_path_type_changed)

        # Slider theme row (1D only)
        self.slider_theme_row_widget = QtWidgets.QWidget()
        st_row = QtWidgets.QHBoxLayout(self.slider_theme_row_widget)
        st_row.setContentsMargins(0, 0, 0, 0)
        st_label = self._section_label("Slider Theme")
        st_row.addWidget(st_label)
        st_row.addStretch()

        self.slider_theme_segment = TextSegmentControl(
            ["Bar", "Circle"],
            height=24,
            font_size=11,
            radius=6,
            frame_radius=6,
            use_frame=True,
            frame_bg="rgba(255, 255, 255, 0.06)",
            selected_color="#1D65CA",
            expand=False,
        )
        st_row.addWidget(self.slider_theme_segment)
        dp_lay.addWidget(self.slider_theme_row_widget)

        # Slider (1D) path input
        self.slider_path_widget = QtWidgets.QWidget()
        sp_lay = QtWidgets.QVBoxLayout(self.slider_path_widget)
        sp_lay.setContentsMargins(0, 0, 0, 0)
        sp_lay.setSpacing(6)
        sp_row = QtWidgets.QHBoxLayout()
        sp_row.setSpacing(6)
        self.data_path_edit = QtWidgets.QLineEdit()
        self.data_path_edit.setPlaceholderText('pose.bones["Bone"].location[0]')
        self.data_path_edit.setStyleSheet(self._input_ss())
        self.data_path_edit.setFixedHeight(30)
        sp_row.addWidget(self.data_path_edit, 1)
        self.data_path_pick_btn = self._make_path_pick_button(self.data_path_edit, height=30)
        sp_row.addWidget(self.data_path_pick_btn)
        sp_lay.addLayout(sp_row)
        dp_lay.addWidget(self.slider_path_widget)

        # Omni (2D) path inputs
        self.omni_path_widget = QtWidgets.QWidget()
        op_lay = QtWidgets.QVBoxLayout(self.omni_path_widget)
        op_lay.setContentsMargins(0, 0, 0, 0)
        op_lay.setSpacing(6)
        for label_text, attr_name, placeholder in [
            ("X", "data_path_x_edit", 'pose.bones["Bone"].location[0]'),
            ("Y", "data_path_y_edit", 'pose.bones["Bone"].location[1]'),
        ]:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(8)
            lbl = QtWidgets.QLabel(label_text)
            lbl.setFixedWidth(14)
            lbl.setStyleSheet(
                f"color: {_TEXT_SUB}; background: transparent; border: none; font-size: 11px;"
            )
            edit = QtWidgets.QLineEdit()
            edit.setPlaceholderText(placeholder)
            edit.setStyleSheet(self._input_ss())
            edit.setFixedHeight(28)
            setattr(self, attr_name, edit)
            row.addWidget(lbl)
            row.addWidget(edit, 1)
            pick_btn = self._make_path_pick_button(edit, height=28)
            setattr(self, attr_name + '_pick_btn', pick_btn)
            row.addWidget(pick_btn)
            op_lay.addLayout(row)
        dp_lay.addWidget(self.omni_path_widget)

        # Test row
        test_row = QtWidgets.QHBoxLayout()
        self.test_btn = CB.CustomButton("Test Path", height=28, color="#1D65CA")
        self.test_btn.clicked.connect(self._test_path)
        test_row.addWidget(self.test_btn)
        self.test_result_label = QtWidgets.QLabel("")
        self.test_result_label.setStyleSheet(
            f"color: {_TEXT_MUTED}; background: transparent; border: none; font-size: 11px;"
        )
        test_row.addWidget(self.test_result_label, 1)
        dp_lay.addLayout(test_row)

        root.addWidget(dp_card)
        root.addSpacing(8)

        # ── Range card (slider 1D) ──
        self.range_card_slider = self._card()
        range_lay = QtWidgets.QVBoxLayout(self.range_card_slider)
        range_lay.setContentsMargins(12, 10, 12, 12)
        range_lay.setSpacing(8)

        range_header = self._section_label("Range & Precision")
        range_lay.addWidget(range_header)

        # Min / Max row
        mm_row = QtWidgets.QHBoxLayout()
        mm_row.setSpacing(10)
        for label_text, attr_name, default in [("Min", "min_edit", "0.0"), ("Max", "max_edit", "1.0")]:
            lbl = QtWidgets.QLabel(label_text)
            lbl.setStyleSheet(
                f"color: {_TEXT_SUB}; background: transparent; border: none; font-size: 11px;"
            )
            edit = QtWidgets.QLineEdit(default)
            edit.setFixedHeight(24)
            edit.setAlignment(QtCore.Qt.AlignCenter)
            edit.setStyleSheet(self._input_ss())
            setattr(self, attr_name, edit)
            mm_row.addWidget(lbl)
            mm_row.addWidget(edit, 1)
        range_lay.addLayout(mm_row)

        # Precision / Default / Step row
        pds_row = QtWidgets.QHBoxLayout()
        pds_row.setSpacing(10)
        for label_text, attr_name, default in [("Precision", "precision_edit", "2"), ("Default", "default_edit", "0.0"), ("Step", "step_edit", "0.01")]:
            lbl = QtWidgets.QLabel(label_text)
            lbl.setStyleSheet(
                f"color: {_TEXT_SUB}; background: transparent; border: none; font-size: 11px;"
            )
            edit = QtWidgets.QLineEdit(default)
            edit.setFixedHeight(24)
            edit.setAlignment(QtCore.Qt.AlignCenter)
            edit.setStyleSheet(self._input_ss())
            setattr(self, attr_name, edit)
            pds_row.addWidget(lbl)
            pds_row.addWidget(edit, 1)
        range_lay.addLayout(pds_row)

        root.addWidget(self.range_card_slider)

        # ── Range card (omni 2D) ──
        self.range_card_omni = self._card()
        omni_lay = QtWidgets.QVBoxLayout(self.range_card_omni)
        omni_lay.setContentsMargins(12, 10, 12, 12)
        omni_lay.setSpacing(8)
        omni_lay.addWidget(self._section_label("Min | Max | Precision | Default"))

        for axis_label, min_attr, max_attr, prec_attr, def_attr, default_min, default_max in [
            ("X", "min_x_edit", "max_x_edit", "precision_x_edit", "default_x_edit", "-1.0", "1.0"),
            ("Y", "min_y_edit", "max_y_edit", "precision_y_edit", "default_y_edit", "-1.0", "1.0"),
        ]:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(6)
            axis_lbl = QtWidgets.QLabel(axis_label)
            axis_lbl.setFixedWidth(12)
            axis_lbl.setStyleSheet(
                f"color: {_TEXT_MAIN}; background: transparent; border: none; "
                "font-size: 11px; font-weight: 600;"
            )
            row.addWidget(axis_lbl)
            for attr_name, default, ph in [
                (min_attr, default_min, "min"),
                (max_attr, default_max, "max"),
                (prec_attr, "3", "prec"),
                (def_attr, "0.0", "def"),
            ]:
                edit = QtWidgets.QLineEdit(default)
                edit.setFixedHeight(24)
                edit.setAlignment(QtCore.Qt.AlignCenter)
                edit.setStyleSheet(self._input_ss())
                edit.setPlaceholderText(ph)
                setattr(self, attr_name, edit)
                row.addWidget(edit, 1)
            omni_lay.addLayout(row)

        root.addWidget(self.range_card_omni)
        root.addSpacing(14)

        # ── Apply button ──
        self.apply_btn = _make_btn("Apply", _ACCENT, _TEXT_MAIN)
        self.apply_btn.clicked.connect(self._apply)
        root.addWidget(self.apply_btn)

        outer.addWidget(self.frame)

    # ── Population & Apply ────────────────────────────────────────────────

    def _populate_from_button(self):
        cd = self.button.controller_data
        if not cd:
            self.field_type_segment.set_selected_index(0)
            self.path_type_segment.set_selected_index(0)
            self._on_field_type_changed(0)
            return

        is_omni = cd.get('field_type') == 'omni'
        self.field_type_segment.set_selected_index(1 if is_omni else 0)

        if cd.get('path_type', 'absolute') == 'relative':
            self.path_type_segment.set_selected_index(1)
        else:
            self.path_type_segment.set_selected_index(0)

        if cd.get('slider_theme', 'bar') == 'circle':
            self.slider_theme_segment.set_selected_index(1)
        else:
            self.slider_theme_segment.set_selected_index(0)

        self.data_path_edit.setText(cd.get('data_path', ''))
        self.min_edit.setText(str(cd.get('min_value', 0.0)))
        self.max_edit.setText(str(cd.get('max_value', 1.0)))
        self.precision_edit.setText(str(cd.get('precision', 2)))
        self.default_edit.setText(str(cd.get('default_value', 0.0)))
        self.step_edit.setText(str(cd.get('step', 0.01)))

        self.data_path_x_edit.setText(cd.get('data_path_x', ''))
        self.data_path_y_edit.setText(cd.get('data_path_y', ''))
        self.min_x_edit.setText(str(cd.get('min_value_x', -1.0)))
        self.max_x_edit.setText(str(cd.get('max_value_x', 1.0)))
        self.precision_x_edit.setText(str(cd.get('precision_x', 3)))
        self.default_x_edit.setText(str(cd.get('default_value_x', 0.0)))
        self.min_y_edit.setText(str(cd.get('min_value_y', -1.0)))
        self.max_y_edit.setText(str(cd.get('max_value_y', 1.0)))
        self.precision_y_edit.setText(str(cd.get('precision_y', 3)))
        self.default_y_edit.setText(str(cd.get('default_value_y', 0.0)))

        self._on_field_type_changed(1 if is_omni else 0)

    def _on_field_type_changed(self, index):
        """Show/hide slider vs omni sections based on the field type segment."""
        is_omni = (index == 1)
        self.slider_theme_row_widget.setVisible(not is_omni)
        self.slider_path_widget.setVisible(not is_omni)
        self.range_card_slider.setVisible(not is_omni)
        self.omni_path_widget.setVisible(is_omni)
        self.range_card_omni.setVisible(is_omni)
        # Force the dialog to shrink to its new natural height. adjustSize()
        # alone doesn't reliably shrink frameless top-level widgets after
        # children are hidden.
        self.frame.layout().activate()
        self.frame.updateGeometry()
        self.layout().activate()
        self.updateGeometry()
        self.resize(self.width(), self.sizeHint().height())

    def _apply(self):
        is_omni = self.field_type_segment.get_selected_index() == 1
        path_type = 'relative' if self.path_type_segment.get_selected_index() == 1 else 'absolute'

        if is_omni:
            cd = {
                'field_type': 'omni',
                'omni_theme': 'pad',
                'path_type': path_type,
                'data_path_x': self.data_path_x_edit.text().strip(),
                'data_path_y': self.data_path_y_edit.text().strip(),
                'min_value_x': self._safe_float(self.min_x_edit.text(), -1.0),
                'max_value_x': self._safe_float(self.max_x_edit.text(), 1.0),
                'precision_x': max(0, min(6, int(self._safe_float(self.precision_x_edit.text(), 3)))),
                'default_value_x': self._safe_float(self.default_x_edit.text(), 0.0),
                'min_value_y': self._safe_float(self.min_y_edit.text(), -1.0),
                'max_value_y': self._safe_float(self.max_y_edit.text(), 1.0),
                'precision_y': max(0, min(6, int(self._safe_float(self.precision_y_edit.text(), 3)))),
                'default_value_y': self._safe_float(self.default_y_edit.text(), 0.0),
            }
        else:
            cd = {
                'field_type': 'slider',
                'slider_theme': 'circle' if self.slider_theme_segment.get_selected_index() == 1 else 'bar',
                'data_path': self.data_path_edit.text().strip(),
                'path_type': path_type,
                'min_value': self._safe_float(self.min_edit.text(), 0.0),
                'max_value': self._safe_float(self.max_edit.text(), 1.0),
                'precision': max(0, min(6, int(self._safe_float(self.precision_edit.text(), 2)))),
                'default_value': self._safe_float(self.default_edit.text(), 0.0),
                'step': self._safe_float(self.step_edit.text(), 0.01),
            }

        self.button.controller_data = cd

        # Snap button shape so the omni pad is large and square — width is
        # treated as the dominant dimension and height is derived from it,
        # similar to how pose buttons enforce a fixed aspect ratio.
        if is_omni:
            self._snap_omni_button_shape(self.button)

        # Restart sync with new path(s)
        self.button._stop_controller_sync()
        if is_omni:
            x_val, y_val = self.button._read_controller_xy()
            self.button._controller_value = x_val if x_val is not None else cd['default_value_x']
            self.button._controller_value_y = y_val if y_val is not None else cd['default_value_y']
        else:
            val = self.button._read_controller_value()
            if val is not None:
                self.button._controller_value = val
            else:
                self.button._controller_value = cd['default_value']
        self.button._start_controller_sync()

        # Invalidate pixmap and save
        self.button.controller_pixmap = None
        canvas = self.button.parent()
        if canvas:
            # Re-layout in case the snap changed the button's width/height,
            # then repaint.
            if hasattr(canvas, 'update_button_positions'):
                canvas.update_button_positions()
            canvas.update()
        self.button.changed.emit(self.button)

        # Flush to database
        main_window = self.button.window()
        from . import blender_ui as UI
        if isinstance(main_window, UI.BlenderAnimPickerWindow):
            if hasattr(main_window, 'pending_button_updates'):
                main_window.pending_button_updates.add(self.button.unique_id)
            if hasattr(main_window, '_flush_pending_updates'):
                main_window._flush_pending_updates()

        self._close()

    def _test_path(self):
        """Test the data path(s) by reading the current value."""
        is_omni = self.field_type_segment.get_selected_index() == 1
        old_cd = self.button.controller_data
        test_cd = dict(old_cd) if old_cd else {}
        test_cd['path_type'] = 'relative' if self.path_type_segment.get_selected_index() == 1 else 'absolute'

        if is_omni:
            test_cd['field_type'] = 'omni'
            test_cd['data_path_x'] = self.data_path_x_edit.text().strip()
            test_cd['data_path_y'] = self.data_path_y_edit.text().strip()
            self.button.controller_data = test_cd
            self.button._controller_last_error = ''
            resolved_x = self.button._resolve_controller_data_path('data_path_x')
            resolved_y = self.button._resolve_controller_data_path('data_path_y')
            x_val, y_val = self.button._read_controller_xy()
            self.button.controller_data = old_cd
            if x_val is not None or y_val is not None:
                prec_x = max(0, min(6, int(self._safe_float(self.precision_x_edit.text(), 3))))
                prec_y = max(0, min(6, int(self._safe_float(self.precision_y_edit.text(), 3))))
                x_text = f"{x_val:.{prec_x}f}" if x_val is not None else "—"
                y_text = f"{y_val:.{prec_y}f}" if y_val is not None else "—"
                self.test_result_label.setText(f"= ({x_text}, {y_text})")
                self.test_result_label.setToolTip(f"X: {resolved_x}\nY: {resolved_y}")
                self.test_result_label.setStyleSheet(
                    "color: #4caf50; background: transparent; border: none; font-size: 11px;"
                )
            else:
                error = getattr(self.button, '_controller_last_error', '')
                tip = f"X: {resolved_x}\nY: {resolved_y}\nError: {error}"
                self.test_result_label.setText("Invalid path(s)")
                self.test_result_label.setToolTip(tip)
                self.test_result_label.setStyleSheet(
                    "color: #f44336; background: transparent; border: none; font-size: 11px;"
                )
            return

        test_cd['field_type'] = 'slider'
        test_cd['data_path'] = self.data_path_edit.text().strip()
        self.button.controller_data = test_cd
        self.button._controller_last_error = ''

        resolved = self.button._resolve_controller_data_path()
        val = self.button._read_controller_value()
        self.button.controller_data = old_cd  # Restore

        if val is not None:
            precision = max(0, min(6, int(self._safe_float(self.precision_edit.text(), 2))))
            self.test_result_label.setText(f"= {val:.{precision}f}")
            self.test_result_label.setToolTip(f"Resolved: {resolved}")
            self.test_result_label.setStyleSheet(
                "color: #4caf50; background: transparent; border: none; font-size: 11px;"
            )
        else:
            error = getattr(self.button, '_controller_last_error', '')
            tip = f"Resolved: {resolved}\nError: {error}" if resolved else "Could not resolve path (no armature found)"
            self.test_result_label.setText("Invalid path")
            self.test_result_label.setToolTip(tip)
            self.test_result_label.setStyleSheet(
                "color: #f44336; background: transparent; border: none; font-size: 11px;"
            )

    # ── Path picker dropdown ──────────────────────────────────────────────

    def _make_path_pick_button(self, target_line_edit, height=28):
        """Create a three-dot icon button that opens the path picker menu for a specific line edit."""
        icon = UT.get_icon('ellipsis.png', size=14, opacity=0.9)
        btn = CB.CustomButton(
            icon=icon,
            size=14,
            width=height,
            height=height,
            color="rgba(255,255,255,0.06)",
            radius=6,
            tooltip="Pick path from selection",
        )
        btn.clicked.connect(lambda: self._show_path_picker_menu(target_line_edit, btn))
        return btn

    def _show_path_picker_menu(self, line_edit, anchor_widget):
        """Build and show the path picker menu for the current Blender selection."""
        is_relative = self.path_type_segment.get_selected_index() == 1
        source_label, groups = self._build_blender_path_options(is_relative)

        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(
            f"""
            QMenu {{
                background-color: #2a2a2a;
                color: {_TEXT_MAIN};
                border: 1px solid rgba(255,255,255,0.08);
                padding: 4px;
            }}
            QMenu::item {{
                padding: 4px 14px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {_ACCENT};
                color: white;
            }}
            QMenu::item:disabled {{
                color: {_TEXT_MUTED};
            }}
            QMenu::separator {{
                height: 1px;
                background: rgba(255,255,255,0.08);
                margin: 4px 6px;
            }}
            """
        )

        if source_label:
            header = menu.addAction(source_label)
            header.setEnabled(False)
            menu.addSeparator()

        if not groups:
            empty = menu.addAction("No selection")
            empty.setEnabled(False)
        else:
            for group_name, items in groups:
                sub = menu.addMenu(group_name)
                sub.setStyleSheet(menu.styleSheet())
                for axis_label, path_str in items:
                    act = sub.addAction(axis_label)
                    act.triggered.connect(
                        lambda _checked=False, p=path_str: line_edit.setText(p)
                    )

        pos = anchor_widget.mapToGlobal(QtCore.QPoint(0, anchor_widget.height()))
        menu.exec(pos)

    @staticmethod
    def _strip_to_relative_blender(full_path):
        """Strip the ``bpy.data.objects["..."].`` prefix to produce a relative path."""
        import re
        m = re.match(r'^bpy\.data\.objects\["[^"]+"\]\.(.*)$', full_path)
        if m:
            return m.group(1)
        return full_path

    def _on_path_type_changed(self, index):
        """Convert line edit text to match the new path type so users see what
        will actually be saved/used. Absolute → Relative strips the
        ``bpy.data.objects["X"].`` prefix; Relative → Absolute prepends a
        prefix derived from the namespace dropdown or the active armature.
        """
        edits = []
        for attr in ("data_path_edit", "data_path_x_edit", "data_path_y_edit"):
            edit = getattr(self, attr, None)
            if edit is not None:
                edits.append(edit)

        if index == 1:
            # Switching to Relative: strip any leading bpy.data.objects["..."].
            for edit in edits:
                text = edit.text().strip()
                if not text:
                    continue
                edit.setText(self._strip_to_relative_blender(text))
            return

        # Switching to Absolute: add a prefix if the path looks relative.
        prefix_obj_name = self._guess_armature_name_for_absolute()
        if not prefix_obj_name:
            return
        for edit in edits:
            text = edit.text().strip()
            if not text or text.startswith('bpy.data.objects['):
                continue
            edit.setText(f'bpy.data.objects["{prefix_obj_name}"].{text}')

    def _guess_armature_name_for_absolute(self):
        """Pick a sensible object name to prepend when converting to absolute.

        Prefers the namespace dropdown value, then the view layer's active
        armature. Returns '' if nothing reasonable is found.
        """
        try:
            from . import blender_ui as UI
            main_window = self.parent_picker
            if isinstance(main_window, UI.BlenderAnimPickerWindow):
                ns = main_window.namespace_dropdown.currentText()
                if ns and ns != 'None':
                    return ns
        except Exception:
            pass
        try:
            view_layer = bpy.context.view_layer
            active = view_layer.objects.active if view_layer else None
            if active and active.type == 'ARMATURE':
                return active.name
        except Exception:
            pass
        return ''

    def _build_blender_path_options(self, is_relative):
        """Return (source_label, [(group_name, [(axis_label, path), ...]), ...]).

        Produces absolute paths first (``bpy.data.objects["X"]...``), then
        strips them to relative form if ``is_relative`` is True, so a single
        source of truth drives both modes.
        """
        # In recent Blender versions, bpy.context attributes like active_object
        # and active_pose_bone are not reliably available when accessed from a
        # Qt event handler (outside the normal screen/area context). Use
        # view_layer.objects.active and getattr fallbacks for robustness.
        try:
            view_layer = bpy.context.view_layer
        except Exception:
            return ("", [])
        if view_layer is None:
            return ("", [])

        obj = view_layer.objects.active
        if obj is None:
            return ("", [])

        # From a Qt callback bpy.context.mode can be stale or default to OBJECT
        # even while the armature is in pose mode. The armature object's own
        # `mode` attribute is the authoritative signal for that armature.
        is_armature = getattr(obj, 'type', None) == 'ARMATURE'
        obj_mode = getattr(obj, 'mode', None)
        ctx_mode = getattr(bpy.context, 'mode', None)
        in_pose = (obj_mode == 'POSE') or (is_armature and ctx_mode == 'POSE')

        # Detect pose bone context. From a Qt callback, bpy.context.active_pose_bone
        # is often unavailable, so fall back to the armature's active bone (data.bones.active
        # is the underlying Bone; look up the matching PoseBone by name) and finally to the
        # first selected pose bone.
        bone_name = None
        rotation_mode = 'XYZ'
        if is_armature and in_pose:
            pose_bone = getattr(bpy.context, 'active_pose_bone', None)
            if pose_bone is None:
                arm_data = getattr(obj, 'data', None)
                pose = getattr(obj, 'pose', None)
                active_bone = getattr(getattr(arm_data, 'bones', None), 'active', None) if arm_data else None
                if active_bone is not None and pose is not None:
                    pose_bone = pose.bones.get(active_bone.name)
                if pose_bone is None and pose is not None:
                    selected = getattr(bpy.context, 'selected_pose_bones', None) \
                        or getattr(bpy.context, 'selected_pose_bones_from_active_object', None)
                    if selected:
                        for pb in selected:
                            if pb.id_data == obj:
                                pose_bone = pb
                                break
                        if pose_bone is None:
                            pose_bone = selected[0]
            if pose_bone is not None:
                bone_name = pose_bone.name
                rotation_mode = getattr(pose_bone, 'rotation_mode', 'XYZ')
        else:
            rotation_mode = getattr(obj, 'rotation_mode', 'XYZ')

        if bone_name is not None:
            prefix = f'bpy.data.objects["{obj.name}"].pose.bones["{bone_name}"]'
            source_label = f"Source: {obj.name} › {bone_name}"
        else:
            prefix = f'bpy.data.objects["{obj.name}"]'
            source_label = f"Source: {obj.name}"

        location_items = [
            ("X", f"{prefix}.location[0]"),
            ("Y", f"{prefix}.location[1]"),
            ("Z", f"{prefix}.location[2]"),
        ]
        if rotation_mode == 'QUATERNION':
            rotation_items = [
                ("W", f"{prefix}.rotation_quaternion[0]"),
                ("X", f"{prefix}.rotation_quaternion[1]"),
                ("Y", f"{prefix}.rotation_quaternion[2]"),
                ("Z", f"{prefix}.rotation_quaternion[3]"),
            ]
        elif rotation_mode == 'AXIS_ANGLE':
            rotation_items = [
                ("W", f"{prefix}.rotation_axis_angle[0]"),
                ("X", f"{prefix}.rotation_axis_angle[1]"),
                ("Y", f"{prefix}.rotation_axis_angle[2]"),
                ("Z", f"{prefix}.rotation_axis_angle[3]"),
            ]
        else:
            rotation_items = [
                ("X", f"{prefix}.rotation_euler[0]"),
                ("Y", f"{prefix}.rotation_euler[1]"),
                ("Z", f"{prefix}.rotation_euler[2]"),
            ]
        scale_items = [
            ("X", f"{prefix}.scale[0]"),
            ("Y", f"{prefix}.scale[1]"),
            ("Z", f"{prefix}.scale[2]"),
        ]

        if is_relative:
            location_items = [(a, self._strip_to_relative_blender(p)) for a, p in location_items]
            rotation_items = [(a, self._strip_to_relative_blender(p)) for a, p in rotation_items]
            scale_items = [(a, self._strip_to_relative_blender(p)) for a, p in scale_items]

        groups = [
            ("Location", location_items),
            ("Rotation", rotation_items),
            ("Scale", scale_items),
        ]
        return (source_label, groups)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _close(self):
        if self.parent_picker:
            from . import blender_main
            visibility_manager = blender_main.PickerVisibilityManager.get_instance()
            visibility_manager.unregister_child_widget(self.parent_picker, self)
        self.close()
        self.deleteLater()

    def exec(self):
        """Show and keep visible (non-blocking, frameless window)."""
        self.show()
        self.raise_()
        self.activateWindow()

    def _position_center(self):
        """Center the dialog within the parent picker window."""
        if self.parent_picker:
            pw = self.parent_picker
            geo = pw.geometry()
            self.adjustSize()
            dw = self.width()
            dh = self.height()
            cx = geo.x() + (geo.width() - dw) // 2
            cy = geo.y() + (geo.height() - dh) // 2
            self.move(cx, cy)

    @staticmethod
    def _snap_omni_button_shape(button):
        """Resize an omni controller button so the pad ends up square.

        Width is treated as the dominant dimension. Height is derived from
        width via ``PickerButton.omni_aspect_ratio(has_label)``.
        """
        show_label = button.controller_data.get('show_label', True)
        has_label = bool(button.label and button.label.strip() and show_label)
        ratio = type(button).omni_aspect_ratio(has_label)
        new_width = max(round(button.width, 1), 80.0)
        new_height = round(new_width * ratio, 1)
        if abs(button.width - new_width) > 0.5 or abs(button.height - new_height) > 0.5:
            button.width = new_width
            button.height = new_height
            button.cached_mask = None
            button._cached_envelope = None
            button._cached_envelope_key = None
            button._cached_scene_path = None
            button._cached_scene_path_key = None
            button.controller_pixmap = None
            button.last_size = None
            button.last_zoom_factor = 0

    @staticmethod
    def _safe_float(text, default=0.0):
        try:
            return float(text)
        except (ValueError, TypeError):
            return default

    # ── Dragging ──────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() & QtCore.Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ── Widget factories ──────────────────────────────────────────────────

    @staticmethod
    def _card():
        """Create a styled card QFrame matching codebase pattern."""
        card = QtWidgets.QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {_CARD_BG};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        return card

    @staticmethod
    def _section_label(text):
        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet(
            f"color: {_TEXT_MAIN}; font-size: 11px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        return lbl

    @staticmethod
    def _input_ss():
        return f"""
            QLineEdit {{
                background: {_INPUT_BG};
                color: {_TEXT_MAIN};
                border: 1px solid {_INPUT_BORDER};
                border-radius: 6px;
                padding: 3px 8px;
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border: 1px solid rgba(29,101,202,0.6);
            }}
            QLineEdit::placeholder {{
                color: {_TEXT_MUTED};
            }}
        """
