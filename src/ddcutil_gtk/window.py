"""Main application window."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk

from .ddcutil import DDCUtil, DDCUtilError
from .monitor import Monitor
from .widgets import MonitorPanel

if TYPE_CHECKING:
    from .ddcutil import VCPValue


class MainWindow(Adw.ApplicationWindow):
    """Main application window with monitor controls."""

    def __init__(self, application: Adw.Application):
        super().__init__(application=application)

        self.set_title("DDCUtil Monitor Control")
        self.set_icon_name("video-display-symbolic")
        self.set_default_size(500, 600)

        self._ddcutil: DDCUtil | None = None
        self._monitors: list[Monitor] = []
        self._panels: dict[int, MonitorPanel] = {}
        self._loading = False

        self._build_ui()

        # Initialize async
        GLib.idle_add(self._start_async_init)

    def _build_ui(self) -> None:
        """Build the main UI structure."""
        # Toast overlay for notifications (root container)
        self._toast_overlay = Adw.ToastOverlay()
        self.set_content(self._toast_overlay)

        # Main layout
        self._main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self._toast_overlay.set_child(self._main_box)

        # Header bar
        header = Adw.HeaderBar()

        # Refresh button
        self._refresh_button = Gtk.Button.new_from_icon_name("view-refresh-symbolic")
        self._refresh_button.set_tooltip_text("Refresh monitors")
        self._refresh_button.connect("clicked", self._on_refresh_clicked)
        header.pack_start(self._refresh_button)

        # Elevated privileges indicator (hidden by default)
        self._elevated_indicator = Gtk.Image.new_from_icon_name("system-lock-screen-symbolic")
        self._elevated_indicator.set_tooltip_text("Running with elevated privileges")
        self._elevated_indicator.set_visible(False)
        header.pack_start(self._elevated_indicator)

        # Menu button
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_tooltip_text("Menu")

        # Create menu
        menu = Gio.Menu()
        menu.append("About", "app.about")
        menu.append("Quit", "app.quit")
        menu_button.set_menu_model(menu)

        header.pack_end(menu_button)

        self._main_box.append(header)

        # Stack for monitor views
        self._stack = Adw.ViewStack()
        self._stack.set_vexpand(True)

        # Stack switcher (tabs)
        self._switcher = Adw.ViewSwitcher()
        self._switcher.set_stack(self._stack)
        self._switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(self._switcher)

        self._main_box.append(self._stack)

        # Status page for empty/loading state
        self._status_page = Adw.StatusPage()
        self._status_page.set_icon_name("computer-symbolic")
        self._status_page.set_title("Detecting Monitors...")
        self._status_page.set_description("Please wait while scanning for displays")

        # Spinner for loading
        self._spinner = Gtk.Spinner()
        self._spinner.set_size_request(32, 32)
        self._status_page.set_child(self._spinner)
        self._spinner.start()

        self._stack.add_titled(self._status_page, "status", "Status")

    def _start_async_init(self) -> bool:
        """Start async initialization."""
        asyncio.get_event_loop().create_task(self._async_init())
        return False  # Don't repeat

    async def _async_init(self) -> None:
        """Async initialization."""
        try:
            self._ddcutil = DDCUtil()
            await self._detect_monitors()
        except DDCUtilError as e:
            self._show_error(str(e))

    async def _detect_monitors(self) -> None:
        """Detect and load monitors."""
        if not self._ddcutil:
            return

        self._set_loading(True)

        try:
            # Detect monitors
            monitor_infos = await self._ddcutil.detect_monitors()

            if not monitor_infos:
                self._show_no_monitors()
                return

            # Create monitor objects
            self._monitors = [Monitor.from_info(info) for info in monitor_infos]

            # Load capabilities and VCP values for each monitor
            for monitor in self._monitors:
                await self._load_monitor_capabilities(monitor)
                await self._load_monitor_values(monitor)

            # Build UI for monitors
            self._build_monitor_panels()

        except DDCUtilError as e:
            self._show_error(str(e))
        finally:
            self._set_loading(False)

    async def _load_monitor_capabilities(self, monitor: Monitor) -> None:
        """Load monitor capabilities (supported features and their options)."""
        if not self._ddcutil:
            return

        try:
            supported, feature_options = await self._ddcutil.get_capabilities(
                monitor.display_number
            )
            monitor.supported_features = supported
            monitor.feature_options = feature_options
        except DDCUtilError:
            # Capabilities not available, will use defaults
            pass

    async def _load_monitor_values(self, monitor: Monitor) -> None:
        """Load VCP values for a monitor."""
        if not self._ddcutil:
            return

        # Features to load - batch them in a single call
        features = [
            DDCUtil.VCP_BRIGHTNESS,
            DDCUtil.VCP_CONTRAST,
            DDCUtil.VCP_VOLUME,
            DDCUtil.VCP_INPUT_SOURCE,
        ]

        try:
            # Get all values in a single ddcutil call
            values = await self._ddcutil.get_vcp_multiple(
                monitor.display_number, features
            )
            for value in values.values():
                monitor.set_vcp_value(value)
        except DDCUtilError:
            # Features not supported or error, skip
            pass

    def _build_monitor_panels(self) -> None:
        """Build panels for all detected monitors."""
        # Clear the stack completely
        child = self._stack.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self._stack.remove(child)
            child = next_child

        # Add panel for each monitor
        for monitor in self._monitors:
            panel = MonitorPanel(
                monitor=monitor,
                ddcutil=self._ddcutil,
                on_vcp_change=self._on_vcp_change,
            )
            self._panels[monitor.display_number] = panel

            page = self._stack.add_titled(
                panel,
                f"monitor-{monitor.display_number}",
                monitor.short_name,
            )
            page.set_icon_name("video-display-symbolic")

        # Select first monitor
        if self._monitors:
            first_panel = self._panels.get(self._monitors[0].display_number)
            if first_panel:
                self._stack.set_visible_child(first_panel)

    def _show_no_monitors(self) -> None:
        """Show message when no monitors found."""
        self._status_page.set_icon_name("dialog-warning-symbolic")
        self._status_page.set_title("No Monitors Found")

        # Check if we can offer pkexec authentication
        can_authenticate = (
            self._ddcutil
            and self._ddcutil.has_pkexec()
            and not self._ddcutil.is_privileged
        )

        if can_authenticate:
            self._status_page.set_description(
                "No DDC/CI compatible monitors were detected.\n\n"
                "This may be a permissions issue. You can authenticate\n"
                "to run with elevated privileges."
            )
            # Create authenticate button
            auth_button = Gtk.Button(label="Authenticate")
            auth_button.add_css_class("suggested-action")
            auth_button.add_css_class("pill")
            auth_button.set_halign(Gtk.Align.CENTER)
            auth_button.connect("clicked", self._on_authenticate_clicked)
            self._status_page.set_child(auth_button)
        else:
            self._status_page.set_description(
                "No DDC/CI compatible monitors were detected.\n\n"
                "Make sure:\n"
                "- Your monitor supports DDC/CI\n"
                "- DDC/CI is enabled in monitor settings\n"
                "- You have permission to access I2C devices\n\n"
                "Try: sudo usermod -aG i2c $USER"
            )
            self._status_page.set_child(None)

        self._spinner.stop()

    def _show_error(self, message: str) -> None:
        """Show error message."""
        self._status_page.set_icon_name("dialog-error-symbolic")
        self._status_page.set_title("Error")
        self._status_page.set_description(message)
        self._spinner.stop()
        self._status_page.set_child(None)

    def _set_loading(self, loading: bool) -> None:
        """Set loading state."""
        self._loading = loading
        self._refresh_button.set_sensitive(not loading)

        if loading:
            self._spinner.start()
        else:
            self._spinner.stop()

        for panel in self._panels.values():
            panel.set_loading(loading)

    def _on_refresh_clicked(self, button: Gtk.Button) -> None:
        """Handle refresh button click."""
        asyncio.get_event_loop().create_task(self._refresh_monitors())

    async def _refresh_monitors(self) -> None:
        """Refresh monitor values."""
        self._set_loading(True)

        try:
            for monitor in self._monitors:
                await self._load_monitor_values(monitor)
                panel = self._panels.get(monitor.display_number)
                if panel:
                    panel.refresh_controls()

            self._show_toast("Values refreshed")
        except DDCUtilError as e:
            self._show_toast(f"Error: {e}")
        finally:
            self._set_loading(False)

    def _on_vcp_change(self, display: int, feature_code: int, value: int) -> None:
        """Handle VCP value change from a control."""
        asyncio.get_event_loop().create_task(
            self._set_vcp_value(display, feature_code, value)
        )

    async def _set_vcp_value(
        self, display: int, feature_code: int, value: int
    ) -> None:
        """Set VCP value asynchronously."""
        if not self._ddcutil:
            return

        # Show loading state on the control
        panel = self._panels.get(display)
        if panel:
            panel.set_control_loading(feature_code, True)

        try:
            success = await self._ddcutil.set_vcp(display, feature_code, value)
            if not success:
                self._show_toast("Failed to set value")
        except DDCUtilError as e:
            self._show_toast(f"Error: {e}")
        finally:
            # Clear loading state
            if panel:
                panel.set_control_loading(feature_code, False)

    def _show_toast(self, message: str) -> None:
        """Show a toast notification."""
        toast = Adw.Toast.new(message)
        toast.set_timeout(2)
        self._toast_overlay.add_toast(toast)

    def _on_authenticate_clicked(self, button: Gtk.Button) -> None:
        """Handle authenticate button click."""
        asyncio.get_event_loop().create_task(self._do_authenticate())

    async def _do_authenticate(self) -> None:
        """Perform authentication and retry detection."""
        if not self._ddcutil:
            return

        # Reset UI to loading state
        self._status_page.set_icon_name("computer-symbolic")
        self._status_page.set_title("Authenticating...")
        self._status_page.set_description(
            "Please enter your password when prompted..."
        )
        self._status_page.set_child(self._spinner)
        self._spinner.start()

        # Authenticate - this prompts for password ONCE
        success = await self._ddcutil.authenticate()

        if success:
            self._elevated_indicator.set_visible(True)
            self._status_page.set_title("Detecting Monitors...")
            self._status_page.set_description("Please wait while scanning for displays")
            # Retry detection with elevated privileges
            await self._detect_monitors()
        else:
            self._show_error("Authentication failed or was cancelled.")
