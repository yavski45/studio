# Page Crédits

Surface Operate : connaître son solde, choisir un pack ponctuel et poursuivre sur Genius Pay. Les règles, prix et quantités viennent du catalogue et du portefeuille Django.

## Direction contract

THESIS : une liste compacte de packs et un paiement à côté, choix confirmé par le propriétaire le 10 octobre 2026. Le solde reste un repère fonctionnel, sans dominer l’achat.

OWN-WORLD : palette sombre et verte Dublao, Manrope et DM Sans existants ; liste à séparateurs fins, sélection verte explicitement marquée « Choisi », récapitulatif menthe avec texte vert profond.

STORY : consulter les crédits disponibles et réservés, comparer quantité et coût unitaire, sélectionner un pack, vérifier le total, continuer sur Genius Pay. Les historiques restent séparés.

FIRST VIEWPORT : titre et accès Studio, bandeau de solde compact, puis liste à gauche et total avec bouton de paiement à droite. Sur mobile, le total suit immédiatement les cinq packs.

FORM : extension de la surface existante, construite directement en code selon le choix enregistré. Aucun nouveau monde visuel ni tirage de concept ; prix et mécanisme de paiement conservés.

FINISH : vérifier le rendu Django, le pack présélectionné, les états de paiement indisponible et de portefeuille gelé, puis le rendu ordinateur et mobile si une session authentifiée est accessible. Les protections du paiement ne changent pas.

## Vérification de cette version

Le rendu Django des cinq packs, leurs totaux présélectionnés, le blocage de l’achat pour un portefeuille gelé et l’indisponibilité du paiement sont vérifiés dans une base de test isolée. Les contrastes du récapitulatif sont supérieurs à 4,5:1, y compris pour les erreurs et le bouton. Les composants et polices restent ceux de Dublao ; aucune modification du système visuel global.

Le navigateur intégré redirige actuellement vers la connexion. Le rendu visuel authentifié sur ordinateur et mobile reste à vérifier ; les contrôles de template ne remplacent pas cette inspection.
