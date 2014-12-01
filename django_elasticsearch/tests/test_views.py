import mock

from django.test import TestCase
from django.test.utils import override_settings
from django.utils import simplejson as json

from elasticsearch import TransportError

from django_elasticsearch.managers import es_client
from django_elasticsearch.tests.models import TestModel


@override_settings(ELASTICSEARCH_SETTINGS={})
class EsViewTestCase(TestCase):
    urls = 'django_elasticsearch.tests.urls'

    def setUp(self):
        # auto index is disabled for tests so we do it manually
        TestModel.es.create_index(ignore=True)
        self.instance = TestModel.objects.create(username=u"1",
                                                 first_name=u"woot",
                                                 last_name=u"foo")
        self.instance.es.do_index()
        TestModel.es.do_update()

    def tearDown(self):
        super(EsViewTestCase, self).tearDown()
        es_client.indices.delete(index=TestModel.es.get_index())

    def _test_detail_view(self):
        response = self.client.get('/tests/{id}/'.format(id=self.instance.pk))
        content = json.loads(response.content)
        self.assertEqual(content['first_name'], u"woot")
        self.assertEqual(content['last_name'], u"foo")

    def test_detail_view(self):
        self._test_detail_view()

    def test_fallback_detail_view(self):
        with mock.patch('django_elasticsearch.client.es_client.get') as mock_get:
            mock_get.side_effect = TransportError()
            self._test_detail_view()

    def _test_list_view(self):
        response = self.client.get('/tests/')
        content = json.loads(response.content)
        self.assertTrue('hits' in content)
        self.assertEqual(content['hits']['hits'][0]['_source']['first_name'], u"woot")
        self.assertEqual(content['hits']['hits'][0]['_source']['last_name'], u"foo")

    def test_list_view(self):
        self._test_list_view()

    def test_fallback_list_view(self):
        # Note: in this case views responses don't match because i'm lazy
        with mock.patch('django_elasticsearch.client.es_client.search') as mock_search:
            mock_search.side_effect = TransportError()

            response = self.client.get('/tests/')
            content = json.loads(response.content)
            self.assertEqual(len(content), 1)
            self.assertEqual(content[0]['fields']['first_name'], u"woot")
            self.assertEqual(content[0]['fields']['last_name'], u"foo")
