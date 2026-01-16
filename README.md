# DDCUtil GTK

A modern GTK4 + libadwaita GUI for controlling monitor settings via DDC/CI using ddcutil.

## Disclaimer

This project is fully vibecoded.

## Features

- Brightness, contrast, and backlight control
- Input source selection
- Volume control and mute
- Color presets and RGB gain adjustments
- Support for multiple monitors with individual controls
- Modern GNOME-style interface
- Integrated authentication via PolicyKit (pkexec) for systems requiring elevated privileges

## Requirements

- Python 3.10+
- GTK 4.0+
- libadwaita 1.0+
- ddcutil 2.0+
- PyGObject

## Installation

### System Dependencies

**Fedora:**
```bash
sudo dnf install ddcutil gtk4 libadwaita python3-gobject
```

**Ubuntu/Debian:**
```bash
sudo apt install ddcutil gir1.2-gtk-4.0 gir1.2-adw-1 python3-gi
```

**Arch Linux:**
```bash
sudo pacman -S ddcutil gtk4 libadwaita python-gobject
```

### I2C Permissions

ddcutil requires access to I2C devices. Add your user to the `i2c` group:

```bash
sudo usermod -aG i2c $USER
```

Then log out and back in for the change to take effect.

### Install the Application

```bash
pip install .
```

Or run directly from source:

```bash
./run.sh
```

## Usage

Launch the application:

```bash
ddcutil-gtk
```

Or use the desktop entry after installation.

## Troubleshooting

### No monitors detected

1. Make sure DDC/CI is enabled in your monitor's settings
2. Check I2C permissions: `ls -la /dev/i2c-*`
3. Run `ddcutil detect` to verify ddcutil can see your monitors
4. Run `ddcutil environment` to diagnose issues

### Permission denied

**Option 1: Use the Authenticate button**

If no monitors are detected due to permissions, the app will show an "Authenticate" button. Click it to run ddcutil with elevated privileges via PolicyKit (pkexec). You'll be prompted for your password.

For a nicer authentication dialog, install the PolicyKit policy:
```bash
sudo cp data/org.ddcutil.gtk.policy /usr/share/polkit-1/actions/
```

**Option 2: Add user to i2c group (permanent fix)**

Add your user to the i2c group and re-login:
```bash
sudo usermod -aG i2c $USER
```

This is the recommended long-term solution as it doesn't require authentication each time.

## License

GPL-3.0-or-later
