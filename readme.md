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
>>> q = MyModel.es.search('foo')
>>> q
[{'id': 1, 'foo': 'A value'}, {'id': 2, 'foo': 'Another value'}, ...]
>>> q.deserialize()
[<MyModel #1>, <MyModel #2>, ...]
>>> MyModel.es.get(id=1)
{'id': 1, 'foo': 'A value'}
```
The elasticsearch manager methods (all, search, mlt) returns an instance of a EsQueryset, it's like a django Queryset but it queries elasticsearch instead of your db.  
Like a regular Queryset, an EsQueryset is lazy, and if evaluated, returns a list of documents. The ```.deserialize()``` method returns models instanciated from elasticsearch values.

CONFIGURATION
=============
Project scope configuration (django settings):
----------------------------------------------

* **ELASTICSEARCH_URL**  
Defaults to 'http://localhost:9200'  
The url of your elasticsearch cluster/instance.

* **ELASTICSEARCH_AUTO_INDEX**  
Defaults to True  
Set to false if you want to handle the elasticsearch operations yourself. By default the creation of the index, the indexation and deletions are hooked respectively to the post_syncdb, post_save and post_delete signals.
If you have already done a syncdb, you can just call ```MyModel.es.create_index()``` to create the index/mapping.

* **ELASTICSEARCH_DEFAULT_INDEX**  
Defaults to 'django'  
The default index name used for every document, can be overrided for a model with the ```model.Meta.Elasticsearch.index``` attribute.

* **ELASTICSEARCH_SETTINGS**  
no defaults  
If set, will be passed when creating any index [as is](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/indices-create-index.html#create-index-settings).

* **ELASTICSEARCH_FUZZINESS**  
defaults to 0.5  
Will be applied to any es.search query, See the [fuzziness section](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/common-options.html#fuzziness) of the elasticsearch documentation.

**ELASTICSEARCH_CONNECTION_KWARGS**
defaults to {}
Additional kwargs to be passed to at the instanciation of the elasticsearch client. Useful to manage HTTPS connection for example. ([Reference](http://elasticsearch-py.readthedocs.org/en/master/api.html#elasticsearch.Elasticsearch))

Model scope configuration:
--------------------------

Each EsIndexable model receive an Elasticsearch class that contains its options (just like the Model.Meta class).

* **index**  
defaults to 'django'  
The elasticsearch index in which this model(document type) will be indexed.

* **fields**  
defaults to None  
The fields to be indexed by elasticsearch, if let to None, all models fields will be indexed.

* **mapping**  
defaults to None  
You can override some or all of the fields mapping with this dictionnary
Example:  
```python

MyModel(EsIndexable, models.Model):
    title = models.CharField(max_length=64)

    class Elasticsearch(EsIndexable.Elasticsearch):
        mappings = {'title': {'boost': 2.0}

```
In this example we only override the 'boost' attribute of the 'title' field, but there are plenty of possible configurations, see [the docs](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/indices-put-mapping.html).

* **serializer_class**  
defaults to ModelJsonSerializer  
This is the class used to translate from the django model to elasticsearch document both ways.

* **facets_fields**  
defaults to None  
Can be set to a list of fields to return as facets when doing a query, if not set explicitly.

* **facets_limits**  
defaults to None  
The maximum number of facets to return per query, if None, use the elasticsearch setting.

* **suggest_fields**  
defaults to None  
A dictionary of fields to add in the suggestions, if not set at a search level.

* **suggest_limit**  
defaults to None  
The maximum number of suggestions to return, if None, use the elasticsearch setting.

* **completion_fields**  
defaults to None  
The fields on which to activate auto-completion (needs a specific mapping).

API
===

EsIndexable API:
----------------

The Elasticsearch manager is available from the 'es' attribute of EsIndexable Model classes or instances. Some methods requires an instance though.  

**Manager methods that returns a EsQueryset instance**  

- es.search(query,
            facets=None,
            facets_limit=None,
            global_facets=True,
            suggest_fields=None,
            suggest_limit=None,
            fuzziness=None)  
Returns a configurated EsQueryset with the given options, or the defaults set in ```EsIndexable.Elasticsearch```.  
- es.all()  
Proxy to an empty query ```.search("")```.
- es.mlt *needs_instance*  
Returns an EsQueryset of documents that are 'like' the given instance's document. See the [more like this api](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/search-more-like-this.html).

**Other Manager methods**  
- es.count  
Returns the number of documents in the model's doc_type.
- es.get *needs_instance*  
Returns the elasticsearch document of the model instance.
- es.delete *needs_instance*  
Delete the given instance's document.
- es.do_index *needs_instance*  
Serialize and index the given instance.
- es.complete(field_name, query)  
Returns a list of suggestions from elasticsearch for the given field and query.
**Note**: field_name must be present in ```Elasticsearch.completion_fields``` because it needs a specific mapping.  
Example:
```
>>>MyModel.es.complete('title', 'tset')
['test',]
```
- es.do_update  
Refresh the whole index of the model. This should probably be only used in a TestCase. See the [refresh api](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/indices-refresh.html).
- es.get_mapping  
Returns the current mapping for the model's document type.
- es.get_settings  
Returns the current settings for the model's index.
- es.diff  
Returns a dict containing differences between the db instance and the elasticsearch instance.
- es.check_cluster  
Returns True if the elasticsearch cluster is alive.
- es.reindex_all(queryset=self.model.objects.all())  
Calls ```es.do_index()``` for every instance in queryset.
- es.flush  
Deletes the model's index and then reindex all instances of it.


EsQueryset API:
---------------
This class is as close as possible to a standard relational db Queryset, however the db operations (update and delete) are disactivated (i'm open for discution on if and how to implement these). Note that just like regular Querysets, EsQuerysets are lazy, they can be ordered, filtered and faceted.  

Note that the return value of the queryset is higly dependent on your mapping, for example, if you want to be able to do an exact filtering with filter() you need a field with {"index" : "not_analyzed"}.
Also by defaut, filters are case insensitive, if you have a case sensitive tokenizer, you need to instanciate EsQueryset with ignore_case=False.

An EsQueryset acts a lot like a regular Queryset:
```
>>> q = MyModel.es.queryset.all
>>> q = q.filter(title='foo')
>>> q = q.search('test')
>>> q  # only now is the query evaluated
[{'title': 'foo', 'some_content': 'this is a test.'}]
```

To access the facets you can use the facets property of the EsQueryset:
```python
>>> MyModel.Elasticsearch.default_facets_fields
['author']
>>> q = MyModel.es.search('woot', facets='foo')  # returns a lazy EsQueryset instance
>>> q = MyModel.es.search('woot').facet('foo')  # is exactly the same
>>> q.facets  # evals the query and returns the facets
{u'doc_count': 45,
 u'foo': {u'buckets': [
 {u'doc_count': 13, u'key': u'bar'},
]}}
```
Note that es.search automatically add the default facets set on the model to the query, but you can also set them manually with the ```facets``` and ```facets_limit``` parameters.

**Available methods** all of those are chainable.
- es.queryset.search(query)  
- es.queryset.all()  
- es.queryset.facet(fields, limit=None, use_globals=True)  
If ```use_globals``` is set to False, the facets will be filtered like the documents.
- es.queryset.suggest(fields, limit)  
Add ```fields``` for suggestions.
- es.queryset.order_by  
- es.queryset.filter  
Accepted lookups are: __exact, __should, __contains, __gt, __gte, __lt, __lte, __range  
Just like in django, the default lookup is __exact.  
See the [bool query](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/query-dsl-bool-query.html) for a difference between __exact (which maps to 'must') and __should.  
- es.queryset.exclude  
- es.queryset.mlt(id)  
See the [more like this api](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/search-more-like-this.html).

**Does not return the EsQueryset** and thus is not chainable.  
- es.queryset.count
- es.queryset.get(pk=X)
- es.queryset.complete(field_name, query)

CONTRIB
=======

* restframework.ElasticsearchFilterBackend
A filter backend for [rest framework](http://www.django-rest-framework.org/) that returns a EsQueryset.

* restframework.FacetedListModelMixin
A viewset mixin that adds the facets to the response data in case the ElasticsearchFilterBackend was used.

* taggit.TaggitSerializer
Not really working in all cases :(

LOGGING
=======

Despite what the pyelasticsearch docs says, i didn't have any luck with the 'pyelasticsearch' logger, the 'elasticsearch' and 'elasticsearch.trace' loggers, however, are working well.

FAILING GRACEFULLY
==================

You can catch ```elasticsearch.ConnectionError``` and ```elasticsearch.TransportError``` if you want to recover from an error on elasticsearch side. There is an exemple of it in ```django_elasticsearch.views.ElasticsearchListView```.
You can also use the ```MyModel.es.check_cluster()``` method which returns True if the cluster is available, in case you want to make sure of it before doing anything.


TESTS
=====

django-elasticsearch has a 92% test coverage, and tests pass for django 1.4 to 1.7.

```
$ cd test_project
$ virtualenv env
$ . env/bin/activate
$ pip install -r ../requirements.txt  # app requirements
$ pip install -r requirements.txt  # tests requirements
$ python manage.py test django_elasticsearch
```

**Note**:
To test with a older version of django, simply install it with, for example, ```pip install django==1.4.5``` and run ```python manage.py test django_elasticsearch```.


TODO
====

* advanced docs / docstrings
