# uwsgi --http-socket 127.0.0.1:3031 --wsgi-file cache.py --master --processes 4 --spooler spool --cache2 name=airport,items=5000,blocksize=20,keysize=3 --cache2 name=common,items=100
#
# questions：
# - does cache protected by RWMutex? should all workers stagger refresh time？
# - how to ensure all nodes execute the `refresh_airports` at the same time?
# - minimize the time comsumed on `_refresh_airports_list_in_workers` to handle the normal reqeusts


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
        "bjz" : "Beijing T3 internatianl airport", # Warning: fail to set because excced 20 bytes, but will not throw exc, get will be None
        "tjw" : "Tianjin T1 airport"
    }
    ks = ""
    for k,v in airports.items():
        ks += k
        uwsgi.cache_set(k, v, 0, "airport")   # it's better to pack the `v` use struct to a fixed size string to fit the blocksize
    uwsgi.cache_set("airport_codes", ks, 0, "common")  # TODO: should check length of ks less than 64K, or should truncate to 64K and send warning email
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
