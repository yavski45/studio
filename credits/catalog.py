from decimal import Decimal

# Achats ponctuels : aucun prélèvement récurrent ni abonnement.
PACKS = {
    'starter': {'name': 'Starter', 'quantity': 11, 'usd': Decimal('10.00')},
    'creator': {'name': 'Creator', 'quantity': 28, 'usd': Decimal('25.00')},
    'pro': {'name': 'Pro', 'quantity': 57, 'usd': Decimal('50.00')},
    'business': {'name': 'Business', 'quantity': 175, 'usd': Decimal('150.00')},
    'studio': {'name': 'Studio', 'quantity': 360, 'usd': Decimal('300.00')},
}
