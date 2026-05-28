import os
from functools import partial
import sys
import warnings
from pathlib import Path
import bpy

from PySide6 import QtWidgets, QtCore, QtGui
from PySide6.QtCore import QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QShortcut
from PySide6.QtWidgets import QApplication

from .config.settings import PAGE_SEGMENT_CONTROL_SIZE, CARD_SIZE as DEFAULT_CARD_SIZE
from . import custom_segment_control as CSC
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
from . import edit_mode_controller as EMC
from . fade_away_logic import FadeAway
from . import custom_color_picker as CCP
from .update_ui import UpdateBanner
from . import selection_sync_manager as SSM
from . import local_file_ui as LIB_UI
from .picker_session import PickerSession
from . import picker_io as PIO
from .settings_page import SettingsPage
from .auth_manager import AuthManager
from .bgen_library_manager import BgenLocalFileManager

# Get version from __init__
import ft_anim_picker
anim_picker_version = ft_anim_picker.src.__version__
anim_picker_version = f" (v{anim_picker_version})"

class _LibraryGateBanner(QtWidgets.QWidget):
    """Centered placeholder shown when the library is gated by a feature flag."""

    action_clicked = QtCore.Signal(str)

    def __init__(self, title, subtitle, action_label=None, action_name=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        title_lbl = QtWidgets.QLabel(title)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #ccc;")
        title_lbl.setAlignment(QtCore.Qt.AlignCenter)
        title_lbl.setWordWrap(True)

        sub_lbl = QtWidgets.QLabel(subtitle)
        sub_lbl.setStyleSheet("font-size: 12px; color: #888;")
        sub_lbl.setAlignment(QtCore.Qt.AlignCenter)
        sub_lbl.setWordWrap(True)

        layout.addStretch()
        layout.addWidget(title_lbl)
        layout.addSpacing(6)
        layout.addWidget(sub_lbl)

        if action_label and action_name:
            btn = QtWidgets.QPushButton(action_label)
            btn.setFixedWidth(140)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton { background: #333; color: #ccc; border: 1px solid #555;"
                " border-radius: 4px; padding: 6px 12px; }"
                "QPushButton:hover { background: #444; }"
            )
            btn.clicked.connect(lambda: self.action_clicked.emit(action_name))
            layout.addSpacing(12)
            layout.addWidget(btn, 0, QtCore.Qt.AlignCenter)

        layout.addStretch()


class NamespaceComboBox(QtWidgets.QComboBox):
    """QComboBox that emits a signal on right-click instead of showing the
    default popup, so the parent window can build a context menu that knows
    about the current tab/scene state. Also exposes a helper to swap the
    border color between the default and 'pinned filter active' variants.
    """

    requestContextMenu = QtCore.Signal(QtCore.QPoint)

    _BORDER_DEFAULT = '#2f2f2f'
    _BORDER_FILTERED = '#1d65ca'

    def __init__(self, parent=None):
        super().__init__(parent)
        self._filter_active = False
        self._apply_stylesheet()

    def _apply_stylesheet(self):
        bg = UT.rgba_value('#222222', 1, .9)
        bg_hover = UT.rgba_value('#222222', .8, 1)
        border = self._BORDER_FILTERED if self._filter_active else self._BORDER_DEFAULT
        self.setStyleSheet(
            f'''QComboBox{{background-color: {bg}; color: #dddddd; border: 1px solid {border}; padding: 2px 2px 2px 8px; border-radius: 11px;}}
                QComboBox:hover {{background-color: {bg_hover};}}
                QComboBox::drop-down {{border: 0px; color: #dddddd;}}
                QComboBox::down-arrow {{background-color: transparent;}}
                QComboBox QAbstractItemView {{background-color: #222222; color: #dddddd; border: 1px solid #2f2f2f; selection-background-color: rgba(29,101,202,0.4);}}
                QToolTip {{background-color: #222222; color: #eeeeee;border: 1px solid rgba(255,255,255,.2); padding: 4px; border-radius: 0px;}} '''
        )

    def set_filter_mode_style(self, active):
        active = bool(active)
        if active == self._filter_active:
            return
        self._filter_active = active
        self._apply_stylesheet()

    def contextMenuEvent(self, event):
        # Emit a signal carrying the global position so the main window can
        # build a context menu that closes over its own state.
        self.requestContextMenu.emit(event.globalPos())
        event.accept()


class BlenderAnimPickerWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(BlenderAnimPickerWindow, self).__init__(parent)
        from . import utils as UT
        self.setWindowFlags(UT.picker_window_flags())
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_AlwaysShowToolTips, True)
        self.setStyleSheet('''QWidget {background-color: rgba(40, 40, 40, 0.5); border-radius: 4px;}''')
        
        # Track our visibility state for centralized management
        self.should_be_visible = True
        self.stored_geometry = None
        
        # Track full screen state and original geometry
        self.is_fullscreen = False
        self.pre_fullscreen_geometry = None
        
        # Track window size mode and stored positions for each mode
        # 'min', 'mid', 'full', or None (custom size)
        self.current_size_mode = None
        self.stored_positions = {
            'min': None,   # Stored position for minimum size
            'mid': None,   # Stored position for default/medium size
        }

        # Enable drag and drop for the window
        self.setAcceptDrops(True)
        self.drag_highlight_active = False
        
        self.edit_mode = False
        self._edit_mode_width_delta = 0
        self._width_anim = None
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
    
        # Chunked button loading state (must be before setup_tab_system)
        self._button_load_gen = None
        self._button_load_tab = None
        self._button_load_canvas = None
        self._pending_restore_selection = None
        self._tab_button_versions = {}
        self._chunk_size = 25

        self.setup_ui()
        self.setup_layout()
        self.setup_tab_system()
        self.setup_connections()

        # When focus moves OUT of any picker line edit (color hex input,
        # transform fields, name field, etc.), Blender's GHOST may have
        # missed key-up events for modifier keys (Ctrl/Shift/Alt/Cmd)
        # because Qt was holding the keyboard. The result is "stuck"
        # modifier state in Blender — MMB drag becomes Ctrl+MMB (zoom),
        # so viewport orbit/pan break and only zoom appears to work.
        # Re-activating Blender forces GHOST to refresh its input state.
        try:
            app = QApplication.instance()
            if app is not None:
                app.focusChanged.connect(self._on_app_focus_changed)
        except Exception:
            pass

        # Resize tracking variables
        self.resizing = False
        self.resize_edge = None
        self.resize_start_pos = None
        self.resize_start_geometry = None
        self.resize_border_width = 6  # Width of the resize border area

        # Resize timer for final update after resizing stops
        self.resize_timer = QtCore.QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.on_resize_timer_timeout)

        self.available_ids = {}

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
            {'widget': self.tools_row_frame, 'show_in_minimal': True},
            {'widget': self.canvas_tab_frame, 'hide_in_minimal': True},
            {'widget': self.namespace_dropdown, 'hide_in_minimal': True},
            {'widget': self.close_button, 'hide_in_minimal': False},
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

        # Picker session (active .bpicker file)
        self.session = None  # PickerSession instance

        # Library UI state
        self._library_sort_mode = "modified"
        self._library_search_visible = False
        self._library_view_mode = "medium"

        # Library page controller
        self.library_controller = LIB_UI.LocalFilePageController(
            grid_layout=self.my_library_grid,
            grid_container=self.my_library_grid_container,
            scroll_area=self.my_library_grid_area,
            parent_window=self,
        )
        self.library_controller.picker_open_requested.connect(self.open_picker_from_library)
        self.library_controller.tab_import_requested.connect(self._import_tab_from_library)

        # Initial data load for library (deferred so layouts have valid sizes)
        QTimer.singleShot(100, self.library_controller.refresh)

        # Library manager signals (native pages removed — web handles UI)
        self._bgen_library_mgr.feature_flags_loaded.connect(
            self._on_feature_flags_loaded
        )

        # Check launch state (new flow: prompt or auto-load)
        QTimer.singleShot(100, self._check_launch_state)

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
        self.main_frame.setStyleSheet('''QFrame {border: 0px solid gray; border-radius: 8px; background-color: #1D1D1D;}''')
        self.main_frame_layout = QtWidgets.QVBoxLayout(self.main_frame)
        set_margin_space(self.main_frame_layout,8,4)

        self.main_frame_util_layout = QtWidgets.QHBoxLayout()
        self.main_frame_body_layout = QtWidgets.QHBoxLayout()
        self.main_frame_tool_layout = QtWidgets.QHBoxLayout()

        #-----------------------------------------------------------------------------------------------------------------------------------
        # Utility frame (top bar)
        #-----------------------------------------------------------------------------------------------------------------------------------
        util_button_height = 26
        
        self.util_frame = QtWidgets.QFrame()
        self.util_frame.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.util_frame.setFixedHeight(util_button_height + 4)
        self.util_frame.setStyleSheet('''QFrame {border: 0px solid gray; border-radius: 4px; background-color: rgba(40, 40, 40, 0); padding: 0px;}''')
        self.util_frame_layout = QtWidgets.QHBoxLayout(self.util_frame)
        set_margin_space(self.util_frame_layout,2,0)
        self.util_frame_layout.setAlignment(QtCore.Qt.AlignLeft)
        #-----------------------------------------------------------------------------------------------------------------------------------
        # Icon (opens context menu with page sizes and picker modes)
        icon_size = int(util_button_height * 0.7)
        self.icon_image = QtWidgets.QPushButton()
        self.icon_image.setFixedSize(icon_size, icon_size)
        self.icon_image.setCursor(QtCore.Qt.PointingHandCursor)
        self.icon_image.setToolTip("Picker Options")
        self.icon_image.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                border-radius: 3px;
            }
        """)
        package_dir = Path(__file__).parent
        icon_path = package_dir / 'bgen_picker_icons' / 'bgen-picker-icon-02.png'
        if icon_path.exists():
            self.icon_image.setIcon(QtGui.QIcon(str(icon_path)))
            self.icon_image.setIconSize(QtCore.QSize(icon_size, icon_size))
        self.icon_image.clicked.connect(lambda: self.fade_manager.show_frame_context_menu(self.icon_image.mapTo(self, QtCore.QPoint(0, self.icon_image.height()))))
        #-----------------------------------------------------------------------------------------------------------------------------------
        # Util Buttons
        #-----------------------------------------------------------------------------------------------------------------------------------
        #File Util
        file_util = CB.CustomButton(text='File', height=util_button_height, width=40, radius=3,color='#385c73',alpha=0,textColor='#aaaaaa', ContextMenu=True, onlyContext= True,
                                    cmColor='#333333',tooltip='File Utilities', flat=True)
        file_util.addMenuLabel("File Utilities",position=(0,0))
        file_util.addToMenu("Save", self.save_current_picker, icon=UT.get_icon('save.png'), position=(1,0))
        file_util.addToMenu("Save As...", self.save_picker_as, icon=UT.get_icon('save.png'), position=(2,0))
        file_util.addToMenu("Export Picker", self.export_picker, icon=UT.get_icon('save.png'), position=(3,0))
        file_util.addToMenu("Import Picker", self.import_picker, icon=UT.get_icon('load.png'), position=(4,0))
        #-----------------------------------------------------------------------------------------------------------------------------------
        #Edit Util
        edit_util = CB.CustomButton(text='Edit', height=util_button_height, width=40, radius=3,color='#385c73',alpha=0,textColor='#aaaaaa', ContextMenu=True, onlyContext= True,
                                    cmColor='#333333',tooltip='Edit Utilities', flat=True)
        edit_util.addMenuLabel("Edit Utilities",position=(0,0))
        edit_util.addToMenu("Edit Mode", self.toggle_edit_mode, icon=UT.get_icon('edit.png'), position=(1,0))
        edit_util.addToMenu("Toggle Minimal Mode", self.fade_manager.toggle_minimal_mode, icon=UT.get_icon('visible.png'), position=(2,0))
        edit_util.addToMenu("Toggle Fade Away", self.fade_manager.toggle_fade_away, icon=UT.get_icon('visible.png'), position=(3,0))
        #-----------------------------------------------------------------------------------------------------------------------------------
        #Info Util
        self.info_util = CB.CustomButton(text='Info', height=util_button_height, width=40, radius=3,color='#385c73',alpha=0,textColor='#aaaaaa', ContextMenu=True, onlyContext= True,
                                    cmColor='#333333',tooltip='Info Utilities', flat=True, notification=True)
        self.info_util.addMenuLabel(f"BGEN Picker{anim_picker_version}",position=(0,0))
        self.info_util.addToMenu(f"Manual", self.info, icon=UT.get_icon('manual.png'), position=(1,0))
        self.info_util.addToMenu(f"Update", self.update_anim_picker, icon=UT.get_icon('update.png'), position=(2,0))
        #-----------------------------------------------------------------------------------
        # Page segment control with icons
        self.page_segment_frame = QtWidgets.QFrame()
        self.page_segment_frame.setObjectName("pageSegmentFrame")
        self.page_segment_frame.setStyleSheet(f"""QFrame#pageSegmentFrame 
                                         {{background: rgba(255, 255, 255, .10); 
                                         border: none; 
                                         padding: 3px;
                                         border-radius: {util_button_height/ 2}px;}}""")
        page_segment_layout = QtWidgets.QHBoxLayout(self.page_segment_frame)
        page_segment_layout.setContentsMargins(0, 0, 0, 0)

        icons_dir = Path(__file__).parent / "bgen_picker_icons"
        page_icon_paths = [
            str(icons_dir / "bgen_editor_icon.png"),
            str(icons_dir / "bgen_library_icon.png"),
            str(icons_dir / "bgen_settings_icon.png")
        ]
        page_names = ["BGEN Picker Editor", "BGEN Library", "BGEN Settings"]
        
        self.page_segment = CSC.PageSegmentControl(page_icon_paths, page_names, button_size=util_button_height * 0.8, icon_size=util_button_height * 0.4)
        self.page_segment.set_selected_index(0)  # Start on Library page
        page_segment_layout.addWidget(self.page_segment)
        self.page_segment.page_changed.connect(self._on_page_changed)
        
        #-----------------------------------------------------------------------------------------------------------------------------------
        # Close button
        self.close_button = CB.CustomButton(icon=UT.get_icon('close_01.png',size=16,opacity=1), height=util_button_height, width=util_button_height, radius=util_button_height/2,color='#db2525',tooltip='Close')
        self.close_button.clicked.connect(self.close)
        #-----------------------------------------------------------------------------------------------------------------------------------
        # Add widgets to utility frame
        self.util_frame_layout.addSpacing(4)
        self.util_frame_layout.addWidget(self.icon_image)
        self.util_frame_layout.addSpacing(2)
        self.util_frame_layout.addWidget(file_util)
        self.util_frame_layout.addWidget(edit_util)
        self.util_frame_layout.addWidget(self.info_util)
        self.util_frame_layout.addStretch(1)
        
        
        self.util_frame_layout.addWidget(self.page_segment_frame)
        self.util_frame_layout.addSpacing(6)
        self.util_frame_layout.addWidget(self.close_button)
        self.util_frame_layout.addSpacing(2)
        #-----------------------------------------------------------------------------------------------------------------------------------
        # Canvas frame
        #-----------------------------------------------------------------------------------------------------------------------------------
        self.canvas_frame = QtWidgets.QFrame()
        self.canvas_frame.setStyleSheet('''QFrame {border: 0px solid gray; border-radius: 4px; background-color: rgba(40, 40, 40, 0);}''')
        self.canvas_frame_layout = QtWidgets.QVBoxLayout(self.canvas_frame)
        set_margin_space(self.canvas_frame_layout,4,4)
        # Update notification banner (above tabs)
        from .update_ui import UpdateBanner
        self.update_banner = UpdateBanner(self.canvas_frame)
        self.update_banner.view_details.connect(self.update_anim_picker)
        self.canvas_frame_layout.addWidget(self.update_banner)
        self.canvas_frame_column_1 = QtWidgets.QHBoxLayout()
        self.canvas_frame_layout.addLayout(self.canvas_frame_column_1)
        #-----------------------------------------------------------------------------------------------------------------------------------
        #-Canvas Tab Frame
        self.canvas_tab_frame = QtWidgets.QFrame()
        self.canvas_tab_frame.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        self.canvas_tab_frame.setFixedHeight(24)
        self.canvas_tab_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray; border-radius: 12px; background-color: rgba(255, 255, 255, 0);}}''')
        
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
        self.add_tab_button = CB.CustomButton(icon=UT.get_icon('add.png',size=10,opacity=.9), height=16, width=16, radius=8,color='#1D65CA',tooltip='Add New Tab')
        self.canvas_tab_frame_layout.addWidget(self.add_tab_button)
        
        # Create a stacked widget to hold picker canvases
        self.canvas_stack = QtWidgets.QStackedWidget()
        self.canvas_stack.setStyleSheet(f'''QWidget {{border: 0px solid #223d4f; border-radius: 4px; background-color: transparent;}}''')
        self.canvas_frame_layout.addWidget(self.canvas_stack)
        #-----------------------------------------------------------------------------------------------------------------------------------
        #-Name Space Dropdown
        self.namespace_dropdown = NamespaceComboBox(self)
        self.namespace_dropdown.setFixedHeight(22)
        # Width will be dynamically set based on content (min 40, max 120)
        self.namespace_dropdown.setToolTip('Select Namespace  -  Right-click to pin/filter')
        self.namespace_dropdown.addItems(['None'])
        #-----------------------------------------------------------------------------------------------------------------------------------
        self.canvas_frame_column_1.addWidget(self.canvas_tab_frame_scroll_area)
        #self.canvas_frame_column_1.addStretch()
        self.canvas_frame_column_1.addWidget(self.namespace_dropdown)
        #-----------------------------------------------------------------------------------------------------------------------------------
        #-Edit Frame
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.efw = 200  # edit default width
        self._edit_panel_min_width = 180
        self._edit_panel_max_width = 450

        # Create the canvas edit panel (overlay inside canvas_frame)
        self.canvas_edit_panel = PC.CanvasEditPanel(self.canvas_frame)
        # Anchor positioning to the canvas area so the panel stays correctly placed
        # when reparented to main_frame in minimal mode.
        self.canvas_edit_panel.set_anchor_widget(self.canvas_stack)
        self.canvas_edit_panel.width_changed.connect(self._on_edit_panel_width_changed)
        
        self.edit_frame = QtWidgets.QFrame()
        self.edit_frame.setStyleSheet('QFrame {background-color: #1d1d1d; border: 0px solid #333333;}')
        
        # Create a scroll area
        self.edit_scroll_area = QtWidgets.QScrollArea()
        self.edit_scroll_area.setWidgetResizable(True)
        self.edit_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.edit_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.edit_scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
                padding-top: 0px;
                padding-right: 0px;
                margin: 6px;
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
        set_margin_space(self.edit_layout,8,4)
        #-Edit Label
        self.edit_label = QtWidgets.QLabel("Picker Editor")
        self.edit_label.setAlignment(QtCore.Qt.AlignCenter)        
        self.edit_label.setStyleSheet('QLabel {color: #dddddd; background-color: transparent; font-size: 12px;}')
        #self.edit_layout.addWidget(self.edit_label)

        self.toggle_edit_mode_button_layout = QtWidgets.QHBoxLayout()
        self.toggle_edit_mode_button_layout.setContentsMargins(8, 2, 8, 10)

        self.toggle_edit_mode_button = CB.CustomButton(text='Exit Edit Mode', height=24, radius=4, color='#1D65CA', tooltip='Apply changes')
        self.toggle_edit_mode_button.clicked.connect(self.toggle_edit_mode)

        self.toggle_edit_mode_button_layout.addWidget(self.toggle_edit_mode_button)

        # Add scroll area and button to the canvas edit panel
        self.canvas_edit_panel.add_widget(self.edit_scroll_area)
        self.canvas_edit_panel.add_layout(self.toggle_edit_mode_button_layout)

        self.canvas_edit_panel.setVisible(self.edit_mode)

        # Border is now drawn directly in the canvas paintEvent
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #-Buttons EF (HIDDEN)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.add_button_EF = EF.ExpandableFrame(title='Add Button', color='#222222', border=1, border_color='#333333') 
        self.add_button_EF.toggle_expand()
        # Width is now managed by the resizable panel
        self.add_picker_button = CB.CustomButton(text='Add Button', height=24, radius=4,color='#5285a6')

        p_button_grid1 = QtWidgets.QGridLayout()

        self.add_p_button_label_label = QtWidgets.QLabel("Label")
        self.add_p_button_label_qline = CLE.FocusLosingLineEdit('Button')

        p_button_grid1.addWidget(self.add_p_button_label_label, 1, 0)
        p_button_grid1.addWidget(self.add_p_button_label_qline, 1, 1)
        
        self.add_button_EF.addWidget(self.add_picker_button)
        self.add_button_EF.addLayout(p_button_grid1)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #-Button / Canvas Segment Control
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.button_selection_count = 0

        # Segment control to switch between Button and Canvas edit panels
        self.edit_segment_control = CSC.TextSegmentControl(
            ["Button", "Canvas"],
            height=26,
            font_size=12,
            radius=10,
            frame_radius=12,
            use_frame=True,
            frame_bg="rgba(255, 255, 255, 0.1)",
        )

        # Stacked widget to hold button and canvas pages
        self.edit_stack = QtWidgets.QStackedWidget()
        self.edit_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self.edit_segment_control.segment_changed.connect(self.edit_stack.setCurrentIndex)

        # --- Button page (index 0) ---
        self.edit_button_page = QtWidgets.QWidget()
        self.edit_button_page.setStyleSheet("background: transparent;")
        edit_button_page_layout = QtWidgets.QVBoxLayout(self.edit_button_page)
        edit_button_page_layout.setAlignment(QtCore.Qt.AlignTop)
        set_margin_space(edit_button_page_layout, 0, 4)

        self.edit_value_layout = QtWidgets.QVBoxLayout()
        set_margin_space(self.edit_value_layout, 0, 4)

        self.add_picker_button = CB.CustomButton(text='Add Button', height=24, radius=4, color='#5285a6', tooltip='Add Button to the current tab')
        edit_button_page_layout.addLayout(self.edit_value_layout)

        # Create the edit mode controller (consolidated edit logic)
        self.edit_controller = EMC.EditModeController(self)
        self.edit_value_layout.addWidget(self.edit_controller.get_button_page_widget())
        # Expose widgets dict for backward compatibility
        self.edit_widgets = self.edit_controller.widgets

        self.edit_stack.addWidget(self.edit_button_page)

        # --- Canvas page (index 1) ---
        _CARD_STYLE = (
            "QFrame { background: transparent; "
            "border: 0px solid rgba(255,255,255,0.06); border-radius: 8px; }"
            "QLabel { background: transparent; border: none; }"
        )
        _SECTION_LABEL = "color: #999999; font-size: 11px; font-weight: bold;"
        _SUB_LABEL = "color: #777777; font-size: 10px;"

        self.edit_canvas_page = QtWidgets.QWidget()
        self.edit_canvas_page.setStyleSheet("background: transparent;")
        self.edit_canvas_page_layout = QtWidgets.QVBoxLayout(self.edit_canvas_page)
        self.edit_canvas_page_layout.setAlignment(QtCore.Qt.AlignTop)
        set_margin_space(self.edit_canvas_page_layout, 0, 6)

        def add_divider(layout,spacing=8):
            divider = QtWidgets.QFrame()
            divider.setFixedHeight(1)
            divider.setStyleSheet("background-color: rgba(255, 255, 255, 0.1);")
            layout.addSpacing(spacing)
            layout.addWidget(divider)
        # ── Background Image Card ──────────────────────────────────────
        bg_card = QtWidgets.QFrame()
        bg_card.setStyleSheet(_CARD_STYLE)
        bg_card_layout = QtWidgets.QVBoxLayout(bg_card)
        set_margin_space(bg_card_layout, 6, 6)

        bg_title = QtWidgets.QLabel("Background Image")
        bg_title.setStyleSheet(_SECTION_LABEL)
        bg_card_layout.addWidget(bg_title)

        # Action buttons row
        img_btn_layout = QtWidgets.QHBoxLayout()
        img_btn_layout.setSpacing(4)
        self.add_image = CB.CustomButton(
            text='Import', icon=UT.get_icon('img.png', size=12),
            height=24, radius=4, color='#1D65CA',
            tooltip='Import background image')
        
        self.capture_bg_button = CB.CustomButton(
            text='Capture', icon=UT.get_icon('select.png', size=14),
            height=24, radius=4, color='#1D65CA',
            tooltip='Capture screen region as background')

        self.remove_image = CB.CustomButton(
            text='Remove', icon=UT.get_icon('delete_white.png', size=12),
            height=24, radius=4, color='#555555',
            tooltip='Remove background image')
            
        img_btn_layout.addWidget(self.add_image)
        #img_btn_layout.addWidget(self.remove_image)
        img_btn_layout.addWidget(self.capture_bg_button)
        bg_card_layout.addLayout(img_btn_layout)
        bg_card_layout.addWidget(self.remove_image)

        # Opacity row
        opacity_row = QtWidgets.QHBoxLayout()
        opacity_row.setSpacing(4)
        opacity_lbl = QtWidgets.QLabel("Opacity")
        opacity_lbl.setStyleSheet(_SUB_LABEL)
        opacity_lbl.setFixedWidth(42)
        self.image_opacity_slider = CS.CustomSlider(
            min_value=0, max_value=100, float_precision=0,
            height=17, radius=3, prefix='', suffix='%', color='#1D65CA')
        self.image_opacity_slider.setValue(100)
        opacity_row.addWidget(opacity_lbl)
        opacity_row.addWidget(self.image_opacity_slider)
        bg_card_layout.addLayout(opacity_row)

        # Scale row
        scale_row = QtWidgets.QHBoxLayout()
        scale_row.setSpacing(4)
        scale_lbl = QtWidgets.QLabel("Scale")
        scale_lbl.setStyleSheet(_SUB_LABEL)
        scale_lbl.setFixedWidth(42)
        self.image_scale_factor = CLE.IntegerLineEdit(
            min_value=.01, max_value=400, increment=.1,
            precision=2, width=None, height=18, label="")
        self.image_scale_factor.setText('1.0')
        scale_row.addWidget(scale_lbl)
        scale_row.addWidget(self.image_scale_factor)
        bg_card_layout.addLayout(scale_row)

        self.edit_canvas_page_layout.addWidget(bg_card)
        add_divider(self.edit_canvas_page_layout)
        # ── Canvas Appearance Card ─────────────────────────────────────
        canvas_card = QtWidgets.QFrame()
        canvas_card.setStyleSheet(_CARD_STYLE)
        canvas_card_layout = QtWidgets.QVBoxLayout(canvas_card)
        set_margin_space(canvas_card_layout, 6, 6)

        canvas_title = QtWidgets.QLabel("Canvas Appearance")
        canvas_title.setStyleSheet(_SECTION_LABEL)
        canvas_card_layout.addWidget(canvas_title)

        # Background value row
        bg_row = QtWidgets.QHBoxLayout()
        bg_row.setSpacing(4)
        bg_lbl = QtWidgets.QLabel("Value")
        bg_lbl.setStyleSheet(_SUB_LABEL)
        bg_lbl.setFixedWidth(64)
        self.bg_value_slider = CS.CustomSlider(
            min_value=0, max_value=100, float_precision=0,
            height=17, radius=3, prefix='', suffix='%', color='#1D65CA')
        self.bg_value_slider.setValue(50)
        bg_row.addWidget(bg_lbl)
        bg_row.addWidget(self.bg_value_slider)
        canvas_card_layout.addLayout(bg_row)

        # Toggle row 1: Axes + Dots
        toggle_row1 = QtWidgets.QHBoxLayout()
        toggle_row1.setSpacing(6)
        self.toggle_axes = CB.CustomRadioButton('Axes', height=None, color='#1D65CA', fill=False)
        self.toggle_axes.setChecked(True)
        self.toggle_dots = CB.CustomRadioButton('Dots', height=None, color='#1D65CA', fill=False)
        self.toggle_dots.setChecked(True)
        toggle_row1.addWidget(self.toggle_axes)
        toggle_row1.addWidget(self.toggle_dots)
        canvas_card_layout.addLayout(toggle_row1)

        # Toggle row 2: Grid + Grid Size
        toggle_row2 = QtWidgets.QHBoxLayout()
        toggle_row2.setSpacing(6)
        self.toggle_grid = CB.CustomRadioButton('Grid', height=None, color='#1D65CA', fill=False)
        self.toggle_grid.setChecked(False)
        self.grid_size = CLE.IntegerLineEdit(
            min_value=1, max_value=500, increment=1,
            width=None, height=18, label="Size")
        self.grid_size.setText('50')
        toggle_row2.addWidget(self.toggle_grid)
        toggle_row2.addSpacing(12)
        toggle_row2.addWidget(self.grid_size)
        canvas_card_layout.addLayout(toggle_row2)

        self.edit_canvas_page_layout.addWidget(canvas_card)

        self.edit_stack.addWidget(self.edit_canvas_page)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.edit_layout.addSpacing(4)
        self.edit_layout.addWidget(self.edit_segment_control)
        self.edit_layout.addWidget(self.edit_stack)
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        
        #-----------------------------------------------------------------------------------------------------------------------------------
        #-Tool Frame
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        #Tool Drawer
        self.tools_EF = EF.ExpandableFrame(title='<span style="color: #777777; font-size: 11px;"> Animation Tools</span>', 
        color='#282828',alpha=.8, border=1, border_color='#333333',margin=2, radius=6)
        self.tools_EF.toggle_expand()
        self.tool_buttons = TF.animation_tool_layout()
        self.tools_EF.addLayout(self.tool_buttons.layout)

        # Bone visibility toggle — sits to the left of the Animation Tools drawer
        self._bones_visible_icon = UT.get_icon('visible.png', opacity=0.8, size=16)
        self._bones_hidden_icon = UT.get_icon('invisible.png', opacity=0.8, size=16)
        self.show_bones_button = CB.CustomButton(
            icon=self._bones_visible_icon, color='#333333', size=18,
            tooltip="Show/Hide Bones in Viewport", height=28, width=28,
            alpha=0.8, radius=14, flat=False)
        self.show_bones_button.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.show_bones_button.singleClicked.connect(self._on_toggle_show_bones)

        self.tools_row = QtWidgets.QHBoxLayout()
        self.tools_row.setContentsMargins(0, 0, 0, 0)
        self.tools_row.setSpacing(4)
        self.tools_row.addSpacing(4)
        self.tools_row.addWidget(self.show_bones_button, 0, QtCore.Qt.AlignCenter)
        self.tools_row.addSpacing(2)
        self.tools_row.addWidget(self.tools_EF, 1)
        self.tools_row.addSpacing(4)

        # Wrap tools_row in a widget so it can be reparented in minimal mode
        self.tools_row_frame = QtWidgets.QWidget()
        self.tools_row_frame.setStyleSheet("background: transparent;")
        self.tools_row_frame.setLayout(self.tools_row)

        # Sync timer — polls Blender overlay state every 500ms
        self._last_bones_state = None
        self._bones_sync_timer = QTimer()
        self._bones_sync_timer.setInterval(500)
        self._bones_sync_timer.timeout.connect(self._sync_show_bones_state)
        self._bones_sync_timer.start()
        self._sync_show_bones_state()
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        # Page Stack - holds editor, library, and settings pages
        #------------------------------------------------------------------------------------------------------------------------------------------------------
        self.page_stack = QtWidgets.QStackedWidget()
        self.page_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")

        # Page 0: Editor page (canvas + tools wrapped in a container)
        self.editor_page = QtWidgets.QWidget()
        self.editor_page.setStyleSheet("background: transparent;")
        self.editor_page_layout = QtWidgets.QVBoxLayout(self.editor_page)
        self.editor_page_layout.setContentsMargins(0, 0, 0, 0)
        self.editor_page_layout.setSpacing(4)

        # Page 1: Library page
        self.library_page = QtWidgets.QWidget()
        self.library_page.setStyleSheet("background: transparent;")
        library_layout = QtWidgets.QVBoxLayout(self.library_page)
        library_layout.setContentsMargins(4, 4, 4, 4)
        library_layout.setSpacing(6)

        # Library segment control: My Library | BGEN Library
        self.library_segment = CSC.TextSegmentControl(
            ["My Library", "BGEN Library"], 
            height=28,
            font_size=11,
            radius=10,
            frame_radius=13,
            use_frame=True,
            frame_bg="rgba(255, 255, 255, 0.1)",
        )

        # Stacked content for the two library sub-pages
        self.library_stack = QtWidgets.QStackedWidget()
        self.library_stack.setStyleSheet("background: transparent; border: none;")

        # --- My Library sub-page ---
        my_library_widget = QtWidgets.QWidget()
        my_library_widget.setStyleSheet("background: transparent;")
        my_library_layout = QtWidgets.QVBoxLayout(my_library_widget)
        my_library_layout.setContentsMargins(4, 4, 4, 4)
        my_library_layout.setSpacing(2)

        # Toolbar: Sort + Search
        _lib_toolbar = QtWidgets.QHBoxLayout()
        _lib_toolbar.addStretch()

        _lib_btn_style = (
            "QPushButton { background: rgba(255,255,255,0); color: #dddddd; "
            "border: none; border-radius: 4px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.15); }"
        )

        # Sort button
        self.lib_filter_btn = QtWidgets.QPushButton()
        self.lib_filter_btn.setFixedSize(24, 24)
        self.lib_filter_btn.setToolTip("Sort")
        filter_icon = UT.get_icon('preference_icon.png', size=14)
        if filter_icon:
            self.lib_filter_btn.setIcon(QtGui.QIcon(filter_icon))
            self.lib_filter_btn.setIconSize(QtCore.QSize(14, 14))
        self.lib_filter_btn.setStyleSheet(_lib_btn_style)
        self.lib_filter_btn.clicked.connect(self._on_library_filter_menu)

        # Search button
        self.lib_search_btn = QtWidgets.QPushButton()
        self.lib_search_btn.setFixedSize(24, 24)
        self.lib_search_btn.setToolTip("Search")
        search_icon = UT.get_icon('search_icon.png', size=14)
        if search_icon:
            self.lib_search_btn.setIcon(QtGui.QIcon(search_icon))
            self.lib_search_btn.setIconSize(QtCore.QSize(14, 14))
        self.lib_search_btn.setStyleSheet(_lib_btn_style)
        self.lib_search_btn.clicked.connect(self._toggle_library_search)

        _lib_toolbar.addWidget(self.lib_filter_btn)
        _lib_toolbar.addWidget(self.lib_search_btn)
        my_library_layout.addLayout(_lib_toolbar)

        # Search bar (hidden by default, revealed on search button click)
        self.lib_search_container = QtWidgets.QWidget()
        self.lib_search_container.setMaximumHeight(0)
        self.lib_search_container.setStyleSheet("background: transparent;")
        _search_container_layout = QtWidgets.QHBoxLayout(self.lib_search_container)
        _search_container_layout.setContentsMargins(0, 2, 0, 0)
        _search_container_layout.setSpacing(0)
        self.lib_search_input = QtWidgets.QLineEdit()
        self.lib_search_input.setPlaceholderText("Search pickers...")
        self.lib_search_input.setAlignment(QtCore.Qt.AlignLeft)
        _search_pixmap = QtGui.QPixmap(str(Path(__file__).parent / "bgen_picker_icons" / "search_icon.png"))
        _search_painter = QtGui.QPainter(_search_pixmap)
        _search_painter.setCompositionMode(QtGui.QPainter.CompositionMode_DestinationIn)
        _search_painter.fillRect(_search_pixmap.rect(), QtGui.QColor(0, 0, 0, 102))
        _search_painter.end()
        self.lib_search_input.addAction(
            QtGui.QIcon(_search_pixmap),
            QtWidgets.QLineEdit.LeadingPosition,
        )
        self.lib_search_input.setStyleSheet(
            "QLineEdit { background: rgba(50,50,50,0.8); color: #dddddd; left: -8px; "
            "border: 1px solid #3a3a3a; border-radius: 4px; padding: 4px 8px 4px 4px; font-size: 11px; }"
            "QLineEdit:focus { border: 1px solid rgba(29,101,202,0.6); }"
            "QMenu { background-color: #2b2b2b; color: #dddddd; border: 1px solid #3a3a3a; padding: 2px; }"
            "QMenu::item:selected { background-color: rgba(29,101,202,0.4); }"
        )
        self.lib_search_input.setFixedHeight(26)
        self.lib_search_input.textChanged.connect(self._on_library_search_changed)
        _search_container_layout.addWidget(self.lib_search_input)
        my_library_layout.addWidget(self.lib_search_container)

        # Grid area for picker thumbnails
        self.my_library_grid_area = QtWidgets.QScrollArea()
        self.my_library_grid_area.setWidgetResizable(True)
        self.my_library_grid_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.my_library_grid_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
        self.my_library_grid_area.setStyleSheet("""
            QScrollArea { background: rgba(30, 30, 30, 0.5); border: none; border-radius: 6px; }
            QScrollBar:vertical {
                border: none; background: rgba(30, 30, 30, 0.3); width: 8px; margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: rgba(100, 100, 100, 0.5); min-height: 20px; border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover { background: rgba(120, 120, 120, 0.7); }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px; background: transparent;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
        """)
        self.my_library_grid_container = QtWidgets.QWidget()
        self.my_library_grid_container.setStyleSheet("background: transparent;")
        self.my_library_grid = QtWidgets.QGridLayout(self.my_library_grid_container)
        self.my_library_grid.setContentsMargins(8, 8, 8, 8)
        self.my_library_grid.setSpacing(6)
        self.my_library_grid.setAlignment(QtCore.Qt.AlignTop)
        self.my_library_grid.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        self.my_library_grid_area.setWidget(self.my_library_grid_container)
        my_library_layout.addWidget(self.my_library_grid_area)

        # "+" button at bottom of My Library page
        self.lib_create_btn = QtWidgets.QPushButton("Create New Picker")
        self.lib_create_btn.setFixedHeight(28)
        self.lib_create_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.lib_create_btn.setToolTip("Create New Picker")
        self.lib_create_btn.setStyleSheet(
            "QPushButton { background: #1d65ca; color: #dddddd; "
            "border: none; border-radius: 6px; font-size: 12px; font-weight: regular; }"
            "QPushButton:hover { background: rgba(29,101,202,0.8); }"
        )
        self.lib_create_btn.clicked.connect(self._on_library_plus_menu)
        my_library_layout.addWidget(self.lib_create_btn)

        # --- BGEN Library sub-page (WebView only) ---
        self._bgen_library_mgr = BgenLocalFileManager.get_instance()

        from .library_webview import LibraryWebView
        self._mkt_webview = LibraryWebView(parent=self)
        self._mkt_webview.set_managers(
            AuthManager.get_instance(),
            BgenLocalFileManager.get_instance(),
        )

        # Connect WebView bridge signals
        self._mkt_webview.download_requested.connect(
            lambda pid: self._bgen_library_mgr.download_product(pid)
        )
        self._mkt_webview.checkout_requested.connect(
            lambda pid: self._bgen_library_mgr.initiate_purchase(pid)
        )
        self._mkt_webview.sign_in_requested.connect(
            lambda: AuthManager.get_instance().start_sign_in()
        )
        self._mkt_webview.sign_in_google_requested.connect(
            lambda: AuthManager.get_instance().sign_in_with_google()
        )
        self._mkt_webview.sign_out_requested.connect(
            lambda: AuthManager.get_instance().sign_out()
        )
        self._mkt_webview.open_library_requested.connect(
            lambda: self.library_segment.setCurrentIndex(0)
        )

        # Connect checkout_ready → open embedded Stripe checkout page
        from .stripe_checkout_dialog import StripeCheckoutPage
        self._stripe_checkout_page = StripeCheckoutPage(parent=self)

        self._bgen_library_mgr.checkout_ready.connect(self._on_checkout_ready)
        self._stripe_checkout_page.payment_success.connect(
            lambda pi_id: self._bgen_library_mgr._on_stripe_success(
                pi_id, self._bgen_library_mgr._checkout_product_id
            )
        )
        self._stripe_checkout_page.back_requested.connect(
            lambda: self.library_stack.setCurrentIndex(1)
        )

        # Push download progress/completion to WebView
        self._bgen_library_mgr.download_progress.connect(
            lambda pid, done, total: self._mkt_webview.push_download_progress(pid, done, total)
        )
        self._bgen_library_mgr.download_completed.connect(self._on_webview_download_completed)
        self._bgen_library_mgr.download_failed.connect(
            lambda pid, err: self._mkt_webview.push_download_failed(pid, err)
        )

        # Push auth state changes to WebView
        auth = AuthManager.get_instance()
        auth.auth_state_changed.connect(
            lambda is_signed_in: self._mkt_webview.push_auth_state_changed(is_signed_in)
        )

        # Add sub-pages to library stack
        self.library_stack.addWidget(my_library_widget)           # index 0
        self.library_stack.addWidget(self._mkt_webview)           # index 1
        self.library_stack.addWidget(self._stripe_checkout_page)  # index 2

        # Connect segment to stack + refresh library on BGEN Library tab
        self.library_segment.segment_changed.connect(self._on_library_tab_changed)

        library_layout.addWidget(self.library_segment)
        library_layout.addWidget(self.library_stack)

        # Page 2: Settings page
        self.settings_page = SettingsPage(
            parent_window=self,
            browse_callback=self._browse_library_path,
            open_folder_callback=self._open_library_folder,
            browse_downloads_callback=self._browse_downloads_path,
            open_downloads_callback=self._open_downloads_folder,
        )

        # Auth integration (account management is now in the web library)
        self._auth = AuthManager.get_instance()
        self._auth.auth_state_changed.connect(self._on_auth_state_changed)
        self._auth.profile_error.connect(
            lambda msg: print(f"[BGEN Picker] Warning: {msg}")
        )

        # Add pages to stack
        self.page_stack.addWidget(self.editor_page)      # index 0
        self.page_stack.addWidget(self.library_page)      # index 1
        self.page_stack.addWidget(self.settings_page)     # index 2
        self.page_stack.setCurrentIndex(0)
        #------------------------------------------------------------------------------------------------------------------------------------------------------

    def setup_layout(self):
        # Add frames to main layout
        self.main_layout.addWidget(self.main_frame)

        # Add content frame to main frame
        self.main_frame_util_layout.addWidget(self.util_frame)

        # Editor page holds the canvas and tools
        self.editor_page_layout.addSpacing(2)
        self.editor_page_layout.addWidget(self.canvas_frame)
        self.editor_page_layout.addWidget(self.tools_row_frame)
        self.editor_page_layout.addSpacing(2)

        # Body layout holds the page stack
        self.main_frame_body_layout.addWidget(self.page_stack)

        self.main_frame_layout.addLayout(self.main_frame_util_layout)
        self.main_frame_layout.addLayout(self.main_frame_body_layout)

    # ------ Bone visibility toggle -----------------------------------------------
    def _on_toggle_show_bones(self):
        TF.toggle_show_bones()
        self._sync_show_bones_state()

    def _sync_show_bones_state(self):
        """Poll Blender overlay and update button icon to match."""
        state = TF.get_show_bones_state()
        if state == self._last_bones_state:
            return
        self._last_bones_state = state
        icon = self._bones_visible_icon if state else self._bones_hidden_icon
        if icon:
            self.show_bones_button.setIcon(QtGui.QIcon(icon))

    def _on_page_changed(self, index):
        """Switch the visible page in the stacked widget."""
        self.page_stack.setCurrentIndex(index)
        if index == 1:
            # Defer relayout so Qt processes the page switch geometry first
            if self.library_controller:
                self.library_controller._last_col_count = 0
                self.library_controller.catch_up_if_needed()
                QtCore.QTimer.singleShot(0, self.library_controller._relayout)
        elif index == 2 and hasattr(self, 'settings_page'):
            self.settings_page.on_page_shown()

    def _on_library_tab_changed(self, index):
        """Handle My Library / BGEN Library tab switch."""
        self.library_stack.setCurrentIndex(index)
        if index == 1:
            # Lazy-load the library WebView on first visit
            self._mkt_webview.load_library()

    def _on_checkout_ready(self, stripe_data, product_id):
        """Open the embedded Stripe checkout page when a PaymentIntent is ready."""
        self._stripe_checkout_page.load_checkout(
            publishable_key=stripe_data.get("publishable_key", ""),
            client_secret=stripe_data.get("client_secret", ""),
            customer_session_secret=stripe_data.get("customer_session_secret", ""),
            product_name=stripe_data.get("product_name", ""),
            price_cents=stripe_data.get("price_cents", 0),
        )
        self.library_stack.setCurrentIndex(2)

    def _on_webview_download_completed(self, product_id, path):
        """Handle download completion — notify webview and refresh library."""
        self._mkt_webview.push_download_complete(product_id, path)
        if hasattr(self, 'library_controller') and self.library_controller:
            self.library_controller.refresh()

    def _on_feature_flags_loaded(self, flags):
        """Handle feature flag updates (logging only — web library handles gating)."""
        pass

    def _on_auth_state_changed(self, signed_in: bool):
        """Handle auth state transitions from AuthManager."""
        # Web library handles account UI; just push state to webview
        pass

    def setup_connections(self):
        # Connect close button
        self.close_button.clicked.connect(self.close)
        self.main_frame.installEventFilter(self)
        self.main_frame.setMouseTracking(True)
        # Track canvas_frame resizes to reposition the edit panel overlay
        self.canvas_frame.installEventFilter(self)

        self.add_image.clicked.connect(self.select_image_for_current_tab)
        self.remove_image.clicked.connect(self.remove_image_from_current_tab)
        self.capture_bg_button.clicked.connect(self.capture_background_for_current_tab)
        self.image_opacity_slider.valueChanged.connect(self.update_image_opacity)
        self.add_picker_button.clicked.connect(self.add_new_picker_button)
        
        self.image_scale_factor.valueChanged.connect(self.update_image_scale)
        self.namespace_dropdown.currentTextChanged.connect(self.on_namespace_changed)
        self.namespace_dropdown.requestContextMenu.connect(self._show_namespace_context_menu)
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

        # Save shortcut
        self.save_shortcut = QShortcut(QtGui.QKeySequence("Ctrl+S"), self)
        self.save_shortcut.activated.connect(self.save_current_picker)

        # Install global event filter for hover-based Tab key handling
        self.installEventFilter(self)
        

        
        # Enable key event handling even when window doesn't have focus
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        
        # Track Tab key state to prevent multiple triggers
        self.tab_key_pressed = False
        
        # Keep the original Tab shortcut for when window has focus
        self.tab_key_pressed = False

        self.setup_scene_update_timer()
    
    def resize_window_min(self):
        """Resize window to minimum size (200x200)"""
        self._programmatic_resize = True
        
        # Store current position for the current size mode before switching
        self._store_current_position()
        
        # Restore stored position for min mode if available, otherwise keep current position
        if self.stored_positions['min'] is not None:
            pos = self.stored_positions['min']
            self.setGeometry(pos.x(), pos.y(), 200, 200)
        else:
            self.resize(200, 200)
        
        # Update current size mode
        self.current_size_mode = 'min'
        
        # Reset fullscreen state since we're manually setting size
        self.is_fullscreen = False
        self.pre_fullscreen_geometry = None
        self.update_buttons_for_current_tab(force_update=True)
        if not self.edit_mode:
            UT.blender_main_window()
    
    def resize_window_mid(self):
        """Resize window to medium size (350x450)"""
        self._programmatic_resize = True

        # Store current position for the current size mode before switching
        self._store_current_position()

        new_width = 350

        # Restore stored position for mid mode if available, otherwise keep current position
        if self.stored_positions['mid'] is not None:
            pos = self.stored_positions['mid']
            self.setGeometry(pos.x(), pos.y(), new_width, 450)
        else:
            self.resize(new_width, 450)
        
        # Update current size mode
        self.current_size_mode = 'mid'
        
        # Reset fullscreen state since we're manually setting size
        self.is_fullscreen = False
        self.pre_fullscreen_geometry = None
        self.update_buttons_for_current_tab(force_update=True)
        if not self.edit_mode:
            UT.blender_main_window()
    
    def resize_window_full(self):
        """Maximize window to full screen (always maximizes, does not toggle)"""
        self._programmatic_resize = True
        
        # Store current position for the current size mode before switching
        self._store_current_position()
        
        # Store current geometry if not already in fullscreen
        if not self.is_fullscreen:
            self.pre_fullscreen_geometry = self.geometry()
        
        # Get the screen that the window is currently on
        current_screen = QApplication.screenAt(self.mapToGlobal(self.rect().center()))
        if not current_screen:
            # Fallback to primary screen if detection fails
            current_screen = QApplication.primaryScreen()
        
        screen_geometry = current_screen.availableGeometry()
        
        # Calculate the size for full screen (leaving some margin)
        margin = 50
        full_width = screen_geometry.width() - (margin * 2)
        full_height = screen_geometry.height() - (margin * 2)
        
        # Position to center the window on the current screen
        x = screen_geometry.x() + margin
        y = screen_geometry.y() + margin
        
        # Set the geometry (position and size)
        self.setGeometry(x, y, full_width, full_height)
        self.is_fullscreen = True
        self.current_size_mode = 'full'
        
        self.update_buttons_for_current_tab(force_update=True)
        
        if not self.edit_mode:
            UT.blender_main_window()
    
    def _store_current_position(self):
        """Store the current window position for the current size mode"""
        if self.current_size_mode in ('min', 'mid'):
            self.stored_positions[self.current_size_mode] = self.pos()
    #----------------------------------------------------------------------------------------------------------------------------------------
    def _get_active_canvas(self):
        """Get the canvas for the currently active tab."""
        if not self.tab_system.current_tab:
            return None
        tab_data = self.tab_system.tabs.get(self.tab_system.current_tab)
        return tab_data['canvas'] if tab_data else None

    def undo_action(self):
        """Perform undo operation"""
        try:
            # If curve editing is active, delegate to curve editor's internal undo
            canvas = self._get_active_canvas()
            if canvas and hasattr(canvas, 'curve_editor') and canvas.curve_editor.is_editing():
                if canvas.curve_editor.state.undo():
                    canvas.curve_editor.controls.set_mirror_enabled(
                        canvas.curve_editor.state.mirror_state.enabled)
                    canvas.curve_editor.update()
                return

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
            # If curve editing is active, delegate to curve editor's internal redo
            canvas = self._get_active_canvas()
            if canvas and hasattr(canvas, 'curve_editor') and canvas.curve_editor.is_editing():
                if canvas.curve_editor.state.redo():
                    canvas.curve_editor.controls.set_mirror_enabled(
                        canvas.curve_editor.state.mirror_state.enabled)
                    canvas.curve_editor.update()
                return

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
    
    def _cancel_active_curve_editing(self):
        """Cancel any active curve editing to prevent conflicts with undo/redo."""
        if not self.tab_system.current_tab:
            return
        
        current_tab = self.tab_system.current_tab
        if current_tab not in self.tab_system.tabs:
            return
        
        canvas = self.tab_system.tabs[current_tab]['canvas']
        if hasattr(canvas, 'curve_editor') and canvas.curve_editor.is_editing():
            curve_editor = canvas.curve_editor
            
            # CRITICAL: Restore button opacities and visibility BEFORE cleaning up
            # This ensures buttons return to their original state
            curve_editor._restore_button_opacities()
            
            # Hide curve editor UI
            curve_editor.setVisible(False)
            if hasattr(curve_editor, 'controls'):
                curve_editor.controls.setVisible(False)
            
            # Clean up curve editor state
            curve_editor.target_button = None
            curve_editor.state.current_shape = None
            curve_editor.state.original_shape = None
            curve_editor.state.clear_selection()
            curve_editor.state.clear_undo_history()
            curve_editor.pen_tool._reset_drawing_state()
            curve_editor.hover_hit = None
            
            # Update canvas to reflect restored button states
            canvas.update()
    
    def save_undo_for_curve_edit(self, button):
        """Save undo state after curve editing operation."""
        if not self.tab_system.current_tab:
            return
        
        # Get selected button IDs for undo restore
        selected_button_ids = [button.unique_id] if button else []
        
        # Save the undo state with the curve edit operation
        DM.PickerDataManager.save_undo_state(
            operation_name="Edit Curve Shape",
            selected_button_ids=selected_button_ids
        )
    
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
        """Create buttons and restore selection from undo/redo.

        Works with both the sync and async (chunked) paths —
        selection is restored after all buttons are created.
        """
        # Invalidate cache so buttons are fully recreated
        if self.tab_system.current_tab:
            self._tab_button_versions.pop(self.tab_system.current_tab, None)

        # Store selection IDs — _finalize_button_load / _create_buttons_sync
        # will call _restore_selection_by_ids after all buttons exist.
        self._pending_restore_selection = selected_button_ids
        self.create_buttons()
    
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
    def _save_canvas_view_state(self):
        """Save the current canvas pan/zoom to tab data.

        Writes directly to the data dict and saves without creating an undo
        snapshot, since pan/zoom is a view operation not a data edit.
        """
        tab_name = self.tab_system.current_tab
        if not tab_name:
            return
        canvas = self.tab_system.tabs.get(tab_name, {}).get('canvas')
        if not canvas:
            return
        data = DM.PickerDataManager.get_data()
        if tab_name not in data.get('tabs', {}):
            return
        data['tabs'][tab_name]['pan_offset_x'] = canvas.pan_offset.x()
        data['tabs'][tab_name]['pan_offset_y'] = canvas.pan_offset.y()
        data['tabs'][tab_name]['zoom_factor'] = canvas.zoom_factor
        # View state is persisted in Blender scene only — no need to repack
        # the bpicker archive, so skip session dirty notification.
        DM.PickerDataManager.save_data(data, force_immediate=True, notify_session=False)

        # Schedule a lightweight live preview update for the library card
        if self.session:
            self.session.schedule_preview_update()

    def connect_canvas_signals(self, canvas):
        """ENHANCED signal connection with proper cleanup"""
        # Disconnect ALL existing connections first (guard each individually)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            for sig in (canvas.button_selection_changed, canvas.clicked, canvas.view_changed):
                try:
                    sig.disconnect()
                except (RuntimeError, TypeError):
                    pass

            # Clear any existing button connections
            for button in canvas.buttons:
                try:
                    button.changed.disconnect()
                except (RuntimeError, TypeError):
                    pass
        
        # Re-connect with fresh connections
        canvas.button_selection_changed.connect(self.update_edit_widgets_delayed)
        canvas.clicked.connect(self.clear_line_edit_focus)
        canvas.view_changed.connect(self._save_canvas_view_state)

        # Re-connect transform guides (disconnected above by blanket disconnect)
        if hasattr(canvas, 'transform_guides'):
            canvas.button_selection_changed.connect(
                canvas.transform_guides.update_selection
            )

        # Re-connect selection sync manager
        from . import selection_sync_manager as SSM
        SSM.reconnect_canvas(canvas)
        
        # Connect button signals
        for button in canvas.buttons:
            button.changed.connect(self.on_button_changed) 

    def info(self):
        # Opens link to Manual
        import webbrowser
        webbrowser.open('https://m2ky.com/dev/tools/bgen-picker?tab=manual')
        print(f'BGEN Picker {anim_picker_version}')
     
    def toggle_edit_mode(self):
        self.edit_controller.toggle()
        self.edit_mode = self.edit_controller.is_active

    def _animate_edit_mode_width(self):
        """Smoothly expand/contract the window so the canvas stays usable in edit mode."""
        panel_width = self.canvas_edit_panel.width()
        canvas_width = self.canvas_frame.width()
        geo = self.geometry()

        # The visible canvas area after the panel overlays
        visible_canvas = canvas_width - panel_width
        # We want at least 40% of the canvas to remain visible
        min_visible_ratio = 0.55
        min_visible_px = canvas_width * min_visible_ratio

        if self.edit_mode and visible_canvas < min_visible_px:
            # Canvas is too narrow — expand the window to give enough room
            needed_extra = int(panel_width * 1.1)
            target_width = geo.width() + needed_extra
            # Store how much we added so we can undo it later
            self._edit_mode_width_delta = needed_extra
        elif not self.edit_mode and hasattr(self, '_edit_mode_width_delta') and self._edit_mode_width_delta > 0:
            # Leaving edit mode — shrink back
            target_width = max(200, geo.width() - self._edit_mode_width_delta)
            self._edit_mode_width_delta = 0
        else:
            # No resize needed
            if self.edit_mode:
                self._edit_mode_width_delta = 0
            return

        self._programmatic_resize = True
        self._run_width_animation(geo, target_width)

    def _run_width_animation(self, geo, target_width):
        """Animate the window width from current to target."""
        # Stop any running animation
        if hasattr(self, '_width_anim') and self._width_anim is not None:
            self._width_anim.stop()

        start_w = geo.width()
        if start_w == target_width:
            return

        anim = QtCore.QVariantAnimation(self)
        anim.setStartValue(float(start_w))
        anim.setEndValue(float(target_width))
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        x, y, h = geo.x(), geo.y(), geo.height()

        def on_value_changed(val):
            w = int(val)
            self.setGeometry(x, y, w, h)

        def on_finished():
            self._programmatic_resize = False
            self.update_buttons_for_current_tab(force_update=True)

        anim.valueChanged.connect(on_value_changed)
        anim.finished.connect(on_finished)
        self._width_anim = anim
        anim.start()
    
    #----------------------------------------------------------------------------------------------------------------------------------------
    # Edit Panel Resize Handler
    #----------------------------------------------------------------------------------------------------------------------------------------
    def _on_edit_panel_width_changed(self, new_width):
        """Handle edit panel width changes for UI updates."""
        self.efw = new_width
        # Keep HUD and curve editor controls clear of the edit panel
        current_canvas = self.tab_system.tabs.get(self.tab_system.current_tab, {}).get('canvas')
        if current_canvas:
            current_canvas.update_hud_geometry()
            if hasattr(current_canvas, 'curve_editor') and current_canvas.curve_editor.isVisible():
                current_canvas.curve_editor._update_controls_position()

    def _update_border_overlay_position(self):
        """No-op — border is now drawn in canvas paintEvent."""
        pass

    #----------------------------------------------------------------------------------------------------------------------------------------
    def update_anim_picker(self):
        """Navigate to Settings > Updates section."""
        self.page_segment.set_selected_index(2)
        self._on_page_changed(2)
        self.settings_page.set_section(1)

    def update_anim_picker_checker(self):
        from .update_manager import UpdateManager
        mgr = UpdateManager.get_instance()
        # Connect signals if not already connected
        if not hasattr(self, '_update_signals_connected'):
            mgr.update_available.connect(self._on_update_available)
            mgr.no_update.connect(self._on_no_update)
            mgr.update_check_failed.connect(self._on_update_check_failed)
            self._update_signals_connected = True
        mgr.check_for_update()

    def _on_update_available(self, release):
        try:
            self.info_util.set_notification(state=True)
            self.info_util.set_menu_item_notification("Update", state=True)
            self.page_segment.set_notification(2, state=True, color="#1D65CA")
            # Show banner (unless user dismissed this version during this session)
            version = release.get("version", "")
            is_critical = release.get("is_critical", False)
            if is_critical or not self.update_banner.is_dismissed_this_session(version):
                self.update_banner.show_update(release)
            else:
                self.update_banner.hide_banner()
        except Exception as e:
            print(f"Error showing update notification: {e}")

    def _on_no_update(self, current_version):
        try:
            self.info_util.set_notification(state=False)
            self.info_util.set_menu_item_notification("Update", state=False)
            self.page_segment.set_notification(2, state=False)
            self.update_banner.hide_banner()
        except Exception as e:
            print(f"Error clearing update notification: {e}")

    def _on_update_check_failed(self, error_msg):
        try:
            self.page_segment.set_notification(2, state=False)
        except Exception:
            pass 
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

    def _ensure_window_hidden(self, force=False):
        """Ensure window is hidden when not needed (called by centralized manager)"""
        import sys
        if sys.platform == "darwin" and not force:
            return  # On macOS, Qt.Tool windows hide/show with the app natively
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
    def export_picker(self):
        """Export current tab or all tabs as a .bpicker file to disk."""
        # Choose current tab vs all tabs
        save_mode = PIO.get_save_mode_dialog()
        if save_mode == 'cancel':
            return

        current_tab_name = self.tab_system.current_tab if hasattr(self, 'tab_system') else None

        if save_mode == 'current':
            if not current_tab_name:
                QtWidgets.QMessageBox.warning(
                    self, "No Current Tab",
                    "No current tab is available to export. Please select a tab first.",
                )
                return
            default_filename = f"{current_tab_name}.bpicker"
        else:
            name = "picker_data"
            if self.session and self.session.metadata:
                name = self.session.metadata.get('picker_name', name)
            default_filename = f"{name}.bpicker"

        start_directory = PIO.get_file_dialog_directory()
        default_path = os.path.join(start_directory, default_filename)

        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export Picker", default_path, "BPicker Files (*.bpicker)",
        )
        if not file_path:
            return

        try:
            if save_mode == 'current':
                success = PIO.export_tab_as_bpicker(current_tab_name, file_path)
            else:
                success = PIO.export_all_as_bpicker(file_path)

            if success:
                self.show_blender_message(
                    f"Exported to {os.path.basename(file_path)}"
                )
            else:
                QtWidgets.QMessageBox.warning(self, "Export Failed", "No data to export.")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))
                
    def import_picker(self):
        """Import a .bpicker or legacy .json file, with merge or open-as-new."""
        start_directory = DM.PickerDataManager.get_global_settings().get(
            'last_picker_file_path', ''
        )
        if not start_directory or not os.path.exists(start_directory):
            start_directory = PIO.get_file_dialog_directory()

        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Import Picker", start_directory,
            "Picker Files (*.bpicker *.json);;BPicker Files (*.bpicker);;JSON Files (*.json)",
        )
        if not file_path:
            return

        DM.PickerDataManager.update_global_settings(
            last_picker_file_path=os.path.dirname(file_path)
        )

        self._import_picker_file(file_path)

    def _import_picker_file(self, file_path):
        """Core import logic shared by import_picker() and dropEvent()."""
        from .local_file_manager import LocalFileManager
        ext = os.path.splitext(file_path)[1].lower()
        picker_uuid = None

        if ext == '.bpicker':
            picker_uuid = PIO.import_bpicker_to_library(file_path)
        elif ext == '.json':
            picker_uuid = PIO.import_legacy_json_to_bpicker(file_path)

        if not picker_uuid:
            if ext == '.json':
                # Fallback to legacy direct load
                self._load_picker_from_file(file_path)
            else:
                QtWidgets.QMessageBox.warning(
                    self, "Import Failed",
                    f"Could not import {os.path.basename(file_path)}.",
                )
            return

        # Ask user: merge or open as new
        import_mode = PIO.get_import_mode_dialog(has_session=bool(self.session))

        if import_mode == 'cancel':
            return

        if import_mode == 'merge' and self.session:
            # Merge tabs from the imported bpicker into current session
            lib_path = LocalFileManager.get_picker_path(picker_uuid)
            if lib_path:
                imported_tabs = PIO.import_tabs_from_bpicker(str(lib_path))
                if imported_tabs:
                    self._rebuild_ui_from_data()
                    self.show_blender_message(
                        f"Merged {len(imported_tabs)} tab(s) from "
                        f"{os.path.basename(file_path)}"
                    )
                else:
                    self.show_blender_message("No tabs were imported.")
            else:
                QtWidgets.QMessageBox.warning(
                    self, "Error", "Could not locate imported picker in library.",
                )
        else:
            # Open as new session
            self.open_picker_from_library(picker_uuid)
            self.show_blender_message(
                f"Opened {os.path.basename(file_path)}"
            )

        # Refresh library grid
        if self.library_controller:
            self.library_controller.refresh()

    def _import_tab_from_library(self, uuid, tab_name):
        """Import a single tab from a library picker into the current session."""
        from .local_file_manager import LocalFileManager
        if not self.session:
            return
        lib_path = LocalFileManager.get_picker_path(uuid)
        if not lib_path:
            QtWidgets.QMessageBox.warning(
                self, "Error", "Could not locate picker in library.",
            )
            return
        imported = PIO.import_tab_from_bpicker(str(lib_path), tab_name)
        if imported:
            self._rebuild_ui_from_data()
            self.show_blender_message(f"Imported tab '{imported[0]}'")
        else:
            self.show_blender_message(f"Tab '{tab_name}' was not imported.")

    def _load_picker_from_file(self, file_path):
        """OPTIMIZED: Load picker data from a file path with proper cleanup"""
        try:
            from . import picker_io
            
            # OPTIMIZATION: Clear all existing tabs and canvases BEFORE loading
            # This prevents old data from accumulating
            self.tab_system.clear_all_tabs()
            
            # OPTIMIZATION: Remove all widgets from canvas stack
            while self.canvas_stack.count() > 0:
                widget = self.canvas_stack.widget(0)
                self.canvas_stack.removeWidget(widget)
                if widget:
                    widget.setParent(None)
                    widget.deleteLater()
            
            # OPTIMIZATION: Force Qt to process pending deletions
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            
            # Now load the picker data (this includes cache/undo cleanup internally)
            picker_io.load_picker_data(file_path)
            
            # CRITICAL FIX: Get the loaded data to determine which tabs were loaded
            loaded_data = DM.PickerDataManager.get_data()
            
            if not loaded_data['tabs']:
                QtWidgets.QMessageBox.warning(self, "Warning", "No valid tab data found in the file.")
                return False

            # OPTIMIZATION: Reload data from Blender to ensure fresh state
            DM.PickerDataManager.reload_data_from_blender()

            # Setup tabs from loaded data
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
            
            # OPTIMIZATION: Perform comprehensive cleanup after loading
            self._cleanup_data_structures()
            
            # OPTIMIZATION: Force update to ensure clean state
            self.update()
            QApplication.processEvents()
            
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
        """Handle drop events for picker data files (.json and .bpicker)"""
        # Reset visual feedback
        if self.drag_highlight_active:
            self.drag_highlight_active = False
            self.util_frame.setStyleSheet(f'''QFrame {{border: 0px solid gray;}}''')
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if self._is_valid_picker_file(file_path):
                    self._import_picker_file(file_path)
                    event.acceptProposedAction()
                    return
        event.ignore()
    
    def _is_valid_picker_file(self, file_path):
        """Check if the file is a valid picker data file (.json or .bpicker)"""
        if not os.path.isfile(file_path):
            return False

        _, ext = os.path.splitext(file_path)
        if not ext:
            return False

        ext_lower = ext.lower()

        # Accept .bpicker files
        if ext_lower == '.bpicker':
            return True

        # Accept .json files with picker structure
        if ext_lower == '.json':
            try:
                with open(file_path, 'r') as f:
                    import json
                    data = json.load(f)
                    return 'tabs' in data
            except Exception:
                return False

        return False

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
        """Setup depsgraph handler to detect scene armature changes.

        Performance: in heavy scenes the depsgraph fires many times per second.
        The hot path here must be O(1). We use a length-based pre-filter so the
        full armature-name scan only runs when scene.objects membership changes,
        and we short-circuit entirely when no picker window is visible.
        """
        import bpy
        import weakref
        from . import blender_main as BM

        # Cache current armature names for cheap comparison in the handler
        self._cached_armature_names = self._get_scene_armature_names()
        self._cached_scene_object_count = -1
        self._scene_tick_counter = 0
        try:
            self._cached_scene_object_count = len(bpy.context.scene.objects)
        except Exception:
            pass

        # Debounce timer for batching rapid scene updates
        self._scene_change_timer = QtCore.QTimer(self)
        self._scene_change_timer.setSingleShot(True)
        self._scene_change_timer.timeout.connect(self.check_scene_for_updates)

        _self_ref = weakref.ref(self)

        def _on_depsgraph_update_scene(scene, depsgraph):
            s = _self_ref()
            if s is None:
                return
            # Gate 1: skip all work when the picker is not on screen.
            if not BM.is_any_picker_visible():
                return
            try:
                # Gate 2: cheap O(1) length check. If the scene's object count
                # hasn't changed, membership hasn't changed either — skip the
                # full type-iteration (which is O(N) and expensive in heavy scenes).
                count = len(scene.objects)
                # Every ~120 ticks (~2-5s of activity) force a full scan anyway
                # so armature renames are picked up. Cheap because we only do
                # the scan itself, not every tick.
                s._scene_tick_counter += 1
                force_scan = s._scene_tick_counter >= 120
                if count == s._cached_scene_object_count and not force_scan:
                    return
                s._cached_scene_object_count = count
                if force_scan:
                    s._scene_tick_counter = 0

                # Only now do the full armature-name scan (still cheap relative
                # to running it every tick).
                current = s._get_scene_armature_names()
                if current != s._cached_armature_names:
                    s._cached_armature_names = current
                    if not s._scene_change_timer.isActive():
                        s._scene_change_timer.start(300)
            except Exception:
                pass

        _on_depsgraph_update_scene._bpy_persistent = True
        self._scene_depsgraph_fn = _on_depsgraph_update_scene
        bpy.app.handlers.depsgraph_update_post.append(self._scene_depsgraph_fn)

    def _get_scene_armature_names(self):
        """Return a frozenset of armature object names in the current scene"""
        import bpy
        try:
            return frozenset(
                obj.name for obj in bpy.context.scene.objects
                if obj.type == 'ARMATURE'
            )
        except Exception:
            return frozenset()

    def check_scene_for_updates(self):
        """Update namespace dropdown when scene armatures have changed"""
        self.update_namespace_dropdown()

    def on_namespace_changed(self, namespace_text):
        """Handle namespace dropdown change"""
        if not self.tab_system.current_tab:
            return

        current_tab = self.tab_system.current_tab

        # Update the namespace in the data manager for this tab
        DM.PickerDataManager.update_tab_namespace(current_tab, namespace_text)

        #print(f"Tab '{current_tab}' namespace changed to: {namespace_text}")

    def _show_namespace_context_menu(self, global_pos):
        """Build the right-click context menu for the namespace dropdown.

        Lets the user toggle 'Show Pinned Only' (which filters the dropdown
        and turns the border #1d65ca) and check/uncheck which scene armatures
        are pinned. Per-tab state.
        """
        current_tab = self.tab_system.current_tab
        if not current_tab:
            return

        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        filter_mode = bool(tab_data.get('namespace_filter_mode', False))
        pinned = list(tab_data.get('pinned_namespaces', []) or [])
        scene_rigs = sorted(self._get_scene_armature_names())

        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2a; color: #dddddd;
                border: 1px solid #3a3a3a; border-radius: 4px; padding: 4px;
            }
            QMenu::item { padding: 5px 20px; border-radius: 3px; }
            QMenu::item:selected { background-color: rgba(29,101,202,0.4); }
            QMenu::separator { height: 1px; background: #3a3a3a; margin: 4px 6px; }
        """)

        # 1. Show Pinned Only — checkable, applies immediately, closes menu
        toggle_action = menu.addAction("Show Pinned Only")
        toggle_action.setCheckable(True)
        toggle_action.setChecked(filter_mode)
        toggle_action.triggered.connect(
            lambda checked: self._on_namespace_filter_toggled(bool(checked))
        )

        menu.addSeparator()

        # 2. Quick actions
        pin_all = menu.addAction("Pin All")
        pin_all.setEnabled(bool(scene_rigs))
        pin_all.triggered.connect(lambda: self._on_pin_all_namespaces(scene_rigs))

        clear_all = menu.addAction("Clear Pins")
        clear_all.setEnabled(bool(pinned))
        clear_all.triggered.connect(self._on_clear_pinned_namespaces)

        menu.addSeparator()

        # 3. Per-armature checkboxes (QWidgetAction so toggling stays open)
        if not scene_rigs:
            empty = menu.addAction("No rigs in scene")
            empty.setEnabled(False)
        else:
            for name in scene_rigs:
                cb = QtWidgets.QCheckBox(name)
                cb.setChecked(name in pinned)
                cb.setStyleSheet(
                    "QCheckBox { color: #dddddd; padding: 4px 20px; background: transparent; }"
                    "QCheckBox:hover { background-color: rgba(29,101,202,0.4); border-radius: 3px; }"
                    "QCheckBox::indicator { width: 12px; height: 12px; }"
                )
                cb.toggled.connect(
                    lambda checked, n=name: self._on_pinned_namespace_toggled(n, checked)
                )
                wa = QtWidgets.QWidgetAction(menu)
                wa.setDefaultWidget(cb)
                menu.addAction(wa)

        menu.exec_(global_pos)

    def _on_namespace_filter_toggled(self, enabled):
        if not self.tab_system.current_tab:
            return
        DM.PickerDataManager.update_tab_namespace_filter_mode(
            self.tab_system.current_tab, enabled
        )
        # Refresh dropdown contents + border
        self.update_namespace_dropdown()

    def _on_pin_all_namespaces(self, scene_rigs):
        if not self.tab_system.current_tab:
            return
        DM.PickerDataManager.update_tab_pinned_namespaces(
            self.tab_system.current_tab, list(scene_rigs)
        )
        self.update_namespace_dropdown()

    def _on_clear_pinned_namespaces(self):
        if not self.tab_system.current_tab:
            return
        DM.PickerDataManager.update_tab_pinned_namespaces(
            self.tab_system.current_tab, []
        )
        self.update_namespace_dropdown()

    def _on_pinned_namespace_toggled(self, name, checked):
        if not self.tab_system.current_tab:
            return
        tab_data = DM.PickerDataManager.get_tab_data(self.tab_system.current_tab)
        pinned = list(tab_data.get('pinned_namespaces', []) or [])
        if checked and name not in pinned:
            pinned.append(name)
        elif not checked and name in pinned:
            pinned.remove(name)
        else:
            return
        DM.PickerDataManager.update_tab_pinned_namespaces(
            self.tab_system.current_tab, pinned
        )
        # Live-refresh dropdown so filtered list updates without closing menu
        self.update_namespace_dropdown()


    def update_namespace_dropdown_width(self):
        """Calculate and set optimal width for namespace dropdown based on content"""
        # Use QFontMetrics to measure text width
        font_metrics = QtGui.QFontMetrics(self.namespace_dropdown.font())
        
        max_width = 40  # Start with minimum width
        
        # Measure width of each item
        for i in range(self.namespace_dropdown.count()):
            item_text = self.namespace_dropdown.itemText(i)
            text_width = font_metrics.horizontalAdvance(item_text)
            # Add padding for dropdown arrow, margins, and padding (approximately 35 pixels)
            total_width = text_width + 35
            max_width = max(max_width, total_width)
        
        # Constrain between minimum (40) and maximum (120)
        optimal_width = min(max(max_width, 40), 120)
        
        # Set the fixed width
        self.namespace_dropdown.setFixedWidth(optimal_width)
    
    def populate_namespace_dropdown(self):
        """Populate namespace dropdown with rigs (armature objects) in the scene.

        If the current tab has 'namespace_filter_mode' enabled, the list is
        narrowed to 'pinned_namespaces' (intersected with the actual scene
        contents). The currently-selected namespace is always kept visible
        even if it isn't pinned, so the user never silently loses it.
        """
        import bpy

        # Resolve filter state from the current tab (if any)
        filter_mode = False
        pinned = []
        current_namespace = 'None'
        if self.tab_system.current_tab:
            tab_data = DM.PickerDataManager.get_tab_data(self.tab_system.current_tab)
            filter_mode = bool(tab_data.get('namespace_filter_mode', False))
            pinned = list(tab_data.get('pinned_namespaces', []) or [])
            current_namespace = tab_data.get('namespace', 'None') or 'None'

        # Block signals during population to prevent unwanted triggers
        self.namespace_dropdown.blockSignals(True)

        try:
            with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
                # Clear existing items
                self.namespace_dropdown.clear()

                # Add default "None" option
                self.namespace_dropdown.addItem('None')

                # Get all armature objects in the scene
                scene_rigs = [
                    obj.name for obj in bpy.context.scene.objects
                    if obj.type == 'ARMATURE'
                ]
                scene_set = set(scene_rigs)

                if filter_mode:
                    # Pinned ∩ scene, plus current selection if it's a real
                    # armature missing from the pinned set (preserve selection)
                    visible = [n for n in pinned if n in scene_set]
                    if (current_namespace
                            and current_namespace != 'None'
                            and current_namespace in scene_set
                            and current_namespace not in visible):
                        visible.append(current_namespace)
                    rig_names = sorted(set(visible))
                else:
                    rig_names = sorted(scene_rigs)

                for rig_name in rig_names:
                    self.namespace_dropdown.addItem(rig_name)

                # Update dropdown width based on content
                self.update_namespace_dropdown_width()
        finally:
            # Always re-enable signals
            self.namespace_dropdown.blockSignals(False)

    def update_namespace_dropdown(self):
        """Update the namespace dropdown when scene changes"""
        # Get the namespace stored in the current tab's data (not just UI state)
        if self.tab_system.current_tab:
            tab_data = DM.PickerDataManager.get_tab_data(self.tab_system.current_tab)
            stored_namespace = tab_data.get('namespace', 'None')
            filter_mode = bool(tab_data.get('namespace_filter_mode', False))
        else:
            stored_namespace = 'None'
            filter_mode = False

        # Reflect the current tab's filter mode on the dropdown border
        if hasattr(self.namespace_dropdown, 'set_filter_mode_style'):
            self.namespace_dropdown.set_filter_mode_style(filter_mode)

        # Block signals during update
        self.namespace_dropdown.blockSignals(True)
        
        # Repopulate dropdown
        self.populate_namespace_dropdown()
        
        # Try to restore the stored namespace selection
        index = self.namespace_dropdown.findText(stored_namespace)
        if index >= 0:
            self.namespace_dropdown.setCurrentIndex(index)
            #print(f"update_namespace_dropdown: Successfully restored namespace '{stored_namespace}' at index {index}")
        else:
            # Default to None if stored namespace no longer exists in scene
            self.namespace_dropdown.setCurrentIndex(0)
            #print(f"update_namespace_dropdown: Stored namespace '{stored_namespace}' not found in scene, resetting to 'None'")
            # Update the tab data to reflect this change
            if self.tab_system.current_tab:
                DM.PickerDataManager.update_tab_namespace(self.tab_system.current_tab, 'None')
        
        # Re-enable signals
        self.namespace_dropdown.blockSignals(False)
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

    # --------------------------------------------------------------------------
    # Button creation (chunked with loading overlay)
    # --------------------------------------------------------------------------
    def _create_single_button(self, button_data, canvas, tab_name):
        """Create and configure a single PickerButton from data dict."""
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

        button.radius = button_data.get("radius", [3, 3, 3, 3])
        button.rotation = button_data.get("rotation", 0)
        button.assigned_objects = button_data.get("assigned_objects", [])
        button.mode = button_data.get("mode", "select")

        button.text_color = button_data.get("text_color", "#ffffff")
        button.text_bold = button_data.get("text_bold", False)
        button.text_italic = button_data.get("text_italic", False)
        button.text_underline = button_data.get("text_underline", False)

        script_data = button_data.get("script_data", {})
        if isinstance(script_data, dict):
            button.script_data = script_data
        else:
            button.script_data = {
                'code': str(script_data),
                'type': 'python'
            }

        button.pose_data = button_data.get("pose_data", {})
        button.animation_data = button_data.get("animation_data", {})
        button.controller_data = button_data.get("controller_data", {})

        # Start controller sync if mode is controller with a valid path
        if button.mode == 'controller' and button.controller_data.get('data_path'):
            val = button._read_controller_value()
            if val is not None:
                button._controller_value = val
            else:
                button._controller_value = button.controller_data.get('default_value', 0.0)
            button._start_controller_sync()

        if button_data.get("thumbnail_path"):
            stored_thumbnail_path = button_data["thumbnail_path"]
            button.thumbnail_path = stored_thumbnail_path
            try:
                resolved_path = DM.PickerDataManager.resolve_image_path(
                    stored_thumbnail_path, tab_name
                )
                if resolved_path and os.path.exists(resolved_path):
                    button.thumbnail_pixmap = QtGui.QPixmap(resolved_path)
                    if button.thumbnail_pixmap.isNull():
                        button.thumbnail_pixmap = None
                else:
                    button.thumbnail_pixmap = None
            except Exception as e:
                print(f"Warning: Error resolving thumbnail path '{stored_thumbnail_path}': {e}")
                button.thumbnail_pixmap = None
        else:
            button.thumbnail_pixmap = None

        button.scene_position = QtCore.QPointF(*button_data["position"])
        button.update_tooltip()
        return button

    def create_buttons(self):
        """Create buttons for the active tab. Uses chunked loading for large sets."""
        if not self.tab_system.current_tab:
            return

        self._cancel_button_load()

        current_tab = self.tab_system.current_tab
        self.initialize_tab_data(current_tab)
        canvas = self.tab_system.tabs[current_tab]['canvas']

        # Show loading overlay immediately — before clearing or creating anything.
        # This gives a clean loading state instead of showing buttons popping in.
        canvas.loading_overlay.show_overlay()

        # Suppress canvas repaints while buttons are being swapped out
        canvas.setUpdatesEnabled(False)

        # Clear existing buttons
        for button in canvas.buttons[:]:
            button.setParent(None)
            button.deleteLater()
        canvas.buttons.clear()

        tab_data = DM.PickerDataManager.get_tab_data(current_tab)
        button_data_list = tab_data.get('buttons', [])

        if len(button_data_list) <= self._chunk_size:
            # Small set — synchronous
            self._create_buttons_sync(canvas, button_data_list, current_tab)
        else:
            # Large set — chunked with loading overlay
            self._button_load_tab = current_tab
            self._button_load_canvas = canvas
            self._button_load_gen = self._button_chunk_generator(
                canvas, button_data_list, current_tab
            )
            # Re-enable updates so the overlay animates while chunks load
            canvas.setUpdatesEnabled(True)
            self._process_next_button_chunk()

    def _cancel_button_load(self):
        """Cancel any in-progress chunked button load."""
        if self._button_load_canvas is not None:
            try:
                self._button_load_canvas.setUpdatesEnabled(True)
                self._button_load_canvas.loading_overlay.hide_overlay()
            except RuntimeError:
                pass
        self._button_load_gen = None
        self._button_load_tab = None
        self._button_load_canvas = None

    def _button_chunk_generator(self, canvas, button_data_list, tab_name):
        """Yield chunks of button data for progressive creation."""
        for i in range(0, len(button_data_list), self._chunk_size):
            yield button_data_list[i:i + self._chunk_size]

    def _process_next_button_chunk(self):
        """Process the next chunk of buttons from the generator."""
        if self._button_load_gen is None:
            return

        # Tab changed during load — abort
        if self._button_load_tab != self.tab_system.current_tab:
            self._cancel_button_load()
            return

        canvas = self._button_load_canvas
        if canvas is None:
            self._cancel_button_load()
            return

        try:
            chunk = next(self._button_load_gen)
        except StopIteration:
            self._finalize_button_load(canvas)
            return

        new_buttons = [
            self._create_single_button(bd, canvas, self._button_load_tab)
            for bd in chunk
        ]
        canvas.add_buttons_batch(new_buttons)
        # Keep overlay above newly added button widgets
        canvas.loading_overlay.raise_()

        # Yield to the event loop, then process next chunk
        QtCore.QTimer.singleShot(0, self._process_next_button_chunk)

    def _finalize_button_load(self, canvas):
        """Called when all chunks are done."""
        tab_name = self._button_load_tab
        self._button_load_gen = None
        self._button_load_tab = None
        self._button_load_canvas = None
        canvas.update_button_positions()
        canvas.update()
        canvas.loading_overlay.hide_overlay()

        # Cache data version
        if tab_name:
            self._tab_button_versions[tab_name] = self._compute_tab_data_hash(tab_name)

        # Restore selection if pending (undo/redo path)
        if self._pending_restore_selection is not None:
            self._restore_selection_by_ids(canvas, self._pending_restore_selection)
            self._pending_restore_selection = None

    def _create_buttons_sync(self, canvas, button_data_list, tab_name):
        """Synchronous path for small button sets."""
        new_buttons = [
            self._create_single_button(bd, canvas, tab_name)
            for bd in button_data_list
        ]
        canvas.add_buttons_batch(new_buttons)
        canvas.update_button_positions()

        # Re-enable canvas updates (suppressed during button swap) and reveal
        canvas.setUpdatesEnabled(True)
        canvas.update()
        canvas.loading_overlay.hide_overlay()

        # Cache data version
        self._tab_button_versions[tab_name] = self._compute_tab_data_hash(tab_name)

        # Restore selection if pending (undo/redo path)
        if self._pending_restore_selection is not None:
            self._restore_selection_by_ids(canvas, self._pending_restore_selection)
            self._pending_restore_selection = None

    def _compute_tab_data_hash(self, tab_name):
        """Lightweight hash of button data for cache invalidation."""
        import hashlib
        tab_data = DM.PickerDataManager.get_tab_data(tab_name)
        buttons = tab_data.get('buttons', [])
        key = str([(b.get('id'), b.get('position'), b.get('color'),
                     b.get('label')) for b in buttons])
        return hashlib.md5(key.encode()).hexdigest()

    def _restore_selection_by_ids(self, canvas, button_ids):
        """Restore button selection from a list of IDs."""
        if not button_ids:
            return
        canvas.clear_selection()
        selected = []
        for button in canvas.buttons:
            if hasattr(button, 'unique_id') and button.unique_id in button_ids:
                button.is_selected = True
                button.update()
                selected.append(button)
        if selected:
            if hasattr(canvas, '_cache_valid'):
                canvas._cache_valid = False
            canvas.button_selection_changed.emit()
            if hasattr(canvas, 'transform_guides'):
                canvas.transform_guides.setVisible(True)
                canvas.transform_guides.visual_layer.setVisible(True)
                if hasattr(canvas.transform_guides, 'controls_widget'):
                    canvas.transform_guides.controls_widget.setVisible(True)
                canvas.transform_guides.update_selection()

    def create_buttons_for_tab(self, tab_name):
        """Create buttons for a specific tab (synchronous, non-chunked)."""
        if tab_name not in self.tab_system.tabs:
            return

        self.initialize_tab_data(tab_name)
        canvas = self.tab_system.tabs[tab_name]['canvas']

        for button in canvas.buttons[:]:
            button.setParent(None)
            button.deleteLater()
        canvas.buttons.clear()

        tab_data = DM.PickerDataManager.get_tab_data(tab_name)
        new_buttons = []
        for button_data in tab_data.get('buttons', []):
            button = self._create_single_button(button_data, canvas, tab_name)
            button.changed.connect(self.on_button_changed)
            new_buttons.append(button)

        canvas.add_buttons_batch(new_buttons)
        canvas.update_button_positions()
        canvas.update()

    def on_button_changed(self, button):
        """Handle button change events - FIXED VERSION"""
        # Invalidate tab cache so next switch recreates buttons from data
        if self.tab_system.current_tab:
            self._tab_button_versions.pop(self.tab_system.current_tab, None)
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
        button_data = self._create_button_data(button)

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
                    fields_to_update = ['position', 'width', 'height', 'radius', 'rotation', 'shape_type','label', 'color', 'opacity', 'assigned_objects', 'mode', 'script_data', 'pose_data', 'animation_data', 'controller_data', 'thumbnail_path','svg_path_data','svg_file_path','selectable', 'text_color', 'text_bold', 'text_italic', 'text_underline']
                
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
                                elif field == 'animation_data':
                                    tab_data['buttons'][i]['animation_data'] = getattr(button, 'animation_data', {})
                                elif field == 'controller_data':
                                    tab_data['buttons'][i]['controller_data'] = getattr(button, 'controller_data', {})
                                elif field == 'thumbnail_path':
                                    tab_data['buttons'][i]['thumbnail_path'] = getattr(button, 'thumbnail_path', '')
                                elif field == 'selectable':
                                    tab_data['buttons'][i]['selectable'] = getattr(button, 'selectable', True)
                                elif field == 'text_color':
                                    tab_data['buttons'][i]['text_color'] = getattr(button, 'text_color', '#ffffff')
                                elif field == 'text_bold':
                                    tab_data['buttons'][i]['text_bold'] = getattr(button, 'text_bold', False)
                                elif field == 'text_italic':
                                    tab_data['buttons'][i]['text_italic'] = getattr(button, 'text_italic', False)
                                elif field == 'text_underline':
                                    tab_data['buttons'][i]['text_underline'] = getattr(button, 'text_underline', False)
                                elif field == 'rotation':
                                    tab_data['buttons'][i]['rotation'] = getattr(button, 'rotation', 0)
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
                    button_data = self._create_button_data(button)
                    
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
        button_data = self._create_button_data(button)

        # CRITICAL FIX: Find and update existing button or add new one
        updated = False
        for i, existing_button in enumerate(tab_data['buttons']):
            if existing_button['id'] == button.unique_id:
                # CRITICAL: Update the existing button data completely
                tab_data['buttons'][i] = button_data
                updated = True
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
            "animation_data": getattr(button, 'animation_data', {}),
            "controller_data": getattr(button, 'controller_data', {}),
            "thumbnail_path": getattr(button, 'thumbnail_path', ''),
            "rotation": getattr(button, 'rotation', 0),
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
                    "animation_data": getattr(canvas_button, 'animation_data', {}),
                    "controller_data": getattr(canvas_button, 'controller_data', {}),
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
                'image_scale': 1.0,
                'namespace': 'None'
            }
        elif 'buttons' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['buttons'] = []
        elif 'background_value' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['background_value'] = 20  
        elif 'image_scale' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['image_scale'] = 1.0  
        elif 'image_opacity' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['image_opacity'] = 1.0
        elif 'namespace' not in self.tab_system.tabs[tab_name]:
            self.tab_system.tabs[tab_name]['namespace'] = 'None'
        
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

        # Invalidate stale class-level cache so we always read from the
        # current Blender scene (the cache may belong to a previous window).
        DM.PickerDataManager._cached_data = None

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
        # Performance: only keep updates and mouse tracking enabled for the active canvas
        try:
            for tn, td in self.tab_system.tabs.items():
                canvas = td.get('canvas')
                if canvas:
                    enable = (tn == tab_name)
                    canvas.setUpdatesEnabled(enable)
                    canvas.setMouseTracking(enable)
        except Exception:
            pass
        
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
        
        # Create buttons — skip if tab data hasn't changed (cache hit)
        current_hash = self._compute_tab_data_hash(tab_name)
        cached_hash = self._tab_button_versions.get(tab_name)
        if (cached_hash == current_hash and len(current_canvas.buttons) > 0):
            current_canvas.update_button_positions()
            current_canvas.update()
        else:
            # Show overlay immediately so the user sees a clean loading state
            # instead of a flash of empty canvas before create_buttons fires.
            current_canvas.loading_overlay.show_overlay()
            QtCore.QTimer.singleShot(0, self.create_buttons)
        
        # Update namespace dropdown for the new tab and set to tab's stored namespace
        if hasattr(self, 'namespace_dropdown'):
            # First repopulate the dropdown with current scene rigs
            self.populate_namespace_dropdown()
            
            # Then restore this tab's namespace selection
            tab_data = DM.PickerDataManager.get_tab_data(tab_name)
            stored_namespace = tab_data.get('namespace', 'None')
            
            # Block signals to prevent triggering on_namespace_changed during restore
            self.namespace_dropdown.blockSignals(True)
            
            # Find and set the stored namespace
            index = self.namespace_dropdown.findText(stored_namespace)
            if index >= 0:
                self.namespace_dropdown.setCurrentIndex(index)
            else:
                # If stored namespace doesn't exist in scene, default to 'None'
                self.namespace_dropdown.setCurrentIndex(0)
            
            # Re-enable signals
            self.namespace_dropdown.blockSignals(False)
            
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
        """OPTIMIZED: Properly cleanup deleted tab with all associated resources"""
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
            
        # OPTIMIZATION: Force Qt to process deletion events
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
                
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
        
        # OPTIMIZATION: Cleanup data structures after tab deletion
        QtCore.QTimer.singleShot(100, self._cleanup_data_structures)

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
        
        # Load and set the namespace for this tab
        stored_namespace = tab_data.get('namespace', 'None')
        
        # Block signals to prevent triggering on_namespace_changed during restore
        self.namespace_dropdown.blockSignals(True)
        
        # Find and set the stored namespace
        index = self.namespace_dropdown.findText(stored_namespace)
        if index >= 0:
            self.namespace_dropdown.setCurrentIndex(index)
        else:
            # If stored namespace doesn't exist in scene, default to 'None'
            self.namespace_dropdown.setCurrentIndex(0)
        
        # Re-enable signals
        self.namespace_dropdown.blockSignals(False)

        # Restore saved camera (pan/zoom) state
        saved_zoom = tab_data.get('zoom_factor', 1.0)
        saved_px = tab_data.get('pan_offset_x', 0.0)
        saved_py = tab_data.get('pan_offset_y', 0.0)
        current_canvas.zoom_factor = saved_zoom
        current_canvas.pan_offset = QtCore.QPointF(saved_px, saved_py)
        current_canvas.update_button_positions()

        current_canvas.update()
    #----------------------------------------------------------------------------------------------------------------------------------------
    # [Canvas Image]  
    #----------------------------------------------------------------------------------------------------------------------------------------
    def select_image_for_current_tab(self):
        if self.tab_system.current_tab:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            overlay_folder = os.path.join(current_dir, "picker_canvas_overlays")
            if not os.path.isdir(overlay_folder):
                overlay_folder = os.path.expanduser("~")
            image_path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self, "Select Image", overlay_folder, "Image Files (*.png *.jpg *.jpeg *.bmp)")

            if image_path:
                current_tab = self.tab_system.current_tab
                current_canvas = self.tab_system.tabs[current_tab]['canvas']

                # Route through session if active (bpicker architecture)
                session = DM.PickerDataManager.get_active_session()
                if session:
                    store_path = session.add_media_file(image_path, "backgrounds")
                    if store_path:
                        image_path = store_path  # now a bpicker:// path

                current_canvas.set_background_image(image_path)
                self.remove_image.setEnabled(True)

                self.tab_system.tabs[current_tab]['image_path'] = image_path
                current_opacity = self.tab_system.tabs[current_tab]['image_opacity']
                current_scale = float(self.image_scale_factor.text())

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

    # ── Capture Background ─────────────────────────────────────────────
    def capture_background_for_current_tab(self):
        """Start screen region capture to set as tab background image."""
        if not self.tab_system.current_tab:
            return

        from .picker_button import ScreenRegionSelector  # noqa: F811

        top_window = self.window()
        self._bg_capture_was_visible = top_window.isVisible()
        top_window.hide()
        QtCore.QCoreApplication.processEvents()
        QtCore.QTimer.singleShot(50, self._show_bg_region_selector)

    def _show_bg_region_selector(self):
        """Show the screen region selector for background capture."""
        from .picker_button import ScreenRegionSelector
        try:
            screens = QtGui.QGuiApplication.screens()
            if not screens:
                raise Exception("No screen available for capture")

            # Compute virtual desktop bounding rect
            virtual_rect = QtCore.QRect()
            for s in screens:
                virtual_rect = virtual_rect.united(s.geometry())

            max_dpr = max(s.devicePixelRatio() for s in screens)

            # Create combined pixmap covering entire virtual desktop
            combined = QtGui.QPixmap(
                int(virtual_rect.width() * max_dpr),
                int(virtual_rect.height() * max_dpr)
            )
            combined.setDevicePixelRatio(max_dpr)
            combined.fill(QtCore.Qt.black)

            painter = QtGui.QPainter(combined)
            for s in screens:
                geom = s.geometry()
                shot = s.grabWindow(0)
                x = geom.x() - virtual_rect.x()
                y = geom.y() - virtual_rect.y()
                painter.drawPixmap(x, y, geom.width(), geom.height(), shot)
            painter.end()

            if combined.isNull():
                raise Exception("Failed to capture screen")

            self._bg_capture_pixmap = combined
            self._bg_region_selector = ScreenRegionSelector(combined, virtual_rect)
            self._bg_region_selector.region_selected.connect(self._on_bg_region_selected)
            self._bg_region_selector.cancelled.connect(self._on_bg_capture_cancelled)

        except Exception as e:
            print(f"[blender_ui] Background capture failed: {e}")
            self._restore_bg_capture_window()

    def _on_bg_region_selected(self, rect):
        """Handle selected region — save as background image for current tab."""
        try:
            if not hasattr(self, '_bg_capture_pixmap') or self._bg_capture_pixmap is None:
                return

            dpr = self._bg_capture_pixmap.devicePixelRatio()
            scaled_rect = QtCore.QRect(
                int(rect.x() * dpr), int(rect.y() * dpr),
                int(rect.width() * dpr), int(rect.height() * dpr)
            )
            selected_image = self._bg_capture_pixmap.toImage().copy(scaled_rect)

            if selected_image.isNull():
                return

            # Save to temp file
            import tempfile
            temp_path = os.path.join(tempfile.gettempdir(), "bgen_bg_capture.png")
            selected_image.save(temp_path, "PNG")

            current_tab = self.tab_system.current_tab
            if not current_tab:
                return

            # Route through session if active
            session = DM.PickerDataManager.get_active_session()
            if session:
                store_path = session.add_media_file(temp_path, "backgrounds")
                if store_path:
                    image_path = store_path
                else:
                    image_path = temp_path
            else:
                image_path = temp_path

            # Apply to canvas
            current_canvas = self.tab_system.tabs[current_tab]['canvas']
            current_canvas.set_background_image(image_path)
            self.remove_image.setEnabled(True)

            self.tab_system.tabs[current_tab]['image_path'] = image_path
            current_opacity = self.tab_system.tabs[current_tab].get('image_opacity', 1.0)
            current_scale = float(self.image_scale_factor.text())

            DM.PickerDataManager.update_image_data(
                current_tab, image_path, current_opacity, current_scale
            )
            current_canvas.update()

            # Cleanup temp if it was copied into session
            if session and image_path != temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

        finally:
            self._cleanup_bg_capture()
            self._restore_bg_capture_window()

    def _on_bg_capture_cancelled(self):
        self._cleanup_bg_capture()
        self._restore_bg_capture_window()

    def _cleanup_bg_capture(self):
        for attr in ('_bg_capture_pixmap', '_bg_region_selector'):
            if hasattr(self, attr):
                obj = getattr(self, attr)
                if hasattr(obj, 'deleteLater'):
                    obj.deleteLater()
                delattr(self, attr)

    def _restore_bg_capture_window(self):
        top_window = self.window()
        if getattr(self, '_bg_capture_was_visible', True):
            top_window.show()
        QtCore.QCoreApplication.processEvents()

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
    # [Picker Button Edit Functions] — delegated to EditModeController
    #----------------------------------------------------------------------------------------------------------------------------------------
    def rename_selected_buttons(self, new_label):
        self.edit_controller.rename(new_label)

    def change_opacity_for_selected_buttons(self, value):
        self.edit_controller.set_opacity(value)

    def set_size_for_selected_buttons(self, transform_data):
        self.edit_controller.resize(transform_data)

    def match_button_size(self):
        self.edit_controller.match_size()

    def initialize_button_original_sizes(self):
        if not self.tab_system.current_tab:
            return
        canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
        for button in canvas.buttons:
            if not hasattr(button, 'original_size'):
                button.original_size = QtCore.QSize(button.width, button.height)

    def set_radius_for_selected_buttons(self, tl, tr, br, bl):
        self.edit_controller.set_radius(tl, tr, br, bl)

    def change_color_for_selected_buttons(self, color):
        self.edit_controller.recolor(color)

    def change_text_color_for_selected_buttons(self, color):
        self.edit_controller.set_text_color(color)

    def _apply_widget_changes(self):
        """Delegate to edit mode controller."""
        self.edit_controller._apply_widget_changes()

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
            "animation_data": getattr(button, 'animation_data', {}),
            "controller_data": getattr(button, 'controller_data', {}),
            "thumbnail_path": getattr(button, 'thumbnail_path', ''),
            "shape_type": button.shape_type,
            "svg_path_data": button.svg_path_data,
            "svg_file_path": button.svg_file_path,
            "rotation": getattr(button, 'rotation', 0),
            "text_color": getattr(button, 'text_color', '#ffffff'),
            "text_bold": getattr(button, 'text_bold', False),
            "text_italic": getattr(button, 'text_italic', False),
            "text_underline": getattr(button, 'text_underline', False)
        }
    #----------------------------------------------------------------------------------------------------------------------------------------
    def update_edit_widgets_delayed(self):
        """Delegate to edit mode controller for widget sync."""
        self.edit_controller.on_selection_changed()

    def update_edit_widgets(self):
        """Delegate to edit mode controller."""
        self.edit_controller._sync_widgets()
    
    #-----------------------------------------------------------------------------------------------------------------------------------
    # Events
    #-----------------------------------------------------------------------------------------------------------------------------------
    def _on_app_focus_changed(self, old, new):
        """When focus leaves a picker QLineEdit, refresh Blender's input
        state so it doesn't get stuck thinking a modifier key is held."""
        try:
            if old is None or not isinstance(old, QtWidgets.QLineEdit):
                return
            # Only react if the line edit was inside this picker window.
            if old.window() is not self:
                return
            from . import utils as UT
            UT.blender_main_window()
        except Exception:
            pass

    def enterEvent(self, event):
        """Ensure mouse tracking is active when entering the window"""
        self.setMouseTracking(True)
        #if not self.hasFocus():
        #    self.activateWindow()
        #    self.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Reset cursor and hide tooltips when leaving the window"""
        if not self.resizing:
            self.setCursor(QtCore.Qt.ArrowCursor)
        #QtWidgets.QToolTip.hideText()

        # Hand macOS key window status back to Blender as soon as the
        # cursor leaves the picker. The picker is a floating tool with
        # WindowStaysOnTopHint, so AppKit will never auto-transfer key
        # status — we have to do it explicitly. Without this, Blender's
        # GHOST stays in a "not key" state and viewport orbit/pan/zoom
        # silently break until something forces a GHOST resync (e.g.
        # resizing an area).
        #
        # leaveEvent fires when the cursor crosses to a child widget
        # too, so verify the cursor is actually outside the top-level
        # picker frame before handing focus over.
        try:
            global_pos = QtGui.QCursor.pos()
            if not self.frameGeometry().contains(global_pos):
                from . import utils as UT
                UT.blender_main_window()
        except Exception:
            pass
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        # Check for Alt+Left Click first
        '''if event.button() == QtCore.Qt.LeftButton and event.modifiers() & QtCore.Qt.AltModifier:
            # Alt+Left Click to show context menu
            self.resize_window_full()
            event.accept()
            return
            
        # Check for Shift+Left Click first
        if event.button() == QtCore.Qt.LeftButton and event.modifiers() & QtCore.Qt.ShiftModifier:
            # Shift+Left Click to show context menu
            self.resize_window_min()
            event.accept()
            return'''

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
    
    def showEvent(self, event):
        """Resume per-picker polling and catch up on selection state when the
        window becomes visible. Blender-side handlers skip work while hidden,
        so we need a one-shot resync on reshow.
        """
        super().showEvent(event)
        try:
            if hasattr(self, '_bones_sync_timer') and self._bones_sync_timer is not None:
                if not self._bones_sync_timer.isActive():
                    self._bones_sync_timer.start()
                self._sync_show_bones_state()
        except Exception:
            pass
        # Catch-up selection sync: handlers may have skipped events while hidden.
        try:
            mgr = SSM.SelectionSyncManager.get_instance()
            if mgr is not None and not mgr._update_timer.isActive():
                mgr._update_timer.start(50)
        except Exception:
            pass
        # Refresh namespace dropdown in case armatures changed while hidden.
        try:
            if hasattr(self, 'check_scene_for_updates'):
                self.check_scene_for_updates()
                # Reset cached counters so the gated handler re-syncs correctly.
                if hasattr(self, '_cached_scene_object_count'):
                    import bpy
                    self._cached_scene_object_count = len(bpy.context.scene.objects)
        except Exception:
            pass

    def hideEvent(self, event):
        """Pause per-picker polling while the window is not visible."""
        super().hideEvent(event)
        try:
            if hasattr(self, '_bones_sync_timer') and self._bones_sync_timer is not None:
                if self._bones_sync_timer.isActive():
                    self._bones_sync_timer.stop()
        except Exception:
            pass

    def resizeEvent(self, event):
        """Enhanced resize event with better throttling"""
        # Call parent implementation first
        super().resizeEvent(event)
        
        # Reset fullscreen state if window was manually resized (not from our methods)
        if self.is_fullscreen and hasattr(self, '_programmatic_resize'):
            # This resize was triggered by our code, don't reset fullscreen state
            if hasattr(self, '_programmatic_resize'):
                delattr(self, '_programmatic_resize')
        elif self.is_fullscreen:
            # Manual resize detected, exit fullscreen mode
            self.is_fullscreen = False
            self.pre_fullscreen_geometry = None
        
        # Only update buttons if not in active resize and not during batch operations
        if not self.resize_state.get('active', False) and not getattr(self, 'batch_update_active', False):
            # Use a timer to throttle updates during rapid resize events
            if not hasattr(self, '_resize_update_timer'):
                self._resize_update_timer = QTimer()
                self._resize_update_timer.setSingleShot(True)
                self._resize_update_timer.timeout.connect(lambda: self.update_buttons_for_current_tab(force_update=True))
            
            self._resize_update_timer.stop()
            self._resize_update_timer.start(100)  # 100ms delay

    # ------------------------------------------------------------------
    # Picker Session / Library Methods
    # ------------------------------------------------------------------

    def _check_launch_state(self):
        """Determine what to show on launch: existing session, legacy data, or prompt."""
        # Invalidate stale cache — the class-level _cached_data may belong
        # to a previous window / scene.  Force a fresh read from the scene.
        DM.PickerDataManager._cached_data = None

        # Check for existing scene link (previously opened .bpicker)
        link = DM.PickerDataManager.get_scene_link()
        if link and link.get("bpicker_uuid"):
            try:
                self.open_picker_from_library(link["bpicker_uuid"])
                # Verify the session was actually established
                if self.session and self.session.uuid:
                    return
                print("[launch] Picker link found but session failed to open.")
            except Exception as e:
                print(f"[launch] Could not reopen linked picker: {e}")

        # Check for legacy embedded data — show launch dialog with convert option
        if PIO.detect_legacy_scene_data():
            QTimer.singleShot(200, self._show_launch_dialog)
            return

        # No data — show launch dialog
        QTimer.singleShot(200, self._show_launch_dialog)

    def _show_launch_dialog(self):
        """Show the Create New / Open From Library launch prompt."""
        from . import launch_dialog as LD
        has_legacy = PIO.detect_legacy_scene_data()
        dialog = LD.LaunchDialog(self, has_legacy_data=has_legacy)
        result = dialog.get_result()

        if result == "create_new":
            self._on_library_create_new()
        elif result == "open_library":
            # Switch to Library page
            self.page_segment.set_selected_index(1)
            self._on_page_changed(1)
        elif result == "convert_legacy":
            self._convert_legacy_data()

    def _show_legacy_migration_hint(self):
        """Show a subtle hint that legacy data can be migrated."""
        # Non-blocking — just a print for now; could be a toast notification
        print("[FT Picker] Legacy picker data detected. "
              "Use Library > Import to convert to the new .bpicker format.")

    def _convert_legacy_data(self):
        """Convert embedded scene data to a .bpicker and open it."""
        from . import custom_dialog as CD
        dialog = CD.CustomDialog(self, title="Convert Scene Data", size=(280, 90))
        name_input = QtWidgets.QLineEdit("Converted Picker")
        name_input.setStyleSheet(
            "background: rgba(50,50,50,0.8); color: #dddddd; "
            "border: 1px solid #3a3a3a; border-radius: 4px; padding: 4px;"
        )
        name_input.selectAll()
        dialog.add_widget(name_input)

        btn_layout = QtWidgets.QHBoxLayout()
        ok_btn = CB.CustomButton("Convert", color="#00749a")
        cancel_btn = CB.CustomButton("Cancel", color="#444444")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        dialog.add_layout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            name = name_input.text().strip() or "Converted Picker"
            picker_uuid = PIO.convert_legacy_scene_to_bpicker(picker_name=name)
            if picker_uuid:
                self.open_picker_from_library(picker_uuid)

    def _get_current_canvas(self):
        """Return the active tab's PickerCanvas, or None."""
        try:
            ts = self.tab_system
            if ts and ts.current_tab and ts.current_tab in ts.tabs:
                return ts.tabs[ts.current_tab].get('canvas')
        except Exception:
            pass
        return None

    def create_new_picker(self, name="Untitled Picker"):
        """Create a new .bpicker, add to library, and open it."""
        # Close any existing session first
        if self.session:
            self.session.close()
            DM.PickerDataManager.set_active_session(None)

        self.session = PickerSession()
        self.session.create_new(name=name)
        self.session.sync_to_scene()

        # Invalidate cache so _rebuild reads the freshly synced data
        DM.PickerDataManager._cached_data = None

        self._rebuild_ui_from_data()
        self.session.set_canvas(self._get_current_canvas())
        self._wire_session_callbacks()
        self._update_window_title()

    def open_picker_from_library(self, picker_uuid):
        """Open a .bpicker from the library by UUID."""
        try:
            # Close existing session if any
            if self.session:
                self.session.close()
                DM.PickerDataManager.set_active_session(None)

            self.session = PickerSession()
            self.session.open_from_library(picker_uuid)
            self.session.sync_to_scene()

            # Invalidate cache so _rebuild reads the freshly synced data
            DM.PickerDataManager._cached_data = None

            self._rebuild_ui_from_data()
            self.session.set_canvas(self._get_current_canvas())
            self._wire_session_callbacks()
            self._update_window_title()

            # Switch to editor page
            self.page_segment.set_selected_index(0)
            self._on_page_changed(0)
        except Exception as e:
            print(f"[FT Picker] Failed to open picker: {e}")
            import traceback
            traceback.print_exc()

    def save_current_picker(self):
        """Save the current picker session to its .bpicker archive."""
        if not self.session:
            print("[FT Picker] No active session to save.")
            return
        self.session.save()
        self._update_window_title()

    def save_picker_as(self):
        """Save current picker as a new .bpicker with a new name/UUID."""
        if not self.session:
            return

        from . import custom_dialog as CD
        dialog = CD.CustomDialog(self, title="Save As", size=(280, 90))
        current_name = ""
        if self.session.metadata:
            current_name = self.session.metadata.get("picker_name", "")
        name_input = QtWidgets.QLineEdit(current_name)
        name_input.setStyleSheet(
            "background: rgba(50,50,50,0.8); color: #dddddd; "
            "border: 1px solid #3a3a3a; border-radius: 4px; padding: 4px;"
        )
        name_input.setPlaceholderText("Picker name...")
        dialog.add_widget(name_input)

        btn_layout = QtWidgets.QHBoxLayout()
        ok_btn = CB.CustomButton("Save", color="#00749a")
        cancel_btn = CB.CustomButton("Cancel", color="#444444")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        dialog.add_layout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            new_name = name_input.text().strip()
            if new_name:
                self.session.save_as(new_name)
                self._update_window_title()

    def _wire_session_callbacks(self):
        """Connect the active session's save/dirty callbacks to the UI."""
        if self.session:
            self.session._on_save_callback = self._on_picker_saved
            self.session._on_dirty_callback = self._update_window_title

    def _on_picker_saved(self, auto=False):
        """Called after any save (auto or manual) to show the save indicator."""
        canvas = self._get_current_canvas()
        if canvas and hasattr(canvas, 'save_indicator'):
            label = "Auto-saved \u2713" if auto else "Saved \u2713"
            canvas.save_indicator.show_indicator(label)
        self._update_window_title()

    def _rebuild_ui_from_data(self):
        """Reload tabs and buttons from current PickerDataManager data."""
        self._tab_button_versions.clear()
        data = DM.PickerDataManager.get_data()

        # Clear existing tab buttons from the layout (without deleting data)
        if hasattr(self, 'tab_system') and self.tab_system:
            ts = self.tab_system

            # Remove old canvases from the stack BEFORE clearing tabs,
            # so orphaned canvases don't linger and receive stale events.
            for tab_name, tab_info in list(ts.tabs.items()):
                canvas = tab_info.get('canvas')
                if canvas:
                    idx = self.canvas_stack.indexOf(canvas)
                    if idx != -1:
                        self.canvas_stack.removeWidget(canvas)
                    canvas.setParent(None)
                    canvas.deleteLater()
                btn = tab_info.get('button')
                if btn:
                    ts.tab_layout.removeWidget(btn)
                    btn.deleteLater()
            ts.tabs.clear()
            ts.current_tab = None

            # Re-add tabs from data
            if data.get('tabs'):
                first_tab = next(iter(data['tabs']))
                for tab_name in data['tabs']:
                    ts.add_tab(tab_name, switch=False)

                ts.switch_tab(first_tab)
            else:
                ts.add_tab('Tab 1', switch=True)

        self.create_buttons()

    def _update_window_title(self):
        """Update the window title to show picker name and dirty state."""
        if not self.session or not self.session.metadata:
            return
        name = self.session.metadata.get("picker_name", "Untitled")
        dirty = " *" if self.session.is_dirty() else ""
        self.setWindowTitle(f"BGEN Picker - {name}{dirty}")

    # ------------------------------------------------------------------
    # Library filter / search
    # ------------------------------------------------------------------

    def _on_library_filter_menu(self):
        """Show custom filter popup with sort options and card-size slider."""
        popup = QtWidgets.QFrame(self, QtCore.Qt.Popup)
        popup.setStyleSheet(
            "QFrame#filterPopup { background-color: #2a2a2a; "
            "border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        popup.setObjectName("filterPopup")
        popup.setFixedWidth(200)

        layout = QtWidgets.QVBoxLayout(popup)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        # ---- Sort section ----
        sort_header = QtWidgets.QLabel("Sort by")
        sort_header.setStyleSheet(
            "color: #888888; font-size: 10px; background: transparent; "
            "border: none; padding: 0px 4px 2px 4px;"
        )
        layout.addWidget(sort_header)

        sort_options = [
            ("modified", "Date Modified"),
            ("created", "Date Created"),
            ("az", "Alphabetical (A\u2013Z)"),
            ("za", "Alphabetical (Z\u2013A)"),
        ]

        for key, label_text in sort_options:
            is_active = (key == self._library_sort_mode)
            row = QtWidgets.QFrame()
            row.setFixedHeight(26)
            row.setCursor(QtCore.Qt.PointingHandCursor)
            row.setStyleSheet(
                "QFrame { background: "
                + ("rgba(29,101,202,0.2)" if is_active else "transparent")
                + "; border: none; border-radius: 4px; }"
                + " QFrame:hover { background: rgba(255,255,255,0.08); }"
            )
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(8, 0, 8, 0)
            row_layout.setSpacing(6)

            # Indicator dot
            dot = QtWidgets.QLabel("\u2022" if is_active else " ")
            dot.setFixedWidth(10)
            dot.setStyleSheet(
                f"color: {'#5b9bd5' if is_active else 'transparent'}; "
                "font-size: 14px; background: transparent; border: none;"
            )
            row_layout.addWidget(dot)

            text = QtWidgets.QLabel(label_text)
            text.setStyleSheet(
                f"color: {'#dddddd' if is_active else '#bbbbbb'}; "
                "font-size: 11px; background: transparent; border: none;"
            )
            row_layout.addWidget(text)
            row_layout.addStretch()

            # Closure to capture key
            def make_click_handler(sort_key):
                def handler(event):
                    self._library_sort_mode = sort_key
                    if self.library_controller:
                        self.library_controller.set_sort_mode(sort_key)
                    popup.close()
                return handler
            row.mousePressEvent = make_click_handler(key)
            layout.addWidget(row)

        # ---- Separator ----
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet("color: #3a3a3a; background: #3a3a3a; border: none; max-height: 1px;")
        layout.addSpacing(4)
        layout.addWidget(sep)
        layout.addSpacing(4)

        # ---- View Mode section ----
        view_header = QtWidgets.QLabel("View")
        view_header.setStyleSheet(
            "color: #888888; font-size: 10px; background: transparent; "
            "border: none; padding: 0px 4px 2px 4px;"
        )
        layout.addWidget(view_header)

        view_options = [
            ("small", "Small Icons"),
            ("medium", "Medium Icons"),
            ("large", "Large Icons"),
            ("list", "List"),
        ]

        for key, label_text in view_options:
            is_active = (key == self._library_view_mode)
            row = QtWidgets.QFrame()
            row.setFixedHeight(26)
            row.setCursor(QtCore.Qt.PointingHandCursor)
            row.setStyleSheet(
                "QFrame { background: "
                + ("rgba(29,101,202,0.2)" if is_active else "transparent")
                + "; border: none; border-radius: 4px; }"
                + " QFrame:hover { background: rgba(255,255,255,0.08); }"
            )
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(8, 0, 8, 0)
            row_layout.setSpacing(6)

            dot = QtWidgets.QLabel("•" if is_active else " ")
            dot.setFixedWidth(10)
            dot.setStyleSheet(
                f"color: {'#5b9bd5' if is_active else 'transparent'}; "
                "font-size: 14px; background: transparent; border: none;"
            )
            row_layout.addWidget(dot)

            text = QtWidgets.QLabel(label_text)
            text.setStyleSheet(
                f"color: {'#dddddd' if is_active else '#bbbbbb'}; "
                "font-size: 11px; background: transparent; border: none;"
            )
            row_layout.addWidget(text)
            row_layout.addStretch()

            def make_view_handler(view_key):
                def handler(event):
                    self._library_view_mode = view_key
                    if self.library_controller:
                        self.library_controller.set_view_mode(view_key)
                    popup.close()
                return handler
            row.mousePressEvent = make_view_handler(key)
            layout.addWidget(row)

        # Position below the filter button
        popup.adjustSize()
        btn_pos = self.lib_filter_btn.mapToGlobal(
            QtCore.QPoint(0, self.lib_filter_btn.height() + 4)
        )
        popup.move(btn_pos)
        popup.show()
        self._filter_popup = popup  # prevent GC

    def _on_library_view_mode_changed(self, mode):
        """Handle view mode selection."""
        self._library_view_mode = mode
        if self.library_controller:
            self.library_controller.set_view_mode(mode)

    def _toggle_library_search(self):
        """Toggle the search bar visibility with smooth animation."""
        self._library_search_visible = not self._library_search_visible

        anim = QtCore.QPropertyAnimation(self.lib_search_container, b"maximumHeight")
        anim.setDuration(150)
        anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)

        if self._library_search_visible:
            self.lib_search_container.setMaximumHeight(0)
            anim.setStartValue(0)
            anim.setEndValue(30)
            anim.finished.connect(lambda: self.lib_search_input.setFocus())
        else:
            anim.setStartValue(30)
            anim.setEndValue(0)
            anim.finished.connect(lambda: self.lib_search_input.clear())

        self._search_anim = anim  # prevent GC
        anim.start()

    def _on_library_search_changed(self, text):
        """Forward search text to the library controller."""
        if self.library_controller:
            self.library_controller.set_search_text(text)

    # ------------------------------------------------------------------
    # BGEN Library filter / search
    # ------------------------------------------------------------------

    def _on_bgen_filter_menu(self):
        """Show sort popup for the BGEN library catalogue."""
        popup = QtWidgets.QFrame(self, QtCore.Qt.Popup)
        popup.setStyleSheet(
            "QFrame#bgenFilterPopup { background-color: #2a2a2a; "
            "border: 1px solid #3a3a3a; border-radius: 6px; }"
        )
        popup.setObjectName("bgenFilterPopup")
        popup.setFixedWidth(200)

        layout = QtWidgets.QVBoxLayout(popup)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(2)

        sort_header = QtWidgets.QLabel("Sort by")
        sort_header.setStyleSheet(
            "color: #888888; font-size: 10px; background: transparent; "
            "border: none; padding: 0px 4px 2px 4px;"
        )
        layout.addWidget(sort_header)

        sort_options = [
            ("featured", "Featured"),
            ("newest", "Newest"),
            ("price_low", "Price: Low to High"),
            ("price_high", "Price: High to Low"),
            ("rating", "Top Rated"),
            ("downloads", "Most Downloaded"),
        ]

        for key, label_text in sort_options:
            is_active = (key == self._bgen_sort_mode)
            row = QtWidgets.QFrame()
            row.setFixedHeight(26)
            row.setCursor(QtCore.Qt.PointingHandCursor)
            row.setStyleSheet(
                "QFrame { background: "
                + ("rgba(29,101,202,0.2)" if is_active else "transparent")
                + "; border: none; border-radius: 4px; }"
                + " QFrame:hover { background: rgba(255,255,255,0.08); }"
            )
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(8, 0, 8, 0)
            row_layout.setSpacing(6)

            dot = QtWidgets.QLabel("\u2022" if is_active else " ")
            dot.setFixedWidth(10)
            dot.setStyleSheet(
                f"color: {'#5b9bd5' if is_active else 'transparent'}; "
                "font-size: 14px; background: transparent; border: none;"
            )
            row_layout.addWidget(dot)

            text = QtWidgets.QLabel(label_text)
            text.setStyleSheet(
                f"color: {'#dddddd' if is_active else '#bbbbbb'}; "
                "font-size: 11px; background: transparent; border: none;"
            )
            row_layout.addWidget(text)
            row_layout.addStretch()

            def make_click_handler(sort_key):
                def handler(event):
                    self._bgen_sort_mode = sort_key
                    if hasattr(self, 'bgen_library_controller') and self.bgen_library_controller:
                        self.bgen_library_controller.set_sort_mode(sort_key)
                    popup.close()
                return handler
            row.mousePressEvent = make_click_handler(key)
            layout.addWidget(row)

        # ---- Separator ----
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet("color: #3a3a3a; background: #3a3a3a; border: none; max-height: 1px;")
        layout.addSpacing(4)
        layout.addWidget(sep)
        layout.addSpacing(4)

        # ---- View Mode section ----
        view_header = QtWidgets.QLabel("View")
        view_header.setStyleSheet(
            "color: #888888; font-size: 10px; background: transparent; "
            "border: none; padding: 0px 4px 2px 4px;"
        )
        layout.addWidget(view_header)

        view_options = [
            ("small", "Small Icons"),
            ("medium", "Medium Icons"),
            ("large", "Large Icons"),
            ("list", "List"),
        ]

        for key, label_text in view_options:
            is_active = (key == self._bgen_view_mode)
            row = QtWidgets.QFrame()
            row.setFixedHeight(26)
            row.setCursor(QtCore.Qt.PointingHandCursor)
            row.setStyleSheet(
                "QFrame { background: "
                + ("rgba(29,101,202,0.2)" if is_active else "transparent")
                + "; border: none; border-radius: 4px; }"
                + " QFrame:hover { background: rgba(255,255,255,0.08); }"
            )
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(8, 0, 8, 0)
            row_layout.setSpacing(6)

            dot = QtWidgets.QLabel("•" if is_active else " ")
            dot.setFixedWidth(10)
            dot.setStyleSheet(
                f"color: {'#5b9bd5' if is_active else 'transparent'}; "
                "font-size: 14px; background: transparent; border: none;"
            )
            row_layout.addWidget(dot)

            text = QtWidgets.QLabel(label_text)
            text.setStyleSheet(
                f"color: {'#dddddd' if is_active else '#bbbbbb'}; "
                "font-size: 11px; background: transparent; border: none;"
            )
            row_layout.addWidget(text)
            row_layout.addStretch()

            def make_view_handler(view_key):
                def handler(event):
                    self._bgen_view_mode = view_key
                    if hasattr(self, 'bgen_library_controller') and self.bgen_library_controller:
                        self.bgen_library_controller.set_view_mode(view_key)
                    popup.close()
                return handler
            row.mousePressEvent = make_view_handler(key)
            layout.addWidget(row)

        popup.adjustSize()
        btn_pos = self.bgen_filter_btn.mapToGlobal(
            QtCore.QPoint(0, self.bgen_filter_btn.height() + 4)
        )
        popup.move(btn_pos)
        popup.show()
        self._bgen_filter_popup = popup

    def _toggle_bgen_search(self):
        """Toggle the BGEN library search bar."""
        self._bgen_search_visible = not self._bgen_search_visible

        anim = QtCore.QPropertyAnimation(self.bgen_search_container, b"maximumHeight")
        anim.setDuration(150)
        anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)

        if self._bgen_search_visible:
            self.bgen_search_container.setMaximumHeight(0)
            anim.setStartValue(0)
            anim.setEndValue(30)
            anim.finished.connect(lambda: self.bgen_search_input.setFocus())
        else:
            anim.setStartValue(30)
            anim.setEndValue(0)
            anim.finished.connect(lambda: self.bgen_search_input.clear())

        self._bgen_search_anim = anim
        anim.start()

    def _on_bgen_search_changed(self, text):
        """Forward search text to the library controller."""
        if hasattr(self, 'bgen_library_controller') and self.bgen_library_controller:
            self.bgen_library_controller.set_search_text(text)

    def _on_library_plus_menu(self):
        """Show a menu from the + button with New Picker and Convert options."""
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2a; color: #dddddd;
                border: 1px solid #3a3a3a; border-radius: 4px; padding: 4px;
            }
            QMenu::item { padding: 5px 20px; border-radius: 3px; }
            QMenu::item:selected { background-color: rgba(29,101,202,0.4); }
        """)

        new_action = menu.addAction("New Picker")
        import_action = menu.addAction("Import from File")
        convert_action = None
        if PIO.detect_legacy_scene_data():
            menu.addSeparator()
            convert_action = menu.addAction("Convert Scene Data to .bpicker")

        action = menu.exec_(self.lib_create_btn.mapToGlobal(
            QtCore.QPoint(0, self.lib_create_btn.height())
        ))

        if action == new_action:
            self._on_library_create_new()
        elif action == import_action:
            self._on_library_import()
        elif convert_action and action == convert_action:
            self._convert_legacy_data()

    def _on_library_create_new(self):
        """Handler for Create New button in library header."""
        from . import custom_dialog as CD
        dialog = CD.CustomDialog(self, title="New Picker", size=(280, 90))
        name_input = QtWidgets.QLineEdit("Untitled Picker")
        name_input.setStyleSheet(
            "background: rgba(50,50,50,0.8); color: #dddddd; "
            "border: 1px solid #3a3a3a; border-radius: 4px; padding: 4px;"
        )
        name_input.selectAll()
        dialog.add_widget(name_input)

        btn_layout = QtWidgets.QHBoxLayout()
        ok_btn = CB.CustomButton("Create", color="#00749a")
        cancel_btn = CB.CustomButton("Cancel", color="#444444")
        btn_layout.addWidget(ok_btn)
        btn_layout.addWidget(cancel_btn)
        dialog.add_layout(btn_layout)

        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            name = name_input.text().strip() or "Untitled Picker"
            self.create_new_picker(name)

    def _browse_library_path(self):
        """Browse for a new library folder location."""
        from .local_file_manager import LocalFileManager
        current = str(LocalFileManager.get_library_path())
        new_path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Library Folder", current
        )
        if new_path:
            LocalFileManager.set_library_path(new_path)
            self.settings_page.update_library_path_display(new_path)
            if self.library_controller:
                self.library_controller.refresh()

    def _open_library_folder(self):
        """Open the library folder in the system file manager."""
        from .local_file_manager import LocalFileManager
        lib_path = str(LocalFileManager.get_library_path())
        LocalFileManager.ensure_library_exists()
        import subprocess, sys
        if sys.platform == 'win32':
            os.startfile(lib_path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', lib_path])
        else:
            subprocess.Popen(['xdg-open', lib_path])

    def _browse_downloads_path(self):
        """Browse for a new downloads folder location."""
        from .local_file_manager import LocalFileManager
        current = str(LocalFileManager.get_downloads_path())
        new_path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Downloads Folder", current
        )
        if new_path:
            LocalFileManager.set_downloads_path(new_path)
            self.settings_page.update_downloads_path_display(new_path)

    def _open_downloads_folder(self):
        """Open the downloads folder in the system file manager."""
        from .local_file_manager import LocalFileManager
        dl_path = str(LocalFileManager.get_downloads_path())
        Path(dl_path).mkdir(parents=True, exist_ok=True)
        import subprocess, sys
        if sys.platform == 'win32':
            os.startfile(dl_path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', dl_path])
        else:
            subprocess.Popen(['xdg-open', dl_path])

    def _on_library_import(self):
        """Handler for Import button in library header."""
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Import Picker",
            PIO.get_file_dialog_directory(),
            "Picker Files (*.json *.bpicker);;JSON Files (*.json);;BPicker Files (*.bpicker)",
        )
        if not file_path:
            return

        ext = os.path.splitext(file_path)[1].lower()
        picker_uuid = None

        if ext == ".json":
            picker_uuid = PIO.import_legacy_json_to_bpicker(file_path)
        elif ext == ".bpicker":
            picker_uuid = PIO.import_bpicker_to_library(file_path)

        if picker_uuid:
            # Refresh library grid
            if self.library_controller:
                self.library_controller.refresh()
            # Open the imported picker
            self.open_picker_from_library(picker_uuid)

    def closeEvent(self, event):
        """Enhanced close event to ensure all data is saved and timers are cleaned up"""
        # Exit rename mode for any button in rename mode in the active canvas
        if hasattr(self, 'tab_system') and self.tab_system and self.tab_system.current_tab:
            canvas = self.tab_system.tabs[self.tab_system.current_tab]['canvas']
            for button in getattr(canvas, 'buttons', []):
                if getattr(button, 'rename_mode', False):
                    button.commit_rename()
                    button.exit_rename_mode()

        self.edit_mode = False

        # Flush ALL pending data to PickerDataManager BEFORE session save
        if hasattr(self, 'edit_controller') and self.edit_controller:
            self.edit_controller._commit_drag_to_database()
        if hasattr(self, 'pending_widget_changes') and self.pending_widget_changes:
            self._apply_widget_changes()
        if hasattr(self, 'pending_button_updates') and self.pending_button_updates:
            self._process_batch_updates()

        # Save and close session AFTER all data is flushed
        if self.session:
            if self.session.is_dirty():
                try:
                    self.session.save()
                except Exception as e:
                    print(f"[FT Picker] Auto-save on close failed: {e}")
            self.session.close()
            DM.PickerDataManager.set_active_session(None)
            self.session = None

        # Clean up library controller
        if hasattr(self, 'library_controller') and self.library_controller:
            self.library_controller.cleanup()
        if hasattr(self, '_mkt_webview') and self._mkt_webview:
            self._mkt_webview.cleanup()

        # Kill any lingering tooltip windows
        try:
            from . import custom_button as CB
            for w in QtWidgets.QApplication.topLevelWidgets():
                if isinstance(w, CB.CustomTooltipWidget):
                    w.close()
                    w.deleteLater()
        except Exception:
            pass

        # Invalidate library cache so next window-open fetches fresh data
        try:
            self._bgen_library_mgr.invalidate_all_caches()
        except Exception:
            pass

        # Stop the stay-on-top timer first
        if hasattr(self, 'stay_on_top_timer') and self.stay_on_top_timer:
            self.stay_on_top_timer.stop()
            self.stay_on_top_timer.deleteLater()
            self.stay_on_top_timer = None

        if hasattr(self, 'update_checker_timer') and self.update_checker_timer:
            self.update_checker_timer.stop()
            self.update_checker_timer.deleteLater()
            self.update_checker_timer = None
        
        # Cleanup selection synchronization
        try:
            SSM.cleanup_selection_sync()
            print("Selection sync cleanup completed")
        except Exception as e:
            print(f"Error cleaning up selection sync: {e}")
        
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
        # Reposition canvas overlays when canvas_frame resizes
        if obj == self.canvas_frame and event.type() == QtCore.QEvent.Resize:
            if hasattr(self, 'canvas_edit_panel') and self.canvas_edit_panel.isVisible():
                self.canvas_edit_panel._update_position()
            pass  # Border drawn in canvas paintEvent

        '''# Handle double-click on main frame
        if event.type() == QtCore.QEvent.MouseButtonDblClick and obj == self.main_frame:
            # Reset window to default size when double-clicked, using stored position
            self._programmatic_resize = True

            # Store current position for the current size mode before switching
            self._store_current_position()

            new_width = 350

            # Restore stored position for mid mode if available
            if self.stored_positions['mid'] is not None:
                pos = self.stored_positions['mid']
                self.setGeometry(pos.x(), pos.y(), new_width, 450)
            else:
                self.resize(new_width, 450)

            # Update current size mode
            self.current_size_mode = 'mid'

            # Reset fullscreen state
            self.is_fullscreen = False
            self.pre_fullscreen_geometry = None

            self.update_buttons_for_current_tab()
            if not self.edit_mode:
                UT.blender_main_window()
            return True'''

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
        """Stop and delete all timers and msgbus subscriptions"""
        # Cleanup depsgraph handler for scene armature detection
        if hasattr(self, '_scene_depsgraph_fn'):
            try:
                import bpy
                if self._scene_depsgraph_fn in bpy.app.handlers.depsgraph_update_post:
                    bpy.app.handlers.depsgraph_update_post.remove(self._scene_depsgraph_fn)
            except Exception as e:
                print(f"Error cleaning up scene depsgraph handler: {e}")
        
        # Stop and cleanup timers
        for timer_attr in ['resize_timer', 'batch_update_timer', 'widget_update_timer', 'stay_on_top_timer', 'update_checker_timer', 'scene_update_timer', '_scene_change_timer']:
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
        """OPTIMIZED: Properly cleanup a single button and its resources to prevent memory leaks"""
        try:
            # Disconnect button signals to prevent memory leaks
            if hasattr(button, 'changed'):
                try:
                    button.changed.disconnect()
                except:
                    pass
            if hasattr(button, 'clicked'):
                try:
                    button.clicked.disconnect()
                except:
                    pass
            if hasattr(button, 'selected'):
                try:
                    button.selected.disconnect()
                except:
                    pass
            if hasattr(button, 'deselected'):
                try:
                    button.deselected.disconnect()
                except:
                    pass
            
            # Clear pixmap cache to free memory
            if hasattr(button, 'text_pixmap'):
                button.text_pixmap = None
            if hasattr(button, 'pose_pixmap'):
                button.pose_pixmap = None
            if hasattr(button, 'thumbnail_pixmap'):
                button.thumbnail_pixmap = None
            
            # Clear object references
            if hasattr(button, 'assigned_objects'):
                button.assigned_objects.clear()
            
            # Remove from parent and delete
            button.setParent(None)
            button.deleteLater()
            
        except Exception as e:
            print(f"Error cleaning up button {getattr(button, 'unique_id', 'unknown')}: {e}")

    def _cleanup_data_structures(self):
        """OPTIMIZED: Clear all data structure caches and optimize memory"""
        # Clear pending updates in data manager
        DM.PickerDataManager.flush_pending_saves()
        
        # Clear cache
        DM.PickerDataManager.clear_cache()
        
        # Disable non-active canvases to save resources
        if hasattr(self, 'tab_system') and self.tab_system.current_tab:
            for tab_name, tab_data in self.tab_system.tabs.items():
                canvas = tab_data.get('canvas')
                if canvas:
                    is_active = (tab_name == self.tab_system.current_tab)
                    canvas.setUpdatesEnabled(is_active)
                    canvas.setMouseTracking(is_active)
        
        # Force Qt garbage collection
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
        
        print("Performed data structure cleanup and optimization")
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
    
