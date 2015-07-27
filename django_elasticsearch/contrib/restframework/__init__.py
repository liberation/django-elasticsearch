from rest_framework import VERSION

from django_elasticsearch.contrib.restframework.base import AutoCompletionMixin

if int(VERSION[0]) < 3:
    from django_elasticsearch.contrib.restframework.restframework2 import IndexableModelMixin
    from django_elasticsearch.contrib.restframework.restframework2 import ElasticsearchFilterBackend
else:
    from django_elasticsearch.contrib.restframework.restframework3 import IndexableModelMixin
    from django_elasticsearch.contrib.restframework.restframework3 import ElasticsearchFilterBackend

__all__ = [ElasticsearchFilterBackend,
           IndexableModelMixin,
           AutoCompletionMixin]
