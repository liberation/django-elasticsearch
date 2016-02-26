import json
import datetime

from django.db.models import Model
from django.db.models import FieldDoesNotExist
from django.db.models.fields.related import ManyToManyField


class EsSerializer(object):
    def __init__(self, *args, **kwargs):
        pass

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

def post_save_attr(f):
    # Since related fields can't be set on instanciation
    # this decorator saves them for later
    def wrapper(*args, **kwargs):
        val = f(*args, **kwargs)
        serializer = args[0]
        field_name = args[2]
        serializer._post_save_attrs[field_name] = val
        return None
    return wrapper


class EsJsonToModelMixin(object):
    """
    Serializer mixin that attempts to instanciate the model
    from the json elasticsearch source
    (and disables db operations on the model).
    """
    def __init__(self, *args, **kwargs):
        self._post_save_attrs = {}
        super(EsJsonToModelMixin, self).__init__(*args, **kwargs)

    def instanciate(self, attrs):
        instance = self.model(**attrs)
        instance._is_es_deserialized = True

        # set m2m, fks and such
        # for k, v in self._post_save_attrs.iteritems():
        #     if v:
        #         try:
        #             setattr(instance, k, v)
        #         except TypeError, ValueError:
        #             # bypass ManyRelatedManager complaining
        #             # TODO
        #             # super(Model, instance).__setattr__(k, v)
        #             pass

        return instance

    def nested_deserialize(self, source, rel):
        # check for Elasticsearch.serializer on the related model
        model = rel.related_model
        if source and rel:
            if hasattr(model, 'Elasticsearch'):
                serializer = model.es.get_serializer()
                obj = serializer.deserialize(source)
                return obj
            elif 'id' in source and 'value' in source:
                # fallback
                return source

    def deserialize_type_datetimefield(self, source, field_name):
        val = source.get(field_name)
        if val:
            return datetime.datetime.strptime(val, '%Y-%m-%dT%H:%M:%S.%f')

    def deserialize_type_datefield(self, source, field_name):
        val = source.get(field_name)
        if val:
            return datetime.datetime.strptime(val, '%Y-%m-%d')

    def deserialize_type_timefield(self, source, field_name):
        val = source.get(field_name)
        if val:
            return datetime.datetime.strptime(val, '%H:%M:%S')

    def deserialize_type_rel(self, source, field_name):
        rel, model, direct, m2m = self.model._meta.get_field_by_name(field_name)
        val = source.get(field_name)
        if val:
            return [self.nested_deserialize(r, rel) for r in val]

    @post_save_attr
    def deserialize_type_manytoonerel(self, source, field_name):
        # reverse fk
        return self.deserialize_type_rel(source, field_name)

    @post_save_attr
    def deserialize_type_manytomanyrel(self, source, field_name):
        # reverse m2m
        return self.deserialize_type_rel(source, field_name)

    @post_save_attr
    def deserialize_type_foreignkey(self, source, field_name):
        rel, model, direct, m2m = self.model._meta.get_field_by_name(field_name)
        val = source.get(field_name)
        if val:
            return self.nested_deserialize(val, rel)

    @post_save_attr
    def deserialize_type_onetoonefield(self, source, field_name):
        return self.deserialize_type_foreignkey(source, field_name)

    @post_save_attr
    def deserialize_type_manytomanyfield(self, source, field_name):
        return self.deserialize_type_rel(source, field_name)

    # django <1.8 hack
    @post_save_attr
    def deserialize_type_relatedobject(self, source, field_name):
        return self.deserialize_type_rel(source, field_name)

    def deserialize_field(self, source, field_name):
        method_name = 'deserialize_{0}'.format(field_name)
        if hasattr(self, method_name):
            return getattr(self, method_name)(source, field_name)

        try:
            field, model, direct, m2m = self.model._meta.get_field_by_name(field_name)
        except FieldDoesNotExist:
            # Abstract field
            field = None

        if field:
            field_type_method_name = 'deserialize_type_{0}'.format(
                field.__class__.__name__.lower())
            if hasattr(self, field_type_method_name):
                return getattr(self, field_type_method_name)(source, field_name)

            return source.get(field_name)

    def deserialize(self, source):
        """
        Returns a model instance
        """
        attrs = {}

        for field_name in source.iterkeys():
            val = self.deserialize_field(source, field_name)
            if val:
                attrs[field_name] = val

        return self.instanciate(attrs)


class EsModelToJsonMixin(object):
    def __init__(self, model, max_depth=2, cur_depth=1):
        self.model = model
        # used in case of related field on 'self' to avoid infinite loop
        self.cur_depth = cur_depth
        self.max_depth = max_depth
        super(EsModelToJsonMixin, self).__init__(model, max_depth=max_depth, cur_depth=cur_depth)

    def serialize_type_rel(self, instance, field_name):
        if self.cur_depth >= self.max_depth:
            return

        return [self.nested_serialize(r)
                for r in getattr(instance, field_name).all()]

    def serialize_type_manytoonerel(self, instance, field_name):
        return self.serialize_type_rel(instance, field_name)

    def serialize_type_manytomanyrel(self, instance, field_name):
        return self.serialize_type_rel(instance, field_name)

    def serialize_type_foreignkey(self, instance, field_name):
        if self.cur_depth >= self.max_depth:
            return

        return self.nested_serialize(getattr(instance, field_name))

    def serialize_type_onetoonefield(self, instance, field_name):
        return self.serialize_type_foreignkey(instance, field_name)

    def serialize_type_manytomanyfield(self, instance, field_name):
        return self.serialize_type_rel(instance, field_name)

    # django <1.8 hack
    def serialize_type_relatedobject(self, instance, field_name):
        return self.serialize_type_rel(instance, field_name)

    def serialize_field(self, instance, field_name):
        method_name = 'serialize_{0}'.format(field_name)
        if hasattr(self, method_name):
            return getattr(self, method_name)(instance, field_name)

        try:
            field, model, direct, m2m = self.model._meta.get_field_by_name(field_name)
        except FieldDoesNotExist:
            # Abstract field
            field = None

        if field:
            field_type_method_name = 'serialize_type_{0}'.format(
                field.__class__.__name__.lower())
            if hasattr(self, field_type_method_name):
                return getattr(self, field_type_method_name)(instance, field_name)

        try:
            return getattr(instance, field_name)
        except AttributeError:
            raise AttributeError("The serializer doesn't know how to serialize {0}, "
                                 "please provide it a '{1}' method."
                                 "".format(field_name, method_name))

    def nested_serialize(self, rel):
        if rel is None:
            return

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
