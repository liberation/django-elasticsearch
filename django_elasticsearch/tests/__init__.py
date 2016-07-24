from django_elasticsearch.tests.test_indexable import EsIndexableTestCase
from django_elasticsearch.tests.test_indexable import EsAutoIndexTestCase
from django_elasticsearch.tests.test_qs import EsQuerysetTestCase
from django_elasticsearch.tests.test_views import EsViewTestCase
from django_elasticsearch.tests.test_serializer import EsJsonSerializerTestCase
from django_elasticsearch.tests.test_restframework import EsRestFrameworkTestCase


__all__ = ['EsQuerysetTestCase',
           'EsViewTestCase',
           'EsIndexableTestCase',
           'EsAutoIndexTestCase',
           'EsJsonSerializerTestCase',
           'EsRestFrameworkTestCase']
