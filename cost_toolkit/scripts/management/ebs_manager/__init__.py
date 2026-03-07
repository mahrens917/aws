"""
AWS EBS Volume Manager Package
Provides functionality for managing AWS EBS volumes including deletion,
information retrieval, and snapshot creation.
"""

from .cli import main
from .operations import VolumeNotFoundError, delete_ebs_volume, get_volume_detailed_info
from .reporting import print_snapshot_summary, print_volume_detailed_report
from .snapshot import create_volume_snapshot
from .utils import (
    find_volume_region,
    get_all_aws_regions,
    get_instance_name,
    get_volume_tags,
)

__all__ = [
    "main",
    "create_volume_snapshot",
    "delete_ebs_volume",
    "find_volume_region",
    "get_all_aws_regions",
    "get_instance_name",
    "get_volume_detailed_info",
    "get_volume_tags",
    "print_snapshot_summary",
    "print_volume_detailed_report",
    "VolumeNotFoundError",
]
