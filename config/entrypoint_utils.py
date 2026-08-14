import os
from urllib.parse import urlparse


def resolve_database_host_and_port():
    """
    Resolve database host and port from DATABASE_URL or individual env vars.
    Supports Railway's reference variables like ${{service.VAR}}
    """
    database_url = os.getenv('DATABASE_URL', '').strip()
    
    # Skip resolution if DATABASE_URL is a Railway reference variable (not yet expanded)
    if database_url.startswith('${{') and database_url.endswith('}}'):
        # Fall back to individual env vars (Railway's standard postgres variables)
        host = os.getenv('PGHOST', os.getenv('POSTGRES_HOST', 'db'))
        port = int(os.getenv('PGPORT', os.getenv('POSTGRES_PORT', '5432')))
        return host, port
    
    # Try parsing DATABASE_URL if it exists and is valid
    parsed = urlparse(database_url) if database_url else None
    if parsed is not None and parsed.scheme in {'postgres', 'postgresql', 'postgresql+psycopg', 'postgresql+psycopg2'}:
        host = parsed.hostname or os.getenv('PGHOST', os.getenv('POSTGRES_HOST', 'db'))
        port = parsed.port or int(os.getenv('PGPORT', os.getenv('POSTGRES_PORT', '5432')))
        return host, port
    
    # Fall back to individual env vars (Railway's standard postgres variables)
    host = os.getenv('PGHOST', os.getenv('POSTGRES_HOST', 'db'))
    port = int(os.getenv('PGPORT', os.getenv('POSTGRES_PORT', '5432')))
    return host, port

