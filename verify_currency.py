from main import create_app
from flask import g

app = create_app()

with app.app_context():
    # Mock a creator setting
    from models.nyota import Creator, CreatorSetting, db
    
    # Ensure we have a creator
    db.create_all()
    creator = Creator.query.first()
    if not creator:
        print("No creator found, creating one...")
        creator = Creator(username="test_creator", totp_secret="base32secret3232")
        db.session.add(creator)
        db.session.commit()
    
    # Test default currency
    print(f"Current Currency Setting: {creator.get_setting('payment_uza_currency')}")
    
    # Inject global vars
    context = app.context_processor(lambda: {})
    injected = {}
    for processor in app.template_context_processors[None]:
        injected.update(processor())
        
    print(f"Injected Currency Symbol: {injected.get('currency_symbol')}")
    
    # Change currency
    creator.set_setting('payment_uza_currency', 'TZS')
    db.session.commit()
    
    # Re-inject
    injected = {}
    for processor in app.template_context_processors[None]:
        injected.update(processor())
        
    print(f"New Injected Currency Symbol: {injected.get('currency_symbol')}")
    
    if injected.get('currency_symbol') == 'TZS':
        print("SUCCESS: Dynamic currency is working.")
    else:
        print("FAILURE: Dynamic currency is NOT working.")
