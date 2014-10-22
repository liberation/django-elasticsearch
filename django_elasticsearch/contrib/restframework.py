from django.http import Http404
from django.conf import settings

from rest_framework.response import Response
from rest_framework.mixins import ListModelMixin
from rest_framework.decorators import list_route
from rest_framework.filters import DjangoFilterBackend

from elasticsearch import ConnectionError, TransportError
from django_elasticsearch.models import EsIndexable
from django_elasticsearch.managers import EsQueryset


class ElasticsearchFilterBackend(DjangoFilterBackend):
    search_param = getattr(settings, 'SEARCH_PARAM', 'q')

    def filter_queryset(self, request, queryset, view):
        model = queryset.model

        if view.action == 'list':
            if not issubclass(model, EsIndexable):
                raise ValueError("Model {0} is not indexed in Elasticsearch. "
                                 "Make it indexable by subclassing "
                                 "django_elasticsearch.models.EsIndexable."
                                 "".format(model))

            query = request.QUERY_PARAMS.get(self.search_param, '')
            ordering = getattr(view,
                               'ordering',
                               getattr(model.Meta, 'ordering', None))
            filterable = getattr(view, 'filter_fields', [])
            filters = dict([(k, v)
                            for k, v in request.GET.iteritems()
                            if k in filterable])

            q = model.es.search(query).filter(**filters)
            if ordering:
                q.order_by(*ordering)

            return q
        else:
            return super(ElasticsearchFilterBackend, self).filter_queryset(
                request, queryset, view
            )


class SearchListModelMixin(ListModelMixin):
    """
    Add faceted and suggestions info to the response
    in case the ElasticsearchFilterBackend was used.
    """
    filter_backends = [ElasticsearchFilterBackend]
    fallback_filter_backends = [DjangoFilterBackend]
    FILTER_STATUS_MESSAGE_OK = 'Ok'
    FILTER_STATUS_MESSAGE_FAILED = 'Failed'

    def filter_queryset(self, queryset):
        if self.es_failed:
            for backend in self.fallback_filter_backends:
                queryset = backend().filter_queryset(self.request, queryset, self)
            return queryset
        else:
            return super(SearchListModelMixin, self).filter_queryset(queryset)

    def list(self, request, *args, **kwargs):
        try:
            self.es_failed = False
            r = super(SearchListModelMixin, self).list(request, *args, **kwargs)
        except (ConnectionError, TransportError):
            # something went wrong with elasticsearch
            # but the filterbackend didn't catch it
            # try to recover in a barbaric way
            self.es_failed = True
            r = super(SearchListModelMixin, self).list(request, *args, **kwargs)

        # Add a failed message in case something went wrong with elasticsearch
        # for example if the cluster went down.
        r.data['filter_status'] = (
            isinstance(self.object_list, EsQueryset)
            and self.FILTER_STATUS_MESSAGE_OK
            or self.FILTER_STATUS_MESSAGE_FAILED)

        # Injecting the facets in the response if the FilterBackend was used.
        if getattr(self.object_list, 'facets', None):
            r.data['facets'] = self.object_list.facets

        # And the suggestions
        if getattr(self.object_list, 'suggestions', None):
            r.data['suggestions'] = self.object_list.suggestions

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
