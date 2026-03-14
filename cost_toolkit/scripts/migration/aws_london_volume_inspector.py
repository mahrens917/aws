#!/usr/bin/env python3
"""Inspect EBS volumes in London region."""

from cost_toolkit.scripts import aws_utils

# Command lists for system inspection
SYSTEM_INFO_COMMANDS = [
    "df -h",  # Show mounted filesystems
    "lsblk",  # Show block devices
    "sudo fdisk -l | grep -E '^Disk /dev/'",  # Show disk information
    "ls -la /",  # Root directory contents
    "ls -la /mnt/",  # Check if volumes are mounted in /mnt
    "mount | grep -E '^/dev/'",  # Show mounted devices
]

VOLUME_INSPECTION_COMMANDS = [
    "sudo ls -la /dev/xvd*",  # List all attached volumes
    "sudo file -s /dev/xvdbo",  # Check Tars volume (1024GB)
    "sudo file -s /dev/sdd",  # Check 384GB volume
    "sudo file -s /dev/sde",  # Check Tars 2 volume (1024GB)
    "sudo file -s /dev/sda1",  # Check Tars 3 volume (64GB)
]


def _print_header(instance_ip):
    """Print the script header and connection information."""
    print("AWS London Volume Content Inspector")
    print("=" * 80)
    print(f"🔍 Connecting to instance at {instance_ip}")
    print("📋 Volume Analysis:")
    print()


def _print_command_list(title, commands):
    """Print a formatted list of commands."""
    print(f"{title}:")
    for i, cmd in enumerate(commands, 1):
        print(f"  {i}. {cmd}")
    print()


def _script_header():
    """Generate script header and system info section."""
    return """#!/bin/bash
echo "=== LONDON INSTANCE VOLUME ANALYSIS ==="
echo "Date: $(date)"
echo "Instance: $(curl -s http://169.254.169.254/latest/meta-data/instance-id)"
echo

echo "=== DISK USAGE ==="
df -h
echo

echo "=== BLOCK DEVICES ==="
lsblk
echo

echo "=== MOUNTED FILESYSTEMS ==="
mount | grep -E '^/dev/'
echo

echo "=== DISK INFORMATION ==="
sudo fdisk -l | grep -E '^Disk /dev/'
echo

echo "=== VOLUME DETAILS ==="
echo "Checking each attached volume..."
"""


def _volume_inspect_commands(device, label, mount_point):
    """Generate inspection commands for a single volume."""
    return f"""
echo "--- Volume {device} ({label}) ---"
sudo file -s {device}
if sudo file -s {device} | grep -q filesystem; then
    echo "Filesystem detected, attempting to mount for inspection..."
    sudo mkdir -p {mount_point}
    if sudo mount -o ro {device} {mount_point} 2>/dev/null; then
        echo "Contents of {label} volume:"
        sudo ls -la {mount_point}/ | head -20
        echo "Disk usage:"
        sudo du -sh {mount_point}/* 2>/dev/null | head -10
        sudo umount {mount_point}
    else
        echo "Could not mount volume for inspection"
    fi
fi
echo
"""


def _script_footer():
    """Generate script footer with analysis instructions."""
    return """
echo "=== ANALYSIS COMPLETE ==="
echo "Review the above output to identify:"
echo "1. Which volumes contain similar data (duplicates)"
echo "2. Which volume has the most recent data"
echo "3. Which volumes can be safely deleted"
"""


def _generate_inspection_script():
    """Generate the comprehensive bash inspection script."""
    script = _script_header()
    script += _volume_inspect_commands("/dev/xvdbo", "Tars - 1024GB", "/tmp/inspect_tars")
    script += _volume_inspect_commands("/dev/sdd", "384GB", "/tmp/inspect_384")
    script += _volume_inspect_commands("/dev/sde", "Tars 2 - 1024GB", "/tmp/inspect_tars2")
    script += _volume_inspect_commands("/dev/sda1", "Tars 3 - 64GB", "/tmp/inspect_tars3")
    script += _script_footer()
    return script


def _print_usage_instructions(instance_ip):
    """Print instructions for running the inspection script."""
    print("📝 Created comprehensive volume inspection script")
    print("💡 To run the analysis, execute these commands:")
    print()
    print("# Copy the inspection script to the instance:")
    print(f"scp -i ~/.ssh/your-key.pem /tmp/volume_inspection.sh ec2-user@{instance_ip}:/tmp/")
    print()
    print("# SSH into the instance:")
    print(f"ssh -i ~/.ssh/your-key.pem ec2-user@{instance_ip}")
    print()
    print("# Run the inspection script:")
    print("chmod +x /tmp/volume_inspection.sh")
    print("./tmp/volume_inspection.sh")
    print()


def _print_volume_summary():
    """Print the volume summary and analysis results."""
    print("📊 VOLUME SUMMARY FROM ANALYSIS:")
    print("=" * 80)
    print("✅ 4 volumes attached to instance i-05ad29f28fc8a8fdc:")
    print("   1. vol-0e148f66bcb4f7a0b (Tars) - 1024 GB - Created: 2023-02-25 (OLDEST)")
    print("   2. vol-089b9ed38099c68f3 (384) - 384 GB - Created: 2025-02-05")
    print("   3. vol-0e07da8b7b7dafa17 (Tars 2) - 1024 GB - Created: 2025-02-06")
    print("   4. vol-0249308257e5fa64d (Tars 3) - 64 GB - Created: 2025-02-06 (NEWEST)")
    print()
    print("❌ 1 unattached volume:")
    print("   5. vol-08f9abc839d13db62 (No name) - 32 GB - Created: 2025-02-05")
    print()


def _print_duplicate_analysis():
    """Print duplicate analysis findings."""
    print("🔍 DUPLICATE ANALYSIS:")
    print("   • Two 1024 GB volumes: 'Tars' (2023) vs 'Tars 2' (2025)")
    print("   • 'Tars 2' is nearly 2 years newer than 'Tars'")
    print("   • 'Tars 3' (64 GB) is the most recent, likely the boot/system volume")
    print()


def _print_cost_optimization():
    """Print cost optimization recommendations."""
    print("💰 COST OPTIMIZATION POTENTIAL:")
    print("   • Delete old 'Tars' volume (1024 GB): Save ~$82/month")
    print("   • Delete unattached volume (32 GB): Save ~$3/month")
    print("   • Total potential savings: ~$85/month")
    print()


def _print_recommendations():
    """Print final recommendations."""
    print("⚠️  RECOMMENDATION:")
    print("   1. Inspect 'Tars' vs 'Tars 2' contents to confirm 'Tars 2' is newer/better")
    print("   2. If confirmed, delete the old 'Tars' volume")
    print("   3. Delete the unattached 32 GB volume")
    print("   4. Keep 'Tars 2' (1024 GB), '384' (384 GB), and 'Tars 3' (64 GB)")


def inspect_volumes_via_ssh():
    """Connect to the London instance and inspect volume contents"""
    aws_utils.setup_aws_credentials()

    instance_ip = "35.179.157.191"

    _print_header(instance_ip)
    _print_command_list("🖥️  System Information Commands", SYSTEM_INFO_COMMANDS)
    _print_command_list("📦 Volume Inspection Commands", VOLUME_INSPECTION_COMMANDS)

    inspection_script = _generate_inspection_script()

    with open("/tmp/volume_inspection.sh", "w", encoding="utf-8") as f:
        f.write(inspection_script)

    _print_usage_instructions(instance_ip)
    _print_volume_summary()
    _print_duplicate_analysis()
    _print_cost_optimization()
    _print_recommendations()


def main():
    """Main function."""
    inspect_volumes_via_ssh()


if __name__ == "__main__":
    main()
