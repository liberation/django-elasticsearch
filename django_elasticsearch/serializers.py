import json
import datetime

from django import VERSION as django_version

if django_version < (3, 1, 0):
    from django.db.models import FieldDoesNotExist
else:
    from django.core.exceptions import FieldDoesNotExist

from django.db.models.fields.related import ManyToManyField


class EsSerializer(object):
    def serialize(self, instance):
        raise NotImplementedError()

    def deserialize(self, source):
        raise NotImplementedError()


class EsDbMixin(object):
    """
    Very Naive mixin that deserialize to models
    by doing a db query using ids in the queryset
    """

    def deserialize(self, source):
        pk_field = self.model._meta.auto_field
        ids = [e[pk_field.name] for e in source]
        return self.model.objects.filter(**{pk_field.name + '__in': ids})


class EsJsonToModelMixin(object):
    """
    Serializer mixin that attempts to instanciate the model
    from the json elasticsearch source
    (and disables db operations on the model).
    """

    def instanciate(self, attrs):
        instance = self.model(**attrs)
        instance._is_es_deserialized = True
        return instance

    def nested_deserialize(self, field, source):
        # check for Elasticsearch.serializer on the related model
        if source:
            if hasattr(field.rel.to, 'Elasticsearch'):
                serializer = field.rel.to.es.get_serializer()
                obj = serializer.deserialize(source)
                return obj
            elif 'id' in source and 'value' in source:
                # id/value fallback
                return field.rel.to.objects.get(pk=source.get('id'))

    def deserialize_field(self, source, field_name):
        method_name = 'deserialize_{0}'.format(field_name)
        if hasattr(self, method_name):
            return getattr(self, method_name)(source, field_name)

        field = self.model._meta.get_field(field_name)
        field_type_method_name = 'deserialize_type_{0}'.format(
            field.__class__.__name__.lower())
        if hasattr(self, field_type_method_name):
            return getattr(self, field_type_method_name)(source, field_name)

        val = source.get(field_name)

        # datetime
        typ = field.get_internal_type()
        if val and typ in ('DateField', 'DateTimeField'):
            return datetime.datetime.strptime(val, '%Y-%m-%dT%H:%M:%S.%f')

        if field.rel:
            # M2M
            if isinstance(field, ManyToManyField):
                raise AttributeError

            # FK, OtO
            return self.nested_deserialize(field, source.get(field_name))

        return source.get(field_name)

    def deserialize(self, source):
        """
        Returns a model instance
        """
        attrs = {}
        for k, v in source.iteritems():
            try:
                attrs[k] = self.deserialize_field(source, k)
            except (AttributeError, FieldDoesNotExist):
                # m2m, abstract
                pass

        return self.instanciate(attrs)
        # TODO: we can assign m2ms now


class EsModelToJsonMixin(object):
    def __init__(self, model, max_depth=2, cur_depth=1):
        self.model = model
        # used in case of related field on 'self' to avoid infinite loop
        self.cur_depth = cur_depth
        self.max_depth = max_depth

    def serialize_field(self, instance, field_name):
        method_name = 'serialize_{0}'.format(field_name)
        if hasattr(self, method_name):
            return getattr(self, method_name)(instance, field_name)

        try:
            field = self.model._meta.get_field(field_name)
        except FieldDoesNotExist:
            # Abstract field
            pass
        else:
            field_type_method_name = 'serialize_type_{0}'.format(
                field.__class__.__name__.lower())
            if hasattr(self, field_type_method_name):
                return getattr(self, field_type_method_name)(instance, field_name)

            if field.rel:
                # M2M
                if isinstance(field, ManyToManyField):
                    return [self.nested_serialize(r)
                            for r in getattr(instance, field.name).all()]

                rel = getattr(instance, field.name)
                # FK, OtO
                if rel:  # should be a model instance
                    if self.cur_depth >= self.max_depth:
                        return

                    return self.nested_serialize(rel)

        try:
            return getattr(instance, field_name)
        except AttributeError:
            raise AttributeError("The serializer doesn't know how to serialize {0}, "
                                 "please provide it a {1} method."
                                 "".format(field_name, method_name))

    def nested_serialize(self, rel):
        # check for Elasticsearch.serializer on the related model
        if hasattr(rel, 'Elasticsearch'):
            serializer = rel.es.get_serializer(max_depth=self.max_depth,
                                               cur_depth=self.cur_depth + 1)
            obj = serializer.format(rel)
            return obj

        # Fallback on a dict with id + __unicode__ value of the related model instance.
        return dict(id=rel.pk, value=unicode(rel))

    def format(self, instance):
        # from a model instance to a dict
        fields = self.model.es.get_fields()
        obj = dict([(field, self.serialize_field(instance, field))
                    for field in fields])

        # adding auto complete fields
        completion_fields = instance.Elasticsearch.completion_fields
        for field_name in completion_fields or []:
            suggest_name = "{0}_complete".format(field_name)
            # TODO: could store the value of field_name in case it does some
            # heavy processing or db requests.
            obj[suggest_name] = self.serialize_field(instance, field_name)

        return obj

    def serialize(self, instance):
        return json.dumps(self.format(instance),
                          default=lambda d: (
                              d.isoformat() if isinstance(d, datetime.datetime)
                              or isinstance(d, datetime.date) else None))


class EsJsonSerializer(EsModelToJsonMixin, EsJsonToModelMixin, EsSerializer):
    """
    Default elasticsearch serializer for a django model
    """
    pass


class EsSimpleJsonSerializer(EsModelToJsonMixin, EsDbMixin, EsSerializer):
    pass
