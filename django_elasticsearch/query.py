import copy

from django.conf import settings
from django.db.models import Model
from django.db.models.query import QuerySet
from django.db.models.query import REPR_OUTPUT_SIZE

from django_elasticsearch.client import es_client
from django_elasticsearch.utils import nested_update

from helpers import haversine

class EsQueryset(QuerySet):
    """
    Fake Queryset that is supposed to act somewhat like a django Queryset.
    """
    MODE_SEARCH = 1
    MODE_MLT = 2
    SCORE_FUNCTIONS = []

    #geo
    lat = None
    lng = None
    unit = "mi"

    def __init__(self, model, fuzziness=None):
        self.model = model
        self.index = model.es.index
        self.doc_type = model.es.doc_type

        # config
        self.mode = self.MODE_SEARCH
        self.mlt_kwargs = None
        self.filters = {}
        self.facets_fields = None
        self.suggest_fields = None



        # model.Elasticsearch.ordering -> model._meta.ordering -> _score
        if hasattr(self.model.Elasticsearch, 'ordering'):
            self.ordering = self.model.Elasticsearch.ordering
        else:
            self.ordering = getattr(self.model._meta, 'ordering', None)
        self.fuzziness = fuzziness
        self.ndx = None
        self._query = ''

        self._start = 0
        self._stop = None

        # results
        self._suggestions = None
        self._facets = None
        self._result_cache = []  # store
        self._total = None

    def __getstate__(self):
        obj_dict = self.__dict__.copy()
        return obj_dict

    def __deepcopy__(self, memo):
        """
        Deep copy of a QuerySet doesn't populate the cache
        """
        obj = self.__class__(self.model)
        for k, v in self.__dict__.items():
            if k not in ['_result_cache', '_facets', '_suggestions', '_total']:
                obj.__dict__[k] = copy.deepcopy(v, memo)
        return obj

    def _clone(self):
        # copy everything but the results cache
        clone = copy.deepcopy(self)  # deepcopy because .filters is immutable
        clone._suggestions = None
        clone._facets = None
        clone._result_cache = []  # store
        clone._total = None
        return clone

    def __iter__(self):
        self.do_search()
        for r in self._result_cache:
            yield r

    def __repr__(self):
        data = list(self[:REPR_OUTPUT_SIZE + 1])
        if len(data) > REPR_OUTPUT_SIZE:
            data[-1] = "...(remaining elements truncated)..."
        return repr(data)

    def __getitem__(self, ndx):
        if ndx != self.ndx:
            self._result_cache = []

        if self.is_evaluated:
            return self._result_cache

        self.ndx = ndx

        if type(ndx) is slice:
            self._start = ndx.start or 0  # in case it is None because [:X]
            self._stop = ndx.stop
        elif type(ndx) is int:
            self._start = ndx
            self._stop = ndx + 1

        self.do_search()
        if type(ndx) is slice:
            return self._result_cache
        elif type(ndx) is int:
            return self._result_cache[0]

    def __contains__(self, val):
        self.do_search()
        return val in self._result_cache

    def __and__(self, other):
        raise NotImplementedError

    def __or__(self, other):
        raise NotImplementedError

    def __nonzero__(self):
        self.count()
        return self._total != 0

    def __len__(self):
        # if we pass a body without a query, elasticsearch complains
        if self._total:
            return self._total
        r = es_client.count(
            index=self.index,
            doc_type=self.doc_type,
            body=self.make_search_body() or None)
        self._total = r['count']
        return self._total

    def make_search_body(self):
        body = {}
        search = {}

        if self.fuzziness is None:  # beware, could be 0
            fuzziness = getattr(settings, 'ELASTICSEARCH_FUZZINESS', 0.5)
        else:
            fuzziness = self.fuzziness

        if self._query:
            search['query'] = {
                'match': {
                    '_all': {
                        'query': self._query,
                        'fuzziness': fuzziness
                    }
                },
            }

        if self.filters:
            # TODO: should we add _cache = true ?!
            search['filter'] = {}
            # search['query'] = {}
            mapping = self.model.es.get_mapping()
            for field, value in self.filters.items():

                if (field in mapping and 'index' in mapping[field]
                    and mapping[field]['index'] == 'not_analyzed'):
                  # we dont want to lowercase an un-analyzed term search
                  pass
                else:
                  try:
                      value = value.lower()
                  except AttributeError:
                      pass

                field, operator = self.sanitize_lookup(field)

                try:
                    is_nested = 'properties' in mapping[field]
                except KeyError:
                    is_nested = False
                try:
                  is_geo = 'type' in mapping[field] and mapping[field]['type'] == 'geo_point'
                except KeyError:
                  is_geo = False


                field_name = is_nested and field + ".id" or field
                if is_nested and isinstance(value, Model):
                    value = value.id

                if operator == 'exact':
                    filtr = {'bool': {'must': [{'term': {field_name: value}}]}}

                elif operator == 'not':
                    filtr = {'bool': {'must_not': [{'term': {field_name: value}}]}}

                elif operator in ['should', 'should_not']:
                    filtr = {'bool': {operator: [{'term': {field_name: value}}]}}

                elif operator == 'contains':
                    filtr = {'query': {'match': {field_name: {'query': value}}}}

                elif operator in ['gt', 'gte', 'lt', 'lte']:
                    filtr = {'range': {field_name: {operator: value}}}

                elif operator == 'range':
                    filtr = {'range': {field_name: {
                        'gte': value[0],
                        'lte': value[1]}}}

                elif operator == 'isnull':
                    if value:
                        filtr = {'missing': {'field': field_name}}
                    else:
                        filtr = {'exists': {'field': field_name}}

                else:
                    filtr = {'bool': {'must': [{'term': {
                        field_name + '.' + operator: value}}]}}
                if is_geo:
                  if operator == 'lat':
                    filtr = {'geo_distance': {field_name: {'lat': value}}}
                    self.lat = value
                  elif operator == 'lon':
                    filtr = {'geo_distance': {field_name: {'lon': value}}}
                    self.lng = value
                  elif operator == 'distance':
                    filtr = {'geo_distance': {'distance': value}}
                    self.distance = value
                nested_update(search['filter'], filtr) # geo_distance only works as filter

            functions = False
            for k, v in search['filter'].iteritems():
              # right now only one geo_distance filter to score on is supported
              if k == 'geo_distance':
                self.geo_field_name = (key for key in v.keys()
                              if key != 'distance').next()
                self.geo_field = v[self.geo_field_name]

                functions = [{
                  "gauss": {self.geo_field_name: {
                    "origin": self.geo_field,
                    "scale": "20mi",
                    # "offset": "2mi"
                  }
                  }
                }]
                break

            if functions:
              # todo, sort by score first then geo?... this is only needed to return distance for each result

              geo = copy.copy(search['filter']['geo_distance'])

              if 'bool' in search['filter']:
                if 'must' not in search['filter']['bool']:
                  search['filter']['bool']['must'] = []
                search['filter']['bool']['must'].append({'geo_distance':geo})
                del search['filter']['geo_distance']


              body['query'] = {
                'function_score': {
                  'query':{
                    'filtered': search},
                  'functions': functions
                  }
              }


              # body['sort'] = [
              #
              #   # {'_score': {'order': 'desc'}},
              #   {
              #     '_geo_distance': {
              #       self.geo_field_name: self.geo_field,
              #       'order': 'asc',
              #       'unit': 'mi'
              #     }
              #   }
              # ]

            else:
              body['query'] = {'filtered': search}

        else:
            body = search
        print body
        return body

    @property
    def is_evaluated(self):
        return bool(self._result_cache)

    @property
    def response(self):
        if not self.is_evaluated:
            raise AttributeError(u"EsQueryset must be evaluated before accessing elasticsearch's response.")
        else:
            return self._response

    def do_search(self, extra_body=None):
        if self.is_evaluated:
            return self._result_cache
        print "do_search"
        body = self.make_search_body()

        if self.facets_fields:
            aggs = dict([
                (field, {'terms':
                        {'field': field}})
                for field in self.facets_fields
            ])
            if self.facets_limit:
                aggs[field]['terms']['size'] = self.facets_limit

            if self.global_facets:
                aggs = {'global_count': {'global': {}, 'aggs': aggs}}

            body['aggs'] = aggs

        if self.suggest_fields:
            suggest = {}
            for field_name in self.suggest_fields:
                suggest[field_name] = {"text": self._query,
                                       "term": {"field": field_name}}
                if self.suggest_limit:
                    suggest[field_name]["text"]["term"]["size"] = self.suggest_limit
            body['suggest'] = suggest

        if self.ordering:
            if not len(body.get('sort', [])):
              body['sort'] = []
            body['sort'].extend([{f: "asc"} if f[0] != '-' else {f[1:]: "desc"}
                            for f in self.ordering] + ["_score"])


        search_params = {
            'index': self.index,
            'doc_type': self.doc_type
        }
        if self._start:
            search_params['from'] = self._start
        if self._stop:
            search_params['size'] = self._stop - self._start

        search_params['body'] = body
        self._body = body
        # print search_params
        # print body

        if self.mode == self.MODE_MLT:
            # change include's defaults to False
            # search_params['include'] = self.mlt_kwargs.pop('include', False)
            # update search params names
            for param in ['type', 'indices', 'types', 'scroll', 'size', 'from']:
                if param in search_params:
                    search_params['search_{0}'.format(param)] = search_params.pop(param)
            search_params.update(self.mlt_kwargs)
            r = es_client.mlt(**search_params)
        else:
            if 'from' in search_params:
                search_params['from_'] = search_params.pop('from')
            r = es_client.search(**search_params)

        self._response = r
        if self.facets_fields:
            if self.global_facets:
                try:
                    self._facets = r['aggregations']['global_count']
                except KeyError:
                    self._facets = {}
            else:
                self._facets = r['aggregations']

        self._suggestions = r.get('suggest')
        if self.lat is not None and self.lng is not None:
          for e in r['hits']['hits']:
            e['_source']['distance'] = haversine(self.lng, self.lat,
                                                 e['_source']['lng'], e['_source']['lat'])
        self._result_cache = [e['_source'] for e in r['hits']['hits']]
        self._max_score = r['hits']['max_score']
        self._total = r['hits']['total']
        return self

    def query(self, query):
        clone = self._clone()
        clone._query = query
        return clone

    def facet(self, fields, limit=None, use_globals=True):
        # TODO: bench global facets !!
        clone = self._clone()
        clone.facets_fields = fields
        clone.facets_limit = limit
        clone.global_facets = use_globals
        return clone

    def suggest(self, fields, limit=None):
        clone = self._clone()
        clone.suggest_fields = fields
        clone.suggest_limit = limit
        return clone

    def order_by(self, *fields):
        clone = self._clone()
        clone.ordering = fields
        return clone

    def filter(self, **kwargs):
        clone = self._clone()
        clone.filters.update(kwargs)
        return clone

    def sanitize_lookup(self, lookup):
        valid_operators = ['exact', 'not', 'should', 'should_not', 'range','gt', 'lt', 'gte', 'lte', 'contains', 'isnull', 'lat', 'lon', 'distance']
        words = lookup.split('__')
        fields = [word for word in words if word not in valid_operators]
        # this is also django's default lookup type
        operator = 'exact'
        if words[-1] in valid_operators:
            operator = words[-1]
        return '.'.join(fields), operator

    def exclude(self, **kwargs):
        clone = self._clone()

        filters = {}
        # TODO: not __contains, not __range
        for lookup, value in kwargs.items():
            field, operator = self.sanitize_lookup(lookup)

            if operator == 'exact':
                filters['{0}__not'.format(field)] = value
            elif operator == 'not':
                filters[field] = value
            elif operator == 'should':
                filters['{0}__should_not'.format(field)] = value
            elif operator in ['gt', 'gte', 'lt', 'lte']:
                inverse_map = {'gt': 'lte', 'gte': 'lt', 'lt': 'gte', 'lte': 'gt'}
                filters['{0}__{1}'.format(field, inverse_map[operator])] = value
            elif operator == 'isnull':
                filters[lookup] = not value
            else:
                raise NotImplementedError("{0} is not a valid *exclude* lookup type.".format(operator))

        clone.filters.update(filters)
        return clone

    ## getters
    def all(self):
        clone = self._clone()
        return clone

    def get(self, **kwargs):
        pk = kwargs.get('pk', None) or kwargs.get('id', None)

        if pk is None:
            # maybe it's in a filter, like in django.views.generic.detail
            pk = self.filters.get('pk', None) or self.filters.get('id', None)

        if pk is None:
            raise AttributeError("EsQueryset.get needs to get passed a 'pk' or 'id' parameter.")

        r = es_client.get(index=self.index,
                          doc_type=self.doc_type,
                          id=pk)
        self._response = r
        return r['_source']

    def mlt(self, id, **kwargs):
        self.mode = self.MODE_MLT
        self.mlt_kwargs = kwargs
        self.mlt_kwargs['id'] = id
        return self

    def complete(self, field_name, query):
        resp = es_client.suggest(index=self.index,
                                 body={field_name: {
                                     "text": query,
                                     "completion": {
                                         "field": field_name,
                                         # stick to fuzziness settings
                                         "fuzzy" : {}
                                     }}})

        return [r['text'] for r in resp[field_name][0]['options']]

    def update(self):
        raise NotImplementedError("Db operational methods have been "
                                  "disabled for Elasticsearch Querysets.")

    def delete(self):
        raise NotImplementedError("Db operational methods have been "
                                  "disabled for Elasticsearch Querysets.")

    @property
    def facets(self):
        self.do_search()
        return self._facets

    @property
    def suggestions(self):
        self.do_search()
        return self._suggestions

    def count(self):
        return self.__len__()

    def deserialize(self):
        return self.model.es.deserialize(self)
