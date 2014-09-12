# -*- coding: utf-8 -*-
from django.conf import settings
from django.db.models.query import REPR_OUTPUT_SIZE

from elasticsearch import Elasticsearch


ELASTICSEARCH_URL = getattr(settings, 'ELASTICSEARCH_URL', 'http://localhost:9200')

# TODO: would it be better to give this client a dedicated thread ?!
# and not instanciate it each request ?
es = Elasticsearch(ELASTICSEARCH_URL)


# Note: we use long/double because different db backends could store different sizes of numerics ?
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
        self._ordering = None  # default to 'score'
        self._ndx = None
        self._start = 0
        self._stop = None
        self._query = None
        self._filters = []
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
        return self._results

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
            index=self.model.Elasticsearch.index,
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

    def do_search(self):
        # TODO: regexp:
        # attr:value
        # "match a phrase"
        if self.is_evaluated:
            return self._results

        body = self._make_search_body()

        if self.facets_fields:
            body['facets'] = dict([
                (field, {'terms' : {'field' : field, 'size': self.facets_limit}, 'global': self.global_facets})
                for field in self.facets_fields
            ])

        if self._ordering:
            body['sort'] = self._ordering

        search_params = {
            'index': self.model.Elasticsearch.index,
            'doc_type': self.model.es.get_doc_type()
        }
        if self._start:
            search_params['from_'] = self._start
        if self._stop:
            search_params['size'] = self._stop - self._start
        search_params['body'] = body

        r = es.search(**search_params)

        if self.facets_fields:
            self._facets = r['facets']
        self._results = [self.model.es.deserialize(source=e['_source']) for e in r['hits']['hits']]
        self._max_score = r['hits']['max_score']
        self._total = r['hits']['total']
        return self._results

    def add_facets(self, fields=None, limit=10, use_globals=True):
        self.facets_fields = fields
        self.facets_limit = limit
        self.global_facets = use_globals
        return self

    def query(self, query):
        self._query = query
        return self

    def order_by(self, *fields):
        self._ordering = [{f: "asc"} if f[0] != '-' else {f[1:]: "desc"} for f in fields] + ["_score"]

    def filter(self, **kwargs):
        if self._results:
            # Note: should we just re-request ?
            raise ValueError("You can't filter an already evaluated Elasticsearch Queryset.")
        self._filters.append(kwargs)
        return self

    def exclude(self, **kwargs):
        raise NotImplementedError

    ## getters
    def all(self):
        return self

    def update(self):
        # Note: do we want to be able to change elasticsearch documents directly ?
        raise NotImplementedError("Db operational methods have been disabled for Elasticsearch Querysets.")

    def delete(self):
        raise NotImplementedError("Db operational methods have been disabled for Elasticsearch Querysets.")

    @property
    def facets(self):
        self.do_search()
        return self._facets

    def count(self):
        return self.__len__()


def needs_instance(f):
    def wrapper(*args, **kwargs):
        if args[0].instance is None:
            raise AttributeError("This method requires an instance.")
        return f(*args, **kwargs)
    return wrapper


class ElasticsearchManager():

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

    def get_doc_type(self):
        # TODO: make it a property
        return 'model-{0}'.format(self.model.__name__)

    @needs_instance
    def serialize(self):
        """
        Returns a json object suitable for elasticsearch indexation.
        """
        # Note: by default, will use all the model's fields.
        return self.model.Elasticsearch.serializer_class(self.model).serialize(self.instance)

    def deserialize(self, source):
        """
        Create an instance of the Model from the elasticsearch source
        Note: IMPORTANT: there is no certainty that the elasticsearch instance actually is synchronised with the db one. That is why the save() method is desactivated.
        """
        instance = self.model(**self.model.Elasticsearch.serializer_class(self.model).deserialize(source))
        instance._is_es_deserialized = True  # make sure it won't be saved in db.
        return instance

    @needs_instance
    def do_index(self):
        json = self.serialize()
        es.index(index=self.model.Elasticsearch.index,
                 doc_type=self.get_doc_type(),
                 id=self.instance.id,
                 body=json)

    @needs_instance
    def delete(self):
        es.delete(index=self.model.Elasticsearch.index,
                  doc_type=self.get_doc_type(),
                  id=self.instance.id, ignore=404)

    @needs_instance
    def get(self, **kwargs):
        return es.get(index=self.model.Elasticsearch.index,
                      id=self.instance.id, **kwargs)

    @needs_instance
    def mlt(self, fields=[]):
        """
        Returns documents that are 'like' this instance
        """
        return es.mlt(index=self.model.Elasticsearch.index,
                      doc_type=self.get_doc_type(),
                      id=self.instance.id, mlt_fields=fields)

    def search(self, query, facets=None, facets_limit=5, global_facets=True):
        """
        Returns a EsQueryset instance that acts a bit like a django Queryset
        facets is dictionnary containing facets informations
        If global_facets is True, the es.facets_limit most used facets accross all documents will be returned.
        if set to False, the facets will be filtered by the search query
        """
        if facets is None and self.model.Elasticsearch.default_facets_fields:
            facets = self.model.Elasticsearch.default_facets_fields

        q = EsQueryset(self.model).query(query)

        if facets:
            q.add_facets(facets, limit=facets_limit, use_globals=global_facets)
        return q

    def do_update(self):
        """
        Hit this if you are in a hurry,
        the recently indexed items will be available right away.
        """
        es.indices.refresh(index=self.model.Elasticsearch.index)

    def make_mapping(self):
        """
        Create the model's es mapping on the fly
        """
        mappings = {}

        fields = self.model.Elasticsearch.fields or [f.name for f in self.model._meta.fields]
        for field_name in fields:
            field = self.model._meta.get_field(field_name)
            mapping = {'type': ELASTICSEARCH_FIELD_MAP.get(
                field.get_internal_type(), 'string')
            }
            try:
                # if an analyzer is set as default, use it.
                # TODO: could be also tokenizer, filter, char_filter
                if mapping['type'] == 'string':
                    mapping['analyzer'] = settings.ELASTICSEARCH_SETTINGS['analysis']['default']
            except (ValueError, AttributeError, KeyError, TypeError):
                pass
            try:
                mapping.update(self.model.Elasticsearch.mapping[field_name])
            except (AttributeError, KeyError, TypeError):
                pass
            mappings[field_name] = mapping

        return {
            self.get_doc_type(): {
                "properties": mappings
            }
        }

    def get_mapping(self):
        """
        Debug convenience method.
        """
        return es.indices.get_mapping(index=self.model.Elasticsearch.index,
                                      doc_type=self.get_doc_type())

    def get_settings(self):
        """
        Debug convenience method.
        """
        return es.indices.get_settings(index=self.model.Elasticsearch.index)

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

        es.indices.create(self.model.Elasticsearch.index,
                          body=body, ignore=400)
        es.indices.put_mapping(index=self.model.Elasticsearch.index,
                               doc_type=self.get_doc_type(),
                               body=self.make_mapping())

    def reindex_all(self, queryset=None):
        q = queryset or self.model.objects.all()
        for instance in q:
            instance.es.do_index()

    def flush(self):
        es.indices.delete_mapping(index=self.model.Elasticsearch.index,
                                  doc_type=self.get_doc_type(),
                                  ignore=400)
        self.create_index()
        self.reindex_all()
