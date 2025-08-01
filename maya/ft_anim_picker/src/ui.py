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
from .update_ui import UpdateWidget

# Get version from __init__
import ft_anim_picker
anim_picker_version = ft_anim_picker.src.__version__
anim_picker_version = f" (v{anim_picker_version})"

class AnimPickerWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(AnimPickerWindow, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_AlwaysShowToolTips, True)
        self.setStyleSheet('''QWidget {background-color: rgba(40, 40, 40, 0.5); border-radius: 4px;}''')
        
        # Enable drag and drop
        self.setAcceptDrops(True)
        self.edit_mode = False
        self.fade_manager = FadeAway(self)
        self.drag_highlight_active = False

        self.setup_ui()
        self.setup_layout()
        self.setup_tab_system()
        self.setup_connections()
        self.setup_shortcuts()
        
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
            {'widget': self.canvas_frame, 'exclude': [self.canvas_stack]}, # Keep the canvas content visible
            {'widget': self.tools_EF, 'hide_in_minimal': False},
            {'widget': self.canvas_tab_frame, 'hide_in_minimal': True},
            {'widget': self.namespace_dropdown, 'hide_in_minimal': True},
            {'widget': self.close_button, 'hide_in_minimal': True},
        ]

        # Set the affected widgets in the fade manager
        self.fade_manager.set_minimal_affected_widgets(minimal_affected_widgets)

        # Add batch update system
        self.batch_update_active = False
        self.batch_update_timer = QTimer()
        self.batch_update_timer.setSingleShot(True)
        self.batch_update_timer.timeout.connect(self._process_batch_updates)
        self.pending_button_updates = set()
        self.batch_update_delay = 20  # ms delay for batching
        
        # Widget update throttling
        self.widget_update_timer = QTimer()
        self.widget_update_timer.setSingleShot(True)
        self.widget_update_timer.timeout.connect(self._apply_widget_changes)
        self.pending_widget_changes = {}
        self.widget_update_delay = 10  # ms delay for widget updates

        # Setup update checker timer (every 5 seconds)
        self.update_checker_timer = QTimer()
        self.update_checker_timer.timeout.connect(self.update_anim_picker_checker)
        self.update_checker_timer.start(3600000)
        
        self.setup_periodic_cleanup()

        # Initial check for updates
        self.update_anim_picker_checker()

    def setup_ui(self):
        # Allow window to be resized
        self.setMinimumSize(200, 200)
        self.setGeometry(800,280,350,450)

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
        edit_util.addToMenu("Toggle Minimal Mode", self.fade_manager.toggle_minimal_mode, icon='eye.png', position=(2,0))
        edit_util.addToMenu("Toggle Fade Away", self.fade_manager.toggle_fade_away, icon='eye.png', position=(3,0))

        self.info_util = CB.CustomButton(text='Info', height=20, width=40, radius=3,color='#385c73',alpha=0,textColor='#aaaaaa', ContextMenu=True, onlyContext= True,
                                    cmColor='#333333',tooltip='Help', flat=True)
        
        
        self.info_util.addMenuLabel(f"Anim Picker{anim_picker_version}",position=(0,0))
        self.info_util.addToMenu(f"Manual", self.info, icon=UT.get_icon('manual.png'), position=(1,0))
        self.info_util.addToMenu(f"Update", self.update_anim_picker, icon=UT.get_icon('update.png'), position=(2,0))
        #-----------------------------------------------------------------------------------------------------------------------------------
        self.update_anim_picker_button = CB.CustomButton(text='Update Available',icon=UT.get_icon('update.png',size=14,opacity=.7), height=16, radius=8,color='#555555',
        text_size=10,tooltip='Update Anim Picker', textColor='#eeeeee')
        self.update_anim_picker_button.clicked.connect(self.update_anim_picker)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #-Close button
        self.close_button = CB.CustomButton(icon=UT.get_icon('close_01.png',size=12,opacity=.7), height=16, width=16, radius=3,color='#c0091a',tooltip='Close')
        #------------------------------------------------------------------------------------------------------------------------------------------------------

        self.util_frame_col.addWidget(file_util)
        self.util_frame_col.addWidget(edit_util)
        self.util_frame_col.addWidget(self.info_util)
        self.util_frame_col.addStretch(1)
        self.util_frame_col.addWidget(self.update_anim_picker_button)
        self.util_frame_col.addSpacing(4)
        self.update_anim_picker_button.setVisible(False)
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
        self.canvas_frame_layout = QtWidgets.QVBoxLayout(self.canvas_frame)
        set_margin_space(self.canvas_frame_layout, 4, 4)
        
        
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
        
        self.canvas_tab_frame_layout = QtWidgets.QHBoxLayout(self.canvas_tab_frame)
        self.add_tab_button = CB.CustomButton(icon=UT.get_icon('add.png',size=10,opacity=.9), height=16, width=16, radius=8,color='#91cb08',tooltip='Add New Tab')
        self.canvas_tab_frame_layout.addWidget(self.add_tab_button)
        
        set_margin_space(self.canvas_tab_frame_layout, 4, 2)

        # Create canvas stack for switching between canvases
        self.canvas_stack = QtWidgets.QStackedWidget()
        self.canvas_stack.setStyleSheet(f'''QWidget {{border: 0px solid #223d4f; border-radius: 4px; background-color: transparent;}}''')
        
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
        efw = 200 #edit fixed width
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
                background: rgba(30, 30, 30, 0.3);
                width: 8px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(100, 100, 100, 0.5);
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: rgba(120, 120, 120, 0.7);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
                background: transparent;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
                                            
        """)
        
        self.edit_scroll_area.setWidget(self.edit_frame)

        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #-EDIT LAYOUT ------------------->
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        widget_color = "#1e1e1e"
        label_color = "#666666"

        self.edit_layout = QtWidgets.QVBoxLayout(self.edit_frame)
        self.edit_layout.setAlignment(QtCore.Qt.AlignTop|QtCore.Qt.AlignCenter)
        els = 6 #edit layout spacing
        self.edit_layout.setContentsMargins(els, els, els, els)
        self.edit_layout.setSpacing(els)
        #-Edit Label
        self.edit_label = QtWidgets.QLabel("Picker Editor")
        self.edit_label.setAlignment(QtCore.Qt.AlignCenter)        
        self.edit_label.setStyleSheet('QLabel {color: #dddddd; background-color: transparent; font-size: 12px;}')
        #self.edit_layout.addWidget(self.edit_label)
        
        
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
        set_margin_space(self.edit_value_layout,0,4)
        
        #BEW.create_button_edit_widgets(self.edit_value_layout)
        self.add_picker_button = CB.CustomButton(text='Add Button', height=24, radius=4,color='#5285a6',tooltip='Add Button to the current tab')
        #self.edit_button_EF.addWidget(self.add_picker_button)
        self.edit_button_EF.addLayout(self.edit_value_layout)
        self.setup_edit_widgets()
    
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #-Canvas EF
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.edit_canvas_EF = EF.ExpandableFrame(title='Canvas', color='#222222', border=1, border_color='#333333') 
        self.edit_canvas_EF.toggle_expand()
        self.edit_canvas_EF.setFixedWidth(efw-20)

        self.image_button_layout = QtWidgets.QHBoxLayout()
        set_margin_space(self.image_button_layout, 0, 4)
        self.add_image = CB.CustomButton(text='Add',icon=UT.get_icon('img.png', size=14), height=24, radius=4,color='#5c7918',tooltip='Add Image to the current tab')
        self.remove_image = CB.CustomButton(text='Remove',icon=UT.get_icon('img.png', size=14), height=24, radius=4,color='#555555',tooltip='Remove Image from the current tab')
        self.image_button_layout.addWidget(self.add_image)
        self.image_button_layout.addWidget(self.remove_image)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #Image Scale
        self.image_scale_widget = QtWidgets.QWidget()
        self.image_scale_widget.setStyleSheet(f"""QWidget {{background-color: {widget_color}; padding: 0px; border-radius: 3px; border: 0px solid #666666;}}
        QLabel {{color: #aaaaaa; border: none}}
        """)
        image_scale_layout = QtWidgets.QVBoxLayout(self.image_scale_widget)
        set_margin_space(image_scale_layout,6,6)
        
        image_scale_label = QtWidgets.QLabel("Image Scale")
        image_scale_label.setStyleSheet(f"color: {label_color}; font-size: 11px;")
        image_scale_layout.addWidget(image_scale_label)
        
        self.image_scale_layout = QtWidgets.QHBoxLayout()
        self.image_scale_factor = CLE.IntegerLineEdit(min_value=.01, max_value=400, increment=.1, precision=2, width=None, height=18, label="")
        self.image_scale_factor.setText('1.0')
        self.image_scale_layout.addWidget(self.image_scale_factor)
        image_scale_layout.addLayout(self.image_scale_layout)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #Toggle Buttons
        self.toggle_appearance_widget = QtWidgets.QWidget()
        self.toggle_appearance_widget.setStyleSheet(f"""QWidget {{background-color: {widget_color}; padding: 0px; border-radius: 3px; border: 0px solid #666666;}}
        QLabel {{color: #aaaaaa; border: none}}
        """)
        self.toggle_appearance_layout = QtWidgets.QVBoxLayout(self.toggle_appearance_widget)
        set_margin_space(self.toggle_appearance_layout,6,6)
        
        self.toggle_axes = CB.CustomRadioButton('Toggle Axes', height=None,color='#5c7918',fill=False)
        self.toggle_axes.setChecked(True)

        self.toggle_dots = CB.CustomRadioButton('Toggle Dots', height=None,color='#5c7918',fill=False)
        self.toggle_dots.setChecked(True)

        self.toggle_grid = CB.CustomRadioButton('Toggle Grid', height=None,color='#5c7918',fill=False)
        self.toggle_grid.setChecked(False)

        self.grid_size = CLE.IntegerLineEdit(min_value=1, max_value=500, increment=1, width=None, height=18, label="Grid Size")
        self.grid_size.setText('50')

        self.toggle_appearance_layout.addWidget(self.toggle_axes)
        self.toggle_appearance_layout.addWidget(self.toggle_dots)
        self.toggle_appearance_layout.addWidget(self.toggle_grid)
        self.toggle_appearance_layout.addWidget(self.grid_size)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        # Opacity widget
        self.opacity_bg_widget = QtWidgets.QWidget()
        self.opacity_bg_widget.setStyleSheet(f"""QWidget {{background-color: {widget_color}; padding: 0px; border-radius: 3px; border: 0px solid #666666;}}
        QLabel {{color: #aaaaaa; border: none}}
        """)
        opacity_layout = QtWidgets.QVBoxLayout(self.opacity_bg_widget)
        set_margin_space(opacity_layout,6,6)

        opacity_label = QtWidgets.QLabel("Image Opacity")
        opacity_label.setStyleSheet(f"color: {label_color}; font-size: 11px;")
        opacity_layout.addWidget(opacity_label)

        self.image_opacity_slider = CS.CustomSlider(min_value=0, max_value=100, float_precision=0, height=16, radius=8,prefix='',suffix='%', color='#5c7918')
        self.image_opacity_slider.setValue(100)

        opacity_layout.addWidget(self.image_opacity_slider)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #-Background Value Slider
        self.bg_value_bg_widget = QtWidgets.QWidget()
        self.bg_value_bg_widget.setStyleSheet(f"""QWidget {{background-color: {widget_color}; padding: 0px; border-radius: 3px; border: 0px solid #666666;}}
        QLabel {{color: #aaaaaa; border: none}}
        """)
        bg_value_layout = QtWidgets.QVBoxLayout(self.bg_value_bg_widget)
        set_margin_space(bg_value_layout,6,6)

        bg_value_label = QtWidgets.QLabel("Background Value")
        bg_value_label.setStyleSheet(f"color: {label_color}; font-size: 11px;")
        bg_value_layout.addWidget(bg_value_label)

        self.bg_value_slider = CS.CustomSlider(min_value=0, max_value=100, float_precision=0, height=16, radius=8,prefix='',suffix='%', color='#5c7918')
        self.bg_value_slider.setValue(50)

        bg_value_layout.addWidget(self.bg_value_slider)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.edit_canvas_EF.addLayout(self.image_button_layout)
        self.edit_canvas_EF.content_layout.addSpacing(4)
        self.edit_canvas_EF.addWidget(self.opacity_bg_widget)
        self.edit_canvas_EF.addWidget(self.image_scale_widget)
        self.edit_canvas_EF.addWidget(self.bg_value_bg_widget)
        
        self.edit_canvas_EF.addWidget(self.toggle_appearance_widget)
        
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

    def setup_layout(self):
        # Add widgets to layouts
        self.area_01_col.addWidget(self.canvas_frame)

        self.canvas_frame_layout.addLayout(self.picker_canvas_col1)

        self.picker_canvas_col1.addWidget(self.canvas_tab_frame_scroll_area)
        self.picker_canvas_col1.addWidget(self.namespace_dropdown)
        
        self.canvas_frame_layout.addWidget(self.canvas_stack)

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
        self.namespace_dropdown.currentTextChanged.connect(self.on_namespace_changed)
        self.add_image.clicked.connect(self.select_image_for_current_tab)
        self.remove_image.clicked.connect(self.remove_image_from_current_tab)
        self.toggle_axes.toggled.connect(self.toggle_axes_visibility)
        self.toggle_dots.toggled.connect(self.toggle_dots_visibility)
        if self.tab_system.current_tab:
            current_canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            current_canvas.clicked.connect(self.clear_line_edit_focus)
            current_canvas.button_selection_changed.connect(self.update_edit_widgets_delayed)
            #current_canvas.button_selection_changed.connect(self.update_edit_widgets) 
        
        self.image_opacity_slider.valueChanged.connect(self.update_image_opacity)
        self.add_picker_button.clicked.connect(self.add_new_picker_button)
        self.bg_value_slider.valueChanged.connect(self.update_background_value)
        self.toggle_grid.toggled.connect(self.toggle_grid_visibility) 
        self.grid_size.valueChanged.connect(self.update_grid_size) 

        # Keyboard shortcuts
        self.undo_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+Z"), self)
        self.undo_shortcut.activated.connect(self.undo_action)
        
        self.redo_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+Y"), self)
        self.redo_shortcut.activated.connect(self.redo_action)

        self.redo_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+Shift+Z"), self)
        self.redo_shortcut.activated.connect(self.redo_action)

        self.edit_mode_shortcut = QShortcut(QtGui.QKeySequence("Tab"), self)
        self.edit_mode_shortcut.activated.connect(self.toggle_edit_mode) 
    #----------------------------------------------------------------------------------------------------------------------------------------
    def undo_action(self):
        """Perform undo operation"""
        try:
            result = DM.PickerDataManager.undo()
            if result[0]:  # operation_name
                operation_name, selected_button_ids = result
                # Apply changes without full UI refresh
                self.apply_undo_redo_changes(selected_button_ids)
                #print(f"Undid: {operation_name}")
            else:
                print("Nothing to undo")
        except Exception as e:
            print(f"Undo failed: {e}")

    def redo_action(self):
        """Perform redo operation"""
        try:
            result = DM.PickerDataManager.redo()
            if result[0]:  # operation_name
                operation_name, selected_button_ids = result
                # Apply changes without full UI refresh
                self.apply_undo_redo_changes(selected_button_ids)
                #print(f"Redid operation")
            else:
                print("Nothing to redo")
        except Exception as e:
            print(f"Redo failed: {e}")
    
    def apply_undo_redo_changes(self, selected_button_ids=None):
        """Apply changes after undo/redo without full UI rebuild"""
        if not self.tab_system.current_tab:
            return
            
        current_tab = self.tab_system.current_tab
        canvas = self.tab_system.tabs[current_tab]['canvas']
        
        if hasattr(canvas, 'transform_guides'):
            canvas.clear_selection()
            canvas.transform_guides.setVisible(False)
            canvas.transform_guides.visual_layer.setVisible(False)
            canvas.transform_guides.controls_widget.setVisible(False)
        
        # Disable updates during refresh
        self.setUpdatesEnabled(False)
        
        try:
            # Clear current canvas buttons
            for button in canvas.buttons[:]:
                button.setParent(None)
                button.deleteLater()
            canvas.buttons.clear()
            
            # For undo/redo, we only need to recreate buttons, not reset the entire canvas
            # The canvas view (image, opacity, scale, etc.) should remain unchanged
            QtCore.QTimer.singleShot(1, lambda: self.create_buttons_and_restore_selection(selected_button_ids))
            
            # Update widget displays
            self.update_edit_widgets_delayed()
            
        finally:
            # Re-enable updates
            self.setUpdatesEnabled(True)
            self.update()
    
    def create_buttons_and_restore_selection(self, selected_button_ids=None):
        """Create buttons and restore selection from undo/redo"""
        # Create buttons first
        self.create_buttons()
        
        # Get the canvas for current tab
        if not self.tab_system.current_tab:
            return
            
        current_tab = self.tab_system.current_tab
        canvas = self.tab_system.tabs[current_tab]['canvas']
        
        # Use the provided selected button IDs
        if selected_button_ids is None:
            # No selected button IDs provided, skip selection restoration
            return
        
        if selected_button_ids:
            # Find buttons by their IDs and select them
            buttons_to_select = []
            for button in canvas.buttons:
                if hasattr(button, 'unique_id') and button.unique_id in selected_button_ids:
                    buttons_to_select.append(button)
            
            # Select the buttons
            if buttons_to_select:
                # Clear current selection first
                canvas.clear_selection()
                
                # Select the restored buttons
                for button in buttons_to_select:
                    button.is_selected = True
                    button.update()
                
                # Update canvas selection state
                if hasattr(canvas, '_cache_valid'):
                    canvas._cache_valid = False
                canvas.button_selection_changed.emit()
                
                # Show transform guides if buttons are selected
                if len(buttons_to_select) > 0 and hasattr(canvas, 'transform_guides'):
                    canvas.transform_guides.setVisible(True)
                    canvas.transform_guides.visual_layer.setVisible(True)
                    if hasattr(canvas.transform_guides, 'controls_widget'):
                        canvas.transform_guides.controls_widget.setVisible(True)
                    canvas.transform_guides.update_selection()
    
    def get_selected_buttons(self):
        """Get selected buttons from the current tab's canvas"""
        try:
            # Check if tab system is initialized
            if not hasattr(self, 'tab_system') or not self.tab_system:
                return []
            
            # Check if there's a current tab
            if not self.tab_system.current_tab:
                return []
            
            # Check if the current tab exists in the tabs dictionary
            if self.tab_system.current_tab not in self.tab_system.tabs:
                return []
            
            # Get the canvas for the current tab
            current_tab = self.tab_system.current_tab
            tab_data = self.tab_system.tabs[current_tab]
            
            if 'canvas' not in tab_data or not tab_data['canvas']:
                return []
            
            canvas = tab_data['canvas']
            
            # Check if canvas has the get_selected_buttons method
            if not hasattr(canvas, 'get_selected_buttons'):
                return []
            
            # Get selected buttons from canvas
            selected_buttons = canvas.get_selected_buttons()
            
            # Ensure we return a list
            if selected_buttons is None:
                return []
            
            return selected_buttons
            
        except Exception as e:
            print(f"Error getting selected buttons: {e}")
            return []
    
    #----------------------------------------------------------------------------------------------------------------------------------------   
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
            self.setMinimumSize(400,200)
            new_width = current_geometry.width() + edit_panel_width
            self.setGeometry(
                current_geometry.x(),
                current_geometry.y(),
                new_width,
                current_geometry.height()
            )
            # Set active window to self
            self.activateWindow()
            self.raise_()
        else:
            # Subtract edit panel width
            self.setMinimumSize(200,200)
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
        self.update_edit_widgets_delayed()
        QtCore.QTimer.singleShot(0, self.update_buttons_for_current_tab)
    #----------------------------------------------------------------------------------------------------------------------------------------
    def update_anim_picker(self):
        UpdateWidget(self).show()

    def update_anim_picker_checker(self):
        if not hasattr(self, '_update_widget'):
            from .update_ui import UpdateWidget
            self._update_widget = UpdateWidget(self)
            self._update_widget.hide()
        
        latest_release = self._update_widget.parse_version(self._update_widget.get_latest_tag())
        current_version = self._update_widget.parse_version(ft_anim_picker.src.__version__)
        
        #print(f'Latest Release: {latest_release}')
        #print(f'Current Version: {current_version}')
        
        try:
            if latest_release and self._update_widget.is_newer_version(latest_release, current_version):
                self.update_anim_picker_button.setVisible(True)
                self.info_util.set_notification(state=True)
                self.info_util.set_menu_item_notification("Update", state=True)
                #print(f"Update available: {latest_release} > {current_version}")
            else:
                self.update_anim_picker_button.setVisible(False)
                self.info_util.set_notification(state=False)
                self.info_util.set_menu_item_notification("Update", state=False)
                #print(f"No update needed: {latest_release} <= {current_version}")
        except Exception as e:
            print(f"Error checking for updates: {e}")
            self.update_anim_picker_button.setVisible(False) 
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [External Data Management]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def store_picker(self):
        """Enhanced store picker method with current tab vs all tabs option"""
        import maya.cmds as cmds
        
        # First, show the dialog to choose save mode
        from . import picker_io
        save_mode = picker_io.get_save_mode_dialog()
        
        if save_mode == 'cancel':
            return  # User cancelled
        
        # Get the current tab name for potential current tab saving
        current_tab_name = self.tab_system.current_tab if hasattr(self, 'tab_system') else None
        
        # Validate that we have a current tab if user chose current tab mode
        if save_mode == 'current':
            if not current_tab_name:
                QtWidgets.QMessageBox.warning(
                    self, 
                    "No Current Tab", 
                    "No current tab is available to save. Please select a tab first."
                )
                return
        
        # Set default filename based on save mode
        if save_mode == 'current':
            default_filename = f"{current_tab_name}_picker_data.json"
        else:
            default_filename = "picker_data.json"
        
        # Get the appropriate directory for the file dialog
        start_directory = picker_io.get_file_dialog_directory()
        # Combine directory with default filename
        default_path = os.path.join(start_directory, default_filename)
        
        # Show file save dialog
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Store Picker Data",
            default_path,
            "JSON Files (*.json)"
        )
        
        if file_path:
            try:
                # Call the enhanced store_picker_data function
                picker_io.store_picker_data(
                    file_path, 
                    current_tab_name=current_tab_name, 
                    save_mode=save_mode
                )
                
                # Show success message
                if save_mode == 'current':
                    message = f"Current tab '{current_tab_name}' saved to {os.path.basename(file_path)}"
                else:
                    # Get tab count for the message
                    data = picker_io.get_picker_data()
                    tab_count = len(data.get('tabs', {}))
                    message = f"All {tab_count} tab(s) saved to {os.path.basename(file_path)}"
                
                cmds.inViewMessage(amg=message, pos='midCenter', fade=True)
                
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))
                
    def load_picker(self):
        from . import picker_io
        # Get the appropriate directory for the file dialog
        start_directory = picker_io.get_file_dialog_directory()
        
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Load Picker Data",
            start_directory,
            "JSON Files (*.json)"
        )
        if file_path:
            try:
                from . import data_management as DM
                
                # Load the picker data
                picker_io.load_picker_data(file_path)
                
                # Force reload data from defaultObjectSet
                DM.PickerDataManager.reload_data_from_maya()
                
                # Clear existing tabs first
                self.tab_system.clear_all_tabs()
                
                # Refresh the UI to show the loaded data
                self.tab_system.setup_tabs()
                
                # Switch to the first tab if available
                if self.tab_system.tabs:
                    first_tab = next(iter(self.tab_system.tabs))
                    self.tab_system.switch_tab(first_tab)
                    # Update the canvas for this tab
                    self.update_canvas_for_tab(first_tab)
                
                # Create buttons for all tabs
                self.create_buttons()
                
                # Force UI update
                self.update()
                
                cmds.inViewMessage(amg=f"Picker data successfully Imported", pos='midCenter', fade=True)
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", str(e))
                print(f"Error loading picker data: {str(e)}")
                
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
    
    def toggle_grid_visibility(self, checked):
        """Toggle grid visibility for the current tab"""
        if self.tab_system.current_tab:
            current_tab = self.tab_system.current_tab
            current_canvas = self.tab_system.tabs[current_tab]['canvas']
            current_canvas.set_show_grid(checked)
            
            # Update the database
            DM.PickerDataManager.update_grid_visibility(current_tab, checked)

    def update_grid_size(self, size):
        """Update grid size for the current tab"""
        if self.tab_system.current_tab:
            current_tab = self.tab_system.current_tab
            current_canvas = self.tab_system.tabs[current_tab]['canvas']
            current_canvas.set_grid_size(size)
            
            # Update the database
            DM.PickerDataManager.update_grid_size(current_tab, size)
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
            "selectable": new_button.selectable,
            "label": button_label,
            "color": new_button.color,
            "opacity": new_button.opacity,
            "position": (new_button.scene_position.x(), new_button.scene_position.y())
        }
        
        # Update the PickerDataManager
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        tab_data['buttons'].append(button_data)
        #DM.PickerDataManager.update_tab_data(current_tab, tab_data)
        DM.PickerDataManager.batch_update_buttons(current_tab, tab_data['buttons'])

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
                selectable=button_data.get("selectable", True),
                color=button_data.get("color", "#444444"),
                opacity=button_data.get("opacity", 1.0),
                width=button_data.get("width", 80),
                height=button_data.get("height", 30),
                shape_type=button_data.get("shape_type", "rounded_rect"),
                svg_path_data=button_data.get("svg_path_data", None),
                svg_file_path=button_data.get("svg_file_path", None)
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
                    try:
                        button.thumbnail_pixmap = QtGui.QPixmap(button.thumbnail_path)
                        if button.thumbnail_pixmap.isNull():
                            #print(f"Warning: Thumbnail file exists but failed to load: {button.thumbnail_path}")
                            button.thumbnail_pixmap = None
                            # Keep the path for potential repath operation
                    except Exception as e:
                        #print(f"Warning: Error loading thumbnail {button.thumbnail_path}: {e}")
                        button.thumbnail_pixmap = None
                        # Keep the path for potential repath operation
                else:
                    #print(f"Warning: Thumbnail file not found: {button.thumbnail_path}")
                    button.thumbnail_pixmap = None
            
            button.scene_position = QtCore.QPointF(*button_data["position"])
            button.update_tooltip()
            canvas.add_button(button)

        canvas.update_button_positions()
        canvas.update()

    def on_button_changed(self, button):
        self.update_button_data(button)

    def update_button_data(self, button, deleted=False):
        """Enhanced update_button_data that uses direct data manager calls for proper undo recording"""
        if not self.tab_system.current_tab:
            return
        
        # Skip individual updates during batch operations
        if self.batch_update_active and not deleted:
            return
            
        current_tab = self.tab_system.current_tab
        
        if deleted:
            # CRITICAL FIX: Use delete_button method directly for proper undo recording
            DM.PickerDataManager.delete_button(current_tab, button.unique_id, "Delete Button")
            
            # Return the button ID to the available pool
            if current_tab not in self.available_ids:
                self.available_ids[current_tab] = set()
            self.available_ids[current_tab].add(button.unique_id)
            
        else:
            # CRITICAL FIX: Use update_button method directly for proper undo recording
            button_data = {
                "id": button.unique_id,
                "selectable": button.selectable,
                "label": button.label,
                "color": button.color,
                "opacity": button.opacity,
                "position": (button.scene_position.x(), button.scene_position.y()),
                "width": button.width,
                "height": button.height,
                "radius": button.radius,
                "assigned_objects": getattr(button, 'assigned_objects', []),
                "mode": getattr(button, 'mode', 'select'),
                "script_data": getattr(button, 'script_data', {'code': '', 'type': 'python'}),
                "pose_data": getattr(button, 'pose_data', {}),
                "thumbnail_path": getattr(button, 'thumbnail_path', ''),
                "shape_type": button.shape_type,
                "svg_path_data": button.svg_path_data,
                "svg_file_path": button.svg_file_path
            }
            
            # Use the data manager's update method for proper undo recording
            DM.PickerDataManager.update_button(current_tab, button.unique_id, button_data, "Update Button")

    def batch_update_buttons_to_database(self, buttons_to_update, fields_to_update=None):
        """
        Batch update button data to database with full batch system handling
        
        Args:
            buttons_to_update (list): List of button objects to update
            fields_to_update (list): List of field names to update. If None, updates all common fields.
                                    Possible fields: 'position', 'width', 'height', 'radius', 'shape_type', 
                                    'svg_path_data', 'svg_file_path', 'label', 'color', 'opacity', 
                                    'assigned_objects', 'mode', 'script_data', 'pose_data', 'thumbnail_path'
        """
        if not buttons_to_update:
            return
        
        # CRITICAL: Disable all update systems during batch
        was_batch_active = getattr(self, 'batch_update_active', False)
        self.batch_update_active = True
        
        # Stop any running timers to prevent interference
        timers_to_stop = ['batch_update_timer', 'widget_update_timer']
        stopped_timers = {}
        
        for timer_name in timers_to_stop:
            if hasattr(self, timer_name):
                timer = getattr(self, timer_name)
                if timer.isActive():
                    timer.stop()
                    stopped_timers[timer_name] = True
        
        # Clear any pending updates
        if hasattr(self, 'pending_button_updates'):
            self.pending_button_updates.clear()
        
        try:
            # Disconnect changed signals temporarily to prevent interference
            for button in buttons_to_update:
                try:
                    button.changed.disconnect()
                except:
                    pass
            
            # ESSENTIAL: Direct database update (same pattern as Maya version)
            if hasattr(self, 'tab_system') and self.tab_system.current_tab:
                current_tab = self.tab_system.current_tab
                self.initialize_tab_data(current_tab)
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                
                # Default fields to update if none specified
                if fields_to_update is None:
                    # Update all fields
                    fields_to_update = [
                        'position', 'width', 'height', 'radius', 'shape_type', 'label', 
                        'color', 'opacity', 'assigned_objects', 'mode', 'script_data', 
                        'pose_data', 'thumbnail_path', 'svg_path_data', 'svg_file_path', 'selectable'
                    ]
                
                # Create a mapping of existing button IDs for faster lookup
                button_map = {btn['id']: i for i, btn in enumerate(tab_data['buttons'])}
                
                # Update specified fields for all affected buttons
                buttons_updated = 0
                for button in buttons_to_update:
                    if button.unique_id in button_map:
                        button_index = button_map[button.unique_id]
                        
                        # Update only specified fields
                        for field in fields_to_update:
                            if field == 'position':
                                tab_data['buttons'][button_index]['position'] = (
                                    button.scene_position.x(), button.scene_position.y()
                                )
                            elif field == 'width':
                                tab_data['buttons'][button_index]['width'] = button.width
                            elif field == 'height':
                                tab_data['buttons'][button_index]['height'] = button.height
                            elif field == 'radius':
                                tab_data['buttons'][button_index]['radius'] = button.radius
                            elif field == 'shape_type':
                                tab_data['buttons'][button_index]['shape_type'] = button.shape_type
                            elif field == 'svg_path_data':
                                tab_data['buttons'][button_index]['svg_path_data'] = button.svg_path_data
                            elif field == 'svg_file_path':
                                tab_data['buttons'][button_index]['svg_file_path'] = button.svg_file_path
                            elif field == 'label':
                                tab_data['buttons'][button_index]['label'] = button.label
                            elif field == 'color':
                                tab_data['buttons'][button_index]['color'] = button.color
                            elif field == 'opacity':
                                tab_data['buttons'][button_index]['opacity'] = button.opacity
                            elif field == 'assigned_objects':
                                tab_data['buttons'][button_index]['assigned_objects'] = getattr(
                                    button, 'assigned_objects', []
                                )
                            elif field == 'mode':
                                tab_data['buttons'][button_index]['mode'] = getattr(
                                    button, 'mode', 'select'
                                )
                            elif field == 'script_data':
                                tab_data['buttons'][button_index]['script_data'] = getattr(
                                    button, 'script_data', {'code': '', 'type': 'python'}
                                )
                            elif field == 'pose_data':
                                tab_data['buttons'][button_index]['pose_data'] = getattr(
                                    button, 'pose_data', {}
                                )
                            elif field == 'thumbnail_path':
                                tab_data['buttons'][button_index]['thumbnail_path'] = getattr(
                                    button, 'thumbnail_path', ''
                                )
                            elif field == 'selectable':
                                tab_data['buttons'][button_index]['selectable'] = getattr(
                                    button, 'selectable', True
                                )
                        
                        buttons_updated += 1
                    else:
                        # If button not found in database, add it with all current properties
                        button_data = {
                            "id": button.unique_id,
                            "selectable": getattr(button, 'selectable', True),
                            "label": button.label,
                            "color": button.color,
                            "opacity": button.opacity,
                            "position": (button.scene_position.x(), button.scene_position.y()),
                            "width": button.width,
                            "height": button.height,
                            "radius": button.radius,
                            "assigned_objects": getattr(button, 'assigned_objects', []),
                            "mode": getattr(button, 'mode', 'select'),
                            "script_data": getattr(button, 'script_data', {'code': '', 'type': 'python'}),
                            "pose_data": getattr(button, 'pose_data', {}),
                            "thumbnail_path": getattr(button, 'thumbnail_path', ''),
                            "shape_type": button.shape_type,
                            "svg_path_data": button.svg_path_data,
                            "svg_file_path": button.svg_file_path
                        }
                        tab_data['buttons'].append(button_data)
                        buttons_updated += 1
                
                # Single database update for all buttons
                #DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                DM.PickerDataManager.batch_update_buttons(current_tab, tab_data['buttons'])
                # Force immediate save to ensure data persistence
                DM.PickerDataManager.save_data(
                    DM.PickerDataManager.get_data(), 
                    force_immediate=True
                )
                
                #print(f"Batch updated {buttons_updated} buttons in database (fields: {fields_to_update})")
            
            # Reconnect signals properly
            for button in buttons_to_update:
                # Reconnect to the main window's handler
                if hasattr(self, 'on_button_changed'):
                    button.changed.connect(self.on_button_changed)
                else:
                    # Fallback connection
                    button.changed.connect(self.update_button_data)
            
            # Update canvas if available
            if hasattr(self, 'tab_system') and self.tab_system.current_tab:
                canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
                canvas.update()
                if hasattr(canvas, 'update_button_positions'):
                    canvas.update_button_positions()
        
        except Exception as e:
            print(f"Error during batch update: {e}")
            
            # Emergency signal reconnection
            for button in buttons_to_update:
                try:
                    if hasattr(self, 'on_button_changed'):
                        button.changed.connect(self.on_button_changed)
                    else:
                        button.changed.connect(self.update_button_data)
                except:
                    pass
                    
        finally:
            # Restore batch mode state
            self.batch_update_active = was_batch_active
            
            # Restart stopped timers if they were originally active
            for timer_name, was_active in stopped_timers.items():
                if was_active and hasattr(self, timer_name):
                    timer = getattr(self, timer_name)
                    # Give a small delay before restarting
                    QtCore.QTimer.singleShot(100, timer.start)

    def _process_batch_updates(self):
        """Enhanced batch updates that skips during active batch operations"""
        # Skip if we're in the middle of a batch operation
        if self.batch_update_active:
            return
            
        if not self.pending_button_updates or not self.tab_system.current_tab:
            return
            
        current_tab = self.tab_system.current_tab
        canvas = self.tab_system.tabs[current_tab]['canvas']
        
        # Collect all button data for batch update
        buttons_to_update = []
        for button in canvas.buttons:
            if button.unique_id in self.pending_button_updates:
                button_data = {
                    "id": button.unique_id,
                    "selectable": button.selectable,
                    "label": button.label,
                    "color": button.color,
                    "opacity": button.opacity,
                    "position": (button.scene_position.x(), button.scene_position.y()),
                    "width": button.width,
                    "height": button.height,
                    "radius": button.radius,
                    "assigned_objects": button.assigned_objects,
                    "mode": button.mode,
                    "script_data": button.script_data,
                    "pose_data": button.pose_data,
                    "thumbnail_path": getattr(button, 'thumbnail_path', ''),
                    "shape_type": button.shape_type,
                    "svg_path_data": button.svg_path_data,
                    "svg_file_path": button.svg_file_path
                }
                buttons_to_update.append(button_data)
        
        # Single database update for all buttons
        if buttons_to_update:
            DM.PickerDataManager.batch_update_buttons(current_tab, buttons_to_update)
        
        self.pending_button_updates.clear()
    
    def _batch_button_operation(self, operation_func, *args, **kwargs):
        """FIXED: Execute button operations in batch mode with proper deletion handling"""
        if not self.tab_system.current_tab:
            return
        
        canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        selected_buttons = canvas.get_selected_buttons()
        current_tab = self.tab_system.current_tab
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        if not selected_buttons:
            return
        
        # Special handling for deletion operations
        operation_name = getattr(operation_func, '__name__', str(operation_func))
        is_deletion_operation = 'delete' in operation_name.lower()
        
        if is_deletion_operation:
            # Handle deletions separately - don't use batch update system
            operation_func(*args, **kwargs)
            return
        
        # Regular batch operations (non-deletion)
        self.batch_update_active = True
        self.edit_widgets_update_enabled = False
        canvas.setUpdatesEnabled(False)
        
        try:
            # Apply operation to all selected buttons
            for button in selected_buttons:
                operation_func(button, *args, **kwargs)
                self.pending_button_updates.add(button.unique_id)  # Use unique_id, not button object
            
            # Single update at the end
            self._flush_pending_updates()
            
        finally:
            # Re-enable updates
            canvas.setUpdatesEnabled(True)
            self.edit_widgets_update_enabled = True
            self.batch_update_active = False
            
            canvas.update()

    def _flush_pending_updates(self):
        """ENHANCED: Flush all pending button updates in one batch - handles both updates and deletions"""
        if not self.pending_button_updates:
            return
        
        current_tab = self.tab_system.current_tab
        if not current_tab:
            self.pending_button_updates.clear()
            return
            
        canvas = self.tab_system.tabs[current_tab]['canvas']
        
        # Separate existing buttons from deleted ones
        existing_button_ids = {button.unique_id for button in canvas.buttons}
        updates_to_process = []
        deletions_to_process = []
        
        for button_id in self.pending_button_updates:
            if button_id in existing_button_ids:
                # Find the actual button object for updates
                for button in canvas.buttons:
                    if button.unique_id == button_id:
                        updates_to_process.append(button)
                        break
            else:
                # Button no longer exists - it was deleted
                deletions_to_process.append(button_id)
        
        #print(f"Processing batch update: {len(updates_to_process)} updates, {len(deletions_to_process)} deletions")
        
        # Process deletions first
        if deletions_to_process:
            self.initialize_tab_data(current_tab)
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            original_count = len(tab_data['buttons'])
            
            # Remove all deleted buttons from data
            tab_data['buttons'] = [b for b in tab_data['buttons'] if b['id'] not in deletions_to_process]
            new_count = len(tab_data['buttons'])
            
            if new_count < original_count:
                # Update data manager
                DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                
                # Add deleted IDs to available IDs
                if current_tab not in self.available_ids:
                    self.available_ids[current_tab] = set()
                self.available_ids[current_tab].update(deletions_to_process)
                
                #print(f"Removed {original_count - new_count} deleted buttons from database")
        
        # Process updates for existing buttons
        if updates_to_process:
            self.initialize_tab_data(current_tab)
            tab_data = DM.PickerDataManager.get_tab_data(current_tab)
            
            # Create a mapping of existing button IDs for faster lookup
            existing_buttons_map = {btn['id']: i for i, btn in enumerate(tab_data['buttons'])}
            
            updates_applied = 0
            for button in updates_to_process:
                try:
                    # Create comprehensive button data
                    button_data = {
                        "id": button.unique_id,
                        "selectable": button.selectable,
                        "label": button.label,
                        "color": button.color,
                        "opacity": button.opacity,
                        "position": (button.scene_position.x(), button.scene_position.y()),
                        "width": button.width,
                        "height": button.height,
                        "radius": button.radius,
                        "assigned_objects": getattr(button, 'assigned_objects', []),
                        "mode": getattr(button, 'mode', 'select'),
                        "script_data": getattr(button, 'script_data', {'code': '', 'type': 'python'}),
                        "pose_data": getattr(button, 'pose_data', {}),
                        "thumbnail_path": getattr(button, 'thumbnail_path', ''),
                        "shape_type": button.shape_type,
                        "svg_path_data": button.svg_path_data,
                        "svg_file_path": button.svg_file_path
                    }
                    
                    # Update existing button or add new one
                    if button.unique_id in existing_buttons_map:
                        # Update existing button
                        index = existing_buttons_map[button.unique_id]
                        tab_data['buttons'][index] = button_data
                    else:
                        # Add new button
                        tab_data['buttons'].append(button_data)
                        existing_buttons_map[button.unique_id] = len(tab_data['buttons']) - 1
                    
                    updates_applied += 1
                    
                except Exception as e:
                    print(f"Error updating button {button.unique_id}: {e}")
                    continue
            
            if updates_applied > 0:
                # Save updated tab data
                #DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                DM.PickerDataManager.batch_update_buttons(current_tab, tab_data['buttons'])
                #print(f"Applied {updates_applied} button updates to database")
        
        # Update button positions once
        canvas.update_button_positions()
        
        # Clear pending updates
        self.pending_button_updates.clear()
        
        #print("Batch update complete")
    
    def get_button_data(self):
        canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        selected_buttons = canvas.get_selected_buttons()
        button_data_list = []
        for button in selected_buttons:
            button_data = {
                "id": button.unique_id,
                "selectable": button.selectable,
                "label": button.label,
                "color": button.color,
                "opacity": button.opacity,
                "position": (button.scene_position.x(), button.scene_position.y()),
                "width": button.width,
                "height": button.height,
                "radius": button.radius,
                "assigned_objects": button.assigned_objects,
                "mode": button.mode,
                "script_data": button.script_data,
                "pose_data": button.pose_data,
                "thumbnail_path": getattr(button, 'thumbnail_path', ''),
                "shape_type": button.shape_type,
                "svg_path_data": button.svg_path_data,
                "svg_file_path": button.svg_file_path
            }
            button_data_list.append(button_data)
        return button_data_list

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
                
    def update_button_z_order(self):
        """Update the z-order of buttons in the database"""
        if not self.tab_system.current_tab:
            return
            
        current_tab = self.tab_system.current_tab
        canvas = self.tab_system.tabs[current_tab]['canvas']
        
        # Get current tab data
        self.initialize_tab_data(current_tab)
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        
        # Create a new buttons list in the current canvas order
        ordered_buttons = []
        button_data_map = {btn_data['id']: btn_data for btn_data in tab_data['buttons']}
        
        # Rebuild the buttons list in the current canvas order
        for canvas_button in canvas.buttons:
            if canvas_button.unique_id in button_data_map:
                # Get the existing button data and preserve all properties
                button_data = button_data_map[canvas_button.unique_id].copy()
                
                # Update position and any other current properties
                button_data.update({
                    "position": (canvas_button.scene_position.x(), canvas_button.scene_position.y()),
                    "selectable": canvas_button.selectable,
                    "width": canvas_button.width,
                    "height": canvas_button.height,
                    "label": canvas_button.label,
                    "color": canvas_button.color,
                    "opacity": canvas_button.opacity,
                    "radius": canvas_button.radius,
                    "assigned_objects": getattr(canvas_button, 'assigned_objects', []),
                    "mode": getattr(canvas_button, 'mode', 'select'),
                    "script_data": getattr(canvas_button, 'script_data', {'code': '', 'type': 'python'}),
                    "pose_data": getattr(canvas_button, 'pose_data', {}),
                    "thumbnail_path": getattr(canvas_button, 'thumbnail_path', ''),
                    "shape_type": canvas_button.shape_type,
                    "svg_path_data": canvas_button.svg_path_data,
                    "svg_file_path": canvas_button.svg_file_path
                })
                
                ordered_buttons.append(button_data)
        
        # Update the tab data with the new order
        tab_data['buttons'] = ordered_buttons
        DM.PickerDataManager.update_tab_data(current_tab, tab_data)
        
        print(f"Updated z-order for {len(ordered_buttons)} buttons in tab '{current_tab}'")
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
        elif 'image_scale' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['image_scale'] = 1.0  
        elif 'image_opacity' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['image_opacity'] = 1.0 

    def setup_tab_system(self):
        self.tab_system = TS.TabSystem(self.canvas_tab_frame_layout, self.add_tab_button)
        self.tab_system.tab_switched.connect(self.on_tab_switched)
        self.tab_system.tab_renamed.connect(self.on_tab_renamed)
        self.tab_system.tab_deleted.connect(self.on_tab_deleted)
        self.tab_system.tab_reordered.connect(self.on_tab_reordered)
        
        self.tab_system.setup_tabs()
        
        if not self.tab_system.tabs:
            self.tab_system.add_tab("Tab 1")
            self.initialize_tab_data("Tab 1")
            DM.PickerDataManager.add_tab("Tab 1")
        
        QtCore.QTimer.singleShot(50, self.create_buttons)

    def on_tab_reordered(self):
        # Update the UI if needed after tab reordering
        if self.tab_system.current_tab:
            self.update_canvas_for_tab(self.tab_system.current_tab)
        else:
            self.clear_canvas()

    def on_tab_switched(self, tab_name):
        # Initialize tab data if needed
        self.initialize_tab_data(tab_name)
        
        # Get the canvas for this tab
        current_canvas = self.tab_system.tabs[tab_name]['canvas']
        current_canvas.clear_selection()
        
        # Add the canvas to the stack if it's not already there
        if self.canvas_stack.indexOf(current_canvas) == -1:
            self.canvas_stack.addWidget(current_canvas)
        
        # Show the current canvas
        self.canvas_stack.setCurrentWidget(current_canvas)
        
        # Update the canvas properties
        self.update_canvas_for_tab(tab_name)
        
        # Update opacity slider if available
        if hasattr(self, 'image_opacity_slider'):
            current_opacity = self.tab_system.tabs[tab_name].get('image_opacity', 1.0)
            self.image_opacity_slider.setValue(int(current_opacity * 100))
        
        # Disconnect any existing connections to avoid duplicates
        try:
            current_canvas.button_selection_changed.disconnect()
            current_canvas.clicked.disconnect()
        except:
            pass
        
        # Connect with the delayed update method
        current_canvas.button_selection_changed.connect(self.update_edit_widgets_delayed)
        current_canvas.clicked.connect(self.clear_line_edit_focus)
        
        # Update image button state if available
        if hasattr(self, 'remove_image'):
            has_image = self.tab_system.tabs[tab_name].get('image_path') is not None
            self.remove_image.setEnabled(has_image)
        
        # Create buttons explicitly for the current tab
        QtCore.QTimer.singleShot(10, self.create_buttons)
        
        # Update namespace dropdown for the new tab
        self.update_namespace_dropdown()
        
        current_canvas.update()
        if self.edit_mode == False:
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
        QtCore.QTimer.singleShot(10, self.create_buttons)
        
        # Refresh the canvas
        current_canvas = self.tab_system.tabs[new_name]['canvas']
        current_canvas.update()

        # Force a refresh of the tab system
        self.tab_system.update_tab_buttons()

    def on_tab_deleted(self, deleted_tab_name):
        # Remove the canvas with proper cleanup
        if deleted_tab_name in self.tab_system.tabs:
            canvas = self.tab_system.tabs[deleted_tab_name]['canvas']
            
            # Cleanup buttons first
            for button in list(canvas.buttons):
                self._cleanup_button(button)
            canvas.buttons.clear()
            
            # Remove from stack
            index = self.canvas_stack.indexOf(canvas)
            if index != -1:
                self.canvas_stack.removeWidget(canvas)
            
            # Disconnect and cleanup canvas
            try:
                canvas.button_selection_changed.disconnect()
                canvas.clicked.disconnect()
            except:
                pass
            
            canvas.setParent(None)
            canvas.deleteLater()
                
        # Update UI for the current tab if there is one
        if self.tab_system.current_tab:
            self.update_canvas_for_tab(self.tab_system.current_tab)
            self.update_buttons_for_current_tab(force_update=True)
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
        QtCore.QTimer.singleShot(10, self.create_buttons)

    def clear_canvas(self):
        # Find and clear the current canvas
        current_tab = self.tab_system.current_tab
        if current_tab and current_tab in self.tab_system.tabs:
            canvas = self.tab_system.tabs[current_tab]['canvas']
            
            # Clear existing buttons
            for button in canvas.buttons[:]:  # Use a copy of the list to avoid modification during iteration
                canvas.remove_button(button)
                button.deleteLater()
                
            # Update canvas
            canvas.update()
        
        # Reset other UI elements as needed
        if hasattr(self, 'image_opacity_slider'):
            self.image_opacity_slider.setValue(100)
        if hasattr(self, 'remove_image'):
            self.remove_image.setEnabled(False)

    def update_canvas_for_tab(self, tab_name):
        if tab_name not in self.tab_system.tabs:
            # If the tab_name is invalid, switch to the first available tab
            if self.tab_system.tabs:
                tab_name = next(iter(self.tab_system.tabs))
            else:
                self.clear_canvas()
                return
                
        # Get the canvas for this tab
        current_canvas = self.tab_system.tabs[tab_name]['canvas']
        # Add the canvas to the stack if it's not already there
        if self.canvas_stack.indexOf(current_canvas) == -1:
            self.canvas_stack.addWidget(current_canvas)
        
        # Show the current canvas
        self.canvas_stack.setCurrentWidget(current_canvas)
        current_canvas.show()

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

        # Set grid visibility and size
        show_grid = tab_data.get('show_grid', False)  # Default to False
        current_canvas.set_show_grid(show_grid)
        self.toggle_grid.setChecked(show_grid)
        
        grid_size = tab_data.get('grid_size', 10)  # Default to 10
        current_canvas.set_grid_size(grid_size)
        self.grid_size.setText(str(grid_size))

        # Get and set background value
        background_value = tab_data.get('background_value', 20)  # Default to 20%
        self.bg_value_slider.setValue(background_value)
        current_canvas.set_background_value(background_value)

        image_scale = tab_data.get('image_scale', 1.0)
        self.image_scale_factor.setText(str(image_scale))  # Always update the UI widget
        current_canvas.set_image_scale(image_scale)  # Always set canvas scale
        
        # Set other canvas properties (image and opacity)
        image_path = tab_data.get('image_path')
        
        image_opacity = tab_data.get('image_opacity', 1.0)
        self.tab_system.tabs[tab_name]['image_opacity'] = image_opacity
        
        if image_path:
            # Set the opacity on the canvas first
            current_canvas.set_image_opacity(image_opacity)
            # Then set the background image
            current_canvas.set_background_image(image_path)
            self.remove_image.setEnabled(True)
            self.tab_system.tabs[tab_name]['image_path'] = image_path
        else:
            current_canvas.set_background_image(None)
            self.remove_image.setEnabled(False)
            self.tab_system.tabs[tab_name]['image_path'] = None

        # Apply the opacity again after setting the image to ensure it's not overridden
        current_canvas.set_image_opacity(image_opacity)
        self.image_opacity_slider.setValue(int(image_opacity * 100))
        
        # Store the values in the tab system
        self.tab_system.tabs[tab_name]['image_scale'] = image_scale
        
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
        def rename_operation(button, label):
            button.label = label
            button.text_pixmap = None  # Force text regeneration
            button.update()
        
        self._batch_button_operation(rename_operation, new_label)

    def _immediate_rename_apply(self):
        """Apply rename immediately on Return key press"""
        if not self.is_updating_widgets:
            self.rename_selected_buttons(self.edit_widgets['rename_edit'].text())

    def change_opacity_for_selected_buttons(self, value):
        canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        selected_buttons = canvas.get_selected_buttons()
        if selected_buttons:
            for button in selected_buttons:
                button.change_opacity(value)
            self.batch_update_buttons_to_database(selected_buttons)   
            self.update_buttons_for_current_tab()
            
    def set_size_for_selected_buttons(self, transform_data):
        """Enhanced set_size method that accepts current reference dimensions"""
        if not self.tab_system.current_tab:
            return
            
        canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        selected_buttons = canvas.get_selected_buttons()
        
        if not selected_buttons:
            return
        
        # Extract transform data
        if isinstance(transform_data, dict):
            target_width = transform_data['target_width']
            target_height = transform_data['target_height']
            ref_width = transform_data['ref_width']
            ref_height = transform_data['ref_height']
        else:
            # Fallback for legacy calls with tuple (width, height)
            target_width, target_height = transform_data
            # Use first button as reference for legacy calls
            ref_width = selected_buttons[0].width
            ref_height = selected_buttons[0].height
        
        # Calculate scale factors from current reference to target
        if ref_width > 0 and ref_height > 0:
            width_scale = target_width / ref_width
            height_scale = target_height / ref_height
            
            # Apply scaling to all selected buttons
            for button in selected_buttons:
                # Scale each button relative to its own current size
                new_width = round(button.width * width_scale)
                new_height = round(button.height * height_scale)
                
                # Ensure minimum size
                new_width = max(1, new_width)
                new_height = max(1, new_height)
                
                # Apply the new size
                button.width = new_width
                if button.mode == 'pose':
                    button._original_height = new_height
                    button.height = new_width * 1.25
                else:
                    button.height = new_height
                
                # Clear cached pixmaps to force regeneration
                button.text_pixmap = None
                button.pose_pixmap = None
                button.last_zoom_factor = 0
                button.update()
                #self.update_button_data(button)
            self.batch_update_buttons_to_database(selected_buttons)
        
        canvas.update_button_positions()

        self.update_buttons_for_current_tab()

    def _apply_width_to_all(self, width):
        '''Apply the entered width to all selected buttons'''
        if not self.is_updating_widgets:
            canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            selected_buttons = canvas.get_selected_buttons()
            
            if selected_buttons:
                # Apply the exact width value to all selected buttons
                for button in selected_buttons:
                    button.width = round(width)
                    if button.mode == 'pose':
                        button.height = button.width * 1.25
                    button.update()
                    self.pending_button_updates.add(button.unique_id)
                
                # Update canvas and process changes
                canvas.update_button_positions()
                self._process_batch_updates()
                self.update_edit_widgets_delayed()

    def _apply_height_to_all(self, height):
        '''Apply the entered height to all selected buttons'''
        if not self.is_updating_widgets:
            canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            selected_buttons = canvas.get_selected_buttons()
            
            if selected_buttons:
                # Apply the exact height value to all selected buttons
                for button in selected_buttons:
                    if button.mode != 'pose':  # Don't override pose button height calculation
                        button.height = round(height)
                    button.update()
                    self.pending_button_updates.add(button.unique_id)
                
                # Update canvas and process changes
                canvas.update_button_positions()
                self._process_batch_updates()
                self.update_edit_widgets_delayed()

    def match_button_size(self):
        """Set the height of selected buttons to match their width"""
        if not self.tab_system.current_tab:
            return
            
        canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        selected_buttons = canvas.get_selected_buttons()
        
        if selected_buttons:
            for button in selected_buttons:
                if button.mode != 'pose':  # Don't override pose button height calculation
                    #button.height = button.width
                    button.width = button.height
                    #self.update_button_data(button)
                button.update()
                self.pending_button_updates.add(button.unique_id)
            
            # Update canvas and process changes
            canvas.update_button_positions()
            self.batch_update_buttons_to_database(selected_buttons)
            self.update_edit_widgets_delayed()
    
    def set_radius_for_selected_buttons(self, tl, tr, br, bl):
        if self.tab_system.current_tab:
            canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            for button in canvas.get_selected_buttons():
                button.set_radius(tl, tr, br, bl)
                
            canvas.update_button_positions() 
            DM.PickerDataManager.batch_update_buttons(self.tab_system.current_tab, self.get_button_data())       
            #self.batch_update_buttons_to_database(canvas.get_selected_buttons())   
            self.update_buttons_for_current_tab()

    def change_color_for_selected_buttons(self, color):
        """Optimized color change with batching"""
        def color_operation(button, new_color):
            button.color = new_color
            button.update()
        
        self._batch_button_operation(color_operation, color)
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [Picker Button Edit Widgets]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def setup_edit_widgets(self):
        """Enhanced setup_edit_widgets method with proper signal connections"""
        widgets = BEW.create_button_edit_widgets(self)
        
        # Add widgets to layout
        self.edit_value_layout.addWidget(widgets['rename_widget'])
        self.edit_value_layout.addWidget(widgets['transform_widget'])
        self.edit_value_layout.addWidget(widgets['radius_widget'])
        self.edit_value_layout.addWidget(widgets['opacity_widget'])
        self.edit_value_layout.addWidget(widgets['color_picker'])
        self.edit_value_layout.addWidget(widgets['placement_widget'])
        self.edit_value_layout.addWidget(widgets['thumbnail_dir_widget'])

        self.is_updating_widgets = False

        # Connect signals with proper methods
        widgets['rename_edit'].textChanged.connect(self._queue_rename_change)
        widgets['rename_edit'].returnPressed.connect(self._immediate_rename_apply)
        widgets['opacity_slider'].valueChanged.connect(self._queue_opacity_change)
        
        # Transform signals
        widgets['transform_w_edit'].valueChanged.connect(self._queue_transform_change)
        widgets['transform_h_edit'].valueChanged.connect(self._queue_transform_change)
        
        # Enable apply-to-all for transform controls
        widgets['transform_w_edit'].setApplyToAllMode(True)
        widgets['transform_h_edit'].setApplyToAllMode(True)
        
        # Connect the new signals
        widgets['transform_w_edit'].applyToAllRequested.connect(self._apply_width_to_all)
        widgets['transform_h_edit'].applyToAllRequested.connect(self._apply_height_to_all)

        # Radius signals - connect ALL radius inputs
        widgets['top_left_radius'].valueChanged.connect(self._queue_radius_change)
        widgets['top_right_radius'].valueChanged.connect(self._queue_radius_change)
        widgets['bottom_right_radius'].valueChanged.connect(self._queue_radius_change)
        widgets['bottom_left_radius'].valueChanged.connect(self._queue_radius_change)
        
        # Single radius toggle
        widgets['single_radius'].toggled.connect(self._handle_single_radius_toggle)
        
        # Color buttons
        for i, color_button in enumerate(widgets['color_buttons']):
            color = color_button.palette().button().color().name()
            color_button.clicked.connect(partial(self._queue_color_change, color))

        self.edit_widgets = widgets

    def _queue_rename_change(self):
        """ADD this method for throttled rename updates"""
        if not self.is_updating_widgets:
            self.pending_widget_changes['rename'] = self.edit_widgets['rename_edit'].text()
            self.widget_update_timer.start(self.widget_update_delay)

    def _queue_opacity_change(self, value):
        """ADD this method for throttled opacity updates"""
        if not self.is_updating_widgets:
            self.pending_widget_changes['opacity'] = value
            self.widget_update_timer.start(50)  # Shorter delay for opacity

    def _queue_transform_change(self):
        """Queue transform changes for batch processing with proper proportional scaling"""
        if not self.is_updating_widgets:
            w_edit = self.edit_widgets['transform_w_edit']
            h_edit = self.edit_widgets['transform_h_edit']
            
            # Handle proportional scaling
            if self.edit_widgets['transform_prop'].isChecked():
                sender = self.sender()
                
                # Get the button's original aspect ratio for proportional scaling
                if self.tab_system.current_tab:
                    canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
                    selected_buttons = canvas.get_selected_buttons()
                    
                    if selected_buttons:
                        # Use the reference button's current dimensions to calculate aspect ratio
                        reference_button = (canvas.last_selected_button 
                                        if canvas.last_selected_button and canvas.last_selected_button.is_selected 
                                        else selected_buttons[-1])
                        
                        original_width = reference_button.width
                        original_height = reference_button.height
                        aspect_ratio = original_width / original_height if original_height > 0 else 1.0
                        
                        self.is_updating_widgets = True
                        
                        if sender == w_edit:
                            # Width changed, calculate proportional height
                            new_width = w_edit.value()
                            new_height = new_width / aspect_ratio
                            h_edit.setValue(round(new_height))
                            
                        elif sender == h_edit:
                            # Height changed, calculate proportional width
                            new_height = h_edit.value()
                            new_width = new_height * aspect_ratio
                            w_edit.setValue(round(new_width))
                        
                        self.is_updating_widgets = False
            
            # CRITICAL FIX: Get current reference button dimensions at edit time
            if self.tab_system.current_tab:
                canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
                selected_buttons = canvas.get_selected_buttons()
                
                if selected_buttons:
                    # Use the last selected button as reference
                    reference_button = (canvas.last_selected_button 
                                    if canvas.last_selected_button and canvas.last_selected_button.is_selected 
                                    else selected_buttons[-1])
                    
                    # Capture current reference dimensions (not stale initial values)
                    current_ref_width = reference_button.width
                    current_ref_height = reference_button.height
                    target_width = w_edit.value()
                    target_height = h_edit.value()
                    
                    # Store transform data with current reference dimensions
                    self.pending_widget_changes['transform'] = {
                        'target_width': target_width,
                        'target_height': target_height,
                        'ref_width': current_ref_width,
                        'ref_height': current_ref_height
                    }
            
            self.widget_update_timer.start(self.widget_update_delay)

    def _queue_radius_change(self):
        """Queue radius changes for batch processing with proper single radius handling"""
        if not self.is_updating_widgets:
            widgets = self.edit_widgets
            
            # Handle single radius mode
            if widgets['single_radius'].isChecked():
                sender = self.sender()
                # Only apply to all if the top-left radius was changed
                if sender == widgets['top_left_radius']:
                    value = sender.value()
                    self.is_updating_widgets = True
                    widgets['top_right_radius'].setValue(value)
                    widgets['bottom_right_radius'].setValue(value)
                    widgets['bottom_left_radius'].setValue(value)
                    self.is_updating_widgets = False
            
            radius_values = (
                widgets['top_left_radius'].value(),
                widgets['top_right_radius'].value(),
                widgets['bottom_right_radius'].value(),
                widgets['bottom_left_radius'].value()
            )
            self.pending_widget_changes['radius'] = radius_values
            self.widget_update_timer.start(self.widget_update_delay)
    
    def _queue_color_change(self, color):
        """Queue color changes with proper validation"""
        if not self.is_updating_widgets:
            # Ensure color is a valid hex string
            if hasattr(color, 'name'):  # QColor object
                color_str = color.name()
            elif isinstance(color, str):
                color_str = color
            else:
                color_str = str(color)
            
            # Validate hex format
            if not (color_str.startswith('#') and len(color_str) == 7):
                print(f"Invalid color format received: {color_str}")
                return
                
            self.pending_widget_changes['color'] = color_str
            self.widget_update_timer.start(50)

    def _handle_single_radius_toggle(self, checked):
        """Handle single radius toggle with visual feedback"""
        widgets = self.edit_widgets
        dss = "background-color: #222222; color: #444444; border: 1px solid #444444; border-radius: 3px;"
        ass = "background-color: #333333; color: #dddddd; border: 1px solid #444444; border-radius: 3px;"
        
        if checked:
            value = widgets['top_left_radius'].value()
            widgets['top_left_radius'].setStyleSheet("background-color: #6c9809; color: #dddddd; border: 1px solid #444444; border-radius: 3px;")
            
            # Disable and style other radius inputs
            for widget_name in ['top_right_radius', 'bottom_right_radius', 'bottom_left_radius']:
                widgets[widget_name].setEnabled(False)
                widgets[widget_name].setStyleSheet(dss)
                widgets[widget_name].setValue(value)
        else:
            widgets['top_left_radius'].setStyleSheet(ass)
            # Enable and style other radius inputs
            for widget_name in ['top_right_radius', 'bottom_right_radius', 'bottom_left_radius']:
                widgets[widget_name].setEnabled(True)
                widgets[widget_name].setStyleSheet(ass)
        
        # Queue the radius update
        self._queue_radius_change()
    
    def _apply_widget_changes(self):
        """Enhanced apply widget changes with improved transform handling"""
        if not self.pending_widget_changes or not self.tab_system.current_tab:
            return
            
        canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        selected_buttons = canvas.get_selected_buttons()
        
        if not selected_buttons:
            self.pending_widget_changes.clear()
            return
        
        # Disable visual updates during batch operation
        self.setUpdatesEnabled(False)
        canvas.setUpdatesEnabled(False)
        
        try:
            # Apply all changes to all selected buttons
            for change_type, value in self.pending_widget_changes.items():
                if change_type == 'transform':
                    # Use the enhanced transform method
                    self.set_size_for_selected_buttons(value)
                else:
                    # Handle other change types normally
                    for button in selected_buttons:
                        if change_type == 'rename':
                            button.label = value
                            button.text_pixmap = None  # Force text regeneration
                        elif change_type == 'opacity':
                            button.opacity = value / 100.0
                        elif change_type == 'radius':
                            tl, tr, br, bl = value
                            button.set_radius(tl, tr, br, bl)
                        elif change_type == 'color':
                            # Validate the color format
                            if isinstance(value, str) and value.startswith('#') and len(value) == 7:
                                button.change_color(value)
                            else:
                                print(f"Invalid color format received: {value}")
                                continue
                        
                        # Mark button as changed
                        button.update()
                        self.pending_button_updates.add(button.unique_id)
            self.batch_update_buttons_to_database(canvas.get_selected_buttons())
            # Update button positions if any transform changes were made
            if 'transform' not in self.pending_widget_changes:
                canvas.update_button_positions()
        
        finally:
            # Re-enable updates and refresh canvas
            canvas.setUpdatesEnabled(True)
            self.setUpdatesEnabled(True)
            canvas.update()
        
        # Clear pending changes
        self.pending_widget_changes.clear()
        
        # Process database updates
        #self.batch_update_timer.start(self.batch_update_delay)
        
    #----------------------------------------------------------------------------------------------------------------------------------------
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
    #----------------------------------------------------------------------------------------------------------------------------------------
    def update_edit_widgets(self):
        if not self.edit_mode or not self.tab_system.current_tab:
            return

        canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        selected_buttons = canvas.get_selected_buttons()
        self.button_selection_count = len(selected_buttons)
        self.edit_button_EF.title_label.setText(f'Button <span style="color: #494949; font-size: 11px;">({self.button_selection_count})</span>')

        widgets = self.edit_widgets

        if not selected_buttons:
            self._clear_edit_widgets_optimized(widgets)
            return
        
        self._update_edit_widgets_with_selection_optimized(widgets, selected_buttons, canvas)

    def update_edit_widgets_delayed(self):
        if self.edit_mode:
            # CRITICAL FIX: Clear pending widget changes when selection changes
            if hasattr(self, 'widget_update_timer'):
                self.widget_update_timer.stop()
            if hasattr(self, 'pending_widget_changes'):
                self.pending_widget_changes.clear()
                
            # Schedule update
            if hasattr(self, '_update_timer'):
                self._update_timer.stop()
            else:
                self._update_timer = QTimer()
                self._update_timer.setSingleShot(True)
                self._update_timer.timeout.connect(self.update_edit_widgets)
            self._update_timer.start(100)

    def _update_widget_container_style_optimized(self, widgets, enabled=True):
        """Update the visual styling of widget containers based on enabled state"""
        if enabled:
            # Style for enabled state (when buttons are selected)
            color = '#222222'
            self.edit_button_EF.content_widget.setStyleSheet(f'''
                QWidget {{border:1px solid #617e1c;background-color:{UT.rgba_value(color,1.2,1)};}}
                QLabel {{border:None;background-color:transparent;}}
                QLineEdit {{border:1px solid #333333;background-color:#222222; margin: 0px; padding: 3px;}}''')
            
            # Individual widget styling
            for widget_name in ['rename_widget', 'opacity_widget', 'transform_widget', 'radius_widget']:
                if widget_name in widgets:
                    widgets[widget_name].setEnabled(True)
                    #widgets[widget_name].setStyleSheet('border: 0px solid #444444;')
            
            if 'color_widget' in widgets:
                widgets['color_widget'].setStyleSheet('border: 0px solid #444444; background-color: #222222;')
        else:
            # Style for disabled state (when no buttons are selected)
            color = '#222222'
            self.edit_button_EF.content_widget.setStyleSheet(f'''
                QWidget {{border:0px solid #eeeeee;background-color:{UT.rgba_value(color,1.2,1)};}}
                QLabel {{border:None;background-color:transparent;}}
                QLineEdit {{border:1px solid #333333;background-color:#222222; margin: 0px; padding: 3px;}}''')
            
            # Disable all widget groups except thumbnail directory
            widget_groups = ['rename_widget', 'opacity_widget', 'transform_widget', 'radius_widget', 'color_widget']
            for widget_name in widget_groups:
                if widget_name in widgets:
                    widgets[widget_name].setEnabled(False)
    
    def _clear_edit_widgets_optimized(self, widgets):
        """Efficiently clear edit widgets when no selection"""
        self.is_updating_widgets = True
        
        # Block signals and batch clear all widgets
        widget_updates = [
            ('rename_edit', ''),
            ('transform_w_edit', 0),
            ('transform_h_edit', 0),
            ('top_left_radius', 0),
            ('top_right_radius', 0),
            ('bottom_right_radius', 0),
            ('bottom_left_radius', 0),
            ('opacity_slider', 100)
        ]
        
        for widget_name, value in widget_updates:
            widget = widgets[widget_name]
            widget.blockSignals(True)
            if hasattr(widget, 'setText'):
                widget.setText(str(value))
            elif hasattr(widget, 'setValue'):
                widget.setValue(value)
            elif hasattr(widget, 'updateLabel'):
                widget.updateLabel(value)
            widget.blockSignals(False)
        
        # Handle checkboxes
        for checkbox_name in ['transform_prop', 'single_radius']:
            widgets[checkbox_name].blockSignals(True)
            widgets[checkbox_name].setChecked(False)
            widgets[checkbox_name].blockSignals(False)
        
        # Update container style
        self._update_widget_container_style_optimized(widgets, enabled=False)
        self.is_updating_widgets = False
    
    def _update_edit_widgets_with_selection_optimized(self, widgets, selected_buttons, canvas):
        """Enhanced widget update that properly sets current dimensions"""
        # Use last selected button or first in list as reference
        button = (canvas.last_selected_button if canvas.last_selected_button and canvas.last_selected_button.is_selected 
                else selected_buttons[-1])
        
        self.is_updating_widgets = True
        
        # IMPORTANT: Store current dimensions (not initial/original values)
        # These will be used as reference for the next edit operation
        widgets['transform_w_edit'].setProperty('current_value', button.width)
        widgets['transform_h_edit'].setProperty('current_value', button.height)
        
        # Batch update with signal blocking
        widget_updates = [
            ('rename_edit', button.label),
            ('opacity_slider', int(button.opacity * 100)),
            ('transform_w_edit', button.width),
            ('transform_h_edit', button.height),
            ('top_left_radius', button.radius[0]),
            ('top_right_radius', button.radius[1]),
            ('bottom_right_radius', button.radius[2]),
            ('bottom_left_radius', button.radius[3])
        ]
        
        for widget_name, value in widget_updates:
            widget = widgets[widget_name]
            widget.blockSignals(True)
            if hasattr(widget, 'setText'):
                widget.setText(str(value))
            elif hasattr(widget, 'setValue'):
                widget.setValue(value)
            elif hasattr(widget, 'updateLabel'):  # For custom sliders
                widget.setValue(value)
                widget.updateLabel(value)
            widget.blockSignals(False)
        
        # Handle single radius state
        is_single_radius = len(set(button.radius)) == 1
        widgets['single_radius'].blockSignals(True)
        widgets['single_radius'].setChecked(is_single_radius)
        widgets['single_radius'].blockSignals(False)
        
        # Apply single radius styling if needed
        self._handle_single_radius_toggle(is_single_radius)
        
        # Update color picker with button's color
        if 'color_picker' in widgets:
            widgets['color_picker'].blockSignals(True)
            # Convert string color (like '#FF0000') to QColor
            if isinstance(button.color, str) and button.color.startswith('#'):
                qcolor = QtGui.QColor(button.color)
                widgets['color_picker'].current_color = qcolor
                widgets['color_picker'].update_all_from_color()
            widgets['color_picker'].blockSignals(False)
        
        # Update container style
        self._update_widget_container_style_optimized(widgets, enabled=True)
        self.is_updating_widgets = False
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [Event Handlers]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Only update buttons if this is not from our manual resize operation
        # This prevents double updates during manual resizing
        if not self.resize_state.get('active', False):
            self.update_buttons_for_current_tab()

    def mousePressEvent(self, event):
        # Check for Ctrl+Alt+Left Click first 
        if event.button() == QtCore.Qt.LeftButton and event.modifiers() & QtCore.Qt.ControlModifier and event.modifiers() & QtCore.Qt.AltModifier:
            # Ctrl+Alt+Left Click to toggle fade away mode
            self.fade_manager.toggle_fade_away()
            event.accept()
            return
        
        # Check for Ctrl+Shift+Left Click first
        if event.button() == QtCore.Qt.LeftButton and event.modifiers() & QtCore.Qt.ControlModifier and event.modifiers() & QtCore.Qt.ShiftModifier:
            # Ctrl+Shift+Left Click to toggle minimal mode
            self.fade_manager.toggle_minimal_mode()
            event.accept()
            return
        
        
        if event.button() == QtCore.Qt.LeftButton and event.modifiers() & QtCore.Qt.ControlModifier:
            # Ctrl+Left Click to toggle edit mode
            self.activateWindow()
            self.raise_()
            self.toggle_edit_mode()
            event.accept()
            return
            
        if event.button() == QtCore.Qt.LeftButton:
            # Enhanced interactive widget detection using hierarchy traversal
            interactive_widget = self._is_interactive_widget(event.pos())
            
            if interactive_widget:
                # For interactive widgets, pass the event to the default handler
                # and explicitly prevent window dragging by NOT setting oldPos
                super().mousePressEvent(event)
                return
            
            # Check for resize operation first (before setting oldPos)
            resize_edge = self.get_resize_edge(event.pos())
            
            if resize_edge:
                # Handle resize operation
                self.begin_resize(resize_edge, event.globalPos())
            else:
                # Only set oldPos for window dragging if we're not on an interactive widget
                # and not resizing
                self.oldPos = event.globalPos()
                
            if self.edit_mode == False:
                UT.maya_main_window().activateWindow()

    def mouseMoveEvent(self, event):
        if event.buttons() == QtCore.Qt.LeftButton:
            # If we're already in resize mode, skip widget checks for performance
            if not self.resize_state['active']:
                # Re-check interactive widget status during move
                interactive_widget = self._is_interactive_widget(event.pos())
                
                if interactive_widget:
                    # Let the interactive widget handle the move
                    super().mouseMoveEvent(event)
                    return

            # Handle resize/move operations
            if self.resize_state['active'] and self.resize_state['edge']:
                # Process resize with throttling
                self.process_resize(event.globalPos())
            elif not self.resize_state['active'] and hasattr(self, 'oldPos'):
                # Handle window dragging only if we have oldPos set
                # Temporarily disable updates during window movement
                self.setUpdatesEnabled(False)
                
                delta = event.globalPos() - self.oldPos
                self.move(self.x() + delta.x(), self.y() + delta.y())
                self.oldPos = event.globalPos()
                
                # Re-enable updates
                self.setUpdatesEnabled(True)
        else:
            # Only update cursor when not dragging
            self._update_cursor_for_position(event.pos())

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            if self.resize_state['active']:
                # End resize operation
                self.end_resize()
            
            # Always clean up oldPos reference to prevent accidental dragging
            if hasattr(self, 'oldPos'):
                delattr(self, 'oldPos')  # Remove the attribute entirely
            
            # Check if this is an interactive widget for proper event handling
            interactive_widget = self._is_interactive_widget(event.pos())
            
            if interactive_widget:
                # Let the interactive widget handle the release
                super().mouseReleaseEvent(event)
                return
            
            # Update cursor position after release
            current_pos = self.mapFromGlobal(QtGui.QCursor.pos())
            QtCore.QTimer.singleShot(10, lambda: self._update_cursor_for_position(current_pos))
    
    def _is_interactive_widget(self, pos):
        """Method to detect if position is over an interactive widget"""
        # Get the widget at the event position
        target_widget = self.childAt(pos)
        
        if not target_widget:
            return False
        
        # Walk up the widget hierarchy to check for interactive widgets
        current_widget = target_widget
        
        while current_widget and current_widget != self:
            # Check for custom interactive widget types
            if isinstance(current_widget, (PC.PickerCanvas, PB.PickerButton, 
                                        TS.TabButton, CB.CustomRadioButton)):
                return True
            
            # Check for standard Qt interactive widget types
            if isinstance(current_widget, (QtWidgets.QPushButton, QtWidgets.QSlider, 
                                            QtWidgets.QLineEdit, QtWidgets.QComboBox,
                                            QtWidgets.QScrollBar, QtWidgets.QCheckBox)):
                return True

            '''if current_widget is self.canvas_tab_frame_scroll_area:
                return True
            # Check for scroll areas and their contents
            if isinstance(current_widget, (QtWidgets.QScrollArea, QtWidgets.QAbstractScrollArea)):
                return True'''
                
            # Move up to parent widget
            current_widget = current_widget.parent()
        
        return False
    #----------------------------------------------------------------------------------------------------------------------------------------
    def dragEnterEvent(self, event):
        # Check if the drag contains URLs (files)
        if event.mimeData().hasUrls():
            # Get the first URL and check if it's a JSON file
            file_path = event.mimeData().urls()[0].toLocalFile()
            if file_path.lower().endswith('.json'):
                event.acceptProposedAction()
                # Add visual feedback for drag
                self.drag_highlight_active = True
                self.util_frame.setStyleSheet(f'''QFrame {{border: 1px solid #3096bb;}}''')
                return
        event.ignore()
    
    def dragLeaveEvent(self, event):
        # Reset visual feedback
        if self.drag_highlight_active:
            self.drag_highlight_active = False
            self.util_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray;}}''')
        event.accept()
    
    def dragMoveEvent(self, event):
        # Continue accepting the drag if it's a JSON file
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile()
            if file_path.lower().endswith('.json'):
                event.acceptProposedAction()
                return
        event.ignore()
    
    def dropEvent(self, event):
        # Reset visual feedback
        if self.drag_highlight_active:
            self.drag_highlight_active = False
            self.util_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray;}}''')
        
        # Process the dropped file
        if event.mimeData().hasUrls():
            file_path = event.mimeData().urls()[0].toLocalFile()
            if file_path.lower().endswith('.json'):
                try:
                    # Load the picker data using the same logic as in load_picker
                    from . import picker_io
                    from . import data_management as DM
                    
                    # Load the picker data
                    picker_io.load_picker_data(file_path)
                    
                    # Force reload data from defaultObjectSet
                    DM.PickerDataManager.reload_data_from_maya()
                    
                    # Clear existing tabs first
                    self.tab_system.clear_all_tabs()
                    
                    # Refresh the UI to show the loaded data
                    self.tab_system.setup_tabs()
                    
                    # Switch to the first tab if available
                    if self.tab_system.tabs:
                        first_tab = next(iter(self.tab_system.tabs))
                        self.tab_system.switch_tab(first_tab)
                        # Update the canvas for this tab
                        self.update_canvas_for_tab(first_tab)
                    
                    # Create buttons for all tabs
                    QtCore.QTimer.singleShot(10, self.create_buttons)
                    
                    # Force UI update
                    self.update()
                    
                    cmds.inViewMessage(amg=f"Picker data successfully imported from {os.path.basename(file_path)}", pos='midCenter', fade=True)
                except Exception as e:
                    QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load picker data: {str(e)}")
                    print(f"Error loading picker data: {str(e)}")
                
                event.acceptProposedAction()
                return
        event.ignore()
    #----------------------------------------------------------------------------------------------------------------------------------------
    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.MouseButtonDblClick and obj == self.main_frame:
            # Reset window to original size when double-clicked
            if self.edit_mode:
                new_width = 350 + self.edit_scroll_area.width()
                self.resize(new_width, 450)
                self.update_buttons_for_current_tab()
            else:
                self.resize(350, 450)
                self.update_buttons_for_current_tab()
                UT.maya_main_window()
            return True
        
        # Continue with other event handling
        return super().eventFilter(obj, event)
    
    def enterEvent(self, event):
        # FIXED: Only update cursor if not currently dragging
        if not (QtWidgets.QApplication.mouseButtons() & QtCore.Qt.LeftButton):
            # Use a small delay to ensure proper cursor state
            pos = event.pos()  # Capture position before event is deleted
            QtCore.QTimer.singleShot(1, lambda: self._update_cursor_for_position(pos))

    def leaveEvent(self, event):
        # FIXED: Always reset cursor when leaving (unless actively resizing)
        try:
            if not self.resize_state['active']:
                self.unsetCursor()
        except:
            pass
    
    def closeEvent(self, event):
        """Enhanced close event with comprehensive cleanup"""
        #print("AnimPickerWindow closeEvent triggered")
        
        # Exit rename mode for any button in rename mode in the active canvas
        if hasattr(self, 'tab_system') and self.tab_system and self.tab_system.current_tab:
            canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            for button in getattr(canvas, 'buttons', []):
                if getattr(button, 'rename_mode', False):
                    button.commit_rename()
                    button.exit_rename_mode()

        self.edit_mode = False
        
        # Stop any pending timers immediately
        timer_list = ['batch_update_timer', 'widget_update_timer', 'resize_timer']
        for timer_name in timer_list:
            if hasattr(self, timer_name):
                timer = getattr(self, timer_name)
                if timer and hasattr(timer, 'stop'):
                    timer.stop()
        
        # Process any pending updates before cleanup
        try:
            if hasattr(self, 'pending_button_updates') and self.pending_button_updates:
                self._process_batch_updates()
            
            if hasattr(self, 'pending_widget_changes') and self.pending_widget_changes:
                self._apply_widget_changes()
        except Exception as e:
            print(f"Error processing pending updates during close: {e}")
        
        

        if hasattr(self, 'update_checker_timer') and self.update_checker_timer:
            self.update_checker_timer.stop()
            self.update_checker_timer.deleteLater()
            self.update_checker_timer = None
        # Flush database operations
        try:
            DM.PickerDataManager.flush_pending_saves()
        except Exception as e:
            print(f"Error flushing database: {e}")
        
        # Perform comprehensive cleanup
        self.cleanup_resources()
        
        # Stop periodic cleanup
        self.end_periodic_cleanup()
        
        # Call parent close event
        super().closeEvent(event)
    #----------------------------------------------------------------------------------------------------------------------------------------
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

    def _update_cursor_for_position(self, pos):
        """Centralized cursor update logic"""
        # Check if the mouse is over the canvas frame
        canvas_frame_geo = self.canvas_frame.geometry()
        if canvas_frame_geo.contains(pos):
            # Always use default cursor over canvas
            if self.cursor().shape() != QtCore.Qt.ArrowCursor:
                self.unsetCursor()
            return
        
        # Check if we're in resize range
        if self.is_in_resize_range(pos):
            self.update_cursor(pos)
        else:
            # Ensure cursor is reset when not over resize edges
            if self.cursor().shape() != QtCore.Qt.ArrowCursor:
                self.unsetCursor()

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
    
    def finalize_resize(self):
            # This method is called when resize timer times out or when mouse is released
            # Update button positions and layout only once at the end of resize
            if self.tab_system.current_tab:
                # Clear any cached data
                self.resize_state['cached_canvas'] = None
                self.resize_state['cached_buttons'] = None
                
                # Do a full update of all buttons
                self.update_buttons_for_current_tab()
            
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
        
        # FIXED: Force cursor update after a brief delay
        QtCore.QTimer.singleShot(50, self._post_resize_cursor_update)

    def _post_resize_cursor_update(self):
        """Update cursor after resize operation completes"""
        current_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        self._update_cursor_for_position(current_pos)
    #----------------------------------------------------------------------------------------------------------------------------------------
    # CLEANUP
    #----------------------------------------------------------------------------------------------------------------------------------------
    def cleanup_resources(self):
        """Comprehensive cleanup of all resources to prevent memory leaks"""
        #print("Starting AnimPickerWindow cleanup...")
        
        # 1. Stop and cleanup all timers
        timer_list = [
            'batch_update_timer', 'widget_update_timer', 'resize_timer', 
            '_update_timer', 'expand_animation', 'collapse_animation'
        ]
        
        for timer_name in timer_list:
            if hasattr(self, timer_name):
                timer = getattr(self, timer_name)
                if timer:
                    if hasattr(timer, 'stop'):
                        timer.stop()
                    if hasattr(timer, 'timeout'):
                        try:
                            timer.timeout.disconnect()
                        except:
                            pass
                    if hasattr(timer, 'finished'):
                        try:
                            timer.finished.disconnect()
                        except:
                            pass
                    # Delete timer object
                    setattr(self, timer_name, None)
        
        # 2. Remove all event filters
        event_filter_objects = [
            self.resize_handle, self.main_frame, self.util_frame, self
        ]
        
        for obj in event_filter_objects:
            if obj:
                try:
                    obj.removeEventFilter(self)
                except:
                    pass
        
        # 3. Clear all cached data and pending operations
        cache_attributes = [
            'pending_button_updates', 'pending_widget_changes', 
            'available_ids', 'resize_state'
        ]
        
        for attr_name in cache_attributes:
            if hasattr(self, attr_name):
                attr = getattr(self, attr_name)
                if isinstance(attr, (set, dict, list)):
                    attr.clear()
                elif isinstance(attr, dict) and 'cached_canvas' in attr:
                    attr['cached_canvas'] = None
                    attr['cached_buttons'] = None
        
        # 4. Disconnect all canvas signals
        if hasattr(self, 'tab_system') and self.tab_system:
            for tab_name, tab_data in self.tab_system.tabs.items():
                if 'canvas' in tab_data:
                    canvas = tab_data['canvas']
                    try:
                        canvas.button_selection_changed.disconnect()
                        canvas.clicked.disconnect()
                    except:
                        pass
                    
                    # Clear canvas button references
                    if hasattr(canvas, 'buttons'):
                        for button in canvas.buttons:
                            button.setParent(None)
                        canvas.buttons.clear()
        
        # 5. Clear widget references that might hold onto large objects
        widget_refs = ['edit_widgets', 'tool_buttons']
        for widget_ref in widget_refs:
            if hasattr(self, widget_ref):
                setattr(self, widget_ref, None)
        
        # 6. Clear fade manager resources
        if hasattr(self, 'fade_manager') and self.fade_manager:
            # If fade manager has cleanup method
            if hasattr(self.fade_manager, 'cleanup'):
                self.fade_manager.cleanup()
            self.fade_manager = None
        
        # 7. Force garbage collection
        import gc
        gc.collect()
        
        #print("AnimPickerWindow cleanup completed")

    def _cleanup_button(self, button):
        """Properly cleanup a single button and its resources"""
        try:
            # Disconnect button signals
            if hasattr(button, 'changed'):
                button.changed.disconnect()
            
            # Clear pixmap cache
            if hasattr(button, 'text_pixmap'):
                button.text_pixmap = None
            if hasattr(button, 'pose_pixmap'):
                button.pose_pixmap = None
            if hasattr(button, 'thumbnail_pixmap'):
                button.thumbnail_pixmap = None
            
            # Remove from parent and delete
            button.setParent(None)
            button.deleteLater()
            
        except Exception as e:
            print(f"Error cleaning up button {getattr(button, 'unique_id', 'unknown')}: {e}")

    def __del__(self):
        """Destructor to ensure cleanup even if closeEvent wasn't called"""
        try:
            self.cleanup_resources()
        except:
            pass  # Ignore errors during destruction

    def periodic_cleanup(self):
        """Periodic cleanup to prevent memory accumulation during long sessions"""
        
        # Clear completed pending updates (older than 5 seconds)
        current_time = QtCore.QTime.currentTime().msecsSinceStartOfDay()
        
        # Clear old cached data in resize state
        if hasattr(self, 'resize_state'):
            if not self.resize_state.get('active', False):
                self.resize_state['cached_canvas'] = None
                self.resize_state['cached_buttons'] = None
        
        # Clear any orphaned button update requests
        if hasattr(self, 'pending_button_updates'):
            if self.tab_system and self.tab_system.current_tab:
                canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
                valid_ids = {button.unique_id for button in canvas.buttons}
                self.pending_button_updates &= valid_ids  # Keep only valid IDs
        
        # Force Qt to clean up deleted objects
        QtCore.QCoreApplication.processEvents()
        
        # Optional: Force garbage collection every 10 calls
        if not hasattr(self, '_cleanup_counter'):
            self._cleanup_counter = 0
        self._cleanup_counter += 1
        
        if self._cleanup_counter % 10 == 0:
            import gc
            gc.collect()

    def setup_periodic_cleanup(self):
        """Set up a timer for periodic cleanup (call this in __init__)"""
        self.cleanup_timer = QTimer()
        self.cleanup_timer.timeout.connect(self.periodic_cleanup)
        self.cleanup_timer.start(30000)  # Run every 30 seconds
    
    def end_periodic_cleanup(self):
        """Stop the periodic cleanup timer"""
        if hasattr(self, 'cleanup_timer') and self.cleanup_timer:
            self.cleanup_timer.stop()
            self.cleanup_timer = None

            
