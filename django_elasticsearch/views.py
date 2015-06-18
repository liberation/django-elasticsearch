from django.http import Http404
from django.views.generic import View
from django.views.generic.list import BaseListView
from django.views.generic.detail import BaseDetailView

from elasticsearch import NotFoundError
try:
    from elasticsearch import ConnectionError
except ImportError:
    from urllib3.connection import ConnectionError
from elasticsearch import TransportError


class ElasticsearchView(View):
    """
    A very simple/naive view, that returns elasticsearch's response directly.
    Note that pagination is also done on elasticsearch side.
    """
    db_fallback = True
    es_queryset = None

    def __init__(self, *args, **kwargs):
        self.es_failed = False
        super(ElasticsearchView, self).__init__(*args, **kwargs)

    def get_queryset(self):
        if self.es_failed:
            return super(ElasticsearchView, self).get_queryset()
        else:
            return self.es_queryset or self.model.es.all().deserialize()


class ElasticsearchListView(ElasticsearchView, BaseListView):
    def get_paginate_by(self, *args, **kwargs):
        # disable pagination since elasticsearch does it by itself
        if self.es_failed:
            return None
        else:
            return super(ElasticsearchListView, self).get_paginate_by(*args, **kwargs)

    def get(self, request, *args, **kwargs):
        try:
            return super(ElasticsearchListView, self).get(request, *args, **kwargs)
        except (TransportError, ConnectionError):
            self.es_failed = True
            if self.db_fallback:
                return super(ElasticsearchListView, self).get(request, *args, **kwargs)
            else:
                raise


class ElasticsearchDetailView(ElasticsearchView, BaseDetailView):
    def get_object(self, queryset=None):
        try:
            return super(ElasticsearchDetailView, self).get_object(queryset=queryset)
        except NotFoundError:
            raise Http404

    def get(self, request, *args, **kwargs):
        try:
            return super(ElasticsearchDetailView, self).get(request, *args, **kwargs)
        except (TransportError, ConnectionError):
            self.es_failed = True
            if self.db_fallback:
                return super(ElasticsearchDetailView, self).get(request, *args, **kwargs)
            else:
                raise
