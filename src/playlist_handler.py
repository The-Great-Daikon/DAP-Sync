"""Playlist handler for generating playlists for DAP."""

import logging
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class PlaylistHandler:
    """Handler for playlist generation and management."""
    
    def __init__(self, dap_music_path: str, library_path: str):
        """
        Initialize playlist handler.
        
        Args:
            dap_music_path: Base path for music on DAP
            library_path: Base path for music library on NAS
        """
        self.dap_music_path = dap_music_path
        self.library_path = library_path
    
    def generate_playlist(self, playlist_name: str, tracks: List[Dict[str, Any]], 
                         playlist_mapping: Optional[Dict[str, str]] = None) -> str:
        """
        Generate M3U playlist content for DAP.
        
        Args:
            playlist_name: Name of playlist
            tracks: List of track dictionaries
            playlist_mapping: Optional mapping for playlist names
            
        Returns:
            M3U playlist content as string
        """
        # Apply playlist name mapping if provided
        if playlist_mapping and playlist_name in playlist_mapping:
            playlist_name = playlist_mapping[playlist_name]
        
        # Generate M3U content
        lines = ['#EXTM3U']
        
        for track in tracks:
            file_path = track.get('file_path', '')
            if not file_path:
                continue
            
            # Get relative path on DAP
            relative_path = self._get_relative_dap_path(file_path)
            if not relative_path:
                continue
            
            # Get track info
            title = track.get('title', os.path.basename(file_path))
            artist = track.get('artist', 'Unknown Artist')
            duration = int(track.get('duration', 0))
            
            # Add extended info line
            lines.append(f'#EXTINF:{duration},{artist} - {title}')
            # Add file path (relative to DAP music path)
            lines.append(relative_path)
        
        return '\n'.join(lines) + '\n'
    
    def _get_relative_dap_path(self, file_path: str) -> Optional[str]:
        """
        Get relative path on DAP for a file.
        
        Args:
            file_path: Absolute file path on NAS
            
        Returns:
            Relative path on DAP, or None if path cannot be determined
        """
        try:
            # Normalize paths
            file_path = os.path.normpath(file_path)
            library_path = os.path.normpath(self.library_path)
            
            # Check if file is within library path
            if not file_path.startswith(library_path):
                # Try to find relative path by matching basename
                # This handles cases where library path structure differs
                basename = os.path.basename(file_path)
                # Create path using artist/album structure
                artist = os.path.basename(os.path.dirname(os.path.dirname(file_path)))
                album = os.path.basename(os.path.dirname(file_path))
                
                # Construct DAP path: Music/Artist/Album/Filename
                relative_path = os.path.join(artist, album, basename)
                return relative_path.replace(os.path.sep, '/')
            
            # Get relative path from library path
            relative_path = os.path.relpath(file_path, library_path)
            
            # Normalize separators for DAP (use forward slashes)
            relative_path = relative_path.replace(os.path.sep, '/')
            
            return relative_path
        
        except Exception as e:
            logger.warning(f"Error getting relative DAP path for {file_path}: {e}")
            return None
    
    def save_playlist(self, playlist_content: str, playlist_name: str, 
                     dap_playlists_path: str) -> str:
        """
        Get playlist file path on DAP.
        
        Args:
            playlist_content: M3U playlist content
            playlist_name: Name of playlist
            dap_playlists_path: Path to playlists directory on DAP
            
        Returns:
            Playlist file path on DAP
        """
        # Sanitize playlist name for filename
        safe_name = self._sanitize_filename(playlist_name)
        playlist_filename = f"{safe_name}.m3u"
        playlist_path = os.path.join(dap_playlists_path, playlist_filename)
        
        return playlist_path
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename by removing invalid characters.
        
        Args:
            filename: Original filename
            
        Returns:
            Sanitized filename
        """
        # Remove invalid characters
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        
        # Remove leading/trailing spaces and dots
        filename = filename.strip(' .')
        
        # Limit length
        if len(filename) > 255:
            filename = filename[:255]
        
        return filename
    
    def get_tracks_for_playlist(self, playlist_name: str, 
                               musicbee_reader, 
                               all_tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Get tracks for a playlist from MusicBee reader.
        
        Args:
            playlist_name: Name of playlist
            musicbee_reader: MusicBeeReader instance
            all_tracks: All available tracks
            
        Returns:
            List of track dictionaries
        """
        # Try to get playlist tracks from MusicBee
        tracks = musicbee_reader.get_playlist_tracks(playlist_name)
        
        # If playlist not found, return empty list
        if not tracks:
            logger.warning(f"Playlist '{playlist_name}' not found in MusicBee")
            return []
        
        # Filter to only include tracks that exist in all_tracks
        # This ensures we only sync tracks that are selected for sync
        file_paths = {track.get('file_path') for track in all_tracks}
        filtered_tracks = [track for track in tracks if track.get('file_path') in file_paths]
        
        return filtered_tracks
    
    def create_playlist_structure(self, tracks: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        """
        Create directory structure for tracks on DAP.
        
        Args:
            tracks: List of track dictionaries
            
        Returns:
            Dictionary mapping directory paths to list of file paths
        """
        structure = {}
        
        for track in tracks:
            file_path = track.get('file_path', '')
            if not file_path:
                continue
            
            # Get relative DAP path
            relative_path = self._get_relative_dap_path(file_path)
            if not relative_path:
                continue
            
            # Get directory path
            dir_path = os.path.dirname(relative_path)
            if not dir_path:
                dir_path = '.'
            
            # Add to structure
            if dir_path not in structure:
                structure[dir_path] = []
            
            structure[dir_path].append(file_path)
        
        return structure
    
    def generate_playlist_file(self, playlist_name: str, tracks: List[Dict[str, Any]],
                              playlist_mapping: Optional[Dict[str, str]] = None) -> tuple[str, str]:
        """
        Generate playlist file content and path.
        
        Args:
            playlist_name: Name of playlist
            tracks: List of track dictionaries
            playlist_mapping: Optional mapping for playlist names
            
        Returns:
            Tuple of (playlist_content, playlist_path)
        """
        content = self.generate_playlist(playlist_name, tracks, playlist_mapping)
        # Playlists are typically stored in a Playlists directory on DAP
        dap_playlists_path = os.path.join(self.dap_music_path, 'Playlists')
        playlist_path = self.save_playlist(content, playlist_name, dap_playlists_path)
        
        return content, playlist_path

