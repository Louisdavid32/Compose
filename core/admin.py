from django.contrib import admin
from .models.user import User
from .models.establishment import Establishment


admin.site.site_header = "Plateforme d'évaluation"
admin.site.site_title = "Administration de la plateforme"
admin.site.index_title = "Bienvenue dans l'administration de la plateforme d'évaluation"

admin.site.register(User)
admin.site.register(Establishment)

