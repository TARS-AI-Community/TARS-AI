"""
Module: WiFi Manager
Author: Latisha Besariani Hendra
Description: WiFi connection management for TARS-AI using NetworkManager (nmcli).
             Supports scanning, connecting (personal + enterprise), hotspot mode,
             and status reporting.
"""

import subprocess
import re
import threading
import time
from typing import Dict, List, Optional, Tuple


class WiFiManager:
    """Manages WiFi connection and hotspot using NetworkManager."""

    HOTSPOT_SSID = "TARS-Setup"
    HOTSPOT_PASSWORD = "tars1234"
    HOTSPOT_IP = "10.42.0.1"
    CONNECTION_NAME = "TARS-Setup"

    def __init__(self):
        """Initialize WiFi manager and ensure hotspot connection profile exists."""
        self._ensure_hotspot_connection()
        self._auto_manage_running = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_command(
        self,
        args: List[str],
        timeout: int = 30,
        use_sudo: bool = False
    ) -> Tuple[int, str, str]:
        """Run a shell command and return (returncode, stdout, stderr)."""
        if use_sudo:
            args = ["sudo"] + args
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        except subprocess.TimeoutExpired:
            print(f"[WiFi] Command timed out: {' '.join(args)}")
            return -1, "", "Command timed out"
        except Exception as e:
            print(f"[WiFi] Command error: {e}")
            return -1, "", str(e)

    def _ensure_hotspot_connection(self) -> bool:
        """Create the TARS-Setup hotspot profile in NetworkManager if absent."""
        code, out, _ = self._run_command(
            ["nmcli", "-t", "-f", "NAME", "connection", "show"],
            timeout=5
        )
        if code == 0 and self.CONNECTION_NAME in out.split("\n"):
            return True

        print(f"[WiFi] Creating hotspot connection '{self.CONNECTION_NAME}'")

        code, _, err = self._run_command([
            "nmcli", "connection", "add",
            "type", "wifi",
            "ifname", "wlan0",
            "con-name", self.CONNECTION_NAME,
            "autoconnect", "no",
            "ssid", self.HOTSPOT_SSID,
        ], timeout=10, use_sudo=True)
        if code != 0:
            print(f"[WiFi] Failed to create hotspot: {err}")
            return False

        code, _, err = self._run_command([
            "nmcli", "connection", "modify", self.CONNECTION_NAME,
            "802-11-wireless.mode", "ap",
            "802-11-wireless.band", "bg",
            "ipv4.method", "shared",
        ], timeout=10, use_sudo=True)
        if code != 0:
            print(f"[WiFi] Failed to configure AP mode: {err}")
            return False

        code, _, err = self._run_command([
            "nmcli", "connection", "modify", self.CONNECTION_NAME,
            "wifi-sec.key-mgmt", "wpa-psk",
            "wifi-sec.psk", self.HOTSPOT_PASSWORD,
        ], timeout=10, use_sudo=True)
        if code != 0:
            print(f"[WiFi] Failed to set hotspot password: {err}")
            return False

        print("[WiFi] Hotspot connection profile created.")
        return True

    def _get_ip_address(self) -> Optional[str]:
        """Return the current IPv4 address of wlan0, or None."""
        code, out, _ = self._run_command(
            ["ip", "-4", "addr", "show", "wlan0"], timeout=5
        )
        if code != 0:
            return None
        match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out)
        return match.group(1) if match else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_known_ssids(self) -> List[str]:
        """Return SSIDs of all saved WiFi client connections (excluding hotspot)."""
        code, out, _ = self._run_command(
            ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"],
            timeout=5
        )
        ssids = []
        if code == 0:
            for line in out.split("\n"):
                parts = line.split(":")
                if len(parts) >= 2 and parts[1].strip() == "802-11-wireless":
                    name = parts[0].strip()
                    if name != self.CONNECTION_NAME:
                        ssids.append(name)
        return ssids

    def auto_connect(self) -> str:
        """
        Connect to a known network if one is in range; otherwise start hotspot.
        Returns: 'connected', 'hotspot', or 'no_change'.
        """
        status = self.get_status()

        if status["mode"] == "client":
            return "no_change"  # already on a real network

        known = self.get_known_ssids()
        if not known:
            if status["mode"] != "hotspot":
                self.start_hotspot()
                return "hotspot"
            return "no_change"

        # Quick scan (use cached results to avoid waiting 30s every check)
        available = {n["ssid"] for n in self.scan_networks(rescan=False)}
        reachable = [s for s in known if s in available]

        if reachable:
            print(f"[WiFi] Known network in range: {reachable[0]} — connecting")
            if status["mode"] == "hotspot":
                self.stop_hotspot()
            code, _, err = self._run_command(
                ["nmcli", "--wait", "30", "connection", "up", reachable[0]],
                timeout=35, use_sudo=True
            )
            if code == 0:
                print(f"[WiFi] Auto-connected to {reachable[0]}")
                return "connected"
            print(f"[WiFi] Auto-connect failed: {err}")

        # No known networks reachable — ensure hotspot is running
        if status["mode"] != "hotspot":
            print("[WiFi] No known networks in range — starting hotspot")
            self.start_hotspot()
            return "hotspot"

        return "no_change"

    def start_auto_manage(self, check_interval: int = 60):
        """
        Start background thread: while in hotspot mode, periodically scan
        for known networks and switch to client mode if one appears.
        """
        if self._auto_manage_running:
            return

        def _loop():
            # Initial connect attempt on startup
            try:
                result = self.auto_connect()
                print(f"[WiFi] Startup auto-connect: {result}")
            except Exception as e:
                print(f"[WiFi] Startup auto-connect error: {e}")

            while self._auto_manage_running:
                time.sleep(check_interval)
                try:
                    status = self.get_status()
                    # Only scan when in hotspot mode (no need to check if already connected)
                    if status["mode"] == "hotspot":
                        result = self.auto_connect()
                        if result != "no_change":
                            print(f"[WiFi] Auto-manage: {result}")
                except Exception as e:
                    print(f"[WiFi] Auto-manage error: {e}")

        self._auto_manage_running = True
        t = threading.Thread(target=_loop, daemon=True, name="wifi-auto-manage")
        t.start()
        print("[WiFi] Auto-manage started (interval={}s)".format(check_interval))

    def stop_auto_manage(self):
        """Stop the background auto-manage thread."""
        self._auto_manage_running = False

    def scan_networks(self, rescan: bool = True) -> List[Dict]:
        """
        Scan for available WiFi networks.

        Returns a list of dicts: {ssid, signal, security, in_use}.
        Networks are sorted by signal strength (strongest first).
        """
        if rescan:
            self._run_command(
                ["nmcli", "device", "wifi", "list", "--rescan", "yes"],
                timeout=30
            )

        code, out, err = self._run_command(
            ["nmcli", "-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY,RSN-FLAGS", "device", "wifi", "list"],
            timeout=10
        )
        if code != 0:
            print(f"[WiFi] Scan failed: {err}")
            return []

        networks = []
        seen = set()

        for line in out.split("\n"):
            if not line.strip():
                continue
            parts = line.split(":")
            if len(parts) < 4:
                continue

            in_use_raw = parts[0].strip()
            ssid      = parts[1].strip()
            signal_str = parts[2].strip()
            sec_raw   = parts[3].strip()
            rsn_flags = parts[4].strip() if len(parts) > 4 else ""

            if not ssid or ssid == "--":
                continue
            if ssid in seen:
                continue
            seen.add(ssid)

            try:
                signal = int(signal_str)
            except ValueError:
                signal = 0

            # Detect enterprise via RSN flags (8021x = 802.1X / EAP)
            is_enterprise = "8021x" in rsn_flags.lower() or "802.1x" in sec_raw.lower()

            if not sec_raw or sec_raw == "--":
                security = "open"
            elif is_enterprise:
                security = "WPA2-Enterprise"
            elif "WPA2" in sec_raw or "WPA3" in sec_raw:
                security = "WPA2"
            elif "WPA" in sec_raw:
                security = "WPA"
            else:
                security = "open"

            networks.append({
                "ssid": ssid,
                "signal": signal,
                "security": security,
                "in_use": in_use_raw == "*",
            })

        networks.sort(key=lambda x: x["signal"], reverse=True)
        return networks

    def connect(self, ssid: str, password: str) -> bool:
        """
        Connect to a personal WPA WiFi network.

        Returns True on success.
        """
        print(f"[WiFi] Connecting to: {ssid}")
        cmd = ["nmcli", "--wait", "30", "device", "wifi", "connect", ssid]
        if password:
            cmd.extend(["password", password])

        code, out, err = self._run_command(cmd, timeout=35, use_sudo=True)
        if code == 0:
            print(f"[WiFi] Connected to {ssid}")
            return True

        msg = err or out
        print(f"[WiFi] Connection failed: {msg}")
        return False

    def connect_enterprise(
        self,
        ssid: str,
        username: str,
        password: str,
        eap_method: str = "peap",
        phase2_auth: str = "mschapv2"
    ) -> bool:
        """
        Connect to a WPA Enterprise (802.1X PEAP/MSCHAPv2) network.

        Returns True on success.
        """
        print(f"[WiFi] Connecting to enterprise network: {ssid} (user={username})")

        code, out, _ = self._run_command(
            ["nmcli", "-t", "-f", "NAME", "connection", "show"], timeout=5
        )
        connection_exists = code == 0 and ssid in out.split("\n")

        if connection_exists:
            code, _, err = self._run_command([
                "nmcli", "connection", "modify", ssid,
                "802-11-wireless-security.key-mgmt", "wpa-eap",
                "802-1x.eap", eap_method,
                "802-1x.phase2-auth", phase2_auth,
                "802-1x.identity", username,
                "802-1x.password", password,
            ], timeout=10, use_sudo=True)
        else:
            code, _, err = self._run_command([
                "nmcli", "connection", "add",
                "type", "wifi",
                "ifname", "wlan0",
                "con-name", ssid,
                "ssid", ssid,
                "802-11-wireless-security.key-mgmt", "wpa-eap",
                "802-1x.eap", eap_method,
                "802-1x.phase2-auth", phase2_auth,
                "802-1x.identity", username,
                "802-1x.password", password,
            ], timeout=10, use_sudo=True)

        if code != 0:
            print(f"[WiFi] Enterprise profile setup failed: {err}")
            return False

        code, _, err = self._run_command(
            ["nmcli", "--wait", "30", "connection", "up", ssid],
            timeout=35, use_sudo=True
        )
        if code == 0:
            print(f"[WiFi] Connected to enterprise {ssid}")
            return True

        print(f"[WiFi] Enterprise connection failed: {err or _}")
        return False

    def start_hotspot(self) -> bool:
        """Start the TARS-Setup access point. Returns True on success."""
        print(f"[WiFi] Starting hotspot: {self.HOTSPOT_SSID}")
        if not self._ensure_hotspot_connection():
            return False

        code, _, err = self._run_command(
            ["nmcli", "connection", "up", self.CONNECTION_NAME],
            timeout=15, use_sudo=True
        )
        if code == 0:
            print("[WiFi] Hotspot started.")
            return True

        print(f"[WiFi] Failed to start hotspot: {err}")
        return False

    def stop_hotspot(self) -> bool:
        """Stop the TARS-Setup access point. Returns True on success."""
        print("[WiFi] Stopping hotspot.")
        code, _, err = self._run_command(
            ["nmcli", "connection", "down", self.CONNECTION_NAME],
            timeout=10, use_sudo=True
        )
        if code == 0:
            return True
        if "not active" in (err or "").lower():
            return True  # Already down — not an error
        print(f"[WiFi] Failed to stop hotspot: {err}")
        return False

    def get_status(self) -> Dict:
        """
        Return current WiFi status as a dict:
          {mode: 'hotspot'|'client'|'disconnected', ssid, ip, signal}
        """
        code, out, err = self._run_command(
            ["nmcli", "-t", "-f", "TYPE,STATE,CONNECTION", "device"],
            timeout=5
        )
        if code != 0:
            return {"mode": "disconnected", "ssid": None, "ip": None, "signal": 0}

        for line in out.split("\n"):
            parts = line.split(":")
            if len(parts) < 3:
                continue
            dev_type, state, connection = parts[0].strip(), parts[1].strip(), parts[2].strip()
            if dev_type != "wifi" or state != "connected":
                continue

            if connection == self.CONNECTION_NAME:
                return {
                    "mode": "hotspot",
                    "ssid": self.HOTSPOT_SSID,
                    "ip": self.HOTSPOT_IP,
                    "signal": 100,
                }

            # Client mode — get signal from nmcli
            signal = self._get_client_signal()
            return {
                "mode": "client",
                "ssid": connection,
                "ip": self._get_ip_address(),
                "signal": signal,
            }

        return {"mode": "disconnected", "ssid": None, "ip": None, "signal": 0}

    def _get_client_signal(self) -> int:
        """Return the signal strength (0-100) of the active WiFi connection."""
        code, out, _ = self._run_command(
            ["nmcli", "-t", "-f", "IN-USE,SIGNAL", "device", "wifi"],
            timeout=5
        )
        if code != 0:
            return 0
        for line in out.split("\n"):
            parts = line.split(":")
            if len(parts) >= 2 and parts[0].strip() == "*":
                try:
                    return int(parts[1].strip())
                except ValueError:
                    pass
        return 0

    def is_connected(self) -> bool:
        """Return True if connected to a client network (not hotspot)."""
        return self.get_status()["mode"] == "client"


# ---------------------------------------------------------------------------
# Module-level helper used by webui routes and the Eyes app
# ---------------------------------------------------------------------------

_wifi_manager: Optional[WiFiManager] = None


def _get_manager() -> WiFiManager:
    global _wifi_manager
    if _wifi_manager is None:
        _wifi_manager = WiFiManager()
    return _wifi_manager


def get_wifi_status() -> Dict:
    """
    Convenience function: return the current WiFi status dict.
    Safe to call without instantiating WiFiManager directly.
    """
    try:
        return _get_manager().get_status()
    except Exception as e:
        print(f"[WiFi] get_wifi_status error: {e}")
        return {"mode": "disconnected", "ssid": None, "ip": None, "signal": 0}
