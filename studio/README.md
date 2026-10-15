# Studio de doublage Dublao

Flux exclusivement `job_id`, via le SDK officiel `MurfDub` :
`jobs.create` → `jobs.get_status` → copie des résultats et SRT dans R2.
Aucun appel à `projects.create` ou `create_with_project_id`.

## Démarrer depuis PowerShell

Le fichier Compose lance désormais toute l'application avec une base Docker
séparée : voir [DOCKER.md](../DOCKER.md). Les commandes ci-dessous décrivent
l'ancien montage avec Django et PostgreSQL sur Windows.

1. Renseigner dans `.env` la clé **Murf Dub** (distincte de Falcon/TTS) sous
   `MURFDUB_API_KEY`, avec `MURFDUB_ENABLED=true`.
2. Installer les dépendances : `env\Scripts\python.exe -m pip install -r requirements.txt`.
3. Appliquer les migrations : `env\Scripts\python.exe manage.py migrate`.
4. Actualiser les langues du compte : `env\Scripts\python.exe manage.py sync_murf_languages`.
   Cette commande ne crée aucun doublage. La migration fournit une première
   sélection de langues documentées ; l’API reste la référence.
5. Pour le nouveau montage complet, suivre le guide Docker ci-dessus.
   Redis écoute uniquement sur localhost. Worker et Beat tournent sous Linux.
6. Garder Django dans l’environnement habituel : `env\Scripts\python.exe manage.py runserver`.
7. Ouvrir `/studio/` avec un compte dont l’email est vérifié, importer une vidéo
   de test et lancer explicitement son doublage. Cet appel consomme les crédits Murf.

Dans le nouveau montage Compose, PostgreSQL est le service `postgres` ; la
base Windows n'est pas transférée automatiquement. Ne pas ouvrir Redis sur Internet.

Pour un essai local Windows seulement : `docker compose up -d redis`, puis dans
deux terminaux `env\Scripts\celery.exe -A dublao worker --pool=solo --loglevel=INFO`
et `env\Scripts\celery.exe -A dublao beat --loglevel=INFO`. Celery ne prend pas
officiellement en charge Windows : utiliser Linux/Docker en production.

## Paramètres

- `CELERY_BROKER_URL=redis://127.0.0.1:6379/0` pour Django sur l’hôte.
- `STUDIO_MAX_UPLOAD_BYTES=0` : aucune limite de taille applicative à l'import,
  sous réserve des limites du serveur et de Murf. Une valeur positive permet
  de rétablir un plafond en octets. La copie des résultats n'a pas de plafond
  de taille ; les délais de téléchargement et d'exécution restent applicables.
- `STUDIO_MAX_ACTIVE_JOBS=3` par compte.
- `STUDIO_DOWNLOAD_HOSTS` : liste d’hôtes HTTPS autorisés pour les sorties Murf.
  Par défaut Murf, AWS et Google Cloud Storage. Si Murf utilise un autre CDN,
  ajouter uniquement son domaine vérifié. Les IP privées et redirections
  vers un domaine non autorisé sont refusées.

Les fichiers sont importés par Django vers R2 avant la mise en file d’attente.
Murf reçoit un lien signé privé de la source, valable une heure, produit au
moment de l’envoi. Les gros imports nécessitent des délais et des limites HTTP
adaptés sur l’hébergement ; ce premier flux n’est pas un import direct navigateur/R2.
Murf peut également limiter la durée et la résolution selon l’offre utilisée.

## Fiabilité et confidentialité

- PostgreSQL conserve le statut ; Redis transporte uniquement l’UUID local.
- La soumission est déclenchée après validation de la transaction.
- Un identifiant de formulaire et un verrou de compte empêchent les doubles clics.
- Beat reprend les travaux restés en attente lors d’une panne de Redis et contrôle
  les résultats toutes les 30 secondes (recul progressif lors d’erreurs).
- Les workers prennent un bail ; deux livraisons ne soumettent pas le même travail.
- Un timeout à la création est ambigu : passage en `review`, sans POST automatique
  supplémentaire. Il faut vérifier chez Murf avant toute nouvelle soumission.
- Si le worker meurt entre la création chez Murf et la sauvegarde du `job_id`,
  il faut réconcilier manuellement ce travail ; l’API ne documente pas de clé
  d’idempotence. La reprise proposée dans l’interface effectue seulement des GET
  lorsque le `job_id` est déjà connu.
- Les liens Murf expirent après 72 heures. Les sorties sont copiées dès réception
  dans R2 ; une récupération interrompue est réessayée sans nouveau doublage.
- Après 48 heures ou des échecs répétés, vérification manuelle. Aucun remboursement
  ni débit utilisateur n’est implémenté à ce stade.
- Téléchargements réservés au propriétaire avec email vérifié, liens R2 de 5 minutes,
  pas de cache des pages privées et pas de clé/URL signée dans les logs applicatifs.
- Les échecs par langue sont conservés, les fichiers déjà récupérés restent accessibles.
- L’import accepte les signatures des conteneurs vidéo. Le fournisseur valide
  ensuite les codecs et la présence de paroles ; aucune validation complète par FFmpeg ici.

Les crédits du fournisseur (`provider_credits_used`) sont enregistrés pour le
rapprochement ultérieur. Ils ne constituent pas le portefeuille du client.
Les paiements, la tarification, les réservations et les remboursements de crédits
utilisateur feront l’objet de l’étape suivante.

## Vérification

`env\Scripts\python.exe manage.py test studio --settings=dublao.test_settings`

Les tests utilisent SQLite, un stockage mémoire et un fournisseur simulé, sans
consommer de crédits ni envoyer de vidéo réelle. Pour vérifier l’exploitation,
`docker compose ps`, `docker compose logs --tail=50 worker beat`, puis un doublage
explicitement lancé avec une courte vidéo. Ne pas publier la sortie des variables
de configuration ni `docker compose config` (contient les secrets de `.env`).

Sources : [Murf Dub](https://murf.ai/api/docs/capabilities/dubbing),
[Celery Django](https://docs.celeryq.dev/en/stable/django/first-steps-with-django.html),
[R2 URLs signées](https://developers.cloudflare.com/r2/api/s3/presigned-urls/).
