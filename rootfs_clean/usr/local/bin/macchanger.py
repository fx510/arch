#!/usr/bin/env python3
"""
MAC Address and Hostname Randomizer
Randomizes MAC address and hostname for privacy
"""

import subprocess
import random
import string
import sys

def generate_random_mac():
    """Generate a random MAC address with locally administered bit set"""
    # First byte: set bit 1 (locally administered) and clear bit 0 (unicast)
    first_byte = random.randint(0, 255) | 0x02 & 0xFE
    
    # Generate remaining 5 bytes
    mac = [first_byte] + [random.randint(0, 255) for _ in range(5)]
    
    return ':'.join(f'{byte:02x}' for byte in mac)

def generate_random_hostname():
    """Generate a random hostname"""
    adjectives = ['quick', 'lazy', 'happy', 'brave', 'calm', 'bright', 'dark', 'swift']
    nouns = ['fox', 'dog', 'cat', 'bird', 'fish', 'wolf', 'bear', 'lion']
    
    adj = random.choice(adjectives)
    noun = random.choice(nouns)
    num = random.randint(100, 999)
    
    return f"{adj}-{noun}-{num}"

def get_network_interfaces():
    """Get list of network interfaces"""
    try:
        result = subprocess.run(['ip', 'link', 'show'], 
                              capture_output=True, text=True, check=True)
        
        interfaces = []
        for line in result.stdout.split('\n'):
            if ':' in line and not line.startswith(' '):
                parts = line.split(':')
                if len(parts) >= 2:
                    iface = parts[1].strip()
                    # Skip loopback and virtual interfaces
                    if iface != 'lo' and not iface.startswith('vir') and not iface.startswith('docker'):
                        interfaces.append(iface)
        
        return interfaces
    except subprocess.CalledProcessError:
        return []

def change_mac_address(interface, new_mac):
    """Change MAC address of an interface"""
    try:
        # Bring interface down
        subprocess.run(['ip', 'link', 'set', interface, 'down'], 
                      check=True, capture_output=True)
        
        # Change MAC address
        subprocess.run(['ip', 'link', 'set', interface, 'address', new_mac], 
                      check=True, capture_output=True)
        
        # Bring interface up
        subprocess.run(['ip', 'link', 'set', interface, 'up'], 
                      check=True, capture_output=True)
        
        print(f"Changed MAC address of {interface} to {new_mac}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to change MAC address of {interface}: {e}", file=sys.stderr)
        return False

def change_hostname(new_hostname):
    """Change system hostname"""
    try:
        subprocess.run(['hostnamectl', 'set-hostname', new_hostname], 
                      check=True, capture_output=True)
        print(f"Changed hostname to {new_hostname}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to change hostname: {e}", file=sys.stderr)
        return False

def main():
    if subprocess.run(['id', '-u'], capture_output=True, text=True).stdout.strip() != '0':
        print("This script must be run as root", file=sys.stderr)
        sys.exit(1)
    
    # Get network interfaces
    interfaces = get_network_interfaces()
    
    if not interfaces:
        print("No network interfaces found", file=sys.stderr)
        sys.exit(1)
    
    # Change MAC address for each interface
    for iface in interfaces:
        new_mac = generate_random_mac()
        change_mac_address(iface, new_mac)
    
    # Change hostname
    new_hostname = generate_random_hostname()
    change_hostname(new_hostname)
    
    print("MAC address and hostname randomization complete")

if __name__ == "__main__":
    main()
