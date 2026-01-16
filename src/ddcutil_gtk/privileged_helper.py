"""Persistent privileged helper for running ddcutil commands.

This helper runs via pkexec and stays alive for the session,
so the user only needs to authenticate once.
"""

from __future__ import annotations

import asyncio
import shutil
from typing import Callable


class PrivilegedHelper:
    """Manages a persistent privileged subprocess for ddcutil commands."""

    def __init__(self):
        self._process: asyncio.subprocess.Process | None = None
        self._ddcutil_path = shutil.which("ddcutil") or "/usr/bin/ddcutil"
        self._pkexec_path = shutil.which("pkexec")
        self._lock = asyncio.Lock()
        self._authenticated = False

    def has_pkexec(self) -> bool:
        """Check if pkexec is available."""
        return self._pkexec_path is not None

    @property
    def is_authenticated(self) -> bool:
        """Check if we have an active authenticated session."""
        return self._authenticated and self._process is not None

    async def start(self) -> bool:
        """Start the privileged helper process.

        This will trigger a pkexec authentication prompt.
        Returns True if successful, False if auth was cancelled.
        """
        if self._process is not None:
            return True

        if not self._pkexec_path:
            return False

        # Start a persistent bash shell via pkexec
        # We use a simple protocol: send command, read until marker
        try:
            self._process = await asyncio.create_subprocess_exec(
                self._pkexec_path,
                "/bin/bash",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Test if auth succeeded by running a simple command
            result = await self._run_command("echo authenticated")
            if result and "authenticated" in result[0]:
                self._authenticated = True
                return True
            else:
                await self.stop()
                return False

        except Exception as e:
            self._process = None
            self._authenticated = False
            return False

    async def stop(self) -> None:
        """Stop the privileged helper process."""
        if self._process:
            try:
                self._process.stdin.write(b"exit\n")
                await self._process.stdin.drain()
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except Exception:
                self._process.kill()
            finally:
                self._process = None
                self._authenticated = False

    async def run_ddcutil(
        self, args: list[str], timeout: float = 30.0
    ) -> tuple[str, str, int]:
        """Run a ddcutil command through the privileged helper.

        Returns (stdout, stderr, returncode).
        """
        if not self._process or not self._authenticated:
            raise RuntimeError("Helper not authenticated")

        cmd = f"{self._ddcutil_path} {' '.join(args)}"
        return await self._run_command(cmd, timeout)

    async def _run_command(
        self, command: str, timeout: float = 30.0
    ) -> tuple[str, str, int]:
        """Run a command and capture output using markers."""
        async with self._lock:
            if not self._process or not self._process.stdin or not self._process.stdout:
                raise RuntimeError("Helper process not running")

            # Use unique markers to delimit output
            marker = "___END_CMD___"
            full_cmd = f'{command}; echo "{marker}$?";\n'

            try:
                self._process.stdin.write(full_cmd.encode())
                await self._process.stdin.drain()

                # Read until we see the marker
                output_lines = []
                return_code = 0

                while True:
                    try:
                        line = await asyncio.wait_for(
                            self._process.stdout.readline(),
                            timeout=timeout
                        )
                        if not line:
                            # Process ended
                            self._authenticated = False
                            self._process = None
                            break

                        line_str = line.decode().rstrip('\n')

                        if line_str.startswith(marker):
                            # Extract return code
                            try:
                                return_code = int(line_str[len(marker):])
                            except ValueError:
                                return_code = -1
                            break
                        else:
                            output_lines.append(line_str)

                    except asyncio.TimeoutError:
                        return ("", "Command timed out", -1)

                stdout = "\n".join(output_lines)
                return (stdout, "", return_code)

            except Exception as e:
                return ("", str(e), -1)
