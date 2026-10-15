# Déploiement de Dublao

## État de préparation

L'hébergeur et le domaine public restent à choisir. Aucun service public n'a
été créé et aucun secret local n'a été modifié.

Le Dockerfile contient Python, Gunicorn et FFmpeg et démarre Django par défaut.
Le fichier compose.yaml lance PostgreSQL, Redis, la préparation des migrations
et fichiers statiques, Django, Nginx, le worker et Beat. Il utilise une base
Docker séparée et persistante. L'accès HTTP est limité à localhost ; HTTPS et
la configuration publique du VPS restent à préparer.

## Services à mettre en place

- Serveur web : Gunicorn avec `dublao.wsgi:application`, derrière HTTPS.
- PostgreSQL avec stockage persistant et sauvegardes restaurables.
- Redis privé pour la file Celery, avec persistance.
- Worker Celery avec FFmpeg, accès à PostgreSQL, Redis, R2 et Murf.
- Une seule instance Celery Beat pour les reprises et vérifications périodiques.
- Service des fichiers statiques issus de `collectstatic`, y compris la démo.
- Bucket R2 privé pour les fichiers utilisateurs, conservant les contrôles
  d'accès de Django.

La concurrence des workers et les délais du serveur web devront tenir compte
des ressources de l'hébergement et des imports de vidéos volumineuses.

## Configuration publique

- `DEBUG=false`, clé Django de production et `ALLOWED_HOSTS` explicites.
- `CSRF_TRUSTED_ORIGINS` avec le domaine HTTPS.
- Redirection HTTPS et reconnaissance du proxy selon l'hébergeur. Ne faire
  confiance à un en-tête de proxy que si celui-ci le remplace et protège
  l'accès direct au serveur Django.
- SMTP réel (`EMAIL_DELIVERY=smtp`), avec test de confirmation et de
  réinitialisation du mot de passe.
- `PAYMENT_PUBLIC_URL=https://<domaine>` et environnement Genius Pay live
  après validation du parcours de test.
- Callback Google : `https://<domaine>/comptes/google/login/callback/`.
- Webhook Genius Pay : `https://<domaine>/credits/webhook/geniuspay/`.
- Retour Genius Pay : `https://<domaine>/credits/callback/` ; les achats
  disposent également de leur route de retour individuelle.

Le retour du navigateur ne suffit pas à créditer un portefeuille. Conserver
la confirmation serveur, la validation du paiement et l'idempotence existantes.
Les secrets sont à saisir dans la configuration protégée de l'hébergement,
sans les publier ni les ajouter au dépôt ou à une image Docker.

## Ordre de mise en service

1. Préparer l'hébergement, le domaine HTTPS, les services et les secrets.
2. Sauvegarder la base existante ; décider si ses utilisateurs et achats doivent
   être transférés. Ne pas lancer de migration destructive sur la base locale.
3. Construire l'image et exécuter `check --deploy` avec la configuration réelle
   de production, puis `migrate` et `collectstatic --noinput`.
4. Démarrer le serveur web, les workers et une seule instance Beat.
5. Vérifier l'accueil, les statiques, Google, les emails, les imports et la
   lecture privée des vidéos avec un compte de test.
6. Tester le paiement, le webhook signé et la répétition d'une notification :
   le portefeuille doit recevoir les crédits une seule fois. Prévoir un essai
   live autorisé avant de déclarer le parcours réel validé.
7. Activer la surveillance des erreurs, de la file Celery, des sauvegardes et
   des crédits Murf ; conserver la procédure de retour à la version précédente.

## Références

- https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/
- https://docs.celeryq.dev/en/stable/userguide/periodic-tasks.html
