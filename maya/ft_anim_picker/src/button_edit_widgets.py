try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Qt, Signal, QSize
    from PySide6.QtGui import QColor, QIntValidator
    from shiboken6 import wrapInstance
    from PySide6.QtGui import QColor, QShortcut
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve, Qt, Signal, QSize
    from PySide2.QtGui import QColor, QIntValidator
    from PySide2.QtWidgets import QShortcut
    from shiboken2 import wrapInstance

from . import custom_line_edit as CLE
from . import custom_button as CB
from . import ui as UI
from . import utils as UT
from . import picker_button as PB
from . import custom_slider as CS
from functools import partial
from . import custom_color_picker as CCP

def create_button_edit_widgets(parent):
    """Optimized widget creation with better performance and batching support"""
    widgets = {}

    label_color = "#666666"
    widget_color = "#1d1d1d"

    def set_margin_space(layout,margin,space):
        layout.setContentsMargins(margin,margin,margin,margin)
        layout.setSpacing(space)
    
    def set_widget_style(widget, color):
        widget.setStyleSheet(f"""QWidget {{background-color: {color}; padding: 0px; border-radius: 3px; border: 0px solid #666666;}}
        QLabel {{color: {label_color}; border: none;font-size: 11px;}}
        """)

    #---------------------------------------------------------------------------------------------------------------------------------------
    # Rename widget - simplified
    rename_widget = QtWidgets.QWidget()
    rename_widget.setStyleSheet(f"border: 1px solid #435813; background-color: {widget_color};")
    rename_widget.setFixedHeight(30)
    rename_layout = QtWidgets.QHBoxLayout(rename_widget)
    set_margin_space(rename_layout,0,0)
    
    rename_edit = QtWidgets.QLineEdit()
    rename_edit.setPlaceholderText("Rename Button")
    rename_edit.setStyleSheet(f''' 
    QLineEdit {{
        background-color: transparent; 
        color: #dddddd; 
        border: 0px solid #5c7918; 
        border-radius: 3px; 
        padding: 2px;
    }}''')
    rename_edit.setFixedHeight(28)
    
    # Clear button
    clear_button = QtWidgets.QPushButton()
    clear_button.setFixedSize(28, 28)
    clear_button.setIcon(QtGui.QIcon(UT.get_icon("close_01.png",size=13,opacity=0.4)))
    clear_button.setStyleSheet('''
        QPushButton {
            background-color: transparent;
            color: #dddddd;
            border-radius: 3px;
            border: 0px solid #5c7918;
            font-weight: bold;
            font-size: 12px;
        }
    ''')

    rename_edit.returnPressed.connect(partial(UT.maya_main_window().activateWindow))
    clear_button.clicked.connect(lambda: rename_edit.setText(" "))

    rename_layout.addWidget(rename_edit)
    rename_layout.addWidget(clear_button)

    widgets['rename_widget'] = rename_widget
    widgets['rename_edit'] = rename_edit
    widgets['clear_button'] = clear_button
    #---------------------------------------------------------------------------------------------------------------------------------------
    # Transform widget
    transform_widget = QtWidgets.QWidget()
    set_widget_style(transform_widget, widget_color)
    transform_main_layout = QtWidgets.QVBoxLayout(transform_widget)
    set_margin_space(transform_main_layout,6,4)

    transform_layout = QtWidgets.QHBoxLayout()
    set_margin_space(transform_layout,2,4)
    
    
    transform_label = QtWidgets.QLabel("Size")
    transform_label.setStyleSheet(f"color: {label_color};")

    transform_prop = CB.CustomRadioButton("", fill=True, width=8, height=8, color="#6c9809")
    transform_w_edit = CLE.IntegerLineEdit(min_value=0, max_value=2000, increment=1, width=None, height=18, label="W")
    transform_h_edit = CLE.IntegerLineEdit(min_value=0, max_value=2000, increment=1, width=None, height=18, label="H")
    transform_match = CB.CustomButton("", width=6, height=18, color="#6c9809", tooltip="Match Width to Height")
    
    transform_main_layout.addWidget(transform_label)
    transform_main_layout.addLayout(transform_layout)

    transform_layout.addWidget(transform_prop)
    transform_layout.addWidget(transform_w_edit)
    transform_layout.addWidget(transform_h_edit)
    transform_layout.addWidget(transform_match)
    

    widgets['transform_widget'] = transform_widget
    widgets['transform_prop'] = transform_prop
    widgets['transform_w_edit'] = transform_w_edit
    widgets['transform_h_edit'] = transform_h_edit
    widgets['transform_match'] = transform_match

    # Connect the transform_match button to call match_button_size
    transform_match.clicked.connect(lambda: parent.match_button_size())
    #---------------------------------------------------------------------------------------------------------------------------------------
    # Radius widget
    radius_widget = QtWidgets.QWidget()
    set_widget_style(radius_widget, widget_color)
    radius_main_layout = QtWidgets.QVBoxLayout(radius_widget)
    set_margin_space(radius_main_layout,6,4)
    
    radius_label = QtWidgets.QLabel("Radius")
    radius_label.setStyleSheet(f"color: {label_color};")   
    radius_layout = QtWidgets.QHBoxLayout()
    set_margin_space(radius_layout,2,4)
    
    srl = QtWidgets.QHBoxLayout()
    set_margin_space(srl,0,0)
    
    rl_right = QtWidgets.QVBoxLayout()
    set_margin_space(rl_right,0,4)
    trl = QtWidgets.QHBoxLayout()
    set_margin_space(trl,0,4)
    brl = QtWidgets.QHBoxLayout()
    set_margin_space(brl,0,4)

    radius_main_layout.addWidget(radius_label)
    radius_main_layout.addLayout(radius_layout)

    radius_layout.addLayout(srl)
    rl_right.addLayout(trl)
    rl_right.addLayout(brl)
    radius_layout.addLayout(rl_right)
    
    bh = 2000  # button height max
    top_left_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=18, label="╭")
    top_right_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=18, label="╮")
    single_radius = CB.CustomRadioButton("", fill=True, width=8, height=8, color="#6c9809")
    bottom_left_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=18, label="╰")
    bottom_right_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, height=18, label="╯")

    srl.addWidget(single_radius)

    trl.addWidget(top_left_radius)
    trl.addWidget(top_right_radius)
    
    brl.addWidget(bottom_left_radius)
    brl.addWidget(bottom_right_radius)
    
    widgets['radius_widget'] = radius_widget
    widgets['top_left_radius'] = top_left_radius
    widgets['top_right_radius'] = top_right_radius
    widgets['single_radius'] = single_radius
    widgets['bottom_left_radius'] = bottom_left_radius
    widgets['bottom_right_radius'] = bottom_right_radius
    #---------------------------------------------------------------------------------------------------------------------------------------
    # Opacity widget
    opacity_widget = QtWidgets.QWidget()
    set_widget_style(opacity_widget, widget_color)
    opacity_layout = QtWidgets.QVBoxLayout(opacity_widget)
    set_margin_space(opacity_layout,6,6)

    opacity_label = QtWidgets.QLabel("Opacity")
    opacity_label.setStyleSheet(f"color: {label_color};")
    opacity_layout.addWidget(opacity_label)

    # Create optimized opacity slider
    opacity_slider = CS.CustomSlider(
        min_value=0, max_value=100, float_precision=0, 
        height=18, radius=8, prefix='',
        suffix='%', color='#5c7918'
    )
    opacity_slider.setValue(100)
    opacity_layout.addWidget(opacity_slider)
    
    widgets['opacity_widget'] = opacity_widget  
    widgets['opacity_slider'] = opacity_slider
    #---------------------------------------------------------------------------------------------------------------------------------------
    # Thumbnail directory widget
    thumbnail_dir_widget = QtWidgets.QWidget()
    set_widget_style(thumbnail_dir_widget, widget_color)
    thumbnail_dir_layout = QtWidgets.QVBoxLayout(thumbnail_dir_widget)
    set_margin_space(thumbnail_dir_layout,6,6)
    
    thumbnail_dir_label = QtWidgets.QLabel("Thumbnail Directory:")
    thumbnail_dir_label.setStyleSheet("color: #666666;")
    
    thumbnail_dir_edit = QtWidgets.QLineEdit()
    thumbnail_dir_edit.setStyleSheet("background-color: #222222; color: #dddddd; border: 1px solid #444444; border-radius: 3px; padding: 2px;")
    thumbnail_dir_edit.setFixedHeight(24)
    thumbnail_dir_edit.setReadOnly(True)
    
    # Set the current thumbnail directory
    from . import data_management as DM
    thumbnail_dir = DM.PickerDataManager.get_thumbnail_directory()
    thumbnail_dir_edit.setText(thumbnail_dir)
    
    thumbnail_dir_button = QtWidgets.QPushButton("Browse")
    thumbnail_dir_button.setStyleSheet("""
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
    thumbnail_dir_button.setFixedHeight(24)
    
    thumbnail_dir_layout.addWidget(thumbnail_dir_label)
    thumbnail_dir_layout.addWidget(thumbnail_dir_edit)
    thumbnail_dir_layout.addWidget(thumbnail_dir_button)
    
    widgets['thumbnail_dir_widget'] = thumbnail_dir_widget
    widgets['thumbnail_dir_edit'] = thumbnail_dir_edit
    widgets['thumbnail_dir_button'] = thumbnail_dir_button
    
    # Connect thumbnail directory functionality
    def browse_thumbnail_directory():
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            parent,
            "Select Thumbnail Directory",
            thumbnail_dir_edit.text() or ""
        )
        if directory:
            thumbnail_dir_edit.setText(directory)
            DM.PickerDataManager.set_thumbnail_directory(directory)
    
    thumbnail_dir_button.clicked.connect(browse_thumbnail_directory)
    #---------------------------------------------------------------------------------------------------------------------------------------
    # Color widget
    color_widget = QtWidgets.QWidget()
    set_widget_style(color_widget, widget_color)
    color_layout = QtWidgets.QGridLayout(color_widget)
    color_layout.setSpacing(5)
    color_layout.setContentsMargins(3, 5, 3, 5)
    
    color_palette = [
        "#000000", "#3F3F3F", "#999999", "#9B0028", "#00045F",  
        "#0000FF", "#004618", "#250043", "#C700C7", "#894733",  
        "#3E221F", "#992500", "#FF0000", "#00FF00", "#004199",  
        "#FFFFFF", "#FFFF00", "#63DCFF", "#43FFA2", "#FFAFAF",  
        "#E3AC79", "#FFFF62", "#009953", "#D9916C", "#DFC74D",  
        "#A1CE46", "#3AC093", "#40D1B8", "#399DCD", "#9B6BCD"  
    ]
    
    color_buttons = []
    for i, color in enumerate(color_palette):
        color_button = QtWidgets.QPushButton()
        color_button.setFixedSize(20, 20)
        color_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {color}; 
                border: 0px solid #222222; 
                border-radius: 10px;
            }} 
            QPushButton:hover {{
                background-color: {UT.rgba_value(color, 1.2, alpha=1)};
            }}
        """)
        color_layout.addWidget(color_button, i // 5, i % 5)
        color_buttons.append(color_button)
        # Connect with throttled color change
        color_button.clicked.connect(partial(lambda c, main_window=parent: queue_color_change(main_window, c), color))
    
    widgets['color_widget'] = color_widget
    widgets['color_buttons'] = color_buttons
    #---------------------------------------------------------------------------------------------------------------------------------------
    color_picker = CCP.ColorPicker(mode='square')
    def handle_color_picker_change(qcolor):
        """Handle QColor from color picker and convert to hex string"""
        if isinstance(qcolor, QtGui.QColor):
            hex_color = qcolor.name()  # Convert QColor to hex string
            queue_color_change(parent, hex_color)
        else:
            # If it's already a string, use it directly
            queue_color_change(parent, qcolor)
    
    color_picker.colorChanged.connect(handle_color_picker_change)
    widgets['color_picker'] = color_picker

    #---------------------------------------------------------------------------------------------------------------------------------------
    # Placement widget
    placement_widget = QtWidgets.QWidget()
    set_widget_style(placement_widget, widget_color)
    placement_layout = QtWidgets.QVBoxLayout(placement_widget)
    set_margin_space(placement_layout, 6, 4)

    placement_label = QtWidgets.QLabel("Placement")
    placement_label.setStyleSheet(f"color: {label_color};")
    placement_layout.addWidget(placement_label)

    # Z-order and mirror buttons
    zorder_layout = QtWidgets.QVBoxLayout()
    set_margin_space(zorder_layout, 4, 6)

    def placement_button_style():
        return """
        QPushButton {
            background-color: #333333;
        }
        QPushButton:hover {
            background-color: #444444;
        }
        QPushButton:pressed {
            background-color: #555555;
        }
        QToolTip {
            background-color: #333333;
            color: #FFFFFF;
            border: 1px solid #222222;
        }
        """
    def zorder_button(btn, tooltip, callback):
        btn.setStyleSheet(placement_button_style())
        btn.setToolTip(tooltip)
        btn.setFixedHeight(24)
        btn.clicked.connect(callback)
        return btn

    move_behind_btn = QtWidgets.QPushButton("Move Behind")
    move_behind_btn = zorder_button(move_behind_btn, "Move selected button behind", lambda: move_selected_buttons_behind(parent))
    zorder_layout.addWidget(move_behind_btn)

    bring_forward_btn = QtWidgets.QPushButton("Bring Forward")
    bring_forward_btn = zorder_button(bring_forward_btn, "Bring selected button forward", lambda: bring_selected_buttons_forward(parent))
    zorder_layout.addWidget(bring_forward_btn)

    horizontal_mirror_btn = QtWidgets.QPushButton("Horizontal Mirror")
    horizontal_mirror_btn = zorder_button(horizontal_mirror_btn, "Mirror selected button positions horizontally", lambda: horizontal_mirror_selected_buttons(parent))
    zorder_layout.addWidget(horizontal_mirror_btn)

    horizontal_mirror_flip_btn = QtWidgets.QPushButton("Horizontal Mirror (WC)")
    horizontal_mirror_flip_btn = zorder_button(horizontal_mirror_flip_btn, "Mirror selected button positions horizontally and assigne counterpart objects", lambda: horizontal_mirror_selected_buttons_wc(parent))
    zorder_layout.addWidget(horizontal_mirror_flip_btn)

    vertical_mirror_btn = QtWidgets.QPushButton("Vertical Mirror")
    vertical_mirror_btn = zorder_button(vertical_mirror_btn, "Mirror selected button positions vertically", lambda: vertical_mirror_selected_buttons(parent))
    zorder_layout.addWidget(vertical_mirror_btn)


    # Create a grid widget for alignment options
    grid_widget = QtWidgets.QWidget()
    grid_layout = QtWidgets.QGridLayout(grid_widget)
    set_margin_space(grid_layout, 4, 6)

    def create_alignment_button(icon_path, tooltip, callback):
        btn = QtWidgets.QPushButton()
        btn.setStyleSheet(placement_button_style())
        btn.setFixedHeight(24)
        btn.setIcon(UT.get_icon(icon_path, opacity=0.9))
        btn.setIconSize(QtCore.QSize(20, 20))
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        return btn

    # Row 1: Vertical alignment options
    align_left_btn = create_alignment_button("align_left.png", "Align Left", lambda: align_selected_buttons_left(parent))
    align_center_btn = create_alignment_button("align_vCenter.png", "Align Vertical Center", lambda: align_selected_buttons_vcenter(parent))
    align_right_btn = create_alignment_button("align_right.png", "Align Right", lambda: align_selected_buttons_right(parent))
    v_space_btn = create_alignment_button("v_spacing.png", "Distribute Evenly (Vertical)", lambda: evenly_space_selected_buttons_vertical(parent))

    # Row 2: Horizontal alignment options
    align_top_btn = create_alignment_button("align_top.png", "Align Top", lambda: align_selected_buttons_top(parent))
    align_middle_btn = create_alignment_button("align_hCenter.png", "Align Horizontal Center", lambda: align_selected_buttons_hcenter(parent))
    align_bottom_btn = create_alignment_button("align_bottom.png", "Align Bottom", lambda: align_selected_buttons_bottom(parent))
    h_space_btn = create_alignment_button("h_spacing.png", "Distribute Evenly (Horizontal)", lambda: evenly_space_selected_buttons_horizontal(parent))

    grid_layout.addWidget(align_left_btn, 0, 0)
    grid_layout.addWidget(align_center_btn, 0, 1)
    grid_layout.addWidget(align_right_btn, 0, 2)
    grid_layout.addWidget(v_space_btn, 0, 3)

    grid_layout.addWidget(align_top_btn, 1, 0)
    grid_layout.addWidget(align_middle_btn, 1, 1)
    grid_layout.addWidget(align_bottom_btn, 1, 2)
    grid_layout.addWidget(h_space_btn, 1, 3)

    placement_layout.addWidget(grid_widget)
    placement_layout.addLayout(zorder_layout)

    widgets['placement_widget'] = placement_widget
    #---------------------------------------------------------------------------------------------------------------------------------------

    return widgets

# Helper functions
def queue_color_change(main_window, color):
    """FIXED: Queue color changes for batch processing with proper color handling"""
    if isinstance(main_window, UI.AnimPickerWindow):
        if not main_window.is_updating_widgets:
            # CRITICAL FIX: Ensure color is always a string
            if hasattr(color, 'name'):  # QColor object
                color_str = color.name()
            elif isinstance(color, str):
                color_str = color
            else:
                color_str = str(color)
            
            main_window.pending_widget_changes['color'] = color_str
            main_window.widget_update_timer.start(10)
            
def rename_selected_buttons(main_window, new_label):
    if isinstance(main_window, UI.AnimPickerWindow):
        main_window.rename_selected_buttons(new_label)

def change_opacity_for_selected_buttons(main_window, value):
    if isinstance(main_window, UI.AnimPickerWindow):
        main_window.change_opacity_for_selected_buttons(value)

def set_size_for_selected_buttons(main_window, width, height):
    if isinstance(main_window, UI.AnimPickerWindow):
        main_window.set_size_for_selected_buttons(width, height)

def set_radius_for_selected_buttons(main_window, tl, tr, br, bl):
    if isinstance(main_window, UI.AnimPickerWindow):
        main_window.set_radius_for_selected_buttons(tl, tr, br, bl)

def change_color_for_selected_buttons(main_window, color):
    if isinstance(main_window, UI.AnimPickerWindow):
        main_window.change_color_for_selected_buttons(color)

#---------------------------------------------------------------------------------------------------------------------------------------
# Placement widget helper functions
#---------------------------------------------------------------------------------------------------------------------------------------
def get_selected_picker_buttons(main_window):
    """Return a list of selected PickerButton objects from the current canvas."""
    canvas = getattr(main_window, 'get_canvas', lambda: None)()
    if not canvas and hasattr(main_window, 'tab_system'):
        # Try to get canvas from tab_system
        tab = getattr(main_window.tab_system, 'current_tab', None)
        if tab and hasattr(main_window.tab_system, 'tabs'):
            canvas = main_window.tab_system.tabs[tab].get('canvas', None)
    if canvas and hasattr(canvas, 'get_selected_buttons'):
        return canvas.get_selected_buttons()
    return []

def move_selected_buttons_behind(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button, 'move_button_behind'):
            button.move_button_behind()

def bring_selected_buttons_forward(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button, 'bring_button_forward'):
            button.bring_button_forward()

def horizontal_mirror_selected_buttons(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button.parent(), 'horizontal_mirror_button_positions'):
            button.parent().horizontal_mirror_button_positions()
            break

def horizontal_mirror_selected_buttons_wc(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button.parent(), 'horizontal_mirror_button_positions'):
            button.parent().horizontal_mirror_button_positions(apply_counterparts=True)
            break

def vertical_mirror_selected_buttons(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button.parent(), 'vertical_mirror_button_positions'):
            button.parent().vertical_mirror_button_positions()
            break

def align_selected_buttons_left(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button, 'align_button_left'):
            button.align_button_left()

def align_selected_buttons_vcenter(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button, 'align_button_center'):
            button.align_button_center()

def align_selected_buttons_right(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button, 'align_button_right'):
            button.align_button_right()

def align_selected_buttons_top(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button, 'align_button_top'):
            button.align_button_top()

def align_selected_buttons_hcenter(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button, 'align_button_middle'):
            button.align_button_middle()

def align_selected_buttons_bottom(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button, 'align_button_bottom'):
            button.align_button_bottom()

def evenly_space_selected_buttons_horizontal(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button, 'evenly_space_horizontal'):
            button.evenly_space_horizontal()

def evenly_space_selected_buttons_vertical(main_window):
    for button in get_selected_picker_buttons(main_window):
        if hasattr(button, 'evenly_space_vertical'):
            button.evenly_space_vertical()

def get_current_selected_button_color(main_window):
    buttons = get_selected_picker_buttons(main_window)
    if buttons:
        return getattr(buttons[0], 'color', '#444444')
    return '#444444'
