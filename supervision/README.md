# Tableau de bord administrateur

Adresse : `/administration/`. Accès réservé aux comptes Django actifs ayant
`is_staff=True`. Un lien apparaît dans leur espace et dans le studio.
Les comptes ordinaires reçoivent HTTP 403 et les visiteurs doivent se connecter.

## Recettes

Seuls les achats live ayant une date de confirmation `paid_at` sont comptés.
Les recettes USD correspondent au prix des packs. Les achats sandbox et les
tentatives non confirmées sont exclus. Les remboursements sont déduits à leur
date de confirmation, même si l'achat est antérieur à la période affichée.
Les frais de paiement, Murf et les autres dépenses ne sont pas déduits :
il s'agit de recettes, pas d'un calcul de bénéfices.

La conversion USD vers FCFA utilise le taux saisi dans le filtre, sans taux
automatique ni arrondi modifiant les transactions. Le montant réellement
réglé et sa devise sont affichés séparément pour chaque achat.

## Visiteurs

Le suivi commence avec les nouvelles visites après la migration. Un cookie
signé contenant un UUID aléatoire identifie un navigateur pendant un an.
La table conserve un hash, un jour et un compteur de pages vues, sans IP,
email, URL ni agent utilisateur. Le nombre de visiteurs de la période est
le nombre de hashes distincts, et non la somme des visiteurs quotidiens.
Changer de navigateur ou effacer le cookie crée un nouvel identifiant.

Seuls les GET HTML répondant HTTP 200 sont comptés. Les pages administrateur,
les comptes staff, les assets, les callbacks de paiement, les requêtes HTMX et
les robots identifiables sont exclus. Une erreur de collecte ne bloque pas le site.

## Alertes Murf Dub

L'administration affiche le dernier `credits_remaining` communiqué par l'API
Murf Dub, un avertissement à 20 crédits ou moins et une alerte à zéro crédit.
La date de vérification reste visible. Un solde inconnu n'est jamais remplacé
par zéro, et une panne conserve la dernière valeur connue avec un avertissement.
Ce solde concerne le compte fournisseur Murf, indépendamment des crédits Dublao.

Les suivis normaux des doublages actualisent le solde. Celery Beat consulte aussi
le statut du dernier job toutes les cinq minutes. Le bouton « Vérifier le solde »
demande la même opération en arrière-plan, et HTMX actualise l'alerte chaque minute.
Sans job existant ou si son statut n'est plus disponible, le solde doit être vérifié
sur le compte Murf. Les réponses anciennes ne remplacent pas une observation plus
récente et un changement de clé masque le solde de l'ancien compte.
Cette fonctionnalité ne crée aucun doublage, n'achète aucun crédit et n'envoie aucun email.

Référence : https://murf.ai/api/docs/api-reference/dubbing/jobs/get-status

## Validation des tests

`python manage.py test supervision --settings=dublao.test_settings`

L'aperçu `preview/render_administration.py` utilise exclusivement une base en
mémoire et des données fictives. Il n'ouvre aucun accès administrateur réel.
