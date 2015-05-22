# -*- coding: utf-8 -*-
import json as json_serializer

from elasticsearch import NotFoundError

from django.test import TestCase
from django.test.utils import override_settings

from django_elasticsearch.managers import es_client
from django_elasticsearch.tests.utils import withattrs
from django_elasticsearch.tests.models import TestModel
from django_elasticsearch.tests.models import TestModelESSerializer
from django_elasticsearch.serializers import ModelJsonSerializer


class CustomSerializer(ModelJsonSerializer):
    def serialize_first_name(self, instance, field_name):
        return u'pedro'


class EsIndexableTestCase(TestCase):
    def setUp(self):
        # auto index is disabled for tests so we do it manually
        TestModel.es.flush()
        self.instance = TestModel.objects.create(username=u"1",
                                                 first_name=u"woot",
                                                 last_name=u"foo")
        self.instance.es.do_index()
        TestModel.es.do_update()

    def tearDown(self):
        super(EsIndexableTestCase, self).tearDown()
        es_client.indices.delete(index=TestModel.es.get_index())

    def _serialize(self):
        json = self.instance.es.serialize()
        # Checking one by one, different types of fields
        self.assertIn('"id": %d' % self.instance.id, json)
        self.assertIn('"first_name": "woot"', json)
        self.assertIn('"last_name": "foo"', json)

        return json

    def test_serializer(self):
        json = self._serialize()
        s = self.instance.es.serializer.serialize_date_joined(self.instance, 'date_joined')
        self.assertIn('"date_joined": %s' % json_serializer.dumps(s), json)

    @withattrs(TestModel.Elasticsearch, 'serializer_class',
               'django_elasticsearch.serializers.ModelJsonSerializer')
    def test_dynamic_serializer_import(self):
        self.instance.es.serializer = None  # reset cached property
        json = self._serialize()
        self.instance.es.serializer = None  # reset cached property
        self.assertIn('"date_joined": "%s"' % self.instance.date_joined.isoformat(), json)

    def test_deserialize(self):
        instance = TestModel.es.deserialize({'username':'test'})
        self.assertEqual(instance.username, 'test')
        self.assertRaises(ValueError, instance.save)

    def test_do_index(self):
        self.instance.es.do_index()
        r = TestModel.es.deserialize(self.instance.es.get())
        self.assertTrue(isinstance(r, TestModel))

    def test_delete(self):
        self.instance.es.delete()
        with self.assertRaises(NotFoundError):
            self.instance.es.get()

    def test_mlt(self):
        q = self.instance.es.mlt(mlt_fields=['first_name',], min_term_freq=1, min_doc_freq=1)
        results = q.deserialize()

        self.assertEqual(len(results), 0)
        a = TestModel.objects.create(username=u"2", first_name=u"woot", last_name=u"foo fooo")
        a.es.do_index()
        a.es.do_update()

        results = self.instance.es.mlt(mlt_fields=['first_name',], min_term_freq=1, min_doc_freq=1).deserialize()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], a)

    def test_search(self):
        hits = TestModel.es.search('wee')
        self.assertEqual(len(hits), 0)

        hits = TestModel.es.search('woot')
        self.assertEqual(len(hits), 1)

    def test_search_with_facets(self):
        s = TestModel.es.search('whatever').facet(['first_name',])
        self.assertEqual(s.count(), 0)
        expected = {u'doc_count': 1,
                    u'first_name': {u'buckets': [{u'doc_count': 1,
                                                  u'key': u'woot'}]}}
        self.assertEqual(s.facets, expected)

    def test_fuzziness(self):
        hits = TestModel.es.search('woo')  # instead of woot
        self.assertEqual(len(hits), 1)

        hits = TestModel.es.search('woo', fuzziness=0)
        self.assertEqual(len(hits), 0)

        hits = TestModel.es.search('waat', fuzziness=2)
        self.assertEqual(len(hits), 1)

    @withattrs(TestModel.Elasticsearch, 'fields', ['username'])
    @withattrs(TestModel.Elasticsearch, 'mappings', {"username": {"boost": 20}})
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
            TestModel.Elasticsearch.doc_type: {
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
        # reset cache on _fields
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
        TestModel.es._mapping = None
        TestModel.es.flush()
        TestModel.es.do_update()

        expected = {
            u'username': {u'index': u'not_analyzed', u'type': u'string'},
            u'date_joined': {u'properties': {
                u'iso': {u'format': u'dateOptionalTime', u'type': u'date'},
                u'date': {u'type': u'string'},
                u'time': {u'type': u'string'}
            }}
        }

        # Reset the eventual cache on the Model mapping
        mapping = TestModel.es.get_mapping()
        TestModel.es._mapping = None
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

    def test_custom_serializer(self):
        old_serializer = self.instance.es.serializer
        self.instance.es.serializer = CustomSerializer(TestModel)
        json = self.instance.es.serialize()
        self.assertIn('"first_name": "pedro"', json)
        self.instance.es.serializer = old_serializer

    def test_custom_index(self):
        es_client.indices.exists(TestModel.Elasticsearch.index)

    def test_custom_doc_type(self):
        es_client.indices.exists_type('django-test', 'test-doc-type')

    def test_reevaluate(self):
        # test that the request is resent if something changed filters, ordering, ndx
        TestModel.es.flush()
        TestModel.es.do_update()

        q = TestModel.es.search('woot')
        self.assertTrue(self.instance in q.deserialize())  # evaluate
        q = q.filter(last_name='grut')
        self.assertFalse(self.instance in q.deserialize())  # evaluate

    def test_diff(self):
        self.assertEqual(self.instance.es.diff(), {})
        self.instance.first_name = 'pouet'

        expected = {
            u'first_name': {
            'es': u'woot',
            'db': u'pouet'
            }
        }
        self.assertEqual(self.instance.es.diff(), expected)
