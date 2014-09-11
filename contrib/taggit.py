from django_elasticsearch.serializers import ModelJsonSerializer


class TaggitSerializer(ModelJsonSerializer):
    """
    Serialize a model with its tags,
    use the es_serializer_class attribute of your model
    """
    tags_attribute_name = 'tags'

    def get_default_fields(self):
        # also returns the tags by default
        fields = super(TaggitSerializer, self).get_default_fields()
        fields.append(self.tags_attribute_name)
        return fields

    def get_tags_val(self):
        manager = getattr(self.instance, self.tags_attribute_name)
        return [unicode(t.name) for t in manager.all()]
