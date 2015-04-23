from django.http import Http404
from django.conf import settings
from django.core.paginator import Page
from django.db import models
from django.db.models import query

from rest_framework.response import Response
from rest_framework.settings import api_settings
from rest_framework.mixins import ListModelMixin
from rest_framework.decorators import list_route
from rest_framework.filters import OrderingFilter
from rest_framework.filters import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from rest_framework.serializers import BaseSerializer, ListSerializer
from rest_framework.compat import OrderedDict

from elasticsearch import NotFoundError
try:
    from elasticsearch import ConnectionError
except ImportError:
    from urllib3.connection import ConnectionError
from elasticsearch import TransportError
from django_elasticsearch.models import EsIndexable


class ElasticsearchFilterBackend(OrderingFilter, DjangoFilterBackend):
    def filter_queryset(self, request, queryset, view):
        model = queryset.model

        if view.action == 'list':
            if not issubclass(model, EsIndexable):
                raise ValueError("Model {0} is not indexed in Elasticsearch. "
                                 "Make it indexable by subclassing "
                                 "django_elasticsearch.models.EsIndexable."
                                 "".format(model))
            search_param = getattr(view, 'search_param', api_settings.SEARCH_PARAM)
            print search_param
            query = request.QUERY_PARAMS.get(search_param, '')

            # order of precedence : query params > class attribute > model Meta attribute
            ordering = self.get_ordering(request, queryset, view)
            if not ordering:
                ordering = self.get_default_ordering(view)

            filterable = getattr(view, 'filter_fields', [])
            print filterable
            filters = dict([(k, v)
                            for k, v in request.GET.iteritems()
                            if k in filterable])

            q = queryset.query(query).filter(**filters)
            if ordering:
                q = q.order_by(*ordering)

            return q
        else:
            return super(ElasticsearchFilterBackend, self).filter_queryset(
                request, queryset, view
            )

class EsPageNumberPagination(PageNumberPagination):
    page_size = 10

    def paginate_queryset(self, queryset, request, view=None):
        data = super(EsPageNumberPagination,self).paginate_queryset(queryset, request, view=view)
        self.facets = getattr(queryset, 'facets', {})
        self.suggestions = getattr(queryset, 'suggestions', {})
        return data

    def get_paginated_response(self, data):
          return Response(OrderedDict([
              ('count', self.page.paginator.count),
              ('next', self.get_next_link()),
              ('previous', self.get_previous_link()),
              ('facets', self.facets),
              ('suggestions', self.suggestions),
              ('results', data)
          ]))


class CustomListSerializer(ListSerializer):
    def to_representation(self, data):
        """
        List of object instances -> List of dicts of primitive datatypes.
        """

        # Dealing with nested relationships, data can be a Manager,
        # so, first get a queryset from the Manager if needed
        iterable = data.all() if isinstance(data, (models.Manager, query.QuerySet)) else data
        #import pdb; pdb.set_trace()
        return iterable

class FakeSerializer(BaseSerializer):
    @property
    def base_fields(self):
        return {}

    @classmethod
    def many_init(cls, *args, **kwargs):
        kwargs['child'] = cls()
        return CustomListSerializer(*args, **kwargs)

    @property
    def data(self):
        import pdb; pdb.set_trace()
        self._data = super(FakeSerializer, self).data
        print type(self._data)
        # if type(self._data) == list:  # better way ?
        #     self._data = {
        #         #'count': self.object.count(),
        #         #'results': self._data
        #     }
        return self._data

    def to_native(self, obj):
        return obj

    # def to_representation(self, obj):
    #   #import pdb; pdb.set_trace()
    #   return obj



class IndexableModelMixin(object):
    """
    Use EsQueryset and ElasticsearchFilterBackend if available
    """
    filter_backends = [ElasticsearchFilterBackend,]
    FILTER_STATUS_MESSAGE_OK = 'Ok'
    FILTER_STATUS_MESSAGE_FAILED = 'Failed'
    pagination_class = EsPageNumberPagination

    ES_ACTIONS = ['list'] # what actions should use ES

    def __init__(self, *args, **kwargs):
        self.es_failed = False
        super(IndexableModelMixin, self).__init__(*args, **kwargs)

    def get_object(self):
        try:
            return super(IndexableModelMixin, self).get_object()
        except NotFoundError:
            raise Http404

    def get_serializer_class(self):

        if self.action in self.ES_ACTIONS and not self.es_failed:
            # let's return the elasticsearch response as it is.
            return FakeSerializer
        return super(IndexableModelMixin, self).get_serializer_class()

    def get_serializer(self, page, many=False):

        context = self.get_serializer_context()
        serializer_class = self.get_serializer_class()
        #import pdb; pdb.set_trace()
        return serializer_class(instance=page, context=context, many=many)

    def get_queryset(self):
        if self.action in self.ES_ACTIONS and not self.es_failed:
            return self.model.es.search("")
        # db fallback
        return super(IndexableModelMixin, self).get_queryset()

    def filter_queryset(self, queryset):
        if self.es_failed:
            for backend in api_settings.DEFAULT_FILTER_BACKENDS:
                queryset = backend().filter_queryset(self.request, queryset, self)
            return queryset
        else:
            return super(IndexableModelMixin, self).filter_queryset(queryset)

    def list(self, request, *args, **kwargs):

        r = super(IndexableModelMixin, self).list(request, *args, **kwargs)

        # if not self.es_failed:
        #     if getattr(self.object_list, 'facets', None):
        #         r.data['facets'] = self.object_list.facets
        #
        #     if getattr(self.object_list, 'suggestions', None):
        #         r.data['suggestions'] = self.object_list.suggestions

        return r

    def dispatch(self, request, *args, **kwargs):
        try:
            r = super(IndexableModelMixin, self).dispatch(request, *args, **kwargs)
        except (ConnectionError, TransportError), e:
            self.es_failed = True
            r = super(IndexableModelMixin, self).dispatch(request, *args, **kwargs)
            if settings.DEBUG and isinstance(r.data, dict):
                r.data["filter_fail_cause"] = str(e)
        # Add a failed message in case something went wrong with elasticsearch
        # for example if the cluster went down.
        if isinstance(r.data, dict) and self.action in ['list', 'retrieve']:
            r.data['filter_status'] = (self.es_failed
                                       and self.FILTER_STATUS_MESSAGE_FAILED
                                       or self.FILTER_STATUS_MESSAGE_OK)
        return r


class AutoCompletionMixin(ListModelMixin):
    """
    Add a route to the ViewSet to get a list of completion suggestion.
    """

    @list_route()
    def autocomplete(self, request, **kwargs):
        field_name = request.QUERY_PARAMS.get('f', None)
        query = request.QUERY_PARAMS.get('q', '')

        try:
            data = self.model.es.complete(field_name, query)
        except ValueError:
            raise Http404("field {0} is either missing or "
                          "not in Elasticsearch.completion_fields.")

        return Response(data)
