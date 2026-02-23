"""
Image compression module using TinyPNG API.

Compresses PNG, JPEG images to reduce file size before uploading to Drive.
"""
import os
import requests

# TinyPNG API key - can be overridden via environment variable
TINYPNG_API_KEY = os.environ.get('TINYPNG_API_KEY', '')

# Supported image types for compression
COMPRESSIBLE_TYPES = {'image/png', 'image/jpeg', 'image/jpg'}

# Minimum file size for TinyPNG compression (500KB)
# Files under this size are not compressed to save API calls
MIN_SIZE_FOR_COMPRESSION = 500 * 1024  # 500KB in bytes


def is_compressible_image(mime_type: str) -> bool:
    """Check if the file type can be compressed by TinyPNG."""
    return mime_type.lower() in COMPRESSIBLE_TYPES


def compress_image(file_bytes: bytes, filename: str = None) -> tuple[bytes, dict]:
    """
    Compress an image using TinyPNG API.

    Args:
        file_bytes: The original image bytes
        filename: Optional filename for logging

    Returns:
        Tuple of (compressed_bytes, stats_dict)
        stats_dict contains: original_size, compressed_size, ratio, saved_percent

    Raises:
        Exception if compression fails
    """
    if not TINYPNG_API_KEY:
        raise ValueError("TinyPNG API key not configured")

    original_size = len(file_bytes)

    try:
        # Send image to TinyPNG API
        response = requests.post(
            'https://api.tinify.com/shrink',
            auth=('api', TINYPNG_API_KEY),
            data=file_bytes,
            timeout=60
        )

        if response.status_code == 201:
            # Get the URL to download the compressed image
            output_url = response.json().get('output', {}).get('url')
            if output_url:
                # Download the compressed image
                compressed_response = requests.get(output_url, timeout=60)
                if compressed_response.status_code == 200:
                    compressed_bytes = compressed_response.content
                    compressed_size = len(compressed_bytes)

                    stats = {
                        'original_size': original_size,
                        'compressed_size': compressed_size,
                        'ratio': compressed_size / original_size if original_size > 0 else 1,
                        'saved_percent': round((1 - compressed_size / original_size) * 100, 1) if original_size > 0 else 0,
                        'saved_bytes': original_size - compressed_size
                    }

                    print(f"TinyPNG: {filename or 'image'} compressed from {original_size} to {compressed_size} bytes ({stats['saved_percent']}% saved)")

                    return compressed_bytes, stats

        # If compression failed, return original
        error_msg = response.json().get('message', 'Unknown error') if response.content else 'No response'
        print(f"TinyPNG compression failed for {filename or 'image'}: {error_msg}")
        return file_bytes, {
            'original_size': original_size,
            'compressed_size': original_size,
            'ratio': 1,
            'saved_percent': 0,
            'saved_bytes': 0,
            'error': error_msg
        }

    except requests.RequestException as e:
        print(f"TinyPNG request error for {filename or 'image'}: {e}")
        return file_bytes, {
            'original_size': original_size,
            'compressed_size': original_size,
            'ratio': 1,
            'saved_percent': 0,
            'saved_bytes': 0,
            'error': str(e)
        }


def compress_if_image(file_bytes: bytes, filename: str, mime_type: str) -> tuple[bytes, dict | None]:
    """
    Compress the file if it's a compressible image and over 500KB, otherwise return as-is.

    Args:
        file_bytes: File content
        filename: Filename
        mime_type: MIME type of the file

    Returns:
        Tuple of (file_bytes, stats_or_none)
        stats is None if file was not compressed (not an image or under 500KB)
    """
    if is_compressible_image(mime_type):
        file_size = len(file_bytes)
        if file_size < MIN_SIZE_FOR_COMPRESSION:
            print(f"Skipping TinyPNG for {filename or 'image'}: {file_size} bytes is under 500KB threshold")
            return file_bytes, None
        return compress_image(file_bytes, filename)
    return file_bytes, None
