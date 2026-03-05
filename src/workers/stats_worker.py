from PyQt6.QtCore import QThread, pyqtSignal


class StatsWorker(QThread):
    """Polls container stats periodically and emits parsed values."""

    stats_updated = pyqtSignal(str, dict)   # container_id, stats dict
    error = pyqtSignal(str, str)            # container_id, error message

    def __init__(self, docker_client, container_id: str):
        super().__init__()
        self._docker = docker_client
        self._container_id = container_id
        self._running = True

    def run(self):
        try:
            c = self._docker.raw.containers.get(self._container_id)
            for raw in c.stats(stream=True, decode=True):
                if not self._running:
                    break
                parsed = self._parse(raw)
                self.stats_updated.emit(self._container_id, parsed)
        except Exception as e:
            if self._running:
                self.error.emit(self._container_id, str(e))

    def stop(self):
        self._running = False

    @staticmethod
    def _parse(raw: dict) -> dict:
        result = {"cpu_pct": 0.0, "mem_usage": 0, "mem_limit": 0,
                  "mem_pct": 0.0, "net_rx": 0, "net_tx": 0,
                  "block_read": 0, "block_write": 0}
        try:
            # CPU %
            cpu = raw.get("cpu_stats", {})
            pre = raw.get("precpu_stats", {})
            delta = cpu["cpu_usage"]["total_usage"] - pre["cpu_usage"]["total_usage"]
            sys_delta = cpu.get("system_cpu_usage", 0) - pre.get("system_cpu_usage", 0)
            ncpu = cpu.get("online_cpus") or len(cpu["cpu_usage"].get("percpu_usage", [1]))
            if sys_delta > 0:
                result["cpu_pct"] = (delta / sys_delta) * ncpu * 100.0
        except Exception:
            pass
        try:
            mem = raw.get("memory_stats", {})
            usage = mem.get("usage", 0) - mem.get("stats", {}).get("cache", 0)
            limit = mem.get("limit", 1)
            result["mem_usage"] = usage
            result["mem_limit"] = limit
            result["mem_pct"] = (usage / limit * 100.0) if limit else 0.0
        except Exception:
            pass
        try:
            nets = raw.get("networks", {})
            for iface in nets.values():
                result["net_rx"] += iface.get("rx_bytes", 0)
                result["net_tx"] += iface.get("tx_bytes", 0)
        except Exception:
            pass
        try:
            for entry in raw.get("blkio_stats", {}).get("io_service_bytes_recursive", []):
                if entry.get("op") == "Read":
                    result["block_read"] += entry.get("value", 0)
                elif entry.get("op") == "Write":
                    result["block_write"] += entry.get("value", 0)
        except Exception:
            pass
        return result
