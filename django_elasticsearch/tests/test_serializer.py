import datetime

from django.test import TestCase

from django_elasticsearch.utils import dict_depth
from django_elasticsearch.managers import es_client
from django_elasticsearch.tests.utils import withattrs
from django_elasticsearch.serializers import EsJsonSerializer
from django_elasticsearch.serializers import EsSimpleJsonSerializer

from test_app.models import Dummy
from test_app.models import Test2Model


class CustomSerializer(EsJsonSerializer):
    def serialize_char(self, instance, field_name):
        return u'FOO'


class EsJsonSerializerTestCase(TestCase):
    def setUp(self):
        Test2Model.es.flush()
        self.target = Dummy.objects.create(foo='test')
        self.instance = Test2Model.objects.create(fk=self.target,
                                                  oto=self.target)
        # to test for infinite nested recursion
        self.instance.fkself = self.instance
        self.instance.save()

        self.instance.mtm.add(self.target)

        # reverse relations
        self.target.reversefk = self.instance
        self.target.save()
        self.target.reversem2m.add(self.instance)

    def tearDown(self):
        super(EsJsonSerializerTestCase, self).tearDown()
        es_client.indices.delete(index=Test2Model.es.get_index())

    def test_serialize(self):
        obj = self.instance.es.serialize()
        self.assertTrue(isinstance(obj, basestring))

    @withattrs(Test2Model.Elasticsearch, 'serializer_class',
               'django_elasticsearch.serializers.EsJsonSerializer')
    def test_dynamic_serializer_import(self):
        obj = self.instance.es.serialize()
        self.assertTrue(isinstance(obj, basestring))

    def test_deserialize(self):
        source = {
            'char': 'char test',
            'text': 'text\ntest',
            'email': 'test@test.com',
            'filef': 'f/test.png',
            'filepf': 'f/test/test.png',
            'ipaddr': '192.168.0.1',
            'genipaddr': '192.168.0.2',
            'slug': 'test',
            'url': 'http://www.perdu.com/',
            
            'intf': 42,
            'bigint': 922337203685477585,
            'intlist': [1, 2, 3],
            'floatf': 15.5,
            'dec': 5/3,
            'posint': 13,
            'smint': -5,
            'possmint': 6,

            'boolf': True,
            'nullboolf': None,

            'datef': '2017-05-02',
            'datetf': {'iso': '2017-05-02T15:22:05.5432'},
            'timef': '05:57:44',
        }

        instance = Test2Model.es.deserialize(source)
        self.assertTrue(isinstance(instance, Test2Model))

        self.assertEqual(instance.char, 'char test')
        self.assertEqual(instance.text, 'text\ntest')
        self.assertEqual(instance.email, 'test@test.com')
        self.assertEqual(instance.filef, 'f/test.png')
        self.assertEqual(instance.filepf, 'f/test/test.png')
        self.assertEqual(instance.ipaddr, '192.168.0.1')
        self.assertEqual(instance.genipaddr, '192.168.0.2')
        self.assertEqual(instance.slug, 'test')
        self.assertEqual(instance.url, 'http://www.perdu.com/')

        self.assertEqual(instance.intf, 45)
        self.assertEqual(instance.bigint, 922337203685477585)
        self.assertEqual(instance.intlist, [1, 2, 3])
        self.assertEqual(instance.floatf, 15.5)
        self.assertEqual(instance.dec, 5/3)
        self.assertEqual(instance.posint, 13)
        self.assertEqual(instance.smint, -5)
        self.assertEqual(instance.possmint, 6)

        self.assertEqual(instance.boolf, True)
        self.assertEqual(instance.nullboolf, None)

        self.assertEqual(instance.datef, datetime.datetime(2017, 5, 2, 0, 0))
        self.assertEqual(instance.datetf, datetime.datetime(2017, 5, 2, 15, 22, 5, 543200))
        self.assertEqual(instance.timef, datetime.datetime(1900, 1, 1, 5, 57, 44))

        self.assertRaises(ValueError, instance.save)

    def test_deserialize_related(self):
        source = {
            'fk': {'id': self.target.id, 'foo': 'test'},
            'oto': {'id': self.target.id, 'foo': 'test'},
            'fkself': {'id': self.instance.id, 'char': 'test'},
            'mtm': [{'id': self.target.id, 'foo': 'test'}]
        }

        with self.assertNumQueries(0):
            instance = Test2Model.es.deserialize(source)
        self.assertTrue(isinstance(instance, Test2Model))

        self.assertTrue(isinstance(instance.fk, Dummy))
        self.assertEqual(instance.fk.id, self.target.id)
        self.assertTrue(isinstance(instance.oto, Dummy))
        self.assertEqual(instance.oto.id, self.target.id)
        self.assertTrue(hasattr(instance.mtm, '__iter__'))  # need something more explicit
        self.assertEqual(instance.mtm[0].id, self.target.id)

    @withattrs(Test2Model.Elasticsearch, 'serializer_class', CustomSerializer)
    def test_custom_serializer(self):
        json = self.instance.es.serialize()
        self.assertIn('"char": "FOO"', json)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'fk'])
    def test_nested_fk(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        expected = {'id': 1, 'fk': {'id':1, 'foo': 'test'}}
        self.assertEqual(obj, expected)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'oto'])
    def test_nested_oto(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        expected = {'id': 1, 'oto': {'id':1, 'foo': 'test'}}
        self.assertEqual(obj, expected)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'fkself'])
    def test_self_fk_depth_test(self):
        Test2Model.es.serializer = None  # reset cache
        serializer = Test2Model.es.get_serializer(max_depth=3)
        obj = serializer.format(self.instance)
        self.assertEqual(dict_depth(obj), 3)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'mtm'])
    def test_nested_m2m(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        expected = {'id': 1, 'mtm': [{'id':1, 'foo': 'test'},]}
        self.assertEqual(obj, expected)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['abstract_prop', 'abstract_method'])
    def test_abstract_field(self):
        serializer = Test2Model.es.get_serializer()        
        obj = serializer.format(self.instance)
        expected = {'abstract_method': 'woot', 'abstract_prop': 'weez'}
        self.assertEqual(obj, expected)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['foo',])
    def test_unknown_field(self):
        with self.assertRaises(AttributeError):
            self.instance.es.serialize()

    def test_specific_field_method(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        self.assertEqual(obj["intf"], 42)

        instance = Test2Model.es.deserialize(obj)
        self.assertEqual(instance.intf, 45)

    def test_type_specific_field_method(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        self.assertTrue(type(obj["datetf"]) is dict)

        instance = Test2Model.es.deserialize({"datetf": obj["datetf"]})
        self.assertEqual(instance.datetf, self.instance.datetf)

    @withattrs(Test2Model.Elasticsearch, 'serializer_class', EsSimpleJsonSerializer)
    def test_simple_serializer(self):
        results = Test2Model.es.deserialize([{'id': self.instance.pk},])
        self.assertTrue(self.instance in results)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'dummies'])
    def test_reverse_fk(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        expected = {'id': 1, 'dummies': [{'id':1, 'foo': 'test'},]}
        self.assertEqual(obj, expected)

    @withattrs(Test2Model.Elasticsearch, 'fields', ['id', 'dummiesm2m'])
    def test_serialize_reverse_m2m(self):
        serializer = Test2Model.es.get_serializer()
        obj = serializer.format(self.instance)
        expected = {'id': 1, 'dummiesm2m': [{'id':1, 'foo': 'test'},]}
        self.assertEqual(obj, expected)

    def test_deserialize_reverse_relationships(self):
        # make sure no sql query is done
        instance = Test2Model.es.deserialize({'dummies': [{'id':1, 'foo': 'test'},],
                                              'dummiesm2m': [{'id':1, 'foo': 'test'},]})
        self.assertTrue(isinstance(instance, Test2Model))

        self.assertEqual(len(instance.dummies), 1)
        self.assertTrue(isinstance(instance.dummies[0], Dummy))
        self.assertEqual(instance.dummies[0].foo, 'test')

        self.assertEqual(len(instance.dummiesm2m), 1)
        self.assertTrue(isinstance(instance.dummiesm2m[0], Dummy))
        self.assertEqual(instance.dummiesm2m[0].foo, 'test')
