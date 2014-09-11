# -*- coding: utf-8 -*-
from django.conf import settings
from django.db.models import Model
from django.db.models.signals import post_save, post_delete, post_syncdb
from django.db.models.query import REPR_OUTPUT_SIZE

from elasticsearch import Elasticsearch

from django_elasticsearch.serializers import ModelJsonSerializer

ELASTICSEARCH_URL = getattr(settings, 'ELASTICSEARCH_URL', 'http://localhost:9200')
ELASTICSEARCH_AUTO_INDEX = getattr(settings, 'ELASTICSEARCH_AUTO_INDEX', True)

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
        self._start = 0
        self._stop = 10  # TODO: should be None to fallback to the elasticsearch setting, not arbitrarly 10, but need to create es.search kwargs dynamically.
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
        if self._results:
            return self._results[ndx]

        if type(ndx) is slice:
            self._start = ndx.start or 0  # in case it is None because [:X]
            self._stop = ndx.stop
        elif type(ndx) is int:
            self._start = ndx
            self._stop = ndx + 1

        self.do_search()
        return self._results[ndx]

    def __nonzero__(self):
        self.count()
        return self._total != 0

    def make_search_body(self):
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
            doc_type=self.model.es_get_doc_type(),
            body=self.make_search_body())
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
        if self._results:
            return self._results

        body = self.make_search_body()

        if self.facets_fields:
            body['facets'] = dict([
                (field, {'terms' : {'field' : field, 'size': self.facets_limit}, 'global': self.global_facets})
                for field in self.facets_fields
            ])

        if self._ordering:
            body['sort'] = self._ordering

        search_params = {
            'index': self.model.Elasticsearch.index,
            'doc_type': self.model.es_get_doc_type()
        }
        if self._start:
            search_params['from_'] = self._start
        if self._stop:
            search_params['size'] = self._stop - self._start
        search_params['body'] = body
        r = es.search(**search_params)
        if self.facets_fields:
            self._facets = r['facets']
        self._results = [self.model.es_deserialize(source=e['_source']) for e in r['hits']['hits']]
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
        raise NotImplementedError

    def delete(self):
        raise NotImplementedError

    @property
    def facets(self):
        self.do_search()
        return self._facets

    def count(self):
        return self.__len__()


class EsIndexable(Model):
    """
    Mixin that encapsulate all the indexation logic of a model.
    """

    class Meta:
        abstract = True

    class Elasticsearch:
        index = 'django'
        mapping = None
        serializer_class = ModelJsonSerializer
        fields = None
        facets_limit = 10
        default_facets_fields = None

    def _raise_no_db_operation(self):
        if getattr(self, '_is_es_deserialized', False):
            raise ValueError("The instance {0} of {1} have been deserialized from an elasticsearch source and thus it's not safe to save it.".format(self, self.__class__))

    def save(self, *args, **kwargs):
        self._raise_no_db_operation()
        super(EsIndexable, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._raise_no_db_operation()
        super(EsIndexable, self).delete(*args, **kwargs)

    @classmethod
    def es_get_doc_type(cls):
        # TODO: make it a property
        return 'model-{0}'.format(cls.__name__)

    def es_serialize(self):
        """
        Returns a json object suitable for elasticsearch indexation.
        """
        # Note: by default, will use all the model's fields.
        return self.Elasticsearch.serializer_class(self.__class__).serialize(self)

    @classmethod
    def es_deserialize(cls, source):
        """
        Create an instance of the Model from the elasticsearch source
        Note: IMPORTANT: there is no certainty that the elasticsearch instance actually is synchronised with the db one. That is why the save() method is desactivated.
        """
        instance = cls(**cls.Elasticsearch.serializer_class(cls).deserialize(source))
        instance._is_es_deserialized = True  # make sure it won't be saved in db.
        return instance

    def es_do_index(self):
        json = self.es_serialize()
        es.index(index=self.Elasticsearch.index,
                 doc_type=self.es_get_doc_type(),
                 id=self.id,
                 body=json)

    def es_delete(self):
        es.delete(index=self.Elasticsearch.index,
                  doc_type=self.es_get_doc_type(),
                  id=self.id, ignore=404)

    def es_get(self, **kwargs):
        return es.get(index=self.Elasticsearch.index, id=self.id, **kwargs)

    def es_mlt(self, fields=[]):
        """
        Returns documents that are 'like' this instance
        """
        return es.mlt(index=self.Elasticsearch.index,
                      doc_type=self.es_get_doc_type(),
                      id=self.id, mlt_fields=fields)

    @classmethod
    def es_search(cls, query, facets=None, facets_limit=5, global_facets=True):
        """
        Returns a EsQueryset instance that acts a bit like a django Queryset
        facets is dictionnary containing facets informations
        If global_facets is True, the es_facets_limit most used facets accross all documents will be returned.
        if set to False, the facets will be filtered by the search query
        """
        if facets is None and cls.Elasticsearch.default_facets_fields:
            facets = cls.Elasticsearch.default_facets_fields

        q = EsQueryset(cls).query(query)

        if facets:
            q.add_facets(facets, limit=facets_limit, use_globals=global_facets)
        return q

    @classmethod
    def es_do_update(cls):
        """
        Hit this if you are in a hurry,
        the recently indexed items will be available right away.
        """
        es.indices.refresh(index=cls.Elasticsearch.index)

    @classmethod
    def es_make_mapping(cls):
        """
        Create the model's es mapping on the fly
        """
        mappings = {}

        fields = cls.Elasticsearch.fields or [f.name for f in cls._meta.fields]
        for field_name in fields:
            field = cls._meta.get_field(field_name)
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
                mapping.update(cls.Elasticsearch.mapping[field_name])
            except (AttributeError, KeyError, TypeError):
                pass
            mappings[field_name] = mapping

        return {
            cls.es_get_doc_type(): {
                "properties": mappings
            }
        }

    @classmethod
    def es_get_mapping(cls):
        """
        Debug convenience method.
        """
        return es.indices.get_mapping(index=cls.Elasticsearch.index,
                                      doc_type=cls.es_get_doc_type())

    @classmethod
    def es_get_settings(cls):
        """
        Debug convenience method.
        """
        return es.indices.get_settings(index=cls.Elasticsearch.index,)

    def es_diff(self, source=None):
        """
        Returns a nice diff between the db and es.
        """
        raise NotImplementedError

    @classmethod
    def es_create_index(cls):
        body = {}
        if hasattr(settings, 'ELASTICSEARCH_SETTINGS'):
            body['settings'] = settings.ELASTICSEARCH_SETTINGS

        es.indices.create(cls.Elasticsearch.index,
                          body=body, ignore=400)
        es.indices.put_mapping(index=cls.Elasticsearch.index,
                               doc_type=cls.es_get_doc_type(),
                               body=cls.es_make_mapping())

    @classmethod
    def es_flush(cls):
        es.indices.delete_mapping(index=cls.Elasticsearch.index,
                                  doc_type=cls.es_get_doc_type(),
                                  ignore=400)
        cls.es_create_index()
        cls.es_reindex_all()

    @classmethod
    def es_reindex_all(cls, queryset=None):
        q = queryset or cls.objects.all()
        for instance in q:
            q.es_do_index()


def es_save_callback(sender, instance, **kwargs):
    # TODO: batch ?! @task ?!
    if not issubclass(sender, EsIndexable):
        return
    instance.es_do_index()


def es_delete_callback(sender, instance, **kwargs):
    if not issubclass(sender, EsIndexable):
        return
    instance.es_delete()


def es_syncdb_callback(sender, app, created_models, **kwargs):
    for model in created_models:
        if issubclass(model, EsIndexable):
            model.es_create_index()


if ELASTICSEARCH_AUTO_INDEX and not settings.DEBUG:
    # Note: can't specify the sender class because EsIndexable is Abstract,
    # see: https://code.djangoproject.com/ticket/9318
    post_save.connect(es_save_callback)
    post_delete.connect(es_delete_callback)
    post_syncdb.connect(es_syncdb_callback)
