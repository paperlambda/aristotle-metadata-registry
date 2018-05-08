from django.db import transaction
from django.forms.models import inlineformset_factory
from django.http import HttpResponseRedirect
from django.views.generic import (
    CreateView, DetailView, UpdateView
)

import reversion

from aristotle_mdr.utils import (
    concept_to_clone_dict,
    construct_change_message, url_slugify_concept, is_active_module
)
from aristotle_mdr import forms as MDRForms
from aristotle_mdr import models as MDR

from aristotle_mdr.views.utils import ObjectLevelPermissionRequiredMixin

import logging

from aristotle_mdr.contrib.generic.forms import (
    one_to_many_formset_factory, one_to_many_formset_save,
    one_to_many_formset_excludes, one_to_many_formset_filters,
    through_formset_factory, ordered_formset_save
)
import re

logger = logging.getLogger(__name__)
logger.debug("Logging started for " + __name__)


class ConceptEditFormView(ObjectLevelPermissionRequiredMixin):
    raise_exception = True
    redirect_unauthenticated_users = True
    object_level_permissions = True
    model = MDR._concept
    pk_url_kwarg = 'iid'

    def dispatch(self, request, *args, **kwargs):
        self.item = super().get_object().item
        self.model = self.item.__class__
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context.update({'model': self.model._meta.model_name,
                        'app_label': self.model._meta.app_label,
                        'item': self.item})
        return context


class EditItemView(ConceptEditFormView, UpdateView):
    template_name = "aristotle_mdr/actions/advanced_editor.html"
    permission_required = "aristotle_mdr.user_can_edit"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.slots_active = is_active_module('aristotle_mdr.contrib.slots')
        self.identifiers_active = is_active_module('aristotle_mdr.contrib.identifiers')

    def get_form_class(self):
        return MDRForms.wizards.subclassed_edit_modelform(self.model)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'user': self.request.user,
            'instance': self.item,
        })
        return kwargs

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        slot_formset = None
        self.object = self.item
        through_list = self.get_m2m_through(self.item)

        if form.is_valid():
            with transaction.atomic(), reversion.revisions.create_revision():
                item = form.save(commit=False)

                has_change_comments = form.data.get('change_comments', False)
                change_comments = form.data.get('change_comments', "")
                changed_formsets = []
                if self.slots_active:
                    slot_formset = self.get_slots_formset()(request.POST, request.FILES, item.concept)
                    if slot_formset.is_valid():

                        # Save the slots
                        slot_formset.save()

                        changed_formsets.append(slot_formset)

                    else:
                        return self.form_invalid(form, slots_FormSet=slot_formset)

                if self.identifiers_active:
                    id_formset = self.get_identifier_formset()(request.POST, request.FILES, item.concept)
                    if id_formset.is_valid():

                        # Save the slots
                        id_formset.save()

                        changed_formsets.append(id_formset)

                    else:
                        return self.form_invalid(form, identifier_FormSet=id_formset)

                if (hasattr(self.item, 'serialize_weak_entities')):
                    # if weak formset is active
                    weak = self.item.serialize_weak_entities

                    for entity in weak:

                        formset_info = self.get_weak_formset(entity)

                        weak_formset = formset_info['formset'](request.POST, request.FILES, prefix=formset_info['prefix'])

                        if weak_formset.is_valid():
                            one_to_many_formset_save(weak_formset, self.item, formset_info['model_field'], formset_info['ordering'])

                            changed_formsets.append(weak_formset)

                        else:
                            return self.form_invalid(form, weak_formset=weak_formset)

                if through_list:
                    # If there are through formsets
                    for through in through_list:
                        formset = self.get_order_formset(through, request.POST)

                        if formset.is_valid():

                            ordered_formset_save(formset, self.item, through['item_fields'][0], 'order')
                            changed_formsets.append(formset)

                        else:

                            return self.form_invalid(form, through_formset=through_formset)


                # save the change comments
                if not has_change_comments:
                    change_comments += construct_change_message(request, form, changed_formsets)

                reversion.revisions.set_user(request.user)
                reversion.revisions.set_comment(change_comments)
                form.save_m2m()
                item.save()
                return HttpResponseRedirect(url_slugify_concept(self.item))

        return self.form_invalid(form)

    def get_slots_formset(self):
        from aristotle_mdr.contrib.slots.forms import slot_inlineformset_factory
        return slot_inlineformset_factory(model=self.model)

    def get_identifier_formset(self):
        from aristotle_mdr.contrib.identifiers.models import ScopedIdentifier

        return inlineformset_factory(
            MDR._concept, ScopedIdentifier,
            can_delete=True,
            fields=('concept', 'namespace', 'identifier', 'version'),
            extra=1,
            )

    def get_weak_model_field(self, field_model):
        # get the field in the model that we are adding so it can be excluded from form
        model_to_add_field = ''
        for field in field_model._meta.get_fields():
            if (field.is_relation):
                if (field.related_model == self.model):
                    model_to_add_field = field.name
                    break

        return model_to_add_field

    def get_weak_formset(self, entity):

        # where entity is an entry in serialize_weak_entities

        field_model = getattr(self.item, entity[1]).model
        model_to_add_field = self.get_weak_model_field(field_model)

        extra_excludes = one_to_many_formset_excludes(self.item, field_model)
        formset = one_to_many_formset_factory(field_model, model_to_add_field, field_model.ordering_field, extra_excludes)
        formset_info = {
            'formset': formset,
            'model_field': model_to_add_field,
            'prefix': entity[0],
            'ordering': field_model.ordering_field,
        }

        return formset_info

    def get_order_formset(self, through, postdata=None):
        excludes = ['order'] + through['item_fields']
        formset = through_formset_factory(through['model'], excludes)

        fsargs = {'prefix': through['field_name']}

        if len(through['item_fields']) == 1:
            through_filter = {through['item_fields'][0]: self.item}
            fsargs.update({'queryset': through['model'].objects.filter(**through_filter)})

        if postdata:
            fsargs.update({'data': postdata})

        formset_instance = formset(**fsargs)

        return formset_instance

    def get_m2m_through(self, item):
        through_list = []

        for field in item._meta.get_fields():
            if field.many_to_many:
                if hasattr(field.remote_field, 'through'):
                    through = field.remote_field.through
                    if not through._meta.auto_created:
                        item_fields = []
                        for through_field in through._meta.get_fields():
                            if through_field.is_relation:
                                logger.debug('realted model is {}'.format(through_field.related_model))
                                if through_field.related_model == self.item.__class__:
                                    item_fields.append(through_field.name)
                        through_list.append({'field_name': field.name, 'model': through, 'item_fields': item_fields})

        return through_list

    def form_invalid(self, form, slots_FormSet=None, identifier_FormSet=None, weak_formset=None):
        """
        If the form is invalid, re-render the context data with the
        data-filled form and errors.
        """
        return self.render_to_response(self.get_context_data(form=form, slots_FormSet=slots_FormSet, weak_formset=weak_formset))

    def get_context_data(self, *args, **kwargs):
        from aristotle_mdr.contrib.slots.models import Slot
        context = super().get_context_data(*args, **kwargs)
        if self.slots_active and kwargs.get('slots_FormSet', None):
            context['slots_FormSet'] = kwargs['slots_FormSet']
        else:
            context['slots_FormSet'] = self.get_slots_formset()(
                queryset=Slot.objects.filter(concept=self.item.id),
                instance=self.item.concept
                )
        from aristotle_mdr.contrib.identifiers.models import ScopedIdentifier
        if self.identifiers_active and kwargs.get('identifier_FormSet', None):
            context['identifier_FormSet'] = kwargs['identifier_FormSet']
        else:
            context['identifier_FormSet'] = self.get_identifier_formset()(
                queryset=ScopedIdentifier.objects.filter(concept=self.item.id),
                instance=self.item.concept
                )

        if (hasattr(self.item, 'serialize_weak_entities')):
            if kwargs.get('weak_formset', None):
                # Will only display the formset that produced an error
                weak_formset = kwargs['weak_formset']
                title = 'Edit ' + weak_formset.model.__name__
                formsets = [{'formset': weak_formset, 'title': title}]
                context['weak_formsets'] = formsets
            elif kwargs.get('through_formset', None):
                through_formset = kwargs.get('through_formset')
                title = through_formset.model.__name__.title()
                formsets = [{'formset': weak_formset, 'title': title}]
                context['through_formsets'] = formsets
            else:
                weak = self.item.serialize_weak_entities
                formsets = []
                for entity in weak:
                    # query weak entity
                    queryset = getattr(self.item, entity[1]).all()

                    formset = self.get_weak_formset(entity)['formset']

                    weak_formset = formset(
                        queryset=queryset,
                        initial=[{'ORDER': queryset.count() + 1}],
                        prefix=entity[0]
                    )

                    weak_formset = one_to_many_formset_filters(weak_formset, self.item)

                    title = 'Edit ' + queryset.model.__name__
                    # add spaces before capital letters
                    title = re.sub(r"\B([A-Z])", r" \1", title)

                    formsets.append({'formset': weak_formset, 'title': title})

                context['weak_formsets'] = formsets

        context['show_slots_tab'] = self.slots_active
        context['show_id_tab'] = self.identifiers_active

        through_list = self.get_m2m_through(self.item)
        through_formsets = []
        for through in through_list:
            formset = self.get_order_formset(through)
            through_formsets.append({'formset': formset, 'title': through['field_name'].title()})

        context['through_formsets'] = through_formsets

        return context


class CloneItemView(ConceptEditFormView, DetailView, CreateView):
    template_name = "aristotle_mdr/create/clone_item.html"
    permission_required = "aristotle_mdr.user_can_view"

    def get_form_class(self):
        return MDRForms.wizards.subclassed_clone_modelform(self.model)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({
            'user': self.request.user,
            'initial': concept_to_clone_dict(self.item)
        })
        return kwargs

    def post(self, request, *args, **kwargs):
        form = self.get_form()

        if form.is_valid():
            with transaction.atomic(), reversion.revisions.create_revision():
                new_clone = form.save(commit=False)
                new_clone.submitter = self.request.user
                new_clone.save()
                reversion.revisions.set_user(self.request.user)
                reversion.revisions.set_comment("Cloned from %s (id: %s)" % (self.item.name, str(self.item.pk)))
                return HttpResponseRedirect(url_slugify_concept(new_clone))
        else:
            return self.form_invalid(form)
