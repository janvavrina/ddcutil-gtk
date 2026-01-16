"""Main entry point for DDCUtil GTK application."""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import NoReturn

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk

from .window import MainWindow


class DDCUtilApplication(Adw.Application):
    """Main GTK application class."""

    def __init__(self):
        super().__init__(
            application_id="org.ddcutil.gtk",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

        self._window: MainWindow | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        # Add command line options
        self.add_main_option(
            "background",
            ord("b"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.NONE,
            "Start in background mode",
            None,
        )

    def do_startup(self) -> None:
        """Handle application startup."""
        Adw.Application.do_startup(self)

        # Set up asyncio integration with GLib
        self._setup_asyncio()

        # Set up actions
        self._setup_actions()

    def _setup_asyncio(self) -> None:
        """Set up asyncio event loop integration with GLib."""
        # Create a new event loop
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # Integrate with GLib main loop
        def glib_iteration() -> bool:
            """Run pending asyncio tasks."""
            self._loop.stop()
            self._loop.run_forever()
            return True

        # Schedule asyncio integration
        GLib.timeout_add(50, glib_iteration)

    def _setup_actions(self) -> None:
        """Set up application actions."""
        # About action
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

        # Quit action
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self._on_quit)
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])

    def do_activate(self) -> None:
        """Handle application activation."""
        if not self._window:
            self._window = MainWindow(self)

        self._window.present()

    def do_handle_local_options(self, options: GLib.VariantDict) -> int:
        """Handle command line options."""
        if options.contains("background"):
            # Start in background mode - just register without showing window
            # The window will be shown when activated via DBus
            pass

        return -1  # Continue normal processing

    def _on_about(self, action: Gio.SimpleAction, param: None) -> None:
        """Show about dialog."""
        about = Adw.AboutDialog.new()
        about.set_application_name("DDCUtil Monitor Control")
        about.set_version("0.1.0")
        about.set_developer_name("Jan Vavřina")
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_comments("Control your monitor settings via DDC/CI")
        about.set_website("https://github.com/janvavrina/ddcutil-gtk")
        about.set_issue_url("https://github.com/janvavrina/ddcutil-gtk/issues")
        about.set_application_icon("video-display-symbolic")

        about.present(self._window)

    def _on_quit(self, action: Gio.SimpleAction, param: None) -> None:
        """Handle quit action."""
        self.quit()


def main() -> NoReturn:
    """Main entry point."""
    # Handle Ctrl+C gracefully
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Set default icon for all windows (must be done before creating application)
    Gtk.Window.set_default_icon_name("video-display-symbolic")

    app = DDCUtilApplication()
    exit_code = app.run(sys.argv)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
