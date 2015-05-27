from django.contrib.auth.models import User
from django_elasticsearch.models import EsIndexable
from django_elasticsearch.serializers import ModelJsonSerializer


class TestModelESSerializer(ModelJsonSerializer):
    def serialize_favorite_color(self, instance, field_name):
        return getattr(instance, field_name)

    def serialize_date_joined(self, instance, field_name):
        d = getattr(instance, field_name)
        # a rather typical api output
        return {
            'iso': d.isoformat(),
            'date': d.date().isoformat(),
            'time': d.time().isoformat()[:5]
        }

    def deserialize_date_joined(self, source, field_name):
        try:
            return source[field_name]['iso']
        except KeyError:
            return None

    # Note: i want this field to be null instead of u''
    def serialize_email(self, instance, field_name):
        val = getattr(instance, field_name)
        if val == u'':
            return None
        return val


class TestModel(User, EsIndexable):
    class Elasticsearch(EsIndexable.Elasticsearch):
        index = 'django-test'
        doc_type = 'test-doc-type'
        mappings = {
            "username": {"index": "not_analyzed"},
            "date_joined": {"type": "object",
                            "properties": {
                                "iso": {"type": "date"},
                                "date": {"type": "string"},
                                "time": {"type": "string"}
                            }}
        }
        serializer_class = TestModelESSerializer

    @property
    def favorite_color(self):
        return 'red'

    class Meta:
        proxy = True
        ordering = ('id',)
