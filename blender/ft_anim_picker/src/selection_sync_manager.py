"""
Selection Synchronization Manager for BGEN Picker
Provides 2-way selection synchronization between Blender and the picker interface.

Architecture (event-driven with debounced Qt updates):
  - Blender handlers (depsgraph, msgbus, undo/redo, frame_change) detect selection
    changes and cache the state in Python variables.
  - A single-shot QTimer (50ms debounce) reads the cached state and updates
    Qt/picker widgets.
  - Neither path crosses the Blender<->Qt event-loop boundary directly.
"""

import bpy
from PySide6 import QtCore
from PySide6.QtCore import QObject, Signal, QTimer
import weakref
import warnings
import threading
from typing import Set, List, Optional, Tuple


class SelectionSyncManager(QObject):
    """
    Manages 2-way selection synchronization between BGEN Picker and Blender.
    """

    # Signals
    blender_selection_changed = Signal(list, list)  # objects, bones

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        super().__init__()

        # State management
        self._sync_enabled = True
        self._sync_lock = False  # Prevents infinite loops
        self._registered_canvases = weakref.WeakSet()

        # Blender state tracking
        self._last_selected_objects = set()
        self._last_selected_bones = set()
        self._last_active_object = None
        self._last_mode = None

        # Click-order history (preserved across selection updates).
        # Items appended in the order they appeared in the current selection;
        # the active item is promoted to the end (most-recent).
        self._selection_history_objects = []        # list[str]
        self._selection_history_bones = []          # list[tuple[str, str]]  (armature_name, bone_name)

        # Timer for debounced updates
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._process_blender_selection_change)

        # msgbus subscription owner (for cleanup)
        self._msgbus_owner = object()

        # Button lookup optimization
        self._button_lookup = {}

        # Setup Blender monitoring
        self._setup_blender_handlers()


    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def cleanup_instance(cls):
        if cls._instance:
            cls._instance.cleanup()
            cls._instance = None

    # ------------------------------------------------------------------
    # Canvas registration
    # ------------------------------------------------------------------

    def register_canvas(self, canvas):
        self._registered_canvases.add(canvas)

        if hasattr(canvas, 'button_selection_changed'):
            canvas.button_selection_changed.connect(self._on_picker_selection_changed)

        self._build_button_lookup(canvas)

    def unregister_canvas(self, canvas):
        try:
            self._registered_canvases.discard(canvas)
            if hasattr(canvas, 'button_selection_changed'):
                try:
                    canvas.button_selection_changed.disconnect(self._on_picker_selection_changed)
                except Exception:
                    pass
            if canvas in self._button_lookup:
                del self._button_lookup[canvas]
            if hasattr(self, '_prev_selected_buttons'):
                self._prev_selected_buttons.pop(canvas, None)
        except Exception as e:
            print(f"SelectionSyncManager: Error unregistering canvas: {e}")

    def set_sync_enabled(self, enabled: bool):
        self._sync_enabled = enabled

    # ------------------------------------------------------------------
    # Blender handler setup
    # ------------------------------------------------------------------

    def _setup_blender_handlers(self):
        """Setup msgbus subscriptions and handlers to monitor selection changes"""
        try:
            self._cleanup_blender_handlers()

            _self_ref = weakref.ref(self)

            # Import the module-level visibility gate lazily to avoid circular import.
            try:
                from . import blender_main as _BM
                _is_visible = _BM.is_any_picker_visible
            except Exception:
                _is_visible = lambda: True

            # --- Depsgraph handler: detects selection changes ---
            def _on_depsgraph_update(scene, depsgraph):
                s = _self_ref()
                if s is None or not s._sync_enabled or s._sync_lock:
                    return
                # Skip all scene queries when no picker window is visible —
                # this is the dominant cost in heavy scenes.
                if not _is_visible():
                    return
                try:
                    current_objects = s._get_current_selected_objects()
                    current_bones = s._get_current_selected_bones()
                    current_active = None
                    current_mode = None
                    try:
                        current_active = bpy.context.view_layer.objects.active
                        current_mode = bpy.context.mode
                    except Exception:
                        return

                    selection_changed = (
                        current_objects != s._last_selected_objects
                        or current_bones != s._last_selected_bones
                        or current_active != s._last_active_object
                        or current_mode != s._last_mode
                    )
                    if not current_objects and not current_bones and (
                        s._last_selected_objects or s._last_selected_bones
                    ):
                        selection_changed = True

                    if selection_changed:
                        s._last_selected_objects = current_objects
                        s._last_selected_bones = current_bones
                        s._last_active_object = current_active
                        s._last_mode = current_mode
                        s._update_selection_history()
                        if not s._update_timer.isActive():
                            s._update_timer.start(50)
                except Exception:
                    pass

            _on_depsgraph_update._bpy_persistent = True
            self._depsgraph_fn = _on_depsgraph_update
            bpy.app.handlers.depsgraph_update_post.append(self._depsgraph_fn)

            # --- Frame change handler: for pose mode bone selection ---
            def _on_frame_change(scene):
                s = _self_ref()
                if s is None or not s._sync_enabled or s._sync_lock:
                    return
                # Skip when picker is not visible.
                if not _is_visible():
                    return
                try:
                    if bpy.context.mode != 'POSE':
                        return
                    # During animation playback the selection cannot change —
                    # rebuilding the pose-bone set every frame is wasted work.
                    try:
                        screen = bpy.context.screen
                        if screen is not None and getattr(screen, 'is_animation_playing', False):
                            return
                    except Exception:
                        pass
                    current_bones = s._get_current_selected_bones()
                    if current_bones != s._last_selected_bones:
                        s._last_selected_bones = current_bones
                        s._update_selection_history()
                        if not s._update_timer.isActive():
                            s._update_timer.start(50)
                except Exception:
                    pass

            _on_frame_change._bpy_persistent = True
            self._frame_change_fn = _on_frame_change
            bpy.app.handlers.frame_change_post.append(self._frame_change_fn)

            # --- Undo/Redo handlers ---
            def _on_undo(scene):
                s = _self_ref()
                if s is None or not s._sync_enabled:
                    return
                if not s._update_timer.isActive():
                    s._update_timer.start(100)

            _on_undo._bpy_persistent = True
            self._undo_fn = _on_undo
            bpy.app.handlers.undo_post.append(self._undo_fn)

            def _on_redo(scene):
                s = _self_ref()
                if s is None or not s._sync_enabled:
                    return
                if not s._update_timer.isActive():
                    s._update_timer.start(100)

            _on_redo._bpy_persistent = True
            self._redo_fn = _on_redo
            bpy.app.handlers.redo_post.append(self._redo_fn)

            # --- msgbus: active object changes ---
            try:
                subscribe_to = bpy.types.LayerObjects, "active"
                bpy.msgbus.subscribe_rna(
                    key=subscribe_to,
                    owner=self._msgbus_owner,
                    args=(),
                    notify=self._on_msgbus_selection_changed,
                    options={'PERSISTENT'}
                )
            except Exception as e:
                print(f"SelectionSyncManager: Could not subscribe to LayerObjects.active: {e}")


        except Exception as e:
            print(f"SelectionSyncManager: Error setting up handlers: {e}")

    def _cleanup_blender_handlers(self):
        """Remove msgbus subscriptions and Blender handlers"""
        try:
            try:
                bpy.msgbus.clear_by_owner(self._msgbus_owner)
            except Exception:
                pass

            handler_attrs = [
                (bpy.app.handlers.depsgraph_update_post, '_depsgraph_fn'),
                (bpy.app.handlers.frame_change_post, '_frame_change_fn'),
                (bpy.app.handlers.undo_post, '_undo_fn'),
                (bpy.app.handlers.redo_post, '_redo_fn'),
            ]
            for handler_list, attr_name in handler_attrs:
                fn = getattr(self, attr_name, None)
                if fn is not None:
                    try:
                        handler_list.remove(fn)
                    except ValueError:
                        pass
        except Exception as e:
            print(f"SelectionSyncManager: Error cleaning up handlers: {e}")

    # ------------------------------------------------------------------
    # msgbus callback
    # ------------------------------------------------------------------

    def _on_msgbus_selection_changed(self):
        """Callback for msgbus selection change events"""
        if not self._sync_enabled or self._sync_lock:
            return
        try:
            from . import blender_main as _BM
            if not _BM.is_any_picker_visible():
                return
        except Exception:
            pass
        try:
            current_objects = self._get_current_selected_objects()
            current_bones = self._get_current_selected_bones()
            current_active = bpy.context.view_layer.objects.active
            current_mode = bpy.context.mode

            selection_changed = (
                current_objects != self._last_selected_objects
                or current_bones != self._last_selected_bones
                or current_active != self._last_active_object
                or current_mode != self._last_mode
            )
            if not current_objects and not current_bones and (
                self._last_selected_objects or self._last_selected_bones
            ):
                selection_changed = True

            if selection_changed:
                self._last_selected_objects = current_objects
                self._last_selected_bones = current_bones
                self._last_active_object = current_active
                self._last_mode = current_mode
                self._update_selection_history()
                if not self._update_timer.isActive():
                    self._update_timer.start(50)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Selection state helpers
    # ------------------------------------------------------------------

    def _get_current_selected_objects(self) -> Set[str]:
        try:
            return {obj.name for obj in bpy.context.selected_objects}
        except Exception:
            return set()

    def _get_current_selected_bones(self) -> Set[Tuple[str, str]]:
        try:
            bones = set()
            if bpy.context.mode == 'POSE':
                # Use selected_pose_bones first - returns bones from ALL
                # armatures currently in pose mode (multi-rig support).
                # Fall back to active-object-only variant for older Blender.
                selected = getattr(bpy.context, 'selected_pose_bones', None)
                if not selected:
                    selected = getattr(bpy.context, 'selected_pose_bones_from_active_object', None)
                if selected:
                    for bone in selected:
                        bones.add((bone.id_data.name, bone.name))
            return bones
        except Exception:
            return set()

    def _get_current_selected_objects_ordered(self) -> List[str]:
        try:
            return [obj.name for obj in bpy.context.selected_objects]
        except Exception:
            return []

    def _get_current_selected_bones_ordered(self) -> List[Tuple[str, str]]:
        try:
            if bpy.context.mode != 'POSE':
                return []
            selected = getattr(bpy.context, 'selected_pose_bones', None)
            if not selected:
                selected = getattr(bpy.context, 'selected_pose_bones_from_active_object', None)
            if not selected:
                return []
            return [(b.id_data.name, b.name) for b in selected]
        except Exception:
            return []

    def _update_selection_history(self):
        """Refresh the ordered click-history from the current Blender selection.

        Strategy: drop entries that are no longer selected (preserves order of
        survivors), append newly-added entries in the order Blender returns them,
        then promote the active object/bone to the end of the list so it is
        treated as the most-recent click. Box-selects fall through to data-block
        order (acceptable fallback)."""
        try:
            current_objects = self._get_current_selected_objects_ordered()
            current_set = set(current_objects)
            survivors = [n for n in self._selection_history_objects if n in current_set]
            existing = set(survivors)
            for n in current_objects:
                if n not in existing:
                    survivors.append(n)
                    existing.add(n)
            try:
                active_obj = bpy.context.view_layer.objects.active
                active_name = active_obj.name if active_obj else None
            except Exception:
                active_name = None
            if active_name and active_name in existing and survivors and survivors[-1] != active_name:
                survivors.remove(active_name)
                survivors.append(active_name)
            self._selection_history_objects = survivors
        except Exception:
            pass

        try:
            current_bones = self._get_current_selected_bones_ordered()
            current_set = set(current_bones)
            survivors = [b for b in self._selection_history_bones if b in current_set]
            existing = set(survivors)
            for b in current_bones:
                if b not in existing:
                    survivors.append(b)
                    existing.add(b)
            active_key = None
            try:
                if bpy.context.mode == 'POSE':
                    apb = getattr(bpy.context, 'active_pose_bone', None)
                    if apb is not None:
                        active_key = (apb.id_data.name, apb.name)
            except Exception:
                active_key = None
            if active_key and active_key in existing and survivors and survivors[-1] != active_key:
                survivors.remove(active_key)
                survivors.append(active_key)
            self._selection_history_bones = survivors
        except Exception:
            pass

    def get_ordered_selected_objects(self) -> List[str]:
        """Return the click-ordered list of currently-selected object names."""
        return list(self._selection_history_objects)

    def get_ordered_selected_bones(self) -> List[Tuple[str, str]]:
        """Return the click-ordered list of currently-selected (armature, bone) pairs."""
        return list(self._selection_history_bones)

    # ------------------------------------------------------------------
    # Process selection change (runs in Qt context via QTimer)
    # ------------------------------------------------------------------

    def _process_blender_selection_change(self):
        """Process Blender selection changes and sync to picker"""
        if not self._sync_enabled or self._sync_lock:
            return

        try:
            self._sync_lock = True

            selected_objects = list(self._last_selected_objects)
            selected_bones = list(self._last_selected_bones)

            # Emit signal for any listeners
            self.blender_selection_changed.emit(selected_objects, selected_bones)

            # Update picker canvases
            self._sync_blender_to_picker(selected_objects, selected_bones)

        except Exception as e:
            print(f"SelectionSyncManager: Error processing selection change: {e}")
        finally:
            QTimer.singleShot(50, self._delayed_unlock)

    # ------------------------------------------------------------------
    # Sync logic: Blender -> Picker
    # ------------------------------------------------------------------

    def _sync_blender_to_picker(self, selected_objects: List[str],
                                 selected_bones: List[Tuple[str, str]]):
        """Update picker buttons to match Blender selection using fast lookup only."""
        try:
            for canvas in list(self._registered_canvases):
                if canvas is None:
                    continue

                current_namespace = self._get_canvas_namespace(canvas)
                buttons_to_select = set()

                lookup = self._button_lookup.get(canvas)
                if not lookup:
                    self._build_button_lookup(canvas)
                    lookup = self._button_lookup.get(canvas, {})

                for obj_name in selected_objects:
                    key = ('object', obj_name)
                    if key in lookup:
                        buttons_to_select.update(lookup[key])
                    if current_namespace and current_namespace != 'None':
                        if obj_name.startswith(f"{current_namespace}_"):
                            stripped = obj_name[len(current_namespace) + 1:]
                            skey = ('object', stripped)
                            if skey in lookup:
                                buttons_to_select.update(lookup[skey])

                for armature_name, bone_name in selected_bones:
                    key = ('bone', armature_name, bone_name)
                    if key in lookup:
                        buttons_to_select.update(lookup[key])
                    if current_namespace and current_namespace != 'None':
                        # Match bones using the namespace armature name
                        # (e.g., buttons stored with Rig_A, user posing Rig_B)
                        ns_key = ('bone', current_namespace, bone_name)
                        if ns_key in lookup:
                            buttons_to_select.update(lookup[ns_key])
                        if armature_name.startswith(f"{current_namespace}_"):
                            stripped_arm = armature_name[len(current_namespace) + 1:]
                            skey = ('bone', stripped_arm, bone_name)
                            if skey in lookup:
                                buttons_to_select.update(lookup[skey])
                    # Cross-rig matching by bone name alone, so the same
                    # picker works for duplicated rigs sharing bone names
                    bn_key = ('bone_name', bone_name)
                    if bn_key in lookup:
                        buttons_to_select.update(lookup[bn_key])

                self._update_canvas_selection(canvas, buttons_to_select)

        except Exception as e:
            print(f"SelectionSyncManager: Error syncing to picker: {e}")

    def _get_canvas_namespace(self, canvas) -> Optional[str]:
        try:
            main_window = canvas.window()
            if hasattr(main_window, '_get_current_namespace'):
                return main_window._get_current_namespace()
            elif hasattr(main_window, 'namespace_dropdown'):
                text = main_window.namespace_dropdown.currentText()
                return text if text != 'None' else None
        except Exception:
            pass
        return None

    def _update_canvas_selection(self, canvas, buttons_to_select: Set):
        try:
            # Track the previously-selected-button set per canvas so we only
            # touch the symmetric difference instead of scanning every button
            # on every sync. O(changed) instead of O(all buttons).
            if not hasattr(self, '_prev_selected_buttons'):
                self._prev_selected_buttons = {}
            prev = self._prev_selected_buttons.get(canvas)
            if prev is None:
                # First sync for this canvas — seed from current state so we
                # don't have to scan every button after this point.
                try:
                    prev = {b for b in canvas.buttons
                            if getattr(b, 'is_selected', False)
                            and getattr(b, 'mode', 'select') != 'pose'}
                except Exception:
                    prev = set()

            to_deselect = prev - buttons_to_select
            to_select = buttons_to_select - prev
            if not to_deselect and not to_select:
                return

            try:
                canvas.setUpdatesEnabled(False)
                for button in to_deselect:
                    try:
                        button.is_selected = False
                    except Exception:
                        pass
                for button in to_select:
                    try:
                        button.is_selected = True
                    except Exception:
                        pass
            finally:
                canvas.setUpdatesEnabled(True)

            self._prev_selected_buttons[canvas] = set(buttons_to_select)
            canvas.update()
            canvas._emit_selection_changed()
        except Exception as e:
            print(f"SelectionSyncManager: Error updating canvas: {e}")

    def _delayed_unlock(self):
        self._sync_lock = False

    # ------------------------------------------------------------------
    # Button lookup
    # ------------------------------------------------------------------

    def _build_button_lookup(self, canvas):
        try:
            lookup = {}
            for button in canvas.buttons:
                if not hasattr(button, 'assigned_objects') or not button.assigned_objects:
                    continue
                # Pose buttons often share controls across many poses; syncing
                # them from Blender selection lights up most of the grid and
                # feels noisy. Skip them — user drives pose selection directly.
                if getattr(button, 'mode', 'select') == 'pose':
                    continue
                for obj_data in button.assigned_objects:
                    if obj_data.get('is_bone', False):
                        bone_name = obj_data.get('name', '')
                        armature_name = obj_data.get('armature', '')
                        lookup.setdefault(('bone', armature_name, bone_name), set()).add(button)
                        # Also index by bone name alone for cross-rig matching
                        # (e.g., picker built with Rig_A works for duplicated Rig_A.001)
                        lookup.setdefault(('bone_name', bone_name), set()).add(button)
                    else:
                        obj_name = obj_data.get('name', '')
                        lookup.setdefault(('object', obj_name), set()).add(button)
            self._button_lookup[canvas] = lookup
        except Exception as e:
            print(f"SelectionSyncManager: Error building lookup: {e}")

    def rebuild_button_lookup(self, canvas):
        self._build_button_lookup(canvas)
        # Button set may have changed (adds/deletes) — drop the cached
        # previously-selected set so the next sync reseeds from canvas state.
        if hasattr(self, '_prev_selected_buttons'):
            self._prev_selected_buttons.pop(canvas, None)

    def _on_picker_selection_changed(self):
        # Ignore signals emitted by our own Blender->picker update; only
        # react to genuine user-driven canvas selection changes.
        if self._sync_lock:
            return
        # Picker-side selection changed (user clicked a button on the canvas).
        # Invalidate cached "previously-selected" sets so the next Blender->
        # picker sync reseeds from live canvas state and correctly computes
        # which buttons need to deselect.
        if hasattr(self, '_prev_selected_buttons'):
            self._prev_selected_buttons.clear()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        try:
            self._sync_enabled = False
            if self._update_timer.isActive():
                self._update_timer.stop()
            self._cleanup_blender_handlers()
            self._registered_canvases.clear()
            self._button_lookup.clear()
        except Exception as e:
            print(f"SelectionSyncManager: Error during cleanup: {e}")


# ------------------------------------------------------------------
# Global functions
# ------------------------------------------------------------------

def enable_selection_sync():
    manager = SelectionSyncManager.get_instance()
    manager.set_sync_enabled(True)

def disable_selection_sync():
    manager = SelectionSyncManager.get_instance()
    manager.set_sync_enabled(False)

def register_canvas_for_sync(canvas):
    manager = SelectionSyncManager.get_instance()
    manager.register_canvas(canvas)

def unregister_canvas_from_sync(canvas):
    manager = SelectionSyncManager.get_instance()
    manager.unregister_canvas(canvas)

def cleanup_selection_sync():
    SelectionSyncManager.cleanup_instance()

def rebuild_canvas_lookup(canvas):
    manager = SelectionSyncManager.get_instance()
    manager.rebuild_button_lookup(canvas)

def reconnect_canvas(canvas):
    manager = SelectionSyncManager.get_instance()
    if canvas not in manager._registered_canvases:
        return
    if hasattr(canvas, 'button_selection_changed'):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            try:
                canvas.button_selection_changed.disconnect(
                    manager._on_picker_selection_changed
                )
            except (RuntimeError, TypeError):
                pass
        canvas.button_selection_changed.connect(
            manager._on_picker_selection_changed
        )
