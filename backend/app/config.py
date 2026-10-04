"""Required service configuration; no runtime profile or local fallback."""
import os
import math
from urllib.parse import urlparse
from sqlalchemy.engine import make_url

REQUIRED = ('DATABASE_URL', 'SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY', 'MISTRAL_API_KEY')

def settings(environ=None):
    source = os.environ if environ is None else environ
    if source.get('APP_MODE'):
        raise RuntimeError('APP_MODE has been removed. Unset it and configure Supabase and Mistral.')
    missing = [name for name in REQUIRED if not source.get(name, '').strip()]
    if missing:
        raise RuntimeError('Missing required configuration: ' + ', '.join(missing))
    values = {name: source[name] for name in REQUIRED}
    raw_url = values['DATABASE_URL']
    if raw_url.startswith('postgres://'):
        raw_url = raw_url.replace('postgres://', 'postgresql+psycopg://', 1)
    elif raw_url.startswith('postgresql://'):
        raw_url = raw_url.replace('postgresql://', 'postgresql+psycopg://', 1)
    try:
        database_url = make_url(raw_url)
    except Exception:
        raise RuntimeError('DATABASE_URL must be a valid Supabase Postgres connection URL.') from None
    if database_url.drivername != 'postgresql+psycopg' or not database_url.host or not database_url.database:
        raise RuntimeError('DATABASE_URL must point to Supabase Postgres using the psycopg driver.')
    parsed = urlparse(values['SUPABASE_URL'])
    if not parsed.hostname or parsed.username or parsed.password or not (parsed.scheme == 'https' or (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1'))):
        raise RuntimeError('SUPABASE_URL must be an HTTPS service URL or a local Supabase HTTP endpoint.')
    try:
        pool_size=int(source.get('DB_POOL_SIZE','2'))
        pool_timeout=float(source.get('DB_POOL_TIMEOUT','5'))
    except (TypeError,ValueError,OverflowError):
        raise RuntimeError('DB_POOL_SIZE must be an integer from 1 to 5; DB_POOL_TIMEOUT must be a finite number greater than 0 and at most 30 seconds.') from None
    if not 1<=pool_size<=5 or not math.isfinite(pool_timeout) or not 0<pool_timeout<=30:
        raise RuntimeError('DB_POOL_SIZE must be an integer from 1 to 5; DB_POOL_TIMEOUT must be a finite number greater than 0 and at most 30 seconds.')
    values['DB_POOL_SIZE']=pool_size
    values['DB_POOL_TIMEOUT']=pool_timeout
    values['DATABASE_URL'] = raw_url
    return values
