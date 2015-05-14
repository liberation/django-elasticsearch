import gc


# taken from https://djangosnippets.org/snippets/1949/
def queryset_iterator(queryset, chunksize=2000):
    '''''
    Iterate over a Django Queryset ordered by the primary key

    This method loads a maximum of chunksize (default: 1000) rows in it's
    memory at the same time while django normally would load all rows in it's
    memory. Using the iterator() method only causes it to not preload all the
    classes.

    Note that the implementation of the iterator does not support ordered query sets.
    '''
    pk = 0
    last_pk = queryset.order_by('-pk')[0].pk
    queryset = queryset.order_by('pk')
    while pk < last_pk:
        for row in queryset.filter(pk__gt=pk)[:chunksize]:
            pk = row.pk
            yield row
            if pk % chunksize == 0:
              print "on pk {}".format(pk)
        #gc.collect()


def queryset_batcher(queryset, chunksize=2000):
    '''''
    Iterator that yields lists of django models in `chunksize` chunks
    '''
    pk = 0
    last_pk = queryset.order_by('-pk')[0].pk
    queryset = queryset.order_by('pk')
    while pk < last_pk:
        chunk = list(queryset.filter(pk__gt=pk)[:chunksize])
        pk = chunk[-1].pk
        yield chunk
        print "on pk {}".format(pk)

from math import radians, cos, sin, asin, sqrt
def haversine(lon1, lat1, lon2, lat2, unit="mi"):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    """
    # convert decimal degrees to radians
    lon1, lat1, lon2, lat2 = map(radians,map(float, [lon1, lat1, lon2, lat2]))
    # haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    if unit == "km":
        distance = 6367 * c
    elif unit == "mi":
        distance = 3956 * c
    else:
      raise("invalid distance unit")
    return distance


