import os
from functools import partial
import sys
from pathlib import Path
import bpy

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QShortcut

from . import custom_button as CB
from . import custom_slider as CS
from . import utils as UT
from . import expandable_frame as EF
from . import tool_functions as TF
from . import tab_system as TS
from . import data_management as DM
from . import picker_canvas as PC
from . import picker_button as PB
from . import custom_line_edit as CLE
from . import button_edit_widgets as BEW
from . fade_away_logic import FadeAway
from . import custom_color_picker as CCP
from .update_ui import UpdateWidget

# Get version from __init__
import ft_anim_picker
anim_picker_version = ft_anim_picker.src.__version__
anim_picker_version = f" (v{anim_picker_version})"

class BlenderAnimPickerWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(BlenderAnimPickerWindow, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_AlwaysShowToolTips, True)
        self.setStyleSheet('''QWidget {background-color: rgba(40, 40, 40, 0.5); border-radius: 4px;}''')
        
        # Track our visibility state for centralized management
        self.should_be_visible = True
        self.stored_geometry = None

        # Enable drag and drop for the window
        self.setAcceptDrops(True)
        self.drag_highlight_active = False
        
        self.edit_mode = False
        self.fade_manager = FadeAway(self)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.fade_manager.show_frame_context_menu)
        
        # Resize optimization variables with advanced caching
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
    
        self.setup_ui()
        self.setup_layout()
        self.setup_tab_system()
        self.setup_connections()
        
        # Resize tracking variables
        self.resizing = False
        self.resize_edge = None
        self.resize_start_pos = None
        self.resize_start_geometry = None
        self.resize_border_width = 4  # Width of the resize border area

        # Resize timer for final update after resizing stops
        self.resize_timer = QtCore.QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.on_resize_timer_timeout)

        self.available_ids = {}
        
        # Create buttons for the active tab
        self.create_buttons()
        
        # Enable mouse tracking for hover detection
        self.setMouseTracking(True)
        
        self.oldPos = self.pos()

        self.batch_update_active = False
        self.pending_button_updates = set()
        self.update_widgets_timer = None
        self.edit_widgets_update_enabled = True

        # Define widgets that should be affected by minimal mode
        minimal_affected_widgets = [
            {'widget': self.util_frame, 'hide_in_minimal': False},
            {'widget': self.main_frame, 'exclude': [self.canvas_frame]}, # Keep canvas frame visible
            {'widget': self.canvas_frame, 'exclude': [self.canvas_frame_layout]}, # Keep the canvas content visible
            {'widget': self.tools_EF, 'hide_in_minimal': False},
            {'widget': self.canvas_tab_frame, 'hide_in_minimal': True},
            {'widget': self.namespace_dropdown, 'hide_in_minimal': True},
            {'widget': self.close_button, 'hide_in_minimal': True},
        ]

        # Set the affected widgets in the fade manager
        self.fade_manager.set_minimal_affected_widgets(minimal_affected_widgets)
        
        # Add batch update system variables (similar to Maya version)
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
        
        # Edit widget update control
        self.is_updating_widgets = False
        self.populate_namespace_dropdown()

        # Setup update checker timer (every 5 seconds)
        self.update_checker_timer = QTimer()
        self.update_checker_timer.timeout.connect(self.update_anim_picker_checker)
        self.update_checker_timer.start(3600000)  # 3600000 ms = 1 hour

        # Setup periodic cleanup
        self.setup_periodic_cleanup()
    
        # Install cleanup on app exit
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self.cleanup_resources)
            
        # Initial check for updates
        self.update_anim_picker_checker()

    def setup_ui(self):
        # Allow window to be resized
        self.setMinimumSize(200, 200)
        self.setGeometry(800, 280, 350, 450)

        # Set up margins and spacing
        def set_margin_space(layout,margin,space):
            layout.setContentsMargins(margin,margin,margin,margin)
            layout.setSpacing(space)
        
        self.main_layout = QtWidgets.QVBoxLayout(self)
        set_margin_space(self.main_layout,5,5)

        # Main frame
        self.main_frame = QtWidgets.QFrame()
        self.main_frame.setStyleSheet('''QFrame {border: 0px solid gray; border-radius: 4px; background-color: rgba(36, 36, 36, .6);}''')
        self.main_frame_layout = QtWidgets.QVBoxLayout(self.main_frame)
        set_margin_space(self.main_frame_layout,8,8)

        self.main_frame_util_layout = QtWidgets.QHBoxLayout()
        self.main_frame_body_layout = QtWidgets.QHBoxLayout()
        self.main_frame_tool_layout = QtWidgets.QHBoxLayout()

        #-----------------------------------------------------------------------------------------------------------------------------------
        # Utility frame (top bar)
        #-----------------------------------------------------------------------------------------------------------------------------------
        self.util_frame = QtWidgets.QFrame()
        self.util_frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.util_frame.setFixedHeight(24)
        self.util_frame.setStyleSheet('''QFrame {border: 0px solid gray; border-radius: 4px; background-color: rgba(40, 40, 40, .8); padding: 0px;}''')
        self.util_frame_layout = QtWidgets.QHBoxLayout(self.util_frame)
        set_margin_space(self.util_frame_layout,2,2)
        self.util_frame_layout.setAlignment(QtCore.Qt.AlignLeft)
        #-----------------------------------------------------------------------------------------------------------------------------------
        # Icon
        self.icon_image = QtWidgets.QLabel()
        package_dir = Path(__file__).parent
        icon_path = package_dir / 'ft_picker_icons' / 'ftap_logo_64.png'
        if icon_path.exists():
            icon_pixmap = QtGui.QPixmap(str(icon_path))
            self.icon_image.setPixmap(icon_pixmap)
            self.icon_image.setScaledContents(True)
            self.icon_image.setFixedSize(14, 14)
        #-----------------------------------------------------------------------------------------------------------------------------------
        # Util Buttons
        #-----------------------------------------------------------------------------------------------------------------------------------
        #File Util
        file_util = CB.CustomButton(text='File', height=20, width=40, radius=3,color='#385c73',alpha=0,textColor='#aaaaaa', ContextMenu=True, onlyContext= True,
                                    cmColor='#333333',tooltip='File Utilities', flat=True)
        file_util.addMenuLabel("File Utilities",position=(0,0))
        file_util.addToMenu("Store Picker", self.store_picker, icon=UT.get_icon('save.png'), position=(1,0))
        file_util.addToMenu("Load Picker", self.load_picker, icon=UT.get_icon('load.png'), position=(2,0))
        #-----------------------------------------------------------------------------------------------------------------------------------
        #Edit Util
        edit_util = CB.CustomButton(text='Edit', height=20, width=40, radius=3,color='#385c73',alpha=0,textColor='#aaaaaa', ContextMenu=True, onlyContext= True,
                                    cmColor='#333333',tooltip='Edit Utilities', flat=True)
        edit_util.addMenuLabel("Edit Utilities",position=(0,0))
        edit_util.addToMenu("Edit Mode", self.toggle_edit_mode, icon=UT.get_icon('edit.png'), position=(1,0))
        edit_util.addToMenu("Toggle Minimal Mode", self.fade_manager.toggle_minimal_mode, icon=UT.get_icon('visible.png'), position=(2,0))
        edit_util.addToMenu("Toggle Fade Away", self.fade_manager.toggle_fade_away, icon=UT.get_icon('visible.png'), position=(3,0))
        #-----------------------------------------------------------------------------------------------------------------------------------
        #Info Util
        self.info_util = CB.CustomButton(text='Info', height=20, width=40, radius=3,color='#385c73',alpha=0,textColor='#aaaaaa', ContextMenu=True, onlyContext= True,
                                    cmColor='#333333',tooltip='Info Utilities', flat=True, notification=True)
        self.info_util.addMenuLabel(f"Anim Picker{anim_picker_version}",position=(0,0))
        self.info_util.addToMenu(f"Manual", self.info, icon=UT.get_icon('manual.png'), position=(1,0))
        self.info_util.addToMenu(f"Update", self.update_anim_picker, icon=UT.get_icon('update.png'), position=(2,0))
        #-----------------------------------------------------------------------------------------------------------------------------------
        self.update_anim_picker_button = CB.CustomButton(text='Update Available',icon=UT.get_icon('update.png',size=14,opacity=.7), height=16, radius=8,color='#555555',
        text_size=10,tooltip='Update Anim Picker', textColor='#eeeeee')
        self.update_anim_picker_button.clicked.connect(self.update_anim_picker)
        #-----------------------------------------------------------------------------------------------------------------------------------
        # Close button
        self.close_button = CB.CustomButton(icon=UT.get_icon('close_01.png',size=12,opacity=.7), height=16, width=16, radius=3,color='#c0091a',tooltip='Close')
        self.close_button.clicked.connect(self.close)
        #-----------------------------------------------------------------------------------------------------------------------------------
        # Add widgets to utility frame
        self.util_frame_layout.addSpacing(4)
        self.util_frame_layout.addWidget(self.icon_image)
        self.util_frame_layout.addWidget(file_util)
        self.util_frame_layout.addWidget(edit_util)
        self.util_frame_layout.addWidget(self.info_util)
        self.util_frame_layout.addStretch(1)
        self.util_frame_layout.addWidget(self.update_anim_picker_button)
        self.util_frame_layout.addSpacing(4)
        self.update_anim_picker_button.setVisible(False)
        self.util_frame_layout.addWidget(self.close_button)
        self.util_frame_layout.addSpacing(2)
        #-----------------------------------------------------------------------------------------------------------------------------------
        # Canvas frame
        #-----------------------------------------------------------------------------------------------------------------------------------
        self.canvas_frame = QtWidgets.QFrame()
        self.canvas_frame.setStyleSheet('''QFrame {border: 0px solid gray; border-radius: 4px; background-color: rgba(40, 40, 40, .8);}''')
        self.canvas_frame_layout = QtWidgets.QVBoxLayout(self.canvas_frame)
        set_margin_space(self.canvas_frame_layout,4,4)
        self.canvas_frame_column_1 = QtWidgets.QHBoxLayout()
        self.canvas_frame_layout.addLayout(self.canvas_frame_column_1)
        #-----------------------------------------------------------------------------------------------------------------------------------
        #-Canvas Tab Frame
        self.canvas_tab_frame = QtWidgets.QFrame()
        self.canvas_tab_frame.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        self.canvas_tab_frame.setFixedHeight(24)
        self.canvas_tab_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray; border-radius: 12px; background-color: rgba(55, 55, 55, .4);}}''')
        
        # Canvas Tab Frame Scroll Area
        self.canvas_tab_frame_scroll_area = CS.HorizontalScrollArea() 
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
        
        #-Canvas Tab Frame Layout
        self.canvas_tab_frame_layout = QtWidgets.QHBoxLayout(self.canvas_tab_frame)
        set_margin_space(self.canvas_tab_frame_layout,4,2)
        
        #-Add Tab button
        self.add_tab_button = CB.CustomButton(icon=UT.get_icon('add.png',size=10,opacity=.9), height=16, width=16, radius=8,color='#91cb08',tooltip='Add New Tab')
        self.canvas_tab_frame_layout.addWidget(self.add_tab_button)
        
        # Create a stacked widget to hold picker canvases
        self.canvas_stack = QtWidgets.QStackedWidget()
        self.canvas_stack.setStyleSheet(f'''QWidget {{border: 0px solid #223d4f; border-radius: 4px; background-color: transparent;}}''')
        self.canvas_frame_layout.addWidget(self.canvas_stack)
        #-----------------------------------------------------------------------------------------------------------------------------------
        #-Name Space Dropdown
        self.namespace_dropdown = QtWidgets.QComboBox(self)
        self.namespace_dropdown.setFixedHeight(24)
        self.namespace_dropdown.setMinimumWidth(40)
        self.namespace_dropdown.setMaximumWidth(120)
        
        self.namespace_dropdown.setStyleSheet(f'''QComboBox{{background-color: {UT.rgba_value('#222222', 1,.9)}; color: #dddddd;border: 1px solid #2f2f2f; padding: 2px;}}
                                    QComboBox:hover {{background-color: {UT.rgba_value('#222222', .8,1)};}}
                                    QComboBox::drop-down {{border: 0px;}}
                                    QComboBox::down-arrow {{background-color: transparent;}} 
                                    QToolTip {{background-color: #222222; color: #eeeeee;border: 1px solid rgba(255,255,255,.2); padding: 4px; border-radius: 0px;}} ''')
        self.namespace_dropdown.setToolTip('Select Namespace')
        self.namespace_dropdown.addItems(['None'])
        #-----------------------------------------------------------------------------------------------------------------------------------
        self.canvas_frame_column_1.addWidget(self.canvas_tab_frame_scroll_area)
        #self.canvas_frame_column_1.addStretch()
        self.canvas_frame_column_1.addWidget(self.namespace_dropdown)
        #-----------------------------------------------------------------------------------------------------------------------------------
        #-Edit Frame
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        efw = 200 #edit fixed width
        self.edit_row = QtWidgets.QVBoxLayout()
        self.edit_frame = QtWidgets.QFrame()
        self.edit_frame.setStyleSheet('QFrame {background-color: rgba(40, 40, 40, .8); border: 0px solid #333333;}')
        self.edit_frame.setFixedWidth(efw - 10)
        
        # Create a scroll area
        self.edit_scroll_area = QtWidgets.QScrollArea()
        self.edit_scroll_area.setWidgetResizable(True)
        self.edit_scroll_area.setFixedWidth(efw)  # Set a fixed width for the scroll area
        self.edit_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.edit_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
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

        #-----------------------------------------------------------------------------------------------------------------------------------
        #-EDIT LAYOUT ------------------->
        widget_color = "#1e1e1e"
        label_color = "#666666"

        self.edit_layout = QtWidgets.QVBoxLayout(self.edit_frame)
        self.edit_layout.setAlignment(QtCore.Qt.AlignTop|QtCore.Qt.AlignCenter)
        set_margin_space(self.edit_layout,6,6)
        #-Edit Label
        self.edit_label = QtWidgets.QLabel("Picker Editor")
        self.edit_label.setAlignment(QtCore.Qt.AlignCenter)        
        self.edit_label.setStyleSheet('QLabel {color: #dddddd; background-color: transparent; font-size: 12px;}')
        #self.edit_layout.addWidget(self.edit_label)

        self.toggle_edit_mode_button = CB.CustomButton(text='Exit Edit Mode', height=24, width=efw, radius=4,color='#5e7b19', tooltip='Apply changes')
        self.toggle_edit_mode_button.clicked.connect(self.toggle_edit_mode)

        self.edit_scroll_area.setVisible(self.edit_mode)
        self.toggle_edit_mode_button.setVisible(self.edit_mode)

        self.edit_row.addWidget(self.edit_scroll_area)
        self.edit_row.addWidget(self.toggle_edit_mode_button)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
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
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.edit_layout.addWidget(self.edit_button_EF)
        self.edit_layout.addWidget(self.edit_canvas_EF)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        
        #-----------------------------------------------------------------------------------------------------------------------------------
        #-Tool Frame
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #Tool Drawer
        self.tools_EF = EF.ExpandableFrame(title='<span style="color: #777777; font-size: 11px;"> Animation Tools</span>', color='#282828',alpha=.8, border=1, border_color='#333333',margin=2) 
        self.tools_EF.toggle_expand()
        self.tool_buttons = TF.animation_tool_layout()
        self.tools_EF.addLayout(self.tool_buttons.layout)
        #------------------------------------------------------------------------------------------------------------------------------------------------------

    def setup_layout(self):
        # Add frames to main layout
        self.main_layout.addWidget(self.main_frame)
        
        # Add content frame to main frame
        self.main_frame_util_layout.addWidget(self.util_frame)
        self.main_frame_body_layout.addWidget(self.canvas_frame)
        self.main_frame_body_layout.addLayout(self.edit_row)
        self.main_frame_tool_layout.addWidget(self.tools_EF)

        self.main_frame_layout.addLayout(self.main_frame_util_layout)
        self.main_frame_layout.addLayout(self.main_frame_body_layout)
        self.main_frame_layout.addLayout(self.main_frame_tool_layout)
        
    def setup_connections(self):
        # Connect close button
        self.close_button.clicked.connect(self.close)
        self.main_frame.installEventFilter(self)
        self.main_frame.setMouseTracking(True)

        self.add_image.clicked.connect(self.select_image_for_current_tab)
        self.remove_image.clicked.connect(self.remove_image_from_current_tab)
        self.image_opacity_slider.valueChanged.connect(self.update_image_opacity)
        self.add_picker_button.clicked.connect(self.add_new_picker_button)
        
        self.image_scale_factor.valueChanged.connect(self.update_image_scale)
        self.namespace_dropdown.currentTextChanged.connect(self.on_namespace_changed)
        if hasattr(self, 'tab_system') and self.tab_system.current_tab:
            current_canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            current_canvas.clicked.connect(self.clear_line_edit_focus)
            current_canvas.button_selection_changed.connect(self.update_edit_widgets_delayed)
        
        self.toggle_axes.toggled.connect(self.toggle_axes_visibility)
        self.toggle_dots.toggled.connect(self.toggle_dots_visibility)
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

        # Install global event filter for hover-based Tab key handling
        self.installEventFilter(self)
        

        
        # Enable key event handling even when window doesn't have focus
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        
        # Track Tab key state to prevent multiple triggers
        self.tab_key_pressed = False
        
        # Keep the original Tab shortcut for when window has focus
        self.tab_key_pressed = False

        self.setup_scene_update_timer()
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
    def connect_canvas_signals(self, canvas):
        """ENHANCED signal connection with proper cleanup"""
        # Disconnect ALL existing connections first
        try:
            canvas.button_selection_changed.disconnect()
            canvas.clicked.disconnect()
        except:
            pass
        
        # Clear any existing button connections
        for button in canvas.buttons:
            try:
                button.changed.disconnect()
            except:
                pass
        
        # Re-connect with fresh connections
        canvas.button_selection_changed.connect(self.update_edit_widgets_delayed)
        canvas.clicked.connect(self.clear_line_edit_focus)
        
        # Connect button signals
        for button in canvas.buttons:
            button.changed.connect(self.on_button_changed) 

    def info(self):
        # Opens link to Manual
        import webbrowser
        webbrowser.open('https://munorr.com/tools/ft-anim-picker/')
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
            self.setMinimumSize(400, 200)
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
            self.setMinimumSize(200, 200)
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
    def _is_task_switcher_active(self):
        """Check if Windows task switcher is currently active"""
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                
                # Get the foreground window
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if not hwnd:
                    return False
                
                # Get window class name
                class_buffer = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetClassNameW(hwnd, class_buffer, 256)
                class_name = class_buffer.value
                
                # Task switcher class names
                task_switcher_classes = [
                    "MultitaskingViewFrame",      # Windows 10+ Task View
                    "XamlExplorerHostIslandWindow", # Alt+Tab
                    "TaskSwitcherWnd",            # Legacy Alt+Tab
                    "TaskSwitcherOverlayWnd"      # Another variant
                ]
                
                return any(tc in class_name for tc in task_switcher_classes)
                
            except Exception:
                return False
        
        # For other platforms, return False
        return False

    def _ensure_window_visible(self):
        """Ensure window is visible - show if hidden (called by centralized manager)"""
        if not self.should_be_visible:
            self.should_be_visible = True
            #print(f"Showing window {id(self)}")
            
            # Restore geometry if we stored it
            if self.stored_geometry:
                self.setGeometry(self.stored_geometry)
                self.stored_geometry = None
            
            # Show the window
            if not self.isVisible():
                self.show()
                self.raise_()
                self.activateWindow()

    def _ensure_window_hidden(self):
        """Ensure window is hidden when not needed (called by centralized manager)"""
        if self.should_be_visible:
            self.should_be_visible = False
            #print(f"Hiding window {id(self)}")
            
            # Store current geometry before hiding
            if self.isVisible():
                self.stored_geometry = self.geometry()
                self.hide()

    def _is_blender_window_active(self):
        """Check if any Blender window is currently active using the same logic as utils.py"""
        system = sys.platform
        
        if system == "win32":
            return self._is_blender_active_windows()
        elif system == "darwin":
            return self._is_blender_active_macos()
        elif system.startswith("linux"):
            return self._is_blender_active_linux()
        else:
            return True  # Default to assuming Blender is active on unknown platforms

    def _is_blender_active_windows(self):
        """Windows: Check if active window belongs to our Blender process OR is a child of our picker"""
        try:
            import ctypes
            from ctypes import wintypes
            
            current_pid = os.getpid()
            
            # Get the foreground window
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return False
            
            # Get process ID of the foreground window
            process_id = wintypes.DWORD()
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
            
            # If the active window belongs to our process (Blender), then check what type of window it is
            if process_id.value == current_pid:
                # Get window class name
                class_buffer = ctypes.create_unicode_buffer(256)
                ctypes.windll.user32.GetClassNameW(hwnd, class_buffer, 256)
                class_name = class_buffer.value
                
                # Check if it's a Blender window OR a Qt widget (our picker and its children)
                if class_name == "GHOST_WindowClass":  # Blender window
                    return True
                elif class_name in ["Qt660QWindowIcon", "Qt660QWindowOwnDCIcon", "Qt5QWindowIcon", "Qt5QWindowOwnDCIcon"]:  # Qt windows (our picker)
                    # This is likely our picker or a child dialog - let _is_picker_or_child_active handle it
                    return False
            
            return False
            
        except Exception as e:
            print(f"Error checking Windows Blender state: {e}")
            return False

    def _is_blender_active_macos(self):
        """macOS: Check if Blender application is frontmost OR picker children are active"""
        try:
            import subprocess
            
            # First check Qt application windows (our picker and children)
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                active_window = app.activeWindow()
                if active_window:
                    # Check if it's our picker or a child
                    parent = active_window
                    while parent:
                        if parent == self:
                            return False  # Let _is_picker_or_child_active handle this
                        parent = parent.parent()
            
            # Then check if Blender itself is frontmost
            applescript = '''
            tell application "System Events"
                set frontApp to first application process whose frontmost is true
                set frontAppName to name of frontApp
                if frontAppName contains "Blender" then
                    return true
                else
                    return false
                end if
            end tell
            '''
            
            result = subprocess.run(
                ['osascript', '-e', applescript],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                return "true" in result.stdout.strip().lower()
            
            return False
            
        except Exception as e:
            print(f"Error checking macOS Blender state: {e}")
            return False

    def _is_blender_active_linux(self):
        """Linux: Check if active window belongs to our Blender process OR is our picker child"""
        try:
            import subprocess
            current_pid = os.getpid()
            
            # Try xdotool first
            if UT._command_exists('xdotool'):
                # Get active window ID
                result = subprocess.run(
                    ['xdotool', 'getactivewindow'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                
                if result.returncode == 0:
                    window_id = result.stdout.strip()
                    
                    # Get PID of active window
                    pid_result = subprocess.run(
                        ['xdotool', 'getwindowpid', window_id],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    
                    if pid_result.returncode == 0:
                        try:
                            window_pid = int(pid_result.stdout.strip())
                            # If active window belongs to our process
                            if window_pid == current_pid:
                                # Get window class to determine if it's Blender or Qt
                                class_result = subprocess.run(
                                    ['xdotool', 'getwindowclassname', window_id],
                                    capture_output=True,
                                    text=True,
                                    timeout=2
                                )
                                
                                if class_result.returncode == 0:
                                    window_class = class_result.stdout.strip().lower()
                                    # If it's a Qt window, let _is_picker_or_child_active handle it
                                    if 'qt' in window_class or window_class in ['python', 'python3']:
                                        return False
                                    # Otherwise it's likely Blender
                                    return True
                                
                                # Fallback: assume it's Blender if we can't get class
                                return True
                        except ValueError:
                            pass
            
            # Fallback to wmctrl
            if UT._command_exists('wmctrl'):
                # Get active window info
                result = subprocess.run(
                    ['wmctrl', '-l', '-p'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                
                if result.returncode == 0:
                    # Get active window ID
                    active_result = subprocess.run(
                        ['xprop', '-root', '_NET_ACTIVE_WINDOW'],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    
                    if active_result.returncode == 0 and 'window id' in active_result.stdout:
                        active_id = active_result.stdout.split('#')[1].split()[0] if '#' in active_result.stdout else None
                        
                        if active_id:
                            # Check if this window belongs to our process
                            for line in result.stdout.strip().split('\n'):
                                if active_id.lower() in line.lower():
                                    parts = line.split()
                                    if len(parts) >= 3:
                                        try:
                                            window_pid = int(parts[2])
                                            if window_pid == current_pid:
                                                # Check window title to determine if it's Blender or picker
                                                window_title = ' '.join(parts[4:]) if len(parts) > 4 else ''
                                                if 'blender' in window_title.lower():
                                                    return True
                                                # If it contains Qt-related terms, let picker handler deal with it
                                                return False
                                        except (ValueError, IndexError):
                                            continue
            
            return False
            
        except Exception as e:
            print(f"Error checking Linux Blender state: {e}")
            return False
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [External Data Management]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def store_picker(self):
        """Enhanced store picker method with current tab vs all tabs option"""
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
                
                self.show_blender_message(message)
                
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
            self._load_picker_from_file(file_path)
            
    def _load_picker_from_file(self, file_path):
        """Load picker data from a file path"""
        try:
            from . import picker_io
            picker_io.load_picker_data(file_path)
            
            # CRITICAL FIX: Get the loaded data to determine which tabs were loaded
            loaded_data = DM.PickerDataManager.get_data()
            
            if not loaded_data['tabs']:
                QtWidgets.QMessageBox.warning(self, "Warning", "No valid tab data found in the file.")
                return False
            
            # CRITICAL FIX: Clear existing tabs first to avoid conflicts
            # Store current tab system state
            #old_tabs = list(self.tab_system.tabs.keys()) if hasattr(self.tab_system, 'tabs') else []
            
            '''# Clear existing tabs
            for tab_name in old_tabs:
                if tab_name in self.tab_system.tabs:
                    # Remove canvas from stack
                    canvas = self.tab_system.tabs[tab_name]['canvas']
                    index = self.canvas_stack.indexOf(canvas)
                    if index != -1:
                        self.canvas_stack.removeWidget(canvas)
                        canvas.deleteLater()'''

            DM.PickerDataManager.reload_data_from_blender()

            self.tab_system.clear_all_tabs()

            self.tab_system.setup_tabs()
            
            first_tab_name = next(iter(loaded_data['tabs']))
            #print(f"Switching to first loaded tab: {first_tab_name}")
            # Switch to the first tab if available
            if self.tab_system.tabs:
                first_tab = next(iter(self.tab_system.tabs))
                self.tab_system.switch_tab(first_tab)
                # Update the canvas for this tab
                self.update_canvas_for_tab(first_tab)

            self.create_buttons_for_tab(first_tab)
            self.update()
            
            # Show success message
            self.show_blender_message(f"Picker data successfully imported from {os.path.basename(file_path)}")
            return True
            
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
            print(f"Error loading picker data: {e}")
            return False

    def dragEnterEvent(self, event):
        """Handle drag enter events for picker data files"""
        if event.mimeData().hasUrls():
            # Check if any of the URLs are JSON files
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if self._is_valid_picker_file(file_path):
                    # Add visual feedback for drag
                    self.drag_highlight_active = True
                    self.util_frame.setStyleSheet(f'''QFrame {{border: 1px solid #3096bb;}}''')
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragLeaveEvent(self, event):
        # Reset visual feedback
        if self.drag_highlight_active:
            self.drag_highlight_active = False
            self.util_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray;}}''')
        event.accept()

    def dragMoveEvent(self, event):
        """Handle drag move events"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dropEvent(self, event):
        """Handle drop events for picker data files"""
        # Reset visual feedback
        if self.drag_highlight_active:
            self.drag_highlight_active = False
            self.util_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray;}}''')
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if self._is_valid_picker_file(file_path):
                    self._load_picker_from_file(file_path)
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def _is_valid_picker_file(self, file_path):
        """Check if the file is a valid picker data file"""
        if not os.path.isfile(file_path):
            return False
            
        # Get the file extension
        _, ext = os.path.splitext(file_path)
        if not ext:
            return False
            
        # Check if it's a JSON file
        if ext.lower() != '.json':
            return False
            
        # Basic validation of file content
        try:
            with open(file_path, 'r') as f:
                import json
                data = json.load(f)
                # Check for basic picker data structure
                return 'tabs' in data
        except:
            return False
        
        return True

    def show_blender_message(message, type='INFO'):
        """Show a message in Blender's UI without needing operator context"""
        import bpy
        
        def show_message():
            # Print to console (always works)
            print(f"[{type}] {message}")
            
            # Try to show in Blender's info area
            try:
                with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                    # Get the main window
                    if bpy.context.window_manager.windows:
                        window = bpy.context.window_manager.windows[0]
                        
                        # Look for info area
                        for area in window.screen.areas:
                            if area.type == 'INFO':
                                # Add report to info area
                                with bpy.context.temp_override(window=window, area=area):
                                    # This adds the message to Blender's report system
                                    if type == 'ERROR':
                                        bpy.context.window_manager.popup_menu(
                                            lambda self, context: self.layout.label(text=message, icon='ERROR'),
                                            title="Error",
                                            icon='ERROR'
                                        )
                                    elif type == 'WARNING':
                                        bpy.context.window_manager.popup_menu(
                                            lambda self, context: self.layout.label(text=message, icon='ERROR'),
                                            title="Warning", 
                                            icon='ERROR'
                                        )
                                    break
            except Exception as e:
                print(f"Could not show UI message: {e}")
            
            return None  # Unregister timer
        
        bpy.app.timers.register(show_message, first_interval=0.01)
    #-----------------------------------------------------------------------------------------------------------------------------------
    def setup_scene_update_timer(self):
        """Setup timer to periodically check for scene changes"""
        self.scene_update_timer = QtCore.QTimer(self)
        self.scene_update_timer.timeout.connect(self.check_scene_for_updates)
        self.scene_update_timer.start(2000)  # Check every 2 seconds

    def check_scene_for_updates(self):
        """Check if rigs in scene have changed and update dropdown if needed"""
        import bpy
        
        # Get current rig names in scene
        current_rigs = []
        for obj in bpy.context.scene.objects:
            if obj.type == 'ARMATURE':
                current_rigs.append(obj.name)
        current_rigs.sort()
        
        # Get dropdown items (excluding 'None')
        dropdown_items = []
        for i in range(1, self.namespace_dropdown.count()):  # Skip index 0 which is 'None'
            dropdown_items.append(self.namespace_dropdown.itemText(i))
        
        # Update dropdown if rigs have changed
        if current_rigs != dropdown_items:
            #print("Scene rigs changed, updating namespace dropdown")
            self.update_namespace_dropdown()

    def on_namespace_changed(self, namespace_text):
        """Handle namespace dropdown change"""
        #print(f"Namespace changed to: {namespace_text}")
        
    def populate_namespace_dropdown(self):
        """Populate namespace dropdown with rigs (armature objects) in the scene"""
        import bpy
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
            # Clear existing items
            self.namespace_dropdown.clear()
            
            # Add default "None" option
            self.namespace_dropdown.addItem('None')
            
            # Get all armature objects in the scene
            rig_names = []
            for obj in bpy.context.scene.objects:
                if obj.type == 'ARMATURE':
                    rig_names.append(obj.name)
            
            # Sort rig names alphabetically
            rig_names.sort()
            
            # Add rig names to dropdown
            for rig_name in rig_names:
                self.namespace_dropdown.addItem(rig_name)
            
            #print(f"Found {len(rig_names)} rigs in scene: {rig_names}")

    def update_namespace_dropdown(self):
        """Update the namespace dropdown when scene changes"""
        # Store current selection
        current_text = self.namespace_dropdown.currentText()
        
        # Repopulate dropdown
        self.populate_namespace_dropdown()
        
        # Try to restore previous selection
        index = self.namespace_dropdown.findText(current_text)
        if index >= 0:
            self.namespace_dropdown.setCurrentIndex(index)
        else:
            # Default to None if previous selection no longer exists
            self.namespace_dropdown.setCurrentIndex(0)
    #-----------------------------------------------------------------------------------------------------------------------------------
    # Resize Helper Methods
    #-----------------------------------------------------------------------------------------------------------------------------------
    def get_resize_edge(self, pos):
        """Determine which edge of the main_frame the mouse is over"""
        frame_rect = self.main_frame.geometry()
        border = self.resize_border_width
        
        # Check if mouse is within the border area
        left_edge = pos.x() <= frame_rect.x() + border
        right_edge = pos.x() >= frame_rect.right() - border
        top_edge = pos.y() <= frame_rect.y() + border
        bottom_edge = pos.y() >= frame_rect.bottom() - border
        
        # Return edge combinations for corners and sides
        if top_edge and left_edge:
            return 'top-left'
        elif top_edge and right_edge:
            return 'top-right'
        elif bottom_edge and left_edge:
            return 'bottom-left'
        elif bottom_edge and right_edge:
            return 'bottom-right'
        elif top_edge:
            return 'top'
        elif bottom_edge:
            return 'bottom'
        elif left_edge:
            return 'left'
        elif right_edge:
            return 'right'
        
        return None

    def get_cursor_for_edge(self, edge):
        """Return appropriate cursor for resize edge"""
        cursors = {
            'top': QtCore.Qt.SizeVerCursor,
            'bottom': QtCore.Qt.SizeVerCursor,
            'left': QtCore.Qt.SizeHorCursor,
            'right': QtCore.Qt.SizeHorCursor,
            'top-left': QtCore.Qt.SizeFDiagCursor,
            'bottom-right': QtCore.Qt.SizeFDiagCursor,
            'top-right': QtCore.Qt.SizeBDiagCursor,
            'bottom-left': QtCore.Qt.SizeBDiagCursor,
        }
        return cursors.get(edge, QtCore.Qt.ArrowCursor)

    def perform_resize(self, edge, current_pos):
        """Perform the actual window resize based on mouse movement"""
        if not self.resize_start_pos or not self.resize_start_geometry:
            return
            
        delta = current_pos - self.resize_start_pos
        start_geo = self.resize_start_geometry
        min_size = self.minimumSize()
        
        new_x = start_geo.x()
        new_y = start_geo.y()
        new_width = start_geo.width()
        new_height = start_geo.height()
        
        # Handle horizontal resizing
        if 'left' in edge:
            new_width = max(min_size.width(), start_geo.width() - delta.x())
            new_x = start_geo.x() + (start_geo.width() - new_width)
        elif 'right' in edge:
            new_width = max(min_size.width(), start_geo.width() + delta.x())
            
        # Handle vertical resizing
        if 'top' in edge:
            new_height = max(min_size.height(), start_geo.height() - delta.y())
            new_y = start_geo.y() + (start_geo.height() - new_height)
        elif 'bottom' in edge:
            new_height = max(min_size.height(), start_geo.height() + delta.y())
            
        self.setGeometry(new_x, new_y, new_width, new_height)
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
        
        # Select button properly (deselect other buttons first)
        canvas.clear_selection()
        new_button.is_selected = True
        new_button.selected.emit(new_button, True)
        
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
        
    def create_buttons_for_tab(self, tab_name):
        """Create buttons specifically for the given tab"""
        if tab_name not in self.tab_system.tabs:
            return
            
        self.initialize_tab_data(tab_name)
        canvas = self.tab_system.tabs[tab_name]['canvas']
        
        # Clear existing buttons first
        for button in canvas.buttons[:]:
            button.setParent(None)
            button.deleteLater()
        canvas.buttons.clear()
        
        # Get button data from PickerDataManager for this specific tab
        tab_data = DM.PickerDataManager.get_tab_data(tab_name)
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
                    button.thumbnail_pixmap = QtGui.QPixmap(button.thumbnail_path)
                else:
                    button.thumbnail_path = ''  # Reset if file doesn't exist
                    button.thumbnail_pixmap = None
            
            button.scene_position = QtCore.QPointF(*button_data["position"])
            button.update_tooltip()
            canvas.add_button(button)
            
            # Connect button signals
            button.changed.connect(self.on_button_changed)
        
        # Update button positions and refresh canvas
        canvas.update_button_positions()
        canvas.update()

    def on_button_changed(self, button):
        """Handle button change events - FIXED VERSION"""
        # CRITICAL: Check if batch mode is truly disabled before processing
        if getattr(self, 'batch_update_active', False):
            # If in batch mode, just add to pending updates
            self.pending_button_updates.add(button.unique_id)
            self.batch_update_timer.start(self.batch_update_delay)
        else:
            # Process immediately
            self._process_single_button_update(button)
        
        # Update edit widgets if needed
        if (self.edit_mode and hasattr(self, 'edit_widgets') and 
            self.tab_system.current_tab):
            canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            if button in canvas.get_selected_buttons():
                self.update_edit_widgets_delayed()

    def save_button_data_immediate(self, button):
        """Save button data immediately to database, bypassing all update systems"""
        current_tab = self.tab_system.current_tab
        if not current_tab:
            return
            
        self.initialize_tab_data(current_tab)
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        
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
        updated = False
        for i, existing_button in enumerate(tab_data['buttons']):
            if existing_button['id'] == button.unique_id:
                tab_data['buttons'][i] = button_data
                updated = True
                break
        
        if not updated:
            tab_data['buttons'].append(button_data)
        
        # Force immediate save
        DM.PickerDataManager.save_data(tab_data, force_immediate=True)
    
    def update_button_data(self, button, deleted=False):
        """Update button data - FIXED VERSION for proper deletion handling"""
        if not self.tab_system.current_tab:
            return
            
        current_tab = self.tab_system.current_tab
        
        if deleted:
            # Handle deletions immediately and synchronously
            self._process_button_deletion(button, current_tab)
        else:
            # For regular updates, process immediately if not in batch mode
            if not getattr(self, 'batch_update_active', False):
                self._process_single_button_update(button)
            else:
                # Add to batch for later processing
                self.pending_button_updates.add(button.unique_id)
                self.batch_update_timer.start(self.batch_update_delay)

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
            
            # ESSENTIAL: Direct database update (same pattern as set_custom_shape)
            if hasattr(self, 'tab_system') and self.tab_system.current_tab:
                current_tab = self.tab_system.current_tab
                tab_data = DM.PickerDataManager.get_tab_data(current_tab)
                
                # Default fields to update if none specified
                if fields_to_update is None:
                    # Update all fields
                    fields_to_update = ['position', 'width', 'height', 'radius', 'shape_type','label', 'color', 'opacity', 'assigned_objects', 'mode', 'script_data', 'pose_data', 'thumbnail_path','svg_path_data','svg_file_path','selectable']
                
                # Update specified fields for all affected buttons
                for button in buttons_to_update:
                    for i, existing_button in enumerate(tab_data['buttons']):
                        if existing_button['id'] == button.unique_id:
                            # Update only specified fields
                            for field in fields_to_update:
                                if field == 'position':
                                    tab_data['buttons'][i]['position'] = (button.scene_position.x(), button.scene_position.y())
                                elif field == 'width':
                                    tab_data['buttons'][i]['width'] = button.width
                                elif field == 'height':
                                    tab_data['buttons'][i]['height'] = button.height
                                elif field == 'radius':
                                    tab_data['buttons'][i]['radius'] = button.radius
                                elif field == 'shape_type':
                                    tab_data['buttons'][i]['shape_type'] = button.shape_type
                                elif field == 'svg_path_data':
                                    tab_data['buttons'][i]['svg_path_data'] = button.svg_path_data
                                elif field == 'svg_file_path':
                                    tab_data['buttons'][i]['svg_file_path'] = button.svg_file_path
                                elif field == 'label':
                                    tab_data['buttons'][i]['label'] = button.label
                                elif field == 'color':
                                    tab_data['buttons'][i]['color'] = button.color
                                elif field == 'opacity':
                                    tab_data['buttons'][i]['opacity'] = button.opacity
                                elif field == 'assigned_objects':
                                    tab_data['buttons'][i]['assigned_objects'] = getattr(button, 'assigned_objects', [])
                                elif field == 'mode':
                                    tab_data['buttons'][i]['mode'] = getattr(button, 'mode', 'select')
                                elif field == 'script_data':
                                    tab_data['buttons'][i]['script_data'] = getattr(button, 'script_data', {'code': '', 'type': 'python'})
                                elif field == 'pose_data':
                                    tab_data['buttons'][i]['pose_data'] = getattr(button, 'pose_data', {})
                                elif field == 'thumbnail_path':
                                    tab_data['buttons'][i]['thumbnail_path'] = getattr(button, 'thumbnail_path', '')
                                elif field == 'selectable':
                                    tab_data['buttons'][i]['selectable'] = getattr(button, 'selectable', True)
                            break
                
                # Single database update for all buttons
                DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                
                #print(f"Batch updated {len(buttons_to_update)} buttons in database (fields: {fields_to_update})")
            
            # Reconnect signals properly
            for button in buttons_to_update:
                # Reconnect to the main window's handler
                if hasattr(self, 'on_button_changed'):
                    button.changed.connect(self.on_button_changed)
                else:
                    # Fallback connection
                    button.changed.connect(self.update_button_data)
            
        except Exception as e:
            print(f"Error during batch update: {e}")
            
            # Emergency signal reconnection
            for button in buttons_to_update:
                try:
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
                DM.PickerDataManager.update_tab_data(current_tab, tab_data)
                #print(f"Applied {updates_applied} button updates to database")
        
        # Update button positions once
        canvas.update_button_positions()
        
        # Clear pending updates
        self.pending_button_updates.clear()
        
        #print("Batch update complete")
    
    def _process_button_deletion(self, button, current_tab):
        """Process button deletion immediately and update data manager"""
        self.initialize_tab_data(current_tab)
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        
        # Remove button from data
        original_count = len(tab_data['buttons'])
        tab_data['buttons'] = [b for b in tab_data['buttons'] if b['id'] != button.unique_id]
        new_count = len(tab_data['buttons'])
        
        # Update data manager
        DM.PickerDataManager.update_tab_data(current_tab, tab_data)
        
        # Add to available IDs for reuse
        if current_tab not in self.available_ids:
            self.available_ids[current_tab] = set()
        self.available_ids[current_tab].add(button.unique_id)

    def _process_single_button_update(self, button):
        """Process single button update immediately - ENHANCED VERSION for position updates"""
        current_tab = self.tab_system.current_tab
        if not current_tab:
            return
            
        self.initialize_tab_data(current_tab)
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        
        # Create comprehensive button data
        button_data = {
            "id": button.unique_id,
            "selectable": button.selectable,
            "label": button.label,
            "color": button.color,
            "opacity": button.opacity,
            "position": (button.scene_position.x(), button.scene_position.y()),  # CRITICAL: Always update position
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
        
        # CRITICAL FIX: Find and update existing button or add new one
        updated = False
        for i, existing_button in enumerate(tab_data['buttons']):
            if existing_button['id'] == button.unique_id:
                # CRITICAL: Update the existing button data completely
                tab_data['buttons'][i] = button_data
                updated = True
                #print(f"Updated existing button {button.unique_id} at position ({button_data['position'][0]:.2f}, {button_data['position'][1]:.2f})")
                break
        
        if not updated:
            # Add new button if not found
            tab_data['buttons'].append(button_data)
            #print(f"Added new button {button.unique_id} at position ({button_data['position'][0]:.2f}, {button_data['position'][1]:.2f})")
        
        # CRITICAL FIX: Force immediate database update
        DM.PickerDataManager.update_tab_data(current_tab, tab_data)
        
        # CRITICAL FIX: Also update button positions specifically
        button_positions = {button.unique_id: (button.scene_position.x(), button.scene_position.y())}
        DM.PickerDataManager.update_button_positions(current_tab, button_positions)

    def _process_immediate_button_update(self, button):
        """Process single button update immediately (for critical operations)"""
        current_tab = self.tab_system.current_tab
        self.initialize_tab_data(current_tab)
        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        
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

    def update_buttons_for_current_tab(self, force_update=False):
        """REPLACE existing method with optimized version"""
        if not self.tab_system.current_tab:
            return
        
        current_tab = self.tab_system.current_tab
        canvas = self.tab_system.tabs[current_tab]['canvas']
        
        # Skip update during active resize or batch operations unless forced
        if not force_update and (self.resize_state.get('active', False) or getattr(self, 'batch_update_active', False)):
            return
        
        # Batch position updates efficiently
        canvas.setUpdatesEnabled(False)
        try:
            canvas.update_button_positions()
            
            # Batch update button positions in data manager
            if canvas.buttons:
                button_positions = {
                    button.unique_id: (button.scene_position.x(), button.scene_position.y())
                    for button in canvas.buttons
                }
                DM.PickerDataManager.update_button_positions(current_tab, button_positions)
        
        finally:
            canvas.setUpdatesEnabled(True)
            canvas.update()
    
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
                'background_value': 18, # Default to 18% 
                'image_scale': 1.0
            }
        elif 'buttons' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['buttons'] = []
        elif 'background_value' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['background_value'] = 20  
        elif 'image_scale' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['image_scale'] = 1.0  
        elif 'image_opacity' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['image_opacity'] = 1.0  
        
        self.initialize_button_original_sizes()
        
    def setup_tab_system(self):
        # Connect add tab button to tab system
        self.add_tab_button.clicked.connect(self.on_add_tab_clicked)
        
        # Create the tab system
        self.tab_system = TS.TabSystem(self.canvas_tab_frame_layout, self.add_tab_button)
        self.tab_system.tab_switched.connect(self.on_tab_switched)
        self.tab_system.tab_renamed.connect(self.on_tab_renamed)
        self.tab_system.tab_deleted.connect(self.on_tab_deleted)
        self.tab_system.tab_reordered.connect(self.on_tab_reordered)
        
        # Set up tabs from saved data
        data = DM.PickerDataManager.get_data()
        if not data['tabs']:
            # If no tabs exist, create default tab
            self.tab_system.add_tab('Tab 1', switch=True)
            DM.PickerDataManager.add_tab('Tab 1')
        else:
            # Set up existing tabs
            for tab_name in data['tabs']:
                self.tab_system.add_tab(tab_name, switch=False)
            
            # Switch to first tab
            first_tab = next(iter(data['tabs']))
            self.tab_system.switch_tab(first_tab)
        
        self.tab_system.setup_tabs()
        
        if not self.tab_system.tabs:
            self.tab_system.add_tab("Tab 1")
            self.initialize_tab_data("Tab 1")
            DM.PickerDataManager.add_tab("Tab 1")
        
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
        
        # FIXED: Use the helper method to connect canvas signals
        self.connect_canvas_signals(current_canvas)
        
        # Update image button state if available
        if hasattr(self, 'remove_image'):
            has_image = self.tab_system.tabs[tab_name].get('image_path') is not None
            self.remove_image.setEnabled(has_image)
        
        # Create buttons explicitly for the current tab
        QtCore.QTimer.singleShot(10, self.create_buttons)
        # Then update buttons for proper positioning
        #self.update_buttons_for_current_tab(force_update=True)
        
        # Update namespace dropdown for the new tab
        if hasattr(self, 'update_namespace_dropdown'):
            self.update_namespace_dropdown()
            
    def on_add_tab_clicked(self):
        # Let the tab system handle creating the new tab
        if hasattr(self, 'tab_system'):
            self.tab_system.add_new_tab()
            
    def focus_window(self):
        #Focus window
        self.activateWindow()

    def on_tab_renamed(self, old_name, new_name):
        # Update the tab data in our local structure
        if old_name in self.tab_system.tabs:
            # Update the canvas for the renamed tab
            self.update_canvas_for_tab(new_name)
            
            # Update any UI elements that reference the tab name
            if self.tab_system.current_tab == new_name:
                # If this is the current tab, update the UI
                self.update_buttons_for_current_tab(force_update=True) 
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
    # [Picker Button Edit Funtions]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def rename_selected_buttons(self, new_label):
        """Optimized rename with batching"""
        def rename_operation(button, label):
            button.label = label
            button.text_pixmap = None  # Force text regeneration
            button.update()
        
        self._batch_button_operation(rename_operation, new_label)

    def change_opacity_for_selected_buttons(self, value):
        """Optimized opacity change with batching"""
        # Capture selected buttons BEFORE the operation
        canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        selected_buttons = canvas.get_selected_buttons()
        selected_button_ids = [button.unique_id for button in selected_buttons] if selected_buttons else []
        
        def opacity_operation(button, opacity_value):
            button.opacity = opacity_value / 100.0
            button.update()
        
        # Save undo state with the captured button IDs
        DM.PickerDataManager.save_undo_state("Opacity Change", selected_button_ids)
        self._batch_button_operation(opacity_operation, value)

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
            #def size_operation(button, w_scale, h_scale):
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
            
            # Apply to all selected buttons using batch operation
            #self._batch_button_operation(size_operation, width_scale, height_scale)
            self.batch_update_buttons_to_database(selected_buttons)
        else:
            # Fallback: direct assignment if no valid reference
            for button in selected_buttons:
                button.width = max(1, round(target_width))
                button.height = max(1, round(target_height))
                button.update()

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
                    self.update_button_data(button)
                button.update()
                self.pending_button_updates.add(button.unique_id)
            
            # Update canvas and process changes
            canvas.update_button_positions()
            self.batch_update_buttons_to_database(selected_buttons)
            self.update_edit_widgets_delayed()
    
    def initialize_button_original_sizes(self):
        """Initialize original_size property for all buttons that don't have it"""
        if not self.tab_system.current_tab:
            return
            
        canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        
        for button in canvas.buttons:
            if not hasattr(button, 'original_size'):
                button.original_size = QtCore.QSize(button.width, button.height)

    def set_radius_for_selected_buttons(self, tl, tr, br, bl):
        """Optimized radius change with batching"""
        def radius_operation(button, tl, tr, br, bl):
            button.set_radius(tl, tr, br, bl)
            button.update()
        
        self._batch_button_operation(radius_operation, tl, tr, br, bl)

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
        """REPLACE the existing setup_edit_widgets method with this optimized version"""
        widgets = BEW.create_button_edit_widgets(self)
        
        # Add widgets to layout (keep existing layout code)
        self.edit_value_layout.addWidget(widgets['rename_widget'])
        self.edit_value_layout.addWidget(widgets['transform_widget'])
        self.edit_value_layout.addWidget(widgets['radius_widget'])
        self.edit_value_layout.addWidget(widgets['opacity_widget'])
        self.edit_value_layout.addWidget(widgets['color_picker'])
        self.edit_value_layout.addWidget(widgets['placement_widget'])
        self.edit_value_layout.addWidget(widgets['thumbnail_dir_widget'])
        

        # REPLACE signal connections with these throttled versions:
        widgets['rename_edit'].textChanged.connect(self._queue_rename_change)
        widgets['rename_edit'].returnPressed.connect(self._immediate_rename_apply)
        widgets['opacity_slider'].valueChanged.connect(self._queue_opacity_change)
        widgets['transform_w_edit'].valueChanged.connect(self._queue_transform_change)
        widgets['transform_h_edit'].valueChanged.connect(self._queue_transform_change)

        # Enable apply-to-all for transform controls
        widgets['transform_w_edit'].setApplyToAllMode(True)
        widgets['transform_h_edit'].setApplyToAllMode(True)
        
        # Connect the new signals
        widgets['transform_w_edit'].applyToAllRequested.connect(self._apply_width_to_all)
        widgets['transform_h_edit'].applyToAllRequested.connect(self._apply_height_to_all)
        
        # Enhanced radius functionality with queuing
        widgets['top_left_radius'].valueChanged.connect(self._queue_radius_change)
        widgets['top_right_radius'].valueChanged.connect(self._queue_radius_change)
        widgets['bottom_right_radius'].valueChanged.connect(self._queue_radius_change)
        widgets['bottom_left_radius'].valueChanged.connect(self._queue_radius_change)
        widgets['single_radius'].toggled.connect(self._handle_single_radius_toggle)
        
        # Color buttons with throttled updates
        for i, color_button in enumerate(widgets['color_buttons']):
            color = widgets['color_buttons'][i].palette().button().color().name()
            color_button.clicked.connect(partial(self._queue_color_change, color))

        
        self.edit_widgets = widgets

    def _queue_rename_change(self):
        """Queue rename changes for batch processing"""
        if not self.is_updating_widgets:
            self.pending_widget_changes['rename'] = self.edit_widgets['rename_edit'].text()
            self.widget_update_timer.start(self.widget_update_delay)

    def _immediate_rename_apply(self):
        """Apply rename immediately on Return key press"""
        if not self.is_updating_widgets:
            self.rename_selected_buttons(self.edit_widgets['rename_edit'].text())

    def _queue_opacity_change(self, value):
        """Queue opacity changes for batch processing"""
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
                
                # Get the button's current aspect ratio for proportional scaling
                if self.tab_system.current_tab:
                    canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
                    selected_buttons = canvas.get_selected_buttons()
                    
                    if selected_buttons:
                        # Use the reference button's current dimensions to calculate aspect ratio
                        reference_button = (canvas.last_selected_button 
                                        if canvas.last_selected_button and canvas.last_selected_button.is_selected 
                                        else selected_buttons[-1])
                        
                        current_width = reference_button.width
                        current_height = reference_button.height
                        aspect_ratio = current_width / current_height if current_height > 0 else 1.0
                        
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
        """Queue radius changes for batch processing"""
        if not self.is_updating_widgets:
            widgets = self.edit_widgets
            
            # Handle single radius mode
            if widgets['single_radius'].isChecked():
                sender = self.sender()
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
        """FIXED: Queue color changes for batch processing with validation"""
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
                    continue  # Skip individual button processing for transform
                
                # Handle other change types normally
                for button in selected_buttons:
                    if change_type == 'rename':
                        button.label = value
                        button.text_pixmap = None  # Force text regeneration
                    elif change_type == 'opacity':
                        button.opacity = value / 100.0
                    elif change_type == 'radius':
                        tl, tr, br, bl = value
                        button.radius = [tl, tr, br, bl]
                    elif change_type == 'color':
                        # Validate the color format
                        if isinstance(value, str) and value.startswith('#') and len(value) == 7:
                            button.color = value
                        else:
                            print(f"Invalid color format received: {value}")
                            continue
                    
                    # Mark button as changed
                    button.update()
                    self.pending_button_updates.add(button.unique_id)
            
            # Update button positions after size/transform changes
            canvas.update_button_positions()
        
        finally:
            # Re-enable updates and refresh canvas
            canvas.setUpdatesEnabled(True)
            self.setUpdatesEnabled(True)
            canvas.update()
        
        # Clear pending changes
        self.pending_widget_changes.clear()
        
        # Process database updates
        self.batch_update_buttons_to_database(canvas.get_selected_buttons())
        #self._process_batch_updates()

    def _process_batch_updates(self):
        """Simplified batch processing like Maya version"""
        if not self.pending_button_updates or not self.tab_system.current_tab:
            return
            
        current_tab = self.tab_system.current_tab
        canvas = self.tab_system.tabs[current_tab]['canvas']
        
        # Collect all button data for batch update
        buttons_to_update = []
        for button in canvas.buttons:
            if button.unique_id in self.pending_button_updates:
                button_data = self._create_button_data(button)
                buttons_to_update.append(button_data)
        
        # Single database update for all buttons
        if buttons_to_update:
            DM.PickerDataManager.batch_update_buttons(current_tab, buttons_to_update)
        
        self.pending_button_updates.clear()

    def _create_button_data(self, button):
        """Helper method to create button data dict"""
        return {
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
    #----------------------------------------------------------------------------------------------------------------------------------------
    def update_edit_widgets_delayed(self):
        """Optimized delayed update with better debouncing"""
        if not self.edit_mode:
            return
        
        # Clear any pending widget changes to prevent property inheritance
        self.pending_widget_changes.clear()
        
        # Use shorter delay for better responsiveness but prevent spam
        if hasattr(self, '_edit_update_timer'):
            self._edit_update_timer.stop()
        else:
            self._edit_update_timer = QTimer()
            self._edit_update_timer.setSingleShot(True)
            self._edit_update_timer.timeout.connect(self.update_edit_widgets)
        
        self._edit_update_timer.start(50)  # 50ms delay

    def update_edit_widgets(self):
        """Highly optimized edit widgets update"""
        if not self.edit_mode or not self.tab_system.current_tab or not hasattr(self, 'edit_widgets'):
            return

        canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        selected_buttons = canvas.get_selected_buttons()
        self.button_selection_count = len(selected_buttons)
        
        # Update title efficiently
        title_text = f'Button <span style="color: #494949; font-size: 11px;">({self.button_selection_count})</span>'
        self.edit_button_EF.title_label.setText(title_text)

        widgets = self.edit_widgets

        if not selected_buttons:
            self._clear_edit_widgets_optimized(widgets)
            return

        self._update_edit_widgets_with_selection_optimized(widgets, selected_buttons, canvas)

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
                widget.setValue(value)
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

    def _update_widget_container_style_optimized(self, widgets, enabled=True):
        """Efficiently update widget container styles"""
        color = '#222222'
        
        if enabled:
            container_style = f'''
                QWidget {{border:1px solid #617e1c;background-color:{UT.rgba_value(color,1.2,1)};}}
                QLabel {{border:None;background-color:transparent;}}
                QLineEdit {{border:1px solid #333333;background-color:#222222; margin: 0px; padding: 3px;}}'''
            
            # Enable all widget groups
            widget_groups = ['rename_widget', 'opacity_widget', 'transform_widget', 'radius_widget', 'color_widget']
            for widget_name in widget_groups:
                if widget_name in widgets:
                    widgets[widget_name].setEnabled(True)
                    #widgets[widget_name].setStyleSheet('border: 0px solid #444444;')
            
            # Special styling for color widget
            if 'color_widget' in widgets:
                widgets['color_widget'].setStyleSheet('border: 0px solid #444444; background-color: #222222;')
        else:
            container_style = f'''
                QWidget {{border:0px solid #eeeeee;background-color:{UT.rgba_value(color,1.2,1)};}}
                QLabel {{border:None;background-color:transparent;}}
                QLineEdit {{border:1px solid #333333;background-color:#222222; margin: 0px; padding: 3px;}}'''
            
            # Disable all widget groups except thumbnail directory
            widget_groups = ['rename_widget', 'opacity_widget', 'transform_widget', 'radius_widget', 'color_widget']
            for widget_name in widget_groups:
                if widget_name in widgets:
                    widgets[widget_name].setEnabled(False)
        
        # Apply container style
        self.edit_button_EF.content_widget.setStyleSheet(container_style)
        
        # Keep thumbnail directory always enabled
        if 'thumbnail_dir_widget' in widgets:
            widgets['thumbnail_dir_widget'].setEnabled(True)
    
    def _perform_delayed_widget_update(self):
        """Perform the actual widget update"""
        if self.edit_mode and hasattr(self, 'edit_widgets'):
            self.update_edit_widgets()

    #----------------------------------------------------------------------------------------------------------------------------------------
    def _delayed_transform_update(self):
        """Delayed transform update for better performance"""
        if not self.is_updating_widgets:
            self.set_size_for_selected_buttons(
                self.edit_widgets['transform_w_edit'].value(),
                self.edit_widgets['transform_h_edit'].value()
            )

    def on_rename_edit_return_pressed(self):
        if not self.is_updating_widgets and not self.batch_update_active:
            self.rename_selected_buttons(self.edit_widgets['rename_edit'].text())

    def on_opacity_slider_value_changed(self, value):
        if not self.is_updating_widgets and not self.batch_update_active:
            self.change_opacity_for_selected_buttons(value)

    def on_transform_edit_value_changed(self):
        if not self.is_updating_widgets and not self.batch_update_active:
            self.set_size_for_selected_buttons(
                self.edit_widgets['transform_w_edit'].value(),
                self.edit_widgets['transform_h_edit'].value()
            )

    def on_color_button_clicked(self, color):
        if not self.is_updating_widgets and not self.batch_update_active:
            self.change_color_for_selected_buttons(color)
    
    def on_color_picker_changed(self, color):
        if not self.is_updating_widgets and not self.batch_update_active:
            self.change_color_for_selected_buttons(color)
            self._process_batch_updates()
    #----------------------------------------------------------------------------------------------------------------------------------------
    
    #-----------------------------------------------------------------------------------------------------------------------------------
    # Events
    #-----------------------------------------------------------------------------------------------------------------------------------
    def enterEvent(self, event):
        """Ensure mouse tracking is active when entering the window"""
        self.setMouseTracking(True)
        # Force update of child widgets' mouse tracking
        for child in self.findChildren(QtWidgets.QWidget):
            child.setMouseTracking(True)
        #if not self.hasFocus():
        #    self.activateWindow()
        #    self.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Reset cursor and hide tooltips when leaving the window"""
        if not self.resizing:
            self.setCursor(QtCore.Qt.ArrowCursor)
        #QtWidgets.QToolTip.hideText()
        super().leaveEvent(event)

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
        
        # Check for Ctrl+Left Click first
        if event.button() == QtCore.Qt.LeftButton and event.modifiers() & QtCore.Qt.ControlModifier:
            # Ctrl+Left Click to toggle edit mode
            self.activateWindow()
            self.raise_()
            self.toggle_edit_mode()
            event.accept()
            return
        
        # Regular left-click handling
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
                self.resizing = True
                self.resize_edge = resize_edge
                self.resize_start_pos = event.globalPos()
                self.resize_start_geometry = self.geometry()
                self.setCursor(self.get_cursor_for_edge(resize_edge))
            else:
                # Only set oldPos for window dragging if we're not on an interactive widget
                # and not resizing
                self.oldPos = event.globalPos()
            
            if self.edit_mode == False:
                UT.blender_main_window()

    def mouseMoveEvent(self, event):
        # Handle resize operation with highest priority
        if self.resizing and event.buttons() == QtCore.Qt.LeftButton:
            self.perform_resize(self.resize_edge, event.globalPos())
            return

        # If we're dragging with left button, check what we're dragging
        if event.buttons() == QtCore.Qt.LeftButton:
            # Check if the original press was on an interactive widget
            target_widget = self.childAt(event.pos())
            interactive_widget = False
            current_widget = target_widget
            
            # Walk up the widget hierarchy
            while current_widget and current_widget != self:
                if isinstance(current_widget, (PC.PickerCanvas, PB.PickerButton, TS.TabButton, CB.CustomRadioButton)):
                    interactive_widget = True
                    break
                
                if isinstance(current_widget, (QtWidgets.QPushButton, QtWidgets.QSlider, 
                                            QtWidgets.QLineEdit, QtWidgets.QComboBox,
                                            QtWidgets.QScrollBar, QtWidgets.QCheckBox)):
                    interactive_widget = True
                    break
                
                current_widget = current_widget.parent()
            
            if interactive_widget:
                # Let the interactive widget handle the move
                super().mouseMoveEvent(event)
                return
            
            # Handle window dragging only if we have a valid oldPos and we're not on an interactive widget
            if hasattr(self, 'oldPos') and self.oldPos is not None:
                delta = QtCore.QPoint(event.globalPos() - self.oldPos)
                self.move(self.x() + delta.x(), self.y() + delta.y())
                self.oldPos = event.globalPos()
                return
        
        # Update cursor for resize edges when not resizing or dragging
        if not self.resizing and not (event.buttons() == QtCore.Qt.LeftButton):
            resize_edge = self.get_resize_edge(event.pos())
            if resize_edge:
                self.setCursor(self.get_cursor_for_edge(resize_edge))
            else:
                self.setCursor(QtCore.Qt.ArrowCursor)
        
        # Pass the event to the parent for any other processing
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        # Handle the end of resize operation first
        if event.button() == QtCore.Qt.LeftButton and self.resizing:
            self.resizing = False
            self.resize_edge = None
            self.resize_start_pos = None
            self.resize_start_geometry = None
            self.setCursor(QtCore.Qt.ArrowCursor)
            event.accept()
            return
        
        # Always clean up oldPos reference to prevent accidental dragging
        if hasattr(self, 'oldPos'):
            self.oldPos = None  # Set to None instead of deleting
            
        # Check if this is an interactive widget
        target_widget = self.childAt(event.pos())
        interactive_widget = False
        current_widget = target_widget
        
        while current_widget and current_widget != self:
            if isinstance(current_widget, (PC.PickerCanvas, PB.PickerButton, TS.TabButton, CB.CustomRadioButton)):
                interactive_widget = True
                break
            
            if isinstance(current_widget, (QtWidgets.QPushButton, QtWidgets.QSlider, 
                                        QtWidgets.QLineEdit, QtWidgets.QComboBox,
                                        QtWidgets.QScrollBar, QtWidgets.QCheckBox)):
                interactive_widget = True
                break
            
            current_widget = current_widget.parent()
        
        if interactive_widget:
            # Let the interactive widget handle the release
            super().mouseReleaseEvent(event)
            return
            
    def _is_interactive_widget(self, pos):
        """
        Enhanced method to detect if position is over an interactive widget
        Uses hierarchical traversal like the Blender version
        """
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
            # Check for specific widgets that should be interactive
            '''if current_widget is self.canvas_tab_frame_scroll_area:
                return True
            # Check for scroll areas and their contents
            if isinstance(current_widget, (QtWidgets.QScrollArea, QtWidgets.QAbstractScrollArea)):
                return True'''
                
            # Move up to parent widget
            current_widget = current_widget.parent()
        
        return False
    #-----------------------------------------------------------------------------------------------------------------------------------
    def leaveEvent(self, event):
        """Reset cursor when mouse leaves the window"""
        if not self.resizing:
            self.setCursor(QtCore.Qt.ArrowCursor)
        super().leaveEvent(event)
    
    def resizeEvent(self, event):
        """Enhanced resize event with better throttling"""
        # Call parent implementation first
        super().resizeEvent(event)
        
        # Only update buttons if not in active resize and not during batch operations
        if not self.resize_state.get('active', False) and not getattr(self, 'batch_update_active', False):
            # Use a timer to throttle updates during rapid resize events
            if not hasattr(self, '_resize_update_timer'):
                self._resize_update_timer = QTimer()
                self._resize_update_timer.setSingleShot(True)
                self._resize_update_timer.timeout.connect(lambda: self.update_buttons_for_current_tab(force_update=True))
            
            self._resize_update_timer.stop()
            self._resize_update_timer.start(100)  # 100ms delay

    def closeEvent(self, event):
        """Enhanced close event to ensure all data is saved and timers are cleaned up"""
        #print(f"Closing picker window {id(self)}")
        
         # Exit rename mode for any button in rename mode in the active canvas
        if hasattr(self, 'tab_system') and self.tab_system and self.tab_system.current_tab:
            canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            for button in getattr(canvas, 'buttons', []):
                if getattr(button, 'rename_mode', False):
                    button.commit_rename()
                    button.exit_rename_mode()
        
        self.edit_mode = False
        
        # Process any pending updates before closing
        if hasattr(self, 'pending_button_updates') and self.pending_button_updates:
            self._process_batch_updates()
        
        if hasattr(self, 'pending_widget_changes') and self.pending_widget_changes:
            self._apply_widget_changes()

        # Stop the stay-on-top timer first
        if hasattr(self, 'stay_on_top_timer') and self.stay_on_top_timer:
            self.stay_on_top_timer.stop()
            self.stay_on_top_timer.deleteLater()
            self.stay_on_top_timer = None

        if hasattr(self, 'update_checker_timer') and self.update_checker_timer:
            self.update_checker_timer.stop()
            self.update_checker_timer.deleteLater()
            self.update_checker_timer = None
        
        # Unregister from visibility manager BEFORE cleanup
        try:
            from . import blender_main
            visibility_manager = blender_main.PickerVisibilityManager.get_instance()
            visibility_manager.unregister_picker(self)
        except Exception as e:
            print(f"Error unregistering from visibility manager: {e}")

        # Comprehensive cleanup
        self.cleanup_resources()
        
        # Stop periodic cleanup
        self.end_periodic_cleanup()
        
        # Force process events to ensure cleanup
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.processEvents()
        
        #print(f"Picker window {id(self)} close event complete")
        
        # Call parent close event
        super().closeEvent(event)

    def on_resize_timer_timeout(self):
        # Timer has timed out, meaning resizing has stopped
        self.resize_state['active'] = False
        
        # Reset cached references
        cached_canvas = self.resize_state['cached_canvas']
        self.resize_state['cached_canvas'] = None
        
        # Perform full update of the canvas and UI
        if cached_canvas:
            # Update button positions with the new canvas size
            cached_canvas.update_button_positions()
            cached_canvas.update()
            
        # Update all UI elements
        self.update()

    def eventFilter(self, obj, event):
        # Handle double-click on main frame
        if event.type() == QtCore.QEvent.MouseButtonDblClick and obj == self.main_frame:
            # Reset window to original size when double-clicked
            if self.edit_mode:
                new_width = 350 + self.edit_scroll_area.width()
                self.resize(new_width, 450)
                self.update_buttons_for_current_tab()
            else:
                self.resize(350, 450)
                self.update_buttons_for_current_tab()
                UT.blender_main_window()
            return True
        

        
        # Continue with other event handling
        return super().eventFilter(obj, event)
    #----------------------------------------------------------------------------------------------------------------------------------------
    #CLEANUP
    #----------------------------------------------------------------------------------------------------------------------------------------
    def cleanup_resources(self):
        """Comprehensive resource cleanup - call this when closing or resetting"""
        #print("Starting comprehensive resource cleanup...")
        
        # Clean up any open script managers
        if hasattr(self, '_open_script_managers'):
            for script_manager in self._open_script_managers:
                script_manager.close()
            self._open_script_managers.clear()
        
        # 1. Stop and cleanup all timers
        self._cleanup_timers()
        
        # 2. Cleanup tabs and canvases
        self._cleanup_tabs_and_canvases()
        
        # 3. Clear data structures
        self._cleanup_data_structures()
        
        # 4. Disconnect signals
        self._cleanup_signal_connections()
        
        # 5. Force garbage collection
        self._force_garbage_collection()
        
        #print("Resource cleanup complete")

    def _cleanup_timers(self):
        """Stop and delete all timers"""
        for timer_attr in ['resize_timer', 'batch_update_timer', 'widget_update_timer', 'stay_on_top_timer', 'update_checker_timer']:
            if hasattr(self, timer_attr):
                timer = getattr(self, timer_attr)
                if timer and isinstance(timer, QtCore.QTimer):
                    timer.stop()
                    timer.deleteLater()
                    setattr(self, timer_attr, None)
                
                #print(f"Cleaned up timer: {timer_attr}")
        
    def _cleanup_tabs_and_canvases(self):
        """Properly cleanup all tabs, canvases and buttons"""
        if hasattr(self, 'tab_system') and self.tab_system.tabs:
            for tab_name, tab_data in list(self.tab_system.tabs.items()):
                canvas = tab_data.get('canvas')
                if canvas:
                    # Cleanup all buttons on this canvas
                    for button in list(canvas.buttons):
                        self._cleanup_button(button)
                    canvas.buttons.clear()
                    
                    # Remove from stack and cleanup canvas
                    index = self.canvas_stack.indexOf(canvas)
                    if index != -1:
                        self.canvas_stack.removeWidget(canvas)
                    
                    # Disconnect canvas signals
                    try:
                        canvas.button_selection_changed.disconnect()
                        canvas.clicked.disconnect()
                    except:
                        pass
                    
                    canvas.setParent(None)
                    canvas.deleteLater()
                    #print(f"Cleaned up canvas for tab: {tab_name}")
            
            # Clear tab system
            self.tab_system.tabs.clear()

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

    def _cleanup_data_structures(self):
        """Clear all data structure caches"""
        # Clear pending updates
        if hasattr(self, 'pending_button_updates'):
            self.pending_button_updates.clear()
        
        if hasattr(self, 'pending_widget_changes'):
            self.pending_widget_changes.clear()
        
        # Clear ID caches
        if hasattr(self, 'available_ids'):
            self.available_ids.clear()
        
        # Clear resize state
        if hasattr(self, 'resize_state'):
            self.resize_state.clear()
        
        #print("Cleared data structure caches")

    def _cleanup_signal_connections(self):
        """Disconnect remaining signal connections"""
        try:
            # Disconnect main frame signals
            if hasattr(self, 'main_frame'):
                self.main_frame.removeEventFilter(self)
            

            
            # Disconnect other widget signals
            widgets_to_disconnect = ['namespace_dropdown', 'close_button']
            for widget_name in widgets_to_disconnect:
                if hasattr(self, widget_name):
                    widget = getattr(self, widget_name)
                    widget.blockSignals(True)
            
            #print("Disconnected signal connections")
            
        except Exception as e:
            print(f"Error disconnecting signals: {e}")

    def _force_garbage_collection(self):
        """Force Python garbage collection"""
        import gc
        
        # Force immediate widget deletion
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Force garbage collection
        collected = gc.collect()
        #print(f"Garbage collection freed {collected} objects")
        
        # Print memory usage if available
        try:
            import psutil
            import os
            process = psutil.Process(os.getpid())
            memory_mb = process.memory_info().rss / 1024 / 1024
            #print(f"Current memory usage: {memory_mb:.1f} MB")
        except ImportError:
            pass
    
    def setup_periodic_cleanup(self):
        """Setup periodic cleanup to prevent accumulation"""
        self.cleanup_timer = QtCore.QTimer(self)
        self.cleanup_timer.timeout.connect(self.periodic_cleanup)
        self.cleanup_timer.start(300000)  # Every 5 minutes

    def end_periodic_cleanup(self):
        """Stop the periodic cleanup timer"""
        if hasattr(self, 'cleanup_timer') and self.cleanup_timer:
            self.cleanup_timer.stop()
            self.cleanup_timer.deleteLater()
            del self.cleanup_timer
            #print("Periodic cleanup Ended.")

    def periodic_cleanup(self):
        """Periodic maintenance cleanup"""
        #print("Running periodic cleanup...")
        
        # Clear unused ID references
        if hasattr(self, 'available_ids'):
            for tab_name in list(self.available_ids.keys()):
                if tab_name not in self.tab_system.tabs:
                    del self.available_ids[tab_name]
        
        # Force widget updates processing
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        
        # Light garbage collection
        import gc
        collected = gc.collect(generation=0)  # Only generation 0
        #if collected > 0:
            #print(f"Periodic cleanup collected {collected} objects")
    
