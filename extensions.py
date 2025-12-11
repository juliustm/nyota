from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Initialize Limiter with key_func=get_remote_address to rate limit by IP
limiter = Limiter(key_func=get_remote_address)
