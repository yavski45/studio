# Interface du studio

L'entrée « Studio », illustrée par une icône de moniteur vidéo, ouvre directement
le formulaire et le lecteur sur `/studio/`. « Mes doublages » ouvre l'historique
sur `/studio/projets/`. L'ancienne adresse `/studio/nouveau/` redirige les visites
vers `/studio/` ; les POST d'un formulaire déjà ouvert restent acceptés.

Les pages de création et de détail utilisent `editor_base.html`, Alpine et
le lecteur vidéo natif du navigateur. Les paramètres sont à gauche, le lecteur
et sa timeline au centre, les versions à droite. Sur mobile, le lecteur précède
les paramètres repliables et les versions.

La timeline reflète la lecture réelle : déplacement dans la vidéo, volume,
pause et plein écran. Elle ne propose pas de montage ou de modification audio.
L'analyse facultative d'un fichier local produit une waveform à partir des
échantillons décodés par Web Audio. Elle dépend du codec et du navigateur et
n'est pas proposée pour les fichiers de plus de 128 Mio afin de limiter la
mémoire utilisée. Cette restriction concerne uniquement l'analyse audio locale,
pas l'import ni le doublage. Les vidéos stockées et les sorties ne sont pas
décodées pour fabriquer une waveform.

Le fragment privé `status?view=studio` actualise les états toutes les dix secondes
pendant un travail actif, sans remplacer le lecteur. Une langue est terminée
uniquement lorsque son fichier a été enregistré. Le fournisseur ne donne pas
de progression individuelle exploitable pendant le travail : les autres états
suivent donc le projet, sans pourcentage inventé. La reprise concerne le projet
entier et reste limitée aux conditions déjà autorisées par le backend.

L'original est lu via une route privée supplémentaire, utilisant le même handler
et les mêmes contrôles que les sorties : propriétaire, email vérifié, lien R2
temporaire, absence de cache. Les snapshots contiennent des routes internes et
ne révèlent ni clé de stockage ni identifiant du fournisseur.

Les crédits affichés viennent du portefeuille. L'estimation locale arrondit à
la minute supérieure par langue ; Django/Celery vérifie toujours la durée et
réserve le solde avant de contacter Murf. Aucune règle de paiement n'est modifiée.

Le nombre de langues annoncé sur l'accueil et dans le studio est calculé à
partir des langues cibles configurées dans la base (44 actuellement).

La bibliothèque « Mes doublages » (`/studio/projets/`) utilise un fond blanc
cassé et le vert de marque, à la demande du propriétaire. Cette variante claire
reste limitée à cette page et à sa navigation. Les projets affichent leurs vrais
statuts, avec accès aux lecteurs et aux téléchargements privés. Le suivi HTMX
est suspendu pendant la lecture d'une vidéo pour préserver le lecteur.

Pour cette refonte, les 15 tests des vues et des lecteurs ont réussi, ainsi que
le rendu automatisé des six pages protégées. La vérification visuelle dans le
navigateur intégré n'a pas pu aboutir : `ERR_NETWORK_IO_SUSPENDED`.

Vérifications sans fournisseur réel :

```powershell
env\Scripts\python.exe manage.py test --settings=dublao.test_settings
node --test studio/tests_js/editor.test.cjs
env\Scripts\python.exe -m preview.check_frontend_pages
```
