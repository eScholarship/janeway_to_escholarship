from django import forms

class EscholAdminForm(forms.Form):
    eschol_url = forms.CharField(required=False)
