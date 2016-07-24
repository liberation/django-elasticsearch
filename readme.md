django_elasticsearch is a wrapper around py-elasticsearch that automates the indexation and search of django models.  
**Note**: if your elasticsearch documents/mappings are not close to django models, this package is probably not for you.

INSTALL
=======
* [Install and launch elasticsearch](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/setup.html) if it's not done already.

* Install [py-elasticsearch](http://www.elasticsearch.org/guide/en/elasticsearch/client/python-api/current/)
    ```shell
    pip install elasticsearch
    ```

* Install django_elasticsearch
    ```shell
    pip install git+https://github.com/liberation/django_elasticsearch.git
    ```
    **Note**: no pypy package yet


ELASTICSEARCH VERSION COMPATIBILITY
===================================

As stated in the python elasticsearch module documentation:


>There are two branches for development - master and 0.4. Master branch is used to track all the changes for Elasticsearch 1.0 and beyond whereas 0.4 tracks Elasticsearch 0.90.
>
>Releases with major version 1 (1.X.Y) are to be used with Elasticsearch 1.* and later, 0.4 releases are meant to work with Elasticsearch 0.90.*.

django_elasticsearch has only been tested with Elasticsearch 1.3.9 and it's corresponding python interface version 1.2.0, but since [the API hasn't change](https://elasticsearch-py.readthedocs.org/en/master/Changelog.html) i'm quite positive that newer and older versions should work fine too, as long as you use the right python module for your Elasticsearch version. [See the official docs on the matter](https://elasticsearch-py.readthedocs.org/en/master/#compatibility).

USAGE
=====

Subclass the models you wish to index/search with ```django_elasticsearch.models.EsIndexable```.
```python
from django.db import models
from django_elasticsearch.models import EsIndexable


MyModel(EsIndexable, models.Model):
    foo = models.CharField(max_length=64)
    [...]

```

Then you can do:
```python
>>> q = MyModel.es.search('value')
>>> q
[{'id': 1, 'foo': 'A value'}, {'id': 2, 'foo': 'Another value'}, ...]
>>> q.deserialize()
[<MyModel #1>, <MyModel #2>, ...]
>>> MyModel.es.get(id=1)
{'id': 1, 'foo': 'A value'}
```
The elasticsearch manager methods (all, search, mlt) returns an instance of a EsQueryset, it's like a django Queryset but it queries elasticsearch instead of your db.  
Like a regular Queryset, an EsQueryset is lazy, and if evaluated, returns a list of documents. The ```.deserialize()``` method makes the queryset return instances of models instead of dicts.

> django-elasticsearch **DOES NOT** index documents by itself unless told to, either set settings.ELASTICSEARCH_AUTO_INDEX to True to index your models when you save them, or call directly myinstance.es.do_index().

To specify the size of output of documents, it is necessary to make a slice of data, for example:

```
len(list(MyModel.es.search('value')))
>>> 10
len(list(MyModel.es.search('value')[0:100]))
>>> 42
```

CONFIGURATION
=============
Project scope configuration (django settings):
----------------------------------------------

* **ELASTICSEARCH_URL**  
    Defaults to 'http://localhost:9200'  
    The url of your elasticsearch cluster/instance.

* **ELASTICSEARCH_AUTO_INDEX**  
    Defaults to False  
    Set to True if you **don't** want to handle the elasticsearch operations yourself. In that case the creation of the index, the indexation and deletions are hooked respectively to the post_syncdb, post_save and post_delete signals.     Should probably only be used in a dev environment or for small scale databases.
    If you have already done a syncdb, you can just call ```MyModel.es.create_index()``` to create the index/mapping.

* **ELASTICSEARCH_DEFAULT_INDEX**  
    Defaults to 'django'  
    The default index name used for every document, can be overrided for a model with the ```model.Meta.Elasticsearch.index``` attribute.

* **ELASTICSEARCH_SETTINGS**  
    No defaults  
    If set, will be passed when creating any index [as is](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/indices-create-index.html#create-index-settings).

* **ELASTICSEARCH_FUZZINESS**  
    Defaults to 0.5  
    Will be applied to any es.search query, See the [fuzziness section](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/common-options.html#fuzziness) of the elasticsearch documentation.

* **ELASTICSEARCH_CONNECTION_KWARGS**  
    Defaults to {}  
    Additional kwargs to be passed to at the instantiation of the elasticsearch client. Useful to manage HTTPS connection for example ([Reference](http://elasticsearch-py.readthedocs.org/en/master/api.html#elasticsearch.Elasticsearch)).

Model scope configuration:
--------------------------

Each EsIndexable model receive an Elasticsearch class that contains its options (just like the Model.Meta class).

* **index**  
    Defaults to 'django'  
    The elasticsearch index in which this model(document type) will be indexed.

* **doc_type**  
    Defaults to 'model-{model_name}'  
    The elasticsearch type in which this model will be indexed.

* **fields**  
    Defaults to None  
    The fields to be indexed by elasticsearch, if left to None, all models fields will be indexed.

* **mappings**  
    Defaults to None  
    You can override some or all of the fields mapping with this dictionary
    Example:  
    
    ```python

    MyModel(EsIndexable, models.Model):
        title = models.CharField(max_length=64)
        
        class Elasticsearch(EsIndexable.Elasticsearch):
            mappings = {'title': {'boost': 2.0}}
    ```
    In this example we only override the 'boost' attribute of the 'title' field, but there are plenty of possible configurations, see [the docs](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/indices-put-mapping.html).

* **serializer_class**  
    Defaults to EsJsonSerializer  
    This is the class used to translate from the django model to elasticsearch document both ways.

* **facets_fields**  
    Defaults to None  
    Can be set to a list of fields to return as facets when doing a search query on the model, if not set explicitly in the query itself.

* **facets_limits**  
    Defaults to None  
    The maximum number of facets to return per query, if None, use the elasticsearch setting.

* **suggest_fields**  
    Defaults to None  
    A dictionary of fields to add in the suggestions, if not set at a search level.

* **suggest_limit**  
    Defaults to None  
    The maximum number of suggestions to return, if None, use the elasticsearch setting.

* **completion_fields**  
    Defaults to None  
    The fields on which to activate auto-completion (needs a specific mapping).

API
===

EsIndexable API:
----------------

The Elasticsearch manager is available from the 'es' attribute of EsIndexable Model classes or instances. Some methods requires an instance though.  

**Manager methods that returns a EsQueryset instance**  

* **es.search**(query,
            facets=None,
            facets_limit=None,
            global_facets=True,
            suggest_fields=None,
            suggest_limit=None,
            fuzziness=None)  
    Returns a configured EsQueryset with the given options, or the defaults set in ```EsIndexable.Elasticsearch```.  
  
* **es.all**()  
    Proxy to an empty query ```.search("")```.
  
* **es.mlt** *needs_instance*  
    Returns an EsQueryset of documents that are 'like' the given instance's document. See the [more like this api](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/search-more-like-this.html).

**Other Manager methods**  
* **es.count**()  
    Returns the number of documents in the model's doc_type.
  
* **es.get**() *needs_instance*  
    Returns the elasticsearch document of the model instance.
  
* **es.delete**() *needs_instance*  
    Delete the given instance's document.
  
* **es.do_index**() *needs_instance*  
    Serialize and index the given instance.
  
* **es.complete**(field_name, query)  
    Returns a list of suggestions from elasticsearch for the given field and query.
    **Note**: field_name must be present in ```Elasticsearch.completion_fields``` because it needs a specific mapping. 
    Example:
    ```
    >>>MyModel.es.complete('title', 'tset')
    ['test',]
    ```
  
* **es.do_update**()  
    Refresh the whole index of the model. This should probably be only used in a TestCase. See the [refresh api](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/indices-refresh.html).
  
* **es.get_mapping**()  
    Returns the current mapping for the model's document type.
  
* **es.get_settings**()  
    Returns the current settings for the model's index.
  
* **es.diff**()  
    Returns a dict containing differences between the db instance and the elasticsearch instance.
  
* **es.check_cluster**()  
    Returns True if the elasticsearch cluster is alive.
  
* **es.reindex_all**(queryset=None)  
    queryset defaults to ```self.model.objects.all()```   
    Calls ```es.do_index()``` for every instance in queryset.
  
* **es.flush**()  
    Deletes the model's index and then reindex all instances of it.


EsQueryset API:
---------------
This class is as close as possible to a standard relational db Queryset, however the db operations (update and delete) are deactivated (i'm open for discussion on if and how to implement these). Note that just like regular Querysets, EsQuerysets are lazy, they can be ordered, filtered and faceted.  

Note that the return value of the queryset is higly dependent on your mapping, for example, if you want to be able to do an exact filtering with filter() you need a field with {"index" : "not_analyzed"}.
Also by default, filters are case insensitive, if you have a case sensitive tokenizer, you need to instantiate EsQueryset with ignore_case=False.

An EsQueryset acts a lot like a regular Queryset:
```
>>> q = MyModel.es.queryset.all()
>>> q = q.filter(title='foo')
>>> q = q.search('test')
>>> q  # only now is the query evaluated
[{'title': 'foo', 'some_content': 'this is a test.'}]
```

If you need models methods or attributes, you can get model instances instead of documents (dicts) by calling the deserialize method on the query before evaluating it. See the Serializer API below.

To access the facets you can use the facets property of the EsQueryset:
```python
>>> MyModel.Elasticsearch.default_facets_fields
['author']
>>> q = MyModel.es.search('woot', facets=['foo'])  # returns a lazy EsQueryset instance
>>> q = MyModel.es.search('woot').facet(['foo'])  # is exactly the same
>>> q.facets  # evals the query and returns the facets
{u'doc_count': 45,
 u'foo': {u'buckets': [
 {u'doc_count': 13, u'key': u'bar'},
]}}
```
Note that es.search automatically add the default facets set on the model to the query, but you can also set them manually with the ```facets``` and ```facets_limit``` parameters.

**Available methods** all of those are chainable.
* **es.queryset.search**(query)  
  
* **es.queryset.all**()  
  
* **es.queryset.facet**(fields, limit=None, use_globals=True)  
    If ```use_globals``` is set to False, the facets will be filtered like the documents.
  
* **es.queryset.suggest**(fields, limit)  
    Add ```fields``` for suggestions.
  
* **es.queryset.order_by**(**kwargs)  
  
* **es.queryset.filter**(**kwargs)  
    Accepted lookups are: __exact, __should, __contains, __gt, __gte, __lt, __lte, __range  
    Just like in django, the default lookup is __exact.  
    See the [bool query](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html) for a difference between __exact (which maps to 'must') and __should.  
  
* **es.queryset.exclude**(**kwargs)  
  
* **es.queryset.mlt**(id)  
    See the [more like this api](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/search-more-like-this.html).

* **es.queryset.deserialize**()
    Makes the queryset return model instances instead of documents.

* **es.queryset.extra**(body)
    Blindly updates the elasticsearch query body with ```body``` allowing to use any non-implemented elasticsearch feature.

**Does not return an EsQueryset** and thus are not chainable.  
* **es.queryset.count**()

* **es.queryset.get**(pk=X)

* **es.queryset.complete**(field_name, query)


Serializer API:
---------------

The serializer's role is to format django model instances to something indexable by elasticsearch : json. The only mandatory method for a serializer is the ```serialize(instance)``` method, deserializing is only an option.  
  
The default serializer does a little bit more though:  
For each indexed fields, look for either ```serialize_{field_name}``` or ```serialize_{field_type}``` methods, and fallback on ```getattr(instance, field_name)```. Also allow naive nested serialization, by looking for an Elasticsearch class attribute on the target model class of the related field, or falling back on ```dict(id=instance.id, value=unicode(instance))```.  
Let's look at a bit complex example:  

my_app.models.py  
```python
from django.db import models
from django_elasticsearch.models import EsIndexable
from my_app.serializers import MyModelEsSerializer

class MyModel(models.Model):
      some_content = models.CharField(max_length=255)
      more_content = models.TextField()
      a_date = models.DateTimeField(auto_now_add=True)
      another_date = models.DateTimeField(auto_now=True)
      some_relation = models.ForeignKey(AnotherModel)

      class Elasticsearch(EsIndexable.Elasticsearch):
            serializer_class = MyModelEsSerializer
            fields = ['some_content', 'more_content', 'content_length', 'a_date', 'some_relation']
            mappings = {'content_length': {'type': 'long'},
                        'a_date': {'type': 'object'}}

```

Note that since ```content_length``` is an abstract field (not present in db), and ```a_date``` is serialized to a dict instead of it's default (datetime), we need to tell elasticsearch their types in the mappings attribute.  

serializers.py  
```python
from django_elasticsearch.serializers import EsJsonSerializer

class MyModelEsSerializer(EsJsonSerializer):
    def serialize_more_content(self, instance, field_name):
        # Specific attribute serializer
        return getattr(instance, field_name)[:5]

    def serialize_content_length(self, instance, field_name):
        # Abstract field serializer
        content = getattr(instance, 'some_content')
        return len(content)

    def serialize_type_datetimefield(self, instance, field_name):
        # Specific field type serializer
        d = getattr(instance, field_name)
        # A rather typical api output,
        # The reasons for indexing dates as this are debatable, but it's just an example
        return {
            'timestamp': d and d.strftime('%s'),
            'date': d and d.date().isoformat(),
            'time': d and d.time().isoformat()[:5]
        }
```

output
```python
>>> instance = MyModel(some_content=u"This is some minimalist content.",
                       more_content=u"And that too.")
<MyModel >
>>> instance.es.serialize()
"{'some_content': 'This is some minimalist content.',
  'more_content': 'And t',
  'content_length': 32,
  'a_date': {
     'timestamp': '1434452101',
     'date': '2015-06-16',
     'time': '05:53:56.626532'
  },
  'some_relation': {'id': 15, 'value': 'something something'}
}"
```

CONTRIB
=======

* **restframework.ElasticsearchFilterBackend**  
    A filter backend for [rest framework](http://www.django-rest-framework.org/) that returns a EsQueryset.  
  
* **restframework.FacetedListModelMixin**  
    A viewset mixin that adds the facets to the response data in case the ElasticsearchFilterBackend was used.  
  
LOGGING
=======

Two loggers are available 'elasticsearch' and 'elasticsearch.trace'.


FAILING GRACEFULLY
==================

You can catch ```elasticsearch.ConnectionError``` and ```elasticsearch.TransportError``` if you want to recover from an error on elasticsearch side. There is an example of it in ```django_elasticsearch.views.ElasticsearchListView```.
You can also use the ```MyModel.es.check_cluster()``` method which returns True if the cluster is available, in case you want to make sure of it before doing anything.


TESTS
=====

Django-elasticsearch has a 95% test coverage, and tests pass for django 1.4 to 1.9.

Using tox
---------

Install [tox](https://testrun.org/tox/), then:
```shell
cd test_project
tox
```

Or to test one specific python/django version combo:
```
tox -e py27-django16
```

Or a specific test case / unit test, with a weird syntax:
Django 1.4
```
tox -epy27-django14 -- .EsQuerysetTestCase
tox -epy27-django14 -- .EsQuerysetTestCase.test_use_cache
```

Django >1.6
```
tox -epy27-django16 -- .tests.test_qs.EsQuerysetTestCase
tox -epy27-django16 -- .tests.test_qs.EsQuerysetTestCase.test_use_cache
```


The old way
-----------

```
$ cd test_project
$ virtualenv env
$ . env/bin/activate
$ pip install -r ../requirements.txt  # app requirements
$ pip install -r requirements.txt  # tests requirements
$ python manage.py test django_elasticsearch
```

Coverage
--------

```
coverage run --source=django_elasticsearch --omit='*tests*','*migrations*' manage.py test django_elasticsearch
```

NOTES
=====

Why not make a django database backend ? Because django *does not* support non relational databases, which means that the db backend API is very heavily designed around SQL. I'm usually in favor of hiding the complexity, but in this case for every bit that feels right - auto db and test db creation, client handling, .. - there is one that feels wrong and keeping up with the api changes makes it worse. There is an avorted prototype branch (feature/db-backend) going this way though.
