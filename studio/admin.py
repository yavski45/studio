from django.contrib import admin

from .models import DubbingJob, DubbingLanguage, DubbingOutput


class OutputInline(admin.TabularInline):
    model = DubbingOutput
    extra = 0
    readonly_fields = ['locale', 'video', 'subtitles', 'error_message']
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(DubbingJob)
class DubbingJobAdmin(admin.ModelAdmin):
    list_display = ['title', 'user', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['title', 'user__email', 'murf_job_id']
    readonly_fields = [field.name for field in DubbingJob._meta.fields]
    inlines = [OutputInline]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(DubbingLanguage)
