import random

mock_assets = [
    {
        'id': 1, 'slug': 'nairobi-at-night', 'title': 'Nairobi at Night - Photo Pack', 'asset_type': 'photo-pack',
        'tags': ['Photography', 'Urban', 'Night'], 'details_line': '50 High-Resolution Photos',
        'story_snippet': "Weeks spent wandering the city after dark, from the bustling CBD to quiet suburbs, capturing the city's dual personality of energy and serenity...",
        'price': 25.00, 'purchase_type': 'onetime', 'subscription_interval': None,
        'deliverables': ['50 high-resolution JPEG files', 'Full commercial license', 'Instant digital download', 'Bonus: 5 mobile-optimized versions'],
        'cover_image_url': 'https://images.unsplash.com/photo-1597931322223-9a5729758b3c?ixlib=rb-4.0.3&q=85&fm=jpg&crop=entropy&cs=srgb&w=600',
        'stats': {'sales': 124, 'reviews': 8},
        'purchased': True,
        'allow_multiple': True,
        'reviews': [
            {'author': 'Juma B.', 'avatar': 'https://i.pravatar.cc/40?u=user1', 'text': 'Absolutely incredible shots! The quality is top-notch.', 'rating': 5, 'replies': []},
            {'author': 'Asha K.', 'avatar': 'https://i.pravatar.cc/40?u=user2', 'text': 'Worth every penny. These photos transformed my project.', 'rating': 5, 'replies': [{'author': 'Amina (Creator)', 'avatar': 'https://i.pravatar.cc/40?u=creator', 'text': 'Thank you, Asha! So glad you found them useful.'}]},
            {'author': 'Mike', 'avatar': 'https://i.pravatar.cc/40?u=user10', 'text': 'Great collection, though I wish there were more shots of the downtown area.', 'rating': 4, 'replies': []},
            {'author': 'Sarah W.', 'avatar': 'https://i.pravatar.cc/40?u=user11', 'text': 'Stunning work. Using these for my website background.', 'rating': 5, 'replies': []},
            {'author': 'Ken O.', 'avatar': 'https://i.pravatar.cc/40?u=user9', 'text': 'The lighting in these is just perfect.', 'rating': 5, 'replies': []},
            {'author': 'Fatma', 'avatar': 'https://i.pravatar.cc/40?u=user12', 'text': 'Good variety of locations.', 'rating': 4, 'replies': []},
            {'author': 'Ben', 'avatar': 'https://i.pravatar.cc/40?u=user13', 'text': 'Instant download, easy to use. Thanks!', 'rating': 5, 'replies': []},
            {'author': 'Chloe', 'avatar': 'https://i.pravatar.cc/40?u=user14', 'text': 'A must-buy for any designer working with African themes.', 'rating': 5, 'replies': []},
        ]
    },
    {
        'id': 2, 'slug': 'swahili-beginners-course', 'title': "Beginner's Guide to Swahili (Video Course)", 'asset_type': 'video-series',
        'tags': ['Education', 'Language', 'Video'], 'details_line': '12 Lessons • 4.5 Hours of Video',
        'story_snippet': "As a native speaker, I wanted to create a course that teaches not just the words, but the culture and heart behind the language...",
        'price': 15.00, 'purchase_type': 'subscription', 'subscription_interval': 'monthly',
        'deliverables': ['12 comprehensive video lessons', 'Downloadable PDF lesson notes', 'Private community access', 'Lifetime access to all future updates'],
        'cover_image_url': 'https://images.unsplash.com/photo-1593369457993-54161579403d?ixlib=rb-4.0.3&q=85&fm=jpg&crop=entropy&cs=srgb&w=600',
        'stats': {'sales': 88, 'reviews': 1},
        'allow_multiple': True,
        'purchased': True,
        'reviews': [{'author': 'David M.', 'avatar': 'https://i.pravatar.cc/40?u=user3', 'text': 'The best language course I\'ve ever taken. The instructor is amazing!', 'rating': 5, 'replies': []}]
    },
    {
        'id': 8, 'slug': 'digital-creator-conference-2025', 'title': 'Digital Creator Conference 2025 Ticket', 'asset_type': 'ticket',
        'tags': ['Event', 'Networking', 'Conference'], 'details_line': 'Dec 15, 2024 • Nairobi',
        'story_snippet': "Join us for a two-day immersive experience with talks from industry leaders, hands-on workshops, and networking opportunities...",
        'price': 150.00, 'purchase_type': 'onetime', 'subscription_interval': None,
        'deliverables': ['Full 2-day event access', 'Entry to the networking mixer', 'Digital goodie bag', 'Access to post-event recordings'],
        'event_date': '2024-12-15T09:00:00', 'tickets_left': 27,
        'allow_multiple': True,
        'cover_image_url': 'https://images.unsplash.com/photo-1511578314322-379afb476865?ixlib=rb-4.0.3&q=85&fm=jpg&crop=entropy&cs=srgb&w=600',
        'stats': {'sales': 45, 'reviews': 2},
        'reviews': [
            {'author': 'Maria S.', 'avatar': 'https://i.pravatar.cc/40?u=user8', 'text': 'Last year\'s event was a game-changer for my career. Can\'t wait!', 'rating': 5, 'replies': []},
            {'author': 'Ken O.', 'avatar': 'https://i.pravatar.cc/40?u=user9', 'text': 'The best networking event for creators in East Africa.', 'rating': 5, 'replies': []},
        ]
    },
    {
        'id': 9, 'slug': 'advanced-blender-techniques', 'title': 'Advanced Blender Techniques (Video Series)', 'asset_type': 'video-series',
        'tags': ['3D', 'Design', 'Blender'], 'details_line': '15 In-depth Lessons • Project Files Included',
        'story_snippet': "Go beyond the basics. In this series, we tackle complex topics like procedural texturing, physics simulations, and advanced lighting...",
        'price': 129.00, 'purchase_type': 'onetime', 'subscription_interval': None,
        'deliverables': ['15 HD video files', 'All .blend project files', 'Texture & asset library', 'Access to exclusive Discord channel'],
        'cover_image_url': 'https://images.unsplash.com/photo-1611669910501-99341483c6d2?ixlib=rb-4.0.3&q=85&fm=jpg&crop=entropy&cs=srgb&w=600',
        'stats': {'sales': 32, 'reviews': 1},
        'allow_multiple': True,
        'purchased': True,
        'reviews': [{'author': 'Alex T.', 'avatar': 'https://i.pravatar.cc/40?u=user15', 'text': 'Mind-blowing content. The section on geometry nodes alone is worth the price.', 'rating': 5, 'replies': []}]
    },
    {'id': 4, 'slug': 'lofi-beats-vol3', 'title': 'Lo-Fi Beats to Code To - Vol. 3', 'asset_type': 'audio-album', 'tags': ['Music', 'Focus', 'Lo-Fi'], 'details_line': '12 Royalty-Free Tracks (MP3 & WAV)', 'story_snippet': "This album was composed during late-night coding sessions, designed to create the perfect soundscape for deep, uninterrupted work...", 'price': 15.00, 'purchase_type': 'onetime', 'subscription_interval': None, 'deliverables': ['12 high-quality MP3 files', '12 uncompressed WAV files', 'Royalty-free license for streaming'], 'cover_image_url': 'https://images.unsplash.com/photo-1511379938547-c1f69419868d?ixlib=rb-4.0.3&q=85&fm=jpg&crop=entropy&cs=srgb&w=600', 'stats': {'sales': 450, 'reviews': 2}, 'reviews': [{'author': 'Chris R.', 'avatar': 'https://i.pravatar.cc/40?u=user5', 'text': 'My daily work soundtrack. Incredible vibes.', 'rating': 5, 'replies': []}, {'author': 'Sam T.', 'avatar': 'https://i.pravatar.cc/40?u=user6', 'text': 'So good, I bought Vol 1 and 2 as well!', 'rating': 4, 'replies': []}]},
    {'id': 3, 'slug': 'creator-contract-template', 'title': "The Digital Creator's Contract Template", 'asset_type': 'template', 'tags': ['Business', 'Legal'], 'details_line': 'Word, Pages & PDF Files', 'story_snippet': "After getting burned, I worked with a lawyer to create the one contract I wish I'd had from the start. Protect your work...", 'price': 49.00, 'purchase_type': 'onetime', 'subscription_interval': None, 'deliverables': ['Microsoft Word (.docx) template', 'Apple Pages (.pages) template', 'Printable PDF version', 'Guide on how to fill it out'], 'cover_image_url': 'https://images.unsplash.com/photo-1556742502-ec7c0e9f34b1?ixlib=rb-4.0.3&q=85&fm=jpg&crop=entropy&cs=srgb&w=600', 'stats': {'sales': 215, 'reviews': 1}, 'reviews': [{'author': 'Zoe P.', 'avatar': 'https://i.pravatar.cc/40?u=user4', 'text': 'Saved me thousands in legal fees. A must-have.', 'rating': 5, 'replies': []}]},
    {'id': 7, 'slug': 'sonder-magazine-4', 'title': 'Sonder - Digital Magazine Issue #4', 'asset_type': 'ebook', 'tags': ['Design', 'Architecture'], 'details_line': '120 Pages • Interactive PDF', 'story_snippet': "In this issue, we travel to the coast of Kenya to explore stunning, eco-friendly homes that blend seamlessly with nature...", 'price': 9.99, 'purchase_type': 'onetime', 'subscription_interval': None, 'deliverables': ['High-resolution interactive PDF', 'Mobile-friendly ePub version'], 'cover_image_url': 'https://images.unsplash.com/photo-1497633762265-9d179a990aa6?ixlib=rb-4.0.3&q=85&fm=jpg&crop=entropy&cs=srgb&w=600', 'stats': {'sales': 302, 'reviews': 1}, 'reviews': [{'author': 'Lena F.', 'avatar': 'https://i.pravatar.cc/40?u=user7', 'text': 'Beautifully designed magazine with inspiring content.', 'rating': 4, 'replies': []}]},
]
random.shuffle(mock_assets)
mock_purchased_assets = [asset for asset in mock_assets if asset.get('purchased', False)]