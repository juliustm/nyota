"""
Image optimization utilities for cover images.

Converts uploaded images to WebP format with optimal compression,
resizes to a maximum width while preserving aspect ratio, and strips
EXIF metadata for privacy and size savings.
"""

import os
import logging
from PIL import Image

logger = logging.getLogger(__name__)

# Optimization settings
MAX_WIDTH = 1200       # Max pixel width (1.5x retina for largest display context ~800px)
WEBP_QUALITY = 82      # Sweet spot: visually lossless, significant size reduction
OUTPUT_FORMAT = 'WEBP'


def optimize_cover_image(file_storage, output_dir, filename_prefix):
    """
    Optimize an uploaded cover image for web delivery.
    
    - Converts to WebP format
    - Resizes to max MAX_WIDTH pixels wide (preserving aspect ratio)
    - Strips EXIF/metadata
    
    Args:
        file_storage: A Werkzeug FileStorage object from the upload.
        output_dir: Directory to save the optimized image.
        filename_prefix: Prefix for the output filename (e.g., "42_1708851234").
    
    Returns:
        str: The filename of the optimized image (e.g., "42_1708851234_cover.webp").
    """
    optimized_filename = f"{filename_prefix}_cover.webp"
    output_path = os.path.join(output_dir, optimized_filename)

    try:
        img = Image.open(file_storage)

        # Convert RGBA/palette images to RGB (WebP supports transparency but
        # cover images don't need it, and RGB compresses better)
        if img.mode in ('RGBA', 'P', 'LA'):
            # Create white background for transparent images
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if 'A' in img.mode else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Resize if wider than MAX_WIDTH, preserving aspect ratio
        if img.width > MAX_WIDTH:
            ratio = MAX_WIDTH / img.width
            new_height = int(img.height * ratio)
            img = img.resize((MAX_WIDTH, new_height), Image.LANCZOS)

        # Save as WebP with optimized quality, stripping all metadata
        img.save(output_path, format=OUTPUT_FORMAT, quality=WEBP_QUALITY, method=4)

        # Log the optimization result
        output_size = os.path.getsize(output_path)
        logger.info(
            f"Cover image optimized: {optimized_filename} "
            f"({img.width}x{img.height}, {output_size / 1024:.1f} KB)"
        )

        return optimized_filename

    except Exception as e:
        logger.error(f"Failed to optimize cover image: {e}")
        # Clean up partial file if it exists
        if os.path.exists(output_path):
            os.remove(output_path)
        raise
