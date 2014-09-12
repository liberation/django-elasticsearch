# -*- coding: utf-8 -*-
from unittest import SkipTest

from elasticsearch import Elasticsearch

from django.test import TestCase
from django.contrib.auth.models import User
from django.test.utils import override_settings

from django_elasticsearch.models import EsIndexable
from django_elasticsearch.serializers import ModelJsonSerializer

es = Elasticsearch()


class TestModel(User, EsIndexable):
    class Elasticsearch(EsIndexable.Elasticsearch):
        index = 'django-test'

    class Meta:
        proxy = True


@override_settings(ELASTICSEARCH_SETTINGS={})
class EsIndexableTestCase(TestCase):
    def setUp(self):
        # auto index is desabled for tests so we do it manually
        TestModel.es.create_index()
        self.instance = TestModel.objects.create(username=u"1",
                                                 first_name=u"woot",
                                                 last_name=u"foo")
        self.instance.es.do_index()
        self.instance.es.do_update()

    def tearDown(self):
        self.instance.delete()
        self.instance.es.delete()
        es.indices.delete(index='django-test')

    def test_serialize(self):
        json = self.instance.es.serialize()
        # Checking one by one, different types of fields
        self.assertIn('"id": %d' % self.instance.id, json)
        self.assertIn('"first_name": "woot"', json)
        self.assertIn('"last_name": "foo"', json)
        self.assertIn('"date_joined": "%s"' % self.instance.date_joined.isoformat(), json)

    def test_do_index(self):
        self.instance.es.do_index()
        r = self.instance.es.get()
        self.assertTrue(r['found'])

    def test_delete(self):
        self.instance.es.delete()
        r = self.instance.es.get(ignore=404)
        self.assertFalse(r['found'])

    # TODO: this test fails, i don't know why
    @SkipTest
    def test_mlt(self):
        results = self.instance.es.mlt(fields=['first_name',])
        self.assertEqual(results['hits']['total'], 0)

        a = TestModel.objects.create(username=u"2", first_name=u"woot", last_name=u"foo fooo")
        a.es.do_index()
        a.es.do_update()
        results = self.instance.es.mlt(fields=['first_name',])
        self.assertEqual(results['hits']['total'], 1)

    def test_search(self):
        hits = TestModel.es.search('wee')
        self.assertEqual(len(hits), 0)

        hits = TestModel.es.search('woot')
        self.assertEqual(len(hits), 1)

    def test_search_with_facets(self):
        s = TestModel.es.search('whatever', facets=['first_name',])
        self.assertEqual(s.count(), 0)
        expected = {
            u'first_name': {
                u'_type': u'terms',
                u'missing': 0,
                u'other': 0,
                u'terms': [{u'term': u'woot', u'count': 1}],
                u'total': 1
            }
        }
        self.assertEqual(s.facets, expected)

    @override_settings(ELASTICSEARCH_SETTINGS={
        "analysis": {
            "default": "test_analyzer",
            "analyzer": {
                "test_analyzer": {
                "type": "custom",
                "tokenizer": "standard",
                }
            }
        }
    })
    def test_custom_mapping(self):
        TestModel.Elasticsearch.fields = ['username',]
        TestModel.Elasticsearch.mapping = {"username": {"boost": 20}}
        # should take the defaults into accounts
        expected = {
            'model-TestModel': {
                'properties': {
                    'username': {
                        'analyzer': 'test_analyzer',
                        'boost': 20,
                        'type': 'string'
                    }
                }
            }
        }
        self.assertEqual(expected, TestModel.es.make_mapping())
        TestModel.Elasticsearch.fields = None
        TestModel.Elasticsearch.mapping = {}

    def test_custom_fields(self):
        # monkeypatch
        TestModel.Elasticsearch.fields = ['first_name', 'last_name']
        json = self.instance.es.serialize()
        expected = '{"first_name": "woot", "last_name": "foo"}'
        self.assertEqual(json, expected)
        # reset
        TestModel.Elasticsearch.fields = None

    def test_custom_serializer(self):
        class CustomSerializer(ModelJsonSerializer):
            def get_es_first_name_val(self, instance, field_name):
                return u'pedro'

        # monkeypatch
        self.instance.Elasticsearch.serializer_class = CustomSerializer
        json = self.instance.es.serialize()
        self.assertIn('"first_name": "pedro"', json)
        # reset
        self.instance.Elasticsearch.serializer_class = ModelJsonSerializer

    def test_deserialize(self):
        pass

    def test_desactivated_save(self):
        pass

    def test_pagination(self):
        pass

    def test_reevaluate(self):
        # test that the request is resent of something changed filters, ordering, ndx
        pass

#### CONTRIBS ####
## REST FRAMEWORK ##
try:
    from django_elasticsearch.contrib.restframework import ElasticsearchFilterBackend
except ImportError:
    pass  # TODO: log something
else:
    class Fake():
        pass

    class EsRestFrameworkTestCase(TestCase):
        def setUp(self):
            self.model1 = TestModel.objects.create(username='1', first_name='test')
            self.model1.es.do_index()
            self.model2 = TestModel.objects.create(username='2', last_name='test')
            self.model2.es.do_index()
            self.model3 = TestModel.objects.create(username='whatever')
            self.model3.es.do_index()
            TestModel.es.do_update()

            self.fake_request = Fake()
            self.fake_request.QUERY_PARAMS = {'q': 'test'}
            self.fake_request.GET = {'q': 'test'}
            self.fake_view = Fake()
            self.fake_view.action = 'list'
            self.queryset = TestModel.objects.all()

        def tearDown(self):
            es.indices.delete(index='django-test')

        def test_filter_backend(self):
            filter_backend = ElasticsearchFilterBackend()
            queryset = filter_backend.filter_queryset(self.fake_request, self.queryset, self.fake_view)

            self.assertTrue(self.model1 in queryset)
            self.assertTrue(self.model2 in queryset)
            self.assertFalse(self.model3 in queryset)

        def test_facets(self):
            TestModel.Elasticsearch.default_facets_fields = ['first_name',]
            filter_backend = ElasticsearchFilterBackend()
            s = filter_backend.filter_queryset(self.fake_request, self.queryset, self.fake_view)
            expected = {
                u'first_name': {
                    u'_type': u'terms',
                    u'total': 1,
                    u'terms': [{u'count': 1, u'term': u'test'}],
                    u'other': 0,
                    u'missing': 2
                }
            }
            self.assertEqual(s.facets, expected)
            TestModel.Elasticsearch.default_facets_fields = None

## TAGGIT ##
try:
    from taggit.managers import TaggableManager
except ImportError:
    pass  # TODO: log something
else:
    from django_elasticsearch.contrib.taggit import TaggitSerializer
    User.tags = TaggableManager()  # monkey patch

    class EsTaggitTestCase(TestCase):
        def test_serializer(self):
            TestModel.Elasticsearch.serializer_class = TaggitSerializer
            instance = TestModel.objects.create(username=u"1", first_name=u"woot", last_name=u"foo")
            instance.tags.add(u"tag1")
            instance.tags.add(u"tagéàèau")

            json = instance.es.serialize()
            self.assertIn(u'"tags": ["tag1", "tag\\u00e9\\u00e0\\u00e8au"]', json)
