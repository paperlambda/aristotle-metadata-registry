from django.conf.urls import url
from aristotle_mdr.contrib.favourites import views

urlpatterns = [
    url(r'^toggleFavourite/(?P<iid>\d+)/?$', views.ToggleFavourite.as_view(), name='toggleFavourite'),
]
