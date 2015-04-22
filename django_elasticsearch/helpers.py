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



