"""DAP sync engine for synchronizing music from MusicBee to Android DAP."""

import logging
import os
import sqlite3
import hashlib
import shutil
import tempfile
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime
import time

from adb_client import ADBClient
from musicbee_reader import MusicBeeReader
from metadata_handler import MetadataHandler
from playlist_handler import PlaylistHandler

logger = logging.getLogger(__name__)


class DAPSync:
    """Main sync engine for DAP synchronization."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize DAP sync engine.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        
        # Initialize components
        musicbee_config = config.get('musicbee', {})
        dap_config = config.get('dap', {})
        sync_config = config.get('sync', {})
        metadata_config = config.get('metadata', {})
        database_config = config.get('database', {})
        
        # MusicBee reader
        self.musicbee_reader = MusicBeeReader(
            library_xml_path=musicbee_config.get('library_xml'),
            playlists_path=musicbee_config.get('playlists_path'),
            library_path=musicbee_config.get('library_path')
        )
        
        # ADB client
        self.adb_client = ADBClient(
            ip_address=dap_config.get('ip_address'),
            port=dap_config.get('port', 5555),
            adb_path=dap_config.get('adb_path', '/usr/bin/adb')
        )
        
        # Metadata handler
        self.metadata_handler = MetadataHandler(
            embed_artwork=metadata_config.get('embed_artwork', True),
            artwork_size=metadata_config.get('artwork_size', 1000)
        )
        
        # Playlist handler
        self.playlist_handler = PlaylistHandler(
            dap_music_path=dap_config.get('music_path', '/sdcard/Music'),
            library_path=musicbee_config.get('library_path')
        )
        
        # Sync settings
        self.sync_mode = sync_config.get('mode', 'incremental')
        self.sync_criteria = sync_config.get('criteria', [])
        
        # Database for sync tracking
        self.db_path = database_config.get('path', '/app/data/sync.db')
        self._init_database()
        
        # Stats
        self.stats = {
            'tracks_synced': 0,
            'tracks_skipped': 0,
            'tracks_failed': 0,
            'playlists_synced': 0,
            'playlists_failed': 0,
            'bytes_transferred': 0,
            'start_time': None,
            'end_time': None
        }
    
    def _init_database(self):
        """Initialize sync database."""
        try:
            # Create database directory if it doesn't exist
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            
            # Connect to database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create sync history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sync_history (
                    file_path TEXT PRIMARY KEY,
                    file_hash TEXT,
                    file_size INTEGER,
                    last_synced TIMESTAMP,
                    sync_status TEXT
                )
            ''')
            
            # Create index
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_file_path ON sync_history(file_path)
            ''')
            
            conn.commit()
            conn.close()
            
            logger.debug(f"Initialized sync database at {self.db_path}")
        
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
    
    def _get_file_hash(self, file_path: str) -> Optional[str]:
        """
        Get file hash for comparison.
        
        Args:
            file_path: Path to file
            
        Returns:
            File hash, or None if file doesn't exist
        """
        if not os.path.exists(file_path):
            return None
        
        try:
            # Use metadata handler for hash
            return self.metadata_handler.get_file_hash(file_path)
        except Exception as e:
            logger.warning(f"Error getting file hash: {e}")
            return None
    
    def _get_sync_status(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get sync status from database.
        
        Args:
            file_path: Path to file
            
        Returns:
            Sync status dictionary, or None if not found
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT file_hash, file_size, last_synced, sync_status
                FROM sync_history
                WHERE file_path = ?
            ''', (file_path,))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'file_hash': row[0],
                    'file_size': row[1],
                    'last_synced': row[2],
                    'sync_status': row[3]
                }
        
        except Exception as e:
            logger.warning(f"Error getting sync status: {e}")
        
        return None
    
    def _update_sync_status(self, file_path: str, file_hash: str, 
                           file_size: int, sync_status: str):
        """
        Update sync status in database.
        
        Args:
            file_path: Path to file
            file_hash: File hash
            file_size: File size in bytes
            sync_status: Sync status
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT OR REPLACE INTO sync_history
                (file_path, file_hash, file_size, last_synced, sync_status)
                VALUES (?, ?, ?, ?, ?)
            ''', (file_path, file_hash, file_size, datetime.now().isoformat(), sync_status))
            
            conn.commit()
            conn.close()
        
        except Exception as e:
            logger.warning(f"Error updating sync status: {e}")
    
    def _should_sync_file(self, file_path: str, file_hash: str, 
                         file_size: int) -> bool:
        """
        Check if file should be synced.
        
        Args:
            file_path: Path to file
            file_hash: File hash
            file_size: File size in bytes
            
        Returns:
            True if file should be synced
        """
        if self.sync_mode == 'full':
            return True
        
        # Incremental sync - check database
        sync_status = self._get_sync_status(file_path)
        
        if not sync_status:
            # New file
            return True
        
        # Check if file has changed
        if sync_status['file_hash'] != file_hash:
            # File has changed
            return True
        
        # Check if file exists on DAP
        dap_path = self._get_dap_path(file_path)
        if not self.adb_client.file_exists(dap_path):
            # File doesn't exist on DAP
            return True
        
        return False
    
    def _get_dap_path(self, file_path: str) -> str:
        """
        Get DAP path for file.
        
        Args:
            file_path: Local file path
            
        Returns:
            DAP file path
        """
        # Get relative path
        relative_path = self.playlist_handler._get_relative_dap_path(file_path)
        if not relative_path:
            # Fallback to basename
            relative_path = os.path.basename(file_path)
        
        # Construct full DAP path
        dap_music_path = self.config.get('dap', {}).get('music_path', '/sdcard/Music')
        dap_path = os.path.join(dap_music_path, relative_path).replace('\\', '/')
        
        return dap_path
    
    def _sync_file(self, file_path: str, retries: int = 3) -> bool:
        """
        Sync a single file to DAP.
        
        Args:
            file_path: Path to file
            retries: Number of retry attempts
            
        Returns:
            True if sync was successful
        """
        if not os.path.exists(file_path):
            logger.error(f"File does not exist: {file_path}")
            return False
        
        # Get file info
        file_hash = self._get_file_hash(file_path)
        file_size = os.path.getsize(file_path)
        
        if not file_hash:
            logger.error(f"Could not get file hash: {file_path}")
            return False
        
        # Check if file should be synced
        if not self._should_sync_file(file_path, file_hash, file_size):
            logger.debug(f"Skipping unchanged file: {file_path}")
            self.stats['tracks_skipped'] += 1
            return True
        
        # Get DAP path
        dap_path = self._get_dap_path(file_path)
        
        # Create temporary file for processing
        temp_file = None
        try:
            # Copy file to temp location for metadata processing
            temp_dir = tempfile.mkdtemp()
            temp_file = os.path.join(temp_dir, os.path.basename(file_path))
            shutil.copy2(file_path, temp_file)
            
            # Preserve metadata if enabled
            if self.config.get('metadata', {}).get('preserve_tags', True):
                # Metadata is already in file, but we can verify/embed artwork
                if self.config.get('metadata', {}).get('embed_artwork', True):
                    # Artwork should already be embedded, but we can verify
                    pass
            
            # Push file to DAP
            success = False
            for attempt in range(retries):
                logger.debug(f"Pushing {file_path} to {dap_path} (attempt {attempt + 1}/{retries})")
                
                if self.adb_client.push_file(temp_file, dap_path, timeout=600):
                    success = True
                    break
                
                if attempt < retries - 1:
                    logger.warning(f"Push failed, retrying in 3 seconds...")
                    time.sleep(3)
            
            if success:
                # Update sync status
                self._update_sync_status(file_path, file_hash, file_size, 'synced')
                self.stats['tracks_synced'] += 1
                self.stats['bytes_transferred'] += file_size
                logger.info(f"Successfully synced: {os.path.basename(file_path)}")
                return True
            else:
                logger.error(f"Failed to sync file after {retries} attempts: {file_path}")
                self._update_sync_status(file_path, file_hash, file_size, 'failed')
                self.stats['tracks_failed'] += 1
                return False
        
        except Exception as e:
            logger.error(f"Error syncing file {file_path}: {e}")
            self.stats['tracks_failed'] += 1
            return False
        
        finally:
            # Clean up temp file
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    os.rmdir(os.path.dirname(temp_file))
                except:
                    pass
    
    def _get_tracks_to_sync(self) -> List[Dict[str, Any]]:
        """
        Get tracks to sync based on criteria.
        
        Returns:
            List of track dictionaries
        """
        tracks_to_sync = []
        
        # Load library and playlists
        if not self.musicbee_reader.load_library():
            logger.error("Failed to load MusicBee library")
            return tracks_to_sync
        
        if not self.musicbee_reader.load_playlists():
            logger.warning("Failed to load MusicBee playlists")
        
        # Process sync criteria
        for criterion in self.sync_criteria:
            if isinstance(criterion, dict):
                # Entire library
                if criterion.get('entire_library'):
                    tracks = self.musicbee_reader.get_all_tracks()
                    tracks_to_sync.extend(tracks)
                
                # Playlists
                if 'playlists' in criterion:
                    playlist_names = criterion['playlists']
                    for playlist_name in playlist_names:
                        tracks = self.musicbee_reader.get_playlist_tracks(playlist_name)
                        tracks_to_sync.extend(tracks)
                
                # Smart playlists
                if 'smart_playlists' in criterion:
                    smart_playlists = criterion['smart_playlists']
                    for smart_playlist in smart_playlists:
                        tracks = self.musicbee_reader.get_smart_playlist_tracks(smart_playlist)
                        tracks_to_sync.extend(tracks)
                
                # Custom criteria
                if 'custom' in criterion:
                    custom_criteria = criterion['custom']
                    tracks = self.musicbee_reader.filter_tracks_by_criteria(custom_criteria)
                    tracks_to_sync.extend(tracks)
        
        # Remove duplicates (based on file_path)
        seen_paths = set()
        unique_tracks = []
        for track in tracks_to_sync:
            file_path = track.get('file_path', '')
            if file_path and file_path not in seen_paths:
                seen_paths.add(file_path)
                unique_tracks.append(track)
        
        logger.info(f"Found {len(unique_tracks)} unique tracks to sync")
        return unique_tracks
    
    def _sync_playlists(self, tracks: List[Dict[str, Any]], 
                       playlist_mapping: Optional[Dict[str, str]] = None):
        """
        Sync playlists to DAP.
        
        Args:
            tracks: List of tracks to sync
            playlist_mapping: Optional mapping for playlist names
        """
        try:
            # Get playlists from MusicBee
            playlists = self.musicbee_reader.playlists
            
            for playlist_name, playlist_tracks in playlists.items():
                # Get tracks for playlist that are in sync list
                track_paths = {track.get('file_path') for track in tracks}
                playlist_tracks_filtered = [
                    track for track in playlist_tracks
                    if track in track_paths
                ]
                
                if not playlist_tracks_filtered:
                    continue
                
                # Get track dictionaries
                playlist_track_dicts = []
                for track_path in playlist_tracks_filtered:
                    track = self.musicbee_reader.get_track(track_path)
                    if track:
                        playlist_track_dicts.append(track)
                
                if not playlist_track_dicts:
                    continue
                
                # Generate playlist
                playlist_content, playlist_path = self.playlist_handler.generate_playlist_file(
                    playlist_name, playlist_track_dicts, playlist_mapping
                )
                
                # Save playlist to temp file
                temp_dir = tempfile.mkdtemp()
                temp_playlist = os.path.join(temp_dir, os.path.basename(playlist_path))
                
                try:
                    with open(temp_playlist, 'w', encoding='utf-8') as f:
                        f.write(playlist_content)
                    
                    # Push playlist to DAP
                    if self.adb_client.push_file(temp_playlist, playlist_path, timeout=60):
                        logger.info(f"Successfully synced playlist: {playlist_name}")
                        self.stats['playlists_synced'] += 1
                    else:
                        logger.error(f"Failed to sync playlist: {playlist_name}")
                        self.stats['playlists_failed'] += 1
                
                finally:
                    # Clean up temp file
                    if os.path.exists(temp_playlist):
                        try:
                            os.remove(temp_playlist)
                            os.rmdir(temp_dir)
                        except:
                            pass
        
        except Exception as e:
            logger.error(f"Error syncing playlists: {e}")
    
    def sync(self) -> bool:
        """
        Perform synchronization.
        
        Returns:
            True if sync was successful
        """
        self.stats['start_time'] = datetime.now()
        logger.info("Starting DAP synchronization")
        
        try:
            # Connect to DAP
            if not self.adb_client.connect():
                logger.error("Failed to connect to DAP")
                return False
            
            # Get tracks to sync
            tracks = self._get_tracks_to_sync()
            
            if not tracks:
                logger.warning("No tracks to sync")
                return True
            
            # Create directory structure on DAP
            dap_music_path = self.config.get('dap', {}).get('music_path', '/sdcard/Music')
            self.adb_client.mkdir(dap_music_path, create_parents=True)
            
            # Create Playlists directory
            dap_playlists_path = os.path.join(dap_music_path, 'Playlists')
            self.adb_client.mkdir(dap_playlists_path, create_parents=True)
            
            # Sync tracks
            logger.info(f"Syncing {len(tracks)} tracks...")
            for i, track in enumerate(tracks, 1):
                file_path = track.get('file_path', '')
                if not file_path:
                    continue
                
                logger.info(f"Syncing track {i}/{len(tracks)}: {os.path.basename(file_path)}")
                
                # Create directory on DAP if needed
                dap_path = self._get_dap_path(file_path)
                dap_dir = os.path.dirname(dap_path)
                if dap_dir:
                    self.adb_client.mkdir(dap_dir, create_parents=True)
                
                # Sync file
                self._sync_file(file_path)
            
            # Sync playlists
            logger.info("Syncing playlists...")
            playlist_mapping = self.config.get('sync_rules', {}).get('playlist_mappings', {})
            self._sync_playlists(tracks, playlist_mapping)
            
            # Disconnect from DAP
            self.adb_client.disconnect()
            
            self.stats['end_time'] = datetime.now()
            duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
            
            logger.info(f"Synchronization completed in {duration:.2f} seconds")
            logger.info(f"Tracks synced: {self.stats['tracks_synced']}")
            logger.info(f"Tracks skipped: {self.stats['tracks_skipped']}")
            logger.info(f"Tracks failed: {self.stats['tracks_failed']}")
            logger.info(f"Playlists synced: {self.stats['playlists_synced']}")
            logger.info(f"Bytes transferred: {self.stats['bytes_transferred'] / 1024 / 1024:.2f} MB")
            
            return True
        
        except Exception as e:
            logger.error(f"Error during synchronization: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get sync statistics.
        
        Returns:
            Dictionary with sync statistics
        """
        return self.stats.copy()

