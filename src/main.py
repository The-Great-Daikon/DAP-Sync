"""Main entry point for DAP sync utility."""

import logging
import os
import sys
import yaml
import argparse
from logging.handlers import RotatingFileHandler
from typing import Dict, Any, Optional
from datetime import datetime

from dap_sync import DAPSync

logger = logging.getLogger(__name__)


def setup_logging(config: Dict[str, Any]) -> None:
    """
    Setup logging configuration.
    
    Args:
        config: Configuration dictionary
    """
    logging_config = config.get('logging', {})
    log_level = logging_config.get('level', 'INFO')
    log_file = logging_config.get('file', '/logs/sync.log')
    max_size_mb = logging_config.get('max_size_mb', 100)
    backup_count = logging_config.get('backup_count', 10)
    
    # Set log level
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    
    # File handler with rotation
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_size_mb * 1024 * 1024,
        backupCount=backup_count
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)


def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
    """
    if not os.path.exists(config_path):
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)
    
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        logger.info(f"Loaded configuration from {config_path}")
        return config
    
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        sys.exit(1)


def load_sync_rules(sync_rules_path: Optional[str]) -> Dict[str, Any]:
    """
    Load sync rules from YAML file.
    
    Args:
        sync_rules_path: Path to sync rules file
        
    Returns:
        Sync rules dictionary
    """
    if not sync_rules_path or not os.path.exists(sync_rules_path):
        logger.warning(f"Sync rules file not found: {sync_rules_path}")
        return {}
    
    try:
        with open(sync_rules_path, 'r') as f:
            sync_rules = yaml.safe_load(f)
        
        logger.info(f"Loaded sync rules from {sync_rules_path}")
        return sync_rules or {}
    
    except Exception as e:
        logger.warning(f"Error loading sync rules: {e}")
        return {}


def validate_config(config: Dict[str, Any]) -> bool:
    """
    Validate configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        True if configuration is valid
    """
    required_keys = ['musicbee', 'dap', 'sync']
    
    for key in required_keys:
        if key not in config:
            logger.error(f"Missing required configuration key: {key}")
            return False
    
    # Validate musicbee config
    musicbee_config = config.get('musicbee', {})
    required_musicbee_keys = ['library_path', 'library_xml', 'playlists_path']
    for key in required_musicbee_keys:
        if key not in musicbee_config:
            logger.error(f"Missing required musicbee configuration key: {key}")
            return False
    
    # Validate dap config
    dap_config = config.get('dap', {})
    required_dap_keys = ['ip_address', 'music_path']
    for key in required_dap_keys:
        if key not in dap_config:
            logger.error(f"Missing required dap configuration key: {key}")
            return False
    
    # Validate sync config
    sync_config = config.get('sync', {})
    if 'criteria' not in sync_config:
        logger.error("Missing required sync configuration key: criteria")
        return False
    
    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='DAP Music Sync Utility')
    parser.add_argument(
        '--config',
        type=str,
        default='/app/config/config.yaml',
        help='Path to configuration file'
    )
    parser.add_argument(
        '--sync-rules',
        type=str,
        default='/app/config/sync-rules.yaml',
        help='Path to sync rules file'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Dry run mode (do not actually sync)'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Load sync rules
    sync_rules = load_sync_rules(args.sync_rules)
    if sync_rules:
        config['sync_rules'] = sync_rules
    
    # Setup logging (needs config)
    if args.verbose:
        config['logging']['level'] = 'DEBUG'
    setup_logging(config)
    
    # Validate configuration
    if not validate_config(config):
        logger.error("Invalid configuration")
        sys.exit(1)
    
    # Log configuration summary
    logger.info("=" * 60)
    logger.info("DAP Music Sync Utility")
    logger.info("=" * 60)
    logger.info(f"Configuration: {args.config}")
    logger.info(f"Sync rules: {args.sync_rules}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info(f"MusicBee library: {config['musicbee']['library_path']}")
    logger.info(f"DAP IP: {config['dap']['ip_address']}:{config['dap'].get('port', 5555)}")
    logger.info(f"DAP music path: {config['dap']['music_path']}")
    logger.info(f"Sync mode: {config['sync'].get('mode', 'incremental')}")
    logger.info("=" * 60)
    
    # Dry run mode
    if args.dry_run:
        logger.info("DRY RUN MODE - No files will be synced")
        logger.info("Configuration validated successfully")
        return 0
    
    # Create sync engine
    try:
        sync_engine = DAPSync(config)
    except Exception as e:
        logger.error(f"Error creating sync engine: {e}")
        sys.exit(1)
    
    # Perform synchronization
    try:
        logger.info("Starting synchronization...")
        success = sync_engine.sync()
        
        if success:
            # Get stats
            stats = sync_engine.get_stats()
            logger.info("=" * 60)
            logger.info("Synchronization Statistics:")
            logger.info("=" * 60)
            logger.info(f"Tracks synced: {stats['tracks_synced']}")
            logger.info(f"Tracks skipped: {stats['tracks_skipped']}")
            logger.info(f"Tracks failed: {stats['tracks_failed']}")
            logger.info(f"Playlists synced: {stats['playlists_synced']}")
            logger.info(f"Playlists failed: {stats['playlists_failed']}")
            logger.info(f"Bytes transferred: {stats['bytes_transferred'] / 1024 / 1024:.2f} MB")
            
            if stats['start_time'] and stats['end_time']:
                duration = (stats['end_time'] - stats['start_time']).total_seconds()
                logger.info(f"Duration: {duration:.2f} seconds")
            logger.info("=" * 60)
            
            return 0
        else:
            logger.error("Synchronization failed")
            return 1
    
    except KeyboardInterrupt:
        logger.warning("Synchronization interrupted by user")
        return 130
    
    except Exception as e:
        logger.error(f"Error during synchronization: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())

