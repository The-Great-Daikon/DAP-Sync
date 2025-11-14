"""ADB client for Android device file operations over network."""

import subprocess
import logging
import os
import time
from typing import Optional, List, Dict, Tuple

logger = logging.getLogger(__name__)


class ADBClient:
    """Client for Android Debug Bridge operations over network."""
    
    def __init__(self, ip_address: str, port: int = 5555, adb_path: str = "/usr/bin/adb"):
        """
        Initialize ADB client.
        
        Args:
            ip_address: IP address of Android device
            port: ADB port (default 5555)
            adb_path: Path to adb executable
        """
        self.ip_address = ip_address
        self.port = port
        self.adb_path = adb_path
        self.device = f"{ip_address}:{port}"
        self.connected = False
    
    def _run_adb(self, command: List[str], timeout: int = 30) -> Tuple[bool, str, str]:
        """
        Run ADB command.
        
        Args:
            command: ADB command as list of strings
            timeout: Command timeout in seconds
            
        Returns:
            Tuple of (success, stdout, stderr)
        """
        try:
            result = subprocess.run(
                [self.adb_path] + command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            success = result.returncode == 0
            return success, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.error(f"ADB command timed out: {' '.join(command)}")
            return False, "", "Command timeout"
        except Exception as e:
            logger.error(f"Error running ADB command: {e}")
            return False, "", str(e)
    
    def connect(self, retries: int = 3) -> bool:
        """
        Connect to Android device over network.
        
        Args:
            retries: Number of connection retries
            
        Returns:
            True if connected successfully
        """
        for attempt in range(retries):
            logger.info(f"Connecting to {self.device} (attempt {attempt + 1}/{retries})")
            
            # Kill existing server to avoid conflicts
            self._run_adb(["kill-server"])
            
            # Connect to device
            success, stdout, stderr = self._run_adb(["connect", self.device])
            
            if success:
                # Wait a moment for connection to establish
                time.sleep(2)
                
                # Verify connection
                if self.is_connected():
                    self.connected = True
                    logger.info(f"Successfully connected to {self.device}")
                    return True
            
            if attempt < retries - 1:
                logger.warning(f"Connection failed, retrying in 3 seconds...")
                time.sleep(3)
        
        logger.error(f"Failed to connect to {self.device} after {retries} attempts")
        return False
    
    def is_connected(self) -> bool:
        """
        Check if device is connected.
        
        Returns:
            True if device is connected
        """
        success, stdout, _ = self._run_adb(["devices"])
        if success:
            # Check if device appears in devices list
            devices = stdout.strip().split('\n')[1:]  # Skip header
            for device in devices:
                if self.device in device and "device" in device:
                    return True
        return False
    
    def disconnect(self) -> bool:
        """
        Disconnect from device.
        
        Returns:
            True if disconnected successfully
        """
        success, stdout, stderr = self._run_adb(["disconnect", self.device])
        if success:
            self.connected = False
            logger.info(f"Disconnected from {self.device}")
        return success
    
    def shell(self, command: str, timeout: int = 30) -> Tuple[bool, str]:
        """
        Execute shell command on device.
        
        Args:
            command: Shell command to execute
            timeout: Command timeout in seconds
            
        Returns:
            Tuple of (success, output)
        """
        success, stdout, stderr = self._run_adb(
            ["shell", command],
            timeout=timeout
        )
        if not success:
            logger.error(f"Shell command failed: {command}, Error: {stderr}")
        return success, stdout
    
    def push_file(self, local_path: str, remote_path: str, timeout: int = 300) -> bool:
        """
        Push file to device.
        
        Args:
            local_path: Local file path
            remote_path: Remote file path on device
            timeout: Transfer timeout in seconds
            
        Returns:
            True if push was successful
        """
        if not os.path.exists(local_path):
            logger.error(f"Local file does not exist: {local_path}")
            return False
        
        # Create remote directory if it doesn't exist
        remote_dir = os.path.dirname(remote_path)
        if remote_dir:
            self.mkdir(remote_dir, create_parents=True)
        
        logger.debug(f"Pushing {local_path} to {remote_path}")
        success, stdout, stderr = self._run_adb(
            ["push", local_path, remote_path],
            timeout=timeout
        )
        
        if success:
            logger.debug(f"Successfully pushed {local_path} to {remote_path}")
        else:
            logger.error(f"Failed to push {local_path}: {stderr}")
        
        return success
    
    def pull_file(self, remote_path: str, local_path: str, timeout: int = 300) -> bool:
        """
        Pull file from device.
        
        Args:
            remote_path: Remote file path on device
            local_path: Local file path
            timeout: Transfer timeout in seconds
            
        Returns:
            True if pull was successful
        """
        # Create local directory if it doesn't exist
        local_dir = os.path.dirname(local_path)
        if local_dir and not os.path.exists(local_dir):
            os.makedirs(local_dir, exist_ok=True)
        
        logger.debug(f"Pulling {remote_path} to {local_path}")
        success, stdout, stderr = self._run_adb(
            ["pull", remote_path, local_path],
            timeout=timeout
        )
        
        if success:
            logger.debug(f"Successfully pulled {remote_path} to {local_path}")
        else:
            logger.error(f"Failed to pull {remote_path}: {stderr}")
        
        return success
    
    def file_exists(self, remote_path: str) -> bool:
        """
        Check if file exists on device.
        
        Args:
            remote_path: Remote file path
            
        Returns:
            True if file exists
        """
        success, output = self.shell(f"test -f '{remote_path}' && echo 'exists'")
        return success and "exists" in output
    
    def get_file_size(self, remote_path: str) -> Optional[int]:
        """
        Get file size on device.
        
        Args:
            remote_path: Remote file path
            
        Returns:
            File size in bytes, or None if file doesn't exist
        """
        success, output = self.shell(f"stat -c%s '{remote_path}' 2>/dev/null || echo ''")
        if success and output.strip().isdigit():
            return int(output.strip())
        return None
    
    def get_file_hash(self, remote_path: str) -> Optional[str]:
        """
        Get MD5 hash of file on device.
        
        Args:
            remote_path: Remote file path
            
        Returns:
            MD5 hash, or None if file doesn't exist
        """
        success, output = self.shell(f"md5sum '{remote_path}' 2>/dev/null | cut -d' ' -f1")
        if success and output.strip():
            return output.strip()
        return None
    
    def mkdir(self, remote_path: str, create_parents: bool = False) -> bool:
        """
        Create directory on device.
        
        Args:
            remote_path: Remote directory path
            create_parents: Create parent directories if they don't exist
            
        Returns:
            True if directory was created or already exists
        """
        flag = "-p" if create_parents else ""
        success, output = self.shell(f"mkdir {flag} '{remote_path}' 2>&1")
        # mkdir returns success even if directory exists, so check if it exists
        if not success:
            # Check if directory already exists
            success, output = self.shell(f"test -d '{remote_path}' && echo 'exists'")
            return "exists" in output
        return True
    
    def list_files(self, remote_path: str, recursive: bool = False) -> List[str]:
        """
        List files in directory on device.
        
        Args:
            remote_path: Remote directory path
            recursive: List files recursively
            
        Returns:
            List of file paths
        """
        flag = "-R" if recursive else ""
        success, output = self.shell(f"find '{remote_path}' {flag} -type f 2>/dev/null")
        if success:
            return [line.strip() for line in output.strip().split('\n') if line.strip()]
        return []
    
    def delete_file(self, remote_path: str) -> bool:
        """
        Delete file on device.
        
        Args:
            remote_path: Remote file path
            
        Returns:
            True if file was deleted successfully
        """
        success, output = self.shell(f"rm -f '{remote_path}'")
        return success
    
    def delete_directory(self, remote_path: str, recursive: bool = False) -> bool:
        """
        Delete directory on device.
        
        Args:
            remote_path: Remote directory path
            recursive: Delete recursively
            
        Returns:
            True if directory was deleted successfully
        """
        flag = "-r" if recursive else ""
        success, output = self.shell(f"rm -f {flag} '{remote_path}'")
        return success
    
    def get_device_info(self) -> Dict[str, str]:
        """
        Get device information.
        
        Returns:
            Dictionary with device information
        """
        info = {}
        commands = {
            "model": "getprop ro.product.model",
            "manufacturer": "getprop ro.product.manufacturer",
            "android_version": "getprop ro.build.version.release",
            "sdk_version": "getprop ro.build.version.sdk",
        }
        
        for key, command in commands.items():
            success, output = self.shell(command)
            if success:
                info[key] = output.strip()
        
        return info

