from rest_framework import VERSION

if int(VERSION[0]) < 3:
    from django_elasticsearch.contrib.restframework.restframework2 import ElasticsearchFilterBackend
    from django_elasticsearch.contrib.restframework.restframework2 import IndexableModelMixin
    from django_elasticsearch.contrib.restframework.restframework2 import AutoCompletionMixin
else:
    from django_elasticsearch.contrib.restframework.restframework3 import ElasticsearchFilterBackend
    from django_elasticsearch.contrib.restframework.restframework3 import IndexableModelMixin
    from django_elasticsearch.contrib.restframework.restframework3 import AutoCompletionMixin


__all__ = [ElasticsearchFilterBackend,
           IndexableModelMixin,
           AutoCompletionMixin]
