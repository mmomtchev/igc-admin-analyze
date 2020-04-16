#!/usr/bin/python3

import os
import argparse
from aerofiles.igc import Reader
import json
from shapely.geometry import shape, Point, box
from rtree import index as rindex
import threading
from concurrent.futures import ThreadPoolExecutor
import copy
import multiprocessing

# Find if there are 0, 1 or more administrative divisions
# intersecting the bounding box
# This is the time-critical function
# and it has a per-thread deep copy
def get_two_intersecting_polygons(polygons, box):
    r = []
    for i in range(len(polygons)):
        p = polygons[i]
        # I refuse to believe that Python does not have a reentrant geometry
        # library in 2020, forcing me to do this, but it seems to be the case
        if threading.get_ident() not in p.keys():
            p[threading.get_ident()] = copy.deepcopy(p['shape'])
        if p[threading.get_ident()].intersects(box):
            r.append(i)
        if len(r) > 2:
            break
    return r

# slice an array into chunks
def chunks(l, n):
    for i in range(0, len(l), n):
        yield l[i:i + n]

rcache = None
rcacheLock = threading.Lock()

def get_intersecting_polygon_with_rtree_cache(polygons, point):
    rcacheLock.acquire()
    p = list(rcache.intersection((point.x, point.y)))
    rcacheLock.release()
    if len(p) > 0:
        return p[0]
    
    # Start with the world, divide by 4 at each step and continue with the
    # subrectangle bbox containing the matched point until the bbox contains
    # only one administrative division 
    left, bottom, right, top = (-180, -90, 180, 90)
    while len(get_two_intersecting_polygons(polygons, box(left, bottom, right, top))) > 1:
        middlex = left + (right - left) / 2
        middley = bottom + (top - bottom) / 2
        if (point.x > middlex):
            left = middlex
        else:
            right = middlex
        if (point.y > middley):
            bottom = middley
        else:
            top = middley

    # Keep track of negative responses too, they can be very slow
    p = get_two_intersecting_polygons(polygons, box(left, bottom, right, top))
    if len(p) < 1:
        rcacheLock.acquire()
        # Maybe another thread already found this bbox
        if (len(list(rcache.intersection((point.x, point.y)))) == 0):
            rcache.insert(-1, (left, bottom, right, top))
        rcacheLock.release()
        return -1

    rcacheLock.acquire()
    # Maybe another thread already found this bbox
    if (len(list(rcache.intersection((point.x, point.y)))) == 0):
        rcache.insert(p[0], (left, bottom, right, top))
    rcacheLock.release()
    return p[0]


# The thread function
progress = 0
def process_gps_points(gps_points):
    global progress, args
    for record in gps_points:
        rcacheLock.acquire()
        if args['verbose'] and progress % 100 == 0:
            print('.', end='', flush=True)
        progress += 1
        rcacheLock.release()

        lat = record['lat']
        lon = record['lon']
        point = Point(lon, lat)

        record['polygon'] = get_intersecting_polygon_with_rtree_cache(
            polygons, point)
    return


ap = argparse.ArgumentParser()
ap.add_argument('-i', '--igc', required=True,
                help='IGC flight data')
ap.add_argument('-a', '--admin', required=True,
                help='Administrative boundaries in GeoJSON format')
ap.add_argument('-q', '--quiet', required=False, action='store_true',
                help='Quiet')
ap.add_argument('-v', '--verbose', required=False, action='store_true',
                help='Verbose')
ap.add_argument('-s', '--selected', required=False,
                help='Selected areas, ID list')
args = vars(ap.parse_args())

basedir = os.path.dirname(os.path.realpath(__file__))

if args['verbose']:
    print('Reading ' + args['igc'])
with open(args['igc'], 'r') as fd_igc:
    igc = Reader().read(fd_igc)
gps_fixes = igc['fix_records'][1]

if args['verbose']:
    print('Reading ' + args['admin'] + '.geojson')
with open(os.path.join(basedir, 'data', args['admin'] + '.geojson')) as fd_admin:
    admin = json.load(fd_admin)

os.makedirs(os.path.join(basedir, 'temp'), 0o755, exist_ok=True)
try:
    rcache = rindex.Rtree(os.path.join(basedir, 'temp', args['admin']))
except:
    print('Deleting corrupted ' + args['admin'] + '.dat')
    os.unlink(os.path.join(basedir, 'temp', args['admin'] + '.dat'))
    os.unlink(os.path.join(basedir, 'temp', args['admin'] + '.idx'))
    rcache = rindex.Rtree(os.path.join('temp', args['admin']))

polygons = []
if args['verbose']:
    print('Parsing admin boundaries', end='', flush=True)
for feature in admin['features']:
    if 'id' not in feature['properties'].keys():
        feature['properties']['id'] = None
    if 'alltags' not in feature['properties'].keys():
        feature['properties']['alltags'] = { 'ref': None }
    polygons.append({
        'shape': shape(feature['geometry']),
        'properties': feature['properties'],
        'fixes': 0
    })
    if args['verbose']:
        print('.', end='', flush=True)

if args['verbose']:
    print('\nProcessing fixes (using {} cores)'.format(
        multiprocessing.cpu_count()), end='', flush=True)
running_threads = []
with ThreadPoolExecutor(max_workers=multiprocessing.cpu_count()) as executor:
    executor.map(process_gps_points, chunks(gps_fixes, 2000))
if args['verbose']:
    print('', flush=True)

last_polygon = None
invalid = 0
launch = None
land = None
for record in gps_fixes:
    p = record['polygon']
    if p >= 0:
        if last_polygon is None or last_polygon != p:
            if args['verbose']:
                print('Entered {} at {} at {:.2f}°:{:.2f}°'.format(
                    polygons[p]['properties']['name'], record['time'], record['lat'], record['lon']))
            last_polygon = p
        polygons[p]['fixes'] += 1
    else:
        if last_polygon != -1 and args['verbose']:
            print('Entered INVALID AREA at {} at {:.2f}°:{:.2f}°'.format(
                record['time'], record['lat'], record['lon']))
        last_polygon = -1
        invalid += 1
    if launch is None:
        launch = last_polygon

land = last_polygon

if args['verbose']:
    print('')
total = len(igc['fix_records'][1])
selected = 0
if args['selected'] is not None:
    list_selected = args['selected'].split(',')

for t in [ { 'k': 'Launch', 'v': launch }, { 'k': 'Land', 'v': land} ]:
    if not args['quiet'] and launch is not None:
        if (t['v'] != -1):
            print('{} in {}'.format(
                t['k'], polygons[t['v']]['properties']['name']))
        else:
            print('{} in INVALID AREA'.format(t['k']))

for p in polygons:
    if p['fixes'] > 0:
        if not args['quiet']:
            print('{:.2f}% ({} of {}) in {}'.format(
                p['fixes'] * 100 / total, p['fixes'], total, p['properties']['name']), end='')
        if args['selected'] is not None and (p['properties']['name'] in list_selected or p['properties']['id'] in list_selected or p['properties']['alltags']['ref'] in list_selected):
            selected += p['fixes']
            if not args['quiet']:
                print(' *', end='')
        if not args['quiet']:
            print('')
if invalid > 0 and not args['quiet']:
    print('{:.2f}% ({} of {}) INVALID AREA'.format(
        invalid * 100 / total, invalid, total))
if args['selected'] is not None:
    if not args['quiet']:
        print('{:.2f}% ({} of {}) in selected areas'.format(
            selected * 100 / total, selected, total))
    else:
        print('{:.2f}%'.format(selected * 100 / total))
