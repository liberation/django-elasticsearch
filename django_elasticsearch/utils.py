import collections


def nested_update(d, u):
    for k, v in u.iteritems():
        if isinstance(v, collections.Mapping):
            r = nested_update(d.get(k, {}), v)
            d[k] = r
        elif isinstance(v, collections.Iterable):
            try:
                d[k].extend(u[k])
            except KeyError:
                d[k] = u[k]
        else:
            d[k] = u[k]
    return d


def dict_depth(d, depth=0):
    if not isinstance(d, dict) or not d:
        return depth
    return max(dict_depth(v, depth + 1)
               for k, v in d.iteritems())
