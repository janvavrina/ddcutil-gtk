"""Monitor data model for DDCUtil GTK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .ddcutil import MonitorInfo, VCPValue


@dataclass
class Monitor:
    """Represents a monitor with its VCP feature values."""

    display_number: int
    i2c_bus: int
    manufacturer: str
    model: str
    serial: str

    # Cached VCP values: feature_code -> VCPValue
    vcp_values: dict[int, "VCPValue"] = field(default_factory=dict)

    # Set of supported VCP feature codes
    supported_features: set[int] = field(default_factory=set)

    # Allowed values for non-continuous features: feature_code -> [(value, name), ...]
    feature_options: dict[int, list[tuple[int, str]]] = field(default_factory=dict)

    # Loading state
    is_loading: bool = False

    @classmethod
    def from_info(cls, info: "MonitorInfo") -> "Monitor":
        """Create Monitor from MonitorInfo."""
        return cls(
            display_number=info.display_number,
            i2c_bus=info.i2c_bus,
            manufacturer=info.manufacturer,
            model=info.model,
            serial=info.serial,
        )

    @property
    def display_name(self) -> str:
        """Get a user-friendly display name."""
        if self.model and self.model != "Unknown":
            return f"{self.manufacturer} {self.model}"
        return f"Display {self.display_number}"

    @property
    def short_name(self) -> str:
        """Get a short name for tabs/labels."""
        if self.model and self.model != "Unknown":
            # Truncate if too long
            name = self.model
            if len(name) > 20:
                name = name[:17] + "..."
            return name
        return f"Display {self.display_number}"

    def get_vcp_value(self, feature_code: int) -> "VCPValue | None":
        """Get cached VCP value for a feature."""
        return self.vcp_values.get(feature_code)

    def set_vcp_value(self, value: "VCPValue") -> None:
        """Update cached VCP value."""
        self.vcp_values[value.code] = value

    def supports_feature(self, feature_code: int) -> bool:
        """Check if monitor supports a VCP feature."""
        # If we haven't loaded capabilities, assume supported
        if not self.supported_features:
            return True
        return feature_code in self.supported_features

    def get_feature_options(self, feature_code: int) -> list[tuple[int, str]]:
        """Get allowed values for a non-continuous feature."""
        return self.feature_options.get(feature_code, [])

    def get_brightness(self) -> int | None:
        """Get current brightness value (0-100)."""
        from .ddcutil import DDCUtil

        value = self.vcp_values.get(DDCUtil.VCP_BRIGHTNESS)
        return value.current if value else None

    def get_contrast(self) -> int | None:
        """Get current contrast value (0-100)."""
        from .ddcutil import DDCUtil

        value = self.vcp_values.get(DDCUtil.VCP_CONTRAST)
        return value.current if value else None
