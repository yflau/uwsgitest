# uwsgi --http-socket 127.0.0.1:3031 --wsgi-file cache.py --master --processes 4 --spooler spool --cache2 name=airport,items=5000,blocksize=20,keysize=3 --cache2 name=common,items=100

import uwsgi
from uwsgidecorators import *

AIRPORTS = {}

def _refresh_airports_list_in_workers(signum):
    if not uwsgi.cache_exists("airport_codes", "common"):
        return
    codes = uwsgi.cache_get("airport_codes", "common")
    codes = [codes[i:i+3] for i in xrange(0, len(codes),3)]
    for e in codes:
        AIRPORTS[e] = uwsgi.cache_get(e, "airport")

@postfork
def refresh_airports_list_in_workers():   # because AIRPORTS of master is empty or dated(even if loaded initially)
    _refresh_airports_list_in_workers(None)

uwsgi.register_signal(17, "workers", _refresh_airports_list_in_workers)

@timer(30, target='spooler')
def refresh_airports(*args):
    airports = {
        "bjz" : "Beijing T3 internatianl airport", # Warning: fail to set because excced 20 bytes, but will not throw exc, got will be None
        "tjw" : "Tianjin T1 airport"
    }
    ks = ""
    for k,v in airports.items():
        ks += k
        uwsgi.cache_set(k, v, 0, "airport")
    uwsgi.cache_set("airport_codes", ks, 0, "common")
    uwsgi.signal(17)

def application(environ, start_response):
    if environ['PATH_INFO'].startswith('/favicon.ico'):
        start_response('404 Not Found', [('Content-Type', 'text/html')])
    else:
        start_response('200 OK', [('Content-Type', 'text/html')])
        if not AIRPORTS:
            yield "No airports"
        for k,v in AIRPORTS.items():
            yield "code: %s: %s<br/>" % (k, v)
