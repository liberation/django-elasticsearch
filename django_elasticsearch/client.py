from django.conf import settings

from elasticsearch import Elasticsearch


es_client = Elasticsearch(getattr(settings,
                                  'ELASTICSEARCH_URL',
                                  'http://localhost:9200'),
                          **getattr(settings,
                                    'ELASTICSEARCH_CONNECTION_KWARGS',
                                    {}))
