from django.shortcuts import get_object_or_404
from aristotle_mdr.utils import url_slugify_concept
from django.contrib.auth.decorators import login_required
from aristotle_mdr.models import _concept
from aristotle_mdr.perms import user_can_view
from django.utils.translation import ugettext_lazy as _
from django.views.generic import View, ListView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.urls import reverse
from django.http.response import JsonResponse, HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from aristotle_mdr.contrib.favourites.models import Favourite, Tag
from django.db.models import Sum, Case, When, Count, Max, Min, F, Prefetch
from aristotle_mdr.views.utils import AjaxFormMixin
from aristotle_mdr.models import _concept

import json
from collections import defaultdict


class ToggleFavourite(LoginRequiredMixin, View):

    def get(self, request, *args, **kwargs):
        itemid = self.kwargs['iid']
        item = get_object_or_404(_concept, pk=itemid).item

        if not user_can_view(request.user, item):
            return HttpResponseForbidden()

        favourited = request.user.profile.toggleFavourite(item)

        if request.is_ajax():
            return self.get_json_response(item, favourited)
        else:
            if self.request.GET.get('next', None):
                return HttpResponseRedirect(self.request.GET.get('next'))
            else:
                return self.redirect_with_message(item, favourited)

    def get_message(self, item, favourited):

        if favourited:
            message = _("%s added to favourites.") % (item.name)
        else:
            message = _("%s removed from favourites.") % (item.name)

        message = _(message + " Review your favourites from the user menu.")
        return message

    def redirect_with_message(self, item, favourited):
        message = self.get_message(item, favourited)
        messages.add_message(self.request, messages.SUCCESS, message)
        return HttpResponseRedirect(url_slugify_concept(item))

    def get_json_response(self, item, favourited):
        message = self.get_message(item, favourited)
        response_dict = {
            'success': True,
            'message': message,
            'favourited': favourited
        }
        return JsonResponse(response_dict)


class EditTags(LoginRequiredMixin, View):

    def post(self, request, *args, **kwargs):

        user = self.request.user
        post_data = self.request.POST
        item_id = self.kwargs['iid']
        item = get_object_or_404(_concept, pk=item_id)

        # Get all the tags on this item by this user
        current_tags = Favourite.objects.filter(
            tag__profile=user.profile,
            tag__primary=False,
            item=item
        ).values_list('tag__name', flat=True)

        tags_json = post_data.get('tags', '')

        if tags_json:
            tags = set(json.loads(tags_json))
            current_set = set(current_tags)

            new = tags - current_set
            deleted = current_set - tags

            for tag in new:
                tag_obj, created = Tag.objects.get_or_create(
                    profile=user.profile,
                    name=tag,
                    primary=False
                )
                Favourite.objects.create(
                    tag=tag_obj,
                    item=item
                )

            for tag in deleted:
                tag_obj, created = Tag.objects.get_or_create(
                    profile=user.profile,
                    name=tag,
                    primary=False
                )
                Favourite.objects.filter(
                    tag=tag_obj,
                    item=item
                ).delete()

        return self.get_json_response()

    def get_json_response(self, success=True):
        response_dict = {
            'success': success,
        }

        if success:
            response_dict['message'] = 'Tags Updated'

        return JsonResponse(response_dict)


class FavouritesAndTags(LoginRequiredMixin, ListView):

    paginate_by = 20
    template_name = "aristotle_mdr/favourites/userFavourites.html"

    def get_queryset(self):

        favourite_queryset = Favourite.objects.filter(
            tag__profile=self.request.user.profile,
            tag__primary=False
        ).select_related('tag')

        return _concept.objects.filter(
            favourites__tag__profile=self.request.user.profile
        ).distinct().prefetch_related(
            Prefetch('favourites', queryset=favourite_queryset, to_attr='user_favourites')
        ).annotate(
            item_favourite=Count(
                Case(When(favourites__tag__primary=True, then=1))
            ),
            used=Max('favourites__created')
        ).order_by('-used')

    def get_tags(self):

        # Get a users tags ordered by last usage, limited to 5
        return Tag.objects.filter(
            profile=self.request.user.profile,
            primary=False
        ).annotate(
            used=Max('favourites__created')
        ).order_by(
            F('used').desc(nulls_last=True)
        )[:5]

    def get_context_data(self, *args, **kwargs):
        context = super().get_context_data(*args, **kwargs)
        context['help'] = self.request.GET.get('help', False)
        context['favourite'] = self.request.GET.get('favourite', False)
        context['tags'] = self.get_tags()
        return context


class TagView(LoginRequiredMixin, ListView):

    paginate_by = 20
    template_name = "aristotle_mdr/favourites/tags.html"

    def dispatch(self, request, *args, **kwargs):
        self.tagid = self.kwargs['tagid']
        self.tag = get_object_or_404(Tag, pk=self.tagid)

        if self.tag.profile != request.user.profile:
            return HttpResponseForbidden()

        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):

        return _concept.objects.annotate(
            item_favourite=Count(
                Case(When(favourites__tag__primary=True, then=1))
            ),
            used=Max('favourites__created')
        ).filter(
            favourites__tag_id=self.tagid
        ).order_by('-used')

    def get_context_data(self):

        context = super().get_context_data()
        context['tag'] = self.tag
        context['title'] = self.tag.name
        context['vue'] = True
        return context


class FavouriteView(LoginRequiredMixin, ListView):

    paginate_by = 20
    template_name = "aristotle_mdr/favourites/tags.html"

    def get_queryset(self):

        try:
            tag = Tag.objects.get(profile=self.request.user.profile, primary=True)
        except Tag.DoesNotExist:
            return _concept.objects.none()

        return _concept.objects.annotate(
            used=Max('favourites__created')
        ).filter(
            favourites__tag=tag
        ).order_by('-used')

    def get_context_data(self):

        context = super().get_context_data()
        context['title'] = 'My Favourites'
        context['all_favourite'] = True
        return context


class AllTagView(LoginRequiredMixin, ListView):

    paginate_by = 20
    template_name = "aristotle_mdr/favourites/all_tags.html"

    def get_queryset(self):
        return Tag.objects.filter(
            profile=self.request.user.profile,
            primary=False
        ).annotate(
            num_items=Count('favourites')
        ).order_by('-created')

    def get_context_data(self):
        context = super().get_context_data()
        context['vue'] = True
        return context


class DeleteTagView(LoginRequiredMixin, View):

    def post(self, request, *args, **kwargs):
        pk = self.request.POST['tagid']
        message = ''
        success = False

        try:
            tag = Tag.objects.get(pk=pk)
        except:
            message = 'Tag not found'
            tag = None

        if tag is not None:
            if tag.profile.id == self.request.user.profile.id:
                tag.delete()
                success = True
            else:
                message = 'Tag could not be deleted'

        return JsonResponse({
            'success': success,
            'message': message
        })


class EditTagView(AjaxFormMixin, UpdateView):
    model = Tag
    fields = ['description']
    pk_url_kwarg = 'tagid'
    ajax_success_message = 'Tag description updated'

    def get_success_url(self):
        return reverse('aristotle_favourites:tag', args=[self.kwargs['tagid']])

    def form_invalid(self, form):
        if not self.request.is_ajax():
            messages.add_message(self.request, messages.SUCCESS, 'Description could not be updated')
            return HttpResponseRedirect(self.get_success_url())
        return super().form_invalid(form)

    def form_valid(self, form):
        if not self.request.is_ajax():
            messages.add_message(self.request, messages.SUCCESS, 'Description updated')
        return super().form_valid(form)
