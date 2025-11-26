#!/usr/bin/env python3
"""
Script to update existing AssetFile records with inferred file_type.
Run this once after deploying the file_type changes.
"""

from main import create_app
from models.nyota import db, AssetFile

def infer_file_type(link):
    """Infer file type from link/path"""
    if not link:
        return 'other'
    
    extension = link.split('.')[-1].lower().split('?')[0]
    
    if extension in ['pdf']:
        return 'pdf'
    elif extension in ['mp3', 'wav', 'ogg', 'm4a', 'aac']:
        return 'audio'
    elif extension in ['mp4', 'webm', 'mov', 'avi']:
        return 'video'
    elif extension in ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg']:
        return 'image'
    else:
        return 'other'

def update_file_types():
    app = create_app()
    with app.app_context():
        print("Updating existing AssetFile records with file_type...")
        
        # Get all files without file_type
        files = AssetFile.query.filter(
            (AssetFile.file_type == None) | (AssetFile.file_type == '')
        ).all()
        
        print(f"Found {len(files)} files to update")
        
        updated = 0
        for file in files:
            old_type = file.file_type
            new_type = infer_file_type(file.storage_path)
            file.file_type = new_type
            updated += 1
            print(f"  [{updated}/{len(files)}] {file.title[:40]:40} | {file.storage_path[-30:]:30} -> {new_type}")
        
        db.session.commit()
        print(f"\n✅ Successfully updated {updated} files!")

if __name__ == '__main__':
    update_file_types()
