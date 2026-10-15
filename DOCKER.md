# Démarrer toute l'application avec Docker

Depuis la racine du projet, avec Docker Desktop démarré :

```powershell
docker compose up -d --build
docker compose ps
docker compose logs --tail=50 init web worker beat
```

Arrêter d'abord le `runserver` local s'il occupe le port 8000. Ouvrir ensuite
http://127.0.0.1:8000/. La première construction peut être longue.

Le service `init` applique les migrations puis collecte les fichiers statiques.
Sa sortie `Exited (0)` est normale. Django et Celery démarrent seulement après
sa réussite et la disponibilité de leurs dépendances. Nginx sert les fichiers
publics et transmet les autres requêtes à Gunicorn. R2 reste privé.

Nginx utilise le résolveur interne de Docker pour suivre les changements
d'adresse du service `web` après une reconstruction. Pour une modification de
`docker/nginx.conf`, valider avec `docker compose exec nginx nginx -t`, puis
recharger avec `docker compose exec nginx nginx -s reload`.

Le catalogue initial inclut désormais les 44 langues cibles confirmées avec
Murf. Une ancienne base Docker limitée à 13 langues peut être actualisée sans
créer de doublage avec `docker compose exec web python manage.py sync_murf_languages`.

Les valeurs PostgreSQL de `.env` initialisent une **nouvelle base Docker**.
La base locale Windows est conservée ; ses comptes, portefeuilles et projets
ne sont pas automatiquement copiés. La connexion des conteneurs utilise
`postgres:5432` et `redis:6379`, sans modifier le `.env` local. Pour créer
l'administrateur dans cette nouvelle base :

```powershell
docker compose exec web python manage.py createsuperuser
```

Pour transférer les données existantes, préparer une sauvegarde et une
restauration PostgreSQL avant de reprendre les doublages réels. Le changement
de base change également l'accès aux fichiers R2 référencés par ses projets.

Le volume `postgres-data` conserve la base après un arrêt. Modifier le mot
de passe dans `.env` après l'initialisation ne modifie pas celui de la base.
Les nouveaux volumes `redis-docker-data` et `beat-docker-data` isolent la file
et le planning de ce montage. Les anciens volumes sont conservés, sans reprise
automatique de leurs tâches contre la nouvelle base. Ne pas lancer un doublage
avant d'avoir vérifié cette transition.

Pour arrêter les services en conservant les volumes :

```powershell
docker compose down
```

Ne pas ajouter `-v` : cela supprimerait les volumes et leurs données.

Pour chaque changement de code, reconstruire avec `docker compose up -d --build`.
Un simple `restart` ne reconstruit pas l'image et ne rejoue pas la préparation.
Garder une seule instance Beat. `WEB_PORT` peut changer le port local, mais il
faut alors adapter les callbacks Google et l'URL publique de paiement.

Cette configuration HTTP locale ne remplace pas le déploiement HTTPS décrit
dans DEPLOIEMENT.md. Pour l'essai local, conserver `DEBUG=true`, les hôtes
`localhost,127.0.0.1` et les URLs de paiement/OAuth locales.
