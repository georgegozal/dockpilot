"""DockPilot CLI subcommands.

Usage
-----
dockpilot ps [-a]                          list containers
dockpilot start <name|id>                  start a container
dockpilot stop <name|id> [-t SECS]         stop a container
dockpilot restart <name|id> [-t SECS]      restart a container
dockpilot rm <name|id> [-f]                remove a container
dockpilot rename <name|id> <new_name>      rename a container
dockpilot restart-policy <name|id> <policy> [--max-retry N]
                                            set a container's restart policy
dockpilot mem <name|id> <limit>            set a container's memory limit
dockpilot logs <name|id> [--tail N] [-f]   show container logs
dockpilot stats <name|id>                  one-shot CPU/memory/network stats
dockpilot inspect <ref> [--type TYPE]      raw JSON inspect (container/image/volume/network)
dockpilot images [-a]                      list images
dockpilot pull <image>[:tag]               pull an image
dockpilot rmi <id|tag> [-f]                remove an image
dockpilot volumes                          list volumes
dockpilot networks                         list networks
dockpilot prune [--images|--volumes|--networks|--all] [-y]
                                            remove unused containers/images/etc.
dockpilot status                           Docker daemon / Colima connectivity
"""
from __future__ import annotations

import argparse
import sys

from src.cli.commands import RESTART_POLICIES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dockpilot",
        description="DockPilot CLI — manage containers, images, volumes and networks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  dockpilot ps                          # running containers\n"
            "  dockpilot ps -a                       # all containers\n"
            "  dockpilot rename web-old web-new\n"
            "  dockpilot restart-policy web unless-stopped\n"
            "  dockpilot restart-policy web on-failure --max-retry 5\n"
            "  dockpilot mem web 512m                # 0 removes the limit\n"
            "  dockpilot logs web -f                 # follow logs\n"
            "  dockpilot stats web\n"
            "  dockpilot pull nginx:alpine\n"
            "  dockpilot prune                       # stopped containers only\n"
            "  dockpilot prune --all -y               # containers+images+volumes+networks\n"
            "  dockpilot status\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = False

    # ── ps ─────────────────────────────────────────────────────────────────
    p_ps = sub.add_parser("ps", help="list containers")
    p_ps.add_argument("-a", "--all", action="store_true", help="include stopped containers")

    # ── start / stop / restart ───────────────────────────────────────────────
    p_start = sub.add_parser("start", help="start a container")
    p_start.add_argument("ref", metavar="NAME_OR_ID")

    p_stop = sub.add_parser("stop", help="stop a container")
    p_stop.add_argument("ref", metavar="NAME_OR_ID")
    p_stop.add_argument("-t", "--timeout", type=int, default=10, metavar="SECS")

    p_restart = sub.add_parser("restart", help="restart a container")
    p_restart.add_argument("ref", metavar="NAME_OR_ID")
    p_restart.add_argument("-t", "--timeout", type=int, default=10, metavar="SECS")

    # ── rm ─────────────────────────────────────────────────────────────────
    p_rm = sub.add_parser("rm", help="remove a container")
    p_rm.add_argument("ref", metavar="NAME_OR_ID")
    p_rm.add_argument("-f", "--force", action="store_true", help="force-remove a running container")

    # ── rename ─────────────────────────────────────────────────────────────
    p_rename = sub.add_parser("rename", help="rename a container")
    p_rename.add_argument("ref", metavar="NAME_OR_ID")
    p_rename.add_argument("new_name", metavar="NEW_NAME")

    # ── restart-policy ───────────────────────────────────────────────────────
    p_pol = sub.add_parser("restart-policy", help="set a container's restart policy")
    p_pol.add_argument("ref", metavar="NAME_OR_ID")
    p_pol.add_argument("policy", choices=RESTART_POLICIES)
    p_pol.add_argument("--max-retry", type=int, default=0, metavar="N",
                       help="max retries for 'on-failure' (0 = retry forever)")

    # ── mem ────────────────────────────────────────────────────────────────
    p_mem = sub.add_parser("mem", help="set a container's memory limit")
    p_mem.add_argument("ref", metavar="NAME_OR_ID")
    p_mem.add_argument("limit", metavar="LIMIT", help="e.g. 256m, 1g -- 0 removes the limit")

    # ── logs ───────────────────────────────────────────────────────────────
    p_logs = sub.add_parser("logs", help="show container logs")
    p_logs.add_argument("ref", metavar="NAME_OR_ID")
    p_logs.add_argument("--tail", type=int, default=200, metavar="N")
    p_logs.add_argument("-f", "--follow", action="store_true")
    p_logs.add_argument("--no-timestamps", action="store_true")

    # ── stats ──────────────────────────────────────────────────────────────
    p_stats = sub.add_parser("stats", help="one-shot CPU/memory/network stats")
    p_stats.add_argument("ref", metavar="NAME_OR_ID")

    # ── inspect ────────────────────────────────────────────────────────────
    p_inspect = sub.add_parser("inspect", help="raw JSON inspect")
    p_inspect.add_argument("ref", metavar="REF")
    p_inspect.add_argument("--type", choices=("container", "image", "volume", "network"),
                           default="container")

    # ── images ─────────────────────────────────────────────────────────────
    p_images = sub.add_parser("images", help="list images")
    p_images.add_argument("-a", "--all", action="store_true", help="include intermediate images")

    # ── pull / rmi ───────────────────────────────────────────────────────────
    p_pull = sub.add_parser("pull", help="pull an image")
    p_pull.add_argument("image", metavar="IMAGE[:TAG]")

    p_rmi = sub.add_parser("rmi", help="remove an image")
    p_rmi.add_argument("ref", metavar="ID_OR_TAG")
    p_rmi.add_argument("-f", "--force", action="store_true")

    # ── volumes / networks ───────────────────────────────────────────────────
    sub.add_parser("volumes", help="list volumes")
    sub.add_parser("networks", help="list networks")

    # ── prune ──────────────────────────────────────────────────────────────
    p_prune = sub.add_parser("prune", help="remove unused containers/images/volumes/networks")
    p_prune.add_argument("--containers", action="store_true", help="prune stopped containers (default)")
    p_prune.add_argument("--images", action="store_true", help="prune dangling images")
    p_prune.add_argument("--volumes", action="store_true", help="prune unused volumes")
    p_prune.add_argument("--networks", action="store_true", help="prune unused networks")
    p_prune.add_argument("--all", action="store_true", help="prune all of the above")
    p_prune.add_argument("-y", "--yes", action="store_true", help="skip the confirmation prompt")

    # ── status ─────────────────────────────────────────────────────────────
    sub.add_parser("status", help="Docker daemon / Colima connectivity")

    return parser


_DISPATCH = {
    "ps": "cmd_ps",
    "start": "cmd_start",
    "stop": "cmd_stop",
    "restart": "cmd_restart",
    "rm": "cmd_rm",
    "rename": "cmd_rename",
    "restart-policy": "cmd_restart_policy",
    "mem": "cmd_mem",
    "logs": "cmd_logs",
    "stats": "cmd_stats",
    "inspect": "cmd_inspect",
    "images": "cmd_images",
    "pull": "cmd_pull",
    "rmi": "cmd_rmi",
    "volumes": "cmd_volumes",
    "networks": "cmd_networks",
    "prune": "cmd_prune",
    "status": "cmd_status",
}


def cli_main(argv: list[str]) -> None:
    """Entry point for `dockpilot <command> ...`. argv excludes the program name."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    from src.cli import commands
    handler = getattr(commands, _DISPATCH[args.command])
    handler(args)
