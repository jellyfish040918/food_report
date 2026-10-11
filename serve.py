"""Single-instance local/SaaS API entrypoint. Production sits behind HTTPS proxy."""
import argparse
import os
import uvicorn
from backend.config import Settings

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=4175);parser.add_argument('--host',default='127.0.0.1');args=parser.parse_args()
    settings=Settings();settings.validate()
    if not settings.production and args.host not in ('127.0.0.1','localhost','::1'):parser.error('Development demo may only bind to loopback. Set FLAVO_ENV=production for public hosting.')
    uvicorn.run('backend.app:app',host=args.host,port=args.port,workers=1,proxy_headers=settings.production,forwarded_allow_ips=os.getenv('FORWARDED_ALLOW_IPS','127.0.0.1'),limit_concurrency=100,timeout_keep_alive=5)
