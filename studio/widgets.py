from django.forms import CheckboxSelectMultiple, RadioSelect
from django.templatetags.static import static

from .languages import flag_code


class FlagOptions:
    option_template_name = 'studio/widgets/language_option.html'

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        option['attrs']['class'] = 'language-option__input'
        country = flag_code(str(value))
        option['flag_url'] = static(f'studio/flags/{country}.svg') if country else None
        return option


class LanguageButtons(FlagOptions, CheckboxSelectMultiple):
    pass


class SourceLanguageButtons(FlagOptions, RadioSelect):
    pass
