from django.contrib import admin
from django.db import models
from django.forms import widgets

from .models import BallPromptMessage


@admin.register(BallPromptMessage)
class BallPromptMessageAdmin(admin.ModelAdmin):
    search_help_text = """{user} will mention the user.
{collectible} is the collectible name.
{collectibles} is the plural collectible name.
{ball} is the spawned collectible's name
{emoji} is the collectible's emoji.
{wrong} is what the user put for a wrong message"""

    formfield_overrides = {models.TextField: {"widget": widgets.Textarea({"rows": 2, "cols": 60})}}

    list_display = ("ball", "category", "message", "rarity")
    list_editable = ("ball", "category", "message", "rarity")

    list_filter = ("category",)
    exclude = ("id",)

    # otherwise, category is link
    list_display_links = None

    search_fields = ("message",)

    list_per_page = 100
