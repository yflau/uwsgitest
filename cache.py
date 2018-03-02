# uwsgi --http-socket 127.0.0.1:3031 --wsgi-file cache.py --master --processes 4 --spooler spool --cache2 name=airport,items=5000,blocksize=20,keysize=3 --cache2 name=common,items=100
#
# QA：
# - Q: Does cache protected by RWMutex? should all workers stagger refresh time？
#   A: If RWMutex, there is no need to stagger because only read operations.
# - Q: How to ensure all nodes execute the `refresh_airports` at the same time?
#   A: Don't use `timer`, use `cron` & jitter(avoid concurrent pressure to DB) instead
# - Q: how to minimize the time comsumed on `_refresh_airports_list_in_workers` to avoid throughput jitter？
#   A：- Maybe it's a bad idea to sleep random time duration, because long sleep will hang the worker.
#      - Another option is using uwsgi.lock to execute `_refresh_airports_list_in_workers` sequentially, but now all workers have entered the 
#        the funciton, lock is useless.
#      - Register signal handler for each worker, signal each worker after some time sequentially, acually there is no need to stagger for one
#        node if nodes have already staggered.
# - Q: what about use lmdb instead uwsgi cache?
#   A: Maybe lmdb can save lots of memory.

import time
import uwsgi
from uwsgidecorators import *
from atomicwrites import atomic_write

AIRPORTS = {}    # it's better load all data from here, thus all forked worker have a basis to work

def init():
    if settings.CONFIG_MODE:
        AIRPORTS = json.loads(open(settings.CONFIG_FILE).read())
    else: # dummy
        AIRPORTS = {
            "bjz" : "Beijing T3 internatianl airport", # Warning: fail to set because excced 20 bytes, but will not throw exc, get will be None
            "tjw" : "Tianjin T1 airport"
        }

class settings:
    CONFIG_MODE = "LOCAL_FILE" # "DATABASE", "DIAMOND"?
    CONFIG_FILE = "/home/admin/xxx/config.json"

def _refresh_worker(signum):
    if not uwsgi.cache_exists("airport_codes", "common"):
        return
    codes = uwsgi.cache_get("airport_codes", "common")
    codes = [codes[i:i+3] for i in xrange(0, len(codes),3)]
    for e in codes:
        AIRPORTS[e] = uwsgi.cache_get(e, "airport")

@postfork
def refresh_worker():   # because AIRPORTS of master is empty or dated(even if loaded initially)
    _refresh_worker(None)

uwsgi.register_signal(17, "workers", _refresh_worker)
# for i,k in enumerate(uwsgi.workers()):  # avoid throughput jitter in one node
#     uwsgi.register_signal(17+i, "worker%s" % i, _refresh_airports_list_in_workers)

@timer(30, target='spooler')
def refresh_shared(*args):
    if settings.CONFIG_MODE = "LOCAL_FILE":
        return
    time.sleep(random.randrange(3, 8))  # jitter, working in spooler, so time.sleep is OK!!!
    airports = {
        "bjz" : "Beijing T3 internatianl airport", # Warning: fail to set because excced 20 bytes, but will not throw exc, get will be None
        "tjw" : "Tianjin T1 airport"
    }
    
    # backup current available to local file used to disaster recovery
    codes = uwsgi.cache_get("airport_codes", "common")
    codes = [codes[i:i+3] for i in xrange(0, len(codes),3)]
    for e in codes:
        AIRPORTS[e] = uwsgi.cache_get(e, "airport")
    with atomic_write(settings.CONFIG_FILE, overwrite=True) as f:
        f.write(json.dumps(AIRPORTS))
    
    ks = ""
    for k,v in airports.items():
        ks += k
        uwsgi.cache_set(k, v, 0, "airport")   # it's better to pack the `v` use struct to a fixed size string to fit the blocksize
    uwsgi.cache_set("airport_codes", ks, 0, "common")  # TODO: should check length of ks less than 64K, or should truncate to 64K and send warning email
    uwsgi.signal(17)
    # for i,k in enumerate(uwsgi.workers()):    # avoid throughput jitter in one node
    #     uwsgi.signal(17+i)

def application(environ, start_response):
    if environ['PATH_INFO'].startswith('/favicon.ico'):
        start_response('404 Not Found', [('Content-Type', 'text/html')])
    else:
        start_response('200 OK', [('Content-Type', 'text/html')])
        if not AIRPORTS:
            yield "No airports"
        for k,v in AIRPORTS.items():
            yield "code: %s: %s<br/>" % (k, v)
