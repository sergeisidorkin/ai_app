from django import forms

class TextForm(forms.Form):
    content = forms.CharField(
        label="Текст",
        widget=forms.Textarea(attrs={"rows": 8, "class": "form-control"}),
        required=True,
    )
