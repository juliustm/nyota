import random

# Master data source for all mock assets
all_assets_data = [
    {'id': 1, 'slug': 'nairobi-at-night', 'title': 'Nairobi at Night - Photo Pack', 'asset_type': 'photo-pack', 'tags': ['Photography', 'Urban', 'Night'], 'details_line': '50 High-Resolution Photos', 'story_snippet': "Weeks spent wandering the city after dark...", 'price': 25.00, 'purchase_type': 'onetime', 'subscription_interval': None, 'deliverables': ['50 high-resolution JPEG files', 'Full commercial license', 'Instant digital download'], 'cover_image_url': 'https://images.unsplash.com/photo-1597931322223-9a5729758b3c?ixlib=rb-4.0.3&q=85&fm=jpg&crop=entropy&cs=srgb&w=600', 'stats': {'sales': 124, 'reviews': 8}, 'revenue': 3100.00, 'purchased': True, 'allow_multiple': False, 'status': 'Published', 'reviews': [{'author': 'Juma B.', 'avatar': 'https://i.pravatar.cc/40?u=user1', 'text': 'Incredible shots!', 'rating': 5, 'replies': []}]},
    {'id': 2, 'slug': 'swahili-beginners-course', 'title': "Beginner's Guide to Swahili (Video Course)", 'asset_type': 'video-series', 'tags': ['Education', 'Language'], 'details_line': '12 Lessons • 4.5 Hours', 'story_snippet': "A course that teaches not just words, but the culture...", 'price': 15.00, 'purchase_type': 'subscription', 'subscription_interval': 'monthly', 'deliverables': ['12 video lessons', 'Downloadable PDF notes', 'Community access'], 'cover_image_url': 'https://images.unsplash.com/photo-1593369457993-54161579403d?ixlib=rb-4.0.3&q=85&fm=jpg&crop=entropy&cs=srgb&w=600', 'stats': {'sales': 88, 'reviews': 1}, 'revenue': 7039.12, 'allow_multiple': False, 'purchased': True, 'status': 'Published', 'reviews': [{'author': 'David M.', 'avatar': 'https://i.pravatar.cc/40?u=user3', 'text': 'The best language course I\'ve ever taken.', 'rating': 5, 'replies': []}]},
    {'id': 8, 'slug': 'creator-conf-2025', 'title': 'Creator Conference 2025 Ticket', 'asset_type': 'ticket', 'tags': ['Event', 'Networking'], 'details_line': 'Dec 15, 2024 • Nairobi', 'story_snippet': "Join us for a two-day immersive experience...", 'price': 150.00, 'purchase_type': 'onetime', 'subscription_interval': None, 'deliverables': ['Full 2-day event access', 'Networking mixer entry', 'Digital goodie bag'], 'event_date': '2024-12-15T09:00:00', 'tickets_left': 27, 'allow_multiple': True, 'purchased': True, 'cover_image_url': 'https://images.unsplash.com/photo-1511578314322-379afb476865?ixlib=rb-4.0.3&q=85&fm=jpg&crop=entropy&cs=srgb&w=600', 'stats': {'sales': 45, 'reviews': 2}, 'revenue': 6750.00, 'status': 'Published', 'reviews': [{'author': 'Maria S.', 'avatar': 'https://i.pravatar.cc/40?u=user8', 'text': 'A game-changer for my career!', 'rating': 5, 'replies': []}]},
    {'id': 9, 'slug': 'advanced-blender-techniques', 'title': 'Advanced Blender Techniques', 'asset_type': 'video-series', 'tags': ['3D', 'Design'], 'details_line': '15 In-depth Lessons', 'story_snippet': "Go beyond the basics into procedural texturing...", 'price': 129.00, 'purchase_type': 'onetime', 'subscription_interval': None, 'deliverables': ['15 HD video files', 'All .blend project files', 'Texture library'], 'cover_image_url': 'https://images.unsplash.com/photo-1611669910501-99341483c6d2?ixlib=rb-4.0.3&q=85&fm=jpg&crop=entropy&cs=srgb&w=600', 'stats': {'sales': 32, 'reviews': 1}, 'revenue': 4128.00, 'allow_multiple': False, 'purchased': False, 'status': 'Draft', 'reviews': [{'author': 'Alex T.', 'avatar': 'https://i.pravatar.cc/40?u=user15', 'text': 'Mind-blowing content.', 'rating': 5, 'replies': []}]},
]
random.shuffle(all_assets_data)

# Derived data for the public-facing storefront
mock_assets = all_assets_data

# Derived data for the customer's personal library
mock_purchased_assets = [asset for asset in all_assets_data if asset.get('purchased', False)]

# Derived data for the admin panel's asset list
mock_admin_assets = [{'id': asset['id'], 'title': asset['title'], 'type': asset['asset_type'], 'cover': asset['cover_image_url'], 'status': asset.get('status', 'Draft'), 'sales': asset['stats']['sales'], 'revenue': asset.get('revenue', 0.00)} for asset in all_assets_data]

# Mock data for other admin pages
dashboard_stats = {'total_earnings': 12450.00, 'earnings_this_month': 1850.50, 'supporters_count': 316, 'new_supporters_this_month': 24}
recent_activity = [
    {'type': 'sale', 'icon': 'sale', 'title': 'Sale: Nairobi at Night', 'subtitle': 'Purchased by Juma B.', 'value': '+ TZS25.00', 'time_ago': '2h ago'},
    {'type': 'new_supporter', 'icon': 'new_supporter', 'title': 'New Supporter', 'subtitle': 'Asha K. made their first purchase.', 'value': '+ TZS15.00', 'time_ago': 'Yesterday'},
    {'type': 'review', 'icon': 'review', 'title': 'New 5-Star Review', 'subtitle': 'for "Beginner\'s Guide to Swahili"', 'value': '', 'time_ago': '2 days ago'},
]
mock_supporters = [
    {'id': 1, 'name': 'Juma Bakari', 'avatar': 'https://i.pravatar.cc/40?u=user1', 'join_date': '2023-10-25', 'total_spent': 150.50, 'purchases': 4, 'is_affiliate': True, 'commission': 15},
    {'id': 2, 'name': 'Asha Kiprop', 'avatar': 'https://i.pravatar.cc/40?u=user2', 'join_date': '2023-10-22', 'total_spent': 79.99, 'purchases': 1, 'is_affiliate': True, 'commission': 10},
    {'id': 3, 'name': 'David Mwangi', 'avatar': 'https://i.pravatar.cc/40?u=user3', 'join_date': '2023-09-15', 'total_spent': 420.00, 'purchases': 8, 'is_affiliate': False, 'commission': None},
]