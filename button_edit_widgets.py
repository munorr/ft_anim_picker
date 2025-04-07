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

def create_button_edit_widgets(parent):
    widgets = {}
    #selected_button = PB.PickerButton()
    # Rename widget
    rename_widget = QtWidgets.QWidget()
    rename_widget.setFixedHeight(30)
    rename_layout = QtWidgets.QHBoxLayout(rename_widget)
    rename_layout.setContentsMargins(2, 2, 2, 2)
    rename_layout.setSpacing(6)
    rename_label = QtWidgets.QLabel("Rename:")
    rename_edit = QtWidgets.QLineEdit()
    
    rename_edit.setPlaceholderText("Rename Button")
    rename_edit.setStyleSheet('''background-color: #222222; color: #dddddd; border: 1px solid #5285A6; border-radius: 3px; padding: 2px;''')
    rename_edit.setFixedHeight(28)
    #rename_layout.addWidget(rename_label)
    rename_layout.addWidget(rename_edit)
    widgets['rename_widget'] = rename_widget
    widgets['rename_edit'] = rename_edit
    #layout.layout().addWidget(rename_widget)

    # Connect rename functionality
    #rename_edit.returnPressed.connect(lambda: rename_selected_buttons(parent, rename_edit.text()))
    def set_margin_space(layout,margin,space):
        layout.setContentsMargins(margin,margin,margin,margin)
        layout.setSpacing(space)

    # Opacity slider
    opacity_widget = QtWidgets.QWidget()
    opacity_widget.setStyleSheet("background-color: None; padding: 0px; border-radius: 3px;")
    opacity_layout = QtWidgets.QHBoxLayout(opacity_widget)
    opacity_layout.setContentsMargins(2, 4, 2, 4)
    opacity_layout.setSpacing(4)
    #------------------------------------------------------------------------------------------------------------------------------------------------------
    #-Opcity Slider
    opacity_frame = QtWidgets.QFrame()
    opacity_frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
    opacity_frame.setFixedHeight(24)
    opacity_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray; padding: 0px; margin: 0px; border-radius: 12px; background-color: rgba(35, 35, 35, .8);}}''')
    opacity_frame_col = QtWidgets.QHBoxLayout(opacity_frame)
    set_margin_space(opacity_frame_col, 4, 2)

    opacity_slider = CS.CustomSlider(min_value=0, max_value=100, float_precision=0, height=16, radius=8,prefix='Button Opacity: ',suffix='%', color='#444444')
    opacity_slider.setValue(100)

    opacity_frame_col.addWidget(opacity_slider)
    #------------------------------------------------------------------------------------------------------------------------------------------------------

    opacity_slider.setRange(0, 100)
    opacity_layout.addWidget(opacity_frame)
    widgets['opacity_widget'] = opacity_widget
    widgets['opacity_slider'] = opacity_slider
    #layout.layout().addWidget(opacity_widget)

    # Connect opacity functionality
    #opacity_slider.valueChanged.connect(lambda value: change_opacity_for_selected_buttons(parent, value))

    # Transform widget
    transform_widget = QtWidgets.QWidget()
    transform_layout = QtWidgets.QHBoxLayout(transform_widget)
    transform_layout.setAlignment(QtCore.Qt.AlignLeft)
    transform_layout.setContentsMargins(2, 2, 2, 2)
    transform_layout.setSpacing(4)
    transform_prop= CB.CustomRadioButton("", fill=True, width=8, height=8, color="#6c9809")
    transform_w_label = QtWidgets.QLabel("W:")
    transform_w_edit = CLE.IntegerLineEdit(min_value=0, max_value=1000, increment=1, width=None, height=18)
    transform_h_label = QtWidgets.QLabel("H:")
    transform_h_edit = CLE.IntegerLineEdit(min_value=0, max_value=1000, increment=1, width=None, height=18)
    transform_layout.addWidget(transform_prop)
    transform_layout.addWidget(transform_w_label)
    transform_layout.addWidget(transform_w_edit)
    transform_layout.addWidget(transform_h_label)
    transform_layout.addWidget(transform_h_edit)
    #widgets['single_radius'] = single_radius
    
    widgets['transform_widget'] = transform_widget
    widgets['transform_prop'] = transform_prop
    widgets['transform_w_edit'] = transform_w_edit
    widgets['transform_h_edit'] = transform_h_edit
    #layout.layout().addWidget(transform_widget)
    
    # Connect transform functionality
    def update_button_size():
        new_width = transform_w_edit.value()
        new_height = transform_h_edit.value()
        set_size_for_selected_buttons(parent, new_width, new_height)

    def scale_transfrom(value):
        if transform_w_label.isChecked():
            transform_h_edit.setValue(value)
        update_button_size()


        transform_w_edit.setValue(value)
        transform_h_edit.setValue(value)
        update_button_size()
    #transform_w_edit.valueChanged.connect(update_button_size)
    #transform_h_edit.valueChanged.connect(update_button_size)

    # Radius widget
    radius_widget = QtWidgets.QWidget()
    radius_widget.setStyleSheet("background-color: None; padding: 0px; border-radius: 3px;")
    radius_layout = QtWidgets.QVBoxLayout(radius_widget)
    radius_layout.setContentsMargins(2, 2, 2, 2)
    radius_layout.setSpacing(6)
    rl1 = QtWidgets.QHBoxLayout()
    rl2 = QtWidgets.QHBoxLayout()
    rl2.setAlignment(QtCore.Qt.AlignCenter)
    rl3 = QtWidgets.QHBoxLayout()
    radius_layout.addLayout(rl1)
    radius_layout.addLayout(rl2)
    radius_layout.addLayout(rl3)

    bh = 500# button height
    top_left_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, width=50, height=18)
    top_right_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, width=50, height=18)
    single_radius = CB.CustomRadioButton("", fill=True, width=8, height=8)
    bottom_left_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, width=50, height=18)
    bottom_right_radius = CLE.IntegerLineEdit(min_value=0, max_value=bh, increment=1, width=50, height=18)

    rl1.addWidget(top_left_radius)
    rl1.addWidget(top_right_radius)
    rl2.addWidget(single_radius)
    rl3.addWidget(bottom_left_radius)
    rl3.addWidget(bottom_right_radius)
    widgets['radius_widget'] = radius_widget
    widgets['top_left_radius'] = top_left_radius
    widgets['top_right_radius'] = top_right_radius
    widgets['single_radius'] = single_radius
    widgets['bottom_left_radius'] = bottom_left_radius
    widgets['bottom_right_radius'] = bottom_right_radius
    #layout.layout().addWidget(radius_widget)
    
    # Connect radius functionality
    def update_radius():
        tl = top_left_radius.value()
        tr = top_right_radius.value()
        br = bottom_right_radius.value()
        bl = bottom_left_radius.value()
        set_radius_for_selected_buttons(parent, tl, tr, br, bl)

    def update_all_radii(value):
        if single_radius.isChecked():
            top_right_radius.setValue(value)
            bottom_right_radius.setValue(value)
            bottom_left_radius.setValue(value)
        update_radius()

    def toggle_single_radius(checked):
        dss = "background-color: #222222; color: #444444; border: 1px solid #444444; border-radius: 3px;"
        ass = "background-color: #333333; color: #dddddd; border: 1px solid #444444; border-radius: 3px;"
        if checked:
            value = top_left_radius.value()
            top_left_radius.setStyleSheet("background-color: #6c9809; color: #dddddd; border: 1px solid #444444; border-radius: 3px;")
            
            #top_right_radius.setValue(value)
            top_right_radius.setEnabled(False)
            top_right_radius.setStyleSheet(dss)

            #bottom_right_radius.setValue(value)
            bottom_right_radius.setEnabled(False)
            bottom_right_radius.setStyleSheet(dss)

            #bottom_left_radius.setValue(value)
            bottom_left_radius.setEnabled(False)
            bottom_left_radius.setStyleSheet(dss)
        else:
            top_left_radius.setStyleSheet(ass)

            top_right_radius.setEnabled(True)
            top_right_radius.setStyleSheet(ass)

            bottom_right_radius.setEnabled(True)
            bottom_right_radius.setStyleSheet(ass)

            bottom_left_radius.setEnabled(True)
            bottom_left_radius.setStyleSheet(ass)
        update_radius()

    #top_left_radius.valueChanged.connect(update_all_radii)
    #top_right_radius.valueChanged.connect(update_radius)
    #bottom_right_radius.valueChanged.connect(update_radius)
    #bottom_left_radius.valueChanged.connect(update_radius)
    #single_radius.toggled.connect(toggle_single_radius)

    # Color widget
    color_widget = QtWidgets.QWidget()
    color_widget.setStyleSheet(('background-color:#222222;'))
    color_layout = QtWidgets.QGridLayout(color_widget)
    color_layout.setSpacing(5)
    color_layout.setContentsMargins(3, 5, 3, 5)
    '''color_palette = [
        "#828282", "#ffca0d", "#1accc7", "#f977f8", "#82b60b", 
        "#4e4e4e", "#ff7f0c", "#38578a", "#c347a5", "#567b02", 
        "#1b1b1b", "#f82929", "#18263d", "#552549", "#324801", 
        
    ]'''
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
        color_button.setStyleSheet(f"""QPushButton {{background-color: {color}; border: 0px solid #222222 ; border-radius: 10px;}} 
                                        QPushButton:hover {{background-color: {UT.rgba_value(color, 1.2, alpha=1)};}}""")
        color_layout.addWidget(color_button, i // 5, i % 5)
        color_buttons.append(color_button)
        color_button.clicked.connect(partial(change_color_for_selected_buttons, parent, color))
    widgets['color_widget'] = color_widget
    widgets['color_buttons'] = color_buttons
    #layout.layout().addWidget(color_widget)

    return widgets


# Helper functions
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
