"""MusicBee library reader for parsing library XML and playlists."""

import logging
import os
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from dateutil import parser as date_parser

logger = logging.getLogger(__name__)


class MusicBeeReader:
    """Reader for MusicBee library XML and playlists."""
    
    def __init__(self, library_xml_path: str, playlists_path: str, library_path: str):
        """
        Initialize MusicBee reader.
        
        Args:
            library_xml_path: Path to MusicBee Library.xml file
            playlists_path: Path to MusicBee Playlists directory
            library_path: Base path to music library files
        """
        self.library_xml_path = library_xml_path
        self.playlists_path = playlists_path
        self.library_path = library_path
        self.tracks: Dict[str, Dict[str, Any]] = {}
        self.playlists: Dict[str, List[str]] = {}
    
    def load_library(self) -> bool:
        """
        Load MusicBee library from XML file.
        
        Returns:
            True if library was loaded successfully
        """
        if not os.path.exists(self.library_xml_path):
            logger.error(f"Library XML file not found: {self.library_xml_path}")
            return False
        
        try:
            logger.info(f"Loading MusicBee library from {self.library_xml_path}")
            tree = ET.parse(self.library_xml_path)
            root = tree.getroot()
            
            # MusicBee library XML structure:
            # <Library>
            #   <Items>
            #     <Item>...</Item>
            #   </Items>
            # </Library>
            
            items = root.find('Items')
            if items is None:
                logger.error("Invalid library XML: Items element not found")
                return False
            
            track_count = 0
            for item in items.findall('Item'):
                track = self._parse_track_item(item)
                if track:
                    # Use file path as key (normalized)
                    file_path = track.get('file_path', '')
                    if file_path:
                        # Normalize path
                        normalized_path = os.path.normpath(file_path)
                        self.tracks[normalized_path] = track
                        track_count += 1
            
            logger.info(f"Loaded {track_count} tracks from library")
            return True
        
        except Exception as e:
            logger.error(f"Error loading library: {e}")
            return False
    
    def _parse_track_item(self, item: ET.Element) -> Optional[Dict[str, Any]]:
        """
        Parse a track item from XML.
        
        Args:
            item: XML element representing a track
            
        Returns:
            Dictionary with track metadata, or None if parsing failed
        """
        try:
            track = {}
            
            # Get file path (required)
            file_path = item.get('FilePath', '')
            if not file_path:
                return None
            
            # Normalize path - MusicBee uses Windows paths, convert to Unix if needed
            if os.path.sep != '\\' and '\\' in file_path:
                # Convert Windows path to Unix
                file_path = file_path.replace('\\', os.path.sep)
                # Handle drive letters (C:\ -> /mnt/c/)
                if ':' in file_path:
                    parts = file_path.split(':', 1)
                    if len(parts) == 2:
                        drive = parts[0].lower()
                        path = parts[1].lstrip('\\')
                        file_path = f"/mnt/{drive}{path}"
            
            # If path is relative, make it absolute using library_path
            if not os.path.isabs(file_path):
                file_path = os.path.join(self.library_path, file_path)
            
            track['file_path'] = file_path
            
            # Parse track metadata
            track['title'] = item.get('TrackTitle', '')
            track['artist'] = item.get('Artist', '')
            track['album'] = item.get('Album', '')
            track['album_artist'] = item.get('AlbumArtist', '')
            track['genre'] = item.get('Genre', '')
            track['year'] = item.get('Year', '')
            track['track_number'] = item.get('TrackNo', '')
            track['disc_number'] = item.get('DiscNo', '')
            track['rating'] = int(item.get('Rating', 0)) if item.get('Rating') else 0
            track['play_count'] = int(item.get('PlayCount', 0)) if item.get('PlayCount') else 0
            track['date_added'] = item.get('DateAdded', '')
            track['date_modified'] = item.get('DateModified', '')
            track['last_played'] = item.get('LastPlayed', '')
            track['bitrate'] = item.get('Bitrate', '')
            track['sample_rate'] = item.get('SampleRate', '')
            track['duration'] = float(item.get('Duration', 0)) if item.get('Duration') else 0
            
            # Parse date fields
            if track['date_added']:
                try:
                    track['date_added_parsed'] = date_parser.parse(track['date_added'])
                except:
                    track['date_added_parsed'] = None
            else:
                track['date_added_parsed'] = None
            
            if track['date_modified']:
                try:
                    track['date_modified_parsed'] = date_parser.parse(track['date_modified'])
                except:
                    track['date_modified_parsed'] = None
            else:
                track['date_modified_parsed'] = None
            
            return track
        
        except Exception as e:
            logger.warning(f"Error parsing track item: {e}")
            return None
    
    def load_playlists(self) -> bool:
        """
        Load playlists from MusicBee Playlists directory.
        
        Returns:
            True if playlists were loaded successfully
        """
        if not os.path.exists(self.playlists_path):
            logger.warning(f"Playlists directory not found: {self.playlists_path}")
            return False
        
        try:
            logger.info(f"Loading playlists from {self.playlists_path}")
            playlist_count = 0
            
            for filename in os.listdir(self.playlists_path):
                if filename.endswith('.m3u') or filename.endswith('.m3u8'):
                    playlist_name = os.path.splitext(filename)[0]
                    playlist_path = os.path.join(self.playlists_path, filename)
                    
                    tracks = self._parse_playlist(playlist_path)
                    if tracks:
                        self.playlists[playlist_name] = tracks
                        playlist_count += 1
                        logger.debug(f"Loaded playlist '{playlist_name}' with {len(tracks)} tracks")
            
            logger.info(f"Loaded {playlist_count} playlists")
            return True
        
        except Exception as e:
            logger.error(f"Error loading playlists: {e}")
            return False
    
    def _parse_playlist(self, playlist_path: str) -> List[str]:
        """
        Parse M3U playlist file.
        
        Args:
            playlist_path: Path to M3U playlist file
            
        Returns:
            List of file paths in playlist
        """
        tracks = []
        
        try:
            with open(playlist_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            for line in lines:
                line = line.strip()
                
                # Skip empty lines and M3U headers
                if not line or line.startswith('#EXTM3U') or line.startswith('#EXTINF'):
                    continue
                
                # Skip if it's a URL
                if line.startswith('http://') or line.startswith('https://'):
                    continue
                
                # Handle relative paths
                if not os.path.isabs(line):
                    # Try relative to playlist directory
                    abs_path = os.path.join(os.path.dirname(playlist_path), line)
                    if os.path.exists(abs_path):
                        tracks.append(os.path.normpath(abs_path))
                    # Try relative to library path
                    else:
                        abs_path = os.path.join(self.library_path, line)
                        if os.path.exists(abs_path):
                            tracks.append(os.path.normpath(abs_path))
                else:
                    # Absolute path
                    # Normalize Windows paths
                    if os.path.sep != '\\' and '\\' in line:
                        line = line.replace('\\', os.path.sep)
                        if ':' in line:
                            parts = line.split(':', 1)
                            if len(parts) == 2:
                                drive = parts[0].lower()
                                path = parts[1].lstrip('\\')
                                line = f"/mnt/{drive}{path}"
                    
                    if os.path.exists(line):
                        tracks.append(os.path.normpath(line))
        
        except Exception as e:
            logger.warning(f"Error parsing playlist {playlist_path}: {e}")
        
        return tracks
    
    def get_all_tracks(self) -> List[Dict[str, Any]]:
        """
        Get all tracks in library.
        
        Returns:
            List of track dictionaries
        """
        return list(self.tracks.values())
    
    def get_track(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get track by file path.
        
        Args:
            file_path: File path of track
            
        Returns:
            Track dictionary, or None if not found
        """
        normalized_path = os.path.normpath(file_path)
        return self.tracks.get(normalized_path)
    
    def get_playlist_tracks(self, playlist_name: str) -> List[Dict[str, Any]]:
        """
        Get tracks in a playlist.
        
        Args:
            playlist_name: Name of playlist
            
        Returns:
            List of track dictionaries
        """
        if playlist_name not in self.playlists:
            logger.warning(f"Playlist not found: {playlist_name}")
            return []
        
        tracks = []
        for file_path in self.playlists[playlist_name]:
            track = self.get_track(file_path)
            if track:
                tracks.append(track)
            else:
                # Try to find track even if path doesn't match exactly
                # This handles path differences between systems
                for normalized_path, track in self.tracks.items():
                    if os.path.basename(normalized_path) == os.path.basename(file_path):
                        tracks.append(track)
                        break
        
        return tracks
    
    def filter_tracks_by_criteria(self, criteria: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Filter tracks based on criteria.
        
        Args:
            criteria: Dictionary with filter criteria
            
        Returns:
            List of filtered track dictionaries
        """
        filtered_tracks = []
        
        for track in self.tracks.values():
            if self._matches_criteria(track, criteria):
                filtered_tracks.append(track)
        
        return filtered_tracks
    
    def _matches_criteria(self, track: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
        """
        Check if track matches criteria.
        
        Args:
            track: Track dictionary
            criteria: Filter criteria
            
        Returns:
            True if track matches criteria
        """
        # Genre filter
        if 'genres' in criteria:
            genres = criteria['genres']
            if isinstance(genres, list):
                track_genre = track.get('genre', '').lower()
                if not any(g.lower() in track_genre for g in genres):
                    return False
        
        # Rating filter
        if 'rating_min' in criteria:
            rating_min = criteria['rating_min']
            if track.get('rating', 0) < rating_min:
                return False
        
        # Date added filter
        if 'date_added_after' in criteria:
            date_str = criteria['date_added_after']
            try:
                date_cutoff = date_parser.parse(date_str)
                date_added = track.get('date_added_parsed')
                if not date_added or date_added < date_cutoff:
                    return False
            except:
                pass
        
        # Days filter (recent tracks)
        if 'days' in criteria:
            days = criteria['days']
            cutoff_date = datetime.now() - timedelta(days=days)
            date_added = track.get('date_added_parsed')
            if not date_added or date_added < cutoff_date:
                return False
        
        # Artist filter
        if 'artists' in criteria:
            artists = criteria['artists']
            if isinstance(artists, list):
                track_artist = track.get('artist', '').lower()
                if not any(a.lower() in track_artist for a in artists):
                    return False
        
        # Album filter
        if 'albums' in criteria:
            albums = criteria['albums']
            if isinstance(albums, list):
                track_album = track.get('album', '').lower()
                if not any(a.lower() in track_album for a in albums):
                    return False
        
        return True
    
    def get_smart_playlist_tracks(self, smart_playlist_config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Get tracks for a smart playlist based on criteria.
        
        Args:
            smart_playlist_config: Smart playlist configuration
            
        Returns:
            List of track dictionaries
        """
        # Extract criteria from smart playlist config
        criteria = {}
        
        if 'rating_min' in smart_playlist_config:
            criteria['rating_min'] = smart_playlist_config['rating_min']
        
        if 'days' in smart_playlist_config:
            criteria['days'] = smart_playlist_config['days']
        
        if 'genres' in smart_playlist_config:
            criteria['genres'] = smart_playlist_config['genres']
        
        if 'artists' in smart_playlist_config:
            criteria['artists'] = smart_playlist_config['artists']
        
        if 'albums' in smart_playlist_config:
            criteria['albums'] = smart_playlist_config['albums']
        
        return self.filter_tracks_by_criteria(criteria)

