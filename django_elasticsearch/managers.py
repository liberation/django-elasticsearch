# -*- coding: utf-8 -*-
import json
try:
    import importlib
except ImportError:  # python < 2.7
    from django.utils import importlib

from django import VERSION as django_version
from django.conf import settings
try:
    from django.utils import importlib
except:
    import importlib

if django_version < (3, 1, 0):
    from django.db.models import FieldDoesNotExist
else:
    from django.core.exceptions import FieldDoesNotExist

from django_elasticsearch.query import EsQueryset
from django_elasticsearch.client import es_client

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
    # u'TimeField': 'string',
    u'FloatField': 'double',
    u'IntegerField': 'long',
    u'PositiveIntegerField': 'long',
    u'PositiveSmallIntegerField': 'short',
    u'SmallIntegerField': 'short',

    u'ForeignKey': 'object',
    u'OneToOneField': 'object',
    u'ManyToManyField': 'object'
}


def needs_instance(f):
    def wrapper(*args, **kwargs):
        if args[0].instance is None:
            raise AttributeError("This method requires an instance of the model.")
        return f(*args, **kwargs)
    return wrapper


class ElasticsearchManager():
    """
    Note: This is not strictly a django model Manager !
    most of those methods don't return a Queryset.
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

        self.serializer = None
        self._mapping = None

    def get_index(self):
        return self.model.Elasticsearch.index

    @property
    def index(self):
        return self.get_index()

    def get_doc_type(self):
        return (self.model.Elasticsearch.doc_type
                or 'model-{0}'.format(self.model.__name__))

    @property
    def doc_type(self):
        return self.get_doc_type()

    def check_cluster(self):
        return es_client.ping()

    def get_serializer(self, **kwargs):
        serializer = self.model.Elasticsearch.serializer_class
        if isinstance(serializer, basestring):
            module, kls = self.model.Elasticsearch.serializer_class.rsplit(".", 1)
            mod = importlib.import_module(module)
            return getattr(mod, kls)(self.model, **kwargs)
        else:
            return serializer(self.model, **kwargs)

    @needs_instance
    def serialize(self):
        """
        Returns a json object suitable for elasticsearch indexation.
        Note: by default, will use all the model's fields.
        """
        serializer = self.get_serializer()
        return serializer.serialize(self.instance)

    def deserialize(self, source):
        """
        Create an instance of the Model from the elasticsearch source
        or an EsQueryset
        Note: IMPORTANT: there is no certainty that the elasticsearch instance
        actually is synchronised with the db one.
        That is why the save() method is desactivated.
        """
        serializer = self.get_serializer()

        if isinstance(source, EsQueryset):
            # Note: generator ?
            return [serializer.deserialize(e) for e in source]
        else:
            return serializer.deserialize(source)

    @needs_instance
    def do_index(self):
        body = self.serialize()
        es_client.index(index=self.index,
                        doc_type=self.doc_type,
                        id=self.instance.id,
                        body=body)

    @needs_instance
    def delete(self):
        es_client.delete(index=self.index,
                         doc_type=self.doc_type,
                         id=self.instance.id,
                         ignore=404)

    def get(self, **kwargs):
        if 'pk' in kwargs:
            pk = kwargs.pop('pk')
        elif 'id' in kwargs:
            pk = kwargs.pop('id')
        else:
            try:
                pk = self.instance.id
            except AttributeError:
                raise AttributeError("The 'es.get' method needs to be called from an instance or be given a 'pk' parameter.")

        return self.queryset.get(id=pk)

    @needs_instance
    def mlt(self, **kwargs):
        """
        Returns documents that are 'like' this instance
        You may have to toy with parameters in case of a low document count:
        min_term_freq, min_doc_freq, and percent_terms_to_match

        See es_client.mlt for all available kwargs
        :arg index: The name of the index * defaults to self.index *
        :arg doc_type: The type of the document (use `_all` to fetch the first
                       document matching the ID across all types)
                       * Defaults to self.doc_type *
        :arg include: Whether to include the queried document from the response
                      * defaults to False *
        :arg mlt_fields: Specific fields to perform the query against
        """
        return self.queryset.mlt(id=self.instance.id, **kwargs)

    def count(self):
        return self.queryset.count()

    @property
    def queryset(self):
        return EsQueryset(self.model)

    def search(self, query,
               facets=None, facets_limit=None, global_facets=True,
               suggest_fields=None, suggest_limit=None,
               fuzziness=None):
        """
        Returns a EsQueryset instance that acts a bit like a django Queryset
        facets is dictionnary containing facets informations
        If global_facets is True,
        the most used facets accross all documents will be returned.
        if set to False, the facets will be filtered by the search query

        :arg query
        :arg facets
        :arg facets_limit
        :arg global_facets
        :arg suggest_fields
        :arg suggest_limit
        :arg fuzziness
        """

        q = self.queryset
        q.fuzziness = fuzziness

        if facets is None and self.model.Elasticsearch.facets_fields:
            facets = self.model.Elasticsearch.facets_fields
        if facets:
            q = q.facet(facets,
                        limit=facets_limit or self.model.Elasticsearch.facets_limit,
                        use_globals=global_facets)

        if suggest_fields is None and self.model.Elasticsearch.suggest_fields:
            suggest_fields = self.model.Elasticsearch.suggest_fields
        if suggest_fields:
            q = q.suggest(fields=suggest_fields, limit=suggest_limit)

        return q.query(query)

    # Convenience methods
    def all(self):
        """
        proxy to an empty search.
        """
        return self.search("")

    def filter(self, **kwargs):
        return self.queryset.filter(**kwargs)

    def exclude(self, **kwargs):
        return self.queryset.exclude(**kwargs)

    def complete(self, field_name, query):
        """
        Returns a list of close values for auto-completion
        """
        if field_name not in (self.model.Elasticsearch.completion_fields or []):
            raise ValueError("{0} is not in the completion_fields list, "
                             "it is required to have a specific mapping."
                             .format(field_name))

        complete_name = "{0}_complete".format(field_name)
        return self.queryset.complete(complete_name, query)

    def do_update(self):
        """
        Hit this if you are in a hurry,
        the recently indexed items will be available right away.
        """
        es_client.indices.refresh(index=self.index)

    def get_fields(self):
        model_fields = [f.name for f in self.model._meta.fields +
                        self.model._meta.many_to_many]

        return self.model.Elasticsearch.fields or model_fields

    def make_mapping(self):
        """
        Create the model's es mapping on the fly
        """
        mappings = {}

        for field_name in self.get_fields():
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

        # add a completion mapping for every auto completable field
        fields = self.model.Elasticsearch.completion_fields or []
        for field_name in fields:
            complete_name = "{0}_complete".format(field_name)
            mappings[complete_name] = {"type": "completion"}

        return {
            self.doc_type: {
                "properties": mappings
            }
        }

    def get_mapping(self):
        if self._mapping is None:
            # TODO: could be done once for every index/doc_type ?
            full_mapping = es_client.indices.get_mapping(index=self.index,
                                                         doc_type=self.doc_type)
            self._mapping = full_mapping[self.index]['mappings'][self.doc_type]['properties']

        return self._mapping

    def get_settings(self):
        """
        Debug convenience method.
        """
        return es_client.indices.get_settings(index=self.index)

    @needs_instance
    def diff(self, source=None):
        """
        Returns a nice diff between the db and es.
        """
        es = self.get()
        if source is not None:
            db = source
        elif getattr(self.instance, '_is_es_deserialized', False):
            # we need to fetch it from db
            db = json.loads(self.model.objects.get(pk=self.instance.pk).es.serialize())
        else:
            db = json.loads(self.instance.es.serialize())  # db value

        # we are only interested in indexed fields
        diff = {}
        for field_name in self.get_fields():
            esval = es.get(field_name)
            dbval = db.get(field_name)
            if esval != dbval:
                diff[field_name] = {'es': esval,
                                    'db': dbval}

        return diff

    def create_index(self, ignore=True):
        body = {}
        if hasattr(settings, 'ELASTICSEARCH_SETTINGS'):
            body['settings'] = settings.ELASTICSEARCH_SETTINGS

        es_client.indices.create(self.index,
                                 body=body,
                                 ignore=ignore and 400)
        es_client.indices.put_mapping(index=self.index,
                                      doc_type=self.doc_type,
                                      body=self.make_mapping())

    def reindex_all(self, queryset=None):
        q = queryset or self.model.objects.all()
        for instance in q:
            instance.es.do_index()

    def flush(self):
        es_client.indices.delete_mapping(index=self.index,
                                         doc_type=self.doc_type,
                                         ignore=404)
        self.create_index()
        self.reindex_all()
