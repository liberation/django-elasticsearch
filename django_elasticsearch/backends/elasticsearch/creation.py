import sys

from django.conf import settings
from django.db.models import FieldDoesNotExist
from django import VERSION
if VERSION < (1, 8):
    from django.db.backends.creation import BaseDatabaseCreation
else:
    from django.db.backends.base.creation import BaseDatabaseCreation


class ElasticsearchCreation(BaseDatabaseCreation):

    def make_mapping(self, model):
        mappings = {}

        for field_name in model.get_fields():
            try:
                field = model._meta.get_field(field_name)
            except FieldDoesNotExist:
                # abstract field
                mapping = {}
            else:
                mapping = {'type': self.connection.data_types.get(
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

    def _get_index_name(self):
        # Note: ugly but get_create_model is called from another instance
        if 'test' in sys.argv:
            return self._get_test_db_name()
        return self.connection.settings_dict['NAME']

    def sql_create_model(self, model, *args, **kwargs):
        from django_elasticsearch.models import EsIndexable

        if isinstance(model, EsIndexable):
            index = self._get_index_name()
            es_client = self.connection.cursor()
            es_client.indices.put_mapping(index=index,
                                          doc_type=model.es.get_doc_type(),
                                          body=self.make_mapping(model))
        return [], {}

    def sql_destroy_model(self, model, *args, **kwargs):
        from django_elasticsearch.models import EsIndexable

        if isinstance(model, EsIndexable):
            es_client = self.connection.cursor()
            es_client.indices.delete_mapping(index=model.es.get_index(),
                                             doc_type=model.es.get_doc_type())

    def _create_test_db(self, *args, **kwargs):
        test_index_name = self._get_test_db_name()
        body = self.connection.settings_dict.get('OPTIONS', {})
        es_client = self.connection.cursor()
        es_client.indices.create(index=test_index_name,
                                 body=body,
                                 ignore=400)  # the index already exists

    def destroy_test_db(self, *args, **kwargs):
        test_index_name = self._get_test_db_name()
        es_client = self.connection.cursor()
        es_client.indices.delete(index=test_index_name,
                                 ignore=400)
