from main import create_app
from models.nyota import db, DigitalAsset, Creator, AssetFile

app = create_app()

def migrate_paths():
    """
    Migrates database records to use new persistence paths.
    """
    with app.app_context():
        print("--- Starting Path Migration ---")
        
        # 1. Update Store Logos
        creators = Creator.query.all()
        for creator in creators:
            logo_url = creator.get_setting('store_logo_url')
            if logo_url and '/static/uploads/logos/' in logo_url:
                new_url = logo_url.replace('/static/uploads/logos/', '/media/logos/')
                creator.set_setting('store_logo_url', new_url)
                print(f"Updated Logo for Creator {creator.id}: {new_url}")
        
        # 2. Update Asset Covers
        assets = DigitalAsset.query.filter(DigitalAsset.cover_image_url.like('%/static/uploads/covers/%')).all()
        for asset in assets:
            old_url = asset.cover_image_url
            new_url = old_url.replace('/static/uploads/covers/', '/media/covers/')
            asset.cover_image_url = new_url
            print(f"Updated Asset {asset.id} Cover: {new_url}")
            
        # 3. Check Asset Files
        files = AssetFile.query.filter(AssetFile.storage_path.like('%/static/uploads/%')).all()
        for f in files:
            if '/static/uploads/covers/' in f.storage_path:
                 f.storage_path = f.storage_path.replace('/static/uploads/covers/', '/media/covers/')
            elif '/static/uploads/logos/' in f.storage_path:
                 f.storage_path = f.storage_path.replace('/static/uploads/logos/', '/media/logos/')
            print(f"Updated File {f.id} Path: {f.storage_path}")

        db.session.commit()
        print("--- Migration Complete ---")

if __name__ == '__main__':
    migrate_paths()
