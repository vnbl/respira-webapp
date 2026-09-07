from django import forms

from .models import Institution, InstitutionAlertRule, PushBroadcast, Stations


class InstitutionAlertRuleForm(forms.ModelForm):
    """Offers only the sensor that belongs to the chosen institution.

    ``InstitutionContract.station`` is a ``OneToOneField``, so an institution
    has exactly one sensor under contract. A picker listing every station on
    the platform therefore offers one right answer and many wrong ones, and
    each wrong one configures an institution's wording onto somebody else's
    sensor — visible only when the wrong followers receive it.

    The narrowing happens in two places, because they cover different moments:

    * ``__init__`` narrows the queryset to whatever institution the form
      already knows about — the one being edited, or the one just posted. This
      is what the browser renders, and what a posted value is validated
      against, so a station outside it is rejected by the field itself.
    * ``clean`` fills the field in when it was left blank, since there is only
      ever one valid choice and making the operator select it adds nothing.

    A JavaScript companion (``institution_alert_rule.js``) repopulates the
    select as soon as the institution changes, so the narrowing is visible
    before saving rather than only enforced on submit. It is a convenience:
    with scripting off, the server-side rules above still hold.
    """

    class Meta:
        model = InstitutionAlertRule
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        institution = self._known_institution()
        if institution is None:
            # No institution chosen yet: an empty list says "pick one first"
            # rather than inviting a choice that would have to be rejected.
            self.fields["station"].queryset = Stations.objects.none()
        else:
            self.fields["station"].queryset = Stations.objects.filter(
                institution_contract__institution=institution
            )
        self.fields["station"].required = False
        self.fields[
            "station"
        ].help_text = "The sensor under contract to the selected institution."

    def _known_institution(self):
        """The institution this form is about, from the POST or the instance.

        Reads the raw posted value rather than ``cleaned_data``: ``__init__``
        runs before validation, and the queryset it sets is what that
        validation then checks the posted station against.
        """
        if self.data:
            raw = self.data.get(self.add_prefix("institution"))
            if raw:
                return Institution.objects.filter(pk=raw).first()
        return getattr(self.instance, "institution", None)

    def clean(self):
        cleaned = super().clean()
        institution = cleaned.get("institution")
        if institution is None:
            # Already reported as a required-field error; a second message
            # about the station it would have resolved is just noise.
            return cleaned

        contract = getattr(institution, "contract", None)
        if contract is None or contract.station_id is None:
            raise forms.ValidationError(
                {
                    "institution": (
                        "This institution has no sensor under contract, so "
                        "there is nothing to alert about. Add an institution "
                        "contract first."
                    )
                }
            )

        # Blank is the ordinary case with scripting off, and the only valid
        # answer is the contracted sensor either way.
        if cleaned.get("station") is None:
            cleaned["station"] = contract.station
            self.instance.station = contract.station
        return cleaned


class PushBroadcastForm(forms.Form):
    """The manual notification an operator composes on the confirmation page.

    A plain ``Form``, not a ``ModelForm``: the ``PushBroadcast`` row is the
    record that a send was *attempted*, so it is created at send time rather
    than existing as an editable draft that could be submitted twice.

    ``scope`` decides which of ``institution`` / ``station`` is required, which
    is checked here rather than shown — Django admin cannot hide one field
    based on another without JavaScript, so the constraint is enforced instead
    of presented.
    """

    scope = forms.ChoiceField(
        choices=PushBroadcast.SCOPE_CHOICES,
        label="Send to",
        help_text="Who receives this notification.",
    )
    institution = forms.ModelChoiceField(
        queryset=Institution.objects.order_by("legal_name"),
        required=False,
        help_text="Required when sending to all of an institution's stations.",
    )
    station = forms.ModelChoiceField(
        queryset=Stations.objects.order_by("name"),
        required=False,
        help_text="Required when sending to a single station's followers.",
    )
    push_title = forms.CharField(
        max_length=100,
        label="Title",
        help_text="Shown in bold on the device.",
    )
    push_body = forms.CharField(
        max_length=500,
        label="Message",
        widget=forms.Textarea(attrs={"rows": 4, "cols": 60}),
        help_text="The notification body. Plain text — no {station} substitution here.",
    )

    def clean(self):
        cleaned = super().clean()
        scope = cleaned.get("scope")

        if scope == PushBroadcast.SCOPE_STATION and not cleaned.get("station"):
            raise forms.ValidationError(
                {"station": "Choose the station whose followers should be notified."}
            )
        if scope == PushBroadcast.SCOPE_INSTITUTION and not cleaned.get("institution"):
            raise forms.ValidationError(
                {"institution": "Choose the institution whose followers to notify."}
            )
        if scope == PushBroadcast.SCOPE_ALL:
            # Cleared rather than rejected: a selection left over from switching
            # scope must not quietly narrow a send meant for the whole platform.
            cleaned["institution"] = None
            cleaned["station"] = None
        return cleaned


class StationStatusOverrideForm(forms.Form):
    """Reason captured on the activate/deactivate confirmation page.

    The note is what tells the next operator *why* a station was turned off, so
    it is required here even though ``StationOverride.note`` stays optional at
    the model level — an override can also be created by hand for other fields.
    """

    note = forms.CharField(
        label="Reason",
        widget=forms.Textarea(attrs={"rows": 4, "cols": 60}),
        help_text="Why this station is being activated or deactivated.",
        strip=True,
    )
