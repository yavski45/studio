# Dublao — Contexte produit

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Les trois publics ont la même priorité, selon la décision explicite du propriétaire :

- Créateurs de contenu : adapter leurs vidéos, tutoriels et interviews à de nouvelles audiences.
- Formateurs en e-learning : proposer leurs cours, démonstrations et modules enregistrés dans plusieurs langues.
- Entrepreneurs et entreprises : adapter leurs présentations, démonstrations commerciales et formations aux clients, partenaires et équipes.

L'administrateur suit les visiteurs, les recettes et les alertes de recharge des crédits Murf.

## Product Purpose

Permettre à un utilisateur d'importer une vidéo, de choisir une ou plusieurs langues,
de lancer son doublage, puis de regarder et télécharger les versions dans son studio privé.
Le parcours doit rendre compréhensibles le coût en crédits, l'attente du traitement
et la disponibilité de chaque résultat.

## Positioning

Dublao propose un studio de doublage multilingue avec un portefeuille de crédits
rechargeable par achats ponctuels. Aucun abonnement mensuel ni prélèvement récurrent.
Ne pas inventer d'exclusivité, de comparaison de qualité ou de performance garantie.

## Operating Context

Application Django et PostgreSQL, avec HTMX, Alpine.js et Tailwind CSS via CDN.
Le traitement asynchrone utilise Celery et Redis. Les fichiers sont stockés dans
Cloudflare R2 privé. L'intégration Murf Dub suit les travaux par `job_id`, sans `project_id`.

Le développement se fait dans le projet principal `C:\Users\COMP2TECH\OneDrive\dubsaas`.
Ne pas créer un worktree pour les modifications courantes : le propriétaire veut
retrouver directement les fichiers modifiés dans son environnement habituel.

Surfaces existantes : accueil, inscription et connexion, confirmation email,
réinitialisation du mot de passe, profil, portefeuille, liste des doublages,
création et suivi dans le studio, administration métier et admin Django.

L'accès « Studio » doit ouvrir directement le formulaire et le lecteur sur
`/studio/`, selon la demande du propriétaire. L'historique « Mes doublages »
dispose d'un accès distinct sur `/studio/projets/`. Ne pas réintroduire un
bouton « Nouveau doublage » pointant vers `/studio/nouveau/` comme accès principal.

## Capabilities and Constraints

- Authentification par email et mot de passe, ou Google via django-allauth ; le studio vérifie que le compte dispose d'une adresse email vérifiée.
- Profil créé par les signaux Django ; photo sur R2. Le propriétaire a demandé de ne pas imposer de plafond de taille à la photo.
- Sélection multiple de langues avec leurs drapeaux. La configuration cible vérifiée pendant le développement contient 44 langues ; le nombre affiché doit provenir de cette configuration. Ne pas présenter ce nombre comme une garantie indépendante de l'offre Murf.
- Lecteur vidéo natif, timeline de lecture synchronisée et téléchargement des sorties disponibles. Le studio n'est pas un outil de montage vidéo.
- Le propriétaire veut expliquer que le doublage conserve l’identité vocale des intervenants à partir de leur voix originale. Présenter la parole traduite comme générée par l’IA, sans promettre une reproduction parfaitement identique ni suggérer le choix d’une voix générique. Sur la démonstration, afficher les boutons des langues sans les textes « Choisissez la langue de la démonstration » et « Démonstration préenregistrée · [langue] ».
- La waveform locale facultative utilise des données audio réellement décodées. Son analyse est limitée à 128 Mio et dépend du navigateur ; cette restriction ne limite pas l'import ni le doublage.
- Les états du traitement et le portefeuille viennent du backend. Ne pas inventer de pourcentage de progression ni d'état individuel d'une langue avant que le fournisseur ou les fichiers enregistrés ne le justifient.
- Les vidéos restent privées : accès contrôlé par propriétaire et liens temporaires. Les snapshots de présentation ne doivent pas exposer de secrets ou de clés de stockage.
- Un crédit utilisateur correspond à une minute entamée, par langue produite. Une vidéo de 1 minute et 1 seconde coûte 2 crédits par langue. Le serveur vérifie la durée et réserve le solde avant l'envoi à Murf.
- Les achats successifs s'ajoutent au portefeuille ; aucun remplacement du solde existant.
- Paiement via Genius Pay. Prix affichés en USD ; conversion et encaissement en XOF acceptés par le propriétaire. L'ajout des crédits exige une confirmation fiable du paiement, pas uniquement un retour du navigateur.
- Le webhook de paiement doit être accessible au fournisseur ; une adresse localhost ne permet pas sa réception depuis Internet. Ne pas affirmer qu'un déploiement public existe sans vérification.
- Alerte de recharge à 20 crédits Murf ou moins. Si le solde fournisseur est insuffisant, le doublage attend la recharge.
- L'administration affiche actuellement les recettes, pas les bénéfices nets.
- Pas de plafond de taille applicatif pour l'import vidéo (`STUDIO_MAX_UPLOAD_BYTES=0`) ni pour la copie des sorties. Les délais d'exécution et les contraintes du fournisseur et de l'infrastructure subsistent. Ne pas promettre un service illimité.
- La documentation Murf Dub consultée le 10 octobre 2026 indique une durée maximale d'une heure, une résolution jusqu'à 1080p et une concurrence dépendant du contrat. Elle ne confirme pas de taille maximale en Go. L'acceptation réelle d'un fichier de 2 Go n'a pas été validée. Ces limites doivent être revérifiées avant de nouvelles promesses produit.
- Une relance de projet ne doit pas contourner les protections existantes contre les doublages et débits répétés.

Catalogue confirmé d'achats ponctuels :

| Pack | Prix affiché | Crédits |
|---|---:|---:|
| Starter | 10 USD | 11 |
| Creator | 25 USD | 28 |
| Pro | 50 USD | 57 |
| Business | 150 USD | 175 |
| Studio | 300 USD | 360 |

## Brand Commitments

Nom : Dublao. Le propriétaire a fourni le logo vert et demandé une couleur de
marque semblable au vert de Django, puis un frontend sombre avec des accents verts.
La bibliothèque `/studio/projets/` fait exception : le propriétaire a demandé un fond clair, en conservant le vert de marque. Cette variante s’applique uniquement à « Mes doublages » et à sa navigation.
Ces engagements sont à préserver ; ce document ne définit pas un nouveau système visuel.

L'interface et la communication actuelles sont en français. La présentation doit
parler concrètement aux trois publics et expliquer le fonctionnement du service.
Les références demandées concernent les plateformes de doublage et les studios
professionnels, sans copier leurs marques ni afficher leurs fonctionnalités absentes.

## Evidence on Hand

- Logo fourni : `landing/static/landing/images/dublao-logo-green.png`.
- Contenu public et cas d'usage : `landing/templates/landing/home.html`.
- Catalogue des packs : `credits/catalog.py`.
- Comportement actuel du studio : `studio/STUDIO_INTERFACE.md` et les vues, modèles et tâches de l'application `studio`.
- Documentation du projet : `README.md`, `CREDITS_PAIEMENTS.md`, `studio/README.md`.
- Capture réelle de l'accueil : `preview/dublao-44-langues.jpg` ; elle constitue un instantané, pas une autorité sur de futurs changements.
- Le propriétaire a confirmé que le doublage fonctionne et que les vidéos doublées sont visibles.
- Aucun témoignage client, logo de client, chiffre d'adoption ou engagement de performance confirmé dans cette conversation. Ne pas en fabriquer.
- Référence des contraintes fournisseur : https://murf.ai/api/docs/capabilities/dubbing.

## Product Principles

1. Servir les créateurs, les formateurs et les entreprises au même niveau.
2. Rendre le coût par minute et par langue explicite avant le lancement.
3. Présenter l'état réel du travail et donner accès à chaque résultat disponible.
4. Préserver la confidentialité des fichiers et la fiabilité du portefeuille.
5. Proposer un parcours simple sans promettre de capacités non implémentées ou non vérifiées.
