#!/bin/bash
# Hardware Info & Driver Suggestion Script (standalone)

set -euo pipefail

echo "============================================"
echo "     Hardware Detection & Driver Guide      "
echo "============================================"

# CPU
echo -e "\n[ CPU ]"
lscpu | grep -E "Model name|Vendor ID|Architecture" || echo "lscpu not available"
grep -E "vendor_id|model name" /proc/cpuinfo | head -2 | uniq

# GPU
echo -e "\n[ GPU ]"
if command -v lspci &>/dev/null; then
    lspci -k | grep -E "VGA|3D|Display" -A 2
else
    echo "lspci missing"
fi

# Network (Ethernet & WiFi)
echo -e "\n[ Network ]"
lspci | grep -E "Ethernet|Network|Wireless" || lsusb | grep -E "Ethernet|Wireless" || echo "No network devices found via lspci/lsusb"
# Wireless chipset often needs specific drivers
iwconfig 2>/dev/null | grep -E "IEEE 802.11" || echo "No wireless extensions found"

# Audio
echo -e "\n[ Audio ]"
lspci | grep -i audio || lsusb | grep -i audio || echo "No audio device found"

# Storage controllers (SATA, NVMe)
echo -e "\n[ Storage Controllers ]"
lspci | grep -E "SATA|NVMe|IDE" || echo "No storage controllers found"

# USB controllers / chipsets
echo -e "\n[ USB Controllers ]"
lspci | grep -i usb || echo "No USB controller found"

# Kernel modules currently loaded for hardware
echo -e "\n[ Loaded Kernel Modules (relevant) ]"
lsmod | grep -E "nvidia|amdgpu|i915|nouveau|intel|radeon|wifi|e1000|r8169|iwlwifi|ath|b43|rtl" || echo "No common driver modules loaded"

# Suggestions (simple heuristic)
echo -e "\n[ Driver Suggestions ]"
if lspci | grep -i "nvidia" >/dev/null; then
    echo "NVIDIA GPU detected: install 'nvidia' (proprietary) or 'nouveau' (open)"
    echo "  For newer cards (Turing+): also consider 'nvidia-dkms'"
fi
if lspci | grep -i "AMD.*Radeon" >/dev/null; then
    echo "AMD GPU detected: use 'amdgpu' (built into kernel), maybe 'mesa' for userspace"
fi
if lspci | grep -i "Intel.*Graphics" >/dev/null; then
    echo "Intel integrated GPU: 'i915' built-in, install 'intel-media-driver' for VA-API"
fi
if lspci | grep -E "Wireless|Network" | grep -i "Intel" >/dev/null; then
    echo "Intel WiFi: 'iwlwifi' – likely 'linux-firmware' sufficient"
fi
if lspci | grep -E "Wireless|Network" | grep -i "Realtek" >/dev/null; then
    echo "Realtek WiFi: try 'rtl88x2bu-dkms-git' or 'rtw88' (kernel 5.14+)"
fi
if lspci | grep -i "Qualcomm" | grep -i "Ethernet" >/dev/null; then
    echo "Qualcomm Ethernet (e.g., AQC107): 'atlantic' driver"
fi
if lspci | grep -i "Ethernet" | grep -i "Realtek" >/dev/null; then
    echo "Realtek Ethernet: 'r8169' built-in, if issues try 'r8168-dkms'"
fi

echo -e "\n[ Full PCI device list for manual inspection ]"
lspci -vnn | head -50
echo "   ... (truncated, run 'lspci -vnn' for complete list)"

echo -e "\n[ USB Devices ]"
lsusb || echo "lsusb not found (install usbutils)"

# Optional: show recommended package groups
echo -e "\n[ Common Driver/Utility Packages ]"
echo "  For Arch Linux: install 'linux-firmware' (already included), 'mesa', 'vulkan-*'"
echo "  For WiFi: 'iwd' or 'NetworkManager' + firmware"
echo "  For audio: 'pipewire' + 'wireplumber' or 'pulseaudio'"
echo "  For printers/scanners: 'cups', 'sane'"

exit 0