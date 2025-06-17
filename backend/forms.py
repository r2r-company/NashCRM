from django import forms
from django.utils.timezone import now


class LeadsReportForm(forms.Form):
    date_from = forms.DateField(label="Від", initial=now().date())
    date_to = forms.DateField(label="До", initial=now().date())
