from decimal import InvalidOperation

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from credits.services import grant_credits


class Command(BaseCommand):
    help = 'Ajout manuel audité de crédits. Une même référence ne crédite jamais deux fois.'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', required=True, type=int)
        parser.add_argument('--credits', required=True)
        parser.add_argument('--reference', required=True)
        parser.add_argument('--reason', required=True)

    def handle(self, *args, **options):
        reference = options['reference'].strip()
        if not reference or len(reference) > 180 or not options['reason'].strip():
            raise CommandError('Référence ou motif invalide.')
        try:
            user = get_user_model().objects.get(pk=options['user_id'])
            entry = grant_credits(user, options['credits'], 'grant:' + reference, options['reason'])
        except get_user_model().DoesNotExist:
            raise CommandError('Utilisateur introuvable.') from None
        except (ValueError, InvalidOperation):
            raise CommandError('Montant invalide ou référence déjà utilisée.') from None
        self.stdout.write(self.style.SUCCESS(f'Écriture {entry.pk} enregistrée.'))
