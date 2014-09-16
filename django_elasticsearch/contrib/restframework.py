from django.http import Http404

from rest_framework.response import Response
from rest_framework.mixins import ListModelMixin
from rest_framework.decorators import list_route
from rest_framework.filters import BaseFilterBackend

from django_elasticsearch.models import EsIndexable


class ElasticsearchFilterBackend(BaseFilterBackend):
    search_param = 'q'

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
            return queryset


class SearchListModelMixin(ListModelMixin):
    """
    Add faceted and suggestions info to the response
    in case the ElasticsearchFilterBackend was used.
    """
    filter_backends = [ElasticsearchFilterBackend]

    def list(self, request, *args, **kwargs):
        r = super(SearchListModelMixin, self).list(request, *args, **kwargs)

        # Injecting the facets in the response if the FilterBackend was used.
        if getattr(self.object_list, 'facets', None):
            r.data['facets'] = self.object_list.facets

        # And the suggestions
        if getattr(self.object_list, 'suggestions', None):
            r.data['suggestions'] = self.object_list.suggestions

        return r


class AutoCompletionMixin(ListModelMixin):
    @list_route()
    def autocomplete(self, request, **kwargs):
        field_name = request.QUERY_PARAMS.get('f', None)
        query = request.QUERY_PARAMS.get('q', '')

        try:
            data = self.model.es.complete(field_name, query)
        except ValueError:
            raise Http404("field {0} is either absent or "
                          "not in Elasticsearch.completion_fields.")

        return Response(data)
