from django.conf import settings

from elasticsearch import Elasticsearch


es_client = Elasticsearch(getattr(settings,
                                  'ELASTICSEARCH_URL',
                                  'http://localhost:9200'))
