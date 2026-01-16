#!/bin/bash
# Run the application in development mode

cd "$(dirname "$0")"

# Temporarily install desktop file so GNOME can find the icon
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"
cp data/org.ddcutil.gtk.desktop "$DESKTOP_DIR/" 2>/dev/null || true

# Update desktop database
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

# Clean up on exit
cleanup() {
    rm -f "$DESKTOP_DIR/org.ddcutil.gtk.desktop"
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
}
trap cleanup EXIT

PYTHONPATH=src python3 -m ddcutil_gtk.main "$@"
