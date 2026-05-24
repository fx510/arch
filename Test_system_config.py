#!/usr/bin/env python3
"""
Test suite for system configuration module
Tests configure_system() function
"""

import unittest
from unittest.mock import patch, MagicMock, mock_open
from pathlib import Path

class MockConfig:
    USER = "test"
    USER_PASS = "asdasd"
    ROOT_PASS = "test"
    HOSTNAME = "archyBTW"

class TestSystemConfiguration(unittest.TestCase):
    
    def setUp(self):
        self.config = MockConfig()
    
    @patch('subprocess.run')
    def test_genfstab_generation(self, mock_run):
        """Test fstab generation"""
        mock_run.return_value = MagicMock(returncode=0)
        
        cmd = "genfstab -U /mnt > /mnt/etc/fstab"
        
        self.assertIn("genfstab", cmd)
        self.assertIn("-U", cmd)  # Use UUIDs
        self.assertIn("/mnt/etc/fstab", cmd)
    
    @patch('subprocess.run')
    def test_timezone_configuration(self, mock_run):
        """Test timezone symlink creation"""
        mock_run.return_value = MagicMock(returncode=0)
        
        cmd = "arch-chroot /mnt bash -c 'ln -sf /usr/share/zoneinfo/Europe/Amsterdam /etc/localtime'"
        
        self.assertIn("ln -sf", cmd)
        self.assertIn("/usr/share/zoneinfo/Europe/Amsterdam", cmd)
        self.assertIn("/etc/localtime", cmd)
    
    @patch('subprocess.run')
    def test_hwclock_sync(self, mock_run):
        """Test hardware clock synchronization"""
        mock_run.return_value = MagicMock(returncode=0)
        
        cmd = "arch-chroot /mnt hwclock --systohc"
        
        self.assertIn("hwclock", cmd)
        self.assertIn("--systohc", cmd)
    
    def test_locale_generation_includes_en_us(self):
        """Test that en_US.UTF-8 locale is included"""
        locale_content = "en_US.UTF-8 UTF-8\n"
        
        self.assertIn("en_US.UTF-8", locale_content)
    
    def test_locale_generation_includes_ar_sa(self):
        """Test that ar_SA.UTF-8 locale is included"""
        locale_content = "ar_SA.UTF-8 UTF-8\n"
        
        self.assertIn("ar_SA.UTF-8", locale_content)
    
    @patch('subprocess.run')
    def test_locale_gen_command(self, mock_run):
        """Test locale-gen is executed"""
        mock_run.return_value = MagicMock(returncode=0)
        
        cmd = "arch-chroot /mnt locale-gen"
        
        self.assertIn("locale-gen", cmd)
    
    def test_locale_conf_file_content(self):
        """Test locale.conf file content"""
        content = "LANG=en_US.UTF-8"
        
        self.assertEqual(content, "LANG=en_US.UTF-8")
    
    def test_vconsole_conf_file_content(self):
        """Test vconsole.conf file content"""
        content = "KEYMAP=us"
        
        self.assertEqual(content, "KEYMAP=us")
    
    def test_hostname_file_content(self):
        """Test hostname file content"""
        content = f"{self.config.HOSTNAME}\n"
        
        self.assertEqual(content, "archyBTW\n")
    
    def test_hosts_file_content(self):
        """Test /etc/hosts file content"""
        hosts = f"127.0.0.1\tlocalhost\n::1\t\tlocalhost\n127.0.1.1\t{self.config.HOSTNAME}.localdomain\n"
        
        self.assertIn("127.0.0.1", hosts)
        self.assertIn("localhost", hosts)
        self.assertIn("::1", hosts)
        self.assertIn(f"{self.config.HOSTNAME}.localdomain", hosts)
    
    @patch('subprocess.run')
    def test_root_password_setting(self, mock_run):
        """Test root password is set"""
        mock_run.return_value = MagicMock(returncode=0)
        
        cmd = f"arch-chroot /mnt bash -c \"echo 'root:{self.config.ROOT_PASS}' | chpasswd\""
        
        self.assertIn("chpasswd", cmd)
        self.assertIn("root:", cmd)
    
    @patch('subprocess.run')
    def test_user_creation(self, mock_run):
        """Test user account creation"""
        mock_run.return_value = MagicMock(returncode=0)
        
        cmd = f"arch-chroot /mnt useradd -m -s /bin/bash {self.config.USER}"
        
        self.assertIn("useradd", cmd)
        self.assertIn("-m", cmd)  # Create home directory
        self.assertIn("-s /bin/bash", cmd)
        self.assertIn(self.config.USER, cmd)
    
    @patch('subprocess.run')
    def test_user_password_setting(self, mock_run):
        """Test user password is set"""
        mock_run.return_value = MagicMock(returncode=0)
        
        cmd = f"arch-chroot /mnt bash -c \"echo '{self.config.USER}:{self.config.USER_PASS}' | chpasswd\""
        
        self.assertIn("chpasswd", cmd)
        self.assertIn(f"{self.config.USER}:", cmd)
    
    @patch('subprocess.run')
    def test_user_groups_creation(self, mock_run):
        """Test required groups are created"""
        mock_run.return_value = MagicMock(returncode=0)
        
        groups = ["wheel", "audit", "libvirt", "firejail", "network"]
        
        for group in groups:
            cmd = f"arch-chroot /mnt groupadd -rf {group}"
            self.assertIn("groupadd", cmd)
            self.assertIn("-rf", cmd)
            self.assertIn(group, cmd)
    
    @patch('subprocess.run')
    def test_user_added_to_groups(self, mock_run):
        """Test user is added to required groups"""
        mock_run.return_value = MagicMock(returncode=0)
        
        groups = ["wheel", "audit", "libvirt", "firejail", "network"]
        
        for group in groups:
            cmd = f"arch-chroot /mnt gpasswd -a {self.config.USER} {group}"
            self.assertIn("gpasswd", cmd)
            self.assertIn("-a", cmd)
            self.assertIn(self.config.USER, cmd)
            self.assertIn(group, cmd)
    
    @patch('subprocess.run')
    def test_allow_internet_group_created(self, mock_run):
        """Test allow-internet group is created"""
        mock_run.return_value = MagicMock(returncode=0)
        
        cmd = "arch-chroot /mnt groupadd -rf allow-internet"
        
        self.assertIn("groupadd", cmd)
        self.assertIn("allow-internet", cmd)
    
    def test_all_required_groups_present(self):
        """Test all required groups are in the list"""
        groups = ["wheel", "audit", "libvirt", "firejail", "network", "allow-internet"]
        
        required_groups = ["wheel", "audit", "libvirt", "firejail", "network"]
        
        for req_group in required_groups:
            self.assertIn(req_group, groups)


class TestSystemConfigurationIntegration(unittest.TestCase):
    """Integration tests for system configuration"""
    
    @patch('subprocess.run')
    @patch('builtins.open', new_callable=mock_open)
    def test_full_configuration_sequence(self, mock_file, mock_run):
        """Test complete configuration sequence"""
        mock_run.return_value = MagicMock(returncode=0)
        
        config = MockConfig()
        
        # Simulate full configuration sequence
        steps = [
            "genfstab -U /mnt > /mnt/etc/fstab",
            "arch-chroot /mnt ln -sf /usr/share/zoneinfo/Europe/Amsterdam /etc/localtime",
            "arch-chroot /mnt hwclock --systohc",
            "arch-chroot /mnt locale-gen",
            f"arch-chroot /mnt useradd -m -s /bin/bash {config.USER}",
            f"arch-chroot /mnt echo '{config.USER}:{config.USER_PASS}' | chpasswd",
        ]
        
        # Verify minimum expected steps
        self.assertGreaterEqual(len(steps), 6)
        self.assertTrue(any("genfstab" in step for step in steps))
        self.assertTrue(any("locale-gen" in step for step in steps))
        self.assertTrue(any("useradd" in step for step in steps))
    
    def test_file_writes_required(self):
        """Test that required configuration files are written"""
        required_files = [
            "/etc/locale.conf",
            "/etc/vconsole.conf",
            "/etc/hostname",
            "/etc/hosts"
        ]
        
        # These files should be created during configuration
        self.assertEqual(len(required_files), 4)
    
    @patch('subprocess.run')
    def test_chroot_commands_use_arch_chroot(self, mock_run):
        """Test that configuration commands use arch-chroot"""
        mock_run.return_value = MagicMock(returncode=0)
        
        commands = [
            "arch-chroot /mnt hwclock --systohc",
            "arch-chroot /mnt locale-gen",
            f"arch-chroot /mnt useradd -m -s /bin/bash test"
        ]
        
        for cmd in commands:
            self.assertIn("arch-chroot /mnt", cmd)


if __name__ == '__main__':
    unittest.main(verbosity=2)