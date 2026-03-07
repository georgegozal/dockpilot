import docker
from docker.errors import DockerException, NotFound, APIError


class DockerClient:
    """Thin wrapper around the docker SDK."""

    def __init__(self):
        self._client = None
        self._connected = False
        self.connect()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        for base_url in self._socket_candidates():
            try:
                client = docker.DockerClient(base_url=base_url) if base_url else docker.from_env()
                client.ping()
                self._client = client
                self._connected = True
                return True
            except Exception:
                continue
        self._connected = False
        self._client = None
        return False

    @staticmethod
    def _socket_candidates() -> list[str | None]:
        import os
        candidates: list[str | None] = [None]  # None = docker.from_env()
        home = os.path.expanduser("~")
        colima_sock = os.path.join(home, ".colima", "default", "docker.sock")
        if os.path.exists(colima_sock):
            candidates.insert(0, f"unix://{colima_sock}")
        return candidates

    @property
    def is_connected(self) -> bool:
        return self._connected

    def ping(self) -> bool:
        if not self._client:
            return self.connect()
        try:
            self._client.ping()
            self._connected = True
            return True
        except Exception:
            self._connected = False
            self._client = None
            return self.connect()

    def version(self) -> dict | None:
        if not self._client:
            return None
        try:
            return self._client.version()
        except Exception:
            return None

    def info(self) -> dict | None:
        if not self._client:
            return None
        try:
            return self._client.info()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Containers
    # ------------------------------------------------------------------

    def containers(self, all: bool = True):
        if not self._client:
            return []
        try:
            return self._client.containers.list(all=all)
        except Exception:
            return []

    def get_container(self, container_id: str):
        try:
            return self._client.containers.get(container_id)
        except Exception:
            return None

    def start_container(self, container_id: str):
        self._client.containers.get(container_id).start()

    def stop_container(self, container_id: str, timeout: int = 10):
        self._client.containers.get(container_id).stop(timeout=timeout)

    def restart_container(self, container_id: str, timeout: int = 10):
        self._client.containers.get(container_id).restart(timeout=timeout)

    def remove_container(self, container_id: str, force: bool = False):
        self._client.containers.get(container_id).remove(force=force)

    def pause_container(self, container_id: str):
        self._client.containers.get(container_id).pause()

    def unpause_container(self, container_id: str):
        self._client.containers.get(container_id).unpause()

    def container_logs(self, container_id: str, tail: int = 500,
                       stream: bool = False, follow: bool = False,
                       timestamps: bool = True):
        c = self._client.containers.get(container_id)
        return c.logs(tail=tail, stream=stream, follow=follow,
                      timestamps=timestamps)

    def container_stats(self, container_id: str, stream: bool = False) -> dict:
        c = self._client.containers.get(container_id)
        return c.stats(stream=stream)

    def inspect_container(self, container_id: str) -> dict:
        return self._client.api.inspect_container(container_id)

    def update_container(self, container_id: str, mem_limit: str):
        """Set memory limit (e.g. '512m', '1g'). memswap_limit matches mem_limit."""
        self._client.api.update_container(container_id,
                                          mem_limit=mem_limit,
                                          memswap_limit=mem_limit)

    # ------------------------------------------------------------------
    # Images
    # ------------------------------------------------------------------

    def images(self, all: bool = False):
        if not self._client:
            return []
        try:
            return self._client.images.list(all=all)
        except Exception:
            return []

    def pull_image(self, name: str, tag: str = "latest"):
        return self._client.images.pull(name, tag=tag)

    def remove_image(self, image_id: str, force: bool = False):
        self._client.images.remove(image_id, force=force)

    def inspect_image(self, image_id: str) -> dict:
        return self._client.api.inspect_image(image_id)

    def prune_images(self) -> dict:
        return self._client.images.prune()

    # ------------------------------------------------------------------
    # Volumes
    # ------------------------------------------------------------------

    def volumes(self):
        if not self._client:
            return []
        try:
            return self._client.volumes.list()
        except Exception:
            return []

    def create_volume(self, name: str, driver: str = "local"):
        return self._client.volumes.create(name, driver=driver)

    def remove_volume(self, name: str, force: bool = False):
        self._client.volumes.get(name).remove(force=force)

    def inspect_volume(self, name: str) -> dict:
        return self._client.api.inspect_volume(name)

    def prune_volumes(self) -> dict:
        return self._client.volumes.prune()

    # ------------------------------------------------------------------
    # Networks
    # ------------------------------------------------------------------

    def networks(self):
        if not self._client:
            return []
        try:
            return self._client.networks.list()
        except Exception:
            return []

    def create_network(self, name: str, driver: str = "bridge"):
        return self._client.networks.create(name, driver=driver)

    def remove_network(self, network_id: str):
        self._client.networks.get(network_id).remove()

    def inspect_network(self, network_id: str) -> dict:
        return self._client.api.inspect_network(network_id)

    def prune_networks(self) -> dict:
        return self._client.networks.prune()

    # ------------------------------------------------------------------
    # System
    # ------------------------------------------------------------------

    def system_prune(self) -> dict:
        """Remove all stopped containers, dangling images, unused networks."""
        result = {}
        try:
            result["containers"] = self._client.containers.prune()
        except Exception:
            pass
        try:
            result["images"] = self._client.images.prune()
        except Exception:
            pass
        try:
            result["networks"] = self._client.networks.prune()
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------
    # Raw API (for exec)
    # ------------------------------------------------------------------

    @property
    def raw(self):
        return self._client
