"""VCP feature control widgets."""

from __future__ import annotations

from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk


class VCPSlider(Adw.ActionRow):
    """Slider control for continuous VCP features (brightness, contrast, etc.)."""

    def __init__(
        self,
        feature_code: int,
        title: str,
        current: int = 0,
        maximum: int = 100,
        on_change: Callable[[int, int], None] | None = None,
    ):
        super().__init__()

        self.feature_code = feature_code
        self._maximum = maximum
        self._on_change = on_change
        self._updating = False
        self._is_loading = False
        self._is_dragging = False
        self._value_before_drag: int | None = None

        self.set_title(title)

        # Create slider
        self._scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, maximum, 1
        )
        self._scale.set_value(current)
        self._scale.set_hexpand(True)
        self._scale.set_size_request(200, -1)
        self._scale.set_draw_value(False)
        self._scale.add_css_class("vcp-slider")

        # Value label
        self._value_label = Gtk.Label()
        self._value_label.set_width_chars(7)
        self._value_label.add_css_class("dim-label")
        self._value_label.add_css_class("numeric")
        self._update_label(current)

        # Loading spinner (hidden by default)
        self._spinner = Gtk.Spinner()
        self._spinner.set_size_request(16, 16)
        self._spinner.set_visible(False)

        # Box to hold slider, label, and spinner
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_valign(Gtk.Align.CENTER)
        box.append(self._scale)
        box.append(self._value_label)
        box.append(self._spinner)

        self.add_suffix(box)

        # Connect value-changed to update label in real-time
        self._scale.connect("value-changed", self._on_value_changed)

        # Use click gesture to detect press/release for applying values
        click_gesture = Gtk.GestureClick()
        click_gesture.connect("pressed", self._on_press)
        click_gesture.connect("stopped", self._on_release)
        click_gesture.connect("cancel", self._on_release)
        self._scale.add_controller(click_gesture)

    def _update_label(self, value: int) -> None:
        """Update the value label."""
        self._value_label.set_text(f"{value}/{self._maximum}")

    def _on_value_changed(self, scale: Gtk.Scale) -> None:
        """Handle slider value change - only update label, don't apply yet."""
        if self._updating:
            return

        value = int(scale.get_value())
        self._update_label(value)

    def _on_press(self, gesture: Gtk.GestureClick, n_press: int, x: float, y: float) -> None:
        """Called when user presses on the slider."""
        self._is_dragging = True
        self._value_before_drag = int(self._scale.get_value())

    def _on_release(self, gesture: Gtk.GestureClick, *args) -> None:
        """Called when gesture ends (release or cancel) - apply the value."""
        if not self._is_dragging:
            return

        self._is_dragging = False
        value = int(self._scale.get_value())

        # Only apply if value actually changed
        if self._on_change and value != self._value_before_drag:
            self.set_loading(True)
            self._on_change(self.feature_code, value)

        self._value_before_drag = None

    def set_value(self, value: int, maximum: int | None = None) -> None:
        """Set the slider value programmatically."""
        self._updating = True
        if maximum is not None and maximum != self._maximum:
            self._maximum = maximum
            self._scale.set_range(0, maximum)
        self._scale.set_value(value)
        self._update_label(value)
        self._updating = False

    def set_sensitive_state(self, sensitive: bool) -> None:
        """Set whether the control is sensitive."""
        self._scale.set_sensitive(sensitive)

    def set_loading(self, loading: bool) -> None:
        """Set loading state - shows spinner and disables control."""
        self._is_loading = loading
        self._scale.set_sensitive(not loading)
        self._spinner.set_visible(loading)
        if loading:
            self._spinner.start()
        else:
            self._spinner.stop()


class VCPCombo(Adw.ComboRow):
    """Dropdown control for non-continuous VCP features (input source, etc.)."""

    def __init__(
        self,
        feature_code: int,
        title: str,
        options: list[tuple[int, str]],
        current: int = 0,
        on_change: Callable[[int, int], None] | None = None,
    ):
        super().__init__()

        self.feature_code = feature_code
        self._on_change = on_change
        self._options = options  # List of (value, name) tuples
        self._updating = False
        self._is_loading = False

        self.set_title(title)

        # Loading spinner (hidden by default)
        self._spinner = Gtk.Spinner()
        self._spinner.set_size_request(16, 16)
        self._spinner.set_visible(False)
        self.add_suffix(self._spinner)

        # Create string list for options
        string_list = Gtk.StringList()
        for _, name in options:
            string_list.append(name)

        self.set_model(string_list)

        # Set current selection
        self._set_selection_by_value(current)

        # Connect signal
        self.connect("notify::selected", self._on_selected_changed)

    def _set_selection_by_value(self, value: int) -> None:
        """Set selection by VCP value."""
        for i, (opt_value, _) in enumerate(self._options):
            if opt_value == value:
                self.set_selected(i)
                return
        # If not found, select first
        if self._options:
            self.set_selected(0)

    def _on_selected_changed(self, row: Adw.ComboRow, param) -> None:
        """Handle selection change."""
        if self._updating:
            return

        selected = self.get_selected()
        if selected < len(self._options):
            value = self._options[selected][0]
            if self._on_change:
                self._on_change(self.feature_code, value)

    def set_value(self, value: int) -> None:
        """Set the selection by VCP value."""
        self._updating = True
        self._set_selection_by_value(value)
        self._updating = False

    def update_options(self, options: list[tuple[int, str]], current: int) -> None:
        """Update available options."""
        self._updating = True
        self._options = options

        string_list = Gtk.StringList()
        for _, name in options:
            string_list.append(name)
        self.set_model(string_list)

        self._set_selection_by_value(current)
        self._updating = False

    def set_loading(self, loading: bool) -> None:
        """Set loading state - shows spinner and disables control."""
        self._is_loading = loading
        self.set_sensitive(not loading)
        self._spinner.set_visible(loading)
        if loading:
            self._spinner.start()
        else:
            self._spinner.stop()
