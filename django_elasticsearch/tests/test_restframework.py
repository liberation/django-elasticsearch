# -*- coding: utf-8 -*-
import mock

from rest_framework import status
from rest_framework import VERSION
from rest_framework.settings import api_settings
from rest_framework.test import APIClient

from django.test import TestCase
from django.db.models.query import QuerySet
from django.contrib.auth.models import User

from elasticsearch import TransportError

from django_elasticsearch.client import es_client
from django_elasticsearch.tests.utils import withattrs
from django_elasticsearch.contrib.restframework import ElasticsearchFilterBackend
from test_app.models import TestModel


class Fake():
    pass


class EsRestFrameworkTestCase(TestCase):
    def setUp(self):
        TestModel.es.create_index()

        self.model1 = TestModel.objects.create(username='1', first_name='test')
        self.model1.es.do_index()
        self.model2 = TestModel.objects.create(username='2', last_name='test')
        self.model2.es.do_index()
        self.model3 = TestModel.objects.create(username='whatever')
        self.model3.es.do_index()
        TestModel.es.do_update()

        self.fake_request = Fake()

        if int(VERSION[0]) < 3:
            self.fake_request.QUERY_PARAMS = {api_settings.SEARCH_PARAM: 'test'}
        else:
            self.fake_request.query_params = {api_settings.SEARCH_PARAM: 'test'}

        self.fake_request.GET = {api_settings.SEARCH_PARAM: 'test'}
        self.fake_view = Fake()
        self.fake_view.action = 'list'

    def tearDown(self):
        super(EsRestFrameworkTestCase, self).tearDown()
        es_client.indices.delete(index=TestModel.es.get_index())

    def _test_filter_backend(self):
        queryset = TestModel.es.all()
        filter_backend = ElasticsearchFilterBackend()
        queryset = filter_backend.filter_queryset(self.fake_request, queryset, self.fake_view)

        l = queryset.deserialize()
        self.assertTrue(self.model1 in l)
        self.assertTrue(self.model2 in l)
        self.assertFalse(self.model3 in l)

    def test_filter_backend(self):
        self._test_filter_backend()

    def test_filter_backend_on_normal_model(self):
        filter_backend = ElasticsearchFilterBackend()
        with self.assertRaises(ValueError):
            filter_backend.filter_queryset(self.fake_request, User.objects.all(), self.fake_view)

    def test_filter_backend_ordering(self):
        queryset = TestModel.es.all()
        filter_backend = ElasticsearchFilterBackend()
        self.fake_view.ordering = ('-username',)
        queryset = filter_backend.filter_queryset(self.fake_request, queryset, self.fake_view).deserialize()

        self.assertEqual(queryset[0].id, self.model2.id)
        self.assertEqual(queryset[1].id, self.model1.id)
        del self.fake_view.ordering

    def test_filter_backend_no_list(self):
        queryset = TestModel.es.all()
        filter_backend = ElasticsearchFilterBackend()
        self.fake_view.action = 'create'
        queryset = filter_backend.filter_queryset(self.fake_request, queryset, self.fake_view)
        # the 'normal' dataflow continues
        self.assertTrue(isinstance(queryset, QuerySet))
        self.fake_view.action = 'list'

    def _test_filter_backend_filters(self):
        r = self.client.get('/rf/tests/', {'username': '1'})
        self.assertEqual(r.data['count'], 1)
        self.assertEqual(r.data['results'][0]['id'], self.model1.id)

    def test_filter_backend_filters(self):
        self._test_filter_backend_filters()

    def test_404(self):
        r = self.client.get('/rf/tests/354xyz/', {'username': '1'})
        self.assertEqual(r.status_code, 404)

    def _test_pagination(self):
        r = self.client.get('/rf/tests/', {'ordering': '-id', 'page': 2, 'page_size':1})
        self.assertEqual(r.data['count'], 3)
        self.assertEqual(r.data['results'][0]['id'], self.model2.id)

    def test_pagination(self):
        self._test_pagination()

    @withattrs(TestModel.Elasticsearch, 'facets_fields', ['first_name',])
    def test_facets(self):
        queryset = TestModel.es.all()
        filter_backend = ElasticsearchFilterBackend()
        s = filter_backend.filter_queryset(self.fake_request, queryset, self.fake_view)
        expected = [{u'doc_count': 1, u'key': u'test'}]
        self.assertEqual(s.facets['doc_count'], 3)
        self.assertEqual(s.facets['first_name']['buckets'], expected)

    @withattrs(TestModel.Elasticsearch, 'facets_fields', ['first_name',])
    def test_faceted_viewset(self):
        r = self.client.get('/rf/tests/', {'q': 'test'})
        self.assertTrue('facets' in r.data)

    @withattrs(TestModel.Elasticsearch, 'suggest_fields', ['first_name'])
    def test_suggestions_viewset(self):
        r = self.client.get('/rf/tests/', {'q': 'tset'})
        self.assertTrue('suggestions' in r.data)
        self.assertEqual(r.data['suggestions']['first_name'][0]['options'][0]['text'], "test")

    @withattrs(TestModel.Elasticsearch, 'completion_fields', ['username'])
    def test_completion_viewset(self):
        # need to re-index :(
        TestModel.es.flush()
        TestModel.es.do_update()

        r = self.client.get('/rf/tests/autocomplete/', {'f': 'username',
                                                        'q': 'what'})
        self.assertTrue('whatever' in r.data)

        r = self.client.get('/rf/tests/autocomplete/', {'f': 'first_name',
                                                        'q': 'woo'})
        # first_name is NOT in the completion_fields -> 404
        self.assertEqual(r.status_code, 404)

    def test_post_put_delete(self):
        client = APIClient()

        # make sure we don't break other methods
        r = client.post('/rf/tests/', {
            'email': u'test@test.com',
            'username': u'test',
            'password': u'test'
        })

        self.assertEqual(r.status_code, status.HTTP_201_CREATED)  # created
        pk = r.data['id']

        r = client.patch('/rf/tests/{0}/'.format(pk), {
            'username': u'test2',
            'password': u'test'
        }, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(TestModel.objects.get(pk=pk).username, 'test2')

        r = client.delete('/rf/tests/{0}/'.format(pk))
        self.assertEqual(r.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(TestModel.objects.filter(pk=pk).exists())

    def test_fallback_gracefully(self):
        # Note: can't use override settings because of how restframework handle settings :(
        #from django_elasticsearch.tests.urls import TestViewSet
        from rest_framework.filters import DjangoFilterBackend, OrderingFilter
        from rest_framework.settings import api_settings

        api_settings.DEFAULT_FILTER_BACKENDS = (DjangoFilterBackend, OrderingFilter)
        # TODO: better way to fake es cluster's death ?

        with mock.patch.object(es_client, 'search') as mock_search:
            mock_search.side_effect = TransportError()
            with mock.patch.object(es_client, 'count') as mock_count:
                mock_count.side_effect = TransportError()
                with mock.patch.object(es_client, 'get') as mock_get:
                    mock_get.side_effect = TransportError()
                    # should fallback to a regular django queryset / filtering
                    r = self.client.get('/rf/tests/')
                    self.assertEqual(r.status_code, 200)
                    self.assertEqual(r.data['filter_status'], 'Failed')
                    self.assertEqual(r.data['count'], 3)
                    self._test_filter_backend_filters()
                    self._test_pagination()
