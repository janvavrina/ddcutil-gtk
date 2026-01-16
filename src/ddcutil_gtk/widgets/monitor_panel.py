"""Monitor control panel widget."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk

from .vcp_control import VCPCombo, VCPSlider

if TYPE_CHECKING:
    from ..ddcutil import DDCUtil, VCPValue
    from ..monitor import Monitor


class MonitorPanel(Gtk.ScrolledWindow):
    """Panel showing all VCP controls for a single monitor."""

    def __init__(
        self,
        monitor: "Monitor",
        ddcutil: "DDCUtil",
        on_vcp_change: Callable[[int, int, int], None] | None = None,
    ):
        super().__init__()

        self.monitor = monitor
        self.ddcutil = ddcutil
        self._on_vcp_change = on_vcp_change
        self._controls: dict[int, VCPSlider | VCPCombo] = {}

        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.set_propagate_natural_height(True)

        # Main content box
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        self._content.set_margin_top(24)
        self._content.set_margin_bottom(24)
        self._content.set_margin_start(24)
        self._content.set_margin_end(24)

        # Clamp for responsive width
        clamp = Adw.Clamp()
        clamp.set_maximum_size(600)
        clamp.set_child(self._content)

        self.set_child(clamp)

        # Build the UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the control groups."""
        from ..ddcutil import DDCUtil

        # Create groups based on feature categories
        for group_name, feature_codes in DDCUtil.FEATURE_GROUPS.items():
            group = self._create_group(group_name, feature_codes)
            if group:
                self._content.append(group)

    def _create_group(
        self, title: str, feature_codes: list[int]
    ) -> Adw.PreferencesGroup | None:
        """Create a preferences group for a set of features."""
        from ..ddcutil import DDCUtil

        group = Adw.PreferencesGroup()
        group.set_title(title)

        has_controls = False

        for code in feature_codes:
            # Check if monitor supports this feature
            if not self.monitor.supports_feature(code):
                continue

            control = self._create_control(code)
            if control:
                group.add(control)
                self._controls[code] = control
                has_controls = True

        return group if has_controls else None

    def _create_control(self, feature_code: int) -> VCPSlider | VCPCombo | None:
        """Create appropriate control widget for a VCP feature."""
        from ..ddcutil import DDCUtil

        name = DDCUtil.get_feature_name(feature_code)
        value = self.monitor.get_vcp_value(feature_code)

        if DDCUtil.is_continuous(feature_code):
            # Slider for continuous values
            current = value.current if value else 50
            maximum = value.maximum if value else 100

            return VCPSlider(
                feature_code=feature_code,
                title=name,
                current=current,
                maximum=maximum,
                on_change=self._handle_vcp_change,
            )

        elif DDCUtil.is_non_continuous(feature_code):
            # Dropdown for discrete values
            options = self._get_options_for_feature(feature_code)

            # Skip if no options available
            if not options:
                return None

            current = value.current if value else 0

            return VCPCombo(
                feature_code=feature_code,
                title=name,
                options=options,
                current=current,
                on_change=self._handle_vcp_change,
            )

        return None

    def _get_options_for_feature(self, feature_code: int) -> list[tuple[int, str]]:
        """Get available options for a non-continuous feature.

        Uses actual monitor capabilities if available, falls back to defaults.
        """
        # First, try to get options from monitor's capabilities
        options = self.monitor.get_feature_options(feature_code)
        if options:
            return options

        # No options available from capabilities
        return []

    def _handle_vcp_change(self, feature_code: int, value: int) -> None:
        """Handle VCP value change from a control."""
        if self._on_vcp_change:
            self._on_vcp_change(self.monitor.display_number, feature_code, value)

    def update_value(self, feature_code: int, value: "VCPValue") -> None:
        """Update a control with a new value."""
        control = self._controls.get(feature_code)
        if control:
            if isinstance(control, VCPSlider):
                control.set_value(value.current, value.maximum)
            elif isinstance(control, VCPCombo):
                control.set_value(value.current)

    def set_loading(self, loading: bool) -> None:
        """Set loading state for all controls."""
        for control in self._controls.values():
            if isinstance(control, VCPSlider):
                control.set_sensitive_state(not loading)
            else:
                control.set_sensitive(not loading)

    def refresh_controls(self) -> None:
        """Refresh control values from monitor cache."""
        for code, control in self._controls.items():
            value = self.monitor.get_vcp_value(code)
            if value:
                self.update_value(code, value)
