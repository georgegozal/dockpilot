"""CLI commands for DockPilot.

All handlers receive parsed argparse.Namespace objects and write to stdout.
Mirrors the actions available in the GUI panels, driven through the same
DockerClient wrapper.
"""
from __future__ import annotations

import sys

import docker.errors

from src.docker_client import DockerClient

RESTART_POLICIES = ("no", "always", "unless-stopped", "on-failure")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _client() -> DockerClient:
    client = DockerClient()
    if not client.is_connected:
        print("dockpilot: cannot reach the Docker daemon.", file=sys.stderr)
        if sys.platform == "darwin":
            print("  Start it with: dockpilot -d", file=sys.stderr)
        sys.exit(1)
    return client


def resolve_container(client: DockerClient, ref: str):
    """Find a container by exact ID/name (native Docker resolution), falling
    back to a substring match on name. Exits with a helpful message if
    nothing matches or the match is ambiguous.
    """
    c = client.get_container(ref)
    if c:
        return c

    ref_lower = ref.lower()
    candidates = [c for c in client.containers(all=True) if ref_lower in c.name.lower()]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        matches = ", ".join(f"{c.name} ({c.short_id})" for c in candidates)
        print(f"dockpilot: ambiguous reference {ref!r}: matches {matches}", file=sys.stderr)
        sys.exit(1)

    print(f"dockpilot: no such container: {ref}", file=sys.stderr)
    sys.exit(1)


def _image_name(c) -> str:
    try:
        img = c.image
        return img.tags[0] if img.tags else img.short_id
    except docker.errors.APIError:
        raw = c.attrs.get("Config", {}).get("Image") or c.attrs.get("Image", "")
        return raw or "<unknown>"


def _fmt_ports(ports: dict) -> str:
    if not ports:
        return ""
    parts = []
    for container_port, host_bindings in ports.items():
        if host_bindings:
            for b in host_bindings:
                host_ip = b.get("HostIp", "0.0.0.0")
                host_port = b.get("HostPort", "?")
                parts.append(f"{host_ip}:{host_port}->{container_port}")
        else:
            parts.append(container_port)
    return "  ".join(parts[:3]) + ("…" if len(parts) > 3 else "")


def _fmt_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}" if unit != "B" else f"{int(n)}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def _print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [
        max(len(str(headers[i])), *(len(str(r[i])) for r in rows)) if rows else len(str(headers[i]))
        for i in range(len(headers))
    ]

    def fmt_row(cells):
        return "  ".join(str(c).ljust(w) for c, w in zip(cells, widths))

    print(fmt_row(headers))
    for row in rows:
        print(fmt_row(row))


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------

def cmd_ps(args) -> None:
    client = _client()
    containers = client.containers(all=args.all)
    if not containers:
        if args.all:
            print("No containers.")
        else:
            print("No running containers.  Use -a/--all to include stopped ones.")
        return
    rows = [
        [c.short_id, c.name, c.status, _image_name(c), _fmt_ports(c.ports)]
        for c in containers
    ]
    _print_table(["CONTAINER ID", "NAME", "STATUS", "IMAGE", "PORTS"], rows)


def cmd_start(args) -> None:
    client = _client()
    c = resolve_container(client, args.ref)
    client.start_container(c.id)
    print(f"✓  Started '{c.name}'.")


def cmd_stop(args) -> None:
    client = _client()
    c = resolve_container(client, args.ref)
    client.stop_container(c.id, timeout=args.timeout)
    print(f"✓  Stopped '{c.name}'.")


def cmd_restart(args) -> None:
    client = _client()
    c = resolve_container(client, args.ref)
    client.restart_container(c.id, timeout=args.timeout)
    print(f"✓  Restarted '{c.name}'.")


def cmd_rm(args) -> None:
    client = _client()
    c = resolve_container(client, args.ref)
    name = c.name
    if not args.force and c.status == "running":
        print(f"dockpilot: container '{name}' is running. Use -f/--force to remove anyway.",
              file=sys.stderr)
        sys.exit(1)
    client.remove_container(c.id, force=args.force)
    print(f"✓  Removed '{name}'.")


def cmd_rename(args) -> None:
    client = _client()
    c = resolve_container(client, args.ref)
    old_name = c.name
    client.rename_container(c.id, args.new_name)
    print(f"✓  Renamed '{old_name}' → '{args.new_name}'.")


def cmd_restart_policy(args) -> None:
    client = _client()
    c = resolve_container(client, args.ref)
    max_retry = args.max_retry or 0
    client.set_restart_policy(c.id, args.policy, max_retry)
    suffix = f" (max retries: {max_retry})" if args.policy == "on-failure" else ""
    print(f"✓  Restart policy for '{c.name}' set to '{args.policy}'{suffix}.")


def cmd_mem(args) -> None:
    client = _client()
    c = resolve_container(client, args.ref)
    limit = args.limit.strip().lower()
    client.update_container(c.id, limit)
    if limit in ("0", ""):
        print(f"✓  Memory limit removed from '{c.name}'.")
    else:
        print(f"✓  Memory limit for '{c.name}' set to {limit}.")


def cmd_logs(args) -> None:
    client = _client()
    c = resolve_container(client, args.ref)
    timestamps = not args.no_timestamps
    if args.follow:
        try:
            for chunk in client.container_logs(c.id, tail=args.tail, stream=True,
                                               follow=True, timestamps=timestamps):
                sys.stdout.write(chunk.decode(errors="replace") if isinstance(chunk, bytes) else str(chunk))
        except KeyboardInterrupt:
            pass
    else:
        data = client.container_logs(c.id, tail=args.tail, stream=False,
                                     follow=False, timestamps=timestamps)
        sys.stdout.write(data.decode(errors="replace") if isinstance(data, bytes) else str(data))


def cmd_stats(args) -> None:
    from src.workers.stats_worker import StatsWorker

    client = _client()
    c = resolve_container(client, args.ref)
    if c.status != "running":
        print(f"dockpilot: container '{c.name}' is not running.", file=sys.stderr)
        sys.exit(1)
    raw = client.container_stats(c.id, stream=False)
    s = StatsWorker._parse(raw)
    print(f"Container:  {c.name}")
    print(f"CPU:        {s['cpu_pct']:.1f}%")
    print(f"Memory:     {_fmt_size(s['mem_usage'])} / {_fmt_size(s['mem_limit'])}  ({s['mem_pct']:.1f}%)")
    print(f"Net I/O:    {_fmt_size(s['net_rx'])} rx / {_fmt_size(s['net_tx'])} tx")
    print(f"Block I/O:  {_fmt_size(s['block_read'])} read / {_fmt_size(s['block_write'])} write")


def cmd_inspect(args) -> None:
    import json

    client = _client()
    kind = args.type
    try:
        if kind == "container":
            c = resolve_container(client, args.ref)
            data = client.inspect_container(c.id)
        elif kind == "image":
            data = client.inspect_image(args.ref)
        elif kind == "volume":
            data = client.inspect_volume(args.ref)
        else:
            data = client.inspect_network(args.ref)
    except docker.errors.NotFound:
        print(f"dockpilot: no such {kind}: {args.ref}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

def cmd_images(args) -> None:
    client = _client()
    images = client.images(all=args.all)
    if not images:
        print("No images.")
        return
    rows = []
    for img in images:
        size = _fmt_size(img.attrs.get("Size", 0))
        tags = img.tags or ["<none>:<none>"]
        for tag in tags:
            rows.append([tag, img.short_id.replace("sha256:", ""), size])
    _print_table(["REPOSITORY:TAG", "IMAGE ID", "SIZE"], rows)


def cmd_pull(args) -> None:
    client = _client()
    name, _, tag = args.image.partition(":")
    tag = tag or "latest"
    print(f"Pulling {name}:{tag} …")
    client.pull_image(name, tag=tag)
    print(f"✓  Pulled {name}:{tag}.")


def cmd_rmi(args) -> None:
    client = _client()
    try:
        client.remove_image(args.ref, force=args.force)
    except docker.errors.NotFound:
        print(f"dockpilot: no such image: {args.ref}", file=sys.stderr)
        sys.exit(1)
    print(f"✓  Removed image '{args.ref}'.")


# ---------------------------------------------------------------------------
# Volumes / Networks
# ---------------------------------------------------------------------------

def cmd_volumes(args) -> None:
    client = _client()
    volumes = client.volumes()
    if not volumes:
        print("No volumes.")
        return
    rows = [[v.name, v.attrs.get("Driver", ""), v.attrs.get("Mountpoint", "")] for v in volumes]
    _print_table(["NAME", "DRIVER", "MOUNTPOINT"], rows)


def cmd_networks(args) -> None:
    client = _client()
    networks = client.networks()
    if not networks:
        print("No networks.")
        return
    rows = [[n.short_id, n.name, n.attrs.get("Driver", ""), n.attrs.get("Scope", "")] for n in networks]
    _print_table(["NETWORK ID", "NAME", "DRIVER", "SCOPE"], rows)


# ---------------------------------------------------------------------------
# Prune / status
# ---------------------------------------------------------------------------

def cmd_prune(args) -> None:
    client = _client()
    targets = []
    if args.all or args.containers or not (args.images or args.volumes or args.networks):
        targets.append(("containers", client.prune_containers))
    if args.all or args.images:
        targets.append(("images", client.prune_images))
    if args.all or args.volumes:
        targets.append(("volumes", client.prune_volumes))
    if args.all or args.networks:
        targets.append(("networks", client.prune_networks))

    if not args.yes:
        names = ", ".join(name for name, _ in targets)
        ans = input(f"Prune unused {names}? [y/N] ").strip().lower()
        if ans != "y":
            print("Aborted.")
            return

    for name, fn in targets:
        result = fn()
        reclaimed = result.get("SpaceReclaimed", 0) if isinstance(result, dict) else 0
        deleted = result.get("ContainersDeleted") or result.get("ImagesDeleted") or \
            result.get("VolumesDeleted") or result.get("NetworksDeleted") or []
        print(f"✓  Pruned {len(deleted)} {name} ({_fmt_size(reclaimed)} reclaimed).")


def cmd_status(args) -> None:
    client = DockerClient()
    if client.is_connected:
        version = client.version() or {}
        engine = version.get("Components", [{}])[0].get("Version", "")
        print(f"Docker daemon:  connected{f' (Docker {engine})' if engine else ''}")
    else:
        print("Docker daemon:  not reachable")

    if sys.platform == "darwin":
        from src.workers.colima_worker import colima_installed, colima_running
        if not colima_installed():
            print("Colima:         not installed")
        elif colima_running():
            print("Colima:         running")
        else:
            print("Colima:         installed, not running  (start with: dockpilot -d)")
