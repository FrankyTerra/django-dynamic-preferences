"""
Preference models, queryset and managers that handle the logic for persisting preferences.
"""

from django.db import models
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.db.models.query import QuerySet
from .utils import update
from django.conf import settings
from django.utils.functional import cached_property
from dynamic_preferences.registries import user_preferences_registry, site_preferences_registry, global_preferences_registry, per_instance_preferences



class PreferenceModelManager(models.Manager):

    def to_dict(self, **kwargs):
        """ 
            Return a dict of preference models values with the same structure as registries
            Used to access preferences value within templates
        """ 

        preferences = self.get_queryset().all()
        if kwargs: 
            preferences = preferences.filter(**kwargs)

        d = {}
        for p in preferences:
            try:
                d[p.section][p.name] = p.value
            except KeyError:
                d[p.section] = {}
                d[p.section][p.name] = p.value

        return d

class BasePreferenceModel(models.Model):
    """
    A base model with common logic for all preferences models.
    """

    #: The section under which the preference is declared
    section = models.TextField(max_length=255, db_index=True, blank=True, null=True, default=None)

    #: a name for the preference
    name = models.TextField(max_length=255, db_index=True)

    #: a value, serialized to a string. This field should not be accessed directly, use :py:attr:`BasePreferenceModel.value` instead
    raw_value = models.TextField(null=True, blank=True)

    #: Keep a reference to the whole preference registry.
    #: In order to map the Preference Model Instance to the Preference object.
    registry = None

    objects = PreferenceModelManager()

    class Meta:
        abstract = True
        app_label = 'dynamic_preferences'


    def __init__(self, *args, **kwargs):
        # Check if the model is already saved in DB
        v = kwargs.pop("value", None)
        super(BasePreferenceModel, self).__init__(*args, **kwargs)

        new = self.pk is None

        if new:
            if v is not None:
                self.value = v
            else:
                self.value = self.preference.default

    @cached_property
    def preference(self):
        return self.registry.get(section=self.section, name=self.name)

    def set_value(self, value):
        """
            Save serialized self.value to self.raw_value
        """
        self.raw_value = self.preference.serializer.serialize(value)

    def get_value(self):
        """
            Return deserialized self.raw_value
        """
        return self.preference.serializer.deserialize(self.raw_value)

    value = property(get_value, set_value)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return '{0} - {1}/{2}: {3}'.format(self.__class__.__name__, self.section, self.name, self.value)

class GlobalPreferenceModel(BasePreferenceModel):

    registry = global_preferences_registry

    class Meta:
        unique_together = ('section', 'name')
        app_label = 'dynamic_preferences'

        verbose_name = "global preference"
        verbose_name_plural = "global preferences"



class PerInstancePreferenceModel(BasePreferenceModel):
    """For preferences that are tied to a specific model instance"""
    #: the instance which is concerned by the preference
    #: use a ForeignKey pointing to the model of your choice 
    instance = None

    class Meta(BasePreferenceModel.Meta):
        unique_together = ('instance', 'section', 'name')
        abstract = True

class UserPreferenceModel(PerInstancePreferenceModel):

    instance = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="preferences")
    registry = user_preferences_registry

    class Meta(PerInstancePreferenceModel.Meta):
        app_label = 'dynamic_preferences'
        verbose_name = "user preference"
        verbose_name_plural = "user preferences"

    @property
    def user(self):
        return self.instance
    @user.setter
    def user(self, value):
        self.instance = value
    

class SitePreferenceModel(BasePreferenceModel):

    instance = models.ForeignKey(Site, related_name="preferences")
    registry = site_preferences_registry

    class Meta(PerInstancePreferenceModel.Meta):
        app_label = 'dynamic_preferences'
        verbose_name = "site preference"
        verbose_name_plural = "site preferences"


    @property
    def site(self):
        return self.instance
    @site.setter
    def site(self, value):
        self.instance = value

global_preferences = GlobalPreferenceModel.objects
site_preferences = SitePreferenceModel.objects
user_preferences = UserPreferenceModel.objects





# Create default preferences for new users
# Right now, only works if the model is django.contrib.auth.models.User
# And if settings.CREATE_DEFAULT_PREFERENCES_FOR_NEW_USERS is set to True in settings

from django.db.models.signals import post_save
from django.contrib.auth.models import User

def create_default_per_instance_preferences(sender, created, instance, **kwargs): 
    """Create default preferences for PerInstancePreferenceModel"""
    preference_class = per_instance_preferences.get(sender)
    if created and preference_class:
        preference_class.registry.create_default_preferences(instance)


post_save.connect(create_default_per_instance_preferences)