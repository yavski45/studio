# Dublao

SaaS de doublage vidéo en cours de construction avec Django, PostgreSQL,
HTMX et Alpine.js. Stockage privé Cloudflare R2 et doublage Murf Dub via
`POST /v1/murfdub/jobs/create`, avec suivi par `job_id`, sans `project_id`.

## Configuration locale

L'interface est disponible en français et en anglais. Voir [I18N.md](I18N.md)
pour le choix de langue et la maintenance des traductions.
Le référencement est préparé dans [SEO.md](SEO.md), avec une activation après
configuration du domaine HTTPS définitif.

Pour lancer Django, PostgreSQL, Redis et Celery ensemble, suivre
[le guide Docker](DOCKER.md). La procédure ci-dessous concerne l'environnement
Python et PostgreSQL installés directement sur le poste.

Depuis PowerShell, à la racine du projet :

```powershell
.\env\Scripts\python.exe -m pip install -r requirements.txt
```

Le fichier `.env` existe déjà. Conserver sa `SECRET_KEY` et ajouter les
variables de `.env.example` qui manquent, avec leurs valeurs réelles.
Ne pas publier `.env` et ne pas copier les valeurs d'exemple sur les secrets
existants. Les variables d'environnement du système sont prioritaires.

### PostgreSQL

Créer une base `dublao` et un utilisateur propriétaire de cette base via
pgAdmin ou votre outil PostgreSQL habituel. Reporter les identifiants dans
`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST` et
`POSTGRES_PORT`. Adapter les noms si une base existe déjà.

L'application utilise PostgreSQL, sans retour automatique vers SQLite.
L'ancien fichier `db.sqlite3` est conservé. Aucun transfert de données n'est
effectué par cette configuration.

### Cloudflare R2

1. Créer un bucket privé et désactiver tout accès public (`r2.dev` ou domaine
   public associé).
2. Créer un jeton R2 avec permission **Object Read & Write**, limité à ce
   bucket, puis récupérer **Access Key ID** et **Secret Access Key** S3.
3. Renseigner les variables `R2_*` dans `.env`. Ce sont des identifiants S3,
   pas un jeton Bearer de l'API de gestion Cloudflare.

Les futurs `FileField` utiliseront R2 via le stockage Django par défaut.
Les URLs générées sont signées et valables une heure. L'application devra
vérifier le propriétaire du fichier avant de générer un lien de téléchargement.
Les fichiers statiques restent séparés du stockage privé des vidéos.

### Emails de réinitialisation

Le parcours « Mot de passe oublié ? » utilise django-allauth. Les emails disposent d'une version HTML et texte en français, avec le sujet Dublao. L'envoi reste en mode console par défaut. Pour envoyer réellement depuis ton adresse, configure SMTP dans `.env` suivant [le guide email](EMAIL_CONFIGURATION.md), puis redémarre Django.

Les emails d'inscription, de confirmation et de réinitialisation partagent le design Dublao. La confirmation se fait depuis le lien reçu par email.

### Vérification et démarrage

```powershell
.\env\Scripts\python.exe manage.py check
.\env\Scripts\python.exe manage.py migrate
.\env\Scripts\python.exe manage.py createsuperuser
.\env\Scripts\python.exe manage.py runserver
```

`check` valide la configuration Django mais ne prouve pas l'accès à PostgreSQL
ou R2. `migrate` nécessite une base PostgreSQL accessible. Le stockage R2 refuse
son initialisation si ses identifiants sont absents, sans utiliser de fichier
local ou d'identifiants AWS implicites.

## État de l'implémentation

La configuration PostgreSQL/R2 est préparée. La landing page française est
disponible à la racine `/`, avec une mise en page responsive, un menu mobile,
une FAQ et un aperçu illustratif avec sélection de langue. Ses fichiers sont
dans `landing/templates/landing/` et `landing/static/landing/`. L'authentification email via django-allauth est disponible dans `/comptes/signup/` et `/comptes/login/`, avec confirmation du mot de passe, erreurs HTMX, affichage du mot de passe Alpine et espace protégé. Tailwind CSS, HTMX et Alpine.js sont chargés par CDN.

La connexion Google nécessite les deux variables `GOOGLE_OAUTH_CLIENT_ID` et `GOOGLE_OAUTH_CLIENT_SECRET`. Suivre [le guide Google OAuth](GOOGLE_OAUTH.md). La vérification email est obligatoire avant l'accès à l'espace. Les emails sont affichés dans le terminal en mode console, ou envoyés avec SMTP si ce mode est configuré.

La page d'inscription ouvre une popup avec le formulaire à gauche et l'image
`comptes/static/comptes/images/signup-scene.jpg` à droite. Sur mobile, l'image
passe sous le formulaire. La croix, Échap ou un clic sur le fond ferment la
popup et reviennent à l'accueil. Le formulaire et ses erreurs utilisent HTMX.
La page de connexion reprend la même popup, avec l'image
`comptes/static/comptes/images/login-scene.jpg` à gauche et le formulaire à
droite. Sur mobile, le formulaire précède l'image.

Le logo officiel est conservé dans `landing/static/landing/images/dublao-logo.png`.
Le composant `dublao/templates/includes/brand_logo.html` l'affiche dans les
en-têtes, les popups, le pied de page et les pages du compte. Son cadrage et ses
dimensions sont définis dans `landing/static/landing/brand.css`. Le même fichier
est utilisé pour l'icône d'onglet.

Pour tester sans toucher PostgreSQL ou R2 : `env/Scripts/python.exe manage.py test comptes --settings=dublao.test_settings`.

### Profils utilisateurs

Chaque utilisateur possède un `Profile`, accessible par `user.profile`. Le signal
`post_save` dans `comptes/signals.py`, chargé par `ComptesConfig.ready()`, crée le
profil à la création du compte, y compris pour Google et les superutilisateurs.
Il ne réenregistre pas le profil lors des modifications ultérieures du compte.
La migration `0002_profiles_for_existing_users` complète les comptes existants.

La page `/comptes/profil/`, accessible depuis « Mon profil » dans l'espace,
permet de modifier le prénom, le nom, la biographie et la photo. L'email doit
être vérifié avant l'accès. Le prénom et le nom restent sur le modèle User ;
la biographie, la photo et les dates sont sur Profile. La page fonctionne avec
HTMX et avec un formulaire classique, et Alpine affiche un aperçu de la photo.

Les photos JPG, PNG et WebP n'ont pas de limite de poids dans le formulaire
(4096 pixels de côté maximum). Elles
sont redimensionnées à 512 pixels maximum, réencodées en PNG sans métadonnées,
puis enregistrées dans le stockage R2 privé existant sous un chemin aléatoire
`profiles/<user_id>/...`. Leur affichage utilise les URLs signées du stockage.
Une photo retirée ou remplacée est supprimée après validation de la transaction.
La suppression d'un compte supprime aussi son profil et sa photo. Si une
suppression R2 échoue, elle est journalisée et le fichier doit être nettoyé
ultérieurement. Les profils sont également consultables dans l'administration.

Référence : [URLs signées R2](https://developers.cloudflare.com/r2/api/s3/presigned-urls/).

Le studio utilise maintenant Murf Dub avec `job_id`, Celery et Redis. Il conserve
les sources, vidéos doublées et sous-titres dans R2, avec lecture et téléchargement
privés. Le portefeuille prépayé, ses cinq packs en dollars et l'intégration Genius
Pay sont décrits dans [le guide crédits et paiements](CREDITS_PAIEMENTS.md).
Les clés et la compatibilité de l'encaissement USD du compte Genius Pay restent
à vérifier avant activation des paiements réels.

Un aperçu HTML autonome de la landing page est fourni dans `preview/landing.html`.
Ouvrir ce fichier dans un navigateur permet de consulter le design sans lancer
Django ni se connecter à PostgreSQL. Ce fichier est un export de présentation :
les modifications du template nécessitent de régénérer cet export.

## Références

- [Murf Dub Automation API](https://murf.ai/api/docs/capabilities/dubbing)
- [Cloudflare R2 et boto3](https://developers.cloudflare.com/r2/examples/aws/boto3/)
- [Configuration S3 de django-storages](https://django-storages.readthedocs.io/en/latest/backends/amazon-S3.html)
