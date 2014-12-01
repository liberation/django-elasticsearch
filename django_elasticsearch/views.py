from django.http import Http404
from django.http import HttpResponse
from django.views.generic import View
from django.views.generic.list import BaseListView
from django.views.generic.detail import BaseDetailView
from django.utils import simplejson as json
from django.core import serializers

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
    def __init__(self, *args, **kwargs):
        self.es_failed = False
        super(ElasticsearchView, self).__init__(*args, **kwargs)

    def serialize(self, qs):
        # fallback serializer, you should probably override this
        return serializers.serialize('json', qs)

    def get_queryset(self):
        if self.es_failed:
            return getattr(self, 'fallback_queryset', None) or self.model.objects.all()
        else:
            return self.queryset or self.model.es.all()


class ElasticsearchListView(ElasticsearchView, BaseListView):

    def get(self, context, *args, **kwargs):
        qs = self.get_queryset()
        if self.es_failed:
            content = qs
        else:
            # by default, would iterate over the results, handle pagination etc
            # but we don't want that because elasticsearch do it by itself.
            try:
                content = json.dumps(qs.do_search().response)
            except (TransportError, ConnectionError):
                self.es_failed = True
                qs = self.get_queryset()  # django queryset now
                page_size = self.get_paginate_by(qs)
                if page_size:
                    content = self.serialize(self.paginate_queryset(qs, page_size))
                else:
                    content = self.serialize(qs)
        return HttpResponse(content, content_type='application/json')


class ElasticsearchDetailView(ElasticsearchView, BaseDetailView):

    def serialize(self, qs):
        s = super(ElasticsearchDetailView, self).serialize(qs)
        # this is higly inneficient: as i said, you should override .serialize() !
        obj = json.loads(s)
        return json.dumps(obj[0]['fields'])

    def get_object(self, queryset=None):
        try:
            return super(ElasticsearchDetailView, self).get_object(queryset=queryset)
        except NotFoundError:
            raise Http404

    def get(self, context, *args, **kwargs):
        try:
            content = json.dumps(self.get_object())
        except (TransportError, ConnectionError):
            self.es_failed = True
            content = self.serialize([self.get_object()])

        return HttpResponse(content, content_type='application/json')
