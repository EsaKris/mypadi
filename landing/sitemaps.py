from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from landlords.models import Property
from landlords.models import User as Landlord
from seekers.models import User as Seeker

class CombinedSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        static_pages = ['landing:home', 'landing:property_list']
        properties = Property.objects.all()
        landlords = Landlord.objects.all()
        seekers = Seeker.objects.all()
        return list(static_pages) + list(properties) + list(landlords) + list(seekers)

    def location(self, item):
        if isinstance(item, str):
            return reverse(item)
        elif hasattr(item, 'slug'):
            return reverse('landing:property_detail', kwargs={'slug': item.slug})
        elif isinstance(item, Landlord):
            return reverse('landlords:dashboard')  # or landlord profile page
        elif isinstance(item, Seeker):
            return reverse('seekers:dashboard')  # or seeker profile page
        return '/'
