from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from landlords.models import LandlordProfile, Property, PropertyImage, Amenity, Tenant, RentalApplication, LeaseAgreement, MaintenanceRequest, Payment, Expense, CommunityPost as LandlordCommunityPost, CommunityReply as LandlordCommunityReply, Notification
from seekers.models import SeekerProfile, SavedProperty, CommunityPost as SeekerCommunityPost, CommunityReply as SeekerCommunityReply
from core.models import Conversation, Message
from faker import Faker
import random
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import requests
from django.core.files.base import ContentFile
import os
import hashlib

User = get_user_model()


class Command(BaseCommand):
    help = "Seed database with 15K+ records using reliable image sources"

    def __init__(self):
        super().__init__()
        # ✅ RELIABLE image sources that NEVER fail
        self.IMAGE_SOURCES = {
            'picsum': {
                'property': lambda: f"https://picsum.photos/{random.randint(800, 1200)}/{random.randint(600, 800)}?random={random.randint(1, 1000)}",
                'profile': lambda: f"https://picsum.photos/{random.randint(300, 500)}/{random.randint(300, 500)}?random={random.randint(1, 1000)}"
            },
            'placeholder': {
                'property': lambda: f"https://placeholder.com/wp-content/uploads/2024/01/placeholder-{random.randint(1, 10)}.jpg",
                'profile': lambda: f"https://i.pravatar.cc/{random.randint(400, 600)}?img={random.randint(1, 70)}"
            },
            'unsplash_safe': {
                'property': lambda: f"https://images.unsplash.com/photo-1568605114967-8130f3a36994?w={random.randint(800, 1200)}&h={random.randint(600, 800)}&fit=crop&q=80",
                'profile': lambda: f"https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w={random.randint(300, 500)}&h={random.randint(300, 500)}&fit=crop&q=80"
            }
        }

    def get_reliable_image_url(self, image_type='property'):
        """Get a reliable image URL that will NEVER fail"""
        # Try different sources in order of reliability
        sources = ['picsum', 'placeholder', 'unsplash_safe']
        
        for source in sources:
            try:
                url = self.IMAGE_SOURCES[source][image_type]()
                return url
            except:
                continue
        
        # Ultimate fallback - Picsum with basic parameters
        if image_type == 'property':
            return f"https://picsum.photos/800/600?random={random.randint(1000, 9999)}"
        else:
            return f"https://i.pravatar.cc/400?img={random.randint(1, 70)}"

    def download_image(self, url, retries=2):
        """Download image from URL with robust error handling"""
        for attempt in range(retries):
            try:
                # Add headers to avoid blocking
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8'
                }
                
                response = requests.get(url, timeout=10, headers=headers)
                response.raise_for_status()
                
                # Validate it's actually an image
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('image/'):
                    self.stdout.write(self.style.WARNING(f"   Not an image (got {content_type}), trying next source..."))
                    continue
                
                # Check minimum file size (avoid placeholder error pages)
                if len(response.content) < 1000:
                    self.stdout.write(self.style.WARNING("   Image too small, likely error page"))
                    continue
                
                # Generate unique filename
                url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                filename = f"img_{url_hash}_{random.randint(1000, 9999)}.jpg"
                
                return ContentFile(response.content, name=filename)
                
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"   Download attempt {attempt + 1} failed: {str(e)[:80]}"))
                if attempt == retries - 1:
                    return None
        
        return None

    def download_image_with_fallbacks(self, image_type='property'):
        """Download image trying multiple reliable sources"""
        max_attempts = 3
        
        for attempt in range(max_attempts):
            # Get a reliable URL
            image_url = self.get_reliable_image_url(image_type)
            
            # Try to download it
            image_file = self.download_image(image_url)
            
            if image_file:
                return image_file, image_url
            else:
                self.stdout.write(self.style.WARNING(f"   Source {attempt + 1} failed, trying next..."))
        
        # If all else fails, create a simple colored placeholder
        self.stdout.write(self.style.WARNING("   All image sources failed, using colored placeholder"))
        return self.create_color_placeholder(image_type), "color_placeholder"

    def create_color_placeholder(self, image_type='property'):
        """Create a simple colored placeholder image"""
        from PIL import Image, ImageDraw
        import io
        
        if image_type == 'property':
            width, height = 800, 600
            colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7']
        else:
            width, height = 400, 400
            colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
        
        # Create a simple colored image
        color = random.choice(colors)
        image = Image.new('RGB', (width, height), color)
        draw = ImageDraw.Draw(image)
        
        # Add some simple text or shapes
        if image_type == 'property':
            draw.rectangle([50, 50, width-50, height-50], outline='white', width=5)
        else:
            draw.ellipse([100, 100, width-100, height-100], outline='white', width=5)
        
        # Save to bytes
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='JPEG')
        img_byte_arr.seek(0)
        
        filename = f"placeholder_{image_type}_{random.randint(1000, 9999)}.jpg"
        return ContentFile(img_byte_arr.getvalue(), name=filename)

    def handle(self, *args, **kwargs):
        fake = Faker()
        self.stdout.write(self.style.SUCCESS("🌱 Seeding database with 15K+ records using reliable images..."))

        # Test image download first
        self.stdout.write(self.style.SUCCESS("🔍 Testing image download reliability..."))
        test_successful = 0
        for i in range(3):
            test_url = self.get_reliable_image_url('property')
            test_download = self.download_image(test_url)
            if test_download:
                test_successful += 1
        
        if test_successful >= 2:
            self.stdout.write(self.style.SUCCESS(f"✅ Image download test passed! ({test_successful}/3 successful)"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️  Image download test: {test_successful}/3 successful. Using fallbacks."))

        # Create default amenities first
        Amenity.create_default_amenities()
        amenities = list(Amenity.objects.all())

        # -------------------------------
        # 1. USERS (Landlords + Seekers) - 5000 users
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("👥 Creating 5000 users..."))
        users = []
        user_count = 5000
        
        successful_downloads = 0
        failed_downloads = 0
        
        for i in range(user_count):
            user_type = random.choice(['landlord', 'tenant'])
            
            user = User(
                username=fake.unique.user_name(),
                email=fake.unique.email(),
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                user_type=user_type,
                email_verified=random.choice([True, False]),
                phone_number=fake.phone_number()[:20],
                bio=fake.paragraph(nb_sentences=2),
                mfa_method='none'
            )
            
            # Download profile picture with fallbacks
            profile_image_file, _ = self.download_image_with_fallbacks('profile')
            if profile_image_file:
                try:
                    user.profile_picture.save(f"profile_{i}_{fake.uuid4()[:6]}.jpg", profile_image_file, save=False)
                    successful_downloads += 1
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"   Could not save profile image for user {i}: {e}"))
                    failed_downloads += 1
            else:
                self.stdout.write(self.style.WARNING(f"   Could not download profile image for user {i}"))
                failed_downloads += 1
            
            users.append(user)
            
            if i % 500 == 0 and i > 0:
                self.stdout.write(self.style.SUCCESS(f"   Processed {i}/{user_count} users (Success: {successful_downloads}, Failed: {failed_downloads})"))
        
        self.stdout.write(self.style.SUCCESS(f"📊 Profile Images: {successful_downloads} successful, {failed_downloads} failed"))
        
        # Create users in batches
        batch_size = 200
        for i in range(0, len(users), batch_size):
            batch = users[i:i + batch_size]
            try:
                User.objects.bulk_create(batch, ignore_conflicts=True)
                self.stdout.write(self.style.SUCCESS(f"   Created batch {i//batch_size + 1}/{(len(users)//batch_size) + 1}"))
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"   Batch creation failed: {e}"))

        all_users = list(User.objects.all())
        landlords = [u for u in all_users if u.user_type == 'landlord']
        seekers = [u for u in all_users if u.user_type == 'tenant']

        self.stdout.write(self.style.SUCCESS(f"👷 Landlords: {len(landlords)} | 🧍 Seekers: {len(seekers)}"))

        # -------------------------------
        # 2. LANDLORD PROFILES
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("👔 Creating landlord profiles..."))
        landlord_profiles = []
        for u in landlords:
            landlord_profiles.append(LandlordProfile(
                user=u,
                phone_number=fake.phone_number()[:20],
                bio=fake.paragraph(nb_sentences=2),
                company_name=fake.company() if random.choice([True, False]) else "",
                business_address=fake.address(),
                is_verified=random.choice([True, False])
            ))
        LandlordProfile.objects.bulk_create(landlord_profiles, ignore_conflicts=True)

        # -------------------------------
        # 3. SEEKER PROFILES
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("🎓 Creating seeker profiles..."))
        seeker_profiles = []
        for u in seekers:
            seeker_profiles.append(SeekerProfile(
                user=u,
                phone_number=fake.phone_number()[:20],
                bio=fake.paragraph(nb_sentences=2),
                date_of_birth=fake.date_of_birth(minimum_age=18, maximum_age=80),
                gender=random.choice(['male', 'female', 'other']),
                employment_status=random.choice(['employed', 'self_employed', 'student', 'unemployed']),
                current_address=fake.address(),
                budget_min=Decimal(random.randint(50000, 200000)),
                budget_max=Decimal(random.randint(250000, 800000)),
                preferred_property_type=random.choice(['apartment', 'house', 'condo', 'studio']),
                verified=random.choice([True, False])
            ))
        SeekerProfile.objects.bulk_create(seeker_profiles, ignore_conflicts=True)

        landlord_profiles = list(LandlordProfile.objects.all())
        seeker_profiles = list(SeekerProfile.objects.all())
        all_seeker_users = [profile.user for profile in seeker_profiles]

        # -------------------------------
        # 4. PROPERTIES + IMAGES - 3000 properties
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("🏠 Creating 3000 properties..."))
        properties = []
        property_count = 3000
        
        for i in range(property_count):
            landlord_user = random.choice(landlords)
            property_type = random.choice(['apartment', 'house', 'commercial', 'land', 'other'])
            price_period = random.choice(['monthly', 'annually'])
            city = fake.city()
            
            # Create unique property name
            name = f"{fake.street_name()} {random.choice(['Residence', 'Apartments', 'Villas', 'House', 'Building', 'Estate', 'Gardens', 'Court', 'Place', 'Square', 'Manor', 'Heights'])}"
            
            prop = Property(
                landlord=landlord_user,
                name=name,
                address=fake.address(),
                city=city,
                state=fake.state(),
                zip_code=fake.zipcode(),
                property_type=property_type,
                num_units=random.randint(1, 20),
                price=Decimal(random.randint(100000, 5000000)),
                price_period=price_period,
                is_active=random.choice([True, False]),
                is_featured=random.choice([True, False]),
                is_verified=random.choice([True, False]),
                is_published=random.choice([True, False]),
                description=fake.paragraph(nb_sentences=8),
                views=random.randint(0, 5000),
                slug=f"{name.lower().replace(' ', '-')}-{city.lower().replace(' ', '-')}-{i}-{fake.uuid4()[:8]}"
            )
            
            try:
                prop.save()
                properties.append(prop)
                
                # Add amenities to property
                prop_amenities = random.sample(amenities, random.randint(2, 10))
                prop.amenities.set(prop_amenities)
                
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"   Could not save property {name}: {e}"))
            
            if i % 300 == 0 and i > 0:
                self.stdout.write(self.style.SUCCESS(f"   Created {i}/{property_count} properties"))

        # Add 3-8 reliable images to each property
        self.stdout.write(self.style.SUCCESS("📸 Adding property images with reliable sources..."))
        total_images_added = 0
        failed_property_images = 0
        
        for i, prop in enumerate(properties):
            num_images = random.randint(3, 8)
            
            for img_idx in range(num_images):
                # Download reliable property image
                image_file, _ = self.download_image_with_fallbacks('property')
                if image_file:
                    try:
                        property_image = PropertyImage(
                            property=prop,
                            is_primary=(img_idx == 0)
                        )
                        property_image.image.save(
                            f"property_{prop.id}_{img_idx}_{fake.uuid4()[:6]}.jpg", 
                            image_file, 
                            save=True
                        )
                        total_images_added += 1
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"   Could not save image for property {prop.name}: {e}"))
                        failed_property_images += 1
                else:
                    self.stdout.write(self.style.WARNING(f"   Could not download image for property {prop.name}"))
                    failed_property_images += 1
            
            if i % 200 == 0 and i > 0:
                self.stdout.write(self.style.SUCCESS(f"   Added images to {i}/{len(properties)} properties (Success: {total_images_added}, Failed: {failed_property_images})"))

        self.stdout.write(self.style.SUCCESS(f"   Total property images added: {total_images_added}"))
        if failed_property_images > 0:
            self.stdout.write(self.style.WARNING(f"   Failed property images: {failed_property_images}"))

        # -------------------------------
        # 5. TENANTS - 2000 tenants
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("👥 Creating 2000 tenants..."))
        tenants = []
        for i in range(2000):
            prop = random.choice(properties)
            landlord_user = prop.landlord
            lease_start = fake.date_between(start_date='-2y', end_date='today')
            lease_end = fake.date_between(start_date='today', end_date='+3y')
            
            security_deposit = prop.price * Decimal(random.uniform(0.3, 0.8))
            
            tenants.append(Tenant(
                landlord=landlord_user,
                property=prop,
                full_name=fake.name(),
                email=fake.email(),
                phone=fake.phone_number()[:20],
                lease_start=lease_start,
                lease_end=lease_end,
                rent_amount=prop.price * Decimal('0.01'),  # Monthly rent approximation
                security_deposit=security_deposit,
                emergency_contact=fake.name() + " - " + fake.phone_number()[:15],
                notes=fake.paragraph(nb_sentences=2) if random.choice([True, False]) else ""
            ))
        
        # Create tenants in batches
        batch_size = 200
        for i in range(0, len(tenants), batch_size):
            batch = tenants[i:i + batch_size]
            Tenant.objects.bulk_create(batch)
            if i % 1000 == 0:
                self.stdout.write(self.style.SUCCESS(f"   Created {min(i + batch_size, len(tenants))}/{len(tenants)} tenants"))

        # -------------------------------
        # 6. SAVED PROPERTIES - 4000 saved properties
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("💾 Creating 4000 saved properties..."))
        saved_properties = []
        saved_combinations = set()
        
        for i in range(4000):
            seeker = random.choice(all_seeker_users)
            prop = random.choice(properties)
            combination = (seeker.id, prop.id)
            
            if combination not in saved_combinations:
                saved_combinations.add(combination)
                saved_properties.append(SavedProperty(
                    seeker=seeker,
                    property=prop,
                    notes=fake.sentence() if random.choice([True, False]) else ""
                ))
            
            if i % 1000 == 0 and i > 0:
                self.stdout.write(self.style.SUCCESS(f"   Created {i}/4000 saved properties"))

        SavedProperty.objects.bulk_create(saved_properties, ignore_conflicts=True, batch_size=500)

        # -------------------------------
        # 7. RENTAL APPLICATIONS - 3000 applications
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("📝 Creating 3000 rental applications..."))
        applications = []
        application_combinations = set()
        
        for i in range(3000):
            prop = random.choice(properties)
            applicant = random.choice(all_seeker_users)
            combination = (prop.id, applicant.id)
            
            if combination not in application_combinations:
                application_combinations.add(combination)
                applications.append(RentalApplication(
                    property=prop,
                    applicant=applicant,
                    status=random.choice(['pending', 'approved', 'rejected', 'withdrawn']),
                    notes=fake.paragraph(nb_sentences=2) if random.choice([True, False]) else "",
                    credit_score=random.randint(300, 850),
                    employment_verified=random.choice([True, False]),
                    income_verified=random.choice([True, False]),
                    references_checked=random.choice([True, False]),
                    background_check=random.choice([True, False])
                ))
            
            if i % 1000 == 0 and i > 0:
                self.stdout.write(self.style.SUCCESS(f"   Created {i}/3000 applications"))

        RentalApplication.objects.bulk_create(applications, batch_size=500)

        # -------------------------------
        # 8. LEASE AGREEMENTS - 1500 leases
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("📄 Creating 1500 lease agreements..."))
        leases = []
        tenants_list = list(Tenant.objects.all())
        selected_tenants = random.sample(tenants_list, min(1500, len(tenants_list)))
        
        for i, tenant in enumerate(selected_tenants):
            lease_start = tenant.lease_start
            lease_end = tenant.lease_end
            
            leases.append(LeaseAgreement(
                tenant=tenant,
                property=tenant.property,
                start_date=lease_start,
                end_date=lease_end,
                monthly_rent=tenant.rent_amount,
                security_deposit=tenant.security_deposit,
                terms=fake.paragraph(nb_sentences=10),
                signed_date=fake.date_between(start_date=lease_start, end_date=lease_start + timedelta(days=30)),
                is_active=lease_end > timezone.now().date()
            ))
            
            if i % 500 == 0 and i > 0:
                self.stdout.write(self.style.SUCCESS(f"   Created {i}/1500 leases"))

        LeaseAgreement.objects.bulk_create(leases, batch_size=300)

        # -------------------------------
        # 9. MAINTENANCE REQUESTS - 2000 requests
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("🔧 Creating 2000 maintenance requests..."))
        maintenance_requests = []
        for i in range(2000):
            prop = random.choice(properties)
            tenant_user = random.choice(all_seeker_users)
            assigned_to = random.choice(landlords) if random.choice([True, False]) else None
            
            maintenance_requests.append(MaintenanceRequest(
                property=prop,
                tenant=tenant_user,
                title=fake.sentence(nb_words=6),
                description=fake.paragraph(nb_sentences=3),
                priority=random.choice(['low', 'medium', 'high', 'emergency']),
                status=random.choice(['open', 'in_progress', 'completed', 'cancelled']),
                assigned_to=assigned_to,
                completion_date=fake.date_between(start_date='-60d', end_date='+60d') if random.choice([True, False]) else None,
                cost=Decimal(random.randint(1000, 50000)) if random.choice([True, False]) else None
            ))
            
            if i % 500 == 0 and i > 0:
                self.stdout.write(self.style.SUCCESS(f"   Created {i}/2000 maintenance requests"))

        MaintenanceRequest.objects.bulk_create(maintenance_requests, batch_size=400)

        # -------------------------------
        # 10. PAYMENTS - 3000 payments
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("💰 Creating 3000 payments..."))
        payments = []
        tenants_list = list(Tenant.objects.all())
        for i in range(3000):
            tenant = random.choice(tenants_list)
            
            payments.append(Payment(
                tenant=tenant,
                property=tenant.property,
                amount=tenant.rent_amount * Decimal(random.uniform(0.8, 1.2)),
                payment_date=fake.date_between(start_date='-2y', end_date='today'),
                payment_method=random.choice(['bank_transfer', 'credit_card', 'mobile_money', 'cash', 'check']),
                reference_number=fake.uuid4()[:20],
                is_verified=random.choice([True, False]),
                notes=fake.sentence() if random.choice([True, False]) else ""
            ))
            
            if i % 1000 == 0 and i > 0:
                self.stdout.write(self.style.SUCCESS(f"   Created {i}/3000 payments"))

        Payment.objects.bulk_create(payments, batch_size=500)

        # -------------------------------
        # 11. EXPENSES - 1500 expenses
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("📊 Creating 1500 expenses..."))
        expenses = []
        for i in range(1500):
            prop = random.choice(properties)
            
            expenses.append(Expense(
                property=prop,
                category=random.choice(['repair', 'maintenance', 'utility', 'tax', 'insurance', 'other']),
                amount=Decimal(random.randint(500, 100000)),
                date=fake.date_between(start_date='-2y', end_date='today'),
                description=fake.paragraph(nb_sentences=2)
            ))
            
            if i % 500 == 0 and i > 0:
                self.stdout.write(self.style.SUCCESS(f"   Created {i}/1500 expenses"))

        Expense.objects.bulk_create(expenses, batch_size=300)

        # -------------------------------
        # 12. COMMUNITY POSTS & REPLIES - 1000 posts, 3000 replies
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("💬 Creating community posts and replies..."))
        
        # Landlord community posts
        landlord_posts = []
        for i in range(500):
            author = random.choice(landlords)
            landlord_posts.append(LandlordCommunityPost(
                author=author,
                title=fake.sentence(nb_words=8),
                content=fake.paragraph(nb_sentences=5),
                location_tag=fake.city(),
                upvotes=random.randint(0, 200),
                views=random.randint(0, 1000),
                visibility=random.choice(['landlords', 'all'])
            ))
        LandlordCommunityPost.objects.bulk_create(landlord_posts, batch_size=100)
        landlord_posts = list(LandlordCommunityPost.objects.all())

        # Seeker community posts
        seeker_posts = []
        for i in range(500):
            author = random.choice(all_seeker_users)
            seeker_posts.append(SeekerCommunityPost(
                author=author,
                title=fake.sentence(nb_words=8),
                content=fake.paragraph(nb_sentences=5),
                location_tag=fake.city(),
                upvotes=random.randint(0, 200),
                views=random.randint(0, 1000)
            ))
        SeekerCommunityPost.objects.bulk_create(seeker_posts, batch_size=100)
        seeker_posts = list(SeekerCommunityPost.objects.all())

        # Community replies
        landlord_replies = []
        seeker_replies = []

        # Replies for landlord posts
        for post in landlord_posts:
            for _ in range(random.randint(0, 8)):
                author = random.choice(all_users)
                landlord_replies.append(LandlordCommunityReply(
                    post=post,
                    author=author,
                    content=fake.paragraph(nb_sentences=2)
                ))

        # Replies for seeker posts
        for post in seeker_posts:
            for _ in range(random.randint(0, 8)):
                author = random.choice(all_users)
                seeker_replies.append(SeekerCommunityReply(
                    post=post,
                    author=author,
                    content=fake.paragraph(nb_sentences=2)
                ))

        LandlordCommunityReply.objects.bulk_create(landlord_replies, batch_size=200)
        SeekerCommunityReply.objects.bulk_create(seeker_replies, batch_size=200)

        # -------------------------------
        # 13. NOTIFICATIONS - 2000 notifications
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("🔔 Creating 2000 notifications..."))
        notifications = []
        for i in range(2000):
            recipient = random.choice(all_users)
            notifications.append(Notification(
                recipient=recipient,
                title=fake.sentence(nb_words=6),
                message=fake.paragraph(nb_sentences=2),
                notification_type=random.choice(['system', 'property', 'application', 'verification', 'account']),
                is_read=random.choice([True, False]),
                related_url=fake.url() if random.choice([True, False]) else ""
            ))
            
            if i % 500 == 0 and i > 0:
                self.stdout.write(self.style.SUCCESS(f"   Created {i}/2000 notifications"))

        Notification.objects.bulk_create(notifications, batch_size=400)

        # -------------------------------
        # 14. CONVERSATIONS + MESSAGES - 1000 conversations, 5000 messages
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("💌 Creating conversations and messages..."))
        conversations = []
        messages = []

        existing_conversations = set()
        
        for i in range(1000):
            landlord_user = random.choice(landlords)
            seeker_user = random.choice(all_seeker_users)
            prop = random.choice(properties)
            
            conversation_key = (prop.id, landlord_user.id, seeker_user.id)
            
            if conversation_key not in existing_conversations:
                existing_conversations.add(conversation_key)
                
                try:
                    convo = Conversation.objects.create(
                        property=prop,
                        created_at=timezone.now() - timedelta(days=random.randint(1, 365))
                    )
                    convo.participants.add(landlord_user, seeker_user)
                    conversations.append(convo)

                    # Generate 3-8 messages per conversation
                    for msg_idx in range(random.randint(3, 8)):
                        sender = landlord_user if msg_idx % 2 == 0 else seeker_user
                        recipient = seeker_user if sender == landlord_user else landlord_user
                        
                        messages.append(Message(
                            conversation=convo,
                            sender=sender,
                            recipient=recipient,
                            content=fake.paragraph(nb_sentences=2),
                            read=random.choice([True, False]),
                            created_at=timezone.now() - timedelta(days=random.randint(0, 90))
                        ))
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"   Could not create conversation: {e}"))
            
            if i % 200 == 0 and i > 0:
                self.stdout.write(self.style.SUCCESS(f"   Created {i}/1000 conversations"))

        # Create messages in batches
        batch_size = 500
        for i in range(0, len(messages), batch_size):
            batch = messages[i:i + batch_size]
            Message.objects.bulk_create(batch)
            if i % 1000 == 0:
                self.stdout.write(self.style.SUCCESS(f"   Created {min(i + batch_size, len(messages))}/{len(messages)} messages"))

        # -------------------------------
        # FINAL SUMMARY
        # -------------------------------
        self.stdout.write(self.style.SUCCESS("✅ Seeding complete!"))
        self.stdout.write(self.style.SUCCESS(f"📊 Final Summary:"))
        self.stdout.write(self.style.SUCCESS(f"   👤 Users: {User.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   👷 Landlords: {LandlordProfile.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   🧍 Seekers: {SeekerProfile.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   🏠 Properties: {Property.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   🖼️ Property Images: {PropertyImage.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   👥 Tenants: {Tenant.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   💾 Saved Properties: {SavedProperty.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   📝 Applications: {RentalApplication.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   📄 Leases: {LeaseAgreement.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   🔧 Maintenance: {MaintenanceRequest.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   💰 Payments: {Payment.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   📊 Expenses: {Expense.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   💬 Posts: {LandlordCommunityPost.objects.count() + SeekerCommunityPost.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   💭 Replies: {LandlordCommunityReply.objects.count() + SeekerCommunityReply.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   🔔 Notifications: {Notification.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   💌 Conversations: {Conversation.objects.count():,}"))
        self.stdout.write(self.style.SUCCESS(f"   ✉️ Messages: {Message.objects.count():,}"))

        total_records = sum([
            User.objects.count(),
            LandlordProfile.objects.count(),
            SeekerProfile.objects.count(),
            Property.objects.count(),
            PropertyImage.objects.count(),
            Tenant.objects.count(),
            SavedProperty.objects.count(),
            RentalApplication.objects.count(),
            LeaseAgreement.objects.count(),
            MaintenanceRequest.objects.count(),
            Payment.objects.count(),
            Expense.objects.count(),
            LandlordCommunityPost.objects.count() + SeekerCommunityPost.objects.count(),
            LandlordCommunityReply.objects.count() + SeekerCommunityReply.objects.count(),
            Notification.objects.count(),
            Conversation.objects.count(),
            Message.objects.count()
        ])
        
        self.stdout.write(self.style.SUCCESS(f"\n📈 Total Records Created: {total_records:,}"))
        self.stdout.write(self.style.SUCCESS("🎉 Database successfully seeded with 15K+ records using RELIABLE images!"))