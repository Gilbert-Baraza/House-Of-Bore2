# crm/urls.py
from django.urls import path
from .views import (
    CRMDashboardView,
    CustomerDetailView,
    CustomerExportView,
    CustomerInteractionLogView,
    CustomerListView,
    CustomerSegmentsView,
    CustomerStaffNoteCreateView,
    CustomerTimelineView,
)

app_name = "crm"

urlpatterns = [
    # CRM Landing Dashboard
    path("", CRMDashboardView.as_view(), name="dashboard"),
    
    # Customer Directory & Segmentation
    path("directory/", CustomerListView.as_view(), name="customer_list"),
    path("segments/", CustomerSegmentsView.as_view(), name="customer_segments"),
    
    # 360° Customer Profile & Inspection
    path("<int:pk>/", CustomerDetailView.as_view(), name="customer_detail"),
    path("<int:pk>/timeline/", CustomerTimelineView.as_view(), name="customer_timeline"),
    
    # Administrative Actions & Mutations
    path("<int:pk>/notes/add/", CustomerStaffNoteCreateView.as_view(), name="staff_note_add"),
    path("<int:pk>/interactions/add/", CustomerInteractionLogView.as_view(), name="interaction_add"),
    path("<int:pk>/export/", CustomerExportView.as_view(), name="customer_export"),
]
