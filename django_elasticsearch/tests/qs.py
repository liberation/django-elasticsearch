import mock

from django.test import TestCase
from django.test.utils import override_settings

from django_elasticsearch.client import es_client
from django_elasticsearch.managers import EsQueryset
from django_elasticsearch.tests.models import TestModel


@override_settings(ELASTICSEARCH_SETTINGS={})
class EsQuerysetTestCase(TestCase):

    def setUp(self):
        # create a bunch of documents
        TestModel.es.create_index(ignore=True)

        self.t1 = TestModel.objects.create(username=u"woot2", first_name=u"John", last_name=u"Smith")
        self.t1.es.do_index()

        self.t2 = TestModel.objects.create(username=u"woot", first_name=u"Jack", last_name=u"Smith")
        self.t2.es.do_index()

        self.t3 = TestModel.objects.create(username=u"BigMama", first_name=u"Mama", last_name=u"Smith")
        self.t3.es.do_index()

        self.t4 = TestModel.objects.create(username=u"foo", first_name=u"Foo", last_name=u"Bar")
        self.t4.es.do_index()

        TestModel.es.do_update()

    def tearDown(self):
        es_client.indices.delete(index=TestModel.es.get_index())

    def test_all(self):
        qs = TestModel.es.queryset.all()
        self.assertTrue(self.t1 in qs)
        self.assertTrue(self.t2 in qs)
        self.assertTrue(self.t3 in qs)
        self.assertTrue(self.t4 in qs)

    def test_repr(self):
        qs = TestModel.es.queryset.order_by('id')
        expected = str(TestModel.objects.all())
        self.assertEqual(expected, str(qs.all()))

    def test_use_cache(self):
        # Note: we use _make_search_body because it's only called
        # if the cache store is not hit
        fake_body = {'query': {'match': {'_all': 'foo'}}}
        with mock.patch.object(EsQueryset,
                               '_make_search_body') as mocked:
            mocked.return_value = fake_body
            qs = EsQueryset(TestModel)
            # eval
            list(qs)
            # use cache
            list(qs)
        mocked.assert_called_once()

        # same for a sliced query
        with mock.patch.object(EsQueryset,
                               '_make_search_body') as mocked:
            mocked.return_value = fake_body
            # re-eval
            list(qs[0:5])
            # use cache
            list(qs[0:5])
        mocked.assert_called_once()

    def test_facets(self):
        qs = TestModel.es.queryset.facet(['last_name'])
        expected = {u'doc_count': 4,
                    u'last_name': {u'buckets': [{u'doc_count': 3,
                                                 u'key': u'smith'},
                                                {u'doc_count': 1,
                                                 u'key': u'bar'}]}}
        self.assertEqual(expected, qs.facets)

    def test_non_global_facets(self):
        qs = TestModel.es.queryset.facet(['last_name'], use_globals=False).query("Foo")
        expected = {u'last_name': {u'buckets': [{u'doc_count': 1,
                                                 u'key': u'bar'}]}}
        self.assertEqual(expected, qs.facets)

    def test_suggestions(self):
        qs = EsQueryset(TestModel).query('smath').suggest(['last_name'])
        expected = {
            u'last_name': [
                {u'length': 5,
                 u'offset': 0,
                 u'options': [{u'freq': 3,
                               u'score': 0.8,
                               u'text': u'smith'}],
                 u'text': u'smath'}]}
        self.assertEqual(expected, qs.suggestions)

    def test_count(self):
        self.assertEqual(TestModel.es.queryset.count(), 4)
        self.assertEqual(EsQueryset(TestModel).query("John").count(), 1)
        self.assertEqual(EsQueryset(TestModel)
                         .filter(last_name=u"Smith")
                         .count(), 3)

    def test_ordering(self):
        qs = TestModel.es.queryset.order_by('username')
        self.assertTrue(qs[0], self.t3)
        self.assertTrue(qs[1], self.t4)
        self.assertTrue(qs[2], self.t2)
        self.assertTrue(qs[3], self.t1)

    def test_filtering(self):
        qs = TestModel.es.queryset.filter(last_name=u"Smith")
        self.assertTrue(self.t1 in qs)
        self.assertTrue(self.t2 in qs)
        self.assertTrue(self.t3 in qs)
        self.assertTrue(self.t4 not in qs)

    def test_filter_range(self):
        qs = TestModel.es.queryset.filter(id__gt=self.t2.id)
        self.assertTrue(self.t1 not in qs)
        self.assertTrue(self.t2 not in qs)
        self.assertTrue(self.t3 in qs)
        self.assertTrue(self.t4 in qs)

        qs = TestModel.es.queryset.filter(id__lt=self.t2.id)
        self.assertTrue(self.t1 in qs)
        self.assertTrue(self.t2 not in qs)
        self.assertTrue(self.t3 not in qs)
        self.assertTrue(self.t4 not in qs)

        qs = TestModel.es.queryset.filter(id__gte=self.t2.id)
        self.assertTrue(self.t1 not in qs)
        self.assertTrue(self.t2 in qs)
        self.assertTrue(self.t3 in qs)
        self.assertTrue(self.t4 in qs)

        qs = TestModel.es.queryset.filter(id__lte=self.t2.id)
        self.assertTrue(self.t1 in qs)
        self.assertTrue(self.t2 in qs)
        self.assertTrue(self.t3 not in qs)
        self.assertTrue(self.t4 not in qs)

        qs = TestModel.es.queryset.filter(id__range=(self.t2.id, self.t3.id))
        self.assertTrue(self.t1 not in qs)
        self.assertTrue(self.t2 in qs)
        self.assertTrue(self.t3 in qs)
        self.assertTrue(self.t4 not in qs)

    def test_filter_date_range(self):
        qs = TestModel.es.queryset.filter(date_joined__gte=self.t2.date_joined)
        self.assertTrue(self.t1 not in qs)
        self.assertTrue(self.t2 in qs)
        self.assertTrue(self.t3 in qs)
        self.assertTrue(self.t4 in qs)

    def test_excluding(self):
        pass
