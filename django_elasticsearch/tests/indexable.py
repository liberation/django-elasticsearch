# -*- coding: utf-8 -*-
from unittest import SkipTest

from django.test import TestCase
from django.test.utils import override_settings

from django_elasticsearch.managers import es_client
from django_elasticsearch.tests.utils import withattrs
from django_elasticsearch.tests.models import TestModel
from django_elasticsearch.serializers import ModelJsonSerializer


class CustomSerializer(ModelJsonSerializer):
    def get_es_first_name_val(self, instance, field_name):
        return u'pedro'


@override_settings(ELASTICSEARCH_SETTINGS={})
class EsIndexableTestCase(TestCase):
    def setUp(self):
        # auto index is disabled for tests so we do it manually
        TestModel.es.create_index(ignore=True)
        self.instance = TestModel.objects.create(username=u"1",
                                                 first_name=u"woot",
                                                 last_name=u"foo")
        self.instance.es.do_index()
        TestModel.es.do_update()

    def tearDown(self):
        super(EsIndexableTestCase, self).tearDown()
        es_client.indices.delete(index=TestModel.es.get_index())

    def test_serialize(self):
        json = self.instance.es.serialize()
        # Checking one by one, different types of fields
        self.assertIn('"id": %d' % self.instance.id, json)
        self.assertIn('"first_name": "woot"', json)
        self.assertIn('"last_name": "foo"', json)
        self.assertIn('"date_joined": "%s"' % self.instance.date_joined.isoformat(), json)

    def test_deserialize(self):
        instance = TestModel.es.deserialize({'username':'test'})
        self.assertEqual(instance.username, 'test')
        self.assertRaises(ValueError, instance.save)

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

    @withattrs(TestModel.Elasticsearch, 'fields', ['username'])
    @withattrs(TestModel.Elasticsearch, 'mapping', {"username": {"boost": 20}})
    @withattrs(TestModel.Elasticsearch, 'completion_fields', ['username'])
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
        # should take the defaults into accounts
        expected = {
            'model-TestModel': {
                'properties': {
                    'username': {
                        'analyzer': 'test_analyzer',
                        'boost': 20,
                        'type': 'string'
                    },
                    'username_complete': {
                        'type': 'completion'
                    }
                }
            }
        }
        self.assertEqual(expected, TestModel.es.make_mapping())

    @withattrs(TestModel.Elasticsearch, 'completion_fields', ['first_name'])
    def test_auto_completion(self):
        # Note: we need to call setUp again to create the mapping taking
        # the new field(s) into account :(
        TestModel.es.flush()
        TestModel.es.do_update()
        data = TestModel.es.complete('first_name', 'woo')
        self.assertTrue('woot' in data)

    @withattrs(TestModel.Elasticsearch, 'fields', ['username', 'date_joined'])
    def test_get_mapping(self):
        TestModel.es.flush()
        TestModel.es.do_update()

        expected = {
            'username': {'type': 'string'},
            'date_joined': {u'type': u'date', u'format': u'dateOptionalTime'}
        }

        mapping = TestModel.es.get_mapping()
        self.assertEqual(expected, mapping)

    def test_get_settings(self):
        # Note i don't really know what's in there so i just check
        # it doesn't crash and deserialize well.
        settings = TestModel.es.get_settings()
        self.assertEqual(dict, type(settings))

    @withattrs(TestModel.Elasticsearch, 'fields', ['first_name', 'last_name'])
    def test_custom_fields(self):
        json = self.instance.es.serialize()
        expected = '{"first_name": "woot", "last_name": "foo"}'
        self.assertEqual(json, expected)

    @withattrs(TestModel.Elasticsearch, 'serializer_class', CustomSerializer)
    def test_custom_serializer(self):
        json = self.instance.es.serialize()
        self.assertIn('"first_name": "pedro"', json)

    def test_reevaluate(self):
        # test that the request is resent if something changed filters, ordering, ndx
        q = TestModel.es.search('woot')
        self.assertTrue(self.instance in q)  # evaluate
        q = q.filter(last_name='grut')
        self.assertFalse(self.instance in q)  # evaluate
