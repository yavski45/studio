# Pages d'erreur Dublao

Les erreurs 400, 403, 404 et 500 utilisent les handlers du projet. Les refus
CSRF utilisent également la page 403. Ces pages sont bilingues, sans scripts
externes et sans lecture de la base, du portefeuille ou des messages de session.
Les exceptions et les paramètres des URL ne sont jamais affichés.

Avec `DEBUG=false`, Django affiche ces pages pour les erreurs réelles.
Avec `DEBUG=true`, les URL inexistantes affichent également la page 404 Dublao.
Les réponses JSON 404 restent inchangées. Les autres erreurs techniques de
développement restent disponibles.
Les aperçus `/erreurs/404/`, `/erreurs/500/`, `/erreurs/502/` et les autres codes
pris en charge sont accessibles uniquement en développement. Ils renvoient le
vrai code d'erreur et ne provoquent pas d'exception ni de panne du serveur.

Docker génère les versions statiques pendant la préparation, après
`collectstatic`. Nginx les sert pour ses propres erreurs 400, 403, 404, 500,
502, 503 et 504. Elles respectent le cookie `django_language` (`fr` ou `en`)
et restent disponibles quand Gunicorn est inaccessible. Ces réponses ne sont
pas converties en succès HTTP 200 et ne sont pas mises en cache.

Les réponses d'erreur renvoyées par Django et les réponses JSON des API ne sont
pas interceptées par Nginx. Aucun arrêt du serveur web n'est nécessaire pour
vérifier la page 502 : utiliser son aperçu en développement ou les tests isolés.

```powershell
docker compose up -d --build
docker compose exec nginx nginx -t
docker compose exec nginx nginx -s reload
```
