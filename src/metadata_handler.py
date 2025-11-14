"""Metadata handler for audio files using mutagen."""

import logging
import os
from typing import Optional, Dict, Any, Tuple
from PIL import Image
import io

try:
    from mutagen import File as MutagenFile
    from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC, TCON, TRCK, TPE2
    from mutagen.mp3 import MP3
    from mutagen.flac import FLAC
    from mutagen.mp4 import MP4
    from mutagen.easyid3 import EasyID3
except ImportError:
    MutagenFile = None

logger = logging.getLogger(__name__)


class MetadataHandler:
    """Handler for audio file metadata and artwork."""
    
    SUPPORTED_FORMATS = {'.mp3', '.flac', '.m4a', '.aac', '.ogg', '.opus', '.wma'}
    
    def __init__(self, embed_artwork: bool = True, artwork_size: int = 1000):
        """
        Initialize metadata handler.
        
        Args:
            embed_artwork: Whether to embed artwork in files
            artwork_size: Maximum artwork dimension in pixels
        """
        self.embed_artwork = embed_artwork
        self.artwork_size = artwork_size
    
    def is_supported(self, file_path: str) -> bool:
        """
        Check if file format is supported.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            True if format is supported
        """
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self.SUPPORTED_FORMATS
    
    def read_metadata(self, file_path: str) -> Dict[str, Any]:
        """
        Read metadata from audio file.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Dictionary with metadata
        """
        if not self.is_supported(file_path):
            logger.warning(f"Unsupported file format: {file_path}")
            return {}
        
        if not os.path.exists(file_path):
            logger.error(f"File does not exist: {file_path}")
            return {}
        
        try:
            audio_file = MutagenFile(file_path)
            if audio_file is None:
                logger.warning(f"Could not read metadata from {file_path}")
                return {}
            
            metadata = {}
            
            # Extract common tags
            if hasattr(audio_file, 'tags'):
                tags = audio_file.tags
                
                # Try EasyID3 first for MP3
                try:
                    if file_path.lower().endswith('.mp3'):
                        easy_tags = EasyID3(file_path)
                        metadata['title'] = easy_tags.get('title', [None])[0]
                        metadata['artist'] = easy_tags.get('artist', [None])[0]
                        metadata['album'] = easy_tags.get('album', [None])[0]
                        metadata['genre'] = easy_tags.get('genre', [None])[0]
                        metadata['date'] = easy_tags.get('date', [None])[0]
                        metadata['tracknumber'] = easy_tags.get('tracknumber', [None])[0]
                        metadata['albumartist'] = easy_tags.get('albumartist', [None])[0]
                    else:
                        # For other formats, use standard tags
                        metadata['title'] = tags.get('TIT2', tags.get('\xa9nam', [None]))[0] if tags.get('TIT2') or tags.get('\xa9nam') else None
                        metadata['artist'] = tags.get('TPE1', tags.get('\xa9ART', [None]))[0] if tags.get('TPE1') or tags.get('\xa9ART') else None
                        metadata['album'] = tags.get('TALB', tags.get('\xa9alb', [None]))[0] if tags.get('TALB') or tags.get('\xa9alb') else None
                        metadata['genre'] = tags.get('TCON', tags.get('\xa9gen', [None]))[0] if tags.get('TCON') or tags.get('\xa9gen') else None
                        metadata['date'] = tags.get('TDRC', tags.get('\xa9day', [None]))[0] if tags.get('TDRC') or tags.get('\xa9day') else None
                        metadata['tracknumber'] = tags.get('TRCK', tags.get('trkn', [None]))[0] if tags.get('TRCK') or tags.get('trkn') else None
                        metadata['albumartist'] = tags.get('TPE2', tags.get('aART', [None]))[0] if tags.get('TPE2') or tags.get('aART') else None
                except Exception as e:
                    logger.warning(f"Error reading tags from {file_path}: {e}")
            
            # Extract artwork
            artwork_data = self.extract_artwork(file_path)
            if artwork_data:
                metadata['artwork'] = artwork_data
            
            # File info
            metadata['length'] = audio_file.info.length if hasattr(audio_file.info, 'length') else None
            metadata['bitrate'] = audio_file.info.bitrate if hasattr(audio_file.info, 'bitrate') else None
            
            return metadata
        
        except Exception as e:
            logger.error(f"Error reading metadata from {file_path}: {e}")
            return {}
    
    def extract_artwork(self, file_path: str) -> Optional[bytes]:
        """
        Extract artwork from audio file.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Artwork data as bytes, or None if not found
        """
        if not self.is_supported(file_path):
            return None
        
        try:
            audio_file = MutagenFile(file_path)
            if audio_file is None:
                return None
            
            # Try to get artwork
            if hasattr(audio_file, 'tags'):
                tags = audio_file.tags
                
                # MP3 - APIC frames
                if file_path.lower().endswith('.mp3'):
                    if 'APIC:' in tags:
                        apic = tags['APIC:'].data
                        return apic
                    # Try all APIC frames
                    for key in tags.keys():
                        if key.startswith('APIC'):
                            apic = tags[key].data
                            return apic
                
                # FLAC - COVERART or PICTURE
                elif file_path.lower().endswith('.flac'):
                    if 'COVERART' in tags:
                        import base64
                        coverart = base64.b64decode(tags['COVERART'][0])
                        return coverart
                    elif 'PICTURE' in tags:
                        picture = tags['PICTURE'][0].data
                        return picture
                
                # MP4/M4A - covr atom
                elif file_path.lower().endswith(('.m4a', '.mp4')):
                    if 'covr' in tags:
                        covr = tags['covr'][0]
                        return covr
        
        except Exception as e:
            logger.warning(f"Error extracting artwork from {file_path}: {e}")
        
        return None
    
    def resize_artwork(self, artwork_data: bytes, max_size: int = None) -> bytes:
        """
        Resize artwork to maximum dimensions.
        
        Args:
            artwork_data: Artwork data as bytes
            max_size: Maximum dimension in pixels
            
        Returns:
            Resized artwork data as bytes
        """
        if max_size is None:
            max_size = self.artwork_size
        
        try:
            image = Image.open(io.BytesIO(artwork_data))
            
            # Resize if necessary
            if max(image.size) > max_size:
                image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            
            # Convert to JPEG if needed (for compatibility)
            if image.format != 'JPEG':
                output = io.BytesIO()
                # Convert RGBA to RGB if needed
                if image.mode == 'RGBA':
                    rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                    rgb_image.paste(image, mask=image.split()[3])
                    image = rgb_image
                image.save(output, format='JPEG', quality=95)
                return output.getvalue()
            
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=95)
            return output.getvalue()
        
        except Exception as e:
            logger.warning(f"Error resizing artwork: {e}")
            return artwork_data
    
    def embed_artwork_in_file(self, file_path: str, artwork_data: bytes) -> bool:
        """
        Embed artwork in audio file.
        
        Args:
            file_path: Path to audio file
            artwork_data: Artwork data as bytes
            
        Returns:
            True if artwork was embedded successfully
        """
        if not self.is_supported(file_path):
            logger.warning(f"Unsupported file format for artwork embedding: {file_path}")
            return False
        
        if not artwork_data:
            logger.warning(f"No artwork data provided for {file_path}")
            return False
        
        try:
            # Resize artwork if needed
            artwork_data = self.resize_artwork(artwork_data)
            
            audio_file = MutagenFile(file_path)
            if audio_file is None:
                logger.error(f"Could not open file for artwork embedding: {file_path}")
                return False
            
            # Embed artwork based on file type
            if file_path.lower().endswith('.mp3'):
                if not audio_file.tags:
                    audio_file.add_tags()
                
                # Remove existing APIC frames
                audio_file.tags.delall('APIC')
                
                # Add new APIC frame
                audio_file.tags.add(APIC(
                    encoding=3,  # UTF-8
                    mime='image/jpeg',
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=artwork_data
                ))
                audio_file.save()
            
            elif file_path.lower().endswith('.flac'):
                if not audio_file.tags:
                    audio_file.add_tags()
                
                # Remove existing PICTURE tags
                audio_file.tags.delall('PICTURE')
                
                # Add new PICTURE tag
                from mutagen.flac import Picture
                picture = Picture()
                picture.type = 3  # Cover (front)
                picture.mime = 'image/jpeg'
                picture.desc = 'Cover'
                picture.data = artwork_data
                audio_file.add_picture(picture)
                audio_file.save()
            
            elif file_path.lower().endswith(('.m4a', '.mp4')):
                if not audio_file.tags:
                    audio_file.add_tags()
                
                # Remove existing covr tags
                audio_file.tags.delall('covr')
                
                # Add new covr tag
                audio_file.tags['covr'] = [artwork_data]
                audio_file.save()
            
            logger.debug(f"Successfully embedded artwork in {file_path}")
            return True
        
        except Exception as e:
            logger.error(f"Error embedding artwork in {file_path}: {e}")
            return False
    
    def preserve_metadata(self, source_path: str, dest_path: str) -> bool:
        """
        Copy metadata from source to destination file.
        
        Args:
            source_path: Source file path
            dest_path: Destination file path
            
        Returns:
            True if metadata was copied successfully
        """
        source_metadata = self.read_metadata(source_path)
        if not source_metadata:
            logger.warning(f"No metadata found in source file: {source_path}")
            return False
        
        # Copy artwork if enabled
        if self.embed_artwork and 'artwork' in source_metadata:
            return self.embed_artwork_in_file(dest_path, source_metadata['artwork'])
        
        return True
    
    def get_file_hash(self, file_path: str) -> Optional[str]:
        """
        Get file hash for comparison (simple size + mtime).
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Hash string, or None if file doesn't exist
        """
        if not os.path.exists(file_path):
            return None
        
        try:
            stat = os.stat(file_path)
            # Simple hash based on size and modification time
            import hashlib
            hash_obj = hashlib.md5()
            hash_obj.update(str(stat.st_size).encode())
            hash_obj.update(str(int(stat.st_mtime)).encode())
            return hash_obj.hexdigest()
        except Exception as e:
            logger.error(f"Error getting file hash: {e}")
            return None

