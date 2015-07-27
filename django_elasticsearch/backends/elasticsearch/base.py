from django import VERSION
if VERSION < (1, 8):
    from django.db.backends import BaseDatabaseWrapper
    from django.db.backends import BaseDatabaseValidation
    from django.db.backends import BaseDatabaseIntrospection
    from django.db.backends import BaseDatabaseOperations
else:
    from django.db.backends.base.base import BaseDatabaseWrapper
    from django.db.backends.base.validation import BaseDatabaseValidation
    from django.db.backends.base.introspection import BaseDatabaseIntrospection
    from django.db.backends.base.operations import BaseDatabaseOperations

from elasticsearch import Elasticsearch

from django_elasticsearch.backends.elasticsearch.creation import ElasticsearchCreation
from django_elasticsearch.backends.elasticsearch.features import ElasticsearchFeatures


class ElasticsearchValidation(BaseDatabaseValidation):
    pass


class ElasticsearchIntrospection(BaseDatabaseIntrospection):
    def get_table_list(self, cursor):
        mappings = cursor.indices.get_mapping()
        try:
            return mappings[self.connection.settings_dict['NAME']]['mappings'].keys()
        except KeyError:
            return []


class ElasticsearchOperations(BaseDatabaseOperations):
    def quote_name(self, name):
        return name


class DatabaseWrapper(BaseDatabaseWrapper):
    vendor = 'elasticsearch'

    # Note: everything elses maps to 'string'
    data_types = {
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

    # operators = {
    #     'exact': '= %s',
    #     'iexact': 'LIKE %s',
    #     'contains': 'LIKE BINARY %s',
    #     'icontains': 'LIKE %s',
    #     'regex': 'REGEXP BINARY %s',
    #     'iregex': 'REGEXP %s',
    #     'gt': '> %s',
    #     'gte': '>= %s',
    #     'lt': '< %s',
    #     'lte': '<= %s',
    #     'startswith': 'LIKE BINARY %s',
    #     'endswith': 'LIKE BINARY %s',
    #     'istartswith': 'LIKE %s',
    #     'iendswith': 'LIKE %s',
    # }

    def __init__(self, *args, **kwargs):
        super(DatabaseWrapper, self).__init__(*args, **kwargs)

        self.features = ElasticsearchFeatures(self)
        self.ops = ElasticsearchOperations(self)
        self.creation = ElasticsearchCreation(self)
        self.introspection = ElasticsearchIntrospection(self)
        self.validation = ElasticsearchValidation(self)

    def get_connection_params(self):
        try:
            return self.settings_dict['CONNECTION_KWARGS']
        except KeyError:
            return {}

    def get_new_connection(self, params={}):
        p = params
        p.update(self.get_connection_params())
        return Elasticsearch('{0}:{1}'.format(self.settings_dict['HOST'],
                                              self.settings_dict['PORT']), **p)

    def is_usable(self):
        return self.connection.ping()

    #def last_insert_id(self, cursor, index_name, pk_name):
    #    return cursor.lastrowid

    def cursor(self):
        if not self.connection:
            self.connection = self.get_new_connection()
        return self.connection

    #def get_server_version(self):
    #    pass

    def get_server_version(self):
        return self.connection.info()

    def close(self):
        pass

    def _commit(self):
        pass
