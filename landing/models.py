from django.db import models

class Property(models.Model):
    title = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=15, decimal_places=2)
    main_image = models.ImageField(upload_to='properties/')
    is_featured = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    bedrooms = models.PositiveIntegerField(default=1)
    bathrooms = models.PositiveIntegerField(default=1)
    has_wifi = models.BooleanField(default=False)
    views = models.PositiveIntegerField(default=0)

    def __str__(self):
        return self.title

class Testimonial(models.Model):
    name = models.CharField(max_length=100)
    text = models.TextField()
    image = models.ImageField(upload_to='testimonials/', blank=True, null=True)
    location = models.CharField(max_length=100, blank=True)
    is_video = models.BooleanField(default=False)
    video_url = models.URLField(blank=True, null=True)
    date = models.DateField(auto_now_add=True)

    def __str__(self):
        return self.name

class Neighborhood(models.Model):
    name = models.CharField(max_length=100)
    map_image = models.ImageField(upload_to='neighborhoods/')
    avg_rent = models.CharField(max_length=100)
    description = models.TextField()
    best_for = models.CharField(max_length=255)
    transport = models.CharField(max_length=255)
    schools = models.CharField(max_length=255)
    favorites = models.CharField(max_length=255)
    tips = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class FAQ(models.Model):
    question = models.CharField(max_length=255)
    answer = models.TextField()

    def __str__(self):
        return self.question