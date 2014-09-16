# -*- coding: utf-8 -*-
from django.conf import settings
from django.db.models import FieldDoesNotExist
from django.db.models.query import REPR_OUTPUT_SIZE

from elasticsearch import Elasticsearch


ELASTICSEARCH_URL = getattr(settings,
                            'ELASTICSEARCH_URL',
                            'http://localhost:9200')

# TODO: would it be better to give this client a dedicated thread ?!
# and not instanciate it each request ?
es = Elasticsearch(ELASTICSEARCH_URL)


# Note: we use long/double because different db backends
# could store different sizes of numerics ?
# Note: everything else is mapped to a string
ELASTICSEARCH_FIELD_MAP = {
    u'AutoField': 'long',
    u'BigIntegerField': 'long',
    u'BinaryField': 'binary',
    u'BooleanField': 'boolean',
    # both defaults to 'dateOptionalTime'
    u'DateField': 'date',
    u'DateTimeField': 'date',
    u'FloatField': 'double',
    u'IntegerField': 'long',
    u'PositiveIntegerField': 'long',
    u'PositiveSmallIntegerField': 'short',
    u'SmallIntegerField': 'short'
}


class EsQueryset(object):
    """
    Fake Queryset that is supposed to act somewhat like a django Queryset.
    """
    def __init__(self, model):
        self.model = model
        self.facets_fields = None
        self.suggest_fields = None
        self._ordering = None  # default to 'score'
        self._ndx = None
        self._start = 0
        self._stop = None
        self._query = None
        self._filters = []
        self._suggestions = None
        self._facets = None
        self._results = []  # store
        self._total = None

    def __iter__(self):
        self.do_search()
        for r in self._results:
            yield r

    def __repr__(self):
        data = list(self[:REPR_OUTPUT_SIZE + 1])
        if len(data) > REPR_OUTPUT_SIZE:
            data[-1] = "...(remaining elements truncated)..."
        return repr(data)

    def __getitem__(self, ndx):
        if self._ndx != ndx:
            # empty the result cache
            self._results = []

        if self.is_evaluated:
            return self._results

        self._ndx = ndx

        if type(ndx) is slice:
            self._start = ndx.start or 0  # in case it is None because [:X]
            self._stop = ndx.stop
        elif type(ndx) is int:
            self._start = ndx
            self._stop = ndx + 1

        self.do_search()
        if type(ndx) is slice:
            return self._results
        elif type(ndx) is int:
            return self._results[0]

    def __nonzero__(self):
        self.count()
        return self._total != 0

    def _make_search_body(self):
        body = {}
        search = {}

        if self._query:
            search['query'] = {
                'match': {'_all': self._query},
            }

        if self._filters:
            # TODO: should we add _cache = true ?!
            # TODO: handle other type of filters ?!
            filters = []
            for f in self._filters:
                for field, value in f.items():
                    filters.append({'term': {field: value}})
            search['filter'] = {'bool': {'must': filters}}
            body['query'] = {'filtered': search}
        else:
            body = search
        return body

    def __len__(self):
        r = es.count(
            index=self.model.es.get_index(),
            doc_type=self.model.es.get_doc_type(),
            body=self._make_search_body())
        self._total = r['count']
        return self._total

    # @property
    # def qs(self):
    #     return self

    @property
    def is_evaluated(self):
        return bool(self._results)

    def do_search(self, extra_body=None):
        # TODO: regexp:
        # attr:value
        # "match a phrase"
        if self.is_evaluated:
            return self._results

        body = self._make_search_body()

        if self.facets_fields:
            body['facets'] = dict([
                (field, {'terms':
                         {'field': field},
                         'global': self.global_facets})
                for field in self.facets_fields
            ])
            if self.facets_limit:
                body['facets'][field]['terms']['size'] = self.facets_limit

        if self.suggest_fields:
            suggest = {}
            for field_name in self.suggest_fields:
                suggest[field_name] = {"text": self._query,
                                       "term": {"field": field_name}}
                if self.suggest_limit:
                    suggest[field_name]["text"]["term"]["size"] = self.suggest_limit
            body['suggest'] = suggest

        if self._ordering:
            body['sort'] = self._ordering

        search_params = {
            'index': self.model.es.get_index(),
            'doc_type': self.model.es.get_doc_type()
        }
        if self._start:
            search_params['from_'] = self._start
        if self._stop:
            search_params['size'] = self._stop - self._start
        search_params['body'] = body

        print search_params

        r = es.search(**search_params)

        if self.facets_fields:
            self._facets = r['facets']

        if self.suggest_fields:
            self._suggestions = r['suggest']

        self._results = [self.model.es.deserialize(source=e['_source'])
                         for e in r['hits']['hits']]
        self._max_score = r['hits']['max_score']
        self._total = r['hits']['total']
        return self._results

    def facet(self, fields, limit=None, use_globals=True):
        self.facets_fields = fields
        self.facets_limit = limit
        self.global_facets = use_globals
        return self

    def suggest(self, fields, limit=None):
        self.suggest_fields = fields
        self.suggest_limit = limit
        return self

    def query(self, query):
        self._query = query
        return self

    def order_by(self, *fields):
        if self.is_evaluated:
            # empty the result cache
            self._results = []
        self._ordering = [{f: "asc"} if f[0] != '-' else {f[1:]: "desc"}
                          for f in fields] + ["_score"]
        return self

    def filter(self, **kwargs):
        if self.is_evaluated:
            # empty the result cache
            self._results = []
        self._filters.append(kwargs)
        return self

    def exclude(self, **kwargs):
        raise NotImplementedError

    ## getters
    def all(self):
        return self

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


def needs_instance(f):
    def wrapper(*args, **kwargs):
        if args[0].instance is None:
            raise AttributeError("This method requires an instance.")
        return f(*args, **kwargs)
    return wrapper


class ElasticsearchManager():
    """
    Note: This is not strictly a django model Manager.
    """

    def __init__(self, k):
        # avoid a circular import, meh :(
        from django_elasticsearch.models import EsIndexable
        # k can be either an instance or a class
        if isinstance(k, EsIndexable):
            self.instance = k
            self.model = k.__class__
        elif issubclass(k, EsIndexable):
            self.instance = None
            self.model = k
        else:
            raise TypeError

    def get_index(self):
        return self.model.Elasticsearch.index

    def get_doc_type(self):
        # TODO: make it a property
        return 'model-{0}'.format(self.model.__name__)

    @needs_instance
    def serialize(self):
        """
        Returns a json object suitable for elasticsearch indexation.
        """
        # Note: by default, will use all the model's fields.
        return (self.model.Elasticsearch.serializer_class(self.model)
                .serialize(self.instance))

    def deserialize(self, source):
        """
        Create an instance of the Model from the elasticsearch source
        Note: IMPORTANT: there is no certainty that the elasticsearch instance
        actually is synchronised with the db one.
        That is why the save() method is desactivated.
        """
        instance = self.model(**self.model.Elasticsearch
                              .serializer_class(self.model)
                              .deserialize(source))
        instance._is_es_deserialized = True
        return instance

    @needs_instance
    def do_index(self):
        json = self.serialize()
        es.index(index=self.get_index(),
                 doc_type=self.get_doc_type(),
                 id=self.instance.id,
                 body=json)

    @needs_instance
    def delete(self):
        es.delete(index=self.get_index(),
                  doc_type=self.get_doc_type(),
                  id=self.instance.id, ignore=404)

    @needs_instance
    def get(self, **kwargs):
        return es.get(index=self.get_index(),
                      id=self.instance.id, **kwargs)

    @needs_instance
    def mlt(self, fields=[]):
        """
        Returns documents that are 'like' this instance
        """
        return es.mlt(index=self.get_index(),
                      doc_type=self.get_doc_type(),
                      id=self.instance.id, mlt_fields=fields)

    def search(self, query,
               facets=None, facets_limit=None, global_facets=True,
               suggest_fields=None, suggest_limit=None):
        """
        Returns a EsQueryset instance that acts a bit like a django Queryset
        facets is dictionnary containing facets informations
        If global_facets is True,
        the most used facets accross all documents will be returned.
        if set to False, the facets will be filtered by the search query
        """
        q = EsQueryset(self.model).query(query)

        if facets is None and self.model.Elasticsearch.facets_fields:
            facets = self.model.Elasticsearch.facets_fields
        if facets:
            q.facet(facets,
                    limit=facets_limit or self.model.Elasticsearch.facets_limit,
                    use_globals=global_facets)

        if suggest_fields is None and self.model.Elasticsearch.suggest_fields:
            suggest_fields = self.model.Elasticsearch.suggest_fields
        if suggest_fields:
            q.suggest(fields=suggest_fields, limit=suggest_limit)

        return q

    def complete(self, field_name, query):
        """
        Returns a list of close values for auto-completion
        """
        if field_name not in self.model.Elasticsearch.completion_fields:
            raise ValueError("{0} is not in the completion_fields list, "
                             "it is required to have a specific mapping."
                             .format(field_name))

        complete_name = "{0}_complete".format(field_name)
        resp = es.suggest(index=self.get_index(),
                          body={complete_name: {
                              "text": query,
                              "completion": {
                                  "field": complete_name,
                                  "fuzzy" : {}  # stick to fuzziness settings
                              }}})

        return [r['text'] for r in resp[complete_name][0]['options']]

    def do_update(self):
        """
        Hit this if you are in a hurry,
        the recently indexed items will be available right away.
        """
        es.indices.refresh(index=self.get_index())

    def make_mapping(self):
        """
        Create the model's es mapping on the fly
        """
        mappings = {}

        model_fields = [f.name for f in self.model._meta.fields]
        fields = self.model.Elasticsearch.fields or model_fields
        for field_name in fields:
            try:
                field = self.model._meta.get_field(field_name)
            except FieldDoesNotExist:
                # abstract field
                mapping = {}
            else:
                mapping = {'type': ELASTICSEARCH_FIELD_MAP.get(
                    field.get_internal_type(), 'string')}
            try:
                # if an analyzer is set as default, use it.
                # TODO: could be also tokenizer, filter, char_filter
                if mapping['type'] == 'string':
                    analyzer = settings.ELASTICSEARCH_SETTINGS['analysis']['default']
                    mapping['analyzer'] = analyzer
            except (ValueError, AttributeError, KeyError, TypeError):
                pass
            try:
                mapping.update(self.model.Elasticsearch.mappings[field_name])
            except (AttributeError, KeyError, TypeError):
                pass
            mappings[field_name] = mapping

        # add a suggest mapping for every suggestable field
        fields = self.model.Elasticsearch.completion_fields or []
        for field_name in fields:
            complete_name = "{0}_complete".format(field_name)
            mappings[complete_name] = {"type": "completion"}

        return {
            self.get_doc_type(): {
                "properties": mappings
            }
        }

    def get_mapping(self):
        """
        Debug convenience method.
        """
        return es.indices.get_mapping(index=self.get_index(),
                                      doc_type=self.get_doc_type())

    def get_settings(self):
        """
        Debug convenience method.
        """
        return es.indices.get_settings(index=self.get_index())

    @needs_instance
    def diff(self, source=None):
        """
        Returns a nice diff between the db and es.
        """
        raise NotImplementedError

    def create_index(self):
        body = {}
        if hasattr(settings, 'ELASTICSEARCH_SETTINGS'):
            body['settings'] = settings.ELASTICSEARCH_SETTINGS

        es.indices.create(self.get_index(),
                          body=body, ignore=400)
        es.indices.put_mapping(index=self.get_index(),
                               doc_type=self.get_doc_type(),
                               body=self.make_mapping())

    def reindex_all(self, queryset=None):
        q = queryset or self.model.objects.all()
        for instance in q:
            instance.es.do_index()

    def flush(self):
        es.indices.delete_mapping(index=self.get_index(),
                                  doc_type=self.get_doc_type(),
                                  ignore=400)
        self.create_index()
        self.reindex_all()
