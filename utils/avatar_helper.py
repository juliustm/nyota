import re
import hashlib

def get_country_flag(phone):
    """
    Returns a country flag emoji based on the phone number prefix.
    Defaults to None if no match found.
    """
    if not phone:
        return None
        
    # Clean phone number
    clean_phone = re.sub(r'[^0-9]', '', str(phone))
    
    # Common African and major world prefixes
    # This is a lightweight map to avoid large dependencies
    prefix_map = {
        '255': '🇹🇿', # Tanzania
        '254': '🇰🇪', # Kenya
        '256': '🇺🇬', # Uganda
        '250': '🇷🇼', # Rwanda
        '257': '🇧🇮', # Burundi
        '234': '🇳🇬', # Nigeria
        '27': '🇿🇦',  # South Africa
        '233': '🇬🇭', # Ghana
        '1': '🇺🇸',   # USA / Canada
        '44': '🇬🇧',  # UK
        '91': '🇮🇳',  # India
        '971': '🇦🇪', # UAE
        '86': '🇨🇳',  # China
    }
    
    for prefix, flag in prefix_map.items():
        if clean_phone.startswith(prefix):
            return flag
            
    return None

def get_initials(name):
    """
    Returns up to 2 initials for a given name.
    """
    if not name:
        return "?"
    
    parts = name.strip().split()
    if not parts:
        return "?"
        
    if len(parts) == 1:
        return parts[0][:2].upper()
        
    return (parts[0][0] + parts[-1][0]).upper()

def get_avatar_color(seed_text):
    """
    Returns a consistent Tailwind color class combination based on input text.
    """
    colors = [
        'bg-red-100 text-red-800',
        'bg-orange-100 text-orange-800',
        'bg-amber-100 text-amber-800',
        'bg-yellow-100 text-yellow-800',
        'bg-lime-100 text-lime-800',
        'bg-green-100 text-green-800',
        'bg-emerald-100 text-emerald-800',
        'bg-teal-100 text-teal-800',
        'bg-cyan-100 text-cyan-800',
        'bg-sky-100 text-sky-800',
        'bg-blue-100 text-blue-800',
        'bg-indigo-100 text-indigo-800',
        'bg-violet-100 text-violet-800',
        'bg-purple-100 text-purple-800',
        'bg-fuchsia-100 text-fuchsia-800',
        'bg-pink-100 text-pink-800',
        'bg-rose-100 text-rose-800',
    ]
    
    # Generate a deterministic index
    seed_hash = hashlib.md5(str(seed_text).encode()).hexdigest()
    index = int(seed_hash, 16) % len(colors)
    
    return colors[index]

def get_avatar_data(supporter):
    """
    Determines how to display the avatar for a supporter.
    Returns:
    {
        'type': 'image' | 'flag' | 'initials',
        'content': url or char or flag emoji,
        'color': tailwind classes (only for flag/initials)
    }
    """
    # 1. Custom Avatar/Image (if implemented later or available)
    # Assuming 'avatar' field exists on supporter but might be None or default
    # If the user has a real custom avatar URL, prioritize it.
    # For now, we assume 'avatar' might be a path. 
    # If it contains 'default-avatar', we treat it as no avatar.
    
    has_custom_avatar = False
    if hasattr(supporter, 'avatar') and supporter.avatar:
        if 'default-avatar' not in supporter.avatar:
            has_custom_avatar = True
            
    if has_custom_avatar:
        return {
            'type': 'image',
            'content': supporter.avatar,
            'color': ''
        }
        
    # 2. Check for Phone Number (Flag)
    # We try to detect if the "name" is actually a phone number fallback
    # OR if we should just use the whatsapp_number field if name is empty/same
    
    name = getattr(supporter, 'name', '')
    phone = getattr(supporter, 'whatsapp_number', '')
    
    # If name looks like a phone number (digits and/or plus), treat as phone
    is_name_phone = re.match(r'^[\d\+\-\s]+$', name) if name else False
    
    display_flag = None
    
    if is_name_phone or not name or name == phone:
        # Try to get flag from the phone number
        display_flag = get_country_flag(phone)
        
        if display_flag:
            return {
                'type': 'flag',
                'content': display_flag,
                'color': 'bg-gray-50 text-2xl' # Light neutral background for flags
            }
        else:
            # Fallback for unknown country codes but clearly a phone number
            return {
                'type': 'flag', # reusing flag type for emoji
                'content': '📞',
                'color': 'bg-blue-50 text-xl'
            }
    
    # 3. Initials
    # If we have a name that isn't a phone number, use initials
    # Fallback to initials of phone if flag lookup fails but we treated it as phone?
    # No, if flag lookup fails for a phone-name, we might just show a generic icon or initials of the phone "06..." -> "06"
    
    initials = get_initials(name if name else phone)
    color = get_avatar_color(name if name else phone)
    
    return {
        'type': 'initials',
        'content': initials,
        'color': color
    }
