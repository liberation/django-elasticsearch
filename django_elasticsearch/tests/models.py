from django.contrib.auth.models import User
from django_elasticsearch.models import EsIndexable


class TestModel(User, EsIndexable):
    class Elasticsearch(EsIndexable.Elasticsearch):
        index = 'django-test'

    class Meta:
        proxy = True
        ordering = ('id',)
