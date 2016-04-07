# -*- coding: utf-8 -*-
from django.conf import settings
from django.db.models import Model
from django.db.models.signals import post_save, post_delete, post_syncdb
from django.db.models.signals import class_prepared

from django_elasticsearch.serializers import EsJsonSerializer
from django_elasticsearch.managers import ElasticsearchManager


class EsIndexable(Model):
    """
    Mixin that encapsulate all the indexation logic of a model.
    """
    class Meta:
        abstract = True

    class Elasticsearch:
        abstract = False
        index = getattr(settings, 'ELASTICSEARCH_DEFAULT_INDEX', 'django')
        doc_type = None  # defaults to 'model-{model.name}'
        mapping = None
        serializer_class = EsJsonSerializer
        fields = None
        facets_limit = 10
        facets_fields = None
        # http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/search-suggesters-term.html
        suggest_fields = None
        # http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/search-suggesters-completion.html
        completion_fields = None

    def __init__(self, *args, **kwargs):
        super(EsIndexable, self).__init__(*args, **kwargs)
        # override the manager because we have an instance now
        self.es = ElasticsearchManager(self)

    def _raise_no_db_operation(self):
        if getattr(self, '_is_es_deserialized', False):
            raise ValueError("""The instance {0} of {1} have been deserialized
            from an elasticsearch source and thus
            it's not safe to save it.""".format(self, self.__class__))

    def save(self, *args, **kwargs):
        self._raise_no_db_operation()
        super(EsIndexable, self).save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._raise_no_db_operation()
        super(EsIndexable, self).delete(*args, **kwargs)


def add_es_manager(sender, **kwargs):
    # Note: the manager needs to know the subclass
    if issubclass(sender, EsIndexable):
        sender.es = ElasticsearchManager(sender)
class_prepared.connect(add_es_manager)


def es_save_callback(sender, instance, **kwargs):
    # TODO: batch ?! @task ?!
    if not issubclass(sender, EsIndexable) or sender.Elasticsearch.abstract:
        return
    instance.es.do_index()


def es_delete_callback(sender, instance, **kwargs):
    if not issubclass(sender, EsIndexable) or sender.Elasticsearch.abstract:
        return
    instance.es.delete()


def es_syncdb_callback(sender, app, created_models, **kwargs):
    for model in created_models:
        if issubclass(model, EsIndexable) and not sender.Elasticsearch.abstract:
            model.es.create_index()

if getattr(settings, 'ELASTICSEARCH_AUTO_INDEX', False):
    # Note: can't specify the sender class because EsIndexable is Abstract,
    # see: https://code.djangoproject.com/ticket/9318
    post_save.connect(es_save_callback)
    post_delete.connect(es_delete_callback)
    post_syncdb.connect(es_syncdb_callback)
