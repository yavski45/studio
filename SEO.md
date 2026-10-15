# Préparer le référencement de Dublao

## Déjà préparé

- Titres et descriptions en français et en anglais, annonçant le nombre réel
  de langues du catalogue de doublage.
- Pages publiques stables `/fr/` et `/en/`, indépendantes du cookie du visiteur.
- URL canonique, liens `hreflang` réciproques et version `x-default`.
- Aperçus de partage Open Graph et Twitter avec le logo officiel.
- Données structurées Organization et WebSite, sans notes ni avis inventés.
- `/robots.txt` et `/sitemap.xml`, limités aux pages publiques.
- Métadonnées et en-tête HTTP `noindex` sur les comptes, portefeuilles,
  le studio, les API et l'administration. L'authentification reste la protection
  des données privées ; robots.txt n'est pas un contrôle d'accès.

Le site local reste en `noindex`. Aucun domaine fictif, URL locale ou lien R2
signé n'est publié dans les balises de référencement ou dans le sitemap.
Changer la langue sur une page publique conserve le choix de l'utilisateur et
renvoie à l'accueil dans sa langue. Les URL des callbacks de paiement et Google
ne sont pas modifiées par les préfixes des pages publiques.

## Activation après hébergement

1. Choisir le domaine définitif, activer HTTPS et terminer les réglages Django
   de production décrits dans DEPLOIEMENT.md.
2. Ajouter dans l'environnement de production :

   ```dotenv
   DEBUG=false
   SITE_PUBLIC_URL=https://VOTRE-DOMAINE
   SEO_INDEXING_ENABLED=true
   ```

   SITE_PUBLIC_URL doit être le domaine réel, sans chemin, paramètres ou clés.
   Un site en DEBUG reste exclu même si SEO_INDEXING_ENABLED vaut true.
3. Vérifier les réponses HTTP 200 de `/fr/`, `/en/`, `/robots.txt` et
   `/sitemap.xml`, les balises canoniques et les redirections HTTPS du domaine.
4. Ajouter le domaine dans Google Search Console et valider la propriété via
   le DNS. Soumettre `https://VOTRE-DOMAINE/sitemap.xml` et inspecter les deux
   URL publiques. Faire l'équivalent dans Bing Webmaster Tools.
5. Suivre l'indexation, les erreurs d'exploration, les requêtes et les clics.

## Développer la visibilité

L'accueil présente les solutions pour les créateurs de contenu, le e-learning
et les entreprises. Pour développer le trafic, produire ensuite des pages
utiles et distinctes pour ces usages, avec de vrais exemples de doublage,
des guides de localisation et des réponses aux questions des utilisateurs.
Ne pas créer des dizaines de pages quasi identiques pour chaque langue.

Google décide de l'indexation et du classement. Les réglages techniques ne
garantissent pas la première place ; mesurer les résultats dans Search Console
après la mise en ligne. Aucune propriété Search Console ni modification DNS
n'a été créée pendant la préparation locale.

Références officielles :

- https://developers.google.com/search/docs/fundamentals/seo-starter-guide
- https://developers.google.com/search/docs/specialty/international/localized-versions
- https://developers.google.com/search/docs/crawling-indexing/sitemaps/overview
