# -*- coding: utf-8 -*-
from elasticsearch import NotFoundError

from django.test import TestCase
from django.test.utils import override_settings

from django_elasticsearch.managers import es_client
from django_elasticsearch.tests.utils import withattrs

from test_app.models import Test2Model


class EsIndexableTestCase(TestCase):
    def setUp(self):
        # auto index is disabled for tests so we do it manually
        Test2Model.es.flush()
        self.instance = Test2Model.objects.create(email=u"1",
                                                 char=u"woot",
                                                 text=u"foo")
        self.instance.es.do_index()
        Test2Model.es.do_update()

    def tearDown(self):
        super(EsIndexableTestCase, self).tearDown()
        es_client.indices.delete(index=Test2Model.es.get_index())

    def test_needs_instance(self):
        with self.assertRaises(AttributeError):
            Test2Model.es.do_index()

    def test_check_cluster(self):
        self.assertEqual(Test2Model.es.check_cluster(), True)

    def test_get_api(self):
        self.assertEqual(self.instance.es.get(),
                         Test2Model.es.get(pk=self.instance.pk),
                         Test2Model.es.get(id=self.instance.pk))

        with self.assertRaises(AttributeError):
            Test2Model.es.get()

    def test_do_index(self):
        self.instance.es.do_index()
        r = es_client.get(index=self.instance.es.get_index(),
                          doc_type=self.instance.es.get_doc_type(),
                          id=self.instance.id)
        self.assertEqual(r['_source']['id'], self.instance.id)

    def test_delete(self):
        self.instance.es.delete()
        with self.assertRaises(NotFoundError):
            self.instance.es.get()

    def test_mlt(self):
        qs = self.instance.es.mlt(mlt_fields=['char',], min_term_freq=1, min_doc_freq=1)
        self.assertEqual(qs.count(), 0)

        a = Test2Model.objects.create(email=u"2", char=u"woot", text=u"foo fooo")
        a.es.do_index()
        a.es.do_update()

        results = self.instance.es.mlt(mlt_fields=['char',], min_term_freq=1, min_doc_freq=1).deserialize()
        self.assertEqual(results.count(), 1)
        self.assertEqual(results[0], a)

    def test_search(self):
        hits = Test2Model.es.search('wee')
        self.assertEqual(hits.count(), 0)

        hits = Test2Model.es.search('woot')
        self.assertEqual(hits.count(), 1)

    def test_search_with_facets(self):
        s = Test2Model.es.search('whatever').facet(['char',])
        self.assertEqual(s.count(), 0)
        expected = [{u'doc_count': 1, u'key': u'woot'}]
        self.assertEqual(s.facets['doc_count'], 1)
        self.assertEqual(s.facets['char']['buckets'], expected)

    def test_fuzziness(self):
        hits = Test2Model.es.search('woo')  # instead of woot
        self.assertEqual(hits.count(), 1)

        hits = Test2Model.es.search('woo', fuzziness=0)
        self.assertEqual(hits.count(), 0)

        hits = Test2Model.es.search('waat', fuzziness=2)
        self.assertEqual(hits.count(), 1)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['email'])
    @withattrs(Test2Model.Elasticsearch, 'mappings', {"email": {"boost": 20}})
    @withattrs(Test2Model.Elasticsearch, 'completion_fields', ['email'])
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
            Test2Model.Elasticsearch.doc_type: {
                'properties': {
                    'email': {
                        'analyzer': 'test_analyzer',
                        'boost': 20,
                        'type': 'string'
                    },
                    'email_complete': {
                        'type': 'completion'
                    }
                }
            }
        }
        # reset cache on _fields
        self.assertEqual(expected, Test2Model.es.make_mapping())

    @withattrs(Test2Model.Elasticsearch, 'completion_fields', ['char'])
    def test_auto_completion(self):
        # Note: we need to call setUp again to create the mapping taking
        # the new field(s) into account :(
        Test2Model.es.flush()
        Test2Model.es.do_update()
        data = Test2Model.es.complete('char', 'woo')
        self.assertTrue('woot' in data)

    def _test_mapping(self, expected):
        Test2Model.es._mapping = None
        Test2Model.es.flush()
        Test2Model.es.do_update()

        # Reset the eventual cache on the Model mapping
        mapping = Test2Model.es.get_mapping()
        Test2Model.es._mapping = None
        self.assertEqual(expected, mapping)        

    @withattrs(Test2Model.Elasticsearch, 'fields', ['email', 'datef'])
    def test_get_mapping(self):
        expected = {u'datef': {u'format': u'dateOptionalTime', u'type': u'date'},
                    u'email': {u'index': u'not_analyzed', u'type': u'string'}}
        self._test_mapping(expected)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'dummies', 'dummiesm2m'])
    def test_reverse_relationship_mapping(self):
        expected = {u'id': {},
                    u'dummies': {},
                    u'dummiesm2M': {}}

        self._test_mapping(expected)

    def test_get_settings(self):
        # Note i don't really know what's in there so i just check
        # it doesn't crash and deserialize well.
        settings = Test2Model.es.get_settings()
        self.assertEqual(dict, type(settings))

    def test_custom_index(self):
        es_client.indices.exists(Test2Model.Elasticsearch.index)

    def test_custom_doc_type(self):
        es_client.indices.exists_type('django-test', 'test-doc-type')

    def test_reevaluate(self):
        # test that the request is resent if something changed filters, ordering, ndx
        Test2Model.es.flush()
        Test2Model.es.do_update()

        q = Test2Model.es.search('woot')
        self.assertTrue(self.instance in q.deserialize())  # evaluate
        q = q.filter(text='grut')
        self.assertFalse(self.instance in q.deserialize())  # evaluate

    def test_diff(self):
        self.assertEqual(self.instance.es.diff(), {})
        self.instance.char = 'pouet'

        expected = {
            u'char': {
            'es': u'woot',
            'db': u'pouet'
            }
        }

        self.assertEqual(self.instance.es.diff(), expected)
        self.assertEqual(self.instance.es.diff(source=self.instance.es.get()), {})

        # force diff to reload from db
        deserialized = Test2Model.es.all().deserialize()[0]
        self.assertEqual(deserialized.es.diff(), {})
