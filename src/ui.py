import os
from functools import partial
import maya.cmds as cmds
from pathlib import Path
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
    from PySide6.QtGui import QColor
    from shiboken6 import wrapInstance
    from PySide6.QtGui import QColor, QShortcut
except ImportError:
    from PySide2 import QtWidgets, QtCore, QtGui
    from PySide2.QtCore import QTimer, QPropertyAnimation, QEasingCurve
    from PySide2.QtGui import QColor
    from PySide2.QtWidgets import QShortcut
    from shiboken2 import wrapInstance

from .import picker_button as PB
from .import picker_canvas as PC
from . import utils as UT
from . import custom_slider as CS
from . import tab_system as TS
from . import expandable_frame as EF
from . import custom_button as CB
from . import custom_line_edit as CLE
from . import data_management as DM
from . import button_edit_widgets as BEW
from . import tool_functions as TF
from . import custom_dialog as CD
from . fade_away_logic import FadeAway

# Get version from __init__
import ft_anim_picker
anim_picker_version = ft_anim_picker.src.__version__
anim_picker_version = f" (v{anim_picker_version})"

class AnimPickerWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(AnimPickerWindow, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setStyleSheet('''QWidget {background-color: rgba(40, 40, 40, 0.5); border-radius: 4px;}''')
        
        self.edit_mode = False
        self.fade_manager = FadeAway(self)

        self.setup_ui()
        self.setup_layout()
        
        # Setup tab system first
        self.setup_tab_system()
        
        # Then initialize the namespace dropdown
        
        
        self.setup_connections()
        self.setup_shortcuts()
        self.setup_edit_widgets()
        
        self.oldPos = self.pos()
        self.resizing = False
        self.resize_edge = None
        self.resize_range = 8 # Pixels from edge where resizing is active
        self.resize_handle.installEventFilter(self)
        self.main_frame.setMouseTracking(True)
        self.main_frame.installEventFilter(self)
        
        # Install event filters on all frames to ensure cursor updates properly
        self.util_frame.setMouseTracking(True)
        self.util_frame.installEventFilter(self)
        self.setMouseTracking(True)
        
        # Resize state tracking
        self.resize_state = {
            'active': False,
            'edge': None,
            'start_pos': None,
            'initial_size': None,
            'initial_pos': None,
            'last_update_time': 0,
            'update_interval_ms': 16,  # ~60 FPS for smoother resizing
            'buttons_update_interval_ms': 100,  # Less frequent full updates
            'last_buttons_update_time': 0,
            'cached_canvas': None,
            'cached_buttons': None
        }
        
        # Add resize timer for performance
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.setInterval(100)  # 100ms throttle for full updates
        self.resize_timer.timeout.connect(self.finalize_resize)
        
        self.available_ids = {}

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.fade_manager.show_frame_context_menu)
        self.image_scale_factor.valueChanged.connect(self.update_image_scale)

        self.update_namespace_dropdown()

        # Define widgets that should be affected by minimal mode
        minimal_affected_widgets = [
            {'widget': self.util_frame, 'hide_in_minimal': False},
            {'widget': self.main_frame, 'exclude': [self.canvas_frame]}, # Keep canvas frame visible
            {'widget': self.canvas_frame, 'exclude': [self.canvas_frame_row]}, # Keep the canvas content visible
            {'widget': self.tools_EF, 'hide_in_minimal': False},
            {'widget': self.canvas_tab_frame, 'hide_in_minimal': True},
            {'widget': self.namespace_dropdown, 'hide_in_minimal': True},
            {'widget': self.close_button, 'hide_in_minimal': True},
        ]

        # Set the affected widgets in the fade manager
        self.fade_manager.set_minimal_affected_widgets(minimal_affected_widgets)

    def setup_ui(self):
        # Allow window to be resized
        self.setMinimumSize(260, 260)
        self.setGeometry(1150,280,350,450)

        def set_margin_space(layout,margin,space):
            layout.setContentsMargins(margin,margin,margin,margin)
            layout.setSpacing(space)

        mls = 5 #main layout spacing
        mfs = 8 #main framespacing
        self.main_layout = QtWidgets.QVBoxLayout(self)
        set_margin_space(self.main_layout, mls, mls)

        mfc = 36 #main frame color
        self.main_frame = QtWidgets.QFrame()
        self.main_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray; border-radius: 4px; background-color: rgba({mfc}, {mfc}, {mfc}, .6);}}''')
        self.main_frame_col = QtWidgets.QVBoxLayout(self.main_frame)
        set_margin_space(self.main_frame_col, mfs, mfs)

        self.util_frame = QtWidgets.QFrame()
        self.util_frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.util_frame.setFixedHeight(24)
        self.util_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray; border-radius: 4px; background-color: rgba(40, 40, 40, .8);padding: 0px;}}''')
        self.util_frame_col = QtWidgets.QHBoxLayout(self.util_frame)
        self.util_frame_col.setAlignment(QtCore.Qt.AlignLeft)
        set_margin_space(self.util_frame_col, 2, 2)

        self.icon_image = QtWidgets.QLabel()
        package_dir = Path(__file__).parent
        icon_path = package_dir / 'ft_picker_icons' / 'ftap_logo_64.png'
        icon_pixmap = QtGui.QPixmap(str(icon_path))
        self.icon_image.setPixmap(icon_pixmap)
        #self.resize(icon_pixmap.width(), icon_pixmap.height())
        self.icon_image.setScaledContents(True)
        self.icon_image.setFixedSize(14, 14)

        self.util_frame_col.addSpacing(4)
        self.util_frame_col.addWidget(self.icon_image)

        file_util = CB.CustomButton(text='File', height=20, width=40, radius=3,color='#385c73',alpha=0,textColor='#aaaaaa', ContextMenu=True, onlyContext= True,
                                    cmColor='#333333',tooltip='File Utilities', flat=True)
        
        file_util.addMenuLabel("File Utilities",position=(0,0))
        file_util.addToMenu("Load Picker", self.load_picker, icon='loadPreset.png', position=(1,0))
        file_util.addToMenu("Store Picker", self.store_picker, icon='save.png', position=(2,0))
        
        edit_util = CB.CustomButton(text='Edit', height=20, width=40, radius=3,color='#385c73',alpha=0,textColor='#aaaaaa', ContextMenu=True, onlyContext= True,
                                    cmColor='#333333',tooltip='Edit Utilities', flat=True)
        
        edit_util.addToMenu("Edit Mode", self.toggle_edit_mode, icon='setEdEditMode.png', position=(0,0))
        edit_util.addToMenu("Mirror Preferences", self.open_mirror_preferences, icon='syncOn.png', position=(1,0))
        edit_util.addToMenu("Minimal Mode", self.fade_manager.toggle_minimal_mode, icon='eye.png', position=(2,0))
        edit_util.addToMenu("Toggle Fade Away", self.fade_manager.toggle_fade_away, icon='eye.png', position=(3,0))

        info_util = CB.CustomButton(text='Info', height=20, width=40, radius=3,color='#385c73',alpha=0,textColor='#aaaaaa', ContextMenu=True, onlyContext= True,
                                    cmColor='#333333',tooltip='Help', flat=True)
        
        
        info_util.addMenuLabel(f"Anim Picker{anim_picker_version}",position=(0,0))
        info_util.addToMenu(f"Manual", self.info, icon='info.png', position=(1,0))
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #-Close button
        self.close_button = CB.CustomButton(icon=UT.get_icon('close_01.png',size=12,opacity=.7), height=16, width=16, radius=3,color='#c0091a',tooltip='Close')
        #------------------------------------------------------------------------------------------------------------------------------------------------------

        self.util_frame_col.addWidget(file_util)
        self.util_frame_col.addWidget(edit_util)
        self.util_frame_col.addWidget(info_util)
        self.util_frame_col.addStretch(1)
        self.util_frame_col.addWidget(self.close_button)
        self.util_frame_col.addSpacing(2)
        #------------------------------------------------------------------------------------------------------------------------------------------------------

        self.top_col = QtWidgets.QHBoxLayout()
        self.area_01_col = QtWidgets.QHBoxLayout()
        self.edit_row = QtWidgets.QVBoxLayout()
        
        
        self.picker_canvas_col1 = QtWidgets.QHBoxLayout()
        self.tool_col = QtWidgets.QHBoxLayout()
        self.tool_col.setAlignment(QtCore.Qt.AlignBottom)
        self.bottom_col = QtWidgets.QHBoxLayout()
        self.bottom_col.setAlignment(QtCore.Qt.AlignRight)

        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.canvas_frame = QtWidgets.QFrame()
        self.canvas_frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.canvas_frame.setMinimumWidth(160)
        self.canvas_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray; border-radius: 3px; background-color: rgba(40, 40, 40, .8);}}''')
        self.canvas_frame_row = QtWidgets.QVBoxLayout(self.canvas_frame)
        set_margin_space(self.canvas_frame_row, 4, 4)
        
        #-Canvas Tab Frame
        self.canvas_tab_frame = QtWidgets.QFrame()
        self.canvas_tab_frame.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        self.canvas_tab_frame.setFixedHeight(24)
        self.canvas_tab_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray; border-radius: 12px; background-color: rgba(55, 55, 55, .4);}}''')

        # Create a scroll area
        self.canvas_tab_frame_scroll_area = CS.HorizontalScrollArea() #QtWidgets.QScrollArea()
        self.canvas_tab_frame_scroll_area.setWidgetResizable(True)
        self.canvas_tab_frame_scroll_area.setFixedHeight(24)
        self.canvas_tab_frame_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.canvas_tab_frame_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        self.canvas_tab_frame_scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:horizontal {
                border: none;
                background: transparent;
                height: 8px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:horizontal {
                background: rgba(100, 100, 100, 0.5);
                min-width: 20px;
                border-radius: 0px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """)
        
        self.canvas_tab_frame_scroll_area.setWidget(self.canvas_tab_frame)
        
        self.canvas_tab_frame_col = QtWidgets.QHBoxLayout(self.canvas_tab_frame)
        self.addTabButton = CB.CustomButton(icon=UT.get_icon('add.png',size=10,opacity=.9), height=16, width=16, radius=8,color='#91cb08',tooltip='Add New Tab')
        set_margin_space(self.canvas_tab_frame_col, 4, 2)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.namespace_dropdown = QtWidgets.QComboBox(self)
        self.namespace_dropdown.setFixedHeight(24)
        self.namespace_dropdown.setMinimumWidth(40)
        self.namespace_dropdown.setMaximumWidth(120)
        #self.namespace_dropdown.setFixedSize(100, 20)
        
        self.namespace_dropdown.setStyleSheet(f'''QComboBox{{background-color: {UT.rgba_value('#222222', 1,.9)}; color: #dddddd;border: 1px solid #2f2f2f; padding: 0px 0px 0px 5px;}}
                                    QComboBox:hover {{background-color: {UT.rgba_value('#222222', .8,1)};}}
                                    QComboBox::drop-down {{border: 0px;}}
                                    QComboBox::down-arrow {{background-color: transparent;}} 
                                    QToolTip {{background-color: #222222; color: white; border:0px;}} ''')
        self.namespace_dropdown.setToolTip('Select Namespace')

        #------------------------------------------------------------------------------------------------------------------------------------------------------
        
        #-Edit Frame
        efw = 180 #edit fixed width
        self.edit_frame = QtWidgets.QFrame()
        self.edit_frame.setStyleSheet('QFrame {background-color: rgba(40, 40, 40, .8); border: 0px solid #333333;}')
        self.edit_frame.setFixedWidth(efw - 10)
        
        # Create a scroll area
        self.edit_scroll_area = QtWidgets.QScrollArea()
        self.edit_scroll_area.setWidgetResizable(True)
        self.edit_scroll_area.setFixedWidth(efw)  # Set a fixed width for the scroll area
        self.edit_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.edit_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        #self.edit_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.edit_scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 8px;
                margin: 0px 0px 0px 0px;
                
            }
            QScrollBar::handle:vertical {
                background: rgba(30, 30, 30, 0.7);
                min-height: 20px;
                width: 6px;
                border-radius: 0px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
                                            
        """)
        
        self.edit_scroll_area.setWidget(self.edit_frame)


        #-EDIT LAYOUT ------------------->
        self.edit_layout = QtWidgets.QVBoxLayout(self.edit_frame)
        self.edit_layout.setAlignment(QtCore.Qt.AlignTop|QtCore.Qt.AlignCenter)
        els = 6 #edit layout spacing
        self.edit_layout.setContentsMargins(els, els, els, els)
        self.edit_layout.setSpacing(els)
        #-Edit Label
        self.edit_label = QtWidgets.QLabel("Picker Editor")
        self.edit_label.setAlignment(QtCore.Qt.AlignCenter)        
        self.edit_label.setStyleSheet('QLabel {color: #dddddd; background-color: transparent; font-size: 12px;}')
        self.edit_layout.addWidget(self.edit_label)
        
        
        #-Buttons EF (HIDDEN)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.add_button_EF = EF.ExpandableFrame(title='Add Button', color='#222222', border=1, border_color='#333333') 
        self.add_button_EF.toggle_expand()
        self.add_button_EF.setFixedWidth(efw-20)
        self.add_picker_button = CB.CustomButton(text='Add Button', height=24, radius=4,color='#5285a6')

        p_button_grid1 = QtWidgets.QGridLayout()

        self.add_p_button_label_label = QtWidgets.QLabel("Label")
        self.add_p_button_label_qline = CLE.FocusLosingLineEdit('Button')

        p_button_grid1.addWidget(self.add_p_button_label_label, 1, 0)
        p_button_grid1.addWidget(self.add_p_button_label_qline, 1, 1)
        
        self.add_button_EF.addWidget(self.add_picker_button)
        self.add_button_EF.addLayout(p_button_grid1)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #-Buttons Edit EF
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.button_selection_count = 0
        self.edit_button_EF = EF.ExpandableFrame(title=f'Button <span style="color: #494949; font-size: 11px;">({self.button_selection_count})</span>', color='#222222', border=1, border_color='#333333') 
        self.edit_button_EF.toggle_expand()
        self.edit_button_EF.setFixedWidth(efw-20)
        self.edit_value_layout = QtWidgets.QVBoxLayout()
        
        #BEW.create_button_edit_widgets(self.edit_value_layout)
        self.add_picker_button = CB.CustomButton(text='Add Button', height=24, radius=4,color='#5285a6',tooltip='Add Button to the current tab')
        self.edit_button_EF.addWidget(self.add_picker_button)
        self.edit_button_EF.addLayout(self.edit_value_layout)


        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #-Canvas EF
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.edit_canvas_EF = EF.ExpandableFrame(title='Canvas', color='#222222', border=1, border_color='#333333') 
        self.edit_canvas_EF.toggle_expand()
        self.edit_canvas_EF.setFixedWidth(efw-20)
        self.add_image = CB.CustomButton(text='Add Image', height=24, radius=4,color='#5285a6',tooltip='Add Image to the current tab')
        self.remove_image = CB.CustomButton(text='Remove Image', height=24, radius=4,color='#5a5a5a',tooltip='Remove Image from the current tab')

        self.image_scale_layout = QtWidgets.QHBoxLayout()
        self.image_scale_factor_label = QtWidgets.QLabel("Image Scale:")
        self.image_scale_factor = CLE.IntegerLineEdit(min_value=.01, max_value=400, increment=.1, width=None, height=18)
        self.image_scale_factor.setText('1.0')
        self.image_scale_layout.addWidget(self.image_scale_factor_label)
        self.image_scale_layout.addWidget(self.image_scale_factor)
        
        self.toggle_axes = CB.CustomRadioButton('Toggle Axes', height=None,color='#5285a6',fill=False)
        self.toggle_axes.setChecked(True)

        self.toggle_dots = CB.CustomRadioButton('Toggle Dots', height=None,color='#5285a6',fill=False)
        self.toggle_dots.setChecked(True)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #-Opcity Slider
        self.bg_opacity_frame = QtWidgets.QFrame()
        self.bg_opacity_frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.bg_opacity_frame.setFixedHeight(24)
        self.bg_opacity_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray; padding: 0px; margin: 0px; border-radius: 12px; background-color: rgba(35, 35, 35, .8);}}''')
        self.bg_opacity_frame_col = QtWidgets.QHBoxLayout(self.bg_opacity_frame)
        set_margin_space(self.bg_opacity_frame_col, 4, 2)

        self.image_opacity_slider = CS.CustomSlider(min_value=0, max_value=100, float_precision=0, height=16, radius=8,prefix='Image Opacity: ',suffix='%', color='#444444')
        self.image_opacity_slider.setValue(100)

        self.bg_opacity_frame_col.addWidget(self.image_opacity_slider)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #-Background Value Slider
        self.bg_value_frame = QtWidgets.QFrame()
        self.bg_value_frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.bg_value_frame.setFixedHeight(24)
        self.bg_value_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray; padding: 0px; margin: 0px; border-radius: 12px; background-color: rgba(35, 35, 35, .8);}}''')
        self.bg_value_frame_col = QtWidgets.QHBoxLayout(self.bg_value_frame)
        set_margin_space(self.bg_value_frame_col, 4, 2)

        self.bg_value_slider = CS.CustomSlider(min_value=0, max_value=100, float_precision=0, height=16, radius=8,prefix='BG Value: ',suffix='%', color='#444444')
        self.bg_value_slider.setValue(50)

        self.bg_value_frame_col.addWidget(self.bg_value_slider)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.edit_canvas_EF.addWidget(self.add_image)
        self.edit_canvas_EF.addWidget(self.remove_image)
        self.edit_canvas_EF.content_layout.addSpacing(10)
        self.edit_canvas_EF.addWidget(self.bg_opacity_frame)
        self.edit_canvas_EF.addWidget(self.bg_value_frame)
        self.edit_canvas_EF.addLayout(self.image_scale_layout)
        self.edit_canvas_EF.addWidget(self.toggle_axes)
        self.edit_canvas_EF.addWidget(self.toggle_dots)
        
        self.toggle_edit_mode_button = CB.CustomButton(text='Exit Edit Mode', height=24, width=efw, radius=4,color='#5e7b19', tooltip='Apply changes')
        self.toggle_edit_mode_button.clicked.connect(self.toggle_edit_mode)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #self.edit_layout.addWidget(self.add_button_EF) 
        self.edit_layout.addWidget(self.edit_button_EF)
        self.edit_layout.addWidget(self.edit_canvas_EF)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        
        # Version Label
        self.versionLabel = QtWidgets.QLabel(f'Anim Picker ({anim_picker_version})')
        self.versionLabel.setStyleSheet(f'''QLabel {{ color:rgba(160, 160, 160, .5); background-color: transparent}},''')  
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #Tool Drawer
        self.tools_EF = EF.ExpandableFrame(title='<span style="color: #777777; font-size: 11px;"> Animation Tools</span>', color='#282828',alpha=.8, border=1, border_color='#333333',margin=2) 
        self.tools_EF.toggle_expand()
        self.tool_buttons = TF.animation_tool_layout()
        self.tools_EF.addLayout(self.tool_buttons.layout)

        # Resize Handle
        self.resize_handle = QtWidgets.QPushButton("◢")
        self.resize_handle.setFixedSize(18, 18)
        self.resize_handle.setStyleSheet('''
            QPushButton {background-color: rgba(30, 30, 30, 0.2); border-radius: 3px; border: none; color: rgba(160, 160, 160, 0.5);}
            QPushButton:hover {background-color: rgba(40, 40, 40, 0.3); }''')
        
    def em(self):
        print('Funtion not assigned')

    def info(self):
        # Opens link to Manual
        cmds.launch(web='https://munorr.com/tools/ft-anim-picker/')
        print(f'Floating Tools Anim Picker {anim_picker_version}')

    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode

        # Store current window geometry
        current_geometry = self.geometry()
        edit_panel_width = self.edit_scroll_area.width()

        # Update Edit mode UI Elements
        self.edit_scroll_area.setVisible(self.edit_mode)
        self.toggle_edit_mode_button.setVisible(self.edit_mode)

        # Adjust window width based on edit mode
        if self.edit_mode:
            # Add edit panel width
            new_width = current_geometry.width() + edit_panel_width
            self.setGeometry(
                current_geometry.x(),
                current_geometry.y(),
                new_width,
                current_geometry.height()
            )
        else:
            # Subtract edit panel width
            new_width = current_geometry.width() - edit_panel_width
            self.setGeometry(
                current_geometry.x(),
                current_geometry.y(),
                new_width,
                current_geometry.height()
            )

        # Update the canvas for all tabs
        for tab_name, tab_data in self.tab_system.tabs.items():
            canvas = tab_data['canvas']
            canvas.set_edit_mode(self.edit_mode)
            
            # Update cursor for all buttons
            for button in canvas.buttons:
                button.update_cursor()
                
        # Update the button state in the UI
        if hasattr(self, 'edit_button'):
            self.edit_button.setChecked(self.edit_mode)

        # Force update of the layout
        self.update()
        QtCore.QTimer.singleShot(0, self.update_buttons_for_current_tab)

    def setup_layout(self):
        # Add widgets to layouts
        self.area_01_col.addWidget(self.canvas_frame)

        self.canvas_frame_row.addLayout(self.picker_canvas_col1)

        self.picker_canvas_col1.addWidget(self.canvas_tab_frame_scroll_area)
        self.picker_canvas_col1.addWidget(self.namespace_dropdown)
        
        self.canvas_tab_frame_col.addWidget(self.addTabButton)

        self.area_01_col.addLayout(self.edit_row)

        self.edit_row.addWidget(self.edit_scroll_area)
        self.edit_scroll_area.setVisible(self.edit_mode)

        self.edit_row.addWidget(self.toggle_edit_mode_button)
        self.toggle_edit_mode_button.setVisible(self.edit_mode)

        # Add layouts to main layout
        self.top_col.addWidget(self.util_frame)

        self.tool_col.addWidget(self.tools_EF)

        self.main_frame_col.addLayout(self.top_col) 
        self.main_frame_col.addLayout(self.area_01_col)
        self.main_frame_col.addLayout(self.tool_col)
        self.main_frame_col.addLayout(self.bottom_col)

        self.main_layout.addWidget(self.main_frame)

    def setup_connections(self):
        self.close_button.clicked.connect(self.close)
        self.resize_handle.setCursor(QtCore.Qt.SizeFDiagCursor)
        self.resize_handle.installEventFilter(self)
        self.add_image.clicked.connect(self.select_image_for_current_tab)
        self.remove_image.clicked.connect(self.remove_image_from_current_tab)
        self.image_opacity_slider.valueChanged.connect(self.update_image_opacity)
        self.add_picker_button.clicked.connect(self.add_new_picker_button)
        self.toggle_axes.toggled.connect(self.toggle_axes_visibility)
        self.toggle_dots.toggled.connect(self.toggle_dots_visibility)
        if self.tab_system.current_tab:
            current_canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            current_canvas.clicked.connect(self.clear_line_edit_focus)
            current_canvas.button_selection_changed.connect(self.update_edit_widgets_delayed)
            #current_canvas.button_selection_changed.connect(self.update_edit_widgets) 
        self.namespace_dropdown.currentTextChanged.connect(self.on_namespace_changed)
        self.bg_value_slider.valueChanged.connect(self.update_background_value)

        self.toggle_axes.toggled.connect(self.toggle_axes_visibility)
        self.toggle_dots.toggled.connect(self.toggle_dots_visibility)
        #self.tools_EF.expandedSignal.connect(self.on_tools_frame_expanded)
        #self.tools_EF.collapsedSignal.connect(self.on_tools_frame_collapsed)
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [External Data Management]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def store_picker(self):
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Store Picker Data",
            "",
            "JSON Files (*.json)"
        )
        if file_path:
            try:
                from . import picker_io
                picker_io.store_picker_data(file_path)
                cmds.inViewMessage(amg=f"Picker data successfully saved to {file_path}", pos='midCenter', fade=True)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))
                
    def load_picker(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Load Picker Data",
            "",
            "JSON Files (*.json)"
        )
        if file_path:
            try:
                from . import picker_io
                picker_io.load_picker_data(file_path)
                # Refresh the UI to show the loaded data
                self.tab_system.setup_tabs()
                
                # Switch to the first tab if available
                if self.tab_system.tabs:
                    first_tab = next(iter(self.tab_system.tabs))
                    self.tab_system.switch_tab(first_tab)
                
                self.create_buttons()
                cmds.inViewMessage(amg=f"Picker data successfully Imported", pos='midCenter', fade=True)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))
                
    def open_mirror_preferences(self):
        """
        Opens the mirror preference window for configuring how objects should be mirrored.
        This window allows users to set custom mirror preferences for selected objects.
        """
        from . import mirror_preferences
        mirror_preferences.MirrorPreferencesWindow(parent=self).show()
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [Canvas Functions Link]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def toggle_axes_visibility(self, checked):
        if self.tab_system.current_tab:
            current_tab = self.tab_system.current_tab
            current_canvas = self.tab_system.tabs[current_tab]['canvas']
            current_canvas.set_show_axes(checked)
            
            # Update the database
            DM.PickerDataManager.update_axes_visibility(current_tab, checked)

    def toggle_dots_visibility(self, checked):
        if self.tab_system.current_tab:
            current_tab = self.tab_system.current_tab
            current_canvas = self.tab_system.tabs[current_tab]['canvas']
            current_canvas.set_show_dots(checked)
            
            # Update the database
            DM.PickerDataManager.update_dots_visibility(current_tab, checked)

    def setup_shortcuts(self):
        self.focus_shortcut = QShortcut(QtGui.QKeySequence("F"), self)
        self.focus_shortcut.activated.connect(self.focus_current_canvas)

    def focus_current_canvas(self):
        if self.tab_system.current_tab:
            current_tab = self.tab_system.current_tab
            current_canvas = self.tab_system.tabs[current_tab]['canvas']
            current_canvas.focus_canvas()
    
    def clear_line_edit_focus(self):
        if self.add_p_button_label_qline.hasFocus():
            self.add_p_button_label_qline.clearFocus()
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [Anim Tools]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def on_tools_frame_expanded(self):
        # Get initial geometry
        current_geometry = self.geometry()
        
        # Calculate the required height increase
        content_height = (self.tools_EF.content_widget.sizeHint().height() + 
                        self.tools_EF.main_layout.spacing() * 2)

        # Create animation for smooth expansion
        self.expand_animation = QPropertyAnimation(self, b"geometry")
        self.expand_animation.setDuration(150)  # Adjust duration as needed
        self.expand_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # Set start and end geometries
        start_geometry = current_geometry
        end_geometry = QtCore.QRect(
            current_geometry.x(),
            current_geometry.y(),
            current_geometry.width(),
            current_geometry.height() + content_height
        )
        
        self.expand_animation.setStartValue(start_geometry)
        self.expand_animation.setEndValue(end_geometry)
        
        # Connect animation finished signal
        self.expand_animation.finished.connect(self.update_buttons_for_current_tab)
        
        # Start animation
        self.expand_animation.start()

    def on_tools_frame_collapsed(self):
        # Get initial geometry
        current_geometry = self.geometry()
        
        # Calculate the required height decrease
        content_height = (self.tools_EF.content_widget.sizeHint().height() + 
                        self.tools_EF.main_layout.spacing() * 2)

        # Create animation for smooth collapse
        self.collapse_animation = QPropertyAnimation(self, b"geometry")
        self.collapse_animation.setDuration(150)  # Adjust duration as needed
        self.collapse_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # Set start and end geometries
        start_geometry = current_geometry
        end_geometry = QtCore.QRect(
            current_geometry.x(),
            current_geometry.y(),
            current_geometry.width(),
            current_geometry.height() - content_height
        )
        
        self.collapse_animation.setStartValue(start_geometry)
        self.collapse_animation.setEndValue(end_geometry)
        
        # Connect animation finished signal
        self.collapse_animation.finished.connect(self.update_buttons_for_current_tab)
        
        # Start animation
        self.collapse_animation.start()    
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [Event Handlers]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Only update buttons if this is not from our manual resize operation
        # This prevents double updates during manual resizing
        if not self.resize_state['active']:
            self.update_buttons_for_current_tab()

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            # Get the widget under the cursor
            child_widget = self.childAt(event.pos())
            
            # Check if we're clicking on any special widgets
            current_widget = child_widget
            while current_widget:
                if isinstance(current_widget, (PC.PickerCanvas, PB.PickerButton, 
                                            TS.TabButton, CB.CustomRadioButton)):
                    event.accept()
                    return
                current_widget = current_widget.parent()
            
            # If we get here, we're not clicking on any special widgets
            # Handle resize and drag operations
            self.oldPos = event.globalPos()
            resize_edge = self.get_resize_edge(event.pos())
            
            if resize_edge:
                # Initialize resize state
                self.begin_resize(resize_edge, event.globalPos())
            else:
                # Not resizing, just moving the window
                self.resize_state['active'] = False
                    
            UT.maya_main_window().activateWindow()

    def mouseMoveEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton:
            # If we're already in resize mode, skip widget checks
            if not self.resize_state['active']:
                # First check if we're interacting with special widgets
                child_widget = self.childAt(event.pos())
                current_widget = child_widget
                while current_widget:
                    if isinstance(current_widget, (PC.PickerCanvas, PB.PickerButton, 
                                                TS.TabButton, CB.CustomRadioButton)):
                        event.accept()
                        return
                    current_widget = current_widget.parent()

            # Handle resize/move operations
            if self.resize_state['active'] and self.resize_state['edge']:
                # Process resize with throttling
                self.process_resize(event.globalPos())
            elif not self.resize_state['active']:
                # Temporarily disable updates during window movement to reduce flickering
                self.setUpdatesEnabled(False)
                
                # Just moving the window
                delta = event.globalPos() - self.oldPos
                self.move(self.x() + delta.x(), self.y() + delta.y())
                self.oldPos = event.globalPos()
                
                # Re-enable updates
                self.setUpdatesEnabled(True)
        
        # Only check cursor state if not dragging the window
        if not (event.buttons() == QtCore.Qt.LeftButton and not self.resize_state['active']):
            pos = event.pos()
            
            # Check if the mouse is over the canvas frame
            canvas_frame_geo = self.canvas_frame.geometry()
            if canvas_frame_geo.contains(pos):
                # Reset cursor when over canvas frame
                self.reset_cursor()
            else:
                # Update cursor based on position relative to edges
                if self.is_in_resize_range(pos):
                    self.update_cursor(pos)
                else:
                    # Reset cursor when not over resize edges
                    self.reset_cursor()

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if self.resize_state['active']:
                # End resize operation
                self.end_resize()
                
                # Check cursor position after releasing to ensure proper cursor state
                pos = self.mapFromGlobal(QtGui.QCursor.pos())
                if self.is_in_resize_range(pos):
                    self.update_cursor(pos)
                else:
                    self.unsetCursor()

    def finalize_resize(self):
        # This method is called when resize timer times out or when mouse is released
        # Update button positions and layout only once at the end of resize
        if self.tab_system.current_tab:
            # Clear any cached data
            self.resize_state['cached_canvas'] = None
            self.resize_state['cached_buttons'] = None
            
            # Do a full update of all buttons
            self.update_buttons_for_current_tab()
        
    def eventFilter(self, obj, event):
        if obj == self.resize_handle:
            if event.type() == QtCore.QEvent.MouseButtonPress:
                if event.button() == QtCore.Qt.LeftButton:
                    # Use the unified resize handling system
                    self.begin_resize('bottom_right', event.globalPos())
                    return True
                    
            elif event.type() == QtCore.QEvent.MouseMove and self.resize_state['active']:
                # Use the unified resize processing system
                self.process_resize(event.globalPos())
                return True
                
            elif event.type() == QtCore.QEvent.MouseButtonRelease:
                if self.resize_state['active']:
                    # Use the unified resize end system
                    self.end_resize()
                    
                    # Check cursor position after releasing
                    pos = self.mapFromGlobal(QtGui.QCursor.pos())
                    if self.is_in_resize_range(pos):
                        self.update_cursor(pos)
                    else:
                        self.unsetCursor()
                return True
        
        # Handle mouse events for all frames including main_frame and util_frame
        if obj in [self.main_frame, self.util_frame] or isinstance(obj, QtWidgets.QFrame):
            if event.type() == QtCore.QEvent.MouseMove:
                # Convert local coordinates to window coordinates
                local_pos = event.pos()
                global_pos = obj.mapToGlobal(local_pos)
                window_pos = self.mapFromGlobal(global_pos)
                
                # Check if the mouse is over the canvas frame
                canvas_frame_geo = self.canvas_frame.geometry()
                if canvas_frame_geo.contains(window_pos):
                    # Reset cursor when over canvas frame
                    self.reset_cursor()
                else:
                    if self.is_in_resize_range(window_pos):
                        self.update_cursor(window_pos)
                    else:
                        # Reset cursor when not over resize edges
                        self.reset_cursor()
                        
                # Don't consume the event so it can propagate
                return False
                
            elif event.type() == QtCore.QEvent.Enter:
                # Handle enter events for child frames
                local_pos = event.pos()
                global_pos = obj.mapToGlobal(local_pos)
                window_pos = self.mapFromGlobal(global_pos)
                
                if self.is_in_resize_range(window_pos):
                    self.update_cursor(window_pos)
                elif not self.resize_state['active']:
                    self.unsetCursor()
                return False
                
            elif event.type() == QtCore.QEvent.MouseButtonDblClick and obj == self.main_frame:
                # Reset window to original size when double-clicked
                #self.setGeometry(1150, 280, 350, 450)
                self.resize(350, 450)
                self.update_buttons_for_current_tab()
                UT.maya_main_window().activateWindow()
                return True
                
            elif event.type() == QtCore.QEvent.Leave:
                # Only unset cursor if we're not resizing
                if not self.resize_state['active']:
                    self.unsetCursor()
                return False
                    
        return super().eventFilter(obj, event)

    def enterEvent(self, event):
        # Always check cursor on enter
        pos = event.pos()
        # Check if the mouse is over the canvas frame
        canvas_frame_geo = self.canvas_frame.geometry()
        
        # Force cursor update regardless of entry point
        if not canvas_frame_geo.contains(pos):
            if self.is_in_resize_range(pos):
                self.update_cursor(pos)
            else:
                self.reset_cursor()
        else:
            self.reset_cursor()
            
        # Ensure cursor updates properly when entering from any edge
        QtWidgets.QApplication.processEvents()

    def leaveEvent(self, event):
        # When leaving the window, we should reset cursor only if not resizing
        self.reset_cursor()

    def is_in_resize_range(self, pos):
        # Make sure pos is within the window bounds first
        if not (0 <= pos.x() <= self.width() and 0 <= pos.y() <= self.height()):
            return False
            
        width = self.width()
        height = self.height()
        edge_size = self.resize_range
        
        # Make the detection more precise (less forgiving)
        return (pos.x() <= edge_size or 
                pos.x() >= width - edge_size or 
                pos.y() <= edge_size or 
                pos.y() >= height - edge_size)
    
    def get_resize_edge(self, pos):
        width = self.width()
        height = self.height()
        edge_size = self.resize_range
        
        # Use the same precise edge detection as is_in_resize_range
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
        
    def reset_cursor(self):
        """Reset cursor to default if not in resize mode"""
        if not self.resize_state['active']:
            self.unsetCursor()

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

    # New unified resize methods
    def begin_resize(self, edge, global_pos):
        """Start a resize operation with the given edge and position"""
        self.resize_state.update({
            'active': True,
            'edge': edge,
            'start_pos': global_pos,
            'initial_size': self.size(),
            'initial_pos': self.pos(),
            'last_update_time': QtCore.QTime.currentTime().msecsSinceStartOfDay(),
            'last_buttons_update_time': QtCore.QTime.currentTime().msecsSinceStartOfDay()
        })
        
        # Cache the current tab and canvas if available
        if self.tab_system.current_tab:
            self.resize_state['cached_canvas'] = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        
        # Capture mouse to prevent losing focus during resize
        self.grabMouse()
        
    def process_resize(self, global_pos):
        """Process resize with the current mouse position"""
        if not self.resize_state['active']:
            return
            
        # Get current time for throttling
        current_time = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        
        # Disable updates during resize for better performance
        self.setUpdatesEnabled(False)
        
        # Calculate delta from start position
        delta = global_pos - self.resize_state['start_pos']
        
        # Calculate new dimensions
        new_width = self.resize_state['initial_size'].width()
        new_height = self.resize_state['initial_size'].height()
        new_x = self.resize_state['initial_pos'].x()
        new_y = self.resize_state['initial_pos'].y()
        
        # Calculate all dimensions based on the resize edge
        edge = self.resize_state['edge']
        if 'left' in str(edge):
            new_width = max(self.minimumWidth(), self.resize_state['initial_size'].width() - delta.x())
            if new_width >= self.minimumWidth():
                new_x = self.resize_state['initial_pos'].x() + delta.x()
                
        if 'right' in str(edge):
            new_width = max(self.minimumWidth(), self.resize_state['initial_size'].width() + delta.x())
            
        if 'top' in str(edge):
            new_height = max(self.minimumHeight(), self.resize_state['initial_size'].height() - delta.y())
            if new_height >= self.minimumHeight():
                new_y = self.resize_state['initial_pos'].y() + delta.y()
            
        if 'bottom' in str(edge):
            new_height = max(self.minimumHeight(), self.resize_state['initial_size'].height() + delta.y())
        
        # Apply geometry changes
        new_geometry = QtCore.QRect(new_x, new_y, new_width, new_height)
        self.setGeometry(new_geometry)
        
        # Check if we should update buttons (less frequently)
        if (current_time - self.resize_state['last_buttons_update_time'] >= 
                self.resize_state['buttons_update_interval_ms']):
            # Update buttons with throttling
            if self.resize_state['cached_canvas']:
                self.resize_state['cached_canvas'].update_button_positions()
            self.resize_state['last_buttons_update_time'] = current_time
        
        # Restart the timer for final update
        self.resize_timer.start()
        
        # Re-enable updates
        self.setUpdatesEnabled(True)
        
        # Update last update time
        self.resize_state['last_update_time'] = current_time
    
    def end_resize(self):
        """End the current resize operation"""
        # Store current geometry before deactivating resize state
        current_geometry = self.geometry()
        
        # Deactivate resize state
        self.resize_state['active'] = False
        self.resize_state['edge'] = None
        self.releaseMouse()
        
        # Immediately finalize the resize
        self.finalize_resize()
        
        # Cancel any pending timer to avoid duplicate updates
        self.resize_timer.stop()
        
        # Update oldPos for next delta calculation
        self.oldPos = QtGui.QCursor.pos()
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [Name Space]    
    #----------------------------------------------------------------------------------------------------------------------------------------
    def get_namespaces(self):
        namespaces = cmds.namespaceInfo(listOnlyNamespaces=True, recurse=True)
        namespaces = [ns for ns in namespaces if ns not in ['UI', 'shared'] and ':' not in ns]
        namespaces.sort()
        return ['None'] + namespaces

    def update_namespace_dropdown(self):
        # Add a check to ensure tab_system exists
        if not hasattr(self, 'tab_system') or not self.tab_system:
            return
            
        if not self.tab_system.current_tab:
            return
            
        current_tab = self.tab_system.current_tab
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        saved_namespace = tab_data.get('namespace', 'None')
        
        # Get available namespaces
        namespaces = self.get_namespaces()
        
        # Block signals to prevent triggering the callback during update
        self.namespace_dropdown.blockSignals(True)
        self.namespace_dropdown.clear()
        self.namespace_dropdown.addItems(namespaces)
        
        # Set to saved namespace if it exists, otherwise default to 'None'
        if saved_namespace in namespaces:
            self.namespace_dropdown.setCurrentText(saved_namespace)
        else:
            self.namespace_dropdown.setCurrentText('None')
            # Update the database with the new 'None' namespace
            DM.PickerDataManager.update_tab_namespace(current_tab, 'None')
        
        self.namespace_dropdown.blockSignals(False)
    
    def on_namespace_changed(self, namespace):
        if self.tab_system.current_tab:
            DM.PickerDataManager.update_tab_namespace(self.tab_system.current_tab, namespace)
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [Picker Button] 
    #----------------------------------------------------------------------------------------------------------------------------------------
    def add_new_picker_button(self):
        if not self.tab_system.current_tab:
            return

        button_label = self.add_p_button_label_qline.text()

        if not button_label:
            button_label = ''
            '''QtWidgets.QMessageBox.warning(self, "Error", "Button label is required.")
            return'''

        current_tab = self.tab_system.current_tab
        canvas = self.tab_system.tabs[current_tab]['canvas']

        unique_id = self.generate_unique_id(current_tab)
        center_pos = canvas.get_center_position()

        new_button = PB.PickerButton(button_label, canvas, unique_id=unique_id)
        new_button.scene_position = center_pos
        
        canvas.add_button(new_button)
        canvas.update_button_positions()
        canvas.update()

        button_data = {
            "id": unique_id,
            "label": button_label,
            "color": new_button.color,
            "opacity": new_button.opacity,
            "position": (new_button.scene_position.x(), new_button.scene_position.y())
        }
        
        # Update the PickerDataManager
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        tab_data['buttons'].append(button_data)
        DM.PickerDataManager.update_tab_data(current_tab, tab_data)

        # Force a refresh of the canvas
        canvas.update()

    def generate_unique_id(self, tab_name):
        if tab_name not in self.available_ids:
            self.available_ids[tab_name] = set()

        # Get all existing IDs for this tab
        existing_ids = set()
        tab_data = DM.PickerDataManager.get_tab_data(tab_name)
        for button in tab_data.get('buttons', []):
            existing_ids.add(button['id'])

        # Find the next available ID
        i = 1
        while True:
            new_id = f"{tab_name}_button_{i:03d}"
            if new_id not in existing_ids and new_id not in self.available_ids[tab_name]:
                return new_id
            i += 1

    def create_buttons(self):
        if not self.tab_system.current_tab:
            return

        current_tab = self.tab_system.current_tab
        self.initialize_tab_data(current_tab)
        canvas = self.tab_system.tabs[current_tab]['canvas']

        # Clear existing buttons
        for button in canvas.buttons[:]:
            button.setParent(None)
            button.deleteLater()
        canvas.buttons.clear()

        # Get button data from PickerDataManager
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        for button_data in tab_data.get('buttons', []):
            # Create button with basic properties
            button = PB.PickerButton(
                button_data["label"],
                canvas,
                unique_id=button_data["id"],
                color=button_data.get("color", "#444444"),
                opacity=button_data.get("opacity", 1.0),
                width=button_data.get("width", 80),
                height=button_data.get("height", 30)
            )
            
            # Set basic properties
            button.radius = button_data.get("radius", [3, 3, 3, 3])
            button.assigned_objects = button_data.get("assigned_objects", [])
            button.mode = button_data.get("mode", "select")
            
            # Handle script data with language type
            script_data = button_data.get("script_data", {})
            if isinstance(script_data, dict):
                button.script_data = script_data
            else:
                # Convert legacy script data to new format
                button.script_data = {
                    'code': str(script_data),
                    'type': 'python'  # Default to python for legacy data
                }
                
            # Load pose data if available
            button.pose_data = button_data.get("pose_data", {})
            
            # Load thumbnail path if available
            if button_data.get("thumbnail_path"):
                button.thumbnail_path = button_data["thumbnail_path"]
                # Load the thumbnail image if the file exists
                if os.path.exists(button.thumbnail_path):
                    button.thumbnail_pixmap = QtGui.QPixmap(button.thumbnail_path)
                else:
                    button.thumbnail_path = ''  # Reset if file doesn't exist
                    button.thumbnail_pixmap = None
            
            button.scene_position = QtCore.QPointF(*button_data["position"])
            button.update_tooltip()
            canvas.add_button(button)

        canvas.update_button_positions()
        canvas.update()

    def on_button_changed(self, button):
        self.update_button_data(button)

    def update_button_data(self, button, deleted=False):
        if self.tab_system.current_tab:
            current_tab = self.tab_system.current_tab
            self.initialize_tab_data(current_tab)
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            if deleted:
                tab_data['buttons'] = [b for b in tab_data['buttons'] if b['id'] != button.unique_id]
                if current_tab not in self.available_ids:
                    self.available_ids[current_tab] = set()
                self.available_ids[current_tab].add(button.unique_id)
            else:
                button_data = {
                    "id": button.unique_id,
                    "label": button.label,
                    "color": button.color,
                    "opacity": button.opacity,
                    "position": (button.scene_position.x(), button.scene_position.y()),
                    "width": button.width,
                    "height": button.height,
                    "radius": button.radius,
                    "assigned_objects": button.assigned_objects,
                    "mode": button.mode,  # Add mode
                    "script_data": button.script_data,  # Add script data
                    "pose_data": button.pose_data,  # Add pose data
                    "thumbnail_path": button.thumbnail_path if hasattr(button, 'thumbnail_path') else ''  # Add thumbnail path
                }
                # Update existing button or add new one
                updated = False
                for i, existing_button in enumerate(tab_data['buttons']):
                    if existing_button['id'] == button.unique_id:
                        tab_data['buttons'][i] = button_data
                        updated = True
                        break
                if not updated:
                    tab_data['buttons'].append(button_data)
            DM.PickerDataManager.update_tab_data(current_tab, tab_data)
            self.update_buttons_for_current_tab()

    def update_buttons_for_current_tab(self, force_update=False):
        if self.tab_system.current_tab:
            current_tab = self.tab_system.current_tab
            canvas = self.tab_system.tabs[current_tab]['canvas']
            
            # Only update if we're not in an active resize operation or if forced
            if not self.resize_state['active'] or force_update:
                canvas.update_button_positions()

                # Update button positions in PickerDataManager
                button_positions = {
                    button.unique_id: (button.scene_position.x(), button.scene_position.y())
                    for button in canvas.buttons
                }
                DM.PickerDataManager.update_button_positions(current_tab, button_positions)
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [Tab Functions]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def initialize_tab_data(self, tab_name):
        if tab_name not in self.tab_system.tabs:
            self.tab_system.tabs[tab_name] = {
                'canvas': PC.PickerCanvas(self),
                'buttons': [],
                'image_path': None,
                'image_opacity': 1.0,
                'background_value': 18 # Default to 18% 
            }
        elif 'buttons' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['buttons'] = []
        elif 'background_value' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['background_value'] = 20  # Add if missing

    def setup_tab_system(self):
        self.tab_system = TS.TabSystem(self.canvas_tab_frame_col, self.addTabButton)
        self.tab_system.tab_switched.connect(self.on_tab_switched)
        self.tab_system.tab_renamed.connect(self.on_tab_renamed)
        self.tab_system.tab_deleted.connect(self.on_tab_deleted)
        self.tab_system.tab_reordered.connect(self.on_tab_reordered)
        
        self.tab_system.setup_tabs()
        
        if not self.tab_system.tabs:
            self.tab_system.add_tab("Tab 1")
            self.initialize_tab_data("Tab 1")
            DM.PickerDataManager.add_tab("Tab 1")
        
        self.create_buttons()

    def on_tab_reordered(self):
        # Update the UI if needed after tab reordering
        if self.tab_system.current_tab:
            self.update_canvas_for_tab(self.tab_system.current_tab)
        else:
            self.clear_canvas()

    def on_tab_switched(self, tab_name):
        self.update_canvas_for_tab(tab_name)
        current_opacity = self.tab_system.tabs[tab_name]['image_opacity']
        self.image_opacity_slider.setValue(int(current_opacity * 100))
        
        # Get current canvas and update signal connections
        current_canvas = self.tab_system.tabs[tab_name]['canvas']
        
        # Disconnect any existing connections to avoid duplicates
        try:
            current_canvas.button_selection_changed.disconnect()
            current_canvas.clicked.disconnect()
        except:
            pass
        
        # Connect with the delayed update method
        current_canvas.button_selection_changed.connect(self.update_edit_widgets_delayed)
        current_canvas.clicked.connect(self.clear_line_edit_focus)
        
        has_image = self.tab_system.tabs[tab_name]['image_path'] is not None
        self.remove_image.setEnabled(has_image)
        
        # Update namespace dropdown for the new tab
        self.update_namespace_dropdown()
        
        self.create_buttons()
        current_canvas.update()
        UT.maya_main_window().activateWindow()

    def on_tab_renamed(self, old_name, new_name):
        # Update the tab data in our local structure
        if old_name in self.tab_system.tabs:
            self.tab_system.tabs[new_name] = self.tab_system.tabs.pop(old_name)
        
        # Update the current tab if it was the renamed one
        if self.tab_system.current_tab == old_name:
            self.tab_system.current_tab = new_name
        
        # Update the UI
        self.update_canvas_for_tab(new_name)
        self.create_buttons()
        
        # Refresh the canvas
        current_canvas = self.tab_system.tabs[new_name]['canvas']
        current_canvas.update()

        # Force a refresh of the tab system
        self.tab_system.update_tab_buttons()

    def on_tab_deleted(self, deleted_tab_name):
        # Remove the tab data from our local structure
        if deleted_tab_name in self.tab_system.tabs:
            del self.tab_system.tabs[deleted_tab_name]
        
        # If the deleted tab was the current one, switch to another tab
        if self.tab_system.current_tab == deleted_tab_name:
            if self.tab_system.tabs:
                new_current_tab = next(iter(self.tab_system.tabs))
                self.tab_system.switch_tab(new_current_tab)
            else:
                # If no tabs left, clear the canvas
                self.clear_canvas()
        
        # Update the UI
        self.update_canvas_for_tab(self.tab_system.current_tab)
        self.create_buttons()

    def clear_canvas(self):
        # Clear the canvas when no tabs are left
        for i in reversed(range(self.canvas_frame_row.count())):
            widget = self.canvas_frame_row.itemAt(i).widget()
            if isinstance(widget, PC.PickerCanvas):
                self.canvas_frame_row.removeWidget(widget)
                widget.setParent(None)
        
        # Reset other UI elements as needed
        self.image_opacity_slider.setValue(100)
        self.remove_image.setEnabled(False)

    def update_canvas_for_tab(self, tab_name):
        if tab_name not in self.tab_system.tabs:
            # If the tab_name is invalid, switch to the first available tab
            if self.tab_system.tabs:
                tab_name = next(iter(self.tab_system.tabs))
            else:
                self.clear_canvas()
                return

        # Remove existing canvas
        for i in reversed(range(self.canvas_frame_row.count())):
            widget = self.canvas_frame_row.itemAt(i).widget()
            if isinstance(widget, PC.PickerCanvas):
                self.canvas_frame_row.removeWidget(widget)
                widget.setParent(None)

        # Add the canvas for the current tab
        current_canvas = self.tab_system.tabs[tab_name]['canvas']
        self.canvas_frame_row.addWidget(current_canvas)

        # Load tab data and update canvas settings
        tab_data = DM.PickerDataManager.get_tab_data(tab_name)
        
        # Set axes visibility
        show_axes = tab_data.get('show_axes', True)  # Default to True if not specified
        current_canvas.set_show_axes(show_axes)
        self.toggle_axes.setChecked(show_axes)

        # Set dots visibility
        show_dots = tab_data.get('show_dots', True)  # Default to True if not specified
        current_canvas.set_show_dots(show_dots)
        self.toggle_dots.setChecked(show_dots)

        # Get and set background value
        background_value = tab_data.get('background_value', 20)  # Default to 20%
        self.bg_value_slider.setValue(background_value)
        current_canvas.set_background_value(background_value)

        # Set other canvas properties (image, opacity, scale)
        image_path = tab_data.get('image_path')
        image_opacity = tab_data.get('image_opacity', 1.0)
        image_scale = tab_data.get('image_scale', 1.0)
        
        if image_path:
            current_canvas.set_background_image(image_path)
            current_canvas.set_image_scale(image_scale)
            self.remove_image.setEnabled(True)
            self.tab_system.tabs[tab_name]['image_path'] = image_path
            self.image_scale_factor.setText(str(image_scale))
        else:
            current_canvas.set_background_image(None)
            self.remove_image.setEnabled(False)
            self.tab_system.tabs[tab_name]['image_path'] = None

        current_canvas.set_image_opacity(image_opacity)
        self.tab_system.tabs[tab_name]['image_opacity'] = image_opacity
        self.tab_system.tabs[tab_name]['image_scale'] = image_scale
        self.image_opacity_slider.setValue(int(image_opacity * 100))

        current_canvas.update()
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [Canvas Image]  
    #----------------------------------------------------------------------------------------------------------------------------------------   
    def select_image_for_current_tab(self):
        if self.tab_system.current_tab:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            overlay_folder = os.path.join(current_dir, "picker_canvas_overlays")
            image_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select Image", overlay_folder, "Image Files (*.png *.jpg *.bmp)")
            
            if image_path:
                current_tab = self.tab_system.current_tab
                current_canvas = self.tab_system.tabs[current_tab]['canvas']
                current_canvas.set_background_image(image_path)
                self.remove_image.setEnabled(True)

                self.tab_system.tabs[current_tab]['image_path'] = image_path
                current_opacity = self.tab_system.tabs[current_tab]['image_opacity']
                current_scale = float(self.image_scale_factor.text())  # Get current scale
                
                DM.PickerDataManager.update_image_data(
                    current_tab, 
                    image_path, 
                    current_opacity,
                    current_scale
                )
                
                current_canvas.update()

    def remove_image_from_current_tab(self):
        if self.tab_system.current_tab:
            current_tab = self.tab_system.current_tab
            current_canvas = self.tab_system.tabs[current_tab]['canvas']
            
            # Update the canvas
            current_canvas.set_background_image(None)
            current_canvas.set_image_opacity(1.0)
            current_canvas.set_image_scale(1.0)  # Reset scale as well
            
            # Update UI elements
            self.remove_image.setEnabled(False)
            self.image_opacity_slider.setValue(100)
            self.image_scale_factor.setText('1.0')
            
            # Update local tab data
            self.tab_system.tabs[current_tab]['image_path'] = None
            self.tab_system.tabs[current_tab]['image_opacity'] = 1.0
            self.tab_system.tabs[current_tab]['image_scale'] = 1.0
            
            # Important: Update the database
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            tab_data['image_path'] = None
            tab_data['image_opacity'] = 1.0
            tab_data['image_scale'] = 1.0
            DM.PickerDataManager.update_tab_data(current_tab, tab_data)
            
            # Force canvas update
            current_canvas.update()

    def update_image_opacity(self, value):
        if self.tab_system.current_tab:
            opacity = value / 100.0
            scale = float(self.image_scale_factor.text())
            current_tab = self.tab_system.current_tab
            canvas = self.tab_system.tabs[current_tab]['canvas']
            canvas.set_image_opacity(opacity)
            self.tab_system.tabs[current_tab]['image_opacity'] = opacity
            self.tab_system.tabs[current_tab]['image_scale'] = scale

            # Get the current image path before updating
            current_image_path = self.tab_system.tabs[current_tab].get('image_path')

            # Update PickerToolData with both the image path and new opacity
            DM.PickerDataManager.update_image_data(current_tab, current_image_path, opacity, scale)

            #print(f"Updated image opacity for tab {current_tab}: opacity = {opacity}, image_path = {current_image_path}")
    
    def update_image_scale(self, value):
        if self.tab_system.current_tab:
            scale = float(value)
            current_tab = self.tab_system.current_tab
            canvas = self.tab_system.tabs[current_tab]['canvas']
            canvas.set_image_scale(scale)
            self.tab_system.tabs[current_tab]['image_scale'] = scale

            # Get current image path and opacity before updating
            current_image_path = self.tab_system.tabs[current_tab].get('image_path')
            current_opacity = self.tab_system.tabs[current_tab].get('image_opacity', 1.0)

            # Update PickerToolData with image path, opacity, and new scale
            DM.PickerDataManager.update_image_data(
                current_tab, 
                current_image_path, 
                current_opacity,
                scale
            )
    
    def update_background_value(self, value):
        """Update the canvas background value when the slider changes"""
        if self.tab_system.current_tab:
            current_tab = self.tab_system.current_tab
            canvas = self.tab_system.tabs[current_tab]['canvas']
            canvas.set_background_value(value)
            
            # Store the background value in the tab data
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            tab_data['background_value'] = value
            DM.PickerDataManager.update_tab_data(current_tab, tab_data)
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [Picker Button Edit Funtions]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def rename_selected_buttons(self, new_label):
        if self.tab_system.current_tab:
            canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            for button in canvas.get_selected_buttons():
                button.rename_button(new_label)
            self.update_buttons_for_current_tab()

    def change_opacity_for_selected_buttons(self, value):
        if self.tab_system.current_tab:
            canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            for button in canvas.get_selected_buttons():
                button.change_opacity(value)
            self.update_buttons_for_current_tab()

    def set_size_for_selected_buttons(self, width, height):
        if self.tab_system.current_tab:
            canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            for button in canvas.get_selected_buttons():
                button.set_size(width, height)
            canvas.update_button_positions()
            self.update_buttons_for_current_tab()

    def set_radius_for_selected_buttons(self, tl, tr, br, bl):
        if self.tab_system.current_tab:
            canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            for button in canvas.get_selected_buttons():
                button.set_radius(tl, tr, br, bl)
            canvas.update_button_positions()
            self.update_buttons_for_current_tab()

    def change_color_for_selected_buttons(self, color):
        if self.tab_system.current_tab:
            canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            for button in canvas.get_selected_buttons():
                button.change_color(color)
            self.update_buttons_for_current_tab()
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [Picker Button Edit Widgets]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def setup_edit_widgets(self):
        widgets = BEW.create_button_edit_widgets(self)
        
        # Add widgets to edit_value_layout
        self.edit_value_layout.addWidget(widgets['rename_widget'])
        self.edit_value_layout.addWidget(widgets['opacity_widget'])
        self.edit_value_layout.addWidget(widgets['transform_widget'])
        self.edit_value_layout.addWidget(widgets['radius_widget'])
        self.edit_value_layout.addWidget(widgets['color_widget'])
        self.edit_value_layout.addWidget(widgets['thumbnail_dir_widget'])

        # Introduce a flag to control updates
        self.is_updating_widgets = False

        # Connect signals
        widgets['rename_edit'].returnPressed.connect(self.on_rename_edit_return_pressed)
        widgets['rename_edit'].editingFinished.connect(self.on_rename_edit_return_pressed)
        widgets['opacity_slider'].valueChanged.connect(self.on_opacity_slider_value_changed)


        def update_transform():
            if not self.is_updating_widgets:
                self.set_size_for_selected_buttons(
                    widgets['transform_w_edit'].value(),
                    widgets['transform_h_edit'].value()
                )

        def scale_transfrom(value):
            if widgets['transform_prop'].isChecked():
                self.is_updating_widgets = True
                initial_width = widgets['transform_w_edit'].property('initial_value')
                initial_height = widgets['transform_h_edit'].property('initial_value')
                scale_factor = value / initial_width 
                #widgets['transform_h_edit'].setValue(float(int(initial_height * scale_factor)))
                widgets['transform_h_edit'].setValue(value)
                self.is_updating_widgets = False
            update_transform()

        widgets['transform_w_edit'].valueChanged.connect(scale_transfrom)
        widgets['transform_h_edit'].valueChanged.connect(update_transform)
        
        def update_radius():
            if not self.is_updating_widgets:
                self.set_radius_for_selected_buttons(
                    widgets['top_left_radius'].value(),
                    widgets['top_right_radius'].value(),
                    widgets['bottom_right_radius'].value(),
                    widgets['bottom_left_radius'].value()
                )

        def update_all_radii(value):
            if widgets['single_radius'].isChecked():
                self.is_updating_widgets = True
                widgets['top_right_radius'].setValue(value)
                widgets['bottom_right_radius'].setValue(value)
                widgets['bottom_left_radius'].setValue(value)
                self.is_updating_widgets = False
            update_radius()

        def toggle_single_radius(checked):
            dss = "background-color: #222222; color: #444444; border: 1px solid #444444; border-radius: 3px;"
            ass = "background-color: #333333; color: #dddddd; border: 1px solid #444444; border-radius: 3px;"
            if checked:
                value = widgets['top_left_radius'].value()
                widgets['top_left_radius'].setStyleSheet("background-color: #6c9809; color: #dddddd; border: 1px solid #444444; border-radius: 3px;")
                
                widgets['top_right_radius'].setEnabled(False)
                widgets['top_right_radius'].setStyleSheet(dss)
                widgets['bottom_right_radius'].setEnabled(False)
                widgets['bottom_right_radius'].setStyleSheet(dss)
                widgets['bottom_left_radius'].setEnabled(False)
                widgets['bottom_left_radius'].setStyleSheet(dss)
            else:
                widgets['top_left_radius'].setStyleSheet(ass)
                widgets['top_right_radius'].setEnabled(True)
                widgets['top_right_radius'].setStyleSheet(ass)
                widgets['bottom_right_radius'].setEnabled(True)
                widgets['bottom_right_radius'].setStyleSheet(ass)
                widgets['bottom_left_radius'].setEnabled(True)
                widgets['bottom_left_radius'].setStyleSheet(ass)
            update_radius()

        widgets['top_left_radius'].valueChanged.connect(update_all_radii)
        widgets['top_right_radius'].valueChanged.connect(update_radius)
        widgets['bottom_right_radius'].valueChanged.connect(update_radius)
        widgets['bottom_left_radius'].valueChanged.connect(update_radius)
        widgets['single_radius'].toggled.connect(toggle_single_radius)

        for i, color_button in enumerate(widgets['color_buttons']):
            color = color_button.palette().button().color().name()
            color_button.clicked.connect(partial(self.on_color_button_clicked, color))

        # Store widgets for later use
        self.edit_widgets = widgets

    def on_rename_edit_return_pressed(self):
        if not self.is_updating_widgets:
            self.rename_selected_buttons(self.edit_widgets['rename_edit'].text())

    def on_opacity_slider_value_changed(self, value):
        if not self.is_updating_widgets:
            self.change_opacity_for_selected_buttons(value)

    def on_transform_edit_value_changed(self):
        if not self.is_updating_widgets:
            self.set_size_for_selected_buttons(
                self.edit_widgets['transform_w_edit'].value(),
                self.edit_widgets['transform_h_edit'].value()
            )
    
    def on_color_button_clicked(self, color):
        if not self.is_updating_widgets:
            self.change_color_for_selected_buttons(color)

    def update_edit_widgets_delayed(self):
        # Only update widgets if we're in edit mode
        if self.edit_mode:
            if hasattr(self, '_update_timer'):
                self._update_timer.stop()
            else:
                self._update_timer = QTimer()
                self._update_timer.setSingleShot(True)
                self._update_timer.timeout.connect(self.update_edit_widgets)
            self._update_timer.start(100)  # 100ms delay

    def update_edit_widgets(self):
        if not self.edit_mode or not self.tab_system.current_tab:
            return

        canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        selected_buttons = canvas.get_selected_buttons()
        self.button_selection_count = len(selected_buttons)
        self.edit_button_EF.title_label.setText(f'Button <span style="color: #494949; font-size: 11px;">({self.button_selection_count})</span>')

        widgets = self.edit_widgets

        if not selected_buttons:
            widgets['rename_edit'].setText('')
            widgets['transform_w_edit'].setValue(0)
            widgets['transform_h_edit'].setValue(0)
            widgets['top_left_radius'].setValue(0)
            widgets['top_right_radius'].setValue(0)
            widgets['bottom_right_radius'].setValue(0)
            widgets['bottom_left_radius'].setValue(0)
            widgets['transform_prop'].setChecked(False)
            widgets['single_radius'].setChecked(False)
            color = '#222222'
            self.edit_button_EF.content_widget.setStyleSheet(f'''
                                          QWidget {{border:0px solid #eeeeee;background-color:{UT.rgba_value(color,1.2,1)};}}
                                          QLabel {{border:None;background-color:transparent;}}
                                          QLineEdit {{border:1px solid #333333;background-color:#222222; margin: 0px; padding: 3px;}}''')
            
            #widgets['rename_edit'].setStyleSheet('border: 0px solid #444444;')
            # Keep thumbnail directory button active even when no button is selected
            widgets['thumbnail_dir_button'].setEnabled(True)
            widgets['thumbnail_dir_widget'].setEnabled(True)
            
            # Disable other widgets
            for widget_name, widget in widgets.items():
                if widget_name not in ['thumbnail_dir_button', 'thumbnail_dir_widget']:
                    if isinstance(widget, (QtWidgets.QWidget, QtWidgets.QLayout)):
                        widget.setEnabled(False)
            return
        else:
            color = '#222222'
            self.edit_button_EF.content_widget.setStyleSheet(f'''
                                          QWidget {{border:1px solid #5285a6;background-color:{UT.rgba_value(color,1.2,1)};}}
                                          QLabel {{border:None;background-color:transparent;}}
                                          QLineEdit {{border:1px solid #333333;background-color:#222222; margin: 0px; padding: 3px;}}''')
            
            widgets['rename_widget'].setStyleSheet('border: 0px solid #444444;')
            widgets['opacity_widget'].setStyleSheet('border: 0px solid #444444;')
            widgets['transform_widget'].setStyleSheet('border: 0px solid #444444;')
            widgets['radius_widget'].setStyleSheet('border: 0px solid #444444;')
            widgets['color_widget'].setStyleSheet('border: 0px solid #444444; background-color: #222222;')

        for widget in widgets.values():
            if isinstance(widget, (QtWidgets.QWidget, QtWidgets.QLayout)):
                widget.setEnabled(True)

        # Use the last selected button to set the values
        if selected_buttons:
            button = (canvas.last_selected_button if canvas.last_selected_button and canvas.last_selected_button.is_selected 
                     else selected_buttons[-1])
            self.is_updating_widgets = True
            
            # Batch update widgets
            updates = {
                'rename_edit': button.label,
                'opacity_slider': int(button.opacity * 100),
                'transform_w_edit': button.width,
                'transform_h_edit': button.height,
                'top_left_radius': button.radius[0],
                'top_right_radius': button.radius[1],
                'bottom_right_radius': button.radius[2],
                'bottom_left_radius': button.radius[3],
            }
            
            for widget_name, value in updates.items():
                widgets[widget_name].blockSignals(True)
                if isinstance(widgets[widget_name], QtWidgets.QLineEdit):
                    widgets[widget_name].setText(str(value))
                else:
                    widgets[widget_name].setValue(value)
                widgets[widget_name].blockSignals(False)
            
            widgets['opacity_slider'].updateLabel(updates['opacity_slider'])
            # Update max values for radius widgets
            #max_radius = button.height // 2
            #for radius_widget in ['top_left_radius', 'top_right_radius', 'bottom_right_radius', 'bottom_left_radius']:
            #    widgets[radius_widget].max_value = max_radius

            widgets['transform_w_edit'].setProperty('initial_value', button.width)
            widgets['transform_h_edit'].setProperty('initial_value', button.height)

            is_single_radius = len(set(button.radius)) == 1
            widgets['single_radius'].setChecked(is_single_radius)

            self.is_updating_widgets = False

        #print("Updating edit widgets")

