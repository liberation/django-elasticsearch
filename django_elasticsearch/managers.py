# -*- coding: utf-8 -*-
from django.conf import settings
from django.db.models import FieldDoesNotExist

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
    u'FloatField': 'double',
    u'IntegerField': 'long',
    u'PositiveIntegerField': 'long',
    u'PositiveSmallIntegerField': 'short',
    u'SmallIntegerField': 'short'
}


def needs_instance(f):
    def wrapper(*args, **kwargs):
        if args[0].instance is None:
            raise AttributeError("This method requires an instance of the model.")
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

    @property
    def index(self):
        return self.get_index()

    def get_doc_type(self):
        return 'model-{0}'.format(self.model.__name__)

    @property
    def doc_type(self):
        return self.get_doc_type()

    def check_cluster(self):
        return es_client.ping()

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
        obj = (self.model.Elasticsearch
               .serializer_class(self.model)
               .deserialize(source))
        instance = self.model(**obj)
        instance._is_es_deserialized = True
        return instance

    @needs_instance
    def do_index(self):
        json = self.serialize()
        es_client.index(index=self.get_index(),
                        doc_type=self.get_doc_type(),
                        id=self.instance.id,
                        body=json)

    @needs_instance
    def delete(self):
        es_client.delete(index=self.get_index(),
                         doc_type=self.get_doc_type(),
                         id=self.instance.id, ignore=404)

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
    def mlt(self, fields=[]):
        """
        Returns documents that are 'like' this instance
        """
        return es_client.mlt(index=self.get_index(),
                             doc_type=self.get_doc_type(),
                             id=self.instance.id, mlt_fields=fields)

    @property
    def queryset(self):
        return EsQueryset(self.model)

    def search(self, *args, **kwargs):
        # proxy to EsQueryset
        return self.queryset.search(*args, **kwargs)

    def complete(self, field_name, query):
        """
        Returns a list of close values for auto-completion
        """
        if field_name not in (self.model.Elasticsearch.completion_fields or []):
            raise ValueError("{0} is not in the completion_fields list, "
                             "it is required to have a specific mapping."
                             .format(field_name))

        complete_name = "{0}_complete".format(field_name)
        resp = es_client.suggest(index=self.get_index(),
                                 body={complete_name: {
                                     "text": query,
                                     "completion": {
                                         "field": complete_name,
                                         # stick to fuzziness settings
                                         "fuzzy" : {}
                                     }}})

        return [r['text'] for r in resp[complete_name][0]['options']]

    def do_update(self):
        """
        Hit this if you are in a hurry,
        the recently indexed items will be available right away.
        """
        es_client.indices.refresh(index=self.get_index())

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
        full_mapping = es_client.indices.get_mapping(index=self.get_index(),
                                                     doc_type=self.get_doc_type())

        # look what pep8 make me do
        index = self.get_index()
        doc_type = self.get_doc_type()
        return full_mapping[index]['mappings'][doc_type]['properties']

    def get_settings(self):
        """
        Debug convenience method.
        """
        return es_client.indices.get_settings(index=self.get_index())

    @needs_instance
    def diff(self, source=None):
        """
        Returns a nice diff between the db and es.
        """
        raise NotImplementedError

    def create_index(self, ignore=True):
        body = {}
        if hasattr(settings, 'ELASTICSEARCH_SETTINGS'):
            body['settings'] = settings.ELASTICSEARCH_SETTINGS

        es_client.indices.create(self.get_index(),
                                 body=body, ignore=ignore and 400)
        es_client.indices.put_mapping(index=self.get_index(),
                                      doc_type=self.get_doc_type(),
                                      body=self.make_mapping())

    def reindex_all(self, queryset=None):
        q = queryset or self.model.objects.all()
        for instance in q:
            instance.es.do_index()

    def flush(self):
        es_client.indices.delete_mapping(index=self.get_index(),
                                         doc_type=self.get_doc_type(),
                                         ignore=404)
        self.create_index()
        self.reindex_all()
