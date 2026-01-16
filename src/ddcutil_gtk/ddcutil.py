"""DDCUtil CLI wrapper for monitor control."""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .privileged_helper import PrivilegedHelper


@dataclass
class VCPValue:
    """Represents a VCP feature value."""

    code: int
    current: int
    maximum: int
    name: str = ""

    @property
    def percentage(self) -> float:
        """Get value as percentage (0-100)."""
        if self.maximum == 0:
            return 0.0
        return (self.current / self.maximum) * 100


@dataclass
class VCPOption:
    """Represents a non-continuous VCP option."""

    value: int
    name: str


@dataclass
class MonitorInfo:
    """Basic monitor information from detection."""

    display_number: int
    i2c_bus: int
    manufacturer: str
    model: str
    serial: str
    edid: str = ""


class DDCUtilError(Exception):
    """Exception raised for ddcutil errors."""

    pass


class PermissionError(DDCUtilError):
    """Exception raised for permission-related errors."""

    pass


class DDCUtil:
    """Wrapper for ddcutil CLI commands."""

    # Common VCP feature codes
    VCP_BRIGHTNESS = 0x10
    VCP_CONTRAST = 0x12
    VCP_BACKLIGHT = 0x13
    VCP_COLOR_PRESET = 0x14
    VCP_RED_GAIN = 0x16
    VCP_GREEN_GAIN = 0x18
    VCP_BLUE_GAIN = 0x1A
    VCP_INPUT_SOURCE = 0x60
    VCP_VOLUME = 0x62
    VCP_MUTE = 0x8D
    VCP_SHARPNESS = 0x87
    VCP_DISPLAY_MODE = 0xDC

    # Feature metadata
    FEATURE_NAMES = {
        0x10: "Brightness",
        0x12: "Contrast",
        0x13: "Backlight",
        0x14: "Color Preset",
        0x16: "Red Gain",
        0x18: "Green Gain",
        0x1A: "Blue Gain",
        0x60: "Input Source",
        0x62: "Volume",
        0x8D: "Audio Mute",
        0x87: "Sharpness",
        0xDC: "Display Mode",
    }

    # Features that use continuous values (sliders)
    CONTINUOUS_FEATURES = {0x10, 0x12, 0x13, 0x16, 0x18, 0x1A, 0x62, 0x87}

    # Features that use discrete values (dropdowns)
    NON_CONTINUOUS_FEATURES = {0x14, 0x60, 0x8D, 0xDC}

    # Feature groups for UI organization
    FEATURE_GROUPS = {
        "Display": [0x10, 0x12, 0x13],
        "Color": [0x14, 0x16, 0x18, 0x1A],
        "Input": [0x60],
        "Audio": [0x62, 0x8D],
        "Image": [0x87, 0xDC],
    }

    # Input source values (common ones)
    INPUT_SOURCES = {
        0x01: "VGA-1",
        0x02: "VGA-2",
        0x03: "DVI-1",
        0x04: "DVI-2",
        0x0F: "DisplayPort-1",
        0x10: "DisplayPort-2",
        0x11: "HDMI-1",
        0x12: "HDMI-2",
        0x13: "HDMI-3",
        0x14: "HDMI-4",
    }

    def __init__(self):
        self._ddcutil_path: str | None = None
        self._helper: "PrivilegedHelper | None" = None
        self._check_ddcutil()

    @property
    def is_privileged(self) -> bool:
        """Check if running with elevated privileges."""
        return self._helper is not None and self._helper.is_authenticated

    def has_pkexec(self) -> bool:
        """Check if pkexec is available."""
        from .privileged_helper import PrivilegedHelper
        helper = PrivilegedHelper()
        return helper.has_pkexec()

    async def authenticate(self) -> bool:
        """Authenticate for privileged access. Only prompts once per session."""
        from .privileged_helper import PrivilegedHelper

        if self._helper and self._helper.is_authenticated:
            return True

        self._helper = PrivilegedHelper()
        return await self._helper.start()

    async def stop_privileged(self) -> None:
        """Stop the privileged helper if running."""
        if self._helper:
            await self._helper.stop()
            self._helper = None

    def _check_ddcutil(self) -> None:
        """Check if ddcutil is available."""
        self._ddcutil_path = shutil.which("ddcutil")
        if not self._ddcutil_path:
            raise DDCUtilError(
                "ddcutil not found. Please install ddcutil:\n"
                "  Fedora: sudo dnf install ddcutil\n"
                "  Ubuntu: sudo apt install ddcutil\n"
                "  Arch: sudo pacman -S ddcutil"
            )

    async def _run_async(
        self, args: list[str], timeout: float = 10.0
    ) -> tuple[str, str, int]:
        """Run ddcutil command asynchronously."""
        # Use privileged helper if authenticated
        if self._helper and self._helper.is_authenticated:
            return await self._helper.run_ddcutil(args, timeout)

        # Otherwise run directly
        cmd = [self._ddcutil_path] + args
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            stdout_str = stdout.decode() if stdout else ""
            stderr_str = stderr.decode() if stderr else ""

            # Check for permission errors
            if proc.returncode != 0:
                if "permission" in stderr_str.lower() or "access" in stderr_str.lower():
                    raise PermissionError(
                        "Permission denied accessing I2C devices.\n"
                        "Click 'Authenticate' to run with elevated privileges,\n"
                        "or add your user to the i2c group:\n"
                        "  sudo usermod -aG i2c $USER"
                    )

            return stdout_str, stderr_str, proc.returncode
        except asyncio.TimeoutError:
            raise DDCUtilError(f"ddcutil command timed out: {' '.join(args)}")

    async def detect_monitors(self) -> list[MonitorInfo]:
        """Detect connected monitors asynchronously."""
        stdout, stderr, returncode = await self._run_async(
            ["detect", "--terse"], timeout=30.0
        )
        return self._parse_detect_output(stdout)

    def _parse_detect_output(self, output: str) -> list[MonitorInfo]:
        """Parse ddcutil detect --terse output."""
        monitors = []
        current_monitor: dict | None = None

        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue

            # New display entry
            if line.startswith("Display"):
                if current_monitor:
                    monitors.append(self._create_monitor_info(current_monitor))
                # Parse "Display 1"
                match = re.match(r"Display\s+(\d+)", line)
                if match:
                    current_monitor = {"display_number": int(match.group(1))}

            elif current_monitor:
                # Parse key-value pairs
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip()

                    if "i2c bus" in key or key == "i2c bus":
                        # Extract bus number from "/dev/i2c-X"
                        match = re.search(r"/dev/i2c-(\d+)", value)
                        if match:
                            current_monitor["i2c_bus"] = int(match.group(1))
                    elif key == "manufacturer" or "mfg" in key:
                        current_monitor["manufacturer"] = value
                    elif key == "model":
                        current_monitor["model"] = value
                    elif key == "serial" or "sn" in key:
                        current_monitor["serial"] = value
                    elif key == "edid":
                        current_monitor["edid"] = value

        # Don't forget the last monitor
        if current_monitor:
            monitors.append(self._create_monitor_info(current_monitor))

        return monitors

    def _create_monitor_info(self, data: dict) -> MonitorInfo:
        """Create MonitorInfo from parsed data."""
        return MonitorInfo(
            display_number=data.get("display_number", 0),
            i2c_bus=data.get("i2c_bus", -1),
            manufacturer=data.get("manufacturer", "Unknown"),
            model=data.get("model", "Unknown"),
            serial=data.get("serial", ""),
            edid=data.get("edid", ""),
        )

    async def get_vcp(self, display: int, feature_code: int) -> VCPValue | None:
        """Get VCP feature value asynchronously."""
        stdout, stderr, returncode = await self._run_async(
            ["getvcp", hex(feature_code), "--display", str(display), "--terse"]
        )
        values = self._parse_getvcp_output_multiple(stdout)
        return values.get(feature_code)

    async def get_vcp_multiple(
        self, display: int, feature_codes: list[int]
    ) -> dict[int, VCPValue]:
        """Get multiple VCP feature values in a single call."""
        if not feature_codes:
            return {}

        # Build command with all feature codes
        args = ["getvcp"] + [hex(code) for code in feature_codes]
        args += ["--display", str(display), "--terse"]

        stdout, stderr, returncode = await self._run_async(args, timeout=30.0)
        return self._parse_getvcp_output_multiple(stdout)

    def _parse_getvcp_output_multiple(self, output: str) -> dict[int, VCPValue]:
        """Parse ddcutil getvcp --terse output for multiple features."""
        # Format: VCP 10 C 70 100 (code, type, current, max)
        # Or: VCP 60 SNC x11 (code, type, value for non-continuous)
        results = {}

        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("VCP"):
                continue

            parts = line.split()
            if len(parts) < 4:
                continue

            try:
                code = int(parts[1], 16)
                vcp_type = parts[2]

                if vcp_type == "C":  # Continuous
                    current = int(parts[3])
                    maximum = int(parts[4]) if len(parts) > 4 else 100
                    results[code] = VCPValue(
                        code=code,
                        current=current,
                        maximum=maximum,
                        name=self.FEATURE_NAMES.get(code, f"Feature {hex(code)}"),
                    )
                elif vcp_type in ("SNC", "NC"):  # Simple/Non-Continuous
                    # Value might be hex (x11) or decimal
                    value_str = parts[3]
                    if value_str.startswith("x"):
                        current = int(value_str[1:], 16)
                    else:
                        current = int(value_str)
                    results[code] = VCPValue(
                        code=code,
                        current=current,
                        maximum=255,  # Non-continuous typically 0-255 range
                        name=self.FEATURE_NAMES.get(code, f"Feature {hex(code)}"),
                    )
            except (ValueError, IndexError):
                # Skip malformed lines
                continue

        return results

    async def set_vcp(self, display: int, feature_code: int, value: int) -> bool:
        """Set VCP feature value asynchronously."""
        stdout, stderr, returncode = await self._run_async(
            ["setvcp", hex(feature_code), str(value), "--display", str(display)]
        )
        return returncode == 0

    # Default names for known VCP values (used when capabilities don't provide names)
    DEFAULT_VALUE_NAMES = {
        0x8D: {  # Audio Mute
            0x01: "Mute",
            0x02: "Unmute",
        },
        0x60: {  # Input Source
            0x01: "VGA-1",
            0x02: "VGA-2",
            0x03: "DVI-1",
            0x04: "DVI-2",
            0x0F: "DisplayPort-1",
            0x10: "DisplayPort-2",
            0x11: "HDMI-1",
            0x12: "HDMI-2",
            0x13: "HDMI-3",
            0x14: "HDMI-4",
        },
        0x14: {  # Color Preset
            0x01: "sRGB",
            0x02: "Native",
            0x03: "4000K",
            0x04: "5000K",
            0x05: "6500K",
            0x06: "7500K",
            0x07: "8200K",
            0x08: "9300K",
            0x09: "10000K",
            0x0A: "11500K",
            0x0B: "User 1",
            0x0C: "User 2",
            0x0D: "User 3",
        },
        0xDC: {  # Display Mode
            0x00: "Standard",
            0x01: "Productivity",
            0x02: "Mixed",
            0x03: "Movie",
            0x04: "User",
            0x05: "Games",
            0x06: "Sports",
            0x07: "Professional",
            0x08: "Standard 2",
            0xF0: "Dynamic Contrast",
        },
    }

    async def get_capabilities(
        self, display: int
    ) -> tuple[set[int], dict[int, list[tuple[int, str]]]]:
        """Get supported VCP features and their allowed values for a display.

        Returns:
            - Set of supported feature codes
            - Dict mapping feature code to list of (value, name) tuples for non-continuous features
        """
        stdout, stderr, returncode = await self._run_async(
            ["capabilities", "--display", str(display)], timeout=30.0
        )

        supported = set()
        feature_values: dict[int, list[tuple[int, str]]] = {}
        current_feature: int | None = None

        for line in stdout.splitlines():
            # Check for feature line: "Feature: 60 (Input Source)"
            feature_match = re.match(
                r"\s*Feature:\s*([0-9A-Fa-f]{2})\s*\(([^)]+)\)", line
            )
            if feature_match:
                current_feature = int(feature_match.group(1), 16)
                supported.add(current_feature)
                continue

            # Check for "Values:" line - may have inline values
            if "Values:" in line and current_feature is not None:
                # Try to extract inline values: "Values: 01 02 (interpretation unavailable)"
                # or "Values: 01 02"
                values_part = line.split("Values:", 1)[1]
                # Remove any trailing description in parentheses
                values_part = re.sub(r'\([^)]*\)\s*$', '', values_part).strip()
                # Extract hex values
                inline_values = re.findall(r'\b([0-9A-Fa-f]{2})\b', values_part)
                for val_str in inline_values:
                    value = int(val_str, 16)
                    # Use default name if available
                    name = self._get_default_value_name(current_feature, value)
                    if current_feature not in feature_values:
                        feature_values[current_feature] = []
                    feature_values[current_feature].append((value, name))
                continue

            # Check for value line: "11: HDMI-1" or "01: sRGB"
            if current_feature is not None:
                value_match = re.match(r"\s*([0-9A-Fa-f]{2}):\s*(.+)", line)
                if value_match:
                    value = int(value_match.group(1), 16)
                    name = value_match.group(2).strip()
                    if current_feature not in feature_values:
                        feature_values[current_feature] = []
                    feature_values[current_feature].append((value, name))

        return supported, feature_values

    def _get_default_value_name(self, feature_code: int, value: int) -> str:
        """Get default name for a VCP value if known."""
        feature_defaults = self.DEFAULT_VALUE_NAMES.get(feature_code, {})
        return feature_defaults.get(value, f"Value {value:#04x}")

    def get_input_source_name(self, value: int) -> str:
        """Get human-readable name for input source value."""
        return self.INPUT_SOURCES.get(value, f"Input {value}")

    @classmethod
    def get_feature_name(cls, code: int) -> str:
        """Get human-readable name for VCP feature code."""
        return cls.FEATURE_NAMES.get(code, f"Feature {hex(code)}")

    @classmethod
    def is_continuous(cls, code: int) -> bool:
        """Check if feature uses continuous values (slider)."""
        return code in cls.CONTINUOUS_FEATURES

    @classmethod
    def is_non_continuous(cls, code: int) -> bool:
        """Check if feature uses discrete values (dropdown)."""
        return code in cls.NON_CONTINUOUS_FEATURES
