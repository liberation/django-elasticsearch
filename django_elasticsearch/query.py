from django.conf import settings
from django.db.models import Model
from django.db.models.query import QuerySet
from django.db.models.query import REPR_OUTPUT_SIZE

from django_elasticsearch.client import es_client
from django_elasticsearch.utils import nested_update


class EsQueryset(QuerySet):
    """
    Fake Queryset that is supposed to act somewhat like a django Queryset.
    """
    MODE_SEARCH = 1
    MODE_MLT = 2

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
            mapping = self.model.es.get_mapping()

            for field, value in self.filters.items():
                try:
                    value = value.lower()
                except AttributeError:
                    pass
                try:
                    field, operator = field.split('__')
                except ValueError:  # could not split
                    # this is also django's default lookup type
                    operator = 'exact'

                try:
                    is_nested = 'properties' in mapping[field]
                except KeyError:
                    is_nested = False

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

                nested_update(search['filter'], filtr)

            body['query'] = {'filtered': search}
        else:
            body = search

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
            body['sort'] = [{f: "asc"} if f[0] != '-' else {f[1:]: "desc"}
                            for f in self.ordering] + ["_score"]

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
        self._result_cache = [e['_source'] for e in r['hits']['hits']]
        self._max_score = r['hits']['max_score']
        self._total = r['hits']['total']
        return self

    def search(self, query):
        self.query(query)
        return self

    def facet(self, fields, limit=None, use_globals=True):
        # TODO: bench global facets !!
        self.facets_fields = fields
        self.facets_limit = limit
        self.global_facets = use_globals
        return self

    def suggest(self, fields, limit=None):
        self.suggest_fields = fields
        self.suggest_limit = limit
        return self

    def query(self, query):
        if self.is_evaluated:
            # empty the result cache
            self._result_cache = []
        self._query = query
        return self

    def order_by(self, *fields):
        if self.is_evaluated:
            # empty the result cache
            self._result_cache = []
        self.ordering = fields
        return self

    def filter(self, **kwargs):
        if self.is_evaluated:
            # empty the result cache
            self._result_cache = []
        self.filters.update(kwargs)
        return self

    def exclude(self, **kwargs):
        if self.is_evaluated:
            # empty the result cache
            self._result_cache = []

        filters = {}
        # TODO: not __contains, not __range
        for field, value in kwargs.items():
            try:
                field, operator = field.split('__')
            except ValueError:  # could not split
                # this is also django's default lookup type
                operator = 'exact'

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
                filters[field] = not value
            else:
                raise NotImplementedError("{0} is not a valid *exclude* lookup type.".format(operator))

        self.filters.update(filters)
        return self

    ## getters
    def all(self):
        self.search('')
        return self

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
