from django.test import TestCase, tag
from aristotle_mdr.tests.utils import AristotleTestUtils
from aristotle_mdr import models as mdr_models
from aristotle_mdr.contrib.favourites import models
from aristotle_mdr.utils import url_slugify_concept
from django.contrib.messages import get_messages
from django.urls import reverse

import json
import re


@tag('favourites')
class FavouritesTestCase(AristotleTestUtils, TestCase):

    def setUp(self):
        super().setUp()
        self.timtam = mdr_models.ObjectClass.objects.create(
            name='Tim Tam',
            definition='Chocolate covered biscuit',
            submitter=self.editor
        )
        self.tastiness = mdr_models.Property.objects.create(
            name='Tastiness',
            definition='How good an item tastes',
            submitter=self.editor
        )
        self.ttt = mdr_models.DataElementConcept.objects.create(
            name='Tim Tam - Tastiness',
            definition='Tim Tam - Tastiness',
            objectClass=self.timtam,
            property=self.tastiness,
            submitter=self.editor
        )

    # --- Utils ---

    def create_some_favs_and_tags(self):
        # Create tags
        tag1 = models.Tag.objects.create(
            profile=self.editor.profile,
            name='very good'
        )
        tag2 = models.Tag.objects.create(
            profile=self.editor.profile,
            name='awesome'
        )
        favtag = models.Tag.objects.create(
            profile=self.editor.profile,
            name='',
            primary=True
        )

        # Add favourites
        models.Favourite.objects.create(
            tag=favtag,
            item=self.timtam
        )
        models.Favourite.objects.create(
            tag=favtag,
            item=self.ttt
        )

        # Add Tags
        models.Favourite.objects.create(
            tag=tag1,
            item=self.ttt
        )
        models.Favourite.objects.create(
            tag=tag2,
            item=self.tastiness
        )

    def check_favourite(self, user, item, status):
        favourited = models.Favourite.objects.filter(
            item_id=item.id,
            tag__primary=True,
            tag__profile=user.profile
        ).exists()
        self.assertEqual(favourited, status)

    def check_tag(self, user, item, tag, status):

        tagged = models.Favourite.objects.filter(
            item_id=item.id,
            tag__primary=False,
            tag__profile=user.profile,
            tag__name=tag
        ).exists()
        self.assertEqual(tagged, status)

    def check_tag_count(self, user, count):
        user_tags = models.Tag.objects.filter(
            profile=user.profile
        ).count()
        self.assertEqual(user_tags, count)

    def check_favourite_count(self, user, count):
        user_favourites = models.Favourite.objects.filter(
            tag__profile=user.profile
        ).count()
        self.assertEqual(user_favourites, count)

    # --- Tests ---

    def test_toggle_favourite_function_on(self):

        self.login_editor()
        self.check_favourite(self.editor, self.timtam, False)

        self.editor.profile.toggleFavourite(self.timtam)

        self.check_favourite(self.editor, self.timtam, True)

    def test_toggle_favourite_function_off(self):

        self.login_editor()
        self.check_favourite(self.editor, self.timtam, False)

        self.editor.profile.toggleFavourite(self.timtam)

        self.check_favourite(self.editor, self.timtam, True)

        self.editor.profile.toggleFavourite(self.timtam)

        self.check_favourite(self.editor, self.timtam, False)

    def test_toggle_favourite_on_view(self):

        self.login_editor()
        self.check_favourite(self.editor, self.timtam, False)

        response = self.reverse_get(
            'aristotle_favourites:toggleFavourite',
            reverse_args=[self.timtam.id],
            status_code=302
        )
        self.assertEqual(response.url, url_slugify_concept(self.timtam))
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(messages[1].message.startswith('Tim Tam added to favourites'))

        self.check_favourite(self.editor, self.timtam, True)

    def test_toggle_favourite_off_view(self):

        primtag = models.Tag.objects.create(
            profile=self.editor.profile,
            name='',
            primary=True
        )
        models.Favourite.objects.create(
            tag=primtag,
            item=self.timtam
        )

        self.login_editor()
        self.check_favourite(self.editor, self.timtam, True)

        response = self.reverse_get(
            'aristotle_favourites:toggleFavourite',
            reverse_args=[self.timtam.id],
            status_code=302
        )
        self.assertEqual(response.url, url_slugify_concept(self.timtam))
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(messages[1].message.startswith('Tim Tam removed from favourites'))

        self.check_favourite(self.editor, self.timtam, False)

    def test_toggle_favourite_view_json(self):

        self.login_editor()
        self.check_favourite(self.editor, self.tastiness, False)

        response = self.reverse_get(
            'aristotle_favourites:toggleFavourite',
            reverse_args=[self.tastiness.id],
            status_code=200,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        response_obj = json.loads(response.content)

        self.check_favourite(self.editor, self.tastiness, True)

        self.assertTrue(response_obj['success'])
        self.assertTrue(response_obj['favourited'])
        self.assertTrue(response_obj['message'].startswith('Tastiness added to favourites'))

    def test_toggle_non_viewable(self):

        self.login_viewer()

        response = self.reverse_get(
            'aristotle_favourites:toggleFavourite',
            reverse_args=[self.timtam.id],
            status_code=403
        )

    def test_toggle_next_redirect(self):

        self.login_editor()

        toggle_url = reverse('aristotle_favourites:toggleFavourite', args=[self.timtam.id]) + '?next=/about'
        response = self.client.get(toggle_url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/about')

    def test_tag_edit_add_tags(self):

        self.login_editor()

        tags = ['very good', 'amazing']
        post_data = {
            'tags': json.dumps(tags)
        }

        response = self.reverse_post(
            'aristotle_favourites:edit_tags',
            post_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            reverse_args=[self.timtam.id]
        )

        response_obj = json.loads(response.content)
        self.assertTrue(response_obj['success'])

        self.check_tag(self.editor, self.timtam, 'very good', True)
        self.check_tag(self.editor, self.timtam, 'amazing', True)

        self.check_tag_count(self.editor, 2)
        self.check_favourite_count(self.editor, 2)

    def test_tag_edit_add_and_remove_tags(self):

        self.login_editor()

        tag = models.Tag.objects.create(
            profile=self.editor.profile,
            name='very good',
            primary=False
        )
        models.Favourite.objects.create(
            tag=tag,
            item=self.timtam,
        )

        post_data = {
            'tags': json.dumps(['10/10'])
        }

        response = self.reverse_post(
            'aristotle_favourites:edit_tags',
            post_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            reverse_args=[self.timtam.id]
        )

        response_obj = json.loads(response.content)
        self.assertTrue(response_obj['success'])

        self.check_tag(self.editor, self.timtam, 'very good', False)
        self.check_tag(self.editor, self.timtam, '10/10', True)

        self.check_tag_count(self.editor, 2)
        self.check_favourite_count(self.editor, 1)

    def test_tags_json_on_item_page(self):
        tag1 = models.Tag.objects.create(
            profile=self.editor.profile,
            name='very good',
            primary=False
        )
        tag2 = models.Tag.objects.create(
            profile=self.editor.profile,
            name='awesome',
            primary=False
        )
        tag3 = models.Tag.objects.create(
            profile=self.editor.profile,
            name='amazing',
            primary=False
        )
        primtag = models.Tag.objects.create(
            profile=self.editor.profile,
            name='',
            primary=True
        )
        models.Favourite.objects.create(
            tag=tag1,
            item=self.timtam,
        )
        models.Favourite.objects.create(
            tag=tag2,
            item=self.timtam,
        )

        tags = {
            'item': ['very good', 'awesome'],
            'user': ['very good', 'awesome', 'amazing']
        }

        self.login_editor()
        response = self.reverse_get(
            'aristotle:item',
            reverse_args=[self.timtam.id, 'objectclass', 'tim-tam']
        )
        result = re.search('<script id="tags-json".*?>(.*?)</script>', str(response.content))
        rendered = json.loads(result.group(1))

        self.assertCountEqual(rendered['item'], tags['item'])
        self.assertCountEqual(rendered['user'], tags['user'])

    def test_edit_tag_description(self):

        tag = models.Tag.objects.create(
            profile=self.editor.profile,
            name='very good'
        )
        post_data = {
            'description': 'Metadata that is very good'
        }

        self.login_editor()
        response = self.reverse_post(
            'aristotle_favourites:tag_edit',
            post_data,
            reverse_args=[tag.id],
            status_code=302
        )
        self.assertEqual(response.url, reverse('aristotle_favourites:tag', args=[tag.id]))

        tag = models.Tag.objects.get(id=tag.id)
        self.assertEqual(tag.description, 'Metadata that is very good')
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(messages[1].message.startswith('Description updated'))

    def test_edit_tag_description_json(self):
        tag = models.Tag.objects.create(
            profile=self.editor.profile,
            name='very good'
        )
        post_data = {
            'description': 'Metadata that is very good'
        }

        self.login_editor()
        response = self.reverse_post(
            'aristotle_favourites:tag_edit',
            post_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            reverse_args=[tag.id],
            status_code=200
        )
        response_obj = json.loads(response.content)

        tag = models.Tag.objects.get(id=tag.id)
        self.assertEqual(tag.description, 'Metadata that is very good')
        self.assertEqual(response_obj['success'], True)
        self.assertEqual(response_obj['message'], 'Tag description updated')

    def test_edit_tag_description_empty(self):
        tag = models.Tag.objects.create(
            profile=self.editor.profile,
            name='very good',
            description='only the best of the best'
        )
        post_data = {
            'description': ''
        }

        self.login_editor()
        response = self.reverse_post(
            'aristotle_favourites:tag_edit',
            post_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            reverse_args=[tag.id],
            status_code=200
        )
        response_obj = json.loads(response.content)

        tag = models.Tag.objects.get(id=tag.id)
        self.assertEqual(tag.description, '')
        self.assertEqual(response_obj['success'], True)
        self.assertEqual(response_obj['message'], 'Tag description updated')

    def test_favs_and_tags_display(self):

        self.create_some_favs_and_tags()

        # Check favs and tags page
        self.login_editor()
        response = self.reverse_get(
            'aristotle_favourites:favs_and_tags',
            status_code=200
        )
        obj_list = response.context['object_list']
        self.assertEqual(len(obj_list), 3)

        # Check favs and tags list
        self.assertEqual(obj_list[0].id, self.tastiness.id)
        self.assertEqual(obj_list[0].item_favourite, 0)
        self.assertEqual(len(obj_list[0].user_favourites), 1)

        self.assertEqual(obj_list[1].id, self.ttt.id)
        self.assertEqual(obj_list[1].item_favourite, 1)
        self.assertEqual(len(obj_list[1].user_favourites), 1)

        self.assertEqual(obj_list[2].id, self.timtam.id)
        self.assertEqual(obj_list[2].item_favourite, 1)
        self.assertEqual(len(obj_list[2].user_favourites), 0)

    def test_favs_and_tags_tag_list(self):

        self.create_some_favs_and_tags()

        # Check favs and tags page
        self.login_editor()
        response = self.reverse_get(
            'aristotle_favourites:favs_and_tags',
            status_code=200
        )

        tags = response.context['tags']

        self.assertEqual(tags[0].name, 'awesome')
        self.assertEqual(tags[1].name, 'very good')

    def test_tag_view(self):

        tag = models.Tag.objects.create(
            profile=self.editor.profile,
            name='mytag'
        )
        favtag = models.Tag.objects.create(
            profile=self.editor.profile,
            name='',
            primary=True
        )

        models.Favourite.objects.create(
            tag=tag,
            item=self.timtam
        )
        models.Favourite.objects.create(
            tag=tag,
            item=self.ttt
        )
        models.Favourite.objects.create(
            tag=favtag,
            item=self.timtam
        )

        self.login_editor()
        response = self.reverse_get(
            'aristotle_favourites:tag',
            reverse_args=[tag.id],
            status_code=200
        )

        obj_list = response.context['object_list']
        self.assertEqual(len(obj_list), 2)

        self.assertEqual(obj_list[0].id, self.timtam.id)
        self.assertEqual(obj_list[0].item_favourite, 1)

        self.assertEqual(obj_list[1].id, self.ttt.id)
        self.assertEqual(obj_list[1].item_favourite, 0)

    def test_tag_view_invalid_tag(self):

        self.login_editor()
        response = self.reverse_get(
            'aristotle_favourites:tag',
            reverse_args=[777],
            status_code=404
        )

    def test_favourite_view(self):

        tag = models.Tag.objects.create(
            profile=self.editor.profile,
            name='mytag'
        )
        favtag = models.Tag.objects.create(
            profile=self.editor.profile,
            name='',
            primary=True
        )

        models.Favourite.objects.create(
            tag=tag,
            item=self.timtam
        )
        models.Favourite.objects.create(
            tag=favtag,
            item=self.timtam
        )
        models.Favourite.objects.create(
            tag=favtag,
            item=self.tastiness
        )

        self.login_editor()
        response = self.reverse_get(
            'aristotle_favourites:favs',
            status_code=200
        )

        self.assertNotContains(response, 'fa-bookmark-o')
        obj_list = response.context['object_list']
        self.assertEqual(len(obj_list), 2)

        self.assertEqual(obj_list[0].id, self.tastiness.id)
        self.assertEqual(obj_list[1].id, self.timtam.id)

    def test_all_tag_view(self):

        tag1 = models.Tag.objects.create(
            profile=self.editor.profile,
            name='my tag'
        )
        tag2 = models.Tag.objects.create(
            profile=self.editor.profile,
            name='my other tag'
        )
        favtag = models.Tag.objects.create(
            profile=self.editor.profile,
            name='',
            primary=True
        )

        models.Favourite.objects.create(
            tag=tag1,
            item=self.timtam
        )
        models.Favourite.objects.create(
            tag=tag2,
            item=self.timtam
        )
        models.Favourite.objects.create(
            tag=tag2,
            item=self.ttt
        )

        self.login_editor()
        response = self.reverse_get(
            'aristotle_favourites:all_tags',
            status_code=200
        )
        obj_list = response.context['object_list']

        self.assertEqual(len(obj_list), 2)
        self.assertEqual(obj_list[0].id, tag2.id)
        self.assertEqual(obj_list[0].num_items, 2)
        self.assertEqual(obj_list[1].id, tag1.id)
        self.assertEqual(obj_list[1].num_items, 1)

    def test_delete_valid_tag(self):

        tag1 = models.Tag.objects.create(
            profile=self.editor.profile,
            name='my tag'
        )
        tag2 = models.Tag.objects.create(
            profile=self.editor.profile,
            name='my other tag'
        )

        self.login_editor()
        postdata = {
            'tagid': tag1.id
        }
        response = self.reverse_post(
            'aristotle_favourites:tag_delete',
            postdata,
            status_code=200
        )

        self.assertFalse(models.Tag.objects.filter(id=postdata['tagid']).exists())

    def test_delete_invalid_tag(self):

        self.login_editor()
        postdata = {
            'tagid': 777
        }
        response = self.reverse_post(
            'aristotle_favourites:tag_delete',
            postdata,
            status_code=200
        )
        response_obj = json.loads(response.content)

        self.assertFalse(response_obj['success'])
        self.assertEqual(response_obj['message'], 'Tag not found')

    def test_delete_tag_witout_permission(self):

        tag1 = models.Tag.objects.create(
            profile=self.editor.profile,
            name='my tag'
        )

        self.login_viewer()
        postdata = {
            'tagid': tag1.id
        }
        response = self.reverse_post(
            'aristotle_favourites:tag_delete',
            postdata,
            status_code=200
        )
        response_obj = json.loads(response.content)

        self.assertFalse(response_obj['success'])
        self.assertEqual(response_obj['message'], 'Tag could not be deleted')
