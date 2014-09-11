django_elasticsearch is a wrapper around a django Model that automate the indexation and search of django models.
Note: if your elasticsearch documents/mappings are not close to django models, this package is probably not for you.

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
Note: no pypy package yet

USAGE
=====

Subclass the models you wish to index/search with ```django_elasticsearch.models.EsIndexable```.
```python
from django.db import models
from django_elasticsearch.models import EsIndexable


MyModel(EsIndexable, models.Model):
    [...]

```

Then you can do:
```python
>>> q = MyModel.es_search('foo')

```
which returns an instance of a EsQueryset, it's like a django Queryset but it instanciates models from Elasticsearch sources (and thus db operations are disactivated).

CONFIGURATION
=============
Project scope configuration (django settings):
----------------------------------------------

* ELASTICSEARCH_URL  
defaults to 'http://localhost:9200'  
The url of your elasticsearch cluster/instance.

* ELASTICSEARCH_AUTO_INDEX  
defaults to True  
Set to false if you want to handle the elasticsearch operations yourself. By default the creation of the index, the indexation and deletions are hooked respectively to the post_syncdb, post_save and post_delete signals.  
If you have already done a syncdb, you can just call ```MyModel.es_create_index()``` to create the index/mapping.

* ELASTICSEARCH_SETTINGS  
no defaults  
If set, will be passed when creating any index [as is](http://www.elasticsearch.org/guide/en/elasticsearch/reference/current/indices-create-index.html#create-index-settings). If you need different settings for different indexes/document types, you can override the ```es_create_index()``` method of your EsIndexable model.

Model scope configuration:
--------------------------

Each EsIndexable model receive an Elasticsearch class that contains its options (just like the Model.Meta class).

* index  
defaults to 'django'  
The elasticsearch index in which this model(document type) will be indexed.

* fields  
defaults to None  
The fields to be indexed by elasticsearch, if let to None, all models fields will be indexed.

* mapping  
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

* serializer_class  
defaults to ModelJsonSerializer  
This is the class used to translate from the django model to elasticsearch document both ways.

* default_facets_fields  
defaults to None  
Can be set to a list of fields to return as facets.

* facets_limits  
defaults to 10  
The maximum number of facets to return per query.


API
===

You can override these methods in your model if you want to change the behavior of the class.

EsIndexable API:
----------------

* OPERATIONS
- es_do_index
- es_delete
- es_do_update  
Call this if you want the documents to be available right away after (re)indexation (in a TestCase probably).
- es_create_index
- es_flush
- es_reindex_all

* GETTERS/CONVENIENCE METHODS
- es_get_doc_type (classmethod)  
defaults to ```'model-{0}'.format(cls.__name__)```  
Returns a string used as document name in the index.
- es_get  
Returns an python object of the document.
- es_get_mapping
- es_make_mapping
- es_get_settings
- es_search(cls, query, facets=None, facets_limit=5, global_facets=True)  
Returns an EsQueryset
- es_diff
- es_mlt


EsQueryset API:
---------------
This class is as close as possible to a standard relational db Queryset, however the db operations (update and delete) are disactivated (i'm open for discution of how to implement these). Note that just like regular Querysets, EsQuerysets are lazy, they can be ordered, filtered and faceted.

To access the facets you can use the facets property of the EsQueryset:
```python
>>> MyModel.Elasticsearch.default_facets_fields
['author']
>>> q = MyModel.es_search('foo')  # returns a lazy EsQueryset instance
>>> q.facets  # evals the query and returns the facets
{u'author': {
   u'_type': u'terms',
   u'total': 1,
   u'terms': [{u'count': 1, u'term': u'test'}],
   u'other': 0,
   u'missing': 2
   }
}
```
Note that es_search automatically add the default facets set on the model to the query, but you can also set them manually with the ```facets``` and ```facets_limit``` parameters.


CONTRIB
=======

* restframework.ElasticsearchFilterBackend  
A filter backend for [rest framework](http://www.django-rest-framework.org/) that returns a EsQueryset.

* restframework.FacetedListModelMixin  
A viewset mixin that adds the facets to the response data in case the ElasticsearchFilterBackend was used.

* taggit.TaggitSerializer  
Not really working in all cases :(


TESTS
-----

There is no test project in this repository, add ```django_elasticsearch``` to django settings INSTALLED_APPS.

From your project do:
```
python manage.py test django_elasticsearch
```

NOTES
-----

* it would be kinda logical to put the es_search method in a custom manager, because it returns a EsQueryset, but the manager would need to access the Elasticsearch subclass which would be a problem.
* having all methods beeing sufixed by es_ is a bit redundant, we could encapsulate everything in a MyModel.es attribute ?
