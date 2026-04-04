from django.urls import path

from . import views


urlpatterns = [
    path("proposals/partial/", views.proposals_partial, name="proposals_partial"),
    path("proposals/cbr-eur-rate/", views.proposal_cbr_eur_rate, name="proposal_cbr_eur_rate"),
    path("proposals/create/", views.proposal_form_create, name="proposal_form_create"),
    path("proposals/<int:pk>/edit/", views.proposal_form_edit, name="proposal_form_edit"),
    path("proposals/<int:pk>/dispatch/edit/", views.proposal_dispatch_form_edit, name="proposal_dispatch_form_edit"),
    path("proposals/<int:pk>/dispatch/docx/download/", views.proposal_generated_docx_download, name="proposal_generated_docx_download"),
    path("proposals/dispatch/send/", views.proposal_dispatch_send, name="proposal_dispatch_send"),
    path("proposals/dispatch/create-documents/", views.proposal_dispatch_create_documents, name="proposal_dispatch_create_documents"),
    path("proposals/templates/create/", views.proposal_template_form_create, name="proposal_template_form_create"),
    path("proposals/templates/<int:pk>/edit/", views.proposal_template_form_edit, name="proposal_template_form_edit"),
    path("proposals/templates/<int:pk>/delete/", views.proposal_template_delete, name="proposal_template_delete"),
    path("proposals/templates/<int:pk>/move-up/", views.proposal_template_move_up, name="proposal_template_move_up"),
    path("proposals/templates/<int:pk>/move-down/", views.proposal_template_move_down, name="proposal_template_move_down"),
    path("proposals/templates/<int:pk>/download/", views.proposal_template_download, name="proposal_template_download"),
    path("proposals/variables/create/", views.proposal_variable_form_create, name="proposal_variable_form_create"),
    path("proposals/variables/<int:pk>/edit/", views.proposal_variable_form_edit, name="proposal_variable_form_edit"),
    path("proposals/variables/<int:pk>/delete/", views.proposal_variable_delete, name="proposal_variable_delete"),
    path("proposals/variables/<int:pk>/move-up/", views.proposal_variable_move_up, name="proposal_variable_move_up"),
    path("proposals/variables/<int:pk>/move-down/", views.proposal_variable_move_down, name="proposal_variable_move_down"),
    path("proposals/<int:pk>/delete/", views.proposal_delete, name="proposal_delete"),
    path("proposals/<int:pk>/move-up/", views.proposal_move_up, name="proposal_move_up"),
    path("proposals/<int:pk>/move-down/", views.proposal_move_down, name="proposal_move_down"),
]
